"""
core/storage/models.py
-----------------------
Data structures for the Storage Analyzer feature.

A scan produces a tree of DirectoryNode objects — one per folder,
each holding its own size and a list of its immediate child folders.
Files are not tracked individually; only aggregated into the parent
folder's total size and file_count, since the UI only needs to show
folder-level breakdowns (matches the plan: "which subfolders are
eating up the most space").
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class DirectoryNode:
    """
    Represents one folder in a storage scan.

    Attributes:
        name (str): Folder name only (e.g., "Documents"), not full path.
        path (str): Full absolute path to this folder.
        size_bytes (int): Total size of this folder and everything inside
            it (files + subfolders), in bytes.
        file_count (int): Number of files directly and indirectly inside
            this folder (not counting the folders themselves).
        children (List[DirectoryNode]): Immediate subfolders, sorted by
            size_bytes descending once a scan completes (largest first).
        is_accessible (bool): False if this folder could not be fully
            read (permission denied) — size_bytes may be a partial/
            undercount in that case, and the UI should indicate this.
        parent (Optional[DirectoryNode]): Reference to the parent node,
            used for "Back" navigation and computing % of parent size.
            None for the root node of a scan.
    """

    name: str
    path: str
    size_bytes: int = 0
    file_count: int = 0
    children: List["DirectoryNode"] = field(default_factory=list)
    is_accessible: bool = True
    parent: Optional["DirectoryNode"] = None

    @property
    def size_mb(self) -> float:
        """Size in megabytes, for display convenience."""
        return self.size_bytes / (1024 * 1024)

    @property
    def size_gb(self) -> float:
        """Size in gigabytes, for display convenience."""
        return self.size_bytes / (1024 * 1024 * 1024)

    def percent_of_parent(self) -> float:
        """
        Calculate what percentage of the parent folder's total size
        this folder represents.

        Used to drive both the progress bar display and the hover
        animation tier (sleeping/peek/shiver/jump-out).

        Returns:
            float: Percentage (0-100). Returns 0.0 if there's no parent
                or the parent has zero size (avoids division by zero).
        """
        if self.parent is None or self.parent.size_bytes == 0:
            return 0.0
        return (self.size_bytes / self.parent.size_bytes) * 100.0

    def sort_children_by_size(self) -> None:
        """
        Sort this folder's children largest-first, in place.

        Called once after a scan completes, so the UI can simply
        iterate self.children in display order without re-sorting.
        """
        self.children.sort(key=lambda child: child.size_bytes, reverse=True)