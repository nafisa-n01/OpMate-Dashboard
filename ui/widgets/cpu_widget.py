"""
ui/widgets/cpu_widget.py
-----------------------
CPU usage widget styled as a bordered pixel-art card.

Features:
    - Card container matching the rest of the dashboard: borderless
      (background + rounded corners only), soft drop shadow, icon +
      title with underline accent
    - Large overall CPU percentage using pixel font
    - Padded, pill-shaped progress bar
    - Per-core breakdown as small boxes in a grid
    - Footer row: core count / frequency
    - Color-coded by load (sage green/muted blue/muted terracotta)
    - 4 pixel-art screw icons pinned to the card's corners

Design (matches the rest of the dashboard's card style):
    ┌─────────────────────────────────────┐
      [icon] CPU USAGE
      ▔▔▔▔▔▔▔▔▔ (underline accent)
                 65.6%
       ┌─────────────────────────────────┐
       │▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░░░░░░░░░░░░░░░│
       └─────────────────────────────────┘
       Core 0  Core 1  Core 2  Core 3
       ┌──┐  ┌──┐  ┌──┐  ┌──┐
       │45│  │12│  │89│  │22│
       └──┘  └──┘  └──┘  └──┘
       Cores: 8              3.45 GHz
    └─────────────────────────────────────┘
"""

import logging
import os
from typing import List

from PyQt6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QProgressBar,
    QWidget,
    QFrame,
    QGraphicsDropShadowEffect,
)
from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtGui import QFont, QPixmap, QColor

from core.data_models import CPUMetrics
from ui.widgets.base_widget import BaseWidget
from ui.styles.fonts import get_pixel_font_family


logger = logging.getLogger(__name__)

CORES_PER_ROW = 8
CORE_BOX_SIZE = 52

# Card color palette (shared visual language with the rest of the
# dashboard). No CARD_BORDER_COLOR — this card is intentionally
# borderless, matching RAM/Disk/Health.
CARD_BACKGROUND_COLOR = "#3d3d5c"
CARD_INNER_BACKGROUND = "#2a2a44"
ACCENT_COLOR = "#D6A85F"  # Muted Amber, CPU's accent color

# Corner screw decoration
SCREW_ICON_PATH = os.path.join("assets", "icons", "screw.png")
SCREW_MARGIN = 4  # px from each edge of the card

# Title icon + text
CPU_ICON_PATH = os.path.join("assets", "icons", "cpu_icon.png")
TITLE_ICON_HEIGHT = 26  # matches RAM/Disk/Health's icon height
TITLE_FONT_SIZE = 12  # matches RAM/Disk/Health's title size

# Title underline accent (thin colored bar under the title text)
UNDERLINE_HEIGHT = 2
UNDERLINE_WIDTH = 90  # px — roughly matches "CPU USAGE" text width

# Drop shadow (soft, subtle — matches the rest of the dashboard)
SHADOW_BLUR_RADIUS = 24
SHADOW_OFFSET_Y = 6
SHADOW_COLOR = QColor(0, 0, 0, 160)  # semi-transparent black

# Severity palette (shared meaning across all widgets):
# safe = sage green, ok = muted blue, severe = muted terracotta
SEVERITY_SAFE = "#8FD6A3"
SEVERITY_OK = "#82B5D8"
SEVERITY_SEVERE = "#D97A6B"


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


class CPUWidget(BaseWidget):
    """
    Widget displaying real-time CPU usage metrics, styled as a pixel-art card.

    Attributes:
        card (_CardFrame): The outer card frame. Borderless — only
            background, rounded corners, and a drop shadow.
        overall_label (QLabel): Shows overall CPU % (large, pixel font)
        freq_label (QLabel): Shows CPU frequency (footer, right side)
        cores_label (QLabel): Shows core count (footer, left side)
        overall_bar (QProgressBar): Padded bar showing overall CPU load
        core_grid_layout (QGridLayout): Container arranging core boxes in a grid
        core_boxes (List[dict]): Widget references for each core box, in order
    """

    def __init__(self) -> None:
        """Initialize CPU widget."""
        super().__init__("CPU Monitor")
        self.core_boxes: List[dict] = []
        self._pixel_font = get_pixel_font_family()
        self._setup_ui()
        logger.debug("CPUWidget initialized")

    def _setup_ui(self) -> None:
        """Build the card-style UI layout."""
        outer_layout = QVBoxLayout()
        outer_layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(outer_layout)

        # --- CARD CONTAINER (borderless — background + rounded corners only) ---
        screw_pixmap = QPixmap(SCREW_ICON_PATH)
        self.card = _CardFrame(screw_pixmap)
        self.card.setStyleSheet(
            f"""
            QFrame {{
                background-color: {CARD_BACKGROUND_COLOR};
                border: none;
                border-radius: 14px;
            }}
        """
        )

        # Soft drop shadow behind the card. Applied to the card itself
        # (not the outer widget) so it reads as the card's own depth.
        shadow = QGraphicsDropShadowEffect(self.card)
        shadow.setBlurRadius(SHADOW_BLUR_RADIUS)
        shadow.setOffset(0, SHADOW_OFFSET_Y)
        shadow.setColor(SHADOW_COLOR)
        self.card.setGraphicsEffect(shadow)

        card_layout = QVBoxLayout()
        card_layout.setContentsMargins(20, 14, 20, 14)
        card_layout.setSpacing(8)
        self.card.setLayout(card_layout)

        outer_layout.addWidget(self.card)

        # --- TITLE ROW (icon + text) ---
        title_layout = QHBoxLayout()
        title_layout.setSpacing(10)

        cpu_icon_pixmap = QPixmap(CPU_ICON_PATH)
        if not cpu_icon_pixmap.isNull():
            icon_label = QLabel()
            icon_label.setPixmap(
                cpu_icon_pixmap.scaledToHeight(
                    TITLE_ICON_HEIGHT, Qt.TransformationMode.SmoothTransformation
                )
            )
            icon_label.setStyleSheet("border: none;")
            title_layout.addWidget(icon_label)
        else:
            logger.warning("CPU icon not loaded from '%s'", CPU_ICON_PATH)

        title = QLabel("CPU USAGE")
        title.setFont(QFont(self._pixel_font, TITLE_FONT_SIZE))
        title.setStyleSheet(f"color: {ACCENT_COLOR}; border: none;")
        title_layout.addWidget(title)

        title_layout.addStretch()

        card_layout.addLayout(title_layout)

        # --- TITLE UNDERLINE ACCENT ---
        underline = QFrame()
        underline.setFixedHeight(UNDERLINE_HEIGHT)
        underline.setFixedWidth(UNDERLINE_WIDTH)
        underline.setStyleSheet(f"background-color: {ACCENT_COLOR}; border: none;")
        underline_row = QHBoxLayout()
        underline_row.setContentsMargins(0, 0, 0, 0)
        underline_row.addWidget(underline)
        underline_row.addStretch()
        card_layout.addLayout(underline_row)

        # --- OVERALL PERCENTAGE (LARGE, CENTERED) ---
        self.overall_label = QLabel("0%")
        self.overall_label.setFont(QFont(self._pixel_font, 18))
        self.overall_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.overall_label.setStyleSheet(f"color: {ACCENT_COLOR}; border: none;")
        card_layout.addWidget(self.overall_label)

        # --- OVERALL PROGRESS BAR (padded, pill-shaped) ---
        self.overall_bar = QProgressBar()
        self.overall_bar.setMaximum(100)
        self.overall_bar.setValue(0)
        self.overall_bar.setTextVisible(False)
        self.overall_bar.setFixedHeight(16)
        self._style_pill_bar(self.overall_bar, ACCENT_COLOR)
        card_layout.addWidget(self.overall_bar)

        card_layout.addSpacing(4)

        # --- PER-CORE GRID ---
        grid_container = QWidget()
        grid_container.setStyleSheet("border: none;")
        self.core_grid_layout = QGridLayout()
        self.core_grid_layout.setSpacing(6)
        self.core_grid_layout.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        grid_container.setLayout(self.core_grid_layout)
        card_layout.addWidget(grid_container)

        card_layout.addSpacing(4)

        # --- FOOTER ROW: Cores | Frequency ---
        footer_layout = QHBoxLayout()

        self.cores_label = QLabel("Cores: --")
        self.cores_label.setFont(QFont(self._pixel_font, 7))
        self.cores_label.setStyleSheet("color: #aaaaaa; border: none;")
        footer_layout.addWidget(self.cores_label)

        footer_layout.addStretch()

        self.freq_label = QLabel("-- GHz")
        self.freq_label.setFont(QFont(self._pixel_font, 7))
        self.freq_label.setStyleSheet("color: #aaaaaa; border: none;")
        footer_layout.addWidget(self.freq_label)

        card_layout.addLayout(footer_layout)

    def _create_core_box(self, core_index: int) -> dict:
        """
        Create a small square box for one CPU core, styled to match the card.

        Args:
            core_index: Which core this box represents (0-based).

        Returns:
            dict: References to the box's internal widgets, for later updates.
        """
        box = QFrame()
        box.setFixedSize(CORE_BOX_SIZE, CORE_BOX_SIZE)
        box.setStyleSheet(
            f"""
            QFrame {{
                background-color: {CARD_INNER_BACKGROUND};
                border: none;
                border-radius: 8px;
            }}
        """
        )

        box_layout = QVBoxLayout()
        box_layout.setContentsMargins(3, 3, 3, 3)
        box_layout.setSpacing(1)
        box.setLayout(box_layout)

        core_label = QLabel(f"C{core_index}")
        core_label.setFont(QFont(self._pixel_font, 6))
        core_label.setStyleSheet("color: #888888; border: none;")
        core_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        box_layout.addWidget(core_label)

        percent_label = QLabel("0%")
        percent_label.setFont(QFont(self._pixel_font, 8))
        percent_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        percent_label.setStyleSheet("border: none;")
        box_layout.addWidget(percent_label)

        row = core_index // CORES_PER_ROW
        col = core_index % CORES_PER_ROW
        self.core_grid_layout.addWidget(box, row, col)

        return {"box": box, "percent_label": percent_label}

    def _style_pill_bar(self, bar: QProgressBar, color: str) -> None:
        """
        Apply the padded, pill-shaped bar style seen across the dashboard.

        Args:
            bar: Progress bar to style.
            color: Fill color (hex string).
        """
        bar.setStyleSheet(
            f"""
            QProgressBar {{
                background-color: {CARD_INNER_BACKGROUND};
                border: none;
                border-radius: 8px;
            }}
            QProgressBar::chunk {{
                background-color: {color};
                border-radius: 6px;
                margin: 2px;
            }}
        """
        )

    @pyqtSlot(CPUMetrics)
    def update_data(self, metrics: CPUMetrics) -> None:
        """
        Update widget with new CPU metrics.

        Called when WorkerThread emits metrics_updated_cpu signal.
        Creates core boxes on first call, then updates everything in place.

        Args:
            metrics: CPUMetrics snapshot from monitor.
        """
        try:
            self.overall_label.setText(f"{metrics.overall_percent:.1f}%")
            self.overall_bar.setValue(int(metrics.overall_percent))

            self.cores_label.setText(f"Cores: {metrics.core_count}")
            self.freq_label.setText(f"{metrics.frequency_ghz:.2f} GHz")

            if not self.core_boxes:
                for i in range(len(metrics.per_core_percents)):
                    self.core_boxes.append(self._create_core_box(i))

            for i, core_percent in enumerate(metrics.per_core_percents):
                if i >= len(self.core_boxes):
                    break

                widgets = self.core_boxes[i]
                widgets["percent_label"].setText(f"{core_percent:.0f}%")

                color = self._severity_color(core_percent)
                widgets["percent_label"].setStyleSheet(
                    f"color: {color}; border: none;"
                )

            logger.debug("CPUWidget updated: %.1f%%", metrics.overall_percent)

        except Exception as e:
            logger.error("Error updating CPU widget: %s", e)
            self.show_error(str(e))

    def _severity_color(self, percent: float) -> str:
        """
        Get a color string based on load severity.

        Args:
            percent: CPU percentage (0-100).

        Returns:
            str: Hex color code.
        """
        if percent < 50:
            return SEVERITY_SAFE
        elif percent < 75:
            return SEVERITY_OK
        else:
            return SEVERITY_SEVERE