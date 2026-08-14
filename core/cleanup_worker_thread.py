"""
core/cleanup_worker_thread.py
--------------------------------
Background threads for the Cleanup Advisor feature.

Two separate thread classes, mirroring the two distinct user actions
in the UI:
    - CleanupScanThread: read-only, runs when the Cleanup tab/section
      opens (or "Rescan" is clicked). Measures category sizes.
    - CleanupDeleteThread: destructive, runs ONLY after the user has
      reviewed sizes and explicitly confirmed which categories to
      delete. Performs the actual removal.

Both follow the same transient, run-once pattern as
core/storage_worker_thread.py's StorageScanThread — created fresh per
action, not a persistent polling loop like WorkerThread.
"""

import logging
from typing import List

from PyQt6.QtCore import QThread, pyqtSignal

from core.cleanup.models import CleanupCategory, CleanupResult
from core.cleanup.scanner import CleanupScanner
from core.cleanup.cleaner import Cleaner


logger = logging.getLogger(__name__)


class CleanupScanThread(QThread):
    """
    Runs CleanupScanner.get_categories() on a background thread.

    Read-only — does not modify the filesystem. Safe to run any time,
    including automatically when the Cleanup section is first opened.

    Signals:
        scan_complete (list): Emitted with the full List[CleanupCategory]
            once scanning finishes successfully.
        scan_error (str): Emitted with a human-readable error message
            if scanning fails unexpectedly.
    """

    scan_complete = pyqtSignal(list)
    scan_error = pyqtSignal(str)

    def __init__(self, parent=None) -> None:
        """Prepare a scan thread. Call .start() to begin scanning."""
        super().__init__(parent)
        self._scanner = CleanupScanner()

    def run(self) -> None:
        """
        Perform the category scan. Called automatically by Qt when
        .start() is invoked — runs on the background thread.
        """
        logger.info("CleanupScanThread starting")

        try:
            categories = self._scanner.get_categories()
            self.scan_complete.emit(categories)

        except Exception as e:
            logger.error("Cleanup scan failed: %s", e)
            self.scan_error.emit(f"Scan failed: {e}")


class CleanupDeleteThread(QThread):
    """
    Runs Cleaner.clean_categories() on a background thread.

    DESTRUCTIVE — deletes files. This thread must only ever be started
    after the UI has shown the user exactly what will be deleted and
    received explicit confirmation. This class itself performs no
    confirmation logic; that responsibility belongs entirely to the
    UI layer that constructs it.

    Signals:
        delete_complete (CleanupResult): Emitted with the outcome once
            deletion finishes.
        delete_error (str): Emitted with a human-readable error message
            if deletion fails unexpectedly (rare — individual file
            failures are handled inside Cleaner and reported via the
            CleanupResult, not this signal).
    """

    delete_complete = pyqtSignal(CleanupResult)
    delete_error = pyqtSignal(str)

    def __init__(self, categories: List[CleanupCategory], parent=None) -> None:
        """
        Prepare a delete thread. Call .start() to begin deletion.

        Args:
            categories: The exact categories to delete. Should already
                be filtered down to only what the user selected and
                confirmed — this thread deletes whatever it's given,
                with no further filtering or confirmation of its own.
        """
        super().__init__(parent)
        self._categories = categories
        self._cleaner = Cleaner()

    def run(self) -> None:
        """
        Perform the deletion. Called automatically by Qt when .start()
        is invoked — runs on the background thread.
        """
        logger.info(
            "CleanupDeleteThread starting: %d categories",
            len(self._categories),
        )

        try:
            result = self._cleaner.clean_categories(self._categories)
            self.delete_complete.emit(result)

        except Exception as e:
            logger.error("Cleanup deletion failed: %s", e)
            self.delete_error.emit(f"Cleanup failed: {e}")