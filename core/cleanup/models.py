"""
core/cleanup/models.py
------------------------
Data structures for the Cleanup Advisor feature.

A cleanup category represents one type of safe-to-delete data (e.g.
"Temporary Files", "Recycle Bin"). Categories are defined once by the
scanner (core/cleanup/scanner.py) based on what actually exists on the
current OS, then displayed to the user for selection before any
deletion happens.
"""

from dataclasses import dataclass, field
from typing import List


@dataclass
class CleanupCategory:
    """
    Represents one safe-to-delete category of cache/temp data.

    Attributes:
        key (str): Stable internal identifier (e.g. "temp_files",
            "recycle_bin"). Used to reference this category without
            depending on its display name.
        display_name (str): Human-readable name shown in the UI
            (e.g. "Temporary Files").
        description (str): One-line explanation of what this category
            is and why it's safe to remove, shown to the user before
            they confirm deletion.
        paths (List[str]): Absolute filesystem path(s) this category
            covers. Some categories span multiple locations (e.g.
            several browsers' cache folders), so this is a list even
            though most categories have exactly one path.
        size_bytes (int): Total size found in this category's paths,
            as of the last scan. 0 until scanned, or if the category
            doesn't apply on this OS / is empty.
        file_count (int): Number of files found, as of the last scan.
        exists (bool): Whether at least one of this category's paths
            was found on this system. Categories that don't exist
            (e.g. a Windows-only path on macOS) are typically hidden
            from the UI entirely rather than shown as empty.
        selected (bool): Whether the user has checked this category
            for inclusion in the next cleanup run. Purely UI state,
            not touched by the scanner.
    """

    key: str
    display_name: str
    description: str
    paths: List[str] = field(default_factory=list)
    size_bytes: int = 0
    file_count: int = 0
    exists: bool = False
    selected: bool = False

    @property
    def size_mb(self) -> float:
        """Size in megabytes, for display convenience."""
        return self.size_bytes / (1024 * 1024)

    @property
    def size_gb(self) -> float:
        """Size in gigabytes, for display convenience."""
        return self.size_bytes / (1024 * 1024 * 1024)


@dataclass
class CleanupResult:
    """
    Outcome of actually performing a cleanup on one or more categories.

    Attributes:
        bytes_freed (int): Total bytes successfully deleted.
        files_deleted (int): Number of files successfully deleted.
        files_skipped (int): Number of files that could not be deleted
            (locked, permission denied, already gone, etc.) — these are
            NOT treated as fatal errors; deletion is best-effort per file.
        errors (List[str]): Human-readable messages for skipped files,
            capped at a reasonable count so the UI doesn't have to
            render thousands of lines after a large cleanup.
    """

    bytes_freed: int = 0
    files_deleted: int = 0
    files_skipped: int = 0
    errors: List[str] = field(default_factory=list)

    @property
    def freed_mb(self) -> float:
        """Bytes freed, in megabytes."""
        return self.bytes_freed / (1024 * 1024)

    @property
    def freed_gb(self) -> float:
        """Bytes freed, in gigabytes."""
        return self.bytes_freed / (1024 * 1024 * 1024)