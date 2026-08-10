"""
ui/main_window.py
-----------------
Main application window controller.

Responsibilities:
    - Create the main window and set its properties
    - Build the tab-based interface (Dashboard, Processes, Storage, Settings)
    - Instantiate the background worker thread
    - Connect worker signals to widget slots (glue layer between core and UI)
    - Handle cleanup when the app closes

Layout design:
    Flat, minimalist framing — a single background color throughout,
    with generous margins providing breathing room instead of a boxed
    "panel within a panel" look. Tabs use an underline style (no filled
    background) to keep navigation lightweight. The individual metric
    cards (CPU/RAM/Disk/System) retain their own pixel-art borders —
    this flattening only applies to the outer window chrome.
"""

import logging
from typing import Optional

from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QTabWidget,
    QScrollArea,
)
from PyQt6.QtCore import QTimer

from core.worker_thread import WorkerThread
from ui.widgets.placeholder_widget import PlaceholderWidget
from ui.widgets.cpu_widget import CPUWidget
from ui.widgets.memory_widget import MemoryWidget
from ui.widgets.disk_widget import DiskWidget
from ui.widgets.process_widget import ProcessWidget
from ui.widgets.system_widget import SystemWidget


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
    """

    def __init__(self) -> None:
        """Initialize the main window."""
        super().__init__()
        self.setWindowTitle("SystemWatch — System Dashboard")
        self.setGeometry(100, 100, 1400, 900)  # x, y, width, height

        self.worker: Optional[WorkerThread] = None
        self.update_timer = QTimer()

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
                   └─ QTabWidget (underline-style tabs, no filled panel)
                        └─ dashboard_content (cards with generous gaps)
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

        dashboard_layout.addWidget(self.cpu_widget)
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

        # --- REMAINING TABS (placeholders for now) ---
        self.tab_storage = PlaceholderWidget("Storage Analyzer")
        self.tab_settings = PlaceholderWidget("Settings")

        self.tabs.addTab(dashboard_scroll, "Dashboard")
        self.tabs.addTab(processes_content, "Processes")
        self.tabs.addTab(self.tab_storage, "Storage")
        self.tabs.addTab(self.tab_settings, "Settings")

        central_layout.addWidget(self.tabs)

        # Minimalist underline-style tabs — no filled background box,
        # just a colored underline on the active tab
        self.tabs.setStyleSheet(
            f"""
            QTabWidget::pane {{
                background-color: transparent;
                border: none;
            }}
            QTabBar::tab {{
                background-color: transparent;
                color: #888899;
                padding: 10px 18px;
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

        if self.worker:
            self.worker.stop()
            self.worker.wait()  # Block until thread terminates

            logger.info("WorkerThread stopped")

        event.accept()