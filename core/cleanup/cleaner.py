"""
core/cleanup/cleaner.py
-------------------------
Performs the actual deletion for confirmed cleanup categories.

Design notes:
    - This is the ONLY module in the project that deletes files. It
      is intentionally isolated here so the destructive code path is
      easy to find, read, and audit in one place.
    - Deletion is per-file and best-effort: one locked/in-use file
      does not abort the whole category. Each file gets its own
      try/except, and failures are collected (not raised) so the
      caller gets a complete picture of what succeeded and what didn't.
    - This module never decides WHAT to delete — it only deletes
      exactly the CleanupCategory objects it's given, which the UI
      builds from user-checked selections after a scan. No category
      discovery, no "smart" guessing happens here.
"""

import logging
import os
from typing import List

from core.cleanup.models import CleanupCategory, CleanupResult


logger = logging.getLogger(__name__)

# Cap how many individual error messages we keep, so a cleanup with
# thousands of locked files doesn't produce an unusably long error list
# for the UI to render.
MAX_TRACKED_ERRORS = 50


class Cleaner:
    """
    Deletes the contents of confirmed cleanup categories.
    """

    def clean_categories(
        self, categories: List[CleanupCategory]
    ) -> CleanupResult:
        """
        Delete the contents of each given category's path(s).

        Args:
            categories: Categories to clean. Typically the subset of
                a scan's results where the user checked "selected".
                Each category's own .paths are used as the deletion
                roots — nothing outside those paths is ever touched.

        Returns:
            CleanupResult: Aggregate outcome across all given categories.
        """
        result = CleanupResult()

        for category in categories:
            logger.info("Cleaning category: %s", category.key)

            for path in category.paths:
                if not os.path.isdir(path):
                    continue

                self._clean_directory_contents(path, result)

        logger.info(
            "Cleanup complete: %.1f MB freed, %d files deleted, %d skipped",
            result.freed_mb,
            result.files_deleted,
            result.files_skipped,
        )

        return result

    def _clean_directory_contents(
        self, directory: str, result: CleanupResult
    ) -> None:
        """
        Delete everything INSIDE a directory, but not the directory
        itself. This matters for categories like the OS temp folder or
        a browser's cache root — we want to empty it out, not remove
        the folder the OS/app expects to find there next time it runs.

        Args:
            directory: Directory whose contents should be deleted.
            result: CleanupResult to accumulate stats/errors into.
        """
        try:
            entries = list(os.scandir(directory))
        except (PermissionError, OSError) as e:
            self._record_error(result, f"Could not read {directory}: {e}")
            return

        for entry in entries:
            try:
                if entry.is_symlink():
                    # Never follow or delete through symlinks — the
                    # same policy as the Storage Analyzer's scanner,
                    # here for an even more important reason: we don't
                    # want a symlink to cause deletion of something
                    # outside the intended cleanup path.
                    continue

                if entry.is_file(follow_symlinks=False):
                    self._delete_file(entry.path, result)

                elif entry.is_dir(follow_symlinks=False):
                    self._delete_directory_tree(entry.path, result)

            except OSError as e:
                self._record_error(result, f"Could not process {entry.path}: {e}")
                continue

    def _delete_file(self, path: str, result: CleanupResult) -> None:
        """
        Delete a single file, tracking size before removal so it can
        be counted toward bytes freed even after the file is gone.

        Args:
            path: File to delete.
            result: CleanupResult to accumulate stats/errors into.
        """
        try:
            size = os.path.getsize(path)
            os.remove(path)
            result.bytes_freed += size
            result.files_deleted += 1

        except PermissionError:
            # Most common real-world case: file is open/locked by a
            # running process (e.g. active browser cache file).
            result.files_skipped += 1
            self._record_error(result, f"In use, skipped: {path}")

        except FileNotFoundError:
            # Already gone (another process cleaned it up, or it was
            # a very short-lived temp file) — not a real failure.
            pass

        except OSError as e:
            result.files_skipped += 1
            self._record_error(result, f"Could not delete {path}: {e}")

    def _delete_directory_tree(self, path: str, result: CleanupResult) -> None:
        """
        Recursively delete a subdirectory and its contents, file by
        file (not shutil.rmtree()) so individual failures within it
        are tracked the same way as top-level files, rather than
        aborting the whole subtree on the first locked file.

        After clearing its contents, attempts to remove the now-empty
        directory itself — subdirectories ARE removed (unlike the
        top-level category roots), since they were created by
        whatever app owns this cache and will be recreated if needed.

        Args:
            path: Subdirectory to delete.
            result: CleanupResult to accumulate stats/errors into.
        """
        try:
            entries = list(os.scandir(path))
        except (PermissionError, OSError) as e:
            self._record_error(result, f"Could not read {path}: {e}")
            return

        for entry in entries:
            try:
                if entry.is_symlink():
                    continue

                if entry.is_file(follow_symlinks=False):
                    self._delete_file(entry.path, result)

                elif entry.is_dir(follow_symlinks=False):
                    self._delete_directory_tree(entry.path, result)

            except OSError as e:
                self._record_error(result, f"Could not process {entry.path}: {e}")
                continue

        # Try to remove the now-emptied directory. Fails silently if
        # it's not actually empty (some files couldn't be deleted) —
        # that's expected and not worth surfacing as a separate error,
        # since the individual file failures were already recorded.
        try:
            os.rmdir(path)
        except OSError:
            pass

    def _record_error(self, result: CleanupResult, message: str) -> None:
        """
        Append an error message to the result, capped at
        MAX_TRACKED_ERRORS to keep the list a reasonable size for
        the UI to display.

        Args:
            result: CleanupResult to append to.
            message: Human-readable error description.
        """
        if len(result.errors) < MAX_TRACKED_ERRORS:
            result.errors.append(message)
        logger.debug(message)