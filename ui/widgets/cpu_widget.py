"""
ui/widgets/cpu_widget.py
-----------------------
CPU usage widget styled as a bordered pixel-art card.

Features:
    - Card-style container: rounded border, header with title
    - Left/right split layout: big overall percentage + bar on the
      left, a small vertical stat panel (Frequency, Cores) on the
      right — inspired by a reference dashboard, adapted to keep the
      existing pixel-art card look rather than switching to flat
      white stat cards.
    - Per-core breakdown as small boxes in a grid, spanning full width
      below the split layout
    - Color-coded by load (green/yellow/red)
    - 4 pixel-art screw icons pinned to the card's corners
    - Soft drop shadow behind the card for subtle depth
    - Thin accent-colored underline beneath the title text
    - Card border tints toward the current severity color (green →
      yellow → red) as overall CPU load rises — purely visual, reuses
      the existing severity thresholds already driving the bar/labels

Design note:
    No new metrics were introduced here — only overall_percent,
    frequency_ghz, core_count, and per_core_percents (all already
    present on CPUMetrics) were rearranged. A reference image also
    showed a "Threads" stat; that field doesn't exist on CPUMetrics,
    so it was left out rather than inventing new data.

Design:
    ┌─────────────────────────────────────────────┐
    │ CPU USAGE                                    │
    │ ▔▔▔▔▔▔▔▔▔ (underline accent)                 │
    │  ┌───────────────┐   ┌─────────────────────┐│
    │  │     68.1%      │   │  2.92 GHz           ││
    │  │  Average Usage │   │  Current Speed      ││
    │  │ ▓▓▓▓▓▓▓░░░░░░  │   │  8                  ││
    │  └───────────────┘   │  Cores              ││
    │                       └─────────────────────┘│
    │  Core 0  Core 1  Core 2  Core 3      ...     │
    │  ┌──┐  ┌──┐  ┌──┐  ┌──┐                      │
    │  │45│  │12│  │89│  │22│                      │
    │  └──┘  └──┘  └──┘  └──┘                      │
    └─────────────────────────────────────────────┘
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

# Card color palette (matches the RAM usage reference image)
CARD_BORDER_COLOR = "#6a6a9a"
CARD_BACKGROUND_COLOR = "#3d3d5c"
CARD_INNER_BACKGROUND = "#2a2a44"
ACCENT_COLOR = "#ff8fa3"  # Pink-red, CPU's accent color

# Corner screw decoration
SCREW_ICON_PATH = os.path.join("assets", "icons", "screw.png")
SCREW_MARGIN = 4  # px from each edge of the card

# Title icon + text
CPU_ICON_PATH = os.path.join("assets", "icons", "cpu_icon.png")
TITLE_ICON_HEIGHT = 24
TITLE_FONT_SIZE = 12

# Title underline accent (thin colored bar under the title text)
UNDERLINE_HEIGHT = 2
UNDERLINE_WIDTH = 90

# Drop shadow (soft, subtle — depth without breaking the flat/minimal look)
SHADOW_BLUR_RADIUS = 24
SHADOW_OFFSET_Y = 6
SHADOW_COLOR = QColor(0, 0, 0, 160)

# Severity-tinted border: same thresholds/colors as the rest of the card
BORDER_SEVERITY_COLORS = ("#88ff88", "#ffff88", "#ff8888")  # <50 / <75 / >=75

# Right-side stat panel (Frequency + Cores)
STAT_PANEL_WIDTH = 190
STAT_BOX_SPACING = 8


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
        card (_CardFrame): The outer card frame — kept as an attribute so
            its border color can be re-styled as severity changes.
        overall_label (QLabel): Shows overall CPU % (large, pixel font)
        freq_value_label (QLabel): Shows CPU frequency in the right stat panel
        cores_value_label (QLabel): Shows core count in the right stat panel
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

        # --- CARD CONTAINER ---
        screw_pixmap = QPixmap(SCREW_ICON_PATH)
        self.card = _CardFrame(screw_pixmap)
        self._apply_card_border(CARD_BORDER_COLOR)

        shadow = QGraphicsDropShadowEffect(self.card)
        shadow.setBlurRadius(SHADOW_BLUR_RADIUS)
        shadow.setOffset(0, SHADOW_OFFSET_Y)
        shadow.setColor(SHADOW_COLOR)
        self.card.setGraphicsEffect(shadow)

        card_layout = QVBoxLayout()
        card_layout.setContentsMargins(20, 10, 20, 10)
        card_layout.setSpacing(6)
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

        # --- SPLIT ROW: left = big % + bar, right = stat panel ---
        split_layout = QHBoxLayout()
        split_layout.setSpacing(16)

        # -- Left: overall percentage, caption, bar --
        left_column = QVBoxLayout()
        left_column.setSpacing(4)

        self.overall_label = QLabel("0%")
        self.overall_label.setFont(QFont(self._pixel_font, 20))
        self.overall_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.overall_label.setStyleSheet(f"color: {ACCENT_COLOR}; border: none;")
        left_column.addWidget(self.overall_label)

        average_caption = QLabel("Average Usage")
        average_caption.setFont(QFont(self._pixel_font, 7))
        average_caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        average_caption.setStyleSheet("color: #aaaaaa; border: none;")
        left_column.addWidget(average_caption)

        left_column.addSpacing(4)

        self.overall_bar = QProgressBar()
        self.overall_bar.setMaximum(100)
        self.overall_bar.setValue(0)
        self.overall_bar.setTextVisible(False)
        self.overall_bar.setFixedHeight(16)
        self._style_pill_bar(self.overall_bar, ACCENT_COLOR)
        left_column.addWidget(self.overall_bar)

        split_layout.addLayout(left_column, stretch=1)

        # -- Right: vertical stat panel (Frequency, Cores) --
        stat_panel = QFrame()
        stat_panel.setFixedWidth(STAT_PANEL_WIDTH)
        stat_panel.setStyleSheet(
            f"""
            QFrame {{
                background-color: {CARD_INNER_BACKGROUND};
                border: 1px solid {CARD_BORDER_COLOR};
                border-radius: 10px;
            }}
        """
        )
        stat_panel_layout = QVBoxLayout()
        stat_panel_layout.setContentsMargins(12, 10, 12, 10)
        stat_panel_layout.setSpacing(STAT_BOX_SPACING)
        stat_panel.setLayout(stat_panel_layout)

        self.freq_value_label, freq_block = self._create_stat_row("-- GHz", "Current Speed")
        stat_panel_layout.addLayout(freq_block)

        self.cores_value_label, cores_block = self._create_stat_row("--", "Cores")
        stat_panel_layout.addLayout(cores_block)

        stat_panel_layout.addStretch()

        split_layout.addWidget(stat_panel)

        card_layout.addLayout(split_layout)

        card_layout.addSpacing(4)

        # --- PER-CORE GRID (spans full width, below the split row) ---
        grid_container = QWidget()
        grid_container.setStyleSheet("border: none;")
        self.core_grid_layout = QGridLayout()
        self.core_grid_layout.setSpacing(6)
        self.core_grid_layout.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        grid_container.setLayout(self.core_grid_layout)
        card_layout.addWidget(grid_container)

    def _create_stat_row(self, value_text: str, caption_text: str):
        """
        Build one stat row for the right-side panel: a value label
        stacked above a small caption label, matching the reference
        layout's "2.92 GHz / Current Speed" style.

        Args:
            value_text: Initial text for the value line (e.g. "-- GHz").
            caption_text: Static caption beneath the value (e.g. "Current Speed").

        Returns:
            Tuple of (value_label, layout) — the layout is ready to add
            to the stat panel; the value_label is kept for update_data().
        """
        block = QVBoxLayout()
        block.setSpacing(1)

        value_label = QLabel(value_text)
        value_label.setFont(QFont(self._pixel_font, 11))
        value_label.setStyleSheet(f"color: {ACCENT_COLOR}; border: none;")
        block.addWidget(value_label)

        caption_label = QLabel(caption_text)
        caption_label.setFont(QFont(self._pixel_font, 6))
        caption_label.setStyleSheet("color: #888888; border: none;")
        block.addWidget(caption_label)

        return value_label, block

    def _apply_card_border(self, border_color: str) -> None:
        """
        (Re)apply the card's stylesheet with the given border color.

        Args:
            border_color: Hex color string for the card's border.
        """
        self.card.setStyleSheet(
            f"""
            QFrame {{
                background-color: {CARD_BACKGROUND_COLOR};
                border: 2px solid {border_color};
                border-radius: 14px;
            }}
        """
        )

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
                border: 1px solid {CARD_BORDER_COLOR};
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
        Apply the padded, pill-shaped bar style seen in the reference image.

        Args:
            bar: Progress bar to style.
            color: Fill color (hex string).
        """
        bar.setStyleSheet(
            f"""
            QProgressBar {{
                background-color: {CARD_INNER_BACKGROUND};
                border: 1px solid {CARD_BORDER_COLOR};
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

            self._apply_card_border(self._severity_color(metrics.overall_percent))

            self.freq_value_label.setText(f"{metrics.frequency_ghz:.2f} GHz")
            self.cores_value_label.setText(str(metrics.core_count))

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
            return BORDER_SEVERITY_COLORS[0]
        elif percent < 75:
            return BORDER_SEVERITY_COLORS[1]
        else:
            return BORDER_SEVERITY_COLORS[2]