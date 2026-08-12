"""
ui/widgets/disk_widget.py
-------------------------
Disk partition widget styled as a pixel-art card containing per-drive
mini-cards, matching the CPU/RAM card visual language.

Features:
    - Outer card container (title + icon, no border — borderless card
      with background + rounded corners + drop shadow only)
    - Each partition gets its own small inner mini-card (also borderless,
      distinguished by its own background against the outer card)
    - Big drive letter/name + percentage, small pill-shaped bar, GB text
    - Cards arranged in a grid, wrapping automatically — sized to fit
      more drives per row before wrapping to a second line
    - Updates every 5 seconds (disk usage changes slowly)
    - 4 pixel-art screw icons pinned to the outer card's corners
    - Soft drop shadow behind the outer card for subtle depth
    - Thin accent-colored underline beneath the title text
    - Severity color (safe/ok/severe) now shown via each mini-card's
      percentage text and bar fill only — no border retinting, since
      neither card has a border anymore

Design (matches DISK USAGE reference image):
    ┌───────────────────────────────────────────────────────────┐
      [icon] DISK USAGE
      ▔▔▔▔▔▔▔▔▔▔ (underline accent)
       ┌───────┐ ┌───────┐ ┌───────┐ ┌───────┐ ┌───────┐
       │  C:\  │ │  D:\  │ │  E:\  │ │  F:\  │ │  G:\  │
       │  77%  │ │  69%  │ │  26%  │ │  50%  │ │  43%  │
       │▓▓▓░░░│ │▓▓░░░░│ │▓░░░░░│ │▓▓░░░░│ │▓▓░░░░│
       │153/199│ │96/138 │ │36/138 │ │158/318│ │136/318│
       └───────┘ └───────┘ └───────┘ └───────┘ └───────┘
    └───────────────────────────────────────────────────────────┘
"""

import logging
import os
from typing import Dict

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

from core.data_models import DiskMetrics
from ui.widgets.base_widget import BaseWidget
from ui.styles.fonts import get_pixel_font_family


logger = logging.getLogger(__name__)

# Increased from 4 to 6 so more drives fit in a single row before wrapping
CARDS_PER_ROW = 6

# Slightly smaller than before (was 130x110) to help more cards fit per row
CARD_WIDTH = 110
CARD_HEIGHT = 100

# Card color palette (shared visual language with CPU/RAM widgets).
# No CARD_BORDER_COLOR here — both outer card and mini-cards are
# intentionally borderless.
CARD_BACKGROUND_COLOR = "#3d3d5c"
CARD_INNER_BACKGROUND = "#2a2a44"
ACCENT_COLOR = "#B8B4E8"  # Lavender, Disk's accent color

# Corner screw decoration
SCREW_ICON_PATH = os.path.join("assets", "icons", "screw.png")
SCREW_MARGIN = 4  # px from each edge of the card

# Title icon + text
DISK_ICON_PATH = os.path.join("assets", "icons", "disk_icon.png")
TITLE_ICON_HEIGHT = 26  # was 22 — small bump, matches CPU/Memory widgets' delta
TITLE_FONT_SIZE = 12  # was 11 — nudged up to balance the bigger icon

# Title underline accent (thin colored bar under the title text)
UNDERLINE_HEIGHT = 2
UNDERLINE_WIDTH = 100  # px — roughly matches "DISK USAGE" text width

# Drop shadow (soft, subtle — depth without breaking the flat/minimal look)
SHADOW_BLUR_RADIUS = 24
SHADOW_OFFSET_Y = 6
SHADOW_COLOR = QColor(0, 0, 0, 160)  # semi-transparent black

# Severity palette (shared meaning across all widgets):
# safe = sage green, ok = muted blue, severe = muted terracotta.
# Now only drives percent-text and bar-fill colors — no border tinting.
BORDER_SEVERITY_COLORS = ("#8FD6A3", "#82B5D8", "#D97A6B")  # <60 / <80 / >=80


class _CardFrame(QFrame):
    """
    QFrame subclass that keeps 4 corner "screw" icons pinned to its
    corners, repositioning them whenever the frame is resized.
    """

    def __init__(self, screw_pixmap: QPixmap, margin: int = SCREW_MARGIN, parent=None) -> None:
        super().__init__(parent)
        self._margin = margin
        self._screw_labels = []

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


class DiskWidget(BaseWidget):
    """
    Widget displaying real-time disk partition usage as mini-cards inside
    a bordered outer card.

    Attributes:
        card (_CardFrame): The outer card frame. Borderless — only
            background, rounded corners, and a drop shadow.
        grid_layout (QGridLayout): Container that arranges disk mini-cards.
        partition_cards (Dict[str, dict]): Maps device name -> mini-card
            widget references for in-place updates.
    """

    def __init__(self) -> None:
        """Initialize disk widget."""
        super().__init__("Disk Monitor")
        self.partition_cards: Dict[str, dict] = {}
        self._pixel_font = get_pixel_font_family()
        self._setup_ui()
        logger.debug("DiskWidget initialized")

    def _setup_ui(self) -> None:
        """Build the card-style UI layout."""
        outer_layout = QVBoxLayout()
        outer_layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(outer_layout)

        # --- OUTER CARD CONTAINER (borderless — background + rounded corners only) ---
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

        # Soft drop shadow behind the outer card. Applied to the card
        # itself (not the outer widget) so it reads as the card's own
        # depth, matching CPU/RAM widgets.
        shadow = QGraphicsDropShadowEffect(self.card)
        shadow.setBlurRadius(SHADOW_BLUR_RADIUS)
        shadow.setOffset(0, SHADOW_OFFSET_Y)
        shadow.setColor(SHADOW_COLOR)
        self.card.setGraphicsEffect(shadow)

        card_layout = QVBoxLayout()
        card_layout.setContentsMargins(20, 16, 20, 16)
        card_layout.setSpacing(10)
        self.card.setLayout(card_layout)

        outer_layout.addWidget(self.card)

        # --- TITLE ROW (icon + text) ---
        title_layout = QHBoxLayout()
        title_layout.setSpacing(10)  # was 8 — slightly more room next to the bigger icon

        disk_icon_pixmap = QPixmap(DISK_ICON_PATH)
        if not disk_icon_pixmap.isNull():
            icon_label = QLabel()
            icon_label.setPixmap(
                disk_icon_pixmap.scaledToHeight(
                    TITLE_ICON_HEIGHT, Qt.TransformationMode.SmoothTransformation
                )
            )
            icon_label.setStyleSheet("border: none;")
            title_layout.addWidget(icon_label)
        else:
            logger.warning("Disk icon not loaded from '%s'", DISK_ICON_PATH)

        title = QLabel("DISK USAGE")
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

        # --- MINI-CARD GRID ---
        grid_container = QWidget()
        grid_container.setStyleSheet("border: none;")
        self.grid_layout = QGridLayout()
        self.grid_layout.setSpacing(10)
        self.grid_layout.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        grid_container.setLayout(self.grid_layout)

        # Placeholder message until first data arrives
        self.placeholder_label = QLabel("Scanning partitions...")
        self.placeholder_label.setFont(QFont(self._pixel_font, 8))
        self.placeholder_label.setStyleSheet("color: #888888; border: none;")
        self.grid_layout.addWidget(self.placeholder_label, 0, 0)

        card_layout.addWidget(grid_container)

    @pyqtSlot(DiskMetrics)
    def update_data(self, metrics: DiskMetrics) -> None:
        """
        Update widget with new disk metrics.

        Creates a mini-card per partition on first call. On subsequent
        calls, updates existing cards in place (avoids UI flicker).

        Args:
            metrics: DiskMetrics snapshot from monitor.
        """
        try:
            if self.placeholder_label is not None:
                self.placeholder_label.hide()

            for partition in metrics.partitions:
                if partition.device not in self.partition_cards:
                    self._create_partition_card(partition.device)

                self._update_partition_card(partition)

            logger.debug("DiskWidget updated: %d partitions", len(metrics.partitions))

        except Exception as e:
            logger.error("Error updating disk widget: %s", e)
            self.show_error(str(e))

    def _create_partition_card(self, device: str) -> None:
        """
        Create a small mini-card for a new partition.

        Args:
            device: Partition device name (e.g., "C:", "/dev/sda1").
        """
        mini_card = QFrame()
        mini_card.setFixedSize(CARD_WIDTH, CARD_HEIGHT)
        mini_card.setStyleSheet(
            f"""
            QFrame {{
                background-color: {CARD_INNER_BACKGROUND};
                border: none;
                border-radius: 10px;
            }}
        """
        )

        mini_layout = QVBoxLayout()
        mini_layout.setContentsMargins(8, 6, 8, 6)
        mini_layout.setSpacing(3)
        mini_card.setLayout(mini_layout)

        # Device name (e.g., "C:\")
        device_label = QLabel(device)
        device_label.setFont(QFont(self._pixel_font, 7))
        device_label.setStyleSheet("color: #ffffff; border: none;")
        device_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mini_layout.addWidget(device_label)

        # Big percentage number
        percent_label = QLabel("0%")
        percent_label.setFont(QFont(self._pixel_font, 12))
        percent_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        percent_label.setStyleSheet("border: none;")
        mini_layout.addWidget(percent_label)

        # Pill-shaped bar
        bar = QProgressBar()
        bar.setMaximum(100)
        bar.setValue(0)
        bar.setTextVisible(False)
        bar.setFixedHeight(9)
        mini_layout.addWidget(bar)

        # Used/Total text (small, bottom)
        info_label = QLabel("")
        info_label.setFont(QFont(self._pixel_font, 6))
        info_label.setStyleSheet("color: #aaaaaa; border: none;")
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mini_layout.addWidget(info_label)

        # Figure out grid position based on how many cards already exist
        card_count = len(self.partition_cards)
        row = card_count // CARDS_PER_ROW
        col = card_count % CARDS_PER_ROW

        if card_count == 0 and self.placeholder_label is not None:
            self.grid_layout.removeWidget(self.placeholder_label)

        self.grid_layout.addWidget(mini_card, row, col)

        self.partition_cards[device] = {
            "percent_label": percent_label,
            "bar": bar,
            "info_label": info_label,
        }

    def _update_partition_card(self, partition) -> None:
        """
        Update an existing partition mini-card with new data.

        Args:
            partition: PartitionInfo object with current usage data.
        """
        widgets = self.partition_cards[partition.device]

        widgets["percent_label"].setText(f"{partition.percent:.0f}%")
        widgets["bar"].setValue(int(partition.percent))

        widgets["info_label"].setText(
            f"{partition.used_gb:.0f}/{partition.total_gb:.0f} GB"
        )

        color = self._severity_color(partition.percent)
        widgets["percent_label"].setStyleSheet(f"color: {color}; border: none;")
        self._style_pill_bar(widgets["bar"], color)

    def _style_pill_bar(self, bar: QProgressBar, color: str) -> None:
        """
        Apply the padded, pill-shaped bar style used across the dashboard.

        Args:
            bar: Progress bar to style.
            color: Fill color (hex string).
        """
        bar.setStyleSheet(
            f"""
            QProgressBar {{
                background-color: {CARD_BACKGROUND_COLOR};
                border: none;
                border-radius: 5px;
            }}
            QProgressBar::chunk {{
                background-color: {color};
                border-radius: 4px;
            }}
        """
        )

    def _severity_color(self, percent: float) -> str:
        """
        Get a color string based on usage severity.

        Args:
            percent: Disk usage percentage (0-100).

        Returns:
            str: Hex color code.
        """
        if percent < 60:
            return BORDER_SEVERITY_COLORS[0]
        elif percent < 80:
            return BORDER_SEVERITY_COLORS[1]
        else:
            return BORDER_SEVERITY_COLORS[2]