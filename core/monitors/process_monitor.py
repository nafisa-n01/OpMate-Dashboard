"""
core/monitors/process_monitor.py
--------------------------------
Running processes monitoring using psutil.

What we measure:
    1. All running processes on the system
    2. For each: PID, name, CPU %, memory (MB and %), status, owner
    3. Top 10 processes sorted by memory usage (highest first)
    4. Total process count (for system overview)

Why top 10?
    - Full process list is huge (100+ processes on typical systems)
    - Top 10 by memory shows where resources are actually going
    - User can see memory hogs at a glance

CPU percent notes — IMPORTANT:
    psutil's per-process cpu_percent() is stateful — it measures CPU
    time consumed SINCE THE LAST CALL ON THAT SAME Process OBJECT.
    Crucially, psutil.process_iter() creates a brand-new Process
    object every time it's called. If we called cpu_percent() on
    those throwaway objects, every poll would see a "first call" with
    nothing to compare against, and CPU would read 0.0% forever —
    not just on startup, but permanently.

    The fix: ProcessMonitor keeps its own persistent cache of Process
    objects, keyed by PID (self._process_cache). Each poll reuses the
    SAME object for a given PID across calls, so cpu_percent() has a
    real previous timestamp to diff against. A process's CPU % reads
    0.0% only on the single poll where it's first discovered — every
    poll after that returns a real value. Processes that exit are
    removed from the cache to avoid leaking memory over a long-running
    session.

Challenges:
    - Processes die mid-iteration (handle gracefully)
    - Permission errors (can't read other users' processes without root)
    - Process status varies (running, sleeping, zombie, etc.)
    - Some system processes return incomplete/None data even when
      access technically succeeds (e.g. Windows "Memory Compression")
"""

import logging
from datetime import datetime
from typing import Dict, List

import psutil

from core.monitors.base_monitor import BaseMonitor
from core.data_models import ProcessMetrics, ProcessInfo
from core.exceptions import MonitorException


logger = logging.getLogger(__name__)

# Limit for top processes to display
TOP_PROCESSES_LIMIT = 10


class ProcessMonitor(BaseMonitor):
    """
    Monitors running processes.

    Attributes:
        _process_cache (Dict[int, psutil.Process]): Persistent Process
            objects keyed by PID, kept alive across polls so per-process
            cpu_percent() has a real "last call" to measure against
            instead of resetting to 0.0% every poll.
    """

    def __init__(self) -> None:
        """Initialize process monitor."""
        super().__init__()
        self._process_cache: Dict[int, psutil.Process] = {}
        logger.debug("ProcessMonitor initialized")

    def get_data(self) -> ProcessMetrics:
        """
        Fetch current running processes metrics.

        Process:
            1. Get the current set of running PIDs
            2. For each PID, reuse a cached Process object if we've
               seen it before (so cpu_percent() has history to diff
               against), or create + cache a new one if it's new
            3. Prime/measure CPU %, extract memory/status/etc.
            4. Handle errors (process dies, permission denied) gracefully
            5. Prune cache entries for PIDs that no longer exist
            6. Sort by memory usage, take top 10
            7. Return ProcessMetrics with timestamp

        Returns:
            ProcessMetrics: Top 10 processes by memory + total process count.

        Raises:
            MonitorException: If process monitoring fails completely.
        """
        try:
            processes: List[ProcessInfo] = []
            total_processes = 0
            seen_pids = set()

            for pid in psutil.pids():
                seen_pids.add(pid)

                # Reuse the cached Process object for this PID if we
                # have one — this is what makes cpu_percent() actually
                # work across polls. Only create a fresh one the first
                # time we see this PID.
                proc = self._process_cache.get(pid)
                if proc is None:
                    try:
                        proc = psutil.Process(pid)
                        self._process_cache[pid] = proc
                        # Priming call: on a genuinely new Process
                        # object this always returns 0.0. That's
                        # expected and only happens once, on the poll
                        # where this process is first discovered.
                        proc.cpu_percent(interval=None)
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        continue

                total_processes += 1

                try:
                    # Real CPU delta since this object's last call
                    # (either the priming call above on a new process,
                    # or last poll's call on an existing one).
                    cpu_percent = proc.cpu_percent(interval=None)

                    name = proc.name() or "Unknown"

                    try:
                        memory_info = proc.memory_info()
                        memory_mb = memory_info.rss / (1024 * 1024)
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        memory_mb = 0.0

                    try:
                        memory_percent = proc.memory_percent() or 0.0
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        memory_percent = 0.0

                    try:
                        status = proc.status() or "unknown"
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        status = "unknown"

                    try:
                        username = proc.username() or "N/A"
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        username = "N/A"

                    process_info = ProcessInfo(
                        pid=pid,
                        name=name,
                        cpu_percent=cpu_percent,
                        memory_mb=memory_mb,
                        memory_percent=memory_percent,
                        status=status,
                        username=username,
                    )

                    processes.append(process_info)

                except (psutil.NoSuchProcess, psutil.ZombieProcess):
                    # Process died between discovery and data fetch —
                    # normal, just skip it.
                    logger.debug("Process %s exited during iteration", pid)
                    total_processes -= 1
                    continue

                except psutil.AccessDenied:
                    logger.debug("Access denied to process %s", pid)
                    total_processes -= 1
                    continue

                except Exception as e:
                    logger.warning("Error processing process %s: %s", pid, e)
                    total_processes -= 1
                    continue

            # Prune cache entries for processes that no longer exist,
            # so long-running sessions don't accumulate stale objects
            # for every process that has ever existed.
            stale_pids = set(self._process_cache.keys()) - seen_pids
            for stale_pid in stale_pids:
                del self._process_cache[stale_pid]

            # Sort by memory usage (highest first)
            processes.sort(key=lambda p: p.memory_percent, reverse=True)

            # Take top 10
            top_processes = processes[:TOP_PROCESSES_LIMIT]

            metrics = ProcessMetrics(
                processes=top_processes,
                total_processes=total_processes,
                timestamp=datetime.now(),
            )

            logger.debug(
                "Process metrics: %d total processes, top hog: %s (%.1f MB, %.1f%% CPU)",
                total_processes,
                top_processes[0].name if top_processes else "N/A",
                top_processes[0].memory_mb if top_processes else 0,
                top_processes[0].cpu_percent if top_processes else 0,
            )

            return metrics

        except Exception as e:
            logger.error("Failed to get process metrics: %s", e)
            raise MonitorException(f"Process monitoring failed: {e}") from e