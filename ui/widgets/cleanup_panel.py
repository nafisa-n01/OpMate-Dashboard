"""
ui/widgets/cleanup_panel.py
------------------------------
Cleanup Advisor panel: a compact checklist of safe-to-delete cache/temp
categories (Temp Files, Recycle Bin, Browser Cache, etc.), each shown
with its detected size. The user checks which categories to include,
clicks "Clean Selected", reviews an explicit confirmation dialog listing
exactly what will be removed, and only then does deletion happen.

Placement:
    Designed to sit alongside the companion GIF at the bottom of the
    Storage Analyzer card (see storage_widget.py) — a narrower, taller
    panel rather than a full-width section, so the two fit side by side.

Safety flow:
    Scan (read-only) -> user reviews sizes -> user checks categories ->
    "Clean Selected" -> confirmation dialog (exact list + total size) ->
    only on explicit "Yes" does CleanupDeleteThread actually run.
    Nothing is ever deleted without that confirmation step.
"""

import logging
from typing import Dict, List, Optional

from PyQt6.QtWidgets import (
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QWidget,
    QFrame,
    QCheckBox,
    QMessageBox,
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from core.cleanup.models import CleanupCategory, CleanupResult
from core.cleanup_worker_thread import CleanupScanThread, CleanupDeleteThread
from ui.styles.fonts import get_pixel_font_family


logger = logging.getLogger(__name__)

# Matches the visual language established by the rest of the dashboard
# (borderless cards, muted palette). Uses Storage's own accent since
# this panel lives inside the Storage tab.
PANEL_BACKGROUND = "#2a2a44"
ACCENT_COLOR = "#D8A0A8"  # Dusty Rose, matches StorageWidget
BUTTON_BORDER_COLOR = "#6a6a9a"
SAFE_COLOR = "#8FD6A3"

PANEL_WIDTH = 340

BUTTON_STYLE = f"""
    QPushButton {{
        background-color: #3d3d5c;
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

CHECKBOX_STYLE = f"""
    QCheckBox {{
        color: #ffffff;
        spacing: 8px;
    }}
    QCheckBox::indicator {{
        width: 14px;
        height: 14px;
        border: 1px solid {BUTTON_BORDER_COLOR};
        border-radius: 3px;
        background-color: #1f1f33;
    }}
    QCheckBox::indicator:checked {{
        background-color: {ACCENT_COLOR};
        border: 1px solid {ACCENT_COLOR};
    }}
"""


class CleanupPanel(QWidget):
    """
    Compact panel for reviewing and cleaning safe cache/temp categories.

    Attributes:
        categories (List[CleanupCategory]): Latest scan results.
        _category_rows (Dict[str, dict]): Maps category key -> widget
            references (checkbox, size label) for in-place updates.
        _scan_thread (Optional[CleanupScanThread]): In-flight scan, if any.
        _delete_thread (Optional[CleanupDeleteThread]): In-flight
            deletion, if any.
    """

    def __init__(self) -> None:
        """Initialize the cleanup panel."""
        super().__init__()
        self._pixel_font = get_pixel_font_family()
        self.categories: List[CleanupCategory] = []
        self._category_rows: Dict[str, dict] = {}
        self._scan_thread: Optional[CleanupScanThread] = None
        self._delete_thread: Optional[CleanupDeleteThread] = None
        self._setup_ui()
        self.run_scan()

    def _setup_ui(self) -> None:
        """Build the panel layout."""
        self.setFixedWidth(PANEL_WIDTH)
        self.setStyleSheet(
            f"""
            QWidget {{
                background-color: {PANEL_BACKGROUND};
                border-radius: 10px;
            }}
        """
        )

        layout = QVBoxLayout()
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        self.setLayout(layout)

        # --- HEADER ---
        header_layout = QHBoxLayout()

        title = QLabel("CLEANUP ADVISOR")
        title.setFont(QFont(self._pixel_font, 9))
        title.setStyleSheet(f"color: {ACCENT_COLOR}; border: none;")
        header_layout.addWidget(title)

        header_layout.addStretch()

        self.rescan_button = QPushButton("Rescan")
        self.rescan_button.setFont(QFont(self._pixel_font, 6))
        self.rescan_button.setStyleSheet(BUTTON_STYLE)
        self.rescan_button.clicked.connect(self.run_scan)
        header_layout.addWidget(self.rescan_button)

        layout.addLayout(header_layout)

        # --- STATUS LABEL ---
        self.status_label = QLabel("")
        self.status_label.setFont(QFont(self._pixel_font, 6))
        self.status_label.setStyleSheet(f"color: {ACCENT_COLOR}; border: none;")
        self.status_label.setWordWrap(True)
        self.status_label.hide()
        layout.addWidget(self.status_label)

        # --- CATEGORY LIST (scrollable) ---
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFixedHeight(150)
        scroll_area.setStyleSheet(
            """
            QScrollArea {
                background-color: #1f1f33;
                border: none;
                border-radius: 6px;
            }
        """
        )

        list_container = QWidget()
        list_container.setStyleSheet("background-color: transparent;")
        self.list_layout = QVBoxLayout()
        self.list_layout.setSpacing(4)
        self.list_layout.setContentsMargins(8, 8, 8, 8)
        self.list_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        list_container.setLayout(self.list_layout)

        scroll_area.setWidget(list_container)
        layout.addWidget(scroll_area)

        # --- TOTAL + CLEAN BUTTON ---
        self.total_label = QLabel("Selected: 0 MB")
        self.total_label.setFont(QFont(self._pixel_font, 7))
        self.total_label.setStyleSheet("color: #aaaaaa; border: none;")
        layout.addWidget(self.total_label)

        self.clean_button = QPushButton("Clean Selected")
        self.clean_button.setFont(QFont(self._pixel_font, 7))
        self.clean_button.setStyleSheet(BUTTON_STYLE)
        self.clean_button.setEnabled(False)
        self.clean_button.clicked.connect(self._on_clean_clicked)
        layout.addWidget(self.clean_button)

    # ------------------------------------------------------------------
    # Scanning
    # ------------------------------------------------------------------

    def run_scan(self) -> None:
        """Start a background scan of all cleanup categories."""
        if self._scan_thread is not None and self._scan_thread.isRunning():
            return

        self._set_busy_state(True, "Scanning...")

        self._scan_thread = CleanupScanThread()
        self._scan_thread.scan_complete.connect(self._on_scan_complete)
        self._scan_thread.scan_error.connect(self._on_scan_error)
        self._scan_thread.start()

    def _on_scan_complete(self, categories: List[CleanupCategory]) -> None:
        """
        Handle a finished scan by rendering the category checklist.

        Args:
            categories: Full scan results (may include non-applicable
                categories with exists=False, which are filtered out
                here before display).
        """
        self._set_busy_state(False)

        self.categories = [c for c in categories if c.exists]
        self._render_category_list()
        self._update_selection_total()

        logger.info(
            "CleanupPanel scan complete: %d applicable categories",
            len(self.categories),
        )

    def _on_scan_error(self, message: str) -> None:
        """Handle a failed scan."""
        self._set_busy_state(False, f"Scan failed: {message}")

    def _set_busy_state(self, busy: bool, message: str = "") -> None:
        """Toggle button states and status text while scanning/cleaning."""
        self.rescan_button.setEnabled(not busy)
        self.clean_button.setEnabled(not busy and self._any_selected())

        if busy or message:
            self.status_label.setText(message)
            self.status_label.show()
        else:
            self.status_label.hide()

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _render_category_list(self) -> None:
        """Rebuild the checklist rows from self.categories."""
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._category_rows.clear()

        if not self.categories:
            empty_label = QLabel("Nothing found to clean.")
            empty_label.setFont(QFont(self._pixel_font, 7))
            empty_label.setStyleSheet(f"color: {SAFE_COLOR}; border: none;")
            self.list_layout.addWidget(empty_label)
            return

        for category in self.categories:
            row = self._create_category_row(category)
            self.list_layout.addWidget(row)

    def _create_category_row(self, category: CleanupCategory) -> QWidget:
        """
        Build one checklist row: checkbox + name, with size and a
        one-line description shown as a tooltip.

        Args:
            category: The CleanupCategory this row represents.

        Returns:
            QWidget: The completed row.
        """
        row = QWidget()
        row.setStyleSheet("background-color: transparent;")
        row_layout = QHBoxLayout()
        row_layout.setContentsMargins(0, 2, 0, 2)
        row.setLayout(row_layout)

        checkbox = QCheckBox(category.display_name)
        checkbox.setFont(QFont(self._pixel_font, 7))
        checkbox.setStyleSheet(CHECKBOX_STYLE)
        checkbox.setToolTip(category.description)
        checkbox.setChecked(category.selected)
        checkbox.stateChanged.connect(
            lambda state, c=category: self._on_category_toggled(c, state)
        )
        row_layout.addWidget(checkbox)

        row_layout.addStretch()

        size_label = QLabel(self._format_size(category.size_bytes))
        size_label.setFont(QFont(self._pixel_font, 7))
        size_label.setStyleSheet("color: #cccccc; border: none;")
        row_layout.addWidget(size_label)

        self._category_rows[category.key] = {
            "checkbox": checkbox,
            "size_label": size_label,
        }

        return row

    def _on_category_toggled(self, category: CleanupCategory, state: int) -> None:
        """Handle a checkbox being checked/unchecked."""
        category.selected = state == Qt.CheckState.Checked.value
        self._update_selection_total()

    def _update_selection_total(self) -> None:
        """Recompute and display the total size of selected categories."""
        selected = [c for c in self.categories if c.selected]
        total_bytes = sum(c.size_bytes for c in selected)

        self.total_label.setText(
            f"Selected: {self._format_size(total_bytes)}"
            + (f" ({len(selected)} categories)" if selected else "")
        )
        self.clean_button.setEnabled(len(selected) > 0)

    def _any_selected(self) -> bool:
        """Whether at least one category is currently checked."""
        return any(c.selected for c in self.categories)

    # ------------------------------------------------------------------
    # Cleaning (destructive — confirmation required)
    # ------------------------------------------------------------------

    def _on_clean_clicked(self) -> None:
        """
        Handle "Clean Selected": show an explicit confirmation dialog
        listing exactly what will be deleted before doing anything.
        """
        selected = [c for c in self.categories if c.selected]
        if not selected:
            return

        total_bytes = sum(c.size_bytes for c in selected)
        names = "\n".join(f"  • {c.display_name}" for c in selected)

        confirmation = QMessageBox(self)
        confirmation.setWindowTitle("Confirm Cleanup")
        confirmation.setIcon(QMessageBox.Icon.Question)
        confirmation.setText(
            f"Delete the following {len(selected)} categories?\n\n"
            f"{names}\n\n"
            f"Total space to free: {self._format_size(total_bytes)}\n\n"
            "This cannot be undone."
        )
        confirmation.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel
        )
        confirmation.setDefaultButton(QMessageBox.StandardButton.Cancel)

        if confirmation.exec() != QMessageBox.StandardButton.Yes:
            return

        self._run_cleanup(selected)

    def _run_cleanup(self, categories: List[CleanupCategory]) -> None:
        """Start the background deletion thread for confirmed categories."""
        if self._delete_thread is not None and self._delete_thread.isRunning():
            return

        self._set_busy_state(True, "Cleaning...")

        self._delete_thread = CleanupDeleteThread(categories)
        self._delete_thread.delete_complete.connect(self._on_delete_complete)
        self._delete_thread.delete_error.connect(self._on_delete_error)
        self._delete_thread.start()

    def _on_delete_complete(self, result: CleanupResult) -> None:
        """Handle finished cleanup: show a summary, then rescan."""
        summary = (
            f"Freed {self._format_size(result.bytes_freed)} "
            f"({result.files_deleted} files deleted"
            + (f", {result.files_skipped} skipped" if result.files_skipped else "")
            + ")"
        )
        logger.info("Cleanup finished: %s", summary)

        self._set_busy_state(False, summary)

        # Rescan to reflect the new (smaller) sizes.
        self.run_scan()

    def _on_delete_error(self, message: str) -> None:
        """Handle an unexpected cleanup failure."""
        self._set_busy_state(False, f"Cleanup failed: {message}")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _format_size(self, size_bytes: int) -> str:
        """Format a byte count as a human-readable string (MB or GB)."""
        gb = size_bytes / (1024 ** 3)
        if gb >= 1:
            return f"{gb:.2f} GB"
        mb = size_bytes / (1024 ** 2)
        return f"{mb:.0f} MB"