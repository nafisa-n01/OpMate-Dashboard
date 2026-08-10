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
    The window uses a "framed" look: the QMainWindow itself shows a dark
    outer background, and all real content sits inside a rounded panel
    inset with margins — similar to a card floating on a background,
    rather than content stretching edge-to-edge.
"""

import logging
from typing import Optional

from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QTabWidget,
    QFrame,
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

# Outer window background (the "empty" framing area, like the cyan reference)
OUTER_BACKGROUND_COLOR = "#14141f"

# Inner content panel background (where all widgets/tabs actually live)
CONTENT_BACKGROUND_COLOR = "#2a2a3e"

# Space between the window edge and the content panel
OUTER_MARGIN = 24


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
              └─ outer_widget (dark background, provides the margin/frame)
                   └─ content_panel (rounded, lighter background)
                        └─ QTabWidget (Dashboard, Processes, Storage, Settings)
        """
        # --- OUTER WIDGET (provides the framing margin) ---
        outer_widget = QWidget()
        self.setCentralWidget(outer_widget)
        outer_widget.setStyleSheet(f"background-color: {OUTER_BACKGROUND_COLOR};")

        outer_layout = QVBoxLayout()
        outer_layout.setContentsMargins(
            OUTER_MARGIN, OUTER_MARGIN, OUTER_MARGIN, OUTER_MARGIN
        )
        outer_widget.setLayout(outer_layout)

        # --- CONTENT PANEL (rounded card holding all real UI) ---
        content_panel = QFrame()
        content_panel.setStyleSheet(
            f"""
            QFrame {{
                background-color: {CONTENT_BACKGROUND_COLOR};
                border-radius: 16px;
            }}
        """
        )
        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_panel.setLayout(content_layout)

        outer_layout.addWidget(content_panel)

        # --- TABS (now the only navigation — sidebar removed) ---
        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.TabPosition.North)

        # --- DASHBOARD TAB (scrollable container for overview widgets) ---
        dashboard_content = QWidget()
        dashboard_layout = QVBoxLayout()
        dashboard_layout.setSpacing(12)
        dashboard_content.setLayout(dashboard_layout)

        # Create overview widgets (process table now lives in its own tab)
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

        # --- PROCESSES TAB (dedicated home for the process table) ---
        processes_content = QWidget()
        processes_layout = QVBoxLayout()
        processes_content.setLayout(processes_layout)

        self.process_widget = ProcessWidget()
        processes_layout.addWidget(self.process_widget)

        # --- REMAINING TABS (placeholders for now) ---
        self.tab_storage = PlaceholderWidget("Storage Analyzer")
        self.tab_settings = PlaceholderWidget("Settings")

        self.tabs.addTab(dashboard_scroll, "📊 Dashboard")
        self.tabs.addTab(processes_content, "⚙️ Processes")
        self.tabs.addTab(self.tab_storage, "📁 Storage")
        self.tabs.addTab(self.tab_settings, "⚙️ Settings")

        content_layout.addWidget(self.tabs)

        # Tab bar styling
        self.tabs.setStyleSheet(
            f"""
            QTabWidget::pane {{
                background-color: {CONTENT_BACKGROUND_COLOR};
                border: none;
                border-radius: 16px;
            }}
            QTabBar::tab {{
                background-color: #3d3d52;
                color: #c0c0d0;
                padding: 10px 20px;
                margin-right: 4px;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
            }}
            QTabBar::tab:selected {{
                background-color: #5d5d72;
                color: #ffffff;
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