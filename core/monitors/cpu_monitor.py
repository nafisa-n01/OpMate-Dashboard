"""
core/monitors/cpu_monitor.py
----------------------------
CPU usage monitoring using psutil.

What we measure:
    1. Overall CPU percentage (0-100) across all cores
    2. Per-core breakdown (separate % for each logical core)
    3. CPU frequency (current speed in GHz)
    4. Core count (for reference)

How it works:
    - psutil.cpu_percent(interval=1) blocks for 1 second, measuring CPU usage
    - This gives accurate readings; instant reads (interval=None) are less reliable
    - psutil handles cross-platform differences (Windows vs. Linux vs. macOS)
"""

import logging
from datetime import datetime
from typing import List

import psutil

from core.monitors.base_monitor import BaseMonitor
from core.data_models import CPUMetrics
from core.exceptions import MonitorException


logger = logging.getLogger(__name__)


class CPUMonitor(BaseMonitor):
    """
    Monitors CPU usage across all cores.

    Attributes:
        _core_count (int): Number of logical CPU cores (cached at init).
    """

    def __init__(self) -> None:
        """Initialize CPU monitor."""
        super().__init__()
        self._core_count = psutil.cpu_count(logical=True)
        logger.debug("CPUMonitor initialized with %d logical cores", self._core_count)

    def get_data(self) -> CPUMetrics:
        """
        Fetch current CPU usage metrics.

        Process:
            1. Call psutil.cpu_percent(interval=1) to get overall CPU %
               (This blocks for ~1 second while measuring)
            2. Call psutil.cpu_percent(percpu=True) to get per-core %
               (Also ~1 second, but since we already measured, it returns cached)
            3. Call psutil.cpu_freq() to get current frequency
            4. Package everything into a CPUMetrics dataclass
            5. Return the snapshot

        Returns:
            CPUMetrics: Snapshot of CPU usage at this moment.

        Raises:
            MonitorException: If CPU data cannot be retrieved (rare on modern systems).
        """
        try:
            # Get overall CPU percentage (0-100)
            # interval=1 means: measure CPU usage over the next 1 second
            # (This is why the refresh interval in WorkerThread is 1 second)
            overall_cpu = psutil.cpu_percent(interval=1)

            # Get per-core percentages
            # Returns a list like [34.5, 45.2, 12.1, 89.3] for a 4-core system
            per_core_cpus = psutil.cpu_percent(percpu=True, interval=0)

            # Get CPU frequency in MHz, convert to GHz
            freq = psutil.cpu_freq()
            frequency_ghz = freq.current / 1000.0 if freq else 0.0

            # Create and return the metric snapshot
            metrics = CPUMetrics(
                overall_percent=overall_cpu,
                per_core_percents=per_core_cpus,
                frequency_ghz=frequency_ghz,
                core_count=self._core_count,
                timestamp=datetime.now(),
            )

            logger.debug(
                "CPU metrics: overall=%.1f%%, freq=%.2f GHz, cores=%d",
                overall_cpu,
                frequency_ghz,
                self._core_count,
            )

            return metrics

        except Exception as e:
            logger.error("Failed to get CPU metrics: %s", e)
            raise MonitorException(f"CPU monitoring failed: {e}") from e