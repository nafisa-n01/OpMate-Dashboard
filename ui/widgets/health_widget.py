"""
ui/widgets/health_widget.py
----------------------------
PC Health widget: an at-a-glance aggregate status card combining CPU,
RAM, and Disk severity into a single "how is my PC doing?" summary.

Unlike the other dashboard widgets, this one doesn't have its own
monitor/signal — it listens to the SAME three signals already emitted
by WorkerThread (metrics_updated_cpu, metrics_updated_memory,
metrics_updated_disk) and recomputes an overall status whenever any
one of them updates. This keeps it lightweight: no extra polling,
no extra background thread, just reusing data that's already flowing.

Features:
    - Card-style container matching the rest of the dashboard:
      drop shadow, borderless background + rounded corners
    - Icon + title CENTERED (unlike the other widgets' left-aligned
      title row) — this card is a summary, not a metric card, so its
      header is treated as more of a standalone banner
    - Underline accent centered directly beneath the title
    - Big centered status text ("ALL GOOD" / "MINOR ISSUES" / "NEEDS
      ATTENTION")
    - Three small indicator dots (CPU / RAM / Disk), each colored by
      its own individual severity
    - Footer row: numeric health score (0-100) + a short tip that only
      appears when something needs attention

Design:
    ┌─────────────────────────────────────┐
              [icon] PC HEALTH
            ▔▔▔▔▔▔▔▔▔ (centered underline)
                 ALL GOOD
        ● CPU      ● RAM      ● DISK
       Score: 92/100
       Tip: Consider freeing up disk space
    └─────────────────────────────────────┘
"""

import logging
import os
from typing import List, Optional

from PyQt6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QFrame,
    QGraphicsDropShadowEffect,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QPixmap, QColor

from core.data_models import CPUMetrics, MemoryMetrics, DiskMetrics
from ui.widgets.base_widget import BaseWidget
from ui.styles.fonts import get_pixel_font_family


logger = logging.getLogger(__name__)

# Card color palette (shared visual language with CPU/RAM/Disk widgets).
# No CARD_BORDER_COLOR here — this card is intentionally borderless.
CARD_BACKGROUND_COLOR = "#3d3d5c"
CARD_INNER_BACKGROUND = "#2a2a44"
ACCENT_COLOR = "#7FBFB0"  # Muted Teal, Health's accent color

# Corner screw decoration
SCREW_ICON_PATH = os.path.join("assets", "icons", "screw.png")
SCREW_MARGIN = 4  # px from each edge of the card

# Title icon + text
HEALTH_ICON_PATH = os.path.join("assets", "icons", "health_icon.png")
TITLE_ICON_HEIGHT = 26
TITLE_FONT_SIZE = 12

# Title underline accent (thin colored bar under the title text)
UNDERLINE_HEIGHT = 2
UNDERLINE_WIDTH = 90  # px — roughly matches "PC HEALTH" text width

# Drop shadow (soft, subtle — matches the rest of the dashboard)
SHADOW_BLUR_RADIUS = 24
SHADOW_OFFSET_Y = 6
SHADOW_COLOR = QColor(0, 0, 0, 160)

# Severity thresholds (percent used) shared across CPU/RAM/Disk checks.
# Meaning: safe = sage green, ok = muted blue, severe = muted terracotta
SEVERITY_COLORS = ("#8FD6A3", "#82B5D8", "#D97A6B")  # <60 / <80 / >=80

# Status text shown for each overall severity tier
STATUS_TEXT = ("ALL GOOD", "MINOR ISSUES", "NEEDS ATTENTION")

# Tip text shown in the footer for each tier (empty string = no tip shown)
TIP_TEXT = (
    "",
    "Keep an eye on things.",
    "Consider closing apps or freeing disk space.",
)


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


class HealthWidget(BaseWidget):
    """
    Aggregate PC health status widget, combining CPU/RAM/Disk severity.

    Attributes:
        card (_CardFrame): The outer card frame. Borderless — only
            background, rounded corners, and a drop shadow.
        status_label (QLabel): Big centered "ALL GOOD" / etc. text.
        score_label (QLabel): Footer left — "Score: 92/100".
        tip_label (QLabel): Footer — short advice text (hidden when empty).
        cpu_dot / ram_dot / disk_dot (QLabel): Small colored indicator dots.
        _cpu_percent / _ram_percent / _disk_percent (Optional[float]):
            Latest known value from each source signal. None until that
            signal has fired at least once — the health score treats
            "not yet known" as fine (0% severity) rather than blocking
            the whole card on waiting for all three signals to arrive.
    """

    def __init__(self) -> None:
        """Initialize health widget."""
        super().__init__("PC Health")
        self._pixel_font = get_pixel_font_family()

        self._cpu_percent: Optional[float] = None
        self._ram_percent: Optional[float] = None
        self._disk_percent: Optional[float] = None

        self._setup_ui()
        logger.debug("HealthWidget initialized")

    def _setup_ui(self) -> None:
        """Build the compact card-style UI layout."""
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

        # --- TITLE ROW (icon + text, CENTERED — unlike other widgets) ---
        title_layout = QHBoxLayout()
        title_layout.setSpacing(10)
        title_layout.addStretch()

        health_icon_pixmap = QPixmap(HEALTH_ICON_PATH)
        if not health_icon_pixmap.isNull():
            icon_label = QLabel()
            icon_label.setPixmap(
                health_icon_pixmap.scaledToHeight(
                    TITLE_ICON_HEIGHT, Qt.TransformationMode.SmoothTransformation
                )
            )
            icon_label.setStyleSheet("border: none;")
            title_layout.addWidget(icon_label)
        else:
            logger.warning("Health icon not loaded from '%s'", HEALTH_ICON_PATH)

        title = QLabel("PC HEALTH")
        title.setFont(QFont(self._pixel_font, TITLE_FONT_SIZE))
        title.setStyleSheet(f"color: {ACCENT_COLOR}; border: none;")
        title_layout.addWidget(title)

        title_layout.addStretch()

        card_layout.addLayout(title_layout)

        # --- TITLE UNDERLINE ACCENT (centered beneath the title) ---
        self.underline = QFrame()
        self.underline.setFixedHeight(UNDERLINE_HEIGHT)
        self.underline.setFixedWidth(UNDERLINE_WIDTH)
        self.underline.setStyleSheet(f"background-color: {ACCENT_COLOR}; border: none;")
        underline_row = QHBoxLayout()
        underline_row.setContentsMargins(0, 0, 0, 0)
        underline_row.addStretch()
        underline_row.addWidget(self.underline)
        underline_row.addStretch()
        card_layout.addLayout(underline_row)

        # --- BIG STATUS TEXT ---
        self.status_label = QLabel("ALL GOOD")
        self.status_label.setFont(QFont(self._pixel_font, 13))
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet(f"color: {ACCENT_COLOR}; border: none;")
        card_layout.addWidget(self.status_label)

        # --- THREE INDICATOR DOTS: CPU / RAM / DISK ---
        dots_layout = QHBoxLayout()
        dots_layout.setSpacing(24)
        dots_layout.addStretch()

        self.cpu_dot, cpu_group = self._create_indicator("CPU")
        dots_layout.addLayout(cpu_group)

        self.ram_dot, ram_group = self._create_indicator("RAM")
        dots_layout.addLayout(ram_group)

        self.disk_dot, disk_group = self._create_indicator("DISK")
        dots_layout.addLayout(disk_group)

        dots_layout.addStretch()
        card_layout.addLayout(dots_layout)

        # --- FOOTER ROW: Score | Tip ---
        footer_layout = QHBoxLayout()

        self.score_label = QLabel("Score: -- / 100")
        self.score_label.setFont(QFont(self._pixel_font, 7))
        self.score_label.setStyleSheet("color: #aaaaaa; border: none;")
        footer_layout.addWidget(self.score_label)

        footer_layout.addStretch()

        card_layout.addLayout(footer_layout)

        # --- TIP ROW (hidden when there's nothing to say) ---
        self.tip_label = QLabel("")
        self.tip_label.setFont(QFont(self._pixel_font, 7))
        self.tip_label.setStyleSheet("color: #888888; border: none;")
        self.tip_label.setWordWrap(True)
        self.tip_label.hide()
        card_layout.addWidget(self.tip_label)

    def _create_indicator(self, label_text: str):
        """
        Build one small colored-dot indicator with a text label beneath it.

        Args:
            label_text: Short label shown under the dot (e.g., "CPU").

        Returns:
            tuple[QLabel, QVBoxLayout]: The dot QLabel (so its color can
                be updated later) and the assembled layout containing
                both the dot and its text label.
        """
        group = QVBoxLayout()
        group.setSpacing(4)
        group.setAlignment(Qt.AlignmentFlag.AlignCenter)

        dot = QLabel()
        dot.setFixedSize(14, 14)
        dot.setStyleSheet(
            f"background-color: {SEVERITY_COLORS[0]}; border-radius: 7px;"
        )
        dot_row = QHBoxLayout()
        dot_row.addStretch()
        dot_row.addWidget(dot)
        dot_row.addStretch()
        group.addLayout(dot_row)

        text = QLabel(label_text)
        text.setFont(QFont(self._pixel_font, 6))
        text.setStyleSheet("color: #aaaaaa; border: none;")
        text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        group.addWidget(text)

        return dot, group

    def _severity_color(self, percent: float) -> str:
        """
        Get a color string based on usage severity.

        Args:
            percent: Usage percentage (0-100).

        Returns:
            str: Hex color code.
        """
        if percent < 60:
            return SEVERITY_COLORS[0]
        elif percent < 80:
            return SEVERITY_COLORS[1]
        else:
            return SEVERITY_COLORS[2]

    def _severity_tier(self, percent: float) -> int:
        """
        Get a severity tier index (0=good, 1=warning, 2=critical) for
        the given percentage, using the same thresholds as _severity_color.

        Args:
            percent: Usage percentage (0-100).

        Returns:
            int: 0, 1, or 2.
        """
        if percent < 60:
            return 0
        elif percent < 80:
            return 1
        else:
            return 2

    def on_cpu_update(self, metrics: CPUMetrics) -> None:
        """
        Receive CPU metrics directly from WorkerThread's cpu signal.

        Args:
            metrics: CPUMetrics snapshot from monitor.
        """
        self._cpu_percent = metrics.overall_percent
        self._recompute_health()

    def on_memory_update(self, metrics: MemoryMetrics) -> None:
        """
        Receive memory metrics directly from WorkerThread's memory signal.

        Args:
            metrics: MemoryMetrics snapshot from monitor.
        """
        self._ram_percent = metrics.ram_percent
        self._recompute_health()

    def on_disk_update(self, metrics: DiskMetrics) -> None:
        """
        Receive disk metrics directly from WorkerThread's disk signal.

        Uses the single most-full partition as the disk severity
        signal — one nearly-full drive is worth flagging even if
        others are mostly empty.

        Args:
            metrics: DiskMetrics snapshot from monitor.
        """
        if metrics.partitions:
            self._disk_percent = max(p.percent for p in metrics.partitions)
        else:
            self._disk_percent = 0.0

        self._recompute_health()

    def _recompute_health(self) -> None:
        """
        Recalculate overall status from whichever CPU/RAM/Disk values
        are currently known, and refresh every visual element.

        Any source not yet received (still None, e.g. right after
        startup before that signal has fired once) is treated as 0%
        — this avoids the whole card sitting blank/uninitialized while
        waiting for all three signals to arrive at least once.
        """
        try:
            cpu = self._cpu_percent if self._cpu_percent is not None else 0.0
            ram = self._ram_percent if self._ram_percent is not None else 0.0
            disk = self._disk_percent if self._disk_percent is not None else 0.0

            self.cpu_dot.setStyleSheet(
                f"background-color: {self._severity_color(cpu)}; border-radius: 7px;"
            )
            self.ram_dot.setStyleSheet(
                f"background-color: {self._severity_color(ram)}; border-radius: 7px;"
            )
            self.disk_dot.setStyleSheet(
                f"background-color: {self._severity_color(disk)}; border-radius: 7px;"
            )

            # Overall tier = the worst of the three individual tiers
            overall_tier = max(
                self._severity_tier(cpu),
                self._severity_tier(ram),
                self._severity_tier(disk),
            )
            overall_color = SEVERITY_COLORS[overall_tier]

            self.status_label.setText(STATUS_TEXT[overall_tier])
            self.status_label.setStyleSheet(f"color: {overall_color}; border: none;")
            self.underline.setStyleSheet(
                f"background-color: {overall_color}; border: none;"
            )

            # Simple 0-100 score: 100 minus the average of the three
            # percentages (higher usage across the board = lower score).
            score = max(0, round(100 - ((cpu + ram + disk) / 3)))
            self.score_label.setText(f"Score: {score} / 100")

            tip = TIP_TEXT[overall_tier]
            if tip:
                self.tip_label.setText(f"Tip: {tip}")
                self.tip_label.show()
            else:
                self.tip_label.hide()

            logger.debug(
                "HealthWidget updated: cpu=%.0f%% ram=%.0f%% disk=%.0f%% score=%d",
                cpu,
                ram,
                disk,
                score,
            )

        except Exception as e:
            logger.error("Error updating health widget: %s", e)
            self.show_error(str(e))

    def update_data(self, data) -> None:
        """
        Not used directly — HealthWidget listens to three separate
        signals (on_cpu_update / on_memory_update / on_disk_update)
        rather than a single update_data() call, since it aggregates
        multiple metric types. Present only to satisfy BaseWidget's
        interface.
        """
        pass