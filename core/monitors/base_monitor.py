"""
core/monitors/base_monitor.py
------------------------------
Abstract base class for all system monitors.

This enforces a contract: every monitor must implement get_data(),
which returns a metric snapshot. By using inheritance, we ensure
consistency across all monitors.
"""

from abc import ABC, abstractmethod
from typing import Any


class BaseMonitor(ABC):
    """
    Abstract base class for system monitors.

    Subclasses must implement get_data() to return their specific
    metric snapshot (CPUMetrics, MemoryMetrics, etc.).
    """

    @abstractmethod
    def get_data(self) -> Any:
        """
        Fetch system metrics.

        Returns:
            A metric snapshot (CPUMetrics, MemoryMetrics, etc.)

        Raises:
            MonitorException: If metrics cannot be retrieved.
        """
        pass