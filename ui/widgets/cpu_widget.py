"""
ui/widgets/cpu_widget.py
-----------------------
CPU usage widget with live chart and per-core breakdown.

Features:
    - Large overall CPU percentage display
    - Per-core progress bars (colored by load)
    - Line chart showing CPU trend over 60 seconds
    - Frequency display
    - Responsive updates via Qt slots
    - Live matplotlib chart embedded in PyQt6

Design:
    ┌─────────────────────────────────┐
    │ CPU USAGE                       │
    │ 45%                             │
    │ 3.2 GHz | 8 Cores              │
    ├─────────────────────────────────┤
    │ Per-Core Breakdown:             │
    │ Core 0: 52% ████████░░░░░░░░░░ │
    │ Core 1: 38% ██████░░░░░░░░░░░░ │
    │ ... (up to 8 cores)             │
    ├─────────────────────────────────┤
    │      (Line chart here)          │
    │     CPU % over 60 seconds       │
    └─────────────────────────────────┘
"""

import logging
from collections import deque
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
from PyQt6.QtGui import QFont, QColor

import matplotlib.pyplot as plt
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from core.data_models import CPUMetrics
from ui.widgets.base_widget import BaseWidget


logger = logging.getLogger(__name__)

# History size: 60 data points = 1 per second = 60 seconds of history
CHART_HISTORY_SIZE = 60


class CPUWidget(BaseWidget):
    """
    Widget displaying real-time CPU usage metrics.

    Attributes:
        overall_label (QLabel): Shows overall CPU % (large, bold)
        freq_label (QLabel): Shows CPU frequency and core count
        per_core_bars (List[QProgressBar]): Progress bar for each core
        chart (Figure): Matplotlib figure for trend chart
        chart_canvas (FigureCanvas): Qt widget wrapping matplotlib figure
        chart_data (deque): Historical CPU % data (60 points)
    """

    def __init__(self) -> None:
        """Initialize CPU widget."""
        super().__init__("CPU Monitor")

        # History for chart (sliding window of last 60 seconds)
        self.chart_data = deque(maxlen=CHART_HISTORY_SIZE)

        # UI setup
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
        title.setStyleSheet("color: #ff8888;")  # Red-ish
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

        # Scrollable area for per-core bars (in case of 64+ core systems)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet(
            """
            QScrollArea { background-color: #2a2a3e; border: 1px solid #3d3d52; }
            QScrollBar { background-color: #2a2a3e; }
            QScrollBar::handle { background-color: #5d5d72; }
        """
        )

        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout()
        scroll_widget.setLayout(scroll_layout)

        self.per_core_bars: List[QProgressBar] = []

        # Create 16 placeholder progress bars (will be hidden if fewer cores)
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

            # Store references to labels for updates
            progress_bar.core_label = core_label
            progress_bar.percent_label = percent_label

            self.per_core_bars.append(progress_bar)
            scroll_layout.addLayout(bar_layout)

            # Hide by default (show only if we have this many cores)
            core_label.hide()
            percent_label.hide()
            progress_bar.hide()

        scroll_layout.addStretch()
        scroll_area.setWidget(scroll_widget)
        main_layout.addWidget(scroll_area, stretch=1)

        # --- MATPLOTLIB CHART ---
        self.figure = Figure(figsize=(10, 3), dpi=100, facecolor="#2a2a3e")
        self.axes = self.figure.add_subplot(111)
        self.axes.set_facecolor("#1f1f2e")
        self.axes.set_xlabel("Time (seconds ago)", color="#aaaaaa", fontsize=9)
        self.axes.set_ylabel("CPU %", color="#aaaaaa", fontsize=9)
        self.axes.set_ylim(0, 100)
        self.axes.tick_params(colors="#aaaaaa", labelsize=8)
        self.axes.grid(True, alpha=0.2, color="#555555", linestyle="--")

        # Style the spines (borders)
        for spine in self.axes.spines.values():
            spine.set_color("#3d3d52")

        self.chart_canvas = FigureCanvas(self.figure)
        self.chart_canvas.setStyleSheet("background-color: #2a2a3e;")
        main_layout.addWidget(self.chart_canvas)

        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(10)

    @pyqtSlot(CPUMetrics)
    def update_data(self, metrics: CPUMetrics) -> None:
        """
        Update widget with new CPU metrics.

        Called when WorkerThread emits metrics_updated_cpu signal.
        Updates all labels, progress bars, and chart.

        Args:
            metrics: CPUMetrics snapshot from monitor.
        """
        try:
            # Update overall percentage
            self.overall_label.setText(f"{metrics.overall_percent:.1f}%")

            # Update frequency and core info
            self.freq_label.setText(
                f"{metrics.frequency_ghz:.2f} GHz | {metrics.core_count} Cores"
            )

            # Update per-core progress bars
            for i, core_percent in enumerate(metrics.per_core_percents):
                if i >= len(self.per_core_bars):
                    break  # System has more cores than bars we created

                bar = self.per_core_bars[i]

                # Show this bar if hidden
                if bar.isHidden():
                    bar.show()
                    bar.core_label.show()
                    bar.percent_label.show()

                # Update bar value and labels
                bar.setValue(int(core_percent))
                bar.percent_label.setText(f"{core_percent:.1f}%")

                # Color the bar based on load (green → yellow → red)
                self._color_bar(bar, core_percent)

            # Hide bars we don't need
            for i in range(len(metrics.per_core_percents), len(self.per_core_bars)):
                self.per_core_bars[i].hide()
                self.per_core_bars[i].core_label.hide()
                self.per_core_bars[i].percent_label.hide()

            # Update chart history
            self.chart_data.append(metrics.overall_percent)

            # Redraw chart
            self._update_chart()

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

    def _update_chart(self) -> None:
        """Redraw the matplotlib chart with current history."""
        self.axes.clear()

        if len(self.chart_data) > 0:
            # X-axis: time (reversed, so time flows left to right)
            x_values = list(range(len(self.chart_data) - 1, -1, -1))

            # Y-axis: CPU percentages
            y_values = list(self.chart_data)

            # Plot line
            self.axes.plot(
                x_values, y_values, color="#ff8888", linewidth=2, label="CPU %"
            )

            # Fill under curve
            self.axes.fill_between(x_values, y_values, alpha=0.3, color="#ff8888")

        # Styling
        self.axes.set_facecolor("#1f1f2e")
        self.axes.set_xlabel("Time (seconds ago)", color="#aaaaaa", fontsize=9)
        self.axes.set_ylabel("CPU %", color="#aaaaaa", fontsize=9)
        self.axes.set_ylim(0, 100)
        self.axes.tick_params(colors="#aaaaaa", labelsize=8)
        self.axes.grid(True, alpha=0.2, color="#555555", linestyle="--")

        for spine in self.axes.spines.values():
            spine.set_color("#3d3d52")

        self.figure.tight_layout()
        self.chart_canvas.draw()