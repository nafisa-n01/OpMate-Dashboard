r"""
ui/widgets/storage_widget.py
------------------------------
Storage Analyzer widget: pick a disk, see its top space-consuming
folders bucketed into 4 tiers, and drill down through subfolders.
A companion GIF reacts to whatever disk or folder the user is
currently hovering, giving an at-a-glance read on severity.

Design:
    ┌───────────────────────────────────────────────────┐
      STORAGE ANALYZER
      ▔▔▔▔▔▔▔▔▔▔▔▔ (underline accent)
      ┌── Disk Picker (default view) ─────────────────┐
      │  C:\   [████░░░░░░]     412 GB / 512 GB  Clean │
      │  D:\   [█░░░░░░░░░]      88 GB / 1 TB    Safe  │
      └──────────────────────────────────────────────────┘
            -- or, after picking a disk --
      Path: C:\Users\you      [Disks] [Back] [Rescan]
      ┌─────────────────────────────────────────────────┐
      │ Documents  [████░░░░░░]   2.3 GB  46%  Clean Up │
      │ Downloads  [██░░░░░░░░]   1.1 GB  22%  Watch    │
      │ ...                                              │
      └─────────────────────────────────────────────────┘
                [ companion GIF ]
    └───────────────────────────────────────────────────┘

Navigation:
    Disk picker is the entry point. Picking a disk starts a scan
    rooted at that disk and switches to the folder list view.
    Clicking a folder row drills into it (scanning on demand if it's
    a depth-limit placeholder); "Back" returns to the parent folder;
    "Disks" returns all the way out to the disk picker.

Companion animation:
    Hovering a disk card or a folder row swaps the companion QMovie
    to that item's tier GIF; moving the mouse away reverts to the
    idle GIF. This is pure UI reaction — no extra scanning happens
    on hover, so it costs nothing beyond a QMovie swap.

    COMPANION_SIZE controls the display size. For pixel-art GIFs to
    stay crisp (not blurry), this should be an exact integer multiple
    of the GIF's native resolution — e.g. a 80x80 source GIF should
    display at 160 (2x), 240 (3x), or 320 (4x), not an arbitrary size.

Row layout:
    Bars are intentionally short and fixed-width (BAR_WIDTH) rather
    than stretching to fill the row — a full-width bar per row reads
    as noisy/loud, and a short, consistent bar length keeps the list
    calm and comparable at a glance. A flexible spacer pushes the
    size/percent/tier text group flush to the right; those labels are
    NOT fixed-width (only a minimum), so long values are never clipped.

Visual style:
    Cards and rows are borderless (background + rounded corners only),
    matching the rest of the dashboard's flat/minimal look. Buttons
    keep a thin border, since interactive controls benefit from a
    visible edge for clickability — that's a functional affordance,
    not decorative card framing, so it's exempt from the borderless rule.
"""

import logging
import os
import shutil
from typing import Dict, List, Optional

import psutil
from PyQt6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QWidget,
    QFrame,
    QProgressBar,
    QGraphicsDropShadowEffect,
)
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QFont, QMovie, QColor

from core.storage.models import DirectoryNode
from core.storage_worker_thread import StorageScanThread
from ui.widgets.base_widget import BaseWidget
from ui.styles.fonts import get_pixel_font_family


logger = logging.getLogger(__name__)

# How many levels deep each scan (initial or drill-down) goes before
# stopping — matches analyzer.py's MAX_SCAN_DEPTH default.
SCAN_DEPTH = 2

# Only the top N folders (by size, already sorted) are rendered per
# level — keeps row-building cheap even in folders with hundreds of
# subfolders.
MAX_DISPLAYED_ROWS = 15

# Card color palette (shared visual language with the rest of the
# dashboard). No CARD_BORDER_COLOR — cards/rows here are intentionally
# borderless, matching CPU/RAM/Disk/Health.
CARD_BACKGROUND_COLOR = "#3d3d5c"
CARD_INNER_BACKGROUND = "#2a2a44"
ACCENT_COLOR = "#D8A0A8"  # Dusty Rose, Storage's accent color

# Border used only for interactive controls (buttons) — a functional
# affordance, kept separate from the borderless card/row styling above.
BUTTON_BORDER_COLOR = "#6a6a9a"

# Title underline accent (thin colored bar under the title text)
UNDERLINE_HEIGHT = 2
UNDERLINE_WIDTH = 130  # px — roughly matches "STORAGE ANALYZER" text width

# Drop shadow (soft, subtle — matches the rest of the dashboard)
SHADOW_BLUR_RADIUS = 24
SHADOW_OFFSET_Y = 6
SHADOW_COLOR = QColor(0, 0, 0, 160)

# --- Tier system ---
# Percent-of-parent thresholds that separate the 4 tiers. A folder
# using less than TIER_THRESHOLDS[0]% of its parent's total is Tier 0
# (Safe); at or above TIER_THRESHOLDS[-1]% it's Tier 3 (Clean Up).
TIER_THRESHOLDS = (15, 40, 70)
TIER_LABELS = ("Safe", "Watch", "Consider", "Clean Up")
# 4-step severity gradient built from the shared dashboard palette:
# sage (safe) -> muted blue (ok) -> muted amber (consider) -> muted
# terracotta (clean up). Only 3 tones exist in the shared severity
# palette, so amber fills the gap as a middle step here.
TIER_COLORS = ("#8FD6A3", "#82B5D8", "#D6A85F", "#D97A6B")

# --- Row layout constants ---
# Fixed bar width keeps every bar the same short, calm length instead
# of stretching to fill the row — a deliberately minimalist choice.
BAR_WIDTH = 220
BAR_HEIGHT = 12
ROW_SPACING = 14
ROW_CONTENT_MARGINS = (14, 9, 18, 9)  # left, top, right, bottom

# --- Companion GIF assets ---
GIF_DIR = os.path.join("assets", "gifs")
TIER_GIF_FILENAMES = ("tier00.gif", "tier01.gif", "tier02.gif", "tier03.gif")
IDLE_GIF_FILENAME = "notier.gif"
# Was 180x180 — bumped up for more visual presence. For crisp pixel
# art, this should be an exact integer multiple of the GIF's actual
# source resolution (e.g. 80px source -> 160/240/320 target). Adjust
# once the source size is confirmed.
COMPANION_SIZE = QSize(240, 240)

BUTTON_STYLE = f"""
    QPushButton {{
        background-color: {CARD_INNER_BACKGROUND};
        color: #ffffff;
        border: 1px solid {BUTTON_BORDER_COLOR};
        border-radius: 6px;
        padding: 6px 14px;
    }}
    QPushButton:hover {{
        background-color: #4a4a6c;
    }}
    QPushButton:disabled {{
        color: #666666;
    }}
"""


class StorageWidget(BaseWidget):
    """
    Widget for browsing folder sizes with a disk picker entry point,
    4-tier severity classification, and drill-down navigation.

    Attributes:
        card (QFrame): The outer card frame. Borderless — only
            background, rounded corners, and a drop shadow.
        nav_stack (List[DirectoryNode]): Folders visited, root to
            current — nav_stack[-1] is the currently displayed folder.
            Used to support the "Back" button. Empty while the disk
            picker is showing.
        current_disk_path (Optional[str]): Mount point / drive root of
            the disk currently being browsed, or None if still on the
            disk picker.
        current_thread (Optional[StorageScanThread]): The in-flight
            scan thread, if any. Kept referenced so Qt doesn't garbage
            collect it mid-scan, and to avoid starting a second scan
            while one is already running.
    """

    def __init__(self) -> None:
        """Initialize storage widget."""
        super().__init__("Storage Analyzer")
        self._pixel_font = get_pixel_font_family()
        self.nav_stack: List[DirectoryNode] = []
        self.current_disk_path: Optional[str] = None
        self.current_thread: Optional[StorageScanThread] = None
        self._row_widgets: Dict[str, dict] = {}
        self._companion_movies: Dict[str, QMovie] = {}
        self._setup_ui()
        self._load_companion_movies()
        self._populate_disk_picker()
        logger.debug("StorageWidget initialized")

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        """Build the card-style UI layout: title, stacked views, companion."""
        outer_layout = QVBoxLayout()
        outer_layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(outer_layout)

        # --- CARD CONTAINER (borderless — background + rounded corners only) ---
        self.card = QFrame()
        self.card.setStyleSheet(
            f"""
            QFrame {{
                background-color: {CARD_BACKGROUND_COLOR};
                border: none;
                border-radius: 14px;
            }}
        """
        )

        # Soft drop shadow behind the card, matching the rest of the
        # dashboard's cards.
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

        # --- TITLE ---
        title = QLabel("STORAGE ANALYZER")
        title.setFont(QFont(self._pixel_font, 11))
        title.setStyleSheet(f"color: {ACCENT_COLOR}; border: none;")
        card_layout.addWidget(title)

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

        # --- STATUS LABEL (shows "Scanning..." / error messages) ---
        self.status_label = QLabel("")
        self.status_label.setFont(QFont(self._pixel_font, 7))
        self.status_label.setStyleSheet(f"color: {ACCENT_COLOR}; border: none;")
        self.status_label.hide()
        card_layout.addWidget(self.status_label)

        # --- STACKED VIEWS: disk picker (0) / folder list (1) ---
        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_disk_picker_page())
        self.stack.addWidget(self._build_folder_list_page())
        card_layout.addWidget(self.stack)

        # --- COMPANION GIF ---
        # No border/frame of its own — it shares the card's background
        # directly so there's no visible seam between the list above
        # and the companion below, just generous top spacing.
        card_layout.addWidget(self._build_companion_area())

    def _build_disk_picker_page(self) -> QWidget:
        """Build the disk-picker view (shown on load / via "Disks" button)."""
        page = QWidget()
        page_layout = QVBoxLayout()
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(8)
        page.setLayout(page_layout)

        hint_label = QLabel("Select a disk to scan:")
        hint_label.setFont(QFont(self._pixel_font, 7))
        hint_label.setStyleSheet("color: #aaaaaa; border: none;")
        page_layout.addWidget(hint_label)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setMinimumHeight(320)
        scroll_area.setStyleSheet(
            f"""
            QScrollArea {{
                background-color: {CARD_INNER_BACKGROUND};
                border: none;
                border-radius: 8px;
            }}
        """
        )

        disk_list_container = QWidget()
        disk_list_container.setStyleSheet("background-color: transparent;")
        self.disk_list_layout = QVBoxLayout()
        self.disk_list_layout.setSpacing(6)
        self.disk_list_layout.setContentsMargins(10, 10, 10, 10)
        self.disk_list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        disk_list_container.setLayout(self.disk_list_layout)

        scroll_area.setWidget(disk_list_container)
        page_layout.addWidget(scroll_area)

        return page

    def _build_folder_list_page(self) -> QWidget:
        """Build the folder-list view (shown after a disk is picked)."""
        page = QWidget()
        page_layout = QVBoxLayout()
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(10)
        page.setLayout(page_layout)

        # --- PATH + CONTROLS ROW ---
        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(8)

        self.path_label = QLabel("")
        self.path_label.setFont(QFont(self._pixel_font, 7))
        self.path_label.setStyleSheet("color: #aaaaaa; border: none;")
        controls_layout.addWidget(self.path_label, stretch=1)

        self.disks_button = QPushButton("Disks")
        self.disks_button.setFont(QFont(self._pixel_font, 7))
        self.disks_button.setStyleSheet(BUTTON_STYLE)
        self.disks_button.clicked.connect(self._show_disk_picker)
        controls_layout.addWidget(self.disks_button)

        self.back_button = QPushButton("Back")
        self.back_button.setFont(QFont(self._pixel_font, 7))
        self.back_button.setStyleSheet(BUTTON_STYLE)
        self.back_button.setEnabled(False)
        self.back_button.clicked.connect(self._go_back)
        controls_layout.addWidget(self.back_button)

        self.rescan_button = QPushButton("Rescan")
        self.rescan_button.setFont(QFont(self._pixel_font, 7))
        self.rescan_button.setStyleSheet(BUTTON_STYLE)
        self.rescan_button.setEnabled(False)
        self.rescan_button.clicked.connect(self._rescan_current)
        controls_layout.addWidget(self.rescan_button)

        page_layout.addLayout(controls_layout)

        # --- SCROLLABLE FOLDER LIST ---
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setMinimumHeight(280)
        scroll_area.setStyleSheet(
            f"""
            QScrollArea {{
                background-color: {CARD_INNER_BACKGROUND};
                border: none;
                border-radius: 8px;
            }}
        """
        )

        list_container = QWidget()
        list_container.setStyleSheet("background-color: transparent;")
        self.list_layout = QVBoxLayout()
        self.list_layout.setSpacing(6)
        self.list_layout.setContentsMargins(10, 10, 10, 10)
        self.list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        list_container.setLayout(self.list_layout)

        scroll_area.setWidget(list_container)
        page_layout.addWidget(scroll_area)

        return page

    def _build_companion_area(self) -> QWidget:
        """Build the centered companion GIF area at the bottom of the card."""
        wrapper = QWidget()
        wrapper.setStyleSheet("background-color: transparent;")
        wrapper_layout = QHBoxLayout()
        # Generous top margin so the companion clearly reads as its
        # own relaxed zone rather than butting against the list above.
        wrapper_layout.setContentsMargins(0, 18, 0, 4)
        wrapper.setLayout(wrapper_layout)

        self.companion_label = QLabel()
        self.companion_label.setFixedSize(COMPANION_SIZE)
        # Background matches the card exactly. If a GIF's own frames
        # aren't transparent, this keeps any visible edge blending
        # into the card instead of contrasting against it.
        self.companion_label.setStyleSheet(
            f"background-color: {CARD_BACKGROUND_COLOR}; border: none;"
        )
        self.companion_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        wrapper_layout.addStretch(1)
        wrapper_layout.addWidget(self.companion_label)
        wrapper_layout.addStretch(1)

        return wrapper

    # ------------------------------------------------------------------
    # Companion GIF handling
    # ------------------------------------------------------------------

    def _load_companion_movies(self) -> None:
        """
        Preload all companion QMovies (idle + 4 tiers) once at startup,
        so hover events only need to swap an already-loaded QMovie
        rather than re-reading from disk each time.
        """
        gif_files = {"idle": IDLE_GIF_FILENAME}
        for tier_index, filename in enumerate(TIER_GIF_FILENAMES):
            gif_files[f"tier{tier_index}"] = filename

        for key, filename in gif_files.items():
            path = os.path.join(GIF_DIR, filename)
            movie = QMovie(path)
            if not movie.isValid():
                logger.warning("Companion GIF not found or invalid: '%s'", path)
            movie.setScaledSize(COMPANION_SIZE)
            self._companion_movies[key] = movie

        self._show_companion("idle")

    def _show_companion(self, key: str) -> None:
        """
        Swap the companion label to the given preloaded movie and play
        it. Falls back silently if the movie failed to load.

        Args:
            key: "idle" or "tier0".."tier3".
        """
        movie = self._companion_movies.get(key)
        if movie is None or not movie.isValid():
            return

        current = self.companion_label.movie()
        if current is not None and current is not movie:
            current.stop()

        self.companion_label.setMovie(movie)
        movie.start()

    def _attach_hover_companion(self, widget: QWidget, tier_index: int) -> None:
        """
        Wire a row/card widget's hover events to swap the companion GIF
        to the given tier while hovered, and back to idle on leave.

        Args:
            widget: The QFrame (disk card or folder row) to attach to.
            tier_index: 0-3, indexing into TIER_LABELS / companion movies.
        """
        widget.enterEvent = lambda event, t=tier_index: self._show_companion(f"tier{t}")
        widget.leaveEvent = lambda event: self._show_companion("idle")

    # ------------------------------------------------------------------
    # Tier helpers
    # ------------------------------------------------------------------

    def _tier_index_for_percent(self, percent: float) -> int:
        """Map a percent-of-parent value to a tier index 0-3."""
        if percent < TIER_THRESHOLDS[0]:
            return 0
        elif percent < TIER_THRESHOLDS[1]:
            return 1
        elif percent < TIER_THRESHOLDS[2]:
            return 2
        else:
            return 3

    # ------------------------------------------------------------------
    # Disk picker
    # ------------------------------------------------------------------

    def _populate_disk_picker(self) -> None:
        """Detect available disks/partitions and build a card for each."""
        # Clear any existing cards (supports being called again later)
        while self.disk_list_layout.count():
            item = self.disk_list_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        try:
            partitions = psutil.disk_partitions(all=False)
        except Exception as e:
            logger.error("Failed to enumerate disks: %s", e)
            partitions = []

        if not partitions:
            empty_label = QLabel("No disks detected.")
            empty_label.setFont(QFont(self._pixel_font, 7))
            empty_label.setStyleSheet("color: #888888; border: none;")
            self.disk_list_layout.addWidget(empty_label)
            return

        for partition in partitions:
            try:
                usage = shutil.disk_usage(partition.mountpoint)
            except OSError as e:
                # Unreadable/empty removable drives, etc. — skip rather
                # than crash the whole picker.
                logger.debug("Skipping disk %s: %s", partition.mountpoint, e)
                continue

            card = self._create_disk_card(partition.mountpoint, usage)
            self.disk_list_layout.addWidget(card)

    def _create_disk_card(self, mount_point: str, usage) -> QFrame:
        """
        Build one clickable card representing a disk.

        Args:
            mount_point: The disk's mount point / drive root (e.g. "C:\\").
            usage: Result of shutil.disk_usage() — has .total/.used/.free.

        Returns:
            QFrame: The completed card, ready to add to the disk list.
        """
        percent_used = (usage.used / usage.total * 100.0) if usage.total else 0.0
        tier_index = self._tier_index_for_percent(percent_used)

        card = QFrame()
        card.setCursor(Qt.CursorShape.PointingHandCursor)
        card.setStyleSheet(
            f"""
            QFrame {{
                background-color: {CARD_INNER_BACKGROUND};
                border: none;
                border-radius: 8px;
            }}
            QFrame:hover {{
                background-color: #4a4a6c;
            }}
        """
        )

        row_layout = QHBoxLayout()
        row_layout.setContentsMargins(*ROW_CONTENT_MARGINS)
        row_layout.setSpacing(ROW_SPACING)
        card.setLayout(row_layout)

        name_label = QLabel(mount_point)
        name_label.setFont(QFont(self._pixel_font, 8))
        name_label.setStyleSheet("color: #ffffff; border: none;")
        name_label.setFixedWidth(70)
        row_layout.addWidget(name_label)

        bar = QProgressBar()
        bar.setMaximum(100)
        bar.setValue(int(percent_used))
        bar.setTextVisible(False)
        bar.setFixedHeight(BAR_HEIGHT)
        bar.setFixedWidth(BAR_WIDTH)
        self._style_pill_bar(bar, TIER_COLORS[tier_index])
        row_layout.addWidget(bar)

        # Pushes the text group flush right, independent of bar length.
        row_layout.addStretch(1)

        usage_label = QLabel(
            f"{self._format_size(usage.used)} / {self._format_size(usage.total)}"
        )
        usage_label.setFont(QFont(self._pixel_font, 7))
        usage_label.setStyleSheet("color: #cccccc; border: none;")
        usage_label.setMinimumWidth(150)
        usage_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        row_layout.addWidget(usage_label)

        tier_label = QLabel(TIER_LABELS[tier_index])
        tier_label.setFont(QFont(self._pixel_font, 7))
        tier_label.setStyleSheet(f"color: {TIER_COLORS[tier_index]}; border: none;")
        tier_label.setMinimumWidth(75)
        tier_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        row_layout.addWidget(tier_label)

        card.mousePressEvent = lambda event, p=mount_point: self._select_disk(p)
        self._attach_hover_companion(card, tier_index)

        return card

    def _select_disk(self, mount_point: str) -> None:
        """Handle a disk being picked: switch views and start scanning it."""
        self.current_disk_path = mount_point
        self.nav_stack = []
        self.stack.setCurrentIndex(1)
        self._run_scan(mount_point)

    def _show_disk_picker(self) -> None:
        """Return to the disk picker view."""
        self.current_disk_path = None
        self.nav_stack = []
        self.stack.setCurrentIndex(0)

    # ------------------------------------------------------------------
    # Scan triggering
    # ------------------------------------------------------------------

    def _rescan_current(self) -> None:
        """Re-scan the folder currently being viewed."""
        if not self.nav_stack:
            return
        current_path = self.nav_stack[-1].path
        # Drop the stale node; the scan result will replace it in place
        # once complete (see _on_scan_complete).
        self._run_scan(current_path, replace_top=True)

    def _drill_into(self, node: DirectoryNode) -> None:
        """
        Navigate into a child folder, scanning it first if needed.

        Args:
            node: The DirectoryNode the user clicked on.
        """
        already_scanned = len(node.children) > 0 or node.file_count > 0

        if already_scanned:
            self.nav_stack.append(node)
            self._render_current_level()
        else:
            # Placeholder node from hitting the parent scan's depth
            # limit — scan it now, on demand.
            self.nav_stack.append(node)
            self._run_scan(node.path, replace_top=True)

    def _go_back(self) -> None:
        """Return to the previous (parent) folder in the nav stack."""
        if len(self.nav_stack) > 1:
            self.nav_stack.pop()
            self._render_current_level()

    def _run_scan(self, path: str, replace_top: bool = False) -> None:
        """
        Kick off a background scan for the given path.

        Args:
            path: Folder to scan.
            replace_top: If True, the scan result replaces the current
                top of nav_stack in place (used for drill-down and
                rescan); if False, this is treated as a brand-new root
                scan (used when a disk is first picked).
        """
        if self.current_thread is not None and self.current_thread.isRunning():
            logger.debug("Scan already in progress, ignoring new request")
            return

        self._set_scanning_state(True)

        self.current_thread = StorageScanThread(path, SCAN_DEPTH)
        self.current_thread.scan_complete.connect(
            lambda result: self._on_scan_complete(result, replace_top)
        )
        self.current_thread.scan_error.connect(self._on_scan_error)
        self.current_thread.start()

    # ------------------------------------------------------------------
    # Scan result handling
    # ------------------------------------------------------------------

    def _on_scan_complete(self, result: DirectoryNode, replace_top: bool) -> None:
        """
        Handle a finished scan.

        Args:
            result: The freshly-scanned DirectoryNode tree.
            replace_top: Whether this scan should replace the current
                top of nav_stack (drill-down/rescan) or become a new
                root (initial disk scan).
        """
        self._set_scanning_state(False)

        if replace_top and self.nav_stack:
            # Preserve the parent link so "Back" and percent_of_parent()
            # still work correctly after swapping in the fresh data.
            result.parent = self.nav_stack[-1].parent
            self.nav_stack[-1] = result
        else:
            self.nav_stack = [result]

        self._render_current_level()
        logger.info("Storage scan complete: %s", result.path)

    def _on_scan_error(self, message: str) -> None:
        """Handle a failed scan by showing the error inline."""
        self._set_scanning_state(False)
        self.status_label.setText(f"Scan failed: {message}")
        self.status_label.show()
        logger.error("Storage scan error: %s", message)

    def _set_scanning_state(self, scanning: bool) -> None:
        """Toggle button states and status text while a scan runs."""
        self.rescan_button.setEnabled(not scanning and len(self.nav_stack) > 0)
        self.back_button.setEnabled(not scanning and len(self.nav_stack) > 1)
        self.disks_button.setEnabled(not scanning)

        if scanning:
            self.status_label.setText("Scanning...")
            self.status_label.show()
        else:
            self.status_label.hide()

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _render_current_level(self) -> None:
        """Redraw the folder list for the current top of nav_stack."""
        if not self.nav_stack:
            return

        current = self.nav_stack[-1]

        self.path_label.setText(current.path)
        self.rescan_button.setEnabled(True)
        self.back_button.setEnabled(len(self.nav_stack) > 1)

        # Clear existing rows
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._row_widgets.clear()

        if not current.children:
            empty_label = QLabel("No subfolders here.")
            empty_label.setFont(QFont(self._pixel_font, 7))
            empty_label.setStyleSheet("color: #888888; border: none;")
            self.list_layout.addWidget(empty_label)
            return

        # children are already sorted largest-first by the analyzer
        displayed = current.children[:MAX_DISPLAYED_ROWS]
        remaining = len(current.children) - len(displayed)

        for child in displayed:
            row = self._create_folder_row(child)
            self.list_layout.addWidget(row)

        if remaining > 0:
            more_label = QLabel(f"+ {remaining} more not shown")
            more_label.setFont(QFont(self._pixel_font, 7))
            more_label.setStyleSheet("color: #666677; border: none;")
            self.list_layout.addWidget(more_label)

    def _create_folder_row(self, node: DirectoryNode) -> QFrame:
        """
        Build one clickable row representing a folder.

        Args:
            node: The DirectoryNode this row represents.

        Returns:
            QFrame: The completed row, ready to add to the list layout.
        """
        percent = node.percent_of_parent()
        tier_index = self._tier_index_for_percent(percent)

        row = QFrame()
        row.setCursor(Qt.CursorShape.PointingHandCursor)
        row.setStyleSheet(
            f"""
            QFrame {{
                background-color: {CARD_INNER_BACKGROUND};
                border: none;
                border-radius: 8px;
            }}
            QFrame:hover {{
                background-color: #4a4a6c;
            }}
        """
        )

        row_layout = QHBoxLayout()
        row_layout.setContentsMargins(*ROW_CONTENT_MARGINS)
        row_layout.setSpacing(ROW_SPACING)
        row.setLayout(row_layout)

        icon_prefix = "🔒 " if not node.is_accessible else ""
        name_label = QLabel(f"{icon_prefix}{node.name}")
        name_label.setFont(QFont(self._pixel_font, 8))
        name_label.setStyleSheet("color: #ffffff; border: none;")
        name_label.setFixedWidth(150)
        row_layout.addWidget(name_label)

        bar = QProgressBar()
        bar.setMaximum(100)
        bar.setValue(int(percent))
        bar.setTextVisible(False)
        bar.setFixedHeight(BAR_HEIGHT)
        bar.setFixedWidth(BAR_WIDTH)
        self._style_pill_bar(bar, TIER_COLORS[tier_index])
        row_layout.addWidget(bar)

        # Pushes the text group flush right, independent of bar length.
        row_layout.addStretch(1)

        size_label = QLabel(self._format_size(node.size_bytes))
        size_label.setFont(QFont(self._pixel_font, 7))
        size_label.setStyleSheet("color: #cccccc; border: none;")
        size_label.setMinimumWidth(70)
        size_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        row_layout.addWidget(size_label)

        percent_label = QLabel(f"{percent:.0f}%")
        percent_label.setFont(QFont(self._pixel_font, 7))
        percent_label.setStyleSheet("color: #cccccc; border: none;")
        percent_label.setMinimumWidth(45)
        percent_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        row_layout.addWidget(percent_label)

        tier_label = QLabel(TIER_LABELS[tier_index])
        tier_label.setFont(QFont(self._pixel_font, 7))
        tier_label.setStyleSheet(f"color: {TIER_COLORS[tier_index]}; border: none;")
        tier_label.setMinimumWidth(75)
        tier_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        row_layout.addWidget(tier_label)

        row.mousePressEvent = lambda event, n=node: self._drill_into(n)
        self._attach_hover_companion(row, tier_index)

        return row

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _style_pill_bar(self, bar: QProgressBar, color: str) -> None:
        """Apply the padded, pill-shaped bar style used across the dashboard."""
        bar.setStyleSheet(
            f"""
            QProgressBar {{
                background-color: {CARD_BACKGROUND_COLOR};
                border: none;
                border-radius: 6px;
            }}
            QProgressBar::chunk {{
                background-color: {color};
                border-radius: 5px;
            }}
        """
        )

    def _format_size(self, size_bytes: int) -> str:
        """Format a byte count as a human-readable string (MB or GB)."""
        gb = size_bytes / (1024 ** 3)
        if gb >= 1:
            return f"{gb:.1f} GB"
        mb = size_bytes / (1024 ** 2)
        return f"{mb:.0f} MB"

    def update_data(self, data) -> None:
        """
        Not used — StorageWidget is on-demand (user-triggered), not
        driven by WorkerThread's continuous polling signals like the
        other dashboard widgets. Present only to satisfy BaseWidget's
        interface.
        """
        pass