"""
ui/widgets/base_widget.py
------------------------
Base class for all metric widgets.

Provides:
    - Standard slot signatures for receiving metric updates
    - Error handling (shows error message to user)
    - Common styling

Note on design:
    We do NOT inherit from Python's ABC (Abstract Base Class) here.
    QWidget uses its own metaclass internally (from PyQt6's sip bindings),
    and Python's ABCMeta conflicts with it, causing:
        TypeError: metaclass conflict
    Instead, update_data() raises NotImplementedError by default —
    same safety net, without the metaclass collision.
"""

from PyQt6.QtWidgets import QWidget


class BaseWidget(QWidget):
    """
    Base class for all monitoring widgets.

    Subclasses must override update_data() to handle incoming metrics.
    Error handling is standardized across all widgets.
    """

    def __init__(self, title: str) -> None:
        """
        Initialize base widget.

        Args:
            title: Display name of this widget (e.g., "CPU Monitor").
        """
        super().__init__()
        self.title = title
        self.setStyleSheet("background-color: #2a2a3e; color: #c0c0d0;")

    def update_data(self, data) -> None:
        """
        Update widget with new metric data.

        Called whenever new metrics arrive from worker thread via signal.
        Subclasses MUST override this method.

        Args:
            data: Metric object (CPUMetrics, MemoryMetrics, etc.)

        Raises:
            NotImplementedError: If a subclass forgets to override this.
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement update_data()"
        )

    def show_error(self, error_message: str) -> None:
        """
        Display an error message to the user.

        Called when monitoring fails. Subclasses can override for custom
        error display (e.g., red text, warning icon).

        Args:
            error_message: Human-readable error description.
        """
        print(f"[{self.title}] Error: {error_message}")