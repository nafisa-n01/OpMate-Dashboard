"""
core/storage/analyzer.py
--------------------------
Recursive directory scanner for the Storage Analyzer feature.

Design notes:
    - Scans are shallow by default (see MAX_SCAN_DEPTH) — we scan a
      couple of levels deep immediately, and the UI triggers deeper
      scans lazily as the user drills into a folder. This keeps the
      initial "Scan" click fast even on large drives, matching the
      on-demand, lightweight philosophy from the project's original
      requirements.
    - Symlinks/junctions are never followed, to avoid infinite loops
      (a symlink pointing back to an ancestor folder would otherwise
      cause unbounded recursion).
    - Permission errors on individual folders are caught and marked
      via is_accessible=False rather than aborting the whole scan —
      one locked folder shouldn't prevent seeing the rest of the tree.
"""

import logging
import os
from typing import Optional

from core.storage.models import DirectoryNode
from core.exceptions import FileSystemError


logger = logging.getLogger(__name__)

# How many folder levels deep a single scan() call will recurse before
# stopping. Deeper folders still appear as childless DirectoryNode
# entries with size_bytes=0 — the UI can trigger a fresh, deeper scan
# rooted at that folder when the user drills into it.
MAX_SCAN_DEPTH = 2

# Folder names to skip entirely (system/junk folders that are slow to
# scan and rarely what the user is looking for).
SKIPPED_FOLDER_NAMES = {
    "$RECYCLE.BIN",
    "System Volume Information",
    "node_modules",
    ".git",
}


class StorageAnalyzer:
    """
    Scans a directory tree and builds a DirectoryNode hierarchy showing
    folder sizes, for the Storage Analyzer feature.

    This class holds no state between scans — each call to scan()
    produces a fresh, independent DirectoryNode tree.
    """

    def scan(self, root_path: str, max_depth: int = MAX_SCAN_DEPTH) -> DirectoryNode:
        """
        Scan a directory and build a DirectoryNode tree describing it.

        Args:
            root_path: Absolute path to the folder to scan.
            max_depth: How many levels of subfolders to recurse into.
                A value of 0 scans only root_path's direct files (no
                subfolder recursion); each increment goes one level
                deeper.

        Returns:
            DirectoryNode: Root of the resulting tree. Its size_bytes
                reflects everything actually scanned; folders beyond
                max_depth appear as childless nodes with size_bytes=0
                (the UI treats these as "not yet scanned").

        Raises:
            FileSystemError: If root_path itself doesn't exist or isn't
                a directory — this is a genuine usage error, not just
                an inaccessible subfolder, so it's raised rather than
                silently marked inaccessible.
        """
        if not os.path.isdir(root_path):
            raise FileSystemError(f"Not a valid directory: {root_path}")

        root_node = DirectoryNode(
            name=os.path.basename(root_path.rstrip(os.sep)) or root_path,
            path=root_path,
            parent=None,
        )

        self._scan_recursive(root_node, current_depth=0, max_depth=max_depth)
        root_node.sort_children_by_size()

        logger.info(
            "Scan complete: %s (%.1f MB, %d files)",
            root_path,
            root_node.size_mb,
            root_node.file_count,
        )

        return root_node

    def _scan_recursive(
        self, node: DirectoryNode, current_depth: int, max_depth: int
    ) -> None:
        """
        Populate a DirectoryNode's size, file_count, and children by
        walking its contents on disk. Recurses into subfolders up to
        max_depth.

        Args:
            node: The DirectoryNode to populate (its .path is used as
                the folder to scan).
            current_depth: How many levels deep we already are (0 = the
                scan's root folder).
            max_depth: The recursion ceiling passed in from scan().
        """
        try:
            entries = list(os.scandir(node.path))
        except PermissionError:
            logger.warning("Permission denied: %s", node.path)
            node.is_accessible = False
            return
        except OSError as e:
            logger.warning("Cannot read %s: %s", node.path, e)
            node.is_accessible = False
            return

        for entry in entries:
            try:
                # Never follow symlinks/junctions — prevents infinite
                # loops from links that point back up the tree, and
                # avoids double-counting space that's really elsewhere.
                if entry.is_symlink():
                    continue

                if entry.is_file(follow_symlinks=False):
                    try:
                        file_size = entry.stat(follow_symlinks=False).st_size
                        node.size_bytes += file_size
                        node.file_count += 1
                    except OSError:
                        # File vanished or became unreadable mid-scan;
                        # skip it rather than aborting the whole folder.
                        continue

                elif entry.is_dir(follow_symlinks=False):
                    if entry.name in SKIPPED_FOLDER_NAMES:
                        continue

                    child_node = DirectoryNode(
                        name=entry.name,
                        path=entry.path,
                        parent=node,
                    )

                    if current_depth < max_depth:
                        self._scan_recursive(
                            child_node, current_depth + 1, max_depth
                        )
                    # else: leave child_node with size_bytes=0 — it's
                    # a placeholder the UI can scan deeper on demand.

                    node.children.append(child_node)
                    node.size_bytes += child_node.size_bytes
                    node.file_count += child_node.file_count

            except OSError as e:
                # Covers rare races (entry deleted mid-iteration, etc.)
                logger.debug("Skipping entry %s: %s", entry.path, e)
                continue

        node.sort_children_by_size()