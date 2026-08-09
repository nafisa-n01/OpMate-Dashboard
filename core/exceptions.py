"""
core/exceptions.py
------------------
Custom exception classes for the core monitoring system.

By defining our own exceptions, we can:
    1. Catch specific errors (e.g., "process no longer exists")
    2. Provide meaningful error messages
    3. Debug faster (know exactly what went wrong)
"""


class MonitorException(Exception):
    """Base exception for all monitoring errors."""

    pass


class PermissionDeniedError(MonitorException):
    """
    Raised when access to a process or file is denied.

    Example: Trying to read memory info of a privileged system process
    without admin/root privileges.
    """

    pass


class ProcessNotFoundError(MonitorException):
    """
    Raised when a process ID no longer exists.

    Common during iteration — a process may exit between the time we
    start iterating and the time we try to read its data.
    """

    pass


class FileSystemError(MonitorException):
    """Raised when accessing the filesystem fails."""

    pass