"""
ui/main_window.py
-----------------
Main application window controller.

Responsibilities:
    - Create the main window and set its properties
    - Build the tab-based interface (Dashboard, Processes, Storage)
    - Instantiate the background worker thread
    - Connect worker signals to widget slots (glue layer between core and UI)
    - Handle cleanup when the app closes

Layout design:
    Flat, minimalist framing — a single background color throughout,
    with generous margins providing breathing room instead of a boxed
    "panel within a panel" look. Tabs use an underline style (no filled
    background) to keep navigation lightweight, styled in the same
    pixel font used across all the metric cards, each with a small
    matching icon (dashboard/process/storage).

    An animated pixel-art GIF sits beside the CPU widget (outside its
    card border), aligned with the card on the dashboard.
"""

import logging
import os
from typing import Optional

from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTabWidget,
    QScrollArea,
    QLabel,
)
from PyQt6.QtCore import Qt, QSize, QTimer
from PyQt6.QtGui import QIcon, QMovie

from core.worker_thread import WorkerThread
from ui.widgets.placeholder_widget import PlaceholderWidget
from ui.widgets.cpu_widget import CPUWidget
from ui.widgets.memory_widget import MemoryWidget
from ui.widgets.disk_widget import DiskWidget
from ui.widgets.process_widget import ProcessWidget
from ui.widgets.system_widget import SystemWidget
from ui.widgets.storage_widget import StorageWidget
from ui.styles.fonts import get_pixel_font_family


logger = logging.getLogger(__name__)

# Single background color for the entire window — no separate "panel" box
BACKGROUND_COLOR = "#22222f"

# Accent color used for the active tab's underline
ACCENT_COLOR = "#8a8aff"

# Outer margin: space between the window edge and all content
OUTER_MARGIN = 40

# Vertical gap between stacked widget cards (CPU, RAM, Disk, System)
CARD_SPACING = 24

# Padding around the scrollable dashboard content itself
DASHBOARD_MARGIN = 4

# Tab bar icons (one per top-level tab)
DASHBOARD_ICON_PATH = os.path.join("assets", "icons", "dashboard_icon.png")
PROCESS_ICON_PATH = os.path.join("assets", "icons", "process_icon.png")
STORAGE_ICON_PATH = os.path.join("assets", "icons", "storage_icon.png")
TAB_ICON_SIZE = QSize(18, 18)

# Animated decorative GIF placed beside the CPU widget (outside its card border)
MAIN_ICON_PATH = os.path.join("assets", "icons", "main_icon.gif")
MAIN_ICON_SIZE = QSize(175, 112)  # same footprint as the previous static image

# Horizontal gap between the CPU widget and its adjacent image
CPU_ROW_SPACING = 20

# Vertical gap between the decorative image and the caption label below it
ICON_CAPTION_SPACING = 6


class MainWindow(QMainWindow):
    """
    Main application window.

    Attributes:
        worker (WorkerThread): Background thread that continuously polls system metrics.
        update_timer (QTimer): Timer to update UI at intervals (fallback if signals fail).
        cpu_widget (CPUWidget): Displays live CPU usage.
        memory_widget (MemoryWidget): Displays live RAM/Swap usage.
        disk_widget (DiskWidget): Displays disk partition usage.
        process_widget (ProcessWidget): Displays top 10 processes by memory.
        system_widget (SystemWidget): Displays system overview info.
        main_icon_movie (QMovie): Animated GIF played beside the CPU widget.
    """

    def __init__(self) -> None:
        """Initialize the main window."""
        super().__init__()
        self.setWindowTitle("SystemWatch — System Dashboard")
        self.setGeometry(100, 100, 1400, 900)  # x, y, width, height

        self.worker: Optional[WorkerThread] = None
        self.update_timer = QTimer()
        self._pixel_font = get_pixel_font_family()
        self.main_icon_movie: Optional[QMovie] = None

        self._setup_ui()
        self._start_worker()
        self._connect_signals()

        logger.info("MainWindow initialized")

    def _setup_ui(self) -> None:
        """
        Build the entire UI layout.

        Structure:
            QMainWindow
              └─ central_widget (flat background, provides the outer margin)
                   └─ QTabWidget (underline-style tabs, pixel font, no filled panel)
                        └─ dashboard_content (cards with generous gaps)
                             └─ cpu_row (CPU widget + animated GIF, side by side)
        """
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        central_widget.setStyleSheet(f"background-color: {BACKGROUND_COLOR};")

        central_layout = QVBoxLayout()
        central_layout.setContentsMargins(
            OUTER_MARGIN, OUTER_MARGIN, OUTER_MARGIN, OUTER_MARGIN
        )
        central_widget.setLayout(central_layout)

        # --- TABS ---
        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.TabPosition.North)
        self.tabs.setIconSize(TAB_ICON_SIZE)

        # --- DASHBOARD TAB (scrollable container for overview widgets) ---
        dashboard_content = QWidget()
        dashboard_layout = QVBoxLayout()
        dashboard_layout.setContentsMargins(
            DASHBOARD_MARGIN, DASHBOARD_MARGIN, DASHBOARD_MARGIN, DASHBOARD_MARGIN
        )
        dashboard_layout.setSpacing(CARD_SPACING)
        dashboard_content.setLayout(dashboard_layout)

        # Create overview widgets (process table lives in its own tab)
        self.cpu_widget = CPUWidget()
        self.memory_widget = MemoryWidget()
        self.disk_widget = DiskWidget()
        self.system_widget = SystemWidget()

        # --- CPU ROW: CPU widget + animated GIF side by side ---
        cpu_row_layout = QHBoxLayout()
        cpu_row_layout.setSpacing(CPU_ROW_SPACING)
        cpu_row_layout.addWidget(self.cpu_widget, stretch=1)

        # Wrap the image and its caption in a vertical layout so the
        # caption sits directly under the image
        icon_column_layout = QVBoxLayout()
        icon_column_layout.setSpacing(ICON_CAPTION_SPACING)
        icon_column_layout.setContentsMargins(0, 0, 0, 0)

        icon_label = QLabel()
        icon_label.setFixedSize(MAIN_ICON_SIZE)
        icon_label.setStyleSheet("border: none;")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.main_icon_movie = QMovie(MAIN_ICON_PATH)
        if self.main_icon_movie.isValid():
            self.main_icon_movie.setScaledSize(MAIN_ICON_SIZE)
            icon_label.setMovie(self.main_icon_movie)
            self.main_icon_movie.start()
        else:
            logger.warning("Main icon GIF not found or invalid at '%s'", MAIN_ICON_PATH)

        icon_caption_label = QLabel("Your current PC operations")
        icon_caption_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_caption_label.setStyleSheet(
            f"""
            color: #888899;
            font-family: '{self._pixel_font}';
            font-size: 8pt;
            border: none;
            """
        )

        icon_column_layout.addWidget(icon_label, alignment=Qt.AlignmentFlag.AlignHCenter)
        icon_column_layout.addWidget(icon_caption_label, alignment=Qt.AlignmentFlag.AlignHCenter)

        # Center the image column vertically alongside the CPU card
        cpu_row_layout.addLayout(icon_column_layout)

        dashboard_layout.addLayout(cpu_row_layout)
        dashboard_layout.addWidget(self.memory_widget)
        dashboard_layout.addWidget(self.disk_widget)
        dashboard_layout.addWidget(self.system_widget)

        dashboard_scroll = QScrollArea()
        dashboard_scroll.setWidgetResizable(True)
        dashboard_scroll.setWidget(dashboard_content)
        dashboard_scroll.setStyleSheet(
            "QScrollArea { background-color: transparent; border: none; }"
        )

        # --- PROCESSES TAB ---
        processes_content = QWidget()
        processes_layout = QVBoxLayout()
        processes_layout.setContentsMargins(
            DASHBOARD_MARGIN, DASHBOARD_MARGIN, DASHBOARD_MARGIN, DASHBOARD_MARGIN
        )
        processes_content.setLayout(processes_layout)

        self.process_widget = ProcessWidget()
        processes_layout.addWidget(self.process_widget)

        # --- STORAGE TAB ---
        self.tab_storage = StorageWidget()

        self.tabs.addTab(dashboard_scroll, QIcon(DASHBOARD_ICON_PATH), "Dashboard")
        self.tabs.addTab(processes_content, QIcon(PROCESS_ICON_PATH), "Processes")
        self.tabs.addTab(self.tab_storage, QIcon(STORAGE_ICON_PATH), "Storage")

        central_layout.addWidget(self.tabs)

        # Minimalist underline-style tabs, using the pixel font so the
        # navigation matches the same visual language as the metric cards
        self.tabs.setStyleSheet(
            f"""
            QTabWidget::pane {{
                background-color: transparent;
                border: none;
            }}
            QTabBar::tab {{
                background-color: transparent;
                color: #888899;
                font-family: '{self._pixel_font}';
                font-size: 9pt;
                padding: 12px 18px;
                margin-right: 8px;
                border: none;
                border-bottom: 2px solid transparent;
            }}
            QTabBar::tab:selected {{
                color: #ffffff;
                border-bottom: 2px solid {ACCENT_COLOR};
            }}
            QTabBar::tab:hover {{
                color: #cccccc;
            }}
        """
        )

    def _start_worker(self) -> None:
        """
        Create and start the background worker thread.

        The worker continuously polls CPU, RAM, disk, process, and system
        data and emits Qt signals whenever new data is available. The
        signals are connected to widget slots in _connect_signals().
        """
        self.worker = WorkerThread()
        self.worker.start()

        logger.info("WorkerThread started")

    def _connect_signals(self) -> None:
        """
        Connect worker thread signals to widget slots.

        This is the glue layer that bridges worker thread → UI widgets.
        Qt automatically marshals data across thread boundaries safely.
        """
        if self.worker is None:
            return

        self.worker.metrics_updated_cpu.connect(self.cpu_widget.update_data)
        self.worker.metrics_updated_memory.connect(self.memory_widget.update_data)
        self.worker.metrics_updated_disk.connect(self.disk_widget.update_data)
        self.worker.metrics_updated_processes.connect(
            self.process_widget.update_data
        )
        self.worker.metrics_updated_system.connect(self.system_widget.update_data)

        self.worker.error.connect(self._on_worker_error)

        logger.info("Signals connected")

    def _on_worker_error(self, error_msg: str) -> None:
        """Handle errors from worker thread."""
        logger.error("Worker error: %s", error_msg)

    def closeEvent(self, event) -> None:
        """
        Handle window close event.

        Stops the worker thread gracefully before closing the window.
        Without this, the worker thread would keep running in the background,
        wasting CPU cycles even after you close the window.

        Args:
            event: Qt close event object.
        """
        logger.info("Closing MainWindow...")

        if self.main_icon_movie is not None:
            self.main_icon_movie.stop()

        if self.worker:
            self.worker.stop()
            self.worker.wait()  # Block until thread terminates

            logger.info("WorkerThread stopped")

        event.accept()