"""
ui/widgets/cpu_widget.py
-----------------------
CPU usage widget with per-core breakdown (no chart — lightweight design).

Features:
    - Large overall CPU percentage display
    - Per-core progress bars (colored by load)
    - Frequency display
    - Responsive updates via Qt slots

Why no chart?
    Matplotlib redraws (clear + replot + layout) are expensive operations
    that run on the UI thread. Doing this every second causes visible
    stutter and high CPU usage — a poor fit for a lightweight dashboard
    on low-end hardware. Progress bars give the same "at a glance" info
    at a fraction of the render cost.

Design:
    ┌─────────────────────────────────┐
    │ CPU USAGE                       │
    │ 45%                             │
    │ 3.2 GHz | 8 Cores              │
    ├─────────────────────────────────┤
    │ Per-Core Breakdown:             │
    │ Core 0: 52% ████████░░░░░░░░░░ │
    │ Core 1: 38% ██████░░░░░░░░░░░░ │
    │ ... (up to N cores)             │
    └─────────────────────────────────┘
"""

import logging
from typing import List

from PyQt6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QScrollArea,
    QWidget,
)
from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtGui import QFont

from core.data_models import CPUMetrics
from ui.widgets.base_widget import BaseWidget


logger = logging.getLogger(__name__)


class CPUWidget(BaseWidget):
    """
    Widget displaying real-time CPU usage metrics.

    Attributes:
        overall_label (QLabel): Shows overall CPU % (large, bold)
        freq_label (QLabel): Shows CPU frequency and core count
        per_core_bars (List[QProgressBar]): Progress bar for each core
    """

    def __init__(self) -> None:
        """Initialize CPU widget."""
        super().__init__("CPU Monitor")
        self._setup_ui()
        logger.debug("CPUWidget initialized")

    def _setup_ui(self) -> None:
        """Build the UI layout."""
        main_layout = QVBoxLayout()
        self.setLayout(main_layout)

        # --- TITLE & FREQUENCY ---
        title_layout = QHBoxLayout()

        title = QLabel("CPU USAGE")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet("color: #ff8888;")
        title_layout.addWidget(title)
        title_layout.addStretch()

        self.freq_label = QLabel("")
        self.freq_label.setStyleSheet("color: #aaaaaa;")
        title_layout.addWidget(self.freq_label)

        main_layout.addLayout(title_layout)

        # --- OVERALL PERCENTAGE (LARGE) ---
        self.overall_label = QLabel("0%")
        overall_font = QFont()
        overall_font.setPointSize(48)
        overall_font.setBold(True)
        self.overall_label.setFont(overall_font)
        self.overall_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.overall_label.setStyleSheet("color: #ff8888;")
        main_layout.addWidget(self.overall_label)

        # --- PER-CORE PROGRESS BARS ---
        cores_label = QLabel("Per-Core Breakdown:")
        cores_label.setStyleSheet("color: #c0c0d0;")
        main_layout.addWidget(cores_label)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet(
            """
            QScrollArea { background-color: #2a2a3e; border: 1px solid #3d3d52; }
        """
        )

        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout()
        scroll_widget.setLayout(scroll_layout)

        self.per_core_bars: List[QProgressBar] = []

        # Create 16 placeholder progress bars (hidden if system has fewer cores)
        for i in range(16):
            bar_layout = QHBoxLayout()

            core_label = QLabel(f"Core {i}:")
            core_label.setFixedWidth(80)
            core_label.setStyleSheet("color: #aaaaaa;")
            bar_layout.addWidget(core_label)

            percent_label = QLabel("0%")
            percent_label.setFixedWidth(40)
            percent_label.setStyleSheet("color: #aaaaaa;")
            bar_layout.addWidget(percent_label)

            progress_bar = QProgressBar()
            progress_bar.setMaximum(100)
            progress_bar.setValue(0)
            progress_bar.setStyleSheet(
                """
                QProgressBar {
                    border: 1px solid #3d3d52;
                    border-radius: 4px;
                    background-color: #1f1f2e;
                    height: 18px;
                }
                QProgressBar::chunk {
                    background-color: #ff8888;
                    border-radius: 2px;
                }
            """
            )
            bar_layout.addWidget(progress_bar)
            bar_layout.addStretch()

            progress_bar.core_label = core_label
            progress_bar.percent_label = percent_label

            self.per_core_bars.append(progress_bar)
            scroll_layout.addLayout(bar_layout)

            core_label.hide()
            percent_label.hide()
            progress_bar.hide()

        scroll_layout.addStretch()
        scroll_area.setWidget(scroll_widget)
        main_layout.addWidget(scroll_area, stretch=1)

        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

    @pyqtSlot(CPUMetrics)
    def update_data(self, metrics: CPUMetrics) -> None:
        """
        Update widget with new CPU metrics.

        Called when WorkerThread emits metrics_updated_cpu signal.
        Updates the overall label, frequency, and per-core bars.

        Args:
            metrics: CPUMetrics snapshot from monitor.
        """
        try:
            self.overall_label.setText(f"{metrics.overall_percent:.1f}%")

            self.freq_label.setText(
                f"{metrics.frequency_ghz:.2f} GHz | {metrics.core_count} Cores"
            )

            for i, core_percent in enumerate(metrics.per_core_percents):
                if i >= len(self.per_core_bars):
                    break

                bar = self.per_core_bars[i]

                if bar.isHidden():
                    bar.show()
                    bar.core_label.show()
                    bar.percent_label.show()

                bar.setValue(int(core_percent))
                bar.percent_label.setText(f"{core_percent:.1f}%")
                self._color_bar(bar, core_percent)

            for i in range(len(metrics.per_core_percents), len(self.per_core_bars)):
                self.per_core_bars[i].hide()
                self.per_core_bars[i].core_label.hide()
                self.per_core_bars[i].percent_label.hide()

            logger.debug("CPUWidget updated: %.1f%%", metrics.overall_percent)

        except Exception as e:
            logger.error("Error updating CPU widget: %s", e)
            self.show_error(str(e))

    def _color_bar(self, bar: QProgressBar, percent: float) -> None:
        """
        Set progress bar color based on CPU load.

        Args:
            bar: Progress bar to color.
            percent: CPU percentage (0-100).
        """
        if percent < 50:
            color = "#88ff88"  # Green
        elif percent < 75:
            color = "#ffff88"  # Yellow
        else:
            color = "#ff8888"  # Red

        bar.setStyleSheet(
            f"""
            QProgressBar {{
                border: 1px solid #3d3d52;
                border-radius: 4px;
                background-color: #1f1f2e;
                height: 18px;
            }}
            QProgressBar::chunk {{
                background-color: {color};
                border-radius: 2px;
            }}
        """
        )