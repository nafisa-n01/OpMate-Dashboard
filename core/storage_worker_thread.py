"""
core/storage_worker_thread.py
-------------------------------
Background thread for running a single Storage Analyzer scan.

Unlike WorkerThread (core/worker_thread.py), which loops forever
polling live system metrics, this thread runs ONE scan and then stops.
A fresh StorageScanThread is created each time the user clicks "Scan"
or drills into a folder that needs deeper scanning — there's no
persistent background polling here, matching the on-demand design
from the project's original requirements.
"""

import logging

from PyQt6.QtCore import QThread, pyqtSignal

from core.storage.analyzer import StorageAnalyzer
from core.storage.models import DirectoryNode
from core.exceptions import FileSystemError


logger = logging.getLogger(__name__)


class StorageScanThread(QThread):
    """
    Runs a single StorageAnalyzer.scan() call on a background thread.

    Signals:
        scan_complete (DirectoryNode): Emitted with the resulting tree
            once the scan finishes successfully.
        scan_error (str): Emitted with a human-readable error message
            if the scan fails (e.g., invalid path).
    """

    scan_complete = pyqtSignal(DirectoryNode)
    scan_error = pyqtSignal(str)

    def __init__(self, root_path: str, max_depth: int, parent=None) -> None:
        """
        Prepare a scan thread. Call .start() to actually begin scanning.

        Args:
            root_path: Absolute path to the folder to scan.
            max_depth: How many folder levels deep to recurse (passed
                straight through to StorageAnalyzer.scan()).
            parent: Optional Qt parent object.
        """
        super().__init__(parent)
        self._root_path = root_path
        self._max_depth = max_depth
        self._analyzer = StorageAnalyzer()

    def run(self) -> None:
        """
        Perform the scan. Called automatically by Qt when .start() is
        invoked — runs on the background thread, not the UI thread.
        """
        logger.info(
            "StorageScanThread starting: %s (depth=%d)",
            self._root_path,
            self._max_depth,
        )

        try:
            result = self._analyzer.scan(self._root_path, self._max_depth)
            self.scan_complete.emit(result)

        except FileSystemError as e:
            logger.error("Storage scan failed: %s", e)
            self.scan_error.emit(str(e))

        except Exception as e:
            # Catch-all so an unexpected error surfaces in the UI
            # instead of silently killing the thread.
            logger.error("Unexpected error during storage scan: %s", e)
            self.scan_error.emit(f"Unexpected error: {e}")