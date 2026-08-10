"""
ui/widgets/process_widget.py
-----------------------------
Running processes widget showing top 10 by memory usage in a table.

Features:
    - Sortable-looking table: PID, Name, User, Memory, Status
    - Color-coded status text
    - Total process count shown below table
    - Updates every 2 seconds

Design:
    ┌──────────────────────────────────────────────┐
    │ RUNNING PROCESSES (Top 10 by Memory)          │
    ├──────────────────────────────────────────────┤
    │ PID   Name          User    Memory    Status │
    │ 1234  chrome.exe    Admin   520 MB    running│
    │ 5678  firefox.exe   Admin   892 MB    running│
    │ ...                                            │
    ├──────────────────────────────────────────────┤
    │ Total processes: 187                          │
    └──────────────────────────────────────────────┘
"""

import logging

from PyQt6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QAbstractItemView,
)
from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtGui import QFont, QColor

from core.data_models import ProcessMetrics
from ui.widgets.base_widget import BaseWidget


logger = logging.getLogger(__name__)

# Table column indices (named constants avoid "magic numbers" scattered in code)
COL_PID = 0
COL_NAME = 1
COL_USER = 2
COL_MEMORY = 3
COL_STATUS = 4


class ProcessWidget(BaseWidget):
    """
    Widget displaying top 10 running processes by memory usage.

    Attributes:
        table (QTableWidget): The process table.
        total_label (QLabel): Shows total process count on the system.
    """

    def __init__(self) -> None:
        """Initialize process widget."""
        super().__init__("Process Monitor")
        self._setup_ui()
        logger.debug("ProcessWidget initialized")

    def _setup_ui(self) -> None:
        """Build the UI layout."""
        main_layout = QVBoxLayout()
        self.setLayout(main_layout)

        # --- TITLE ---
        title_layout = QHBoxLayout()

        # TODO: Uncomment when you create process_icon.png
        # try:
        #     icon_pixmap = QPixmap("assets/icons/process_icon.png")
        #     if not icon_pixmap.isNull():
        #         icon_label = QLabel()
        #         icon_label.setPixmap(
        #             icon_pixmap.scaledToHeight(
        #                 32, Qt.TransformationMode.SmoothTransformation
        #             )
        #         )
        #         title_layout.addWidget(icon_label)
        # except Exception as e:
        #     logger.warning("Could not load process icon: %s", e)

        title = QLabel("RUNNING PROCESSES (Top 10 by Memory)")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet("color: #ffaa88;")  # Orange-ish
        title_layout.addWidget(title)
        title_layout.addStretch()

        main_layout.addLayout(title_layout)

        # --- TABLE ---
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(
            ["PID", "Process Name", "User", "Memory", "Status"]
        )
        self.table.setRowCount(10)  # Fixed 10 rows (top 10 processes)

        # Table behavior settings
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )  # Read-only
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.table.verticalHeader().setVisible(False)  # Hide row numbers (we have PID)
        self.table.setAlternatingRowColors(True)

        # Column sizing: Name column stretches, others fit content
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(COL_PID, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(COL_NAME, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(COL_USER, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(COL_MEMORY, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(COL_STATUS, QHeaderView.ResizeMode.ResizeToContents)

        self.table.setStyleSheet(
            """
            QTableWidget {
                background-color: #1f1f2e;
                color: #c0c0d0;
                gridline-color: #3d3d52;
                border: 1px solid #3d3d52;
            }
            QTableWidget::item {
                padding: 6px;
            }
            QTableWidget::item:alternate {
                background-color: #262638;
            }
            QTableWidget::item:selected {
                background-color: #5d5d72;
            }
            QHeaderView::section {
                background-color: #3d3d52;
                color: #ffffff;
                padding: 6px;
                border: none;
                font-weight: bold;
            }
        """
        )

        # Give the table a reasonable minimum height so it doesn't
        # collapse to nothing inside the scrollable dashboard
        self.table.setMinimumHeight(320)

        main_layout.addWidget(self.table)

        # --- FOOTER: TOTAL PROCESS COUNT ---
        self.total_label = QLabel("Total processes: --")
        self.total_label.setStyleSheet("color: #aaaaaa; font-size: 11px;")
        self.total_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        main_layout.addWidget(self.total_label)

        main_layout.setContentsMargins(12, 12, 12, 12)

    @pyqtSlot(ProcessMetrics)
    def update_data(self, metrics: ProcessMetrics) -> None:
        """
        Update table with new process metrics.

        Rewrites all 10 rows each update. Unlike the disk widget (rows
        persist per-device), process rows must be fully replaced each time
        because *which* processes occupy the top 10 changes constantly as
        processes launch, exit, and use varying memory.

        Args:
            metrics: ProcessMetrics snapshot from monitor.
        """
        try:
            processes = metrics.processes

            for row_index in range(10):
                if row_index < len(processes):
                    proc = processes[row_index]
                    self._fill_row(row_index, proc)
                else:
                    self._clear_row(row_index)

            self.total_label.setText(f"Total processes: {metrics.total_processes}")

            logger.debug(
                "ProcessWidget updated: %d processes shown, %d total",
                len(processes),
                metrics.total_processes,
            )

        except Exception as e:
            logger.error("Error updating process widget: %s", e)
            self.show_error(str(e))

    def _fill_row(self, row: int, proc) -> None:
        """
        Fill a table row with process data.

        Args:
            row: Row index (0-9).
            proc: ProcessInfo object.
        """
        # PID column
        pid_text = str(proc.pid) if proc.pid is not None else "?"
        pid_item = QTableWidgetItem(pid_text)
        pid_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.table.setItem(row, COL_PID, pid_item)

        # Name column
        name_item = QTableWidgetItem(proc.name)
        self.table.setItem(row, COL_NAME, name_item)

        # User column
        user_item = QTableWidgetItem(proc.username or "N/A")
        self.table.setItem(row, COL_USER, user_item)

        # Memory column: "520.3 MB (3.2%)"
        memory_item = QTableWidgetItem(
            f"{proc.memory_mb:.1f} MB ({proc.memory_percent:.1f}%)"
        )
        memory_item.setTextAlignment(Qt.AlignmentFlag.AlignRight)
        self.table.setItem(row, COL_MEMORY, memory_item)

        # Status column, color-coded
        status_item = QTableWidgetItem(proc.status)
        status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        status_item.setForeground(self._status_color(proc.status))
        self.table.setItem(row, COL_STATUS, status_item)

    def _clear_row(self, row: int) -> None:
        """
        Clear a table row (used when fewer than 10 processes exist).

        Args:
            row: Row index to clear.
        """
        for col in range(5):
            self.table.setItem(row, col, QTableWidgetItem(""))

    def _status_color(self, status: str) -> QColor:
        """
        Get display color for a process status.

        Args:
            status: Process status string ("running", "sleeping", "zombie", etc.)

        Returns:
            QColor: Color to use for status text.
        """
        status_lower = status.lower()
        if status_lower == "running":
            return QColor("#88ff88")  # Green
        elif status_lower == "sleeping":
            return QColor("#aaaaaa")  # Gray
        elif status_lower == "zombie":
            return QColor("#ff8888")  # Red
        else:
            return QColor("#c0c0d0")  # Default light gray