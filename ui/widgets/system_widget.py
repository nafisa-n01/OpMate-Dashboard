"""
ui/widgets/system_widget.py
---------------------------
System overview widget showing hostname, OS, CPU, RAM, and uptime.

Features:
    - Mostly static info (hostname, OS, CPU model, RAM) — set once
    - Dynamic uptime and process/thread count — refreshed every 10 seconds
    - Simple key-value layout, no chart or table needed

Design:
    ┌─────────────────────────────────────────┐
    │ SYSTEM OVERVIEW                          │
    ├─────────────────────────────────────────┤
    │ Hostname:        DESKTOP-ABC1234         │
    │ OS:              Windows 10              │
    │ Architecture:    AMD64                   │
    │ CPU:             Intel Core i7-10700K    │
    │ Cores:           8                       │
    │ RAM:             16.0 GB                 │
    ├─────────────────────────────────────────┤
    │ Uptime:          5 days 12h 34m          │
    │ Processes:       187                     │
    │ Threads:         2341                    │
    └─────────────────────────────────────────┘
"""

import logging

from PyQt6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QFrame,
)
from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtGui import QFont

from core.data_models import SystemMetrics
from core.monitors.system_monitor import SystemMonitor
from ui.widgets.base_widget import BaseWidget


logger = logging.getLogger(__name__)


class SystemWidget(BaseWidget):
    """
    Widget displaying system overview information.

    Attributes:
        row_labels (dict): Maps field name -> QLabel (value side) for updates.
    """

    def __init__(self) -> None:
        """Initialize system widget."""
        super().__init__("System Overview")
        self.row_labels = {}
        self._setup_ui()
        logger.debug("SystemWidget initialized")

    def _setup_ui(self) -> None:
        """Build the UI layout."""
        main_layout = QVBoxLayout()
        self.setLayout(main_layout)

        # --- TITLE ---
        title_layout = QHBoxLayout()

        # TODO: Uncomment when you create system_icon.png
        # try:
        #     icon_pixmap = QPixmap("assets/icons/system_icon.png")
        #     if not icon_pixmap.isNull():
        #         icon_label = QLabel()
        #         icon_label.setPixmap(
        #             icon_pixmap.scaledToHeight(
        #                 32, Qt.TransformationMode.SmoothTransformation
        #             )
        #         )
        #         title_layout.addWidget(icon_label)
        # except Exception as e:
        #     logger.warning("Could not load system icon: %s", e)

        title = QLabel("SYSTEM OVERVIEW")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet("color: #88ccff;")  # Blue-ish
        title_layout.addWidget(title)
        title_layout.addStretch()

        main_layout.addLayout(title_layout)

        # --- INFO CONTAINER ---
        container = QFrame()
        container.setStyleSheet(
            "background-color: #1f1f2e; border-radius: 6px; padding: 10px;"
        )
        info_layout = QVBoxLayout()
        info_layout.setSpacing(6)
        container.setLayout(info_layout)

        # Define rows: (internal key, display label)
        static_rows = [
            ("hostname", "Hostname"),
            ("os", "Operating System"),
            ("architecture", "Architecture"),
            ("cpu_model", "Processor"),
            ("cpu_cores", "CPU Cores"),
            ("ram_total", "Total RAM"),
        ]
        dynamic_rows = [
            ("uptime", "Uptime"),
            ("processes", "Active Processes"),
            ("threads", "Active Threads"),
        ]

        for key, label_text in static_rows:
            info_layout.addLayout(self._create_row(key, label_text))

        # Divider between static and dynamic info
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet("background-color: #3d3d52;")
        divider.setFixedHeight(1)
        info_layout.addWidget(divider)

        for key, label_text in dynamic_rows:
            info_layout.addLayout(self._create_row(key, label_text))

        main_layout.addWidget(container)
        main_layout.setContentsMargins(12, 12, 12, 12)

    def _create_row(self, key: str, label_text: str) -> QHBoxLayout:
        """
        Create a single key-value row (e.g., "Hostname: DESKTOP-ABC1234").

        Args:
            key: Internal identifier used to look up this row's value label later.
            label_text: Human-readable label shown on the left side.

        Returns:
            QHBoxLayout: The row, ready to add to a parent layout.
        """
        row_layout = QHBoxLayout()

        label = QLabel(f"{label_text}:")
        label.setStyleSheet("color: #aaaaaa;")
        label.setFixedWidth(140)
        row_layout.addWidget(label)

        value_label = QLabel("--")
        value_label.setStyleSheet("color: #ffffff; font-weight: bold;")
        row_layout.addWidget(value_label)

        row_layout.addStretch()

        # Store reference so update_data() can find and update this later
        self.row_labels[key] = value_label

        return row_layout

    @pyqtSlot(SystemMetrics)
    def update_data(self, metrics: SystemMetrics) -> None:
        """
        Update widget with new system metrics.

        Called when WorkerThread emits metrics_updated_system signal
        (every 10 seconds — this data changes slowly, see system_monitor.py).

        Args:
            metrics: SystemMetrics snapshot from monitor.
        """
        try:
            self.row_labels["hostname"].setText(metrics.hostname)
            self.row_labels["os"].setText(
                f"{metrics.os_name} {metrics.os_version}"
            )
            self.row_labels["architecture"].setText(metrics.os_architecture)
            self.row_labels["cpu_model"].setText(metrics.cpu_model or "Unknown")
            self.row_labels["cpu_cores"].setText(str(metrics.cpu_core_count))
            self.row_labels["ram_total"].setText(f"{metrics.ram_total_gb:.1f} GB")

            uptime_str = SystemMonitor.format_uptime(metrics.uptime_seconds)
            self.row_labels["uptime"].setText(uptime_str)
            self.row_labels["processes"].setText(str(metrics.total_processes))
            self.row_labels["threads"].setText(str(metrics.total_threads))

            logger.debug("SystemWidget updated: uptime=%s", uptime_str)

        except Exception as e:
            logger.error("Error updating system widget: %s", e)
            self.show_error(str(e))