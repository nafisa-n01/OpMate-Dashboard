"""
ui/widgets/disk_widget.py
-------------------------
Disk partition widget styled as a pixel-art card containing per-drive
mini-cards, matching the CPU/RAM card visual language.

Features:
    - Outer card container (title + icon + border, matches CPU/RAM cards)
    - Each partition gets its own small inner card inside the outer card
    - Big drive letter/name + percentage, small pill-shaped bar, GB text
    - Cards arranged in a grid, wrapping automatically — sized to fit
      more drives per row before wrapping to a second line
    - Updates every 5 seconds (disk usage changes slowly)
    - 4 pixel-art screw icons pinned to the outer card's corners

Design (matches DISK USAGE reference image):
    ┌───────────────────────────────────────────────────────────┐
    │ [icon] DISK USAGE                                          │
    │  ┌───────┐ ┌───────┐ ┌───────┐ ┌───────┐ ┌───────┐        │
    │  │  C:\  │ │  D:\  │ │  E:\  │ │  F:\  │ │  G:\  │        │
    │  │  77%  │ │  69%  │ │  26%  │ │  50%  │ │  43%  │        │
    │  │▓▓▓░░░│ │▓▓░░░░│ │▓░░░░░│ │▓▓░░░░│ │▓▓░░░░│        │
    │  │153/199│ │96/138 │ │36/138 │ │158/318│ │136/318│        │
    │  └───────┘ └───────┘ └───────┘ └───────┘ └───────┘        │
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
)
from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtGui import QFont, QPixmap

from core.data_models import DiskMetrics
from ui.widgets.base_widget import BaseWidget
from ui.styles.fonts import get_pixel_font_family


logger = logging.getLogger(__name__)

# Increased from 4 to 6 so more drives fit in a single row before wrapping
CARDS_PER_ROW = 6

# Slightly smaller than before (was 130x110) to help more cards fit per row
CARD_WIDTH = 110
CARD_HEIGHT = 100

# Card color palette (shared visual language with CPU/RAM widgets)
CARD_BORDER_COLOR = "#6a6a9a"
CARD_BACKGROUND_COLOR = "#3d3d5c"
CARD_INNER_BACKGROUND = "#2a2a44"
ACCENT_COLOR = "#a888ff"  # Purple, Disk's accent color

# Corner screw decoration
SCREW_ICON_PATH = os.path.join("assets", "icons", "screw.png")
SCREW_MARGIN = 4  # px from each edge of the card

# Title icon
DISK_ICON_PATH = os.path.join("assets", "icons", "disk_icon.png")
TITLE_ICON_HEIGHT = 22  # px, scaled to fit next to the title text


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

        # --- OUTER CARD CONTAINER ---
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
        card_layout = QVBoxLayout()
        card_layout.setContentsMargins(20, 16, 20, 16)
        card_layout.setSpacing(10)
        card.setLayout(card_layout)

        outer_layout.addWidget(card)

        # --- TITLE ROW (icon + text) ---
        title_layout = QHBoxLayout()
        title_layout.setSpacing(8)

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
        title.setFont(QFont(self._pixel_font, 11))
        title.setStyleSheet(f"color: {ACCENT_COLOR}; border: none;")
        title_layout.addWidget(title)

        title_layout.addStretch()

        card_layout.addLayout(title_layout)

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
                border: 1px solid {CARD_BORDER_COLOR};
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
                border: 1px solid {CARD_BORDER_COLOR};
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
            return "#88ff88"
        elif percent < 80:
            return "#ffff88"
        else:
            return "#ff8888"