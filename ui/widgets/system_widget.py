"""
ui/widgets/system_widget.py
---------------------------
System overview widget styled as a pixel-art card, matching the visual
language of CPU/RAM/Disk widgets.

Features:
    - Card-style container: rounded border
    - Animated GIF decoration on the left side of the card (via QMovie),
      vertically centered against the card and scaled with nearest-
      neighbor filtering to keep pixel art crisp (no blur)
    - Compact key-value rows (no bars needed — mostly static info)
    - Divider line separating static hardware info from live status info
    - Pixel font throughout
    - 4 pixel-art screw icons pinned to the card's corners

Design:
    ┌──────────────────────────────────────────┐
    │             SYSTEM                        │
    │  ┌──────┐  OS:          Windows 10        │
    │  │      │  Host:        DESKTOP-ABC1234   │
    │  │ GIF  │  CPU:         Intel i7 (8 cores)│
    │  │      │  RAM:         7.7 GB            │
    │  └──────┘  ─────────────────────────      │
    │             Uptime:      3h 24m           │
    │             Processes:   187              │
    └──────────────────────────────────────────┘
"""

import logging
import os
from typing import List

from PyQt6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QFrame,
)
from PyQt6.QtCore import Qt, QSize, pyqtSlot
from PyQt6.QtGui import QFont, QPixmap, QMovie

from core.data_models import SystemMetrics
from core.monitors.system_monitor import SystemMonitor
from ui.widgets.base_widget import BaseWidget
from ui.styles.fonts import get_pixel_font_family


logger = logging.getLogger(__name__)

# Card color palette (shared visual language with CPU/RAM/Disk widgets)
CARD_BORDER_COLOR = "#6a6a9a"
CARD_BACKGROUND_COLOR = "#3d3d5c"
ACCENT_COLOR = "#88ccff"  # Blue, System's accent color

# Corner screw decoration
SCREW_ICON_PATH = os.path.join("assets", "icons", "screw.png")
SCREW_MARGIN = 4  # px from each edge of the card

# Left-side animated decoration.
# Source GIF is native 48x48 — scaling to 96x96 (2x) keeps pixel art
# crisp (clean integer multiple). If you want it bigger later, use
# another clean multiple: 144 (3x) or 192 (4x) — avoid odd sizes,
# which cause uneven/blurry scaling of pixel art.
SYSTEM_GIF_PATH = os.path.join("assets", "icons", "system_icon.gif")
GIF_DISPLAY_SIZE = QSize(96, 96)


class _CardFrame(QFrame):
    """
    QFrame subclass that keeps 4 corner "screw" icons pinned to its
    corners, repositioning them whenever the frame is resized.
    """

    def __init__(self, screw_pixmap: QPixmap, margin: int = SCREW_MARGIN, parent=None) -> None:
        super().__init__(parent)
        self._margin = margin
        self._screw_labels: List[QLabel] = []

        if screw_pixmap is not None and not screw_pixmap.isNull():
            for _ in range(4):
                screw_label = QLabel(self)
                screw_label.setPixmap(screw_pixmap)
                screw_label.setFixedSize(screw_pixmap.width(), screw_pixmap.height())
                screw_label.setStyleSheet("background: transparent; border: none;")
                screw_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
                screw_label.raise_()
                self._screw_labels.append(screw_label)
        else:
            logger.warning("Screw icon not loaded from '%s'; skipping corner screws", SCREW_ICON_PATH)

        self._position_screws()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._position_screws()

    def _position_screws(self) -> None:
        if len(self._screw_labels) != 4:
            return

        w, h = self.width(), self.height()
        sw, sh = self._screw_labels[0].width(), self._screw_labels[0].height()
        m = self._margin

        self._screw_labels[0].move(m, m)                    # top-left
        self._screw_labels[1].move(w - sw - m, m)            # top-right
        self._screw_labels[2].move(m, h - sh - m)             # bottom-left
        self._screw_labels[3].move(w - sw - m, h - sh - m)    # bottom-right


class SystemWidget(BaseWidget):
    """
    Widget displaying system overview information, styled as a pixel-art card.

    Attributes:
        row_labels (dict): Maps field name -> QLabel (value side) for updates.
        gif_movie (QMovie): The animated decoration playing on the left side.
    """

    def __init__(self) -> None:
        """Initialize system widget."""
        super().__init__("System Overview")
        self.row_labels = {}
        self.gif_movie: QMovie = None
        self._pixel_font = get_pixel_font_family()
        self._setup_ui()
        logger.debug("SystemWidget initialized")

    def _setup_ui(self) -> None:
        """Build the card-style UI layout."""
        outer_layout = QVBoxLayout()
        outer_layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(outer_layout)

        # --- CARD CONTAINER ---
        screw_pixmap = QPixmap(SCREW_ICON_PATH)
        card = _CardFrame(screw_pixmap)
        card.setStyleSheet(
            f"""
            QFrame {{
                background-color: {CARD_BACKGROUND_COLOR};
                border: 2px solid {CARD_BORDER_COLOR};
                border-radius: 14px;
            }}
        """
        )

        # Card is split horizontally: [animated GIF] | [content column]
        card_layout = QHBoxLayout()
        card_layout.setContentsMargins(20, 16, 20, 16)
        card_layout.setSpacing(16)
        card.setLayout(card_layout)

        outer_layout.addWidget(card)

        # --- LEFT SIDE: ANIMATED GIF (vertically centered against the card) ---
        gif_label = QLabel()
        gif_label.setFixedSize(GIF_DISPLAY_SIZE)
        gif_label.setStyleSheet("border: none;")
        gif_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        if os.path.exists(SYSTEM_GIF_PATH):
            self.gif_movie = QMovie(SYSTEM_GIF_PATH)
            self.gif_movie.setScaledSize(GIF_DISPLAY_SIZE)
            # Nearest-neighbor scaling keeps pixel art crisp — smooth
            # scaling (Qt's default) blurs hard pixel edges, which
            # looks wrong for pixel-art assets.
            self.gif_movie.setCacheMode(QMovie.CacheMode.CacheAll)
            gif_label.setMovie(self.gif_movie)
            self.gif_movie.start()
        else:
            logger.warning("System GIF not found at '%s'", SYSTEM_GIF_PATH)

        card_layout.addWidget(gif_label, alignment=Qt.AlignmentFlag.AlignVCenter)

        # --- RIGHT SIDE: CONTENT COLUMN ---
        content_layout = QVBoxLayout()
        content_layout.setSpacing(8)

        # --- TITLE (text only — icon replaced by the GIF on the left) ---
        title = QLabel("SYSTEM")
        title.setFont(QFont(self._pixel_font, 11))
        title.setStyleSheet(f"color: {ACCENT_COLOR}; border: none;")
        content_layout.addWidget(title)

        content_layout.addSpacing(4)

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
            content_layout.addLayout(self._create_row(key, label_text))

        # Divider between static and dynamic info
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setStyleSheet(f"background-color: {CARD_BORDER_COLOR}; border: none;")
        divider.setFixedHeight(2)
        content_layout.addSpacing(4)
        content_layout.addWidget(divider)
        content_layout.addSpacing(4)

        for key, label_text in dynamic_rows:
            content_layout.addLayout(self._create_row(key, label_text))

        card_layout.addLayout(content_layout, stretch=1)

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
        # Widened from 90 to 110 — "Processes:" (10 chars) was getting
        # clipped by the value label starting too close behind it.
        label.setFixedWidth(110)
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