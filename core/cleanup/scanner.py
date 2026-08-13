"""
core/cleanup/scanner.py
-------------------------
Detects safe-to-delete cleanup categories on the current OS and
computes their sizes.

Design notes:
    - Read-only. This module never deletes anything — see
      core/cleanup/cleaner.py for the deletion logic, which only runs
      after explicit user confirmation.
    - Cross-platform by construction: each category's candidate paths
      are built based on platform.system(), and a category is only
      reported as existing if at least one of its paths is actually
      present on disk. A Windows-only category simply won't appear
      at all on macOS/Linux, rather than showing as "0 bytes."
    - Categories intentionally target CACHE/TEMP data only — data the
      OS or an application is expected to regenerate on its own. This
      is the entire safety argument for the feature; no category here
      should ever touch user documents, downloads, or anything with
      no automatic regeneration path.
"""

import logging
import os
import platform
import tempfile
from typing import List

from core.cleanup.models import CleanupCategory


logger = logging.getLogger(__name__)

# Skip symlinks during size calculation, same policy as the Storage
# Analyzer's directory scanner — avoids double-counting space that
# lives elsewhere, and avoids potential symlink loops.


class CleanupScanner:
    """
    Detects available cleanup categories and measures their sizes.
    """

    def get_categories(self) -> List[CleanupCategory]:
        """
        Build the full list of cleanup categories for the current OS,
        with sizes populated.

        Returns:
            List[CleanupCategory]: Only categories where exists=True
                are typically shown by the UI, but this returns the
                full evaluated list (including non-existent ones) so
                callers can decide how to handle that themselves.
        """
        categories = self._build_category_definitions()

        for category in categories:
            self._scan_category(category)

        logger.info(
            "Cleanup scan complete: %d categories found (%d applicable)",
            len(categories),
            sum(1 for c in categories if c.exists),
        )

        return categories

    def _build_category_definitions(self) -> List[CleanupCategory]:
        """
        Define the candidate categories and their platform-specific
        paths. Paths are only checked for existence later, in
        _scan_category() — this method just builds the candidate list.

        Returns:
            List[CleanupCategory]: Categories with paths populated but
                size_bytes/exists not yet evaluated.
        """
        system = platform.system()  # "Windows", "Linux", "Darwin"
        categories: List[CleanupCategory] = []

        # --- Temporary Files (cross-platform) ---
        # tempfile.gettempdir() asks the OS for its designated scratch
        # space rather than hardcoding a path — this is the same
        # "ask, don't assume" principle used elsewhere in the project
        # (e.g. system_monitor.py's hostname/OS detection).
        categories.append(
            CleanupCategory(
                key="temp_files",
                display_name="Temporary Files",
                description=(
                    "Scratch space used by apps and the OS. Safe to "
                    "clear — regenerated automatically as needed."
                ),
                paths=[tempfile.gettempdir()],
            )
        )

        # --- Recycle Bin / Trash (platform-specific) ---
        if system == "Windows":
            recycle_paths = self._find_windows_recycle_bins()
        elif system == "Darwin":
            recycle_paths = [os.path.expanduser("~/.Trash")]
        else:  # Linux and others: XDG trash spec
            recycle_paths = [
                os.path.expanduser("~/.local/share/Trash/files")
            ]

        categories.append(
            CleanupCategory(
                key="recycle_bin",
                display_name="Recycle Bin",
                description=(
                    "Files already marked for deletion. Removing them "
                    "here just finishes what you already started."
                ),
                paths=recycle_paths,
            )
        )

        # --- Browser Caches (cross-platform, checks common browsers) ---
        browser_cache_paths = self._find_browser_cache_paths(system)
        categories.append(
            CleanupCategory(
                key="browser_cache",
                display_name="Browser Cache",
                description=(
                    "Cached web page data from Chrome/Firefox/Edge. "
                    "Rebuilds automatically the next time you browse."
                ),
                paths=browser_cache_paths,
            )
        )

        # --- Windows-only categories ---
        if system == "Windows":
            categories.append(
                CleanupCategory(
                    key="thumbnail_cache",
                    display_name="Thumbnail Cache",
                    description=(
                        "Cached preview images for files and folders. "
                        "Regenerates automatically when folders are "
                        "reopened."
                    ),
                    paths=[
                        os.path.expanduser(
                            r"~\AppData\Local\Microsoft\Windows\Explorer"
                        )
                    ],
                )
            )

            categories.append(
                CleanupCategory(
                    key="directx_shader_cache",
                    display_name="DirectX Shader Cache",
                    description=(
                        "Compiled graphics shaders cached by games/apps. "
                        "Recompiled automatically the next time they run."
                    ),
                    paths=[
                        os.path.expanduser(
                            r"~\AppData\Local\D3DSCache"
                        )
                    ],
                )
            )

        return categories

    def _find_windows_recycle_bins(self) -> List[str]:
        """
        Windows' Recycle Bin has a hidden $Recycle.Bin folder at the
        root of EVERY drive, not just C:. Scan drive letters A-Z and
        collect any that have one.

        Returns:
            List[str]: Paths to $Recycle.Bin on each drive that has one.
        """
        paths = []
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            candidate = f"{letter}:\\$Recycle.Bin"
            if os.path.isdir(candidate):
                paths.append(candidate)
        return paths

    def _find_browser_cache_paths(self, system: str) -> List[str]:
        """
        Build candidate cache paths for common browsers. Non-existent
        ones are simply filtered out later in _scan_category() — a
        user without Firefox installed just won't have that path
        contribute anything.

        Args:
            system: Result of platform.system().

        Returns:
            List[str]: Candidate browser cache directories for this OS.
        """
        home = os.path.expanduser("~")

        if system == "Windows":
            return [
                os.path.join(
                    home,
                    r"AppData\Local\Google\Chrome\User Data\Default\Cache",
                ),
                os.path.join(
                    home,
                    r"AppData\Local\Microsoft\Edge\User Data\Default\Cache",
                ),
                os.path.join(
                    home,
                    r"AppData\Local\Mozilla\Firefox\Profiles",
                ),
            ]
        elif system == "Darwin":
            return [
                os.path.join(
                    home,
                    "Library/Caches/Google/Chrome",
                ),
                os.path.join(
                    home,
                    "Library/Caches/Firefox",
                ),
            ]
        else:  # Linux
            return [
                os.path.join(home, ".cache/google-chrome"),
                os.path.join(home, ".cache/mozilla/firefox"),
            ]

    def _scan_category(self, category: CleanupCategory) -> None:
        """
        Populate size_bytes, file_count, and exists for one category
        by walking its path(s). Mutates the category in place.

        A category is marked exists=True if at least one of its paths
        is a real, readable directory — even if that directory happens
        to be empty (size_bytes stays 0, but it's still "applicable"
        to this system, just currently clean).

        Args:
            category: The CleanupCategory to scan (mutated in place).
        """
        total_size = 0
        total_files = 0
        found_any_path = False

        for path in category.paths:
            if not os.path.isdir(path):
                continue

            found_any_path = True

            try:
                size, count = self._measure_directory(path)
                total_size += size
                total_files += count
            except OSError as e:
                logger.warning("Could not fully scan %s: %s", path, e)
                continue

        category.exists = found_any_path
        category.size_bytes = total_size
        category.file_count = total_files

        if found_any_path:
            logger.debug(
                "Category '%s': %.1f MB across %d files",
                category.key,
                category.size_mb,
                category.file_count,
            )

    def _measure_directory(self, path: str) -> tuple[int, int]:
        """
        Recursively sum file sizes and count under a directory.

        Uses os.scandir() for the same efficiency reasons as
        StorageAnalyzer (cached file-type info avoids extra syscalls
        per entry). Unlike the Storage Analyzer, this has no depth
        limit — cleanup categories are expected to be flat-ish cache
        folders, not deep user directory trees, so a full walk is
        cheap and gives an accurate total.

        Args:
            path: Directory to measure.

        Returns:
            tuple[int, int]: (total_size_bytes, total_file_count)
        """
        total_size = 0
        total_files = 0

        try:
            entries = list(os.scandir(path))
        except (PermissionError, OSError):
            return total_size, total_files

        for entry in entries:
            try:
                if entry.is_symlink():
                    continue

                if entry.is_file(follow_symlinks=False):
                    total_size += entry.stat(follow_symlinks=False).st_size
                    total_files += 1

                elif entry.is_dir(follow_symlinks=False):
                    sub_size, sub_files = self._measure_directory(entry.path)
                    total_size += sub_size
                    total_files += sub_files

            except OSError:
                # File vanished or became unreadable mid-scan; skip it.
                continue

        return total_size, total_files