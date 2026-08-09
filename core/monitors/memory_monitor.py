"""
core/monitors/memory_monitor.py
-------------------------------
RAM and Swap memory monitoring using psutil.

What we measure:
    1. Physical RAM: used, available, total, and percentage
    2. Swap space: used, total, and percentage
    3. Available memory: memory that can be allocated without swapping to disk

Key concepts:
    - RAM (physical memory): Actual installed RAM chips
    - Swap (virtual memory): Disk space used as overflow when RAM is full
    - Available: RAM that the system can give to new processes (includes cached memory)
    
When to worry:
    - RAM 80-90%: Getting full, consider closing apps
    - Swap 50%+: System is using disk as memory (slow, consider adding RAM)
"""

import logging
from datetime import datetime

import psutil

from core.monitors.base_monitor import BaseMonitor
from core.data_models import MemoryMetrics
from core.exceptions import MonitorException


logger = logging.getLogger(__name__)


class MemoryMonitor(BaseMonitor):
    """
    Monitors RAM and Swap memory usage.

    Attributes:
        None (all data fetched fresh each poll)
    """

    def __init__(self) -> None:
        """Initialize memory monitor."""
        super().__init__()
        logger.debug("MemoryMonitor initialized")

    def get_data(self) -> MemoryMetrics:
        """
        Fetch current memory usage metrics.

        Process:
            1. Call psutil.virtual_memory() to get physical RAM stats
            2. Call psutil.swap_memory() to get swap stats
            3. Convert bytes to megabytes (MB) for readability
            4. Package into MemoryMetrics dataclass
            5. Return the snapshot

        Returns:
            MemoryMetrics: Snapshot of RAM and Swap usage at this moment.

        Raises:
            MonitorException: If memory data cannot be retrieved (extremely rare).
        """
        try:
            # Get physical RAM statistics
            # Returns: virtual_memory(total, available, percent, used, free, active, inactive, buffers, cached)
            ram_info = psutil.virtual_memory()

            # Get Swap statistics
            # Returns: swap_memory(total, used, free, percent, sin, sout)
            swap_info = psutil.swap_memory()

            # Convert bytes to megabytes (1 MB = 1,048,576 bytes)
            # psutil returns everything in bytes; we convert to MB for human readability
            ram_total_mb = ram_info.total / (1024 * 1024)
            ram_used_mb = ram_info.used / (1024 * 1024)
            ram_available_mb = ram_info.available / (1024 * 1024)
            ram_percent = ram_info.percent

            swap_total_mb = swap_info.total / (1024 * 1024)
            swap_used_mb = swap_info.used / (1024 * 1024)
            swap_percent = swap_info.percent

            # Create and return the metric snapshot
            metrics = MemoryMetrics(
                ram_used_mb=ram_used_mb,
                ram_total_mb=ram_total_mb,
                ram_available_mb=ram_available_mb,
                ram_percent=ram_percent,
                swap_used_mb=swap_used_mb,
                swap_total_mb=swap_total_mb,
                swap_percent=swap_percent,
                timestamp=datetime.now(),
            )

            logger.debug(
                "Memory metrics: RAM=%.1f%%/%.0fGB, Swap=%.1f%%/%.0fGB",
                ram_percent,
                ram_total_mb / 1024,
                swap_percent,
                swap_total_mb / 1024,
            )

            return metrics

        except Exception as e:
            logger.error("Failed to get memory metrics: %s", e)
            raise MonitorException(f"Memory monitoring failed: {e}") from e