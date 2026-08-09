"""
core/monitors/process_monitor.py
--------------------------------
Running processes monitoring using psutil.

What we measure:
    1. All running processes on the system
    2. For each: PID, name, memory (MB and %), status, owner
    3. Top 10 processes sorted by memory usage (highest first)
    4. Total process count (for system overview)

Why top 10?
    - Full process list is huge (100+ processes on typical systems)
    - Top 10 by memory shows where resources are actually going
    - User can see memory hogs at a glance

Challenges:
    - Processes die mid-iteration (handle gracefully)
    - Permission errors (can't read other users' processes without root)
    - Process status varies (running, sleeping, zombie, etc.)
"""

import logging
from datetime import datetime
from typing import List

import psutil

from core.monitors.base_monitor import BaseMonitor
from core.data_models import ProcessMetrics, ProcessInfo
from core.exceptions import MonitorException, ProcessNotFoundError, PermissionDeniedError


logger = logging.getLogger(__name__)

# Limit for top processes to display
TOP_PROCESSES_LIMIT = 10


class ProcessMonitor(BaseMonitor):
    """
    Monitors running processes.

    Attributes:
        None (all data fetched fresh each poll)
    """

    def __init__(self) -> None:
        """Initialize process monitor."""
        super().__init__()
        logger.debug("ProcessMonitor initialized")

    def get_data(self) -> ProcessMetrics:
        """
        Fetch current running processes metrics.

        Process:
            1. Iterate through all running processes via psutil.process_iter()
            2. For each process, safely extract: PID, name, memory, status, username
            3. Handle errors (process dies, permission denied) gracefully
            4. Collect into ProcessInfo list
            5. Sort by memory usage (highest first)
            6. Take top 10
            7. Count total processes
            8. Return ProcessMetrics with timestamp

        Returns:
            ProcessMetrics: Top 10 processes by memory + total process count.

        Raises:
            MonitorException: If process monitoring fails completely.
        """
        try:
            processes: List[ProcessInfo] = []
            total_processes = 0

            # Iterate all running processes
            # attrs parameter makes psutil fetch these attributes efficiently
            # (more efficient than calling process.name(), process.memory_info(), etc. separately)
            for proc in psutil.process_iter(
                attrs=["pid", "name", "memory_percent", "status", "username"]
            ):
                total_processes += 1

                try:
                    # Get the process info dict
                    # This is safe to access (already fetched via attrs parameter)
                    info = proc.info

                    # Extract fields, defending against None values
                    # (some Windows system processes like "Memory Compression"
                    # or "Registry" return incomplete data even when access succeeds)
                    pid = info.get("pid")
                    name = info.get("name") or "Unknown"
                    memory_percent = info.get("memory_percent") or 0.0
                    status = info.get("status") or "unknown"
                    username = info.get("username") or "N/A"

                    # Skip this process entirely if we don't even have a valid PID
                    # (this should be rare, but protects against malformed data)
                    if pid is None:
                        logger.debug("Skipping process with missing PID: %s", name)
                        total_processes -= 1
                        continue

                    # Convert memory percent to MB
                    # We need to get absolute memory usage
                    try:
                        memory_mb = proc.memory_info().rss / (1024 * 1024)
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        memory_mb = 0.0

                    # Create ProcessInfo for this process
                    process_info = ProcessInfo(
                        pid=pid,
                        name=name,
                        memory_mb=memory_mb,
                        memory_percent=memory_percent,
                        status=status,
                        username=username,
                    )

                    processes.append(process_info)

                except (psutil.NoSuchProcess, psutil.ZombieProcess):
                    # Process died between iteration and data fetch
                    # This is normal; just skip it
                    logger.debug("Process %s exited during iteration", info.get("pid", "?"))
                    total_processes -= 1  # Don't count processes that died
                    continue

                except psutil.AccessDenied:
                    # Can't read this process (e.g., privileged system process on Linux)
                    # Log and skip; other processes will still be collected
                    logger.debug(
                        "Access denied to process %s",
                        info.get("pid", "?"),
                    )
                    total_processes -= 1  # Don't count inaccessible processes
                    continue

                except Exception as e:
                    # Unexpected error; log but continue
                    logger.warning("Error processing process: %s", e)
                    total_processes -= 1
                    continue

            # Sort by memory usage (highest first)
            processes.sort(key=lambda p: p.memory_percent, reverse=True)

            # Take top 10
            top_processes = processes[:TOP_PROCESSES_LIMIT]

            # Create and return the metric snapshot
            metrics = ProcessMetrics(
                processes=top_processes,
                total_processes=total_processes,
                timestamp=datetime.now(),
            )

            logger.debug(
                "Process metrics: %d total processes, top hog: %s (%.1f MB)",
                total_processes,
                top_processes[0].name if top_processes else "N/A",
                top_processes[0].memory_mb if top_processes else 0,
            )

            return metrics

        except Exception as e:
            logger.error("Failed to get process metrics: %s", e)
            raise MonitorException(f"Process monitoring failed: {e}") from e