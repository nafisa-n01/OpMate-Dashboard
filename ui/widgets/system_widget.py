"""
ui/widgets/system_widget.py
---------------------------
System overview widget styled as a pixel-art card, matching the visual
language of CPU/RAM/Disk widgets.

Features:
    - Card-style container: rounded border, header with title
    - Compact key-value rows (no bars needed — mostly static info)
    - Divider line separating static hardware info from live status info
    - Pixel font throughout

Design (matches SYSTEM card in the inspiration image):
    ┌─────────────────────────────────┐
    │ SYSTEM                           │
    │  OS:          Windows 10         │
    │  Uptime:      3h 24m             │
    │  ─────────────────────────       │
    │  CPU:         Intel i7 (8 cores) │
    │  RAM:         7.7 GB             │
    │  Processes:   187                │
    └─────────────────────────────────┘
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
from ui.styles.fonts import get_pixel_font_family


logger = logging.getLogger(__name__)

# Card color palette (shared visual language with CPU/RAM/Disk widgets)
CARD_BORDER_COLOR = "#6a6a9a"
CARD_BACKGROUND_COLOR = "#3d3d5c"
ACCENT_COLOR = "#88ccff"  # Blue, System's accent color


class SystemWidget(BaseWidget):
    """
    Widget displaying system overview information, styled as a pixel-art card.

    Attributes:
        row_labels (dict): Maps field name -> QLabel (value side) for updates.
    """

    def __init__(self) -> None:
        """Initialize system widget."""
        super().__init__("System Overview")
        self.row_labels = {}
        self._pixel_font = get_pixel_font_family()
        self._setup_ui()
        logger.debug("SystemWidget initialized")

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
        card_layout.setSpacing(8)
        card.setLayout(card_layout)

        outer_layout.addWidget(card)

        # --- TITLE ---
        title = QLabel("SYSTEM")
        title.setFont(QFont(self._pixel_font, 11))
        title.setStyleSheet(f"color: {ACCENT_COLOR}; border: none;")
        card_layout.addWidget(title)

        card_layout.addSpacing(4)

        # Define rows: (internal key, display label)
        static_rows = [
            ("os", "OS"),
            ("hostname", "Host"),
            ("cpu_model", "CPU"),
            ("ram_total", "RAM"),
        ]
        dynamic_rows = [
            ("uptime", "Uptime"),
            ("processes", "Processes"),
        ]

        for key, label_text in static_rows:
            card_layout.addLayout(self._create_row(key, label_text))

        # Divider between static and dynamic info
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet(f"background-color: {CARD_BORDER_COLOR}; border: none;")
        divider.setFixedHeight(2)
        card_layout.addSpacing(4)
        card_layout.addWidget(divider)
        card_layout.addSpacing(4)

        for key, label_text in dynamic_rows:
            card_layout.addLayout(self._create_row(key, label_text))

    def _create_row(self, key: str, label_text: str) -> QHBoxLayout:
        """
        Create a single key-value row (e.g., "OS: Windows 10").

        Args:
            key: Internal identifier used to look up this row's value label later.
            label_text: Human-readable label shown on the left side.

        Returns:
            QHBoxLayout: The row, ready to add to a parent layout.
        """
        row_layout = QHBoxLayout()

        label = QLabel(f"{label_text}:")
        label.setFont(QFont(self._pixel_font, 8))
        label.setStyleSheet("color: #aaaaaa; border: none;")
        label.setFixedWidth(90)
        row_layout.addWidget(label)

        value_label = QLabel("--")
        value_label.setFont(QFont(self._pixel_font, 8))
        value_label.setStyleSheet("color: #ffffff; border: none;")
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
        (every 10 seconds — this data changes slowly).

        Args:
            metrics: SystemMetrics snapshot from monitor.
        """
        try:
            self.row_labels["os"].setText(f"{metrics.os_name} {metrics.os_version}")
            self.row_labels["hostname"].setText(metrics.hostname)

            cpu_text = metrics.cpu_model or "Unknown"
            self.row_labels["cpu_model"].setText(
                f"{cpu_text} ({metrics.cpu_core_count} cores)"
            )
            self.row_labels["ram_total"].setText(f"{metrics.ram_total_gb:.1f} GB")

            uptime_str = SystemMonitor.format_uptime(metrics.uptime_seconds)
            self.row_labels["uptime"].setText(uptime_str)
            self.row_labels["processes"].setText(str(metrics.total_processes))

            logger.debug("SystemWidget updated: uptime=%s", uptime_str)

        except Exception as e:
            logger.error("Error updating system widget: %s", e)
            self.show_error(str(e))