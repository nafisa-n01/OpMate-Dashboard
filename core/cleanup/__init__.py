"""
core.cleanup package
----------------------
Cleanup Advisor feature: detects safe-to-delete cache/temp categories
(temp files, recycle bin, browser cache, thumbnail cache, etc.), reports
their sizes, and performs user-confirmed deletion.

Kept separate from core.storage (the folder browser) since this
feature targets a small, fixed set of KNOWN-safe categories rather
than arbitrary user folders — a deliberately narrower, safer scope.
"""