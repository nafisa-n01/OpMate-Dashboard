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
"""

import logging
from typing import Optional

from PyQt6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTabWidget,
    QPushButton,
    QLabel,
    QStackedWidget,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont

from core.worker_thread import WorkerThread
from ui.widgets.placeholder_widget import PlaceholderWidget
from ui.widgets.cpu_widget import CPUWidget


logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """
    Main application window.

    Attributes:
        worker (WorkerThread): Background thread that continuously polls system metrics.
        update_timer (QTimer): Timer to update UI at intervals (fallback if signals fail).
        cpu_widget (CPUWidget): Displays live CPU usage.
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

        Creates:
            1. Left sidebar with navigation buttons
            2. Right content area with tabs (Dashboard, Processes, Storage, Settings)
            3. Central widget that glues everything together
        """
        # Central widget — parent for all UI elements
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Main layout: horizontal (sidebar left, content right)
        main_layout = QHBoxLayout()
        central_widget.setLayout(main_layout)

        # --- LEFT SIDEBAR ---
        sidebar = self._create_sidebar()
        main_layout.addWidget(sidebar, stretch=0)  # Don't expand sidebar

        # --- RIGHT CONTENT AREA (Tabs) ---
        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.TabPosition.North)

        # --- DASHBOARD TAB (container for CPU/Memory/Disk/Process widgets) ---
        self.tab_dashboard = QWidget()
        dashboard_layout = QVBoxLayout()
        self.tab_dashboard.setLayout(dashboard_layout)

        # Create and add CPU widget (Step 9)
        self.cpu_widget = CPUWidget()
        dashboard_layout.addWidget(self.cpu_widget)

        # --- REMAINING TABS (still placeholders until later steps) ---
        self.tab_processes = PlaceholderWidget("Processes")
        self.tab_storage = PlaceholderWidget("Storage Analyzer")
        self.tab_settings = PlaceholderWidget("Settings")

        self.tabs.addTab(self.tab_dashboard, "📊 Dashboard")
        self.tabs.addTab(self.tab_processes, "⚙️ Processes")
        self.tabs.addTab(self.tab_storage, "📁 Storage")
        self.tabs.addTab(self.tab_settings, "⚙️ Settings")

        main_layout.addWidget(self.tabs, stretch=1)  # Expand content area

        # Dark theme colors
        self.setStyleSheet(
            """
            QMainWindow { background-color: #2a2a3e; }
            QTabWidget { background-color: #2a2a3e; }
            QTabBar::tab { background-color: #3d3d52; color: #c0c0d0; padding: 8px 16px; }
            QTabBar::tab:selected { background-color: #5d5d72; color: #ffffff; }
        """
        )

    def _create_sidebar(self) -> QWidget:
        """
        Create the left sidebar with navigation.

        Returns:
            QWidget: Sidebar container.
        """
        sidebar = QWidget()
        sidebar.setFixedWidth(200)
        sidebar.setStyleSheet(
            """
            QWidget { background-color: #1f1f2e; }
            QPushButton {
                background-color: #3d3d52;
                color: #c0c0d0;
                border: none;
                padding: 12px;
                margin: 4px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5d5d72;
                color: #ffffff;
            }
        """
        )

        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # Title
        title = QLabel("SystemWatch")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet("color: #ffffff;")
        layout.addWidget(title)

        layout.addSpacing(20)

        # Navigation buttons
        nav_buttons = [
            ("📊 Dashboard", lambda: self.tabs.setCurrentIndex(0)),
            ("⚙️ Processes", lambda: self.tabs.setCurrentIndex(1)),
            ("📁 Storage", lambda: self.tabs.setCurrentIndex(2)),
            ("⚙️ Settings", lambda: self.tabs.setCurrentIndex(3)),
        ]

        for label, callback in nav_buttons:
            btn = QPushButton(label)
            btn.clicked.connect(callback)
            layout.addWidget(btn)

        layout.addStretch()

        # Footer info
        footer = QLabel("System is stable.\nCats are pleased. 😸")
        footer.setStyleSheet("color: #888888; font-size: 10px;")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(footer)

        sidebar.setLayout(layout)
        return sidebar

    def _start_worker(self) -> None:
        """
        Create and start the background worker thread.

        The worker continuously polls CPU, RAM, disk, and process data
        and emits Qt signals whenever new data is available. The signals
        are connected to the UI widgets' update slots in _connect_signals().
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

        # Connect CPU signals
        self.worker.metrics_updated_cpu.connect(self.cpu_widget.update_data)

        # Connect error signals
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