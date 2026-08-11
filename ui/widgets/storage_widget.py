r"""
ui/widgets/storage_widget.py
------------------------------
Storage Analyzer widget: lets the user pick a folder, scan it, and
drill down through subfolders to see what's taking up space.

Design:
    ┌───────────────────────────────────────────────────┐
    │ STORAGE ANALYZER                                    │
    │  Path: C:\Users\you           [Back] [Rescan] [Scan]│
    │  ┌─────────────────────────────────────────────────┐│
    │  │ Documents        2.3 GB   [████████░░] 46%      ││
    │  │ Downloads        1.1 GB   [████░░░░░░] 22%      ││
    │  │ Pictures         0.4 GB   [██░░░░░░░░]  8%      ││
    │  │ ...                                              ││
    │  └─────────────────────────────────────────────────┘│
    └───────────────────────────────────────────────────┘

Navigation:
    Clicking a folder row drills into it: if that folder was already
    scanned (has children populated from the parent scan's depth
    limit), we just display its children. If not yet scanned (a
    "placeholder" node from hitting MAX_SCAN_DEPTH), a fresh
    StorageScanThread scans it on demand before showing its contents.
    "Back" pops the navigation stack to return to the parent folder.
"""

import logging
import os
from typing import Dict, List, Optional

from PyQt6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QWidget,
    QFrame,
    QProgressBar,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from core.storage.models import DirectoryNode
from core.storage_worker_thread import StorageScanThread
from ui.widgets.base_widget import BaseWidget
from ui.styles.fonts import get_pixel_font_family


logger = logging.getLogger(__name__)

# How many levels deep each scan (initial or drill-down) goes before
# stopping — matches analyzer.py's MAX_SCAN_DEPTH default.
SCAN_DEPTH = 2

# Card color palette (shared visual language with CPU/RAM/Disk widgets)
CARD_BORDER_COLOR = "#6a6a9a"
CARD_BACKGROUND_COLOR = "#3d3d5c"
CARD_INNER_BACKGROUND = "#2a2a44"
ACCENT_COLOR = "#ffcc66"  # Amber/gold, Storage's accent color

BUTTON_STYLE = f"""
    QPushButton {{
        background-color: {CARD_INNER_BACKGROUND};
        color: #ffffff;
        border: 1px solid {CARD_BORDER_COLOR};
        border-radius: 6px;
        padding: 6px 14px;
    }}
    QPushButton:hover {{
        background-color: #4a4a6c;
    }}
    QPushButton:disabled {{
        color: #666666;
    }}
"""


class StorageWidget(BaseWidget):
    """
    Widget for browsing folder sizes with drill-down navigation.

    Attributes:
        nav_stack (List[DirectoryNode]): Folders visited, root to
            current — nav_stack[-1] is the currently displayed folder.
            Used to support the "Back" button.
        current_thread (Optional[StorageScanThread]): The in-flight
            scan thread, if any. Kept referenced so Qt doesn't garbage
            collect it mid-scan, and to avoid starting a second scan
            while one is already running.
    """

    def __init__(self) -> None:
        """Initialize storage widget."""
        super().__init__("Storage Analyzer")
        self._pixel_font = get_pixel_font_family()
        self.nav_stack: List[DirectoryNode] = []
        self.current_thread: Optional[StorageScanThread] = None
        self._row_widgets: Dict[str, dict] = {}
        self._setup_ui()
        logger.debug("StorageWidget initialized")

    def _setup_ui(self) -> None:
        """Build the card-style UI layout."""
        outer_layout = QVBoxLayout()
        outer_layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(outer_layout)

        # --- CARD CONTAINER ---
        card = QFrame()
        card.setStyleSheet(
            f"""
            QFrame {{
                background-color: {CARD_BACKGROUND_COLOR};
                border: 2px solid {CARD_BORDER_COLOR};
                border-radius: 14px;
            }}
        """
        )
        card_layout = QVBoxLayout()
        card_layout.setContentsMargins(20, 16, 20, 16)
        card_layout.setSpacing(10)
        card.setLayout(card_layout)

        outer_layout.addWidget(card)

        # --- TITLE ---
        title = QLabel("STORAGE ANALYZER")
        title.setFont(QFont(self._pixel_font, 11))
        title.setStyleSheet(f"color: {ACCENT_COLOR}; border: none;")
        card_layout.addWidget(title)

        # --- PATH + CONTROLS ROW ---
        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(8)

        self.path_label = QLabel("No folder scanned yet")
        self.path_label.setFont(QFont(self._pixel_font, 7))
        self.path_label.setStyleSheet("color: #aaaaaa; border: none;")
        controls_layout.addWidget(self.path_label, stretch=1)

        self.back_button = QPushButton("Back")
        self.back_button.setFont(QFont(self._pixel_font, 7))
        self.back_button.setStyleSheet(BUTTON_STYLE)
        self.back_button.setEnabled(False)
        self.back_button.clicked.connect(self._go_back)
        controls_layout.addWidget(self.back_button)

        self.rescan_button = QPushButton("Rescan")
        self.rescan_button.setFont(QFont(self._pixel_font, 7))
        self.rescan_button.setStyleSheet(BUTTON_STYLE)
        self.rescan_button.setEnabled(False)
        self.rescan_button.clicked.connect(self._rescan_current)
        controls_layout.addWidget(self.rescan_button)

        self.scan_button = QPushButton("Scan Home Folder")
        self.scan_button.setFont(QFont(self._pixel_font, 7))
        self.scan_button.setStyleSheet(BUTTON_STYLE)
        self.scan_button.clicked.connect(self._start_initial_scan)
        controls_layout.addWidget(self.scan_button)

        card_layout.addLayout(controls_layout)

        # --- STATUS LABEL (shows "Scanning..." / error messages) ---
        self.status_label = QLabel("")
        self.status_label.setFont(QFont(self._pixel_font, 7))
        self.status_label.setStyleSheet("color: #ffcc66; border: none;")
        self.status_label.hide()
        card_layout.addWidget(self.status_label)

        # --- SCROLLABLE FOLDER LIST ---
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setMinimumHeight(320)
        scroll_area.setStyleSheet(
            f"""
            QScrollArea {{
                background-color: {CARD_INNER_BACKGROUND};
                border: 1px solid {CARD_BORDER_COLOR};
                border-radius: 8px;
            }}
        """
        )

        list_container = QWidget()
        self.list_layout = QVBoxLayout()
        self.list_layout.setSpacing(6)
        self.list_layout.setContentsMargins(10, 10, 10, 10)
        self.list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        list_container.setLayout(self.list_layout)

        self.empty_label = QLabel("Click 'Scan Home Folder' to begin.")
        self.empty_label.setFont(QFont(self._pixel_font, 7))
        self.empty_label.setStyleSheet("color: #888888; border: none;")
        self.list_layout.addWidget(self.empty_label)

        scroll_area.setWidget(list_container)
        card_layout.addWidget(scroll_area)

    # ------------------------------------------------------------------
    # Scan triggering
    # ------------------------------------------------------------------

    def _start_initial_scan(self) -> None:
        """Start a fresh scan rooted at the user's home folder."""
        home_path = os.path.expanduser("~")
        self.nav_stack = []
        self._run_scan(home_path)

    def _rescan_current(self) -> None:
        """Re-scan the folder currently being viewed."""
        if not self.nav_stack:
            return
        current_path = self.nav_stack[-1].path
        # Drop the stale node; the scan result will replace it in place
        # once complete (see _on_scan_complete).
        self._run_scan(current_path, replace_top=True)

    def _drill_into(self, node: DirectoryNode) -> None:
        """
        Navigate into a child folder, scanning it first if needed.

        Args:
            node: The DirectoryNode the user clicked on.
        """
        already_scanned = len(node.children) > 0 or node.file_count > 0

        if already_scanned:
            self.nav_stack.append(node)
            self._render_current_level()
        else:
            # Placeholder node from hitting the parent scan's depth
            # limit — scan it now, on demand.
            self.nav_stack.append(node)
            self._run_scan(node.path, replace_top=True)

    def _go_back(self) -> None:
        """Return to the previous (parent) folder in the nav stack."""
        if len(self.nav_stack) > 1:
            self.nav_stack.pop()
            self._render_current_level()

    def _run_scan(self, path: str, replace_top: bool = False) -> None:
        """
        Kick off a background scan for the given path.

        Args:
            path: Folder to scan.
            replace_top: If True, the scan result replaces the current
                top of nav_stack in place (used for drill-down and
                rescan); if False, this is treated as a brand-new root
                scan (used for the initial "Scan Home Folder" click).
        """
        if self.current_thread is not None and self.current_thread.isRunning():
            logger.debug("Scan already in progress, ignoring new request")
            return

        self._set_scanning_state(True)

        self.current_thread = StorageScanThread(path, SCAN_DEPTH)
        self.current_thread.scan_complete.connect(
            lambda result: self._on_scan_complete(result, replace_top)
        )
        self.current_thread.scan_error.connect(self._on_scan_error)
        self.current_thread.start()

    # ------------------------------------------------------------------
    # Scan result handling
    # ------------------------------------------------------------------

    def _on_scan_complete(self, result: DirectoryNode, replace_top: bool) -> None:
        """
        Handle a finished scan.

        Args:
            result: The freshly-scanned DirectoryNode tree.
            replace_top: Whether this scan should replace the current
                top of nav_stack (drill-down/rescan) or become a new
                root (initial scan).
        """
        self._set_scanning_state(False)

        if replace_top and self.nav_stack:
            # Preserve the parent link so "Back" and percent_of_parent()
            # still work correctly after swapping in the fresh data.
            result.parent = self.nav_stack[-1].parent
            self.nav_stack[-1] = result
        else:
            self.nav_stack = [result]

        self._render_current_level()
        logger.info("Storage scan complete: %s", result.path)

    def _on_scan_error(self, message: str) -> None:
        """Handle a failed scan by showing the error inline."""
        self._set_scanning_state(False)
        self.status_label.setText(f"Scan failed: {message}")
        self.status_label.show()
        logger.error("Storage scan error: %s", message)

    def _set_scanning_state(self, scanning: bool) -> None:
        """Toggle button states and status text while a scan runs."""
        self.scan_button.setEnabled(not scanning)
        self.rescan_button.setEnabled(not scanning and len(self.nav_stack) > 0)
        self.back_button.setEnabled(not scanning and len(self.nav_stack) > 1)

        if scanning:
            self.status_label.setText("Scanning...")
            self.status_label.show()
        else:
            self.status_label.hide()

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _render_current_level(self) -> None:
        """Redraw the folder list for the current top of nav_stack."""
        if not self.nav_stack:
            return

        current = self.nav_stack[-1]

        self.path_label.setText(current.path)
        self.rescan_button.setEnabled(True)
        self.back_button.setEnabled(len(self.nav_stack) > 1)

        # Clear existing rows
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._row_widgets.clear()

        if not current.children:
            empty_label = QLabel("No subfolders here.")
            empty_label.setFont(QFont(self._pixel_font, 7))
            empty_label.setStyleSheet("color: #888888; border: none;")
            self.list_layout.addWidget(empty_label)
            return

        for child in current.children:
            row = self._create_folder_row(child)
            self.list_layout.addWidget(row)

    def _create_folder_row(self, node: DirectoryNode) -> QFrame:
        """
        Build one clickable row representing a folder.

        Args:
            node: The DirectoryNode this row represents.

        Returns:
            QFrame: The completed row, ready to add to the list layout.
        """
        row = QFrame()
        row.setCursor(Qt.CursorShape.PointingHandCursor)
        row.setStyleSheet(
            f"""
            QFrame {{
                background-color: {CARD_BACKGROUND_COLOR};
                border: 1px solid {CARD_BORDER_COLOR};
                border-radius: 8px;
            }}
            QFrame:hover {{
                background-color: #4a4a6c;
            }}
        """
        )

        row_layout = QHBoxLayout()
        row_layout.setContentsMargins(12, 8, 12, 8)
        row_layout.setSpacing(10)
        row.setLayout(row_layout)

        icon_prefix = "🔒 " if not node.is_accessible else ""
        name_label = QLabel(f"{icon_prefix}{node.name}")
        name_label.setFont(QFont(self._pixel_font, 8))
        name_label.setStyleSheet("color: #ffffff; border: none;")
        name_label.setFixedWidth(180)
        row_layout.addWidget(name_label)

        bar = QProgressBar()
        bar.setMaximum(100)
        bar.setValue(int(node.percent_of_parent()))
        bar.setTextVisible(False)
        bar.setFixedHeight(14)
        self._style_pill_bar(bar, self._severity_color(node.percent_of_parent()))
        row_layout.addWidget(bar, stretch=1)

        size_label = QLabel(self._format_size(node.size_bytes))
        size_label.setFont(QFont(self._pixel_font, 7))
        size_label.setStyleSheet("color: #cccccc; border: none;")
        size_label.setFixedWidth(70)
        size_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        row_layout.addWidget(size_label)

        percent_label = QLabel(f"{node.percent_of_parent():.0f}%")
        percent_label.setFont(QFont(self._pixel_font, 7))
        percent_label.setStyleSheet("color: #cccccc; border: none;")
        percent_label.setFixedWidth(40)
        percent_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        row_layout.addWidget(percent_label)

        row.mousePressEvent = lambda event, n=node: self._drill_into(n)

        return row

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _style_pill_bar(self, bar: QProgressBar, color: str) -> None:
        """Apply the padded, pill-shaped bar style used across the dashboard."""
        bar.setStyleSheet(
            f"""
            QProgressBar {{
                background-color: {CARD_INNER_BACKGROUND};
                border: 1px solid {CARD_BORDER_COLOR};
                border-radius: 6px;
            }}
            QProgressBar::chunk {{
                background-color: {color};
                border-radius: 5px;
            }}
        """
        )

    def _severity_color(self, percent: float) -> str:
        """Get a color string based on how much of the parent this folder uses."""
        if percent < 15:
            return "#88ff88"
        elif percent < 40:
            return "#ffff88"
        elif percent < 70:
            return "#ffaa66"
        else:
            return "#ff8888"

    def _format_size(self, size_bytes: int) -> str:
        """Format a byte count as a human-readable string (MB or GB)."""
        gb = size_bytes / (1024 ** 3)
        if gb >= 1:
            return f"{gb:.1f} GB"
        mb = size_bytes / (1024 ** 2)
        return f"{mb:.0f} MB"

    def update_data(self, data) -> None:
        """
        Not used — StorageWidget is on-demand (user-triggered), not
        driven by WorkerThread's continuous polling signals like the
        other dashboard widgets. Present only to satisfy BaseWidget's
        interface.
        """
        pass