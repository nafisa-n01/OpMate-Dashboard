"""
ui/widgets/memory_widget.py
---------------------------
RAM and Swap memory widget styled as a compact pixel-art card.

Features:
    - Card-style container matching CPU widget's visual language, but
      shorter overall — RAM has less to show (no per-core equivalent),
      so the card stays lean: title, big stat, one bar, footer, optional
      swap row.
    - Padded, pill-shaped progress bar (matches reference image)
    - Footer row: Used | Available (matches reference image)
    - Swap row only appears if swap is actually configured
    - Color-coded by load (green/yellow/red)
    - 4 pixel-art screw icons pinned to the card's corners

Design (matches RAM usage reference image):
    ┌─────────────────────────────────────┐
    │ [icon] RAM USAGE                     │
    │        7.2 GB / 7.7 GB (93.5%)       │
    │  ┌─────────────────────────────────┐│
    │  │▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░│ │
    │  └─────────────────────────────────┘│
    │  Used: 7.2 GB          Available:0.5 │
    │                                       │
    │  Swap: 1.6/12.0 GB (13%)             │
    └─────────────────────────────────────┘
"""

import logging
import os

from PyQt6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QFrame,
)
from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtGui import QFont, QPixmap

from core.data_models import MemoryMetrics
from ui.widgets.base_widget import BaseWidget
from ui.styles.fonts import get_pixel_font_family


logger = logging.getLogger(__name__)

SWAP_WARNING_THRESHOLD = 50  # Show warning if swap > 50%

# Card color palette (shared visual language with CPU widget)
CARD_BORDER_COLOR = "#6a6a9a"
CARD_BACKGROUND_COLOR = "#3d3d5c"
CARD_INNER_BACKGROUND = "#2a2a44"
ACCENT_COLOR = "#88ff88"  # Green, RAM's accent color

# Corner screw decoration
SCREW_ICON_PATH = os.path.join("assets", "icons", "screw.png")
SCREW_MARGIN = 4  # px from each edge of the card

# Title icon
MEMORY_ICON_PATH = os.path.join("assets", "icons", "memory_icon.png")
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


class MemoryWidget(BaseWidget):
    """
    Widget displaying real-time memory usage metrics, styled as a compact card.

    Attributes:
        overall_label (QLabel): Shows "7.2 GB / 7.7 GB (93.5%)"
        ram_bar (QProgressBar): Padded, pill-shaped bar for RAM usage
        used_label (QLabel): Footer left — "Used: 7.2 GB"
        available_label (QLabel): Footer right — "Available: 0.5 GB"
        swap_row (QWidget): Container for the swap info row (hidden if no swap)
        swap_label (QLabel): Shows swap usage text
        swap_bar (QProgressBar): Small bar for swap usage
    """

    def __init__(self) -> None:
        """Initialize memory widget."""
        super().__init__("Memory Monitor")
        self._pixel_font = get_pixel_font_family()
        self._setup_ui()
        logger.debug("MemoryWidget initialized")

    def _setup_ui(self) -> None:
        """Build the compact card-style UI layout."""
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
        card_layout = QVBoxLayout()
        card_layout.setContentsMargins(20, 14, 20, 14)
        card_layout.setSpacing(8)
        card.setLayout(card_layout)

        outer_layout.addWidget(card)

        # --- TITLE ROW (icon + text) ---
        title_layout = QHBoxLayout()
        title_layout.setSpacing(8)

        memory_icon_pixmap = QPixmap(MEMORY_ICON_PATH)
        if not memory_icon_pixmap.isNull():
            icon_label = QLabel()
            icon_label.setPixmap(
                memory_icon_pixmap.scaledToHeight(
                    TITLE_ICON_HEIGHT, Qt.TransformationMode.SmoothTransformation
                )
            )
            icon_label.setStyleSheet("border: none;")
            title_layout.addWidget(icon_label)
        else:
            logger.warning("Memory icon not loaded from '%s'", MEMORY_ICON_PATH)

        title = QLabel("RAM USAGE")
        title.setFont(QFont(self._pixel_font, 11))
        title.setStyleSheet(f"color: {ACCENT_COLOR}; border: none;")
        title_layout.addWidget(title)

        title_layout.addStretch()

        card_layout.addLayout(title_layout)

        # --- STAT LINE (e.g. "7.2 GB / 7.7 GB (93.5%)") ---
        self.overall_label = QLabel("0 GB / 0 GB (0%)")
        self.overall_label.setFont(QFont(self._pixel_font, 13))
        self.overall_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.overall_label.setStyleSheet(f"color: {ACCENT_COLOR}; border: none;")
        card_layout.addWidget(self.overall_label)

        # --- RAM BAR (padded, pill-shaped) ---
        self.ram_bar = QProgressBar()
        self.ram_bar.setMaximum(100)
        self.ram_bar.setValue(0)
        self.ram_bar.setTextVisible(False)
        self.ram_bar.setFixedHeight(18)
        self._style_pill_bar(self.ram_bar, ACCENT_COLOR)
        card_layout.addWidget(self.ram_bar)

        # --- FOOTER ROW: Used | Available ---
        footer_layout = QHBoxLayout()

        self.used_label = QLabel("Used: -- GB")
        self.used_label.setFont(QFont(self._pixel_font, 7))
        self.used_label.setStyleSheet("color: #aaaaaa; border: none;")
        footer_layout.addWidget(self.used_label)

        footer_layout.addStretch()

        self.available_label = QLabel("Available: -- GB")
        self.available_label.setFont(QFont(self._pixel_font, 7))
        self.available_label.setStyleSheet("color: #aaaaaa; border: none;")
        footer_layout.addWidget(self.available_label)

        card_layout.addLayout(footer_layout)

        # --- SWAP ROW (compact, hidden entirely if no swap configured) ---
        self.swap_row = QVBoxLayout()
        self.swap_row.setSpacing(3)

        swap_header_layout = QHBoxLayout()

        self.swap_label = QLabel("Swap: no swap configured")
        self.swap_label.setFont(QFont(self._pixel_font, 7))
        self.swap_label.setStyleSheet("color: #888888; border: none;")
        swap_header_layout.addWidget(self.swap_label)

        swap_header_layout.addStretch()

        self.swap_warning_label = QLabel("")
        self.swap_warning_label.setFont(QFont(self._pixel_font, 7))
        self.swap_warning_label.setStyleSheet("color: #ff8888; border: none;")
        swap_header_layout.addWidget(self.swap_warning_label)

        self.swap_row.addLayout(swap_header_layout)

        self.swap_bar = QProgressBar()
        self.swap_bar.setMaximum(100)
        self.swap_bar.setValue(0)
        self.swap_bar.setTextVisible(False)
        self.swap_bar.setFixedHeight(10)
        self._style_pill_bar(self.swap_bar, "#ffff88")
        self.swap_bar.hide()
        self.swap_row.addWidget(self.swap_bar)

        card_layout.addLayout(self.swap_row)

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
                border-radius: 9px;
            }}
            QProgressBar::chunk {{
                background-color: {color};
                border-radius: 7px;
                margin: 2px;
            }}
        """
        )

    @pyqtSlot(MemoryMetrics)
    def update_data(self, metrics: MemoryMetrics) -> None:
        """
        Update widget with new memory metrics.

        Called when WorkerThread emits metrics_updated_memory signal.
        Updates the stat line, bar, footer, and swap row.

        Args:
            metrics: MemoryMetrics snapshot from monitor.
        """
        try:
            ram_used_gb = metrics.ram_used_mb / 1024.0
            ram_total_gb = metrics.ram_total_mb / 1024.0
            ram_available_gb = metrics.ram_available_mb / 1024.0

            self.overall_label.setText(
                f"{ram_used_gb:.1f} GB / {ram_total_gb:.1f} GB "
                f"({metrics.ram_percent:.1f}%)"
            )

            self.ram_bar.setValue(int(metrics.ram_percent))
            self._style_pill_bar(
                self.ram_bar, self._severity_color(metrics.ram_percent)
            )

            self.used_label.setText(f"Used: {ram_used_gb:.1f} GB")
            self.available_label.setText(f"Available: {ram_available_gb:.1f} GB")

            if metrics.swap_total_mb > 0:
                swap_used_gb = metrics.swap_used_mb / 1024.0
                swap_total_gb = metrics.swap_total_mb / 1024.0

                self.swap_label.setText(
                    f"Swap: {swap_used_gb:.1f}/{swap_total_gb:.1f} GB "
                    f"({metrics.swap_percent:.0f}%)"
                )
                self.swap_bar.setValue(int(metrics.swap_percent))
                self._style_pill_bar(
                    self.swap_bar, self._severity_color(metrics.swap_percent)
                )
                self.swap_bar.show()

                if metrics.swap_percent > SWAP_WARNING_THRESHOLD:
                    self.swap_warning_label.setText("HIGH")
                else:
                    self.swap_warning_label.setText("")
            else:
                self.swap_label.setText("Swap: not configured")
                self.swap_bar.hide()
                self.swap_warning_label.setText("")

            logger.debug(
                "MemoryWidget updated: %.1f%% (%.1f/%.1f GB)",
                metrics.ram_percent,
                ram_used_gb,
                ram_total_gb,
            )

        except Exception as e:
            logger.error("Error updating memory widget: %s", e)
            self.show_error(str(e))

    def _severity_color(self, percent: float) -> str:
        """
        Get a color string based on usage severity.

        Args:
            percent: Usage percentage (0-100).

        Returns:
            str: Hex color code.
        """
        if percent < 60:
            return "#88ff88"
        elif percent < 80:
            return "#ffff88"
        else:
            return "#ff8888"