"""
core/monitors/system_monitor.py
-------------------------------
Static system information monitoring.

What we measure:
    1. Hostname (computer name)
    2. Operating system (Windows, Linux, Darwin/macOS)
    3. OS version (11, 22.04, 12.6, etc.)
    4. Architecture (x86-64, arm64, i686, etc.)
    5. Uptime (time since last boot)
    6. Boot time (when system last started)
    7. CPU model name
    8. CPU core count
    9. Total RAM in GB
    10. Total processes and threads

Why separate from other monitors?
    - Most data is STATIC (doesn't change after boot)
    - Uptime is SEMI-STATIC (updates every second but predictable)
    - Computing thread count is EXPENSIVE (iterates all processes)
    - Polled less frequently (every 10 seconds instead of every 1-2 seconds)

Data sources:
    - socket.gethostname() → hostname
    - platform.system(), platform.release() → OS info
    - psutil.boot_time() → boot timestamp
    - platform.processor(), psutil.cpu_count() → CPU info
    - psutil.virtual_memory().total → RAM size
    - psutil.process_iter() + counting → process/thread count (slow!)
"""

import logging
import socket
import platform
from datetime import datetime, timedelta
from typing import Optional

import psutil

from core.monitors.base_monitor import BaseMonitor
from core.data_models import SystemMetrics
from core.exceptions import MonitorException


logger = logging.getLogger(__name__)


class SystemMonitor(BaseMonitor):
    """
    Monitors static system information.

    This monitor is special:
    - Most data is fetched ONCE at initialization
    - Only uptime/thread count update on each poll
    - Designed for low-frequency polling (every 10 seconds)

    Attributes:
        _hostname (str): Computer name (cached, never changes).
        _os_name (str): OS name like "Windows", "Linux", "Darwin" (cached).
        _os_version (str): OS version like "11", "22.04", "12.6" (cached).
        _os_architecture (str): "x86-64", "arm64", etc. (cached).
        _boot_time (datetime): When system last started (cached).
        _cpu_model (str): CPU model name (cached).
        _cpu_core_count (int): Number of cores (cached).
        _ram_total_gb (float): Total RAM in GB (cached).
    """

    def __init__(self) -> None:
        """
        Initialize system monitor.

        Fetches all static data once at startup (efficient).
        Dynamic data (uptime, threads) will be computed on each poll.
        """
        super().__init__()

        try:
            # Fetch static data (never changes until reboot)
            self._hostname = socket.gethostname()
            self._os_name = platform.system()  # "Windows", "Linux", "Darwin"
            self._os_version = platform.release()  # "11", "22.04", "12.6"
            self._os_architecture = platform.machine()  # "x86_64", "arm64"
            self._boot_time = datetime.fromtimestamp(psutil.boot_time())
            self._cpu_model = platform.processor()  # CPU model name
            self._cpu_core_count = psutil.cpu_count(logical=True)
            self._ram_total_gb = psutil.virtual_memory().total / (1024**3)

            logger.info(
                "SystemMonitor initialized: %s (%s %s) - %d cores, %.1f GB RAM",
                self._hostname,
                self._os_name,
                self._os_version,
                self._cpu_core_count,
                self._ram_total_gb,
            )

        except Exception as e:
            logger.error("Failed to initialize SystemMonitor: %s", e)
            raise MonitorException(f"System monitoring initialization failed: {e}") from e

    def get_data(self) -> SystemMetrics:
        """
        Fetch current system metrics.

        Process:
            1. Calculate uptime from boot time
            2. Count total processes and threads (expensive!)
            3. Create SystemMetrics dataclass with all info
            4. Return the snapshot

        Most data is cached from __init__; only uptime/threads are recalculated.

        Returns:
            SystemMetrics: Complete system information snapshot.

        Raises:
            MonitorException: If system data cannot be retrieved (rare).
        """
        try:
            # Calculate uptime (current time - boot time)
            now = datetime.now()
            uptime_delta = now - self._boot_time
            uptime_seconds = int(uptime_delta.total_seconds())

            # Count processes and threads
            # This is EXPENSIVE — iterates all processes
            # Only do this every 10 seconds (not every 1-2 seconds)
            total_processes = 0
            total_threads = 0

            try:
                for proc in psutil.process_iter():
                    try:
                        total_processes += 1
                        total_threads += proc.num_threads()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        # Process died or can't read threads (permission)
                        continue
            except Exception as e:
                logger.warning("Error counting processes/threads: %s", e)
                # Continue with partial data rather than failing completely

            # Create and return the metric snapshot
            metrics = SystemMetrics(
                hostname=self._hostname,
                os_name=self._os_name,
                os_version=self._os_version,
                os_architecture=self._os_architecture,
                uptime_seconds=uptime_seconds,
                boot_time=self._boot_time,
                total_processes=total_processes,
                total_threads=total_threads,
                cpu_model=self._cpu_model,
                cpu_core_count=self._cpu_core_count,
                ram_total_gb=self._ram_total_gb,
            )

            logger.debug(
                "System metrics: uptime=%d days %d hours, "
                "%d processes, %d threads",
                uptime_seconds // 86400,
                (uptime_seconds % 86400) // 3600,
                total_processes,
                total_threads,
            )

            return metrics

        except Exception as e:
            logger.error("Failed to get system metrics: %s", e)
            raise MonitorException(f"System monitoring failed: {e}") from e

    @staticmethod
    def format_uptime(uptime_seconds: int) -> str:
        """
        Format uptime seconds into human-readable string.

        Args:
            uptime_seconds: Seconds since boot.

        Returns:
            Formatted string like "45 days 12h 34m 12s".

        Example:
            >>> SystemMonitor.format_uptime(3932652)
            '45 days 12h 34m 12s'
        """
        days = uptime_seconds // 86400
        hours = (uptime_seconds % 86400) // 3600
        minutes = (uptime_seconds % 3600) // 60
        seconds = uptime_seconds % 60

        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")
        if seconds > 0 or not parts:
            parts.append(f"{seconds}s")

        return " ".join(parts)