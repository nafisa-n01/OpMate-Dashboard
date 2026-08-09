"""
core/worker_thread.py
---------------------
Background worker thread for continuous system monitoring.

This thread runs on a separate OS thread (not the main UI thread),
continuously polling CPU, RAM, disk, and process data at regular intervals,
then emitting Qt signals to notify the UI of updates.

Why separate thread?
    - If monitoring code ran on the main UI thread, a slow disk_usage() call
      would freeze the window during the scan
    - By running on a worker thread, the UI stays responsive to clicks/drags
      while we're busy polling system metrics

Signal-based communication:
    - Worker thread emits Qt signals (metrics_updated_cpu, metrics_updated_ram, etc.)
    - Main window connects these signals to widget slots (update methods)
    - Qt automatically marshals data across thread boundaries safely
    - This is thread-safe (Qt handles the synchronization)
"""

import logging
import time
from datetime import datetime
from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal

from core.data_models import (
    CPUMetrics,
    MemoryMetrics,
    DiskMetrics,
    ProcessMetrics,
    SystemMetrics,
)
from core.monitors.cpu_monitor import CPUMonitor
from core.monitors.memory_monitor import MemoryMonitor
from core.monitors.disk_monitor import DiskMonitor
from core.monitors.process_monitor import ProcessMonitor
from core.monitors.system_monitor import SystemMonitor


logger = logging.getLogger(__name__)


class WorkerThread(QThread):
    """
    Background thread for system monitoring.

    Emits signals when new metrics are available. Connect these signals
    in MainWindow to widget update methods.

    Signals:
        metrics_updated_cpu (CPUMetrics): CPU data updated.
        metrics_updated_memory (MemoryMetrics): RAM/Swap data updated.
        metrics_updated_disk (DiskMetrics): Disk partition data updated.
        metrics_updated_processes (ProcessMetrics): Process list updated.
        metrics_updated_system (SystemMetrics): System info updated.
        error (str): An error occurred during monitoring.
    """

    # Define signals (name -> data type)
    metrics_updated_cpu = pyqtSignal(CPUMetrics)
    metrics_updated_memory = pyqtSignal(MemoryMetrics)
    metrics_updated_disk = pyqtSignal(DiskMetrics)
    metrics_updated_processes = pyqtSignal(ProcessMetrics)
    metrics_updated_system = pyqtSignal(SystemMetrics)
    error = pyqtSignal(str)

    def __init__(self) -> None:
        """Initialize the worker thread."""
        super().__init__()
        self._running = False

        # Instantiate all monitors (lightweight, no polling yet)
        self.cpu_monitor = CPUMonitor()
        self.memory_monitor = MemoryMonitor()
        self.disk_monitor = DiskMonitor()
        self.process_monitor = ProcessMonitor()
        self.system_monitor = SystemMonitor()

        logger.info("WorkerThread initialized")

    def run(self) -> None:
        """
        Main loop for the worker thread.

        Continuously polls each monitor at its defined interval and emits
        signals when new data is available. This method is called automatically
        when you call self.start() on the thread.

        Note: This runs on the worker thread, NOT the main UI thread.
        """
        logger.info("WorkerThread.run() started")
        self._running = True

        # Polling intervals (in seconds)
        # CPU/RAM: fast changes, poll every 1 second
        # Disk: slow changes, poll every 5 seconds
        # Processes: medium changes, poll every 2 seconds
        # System: static info, poll once and update every 10 seconds
        cpu_interval = 1.0
        memory_interval = 1.0
        disk_interval = 5.0
        process_interval = 2.0
        system_interval = 10.0

        # Track next poll times
        next_cpu_poll = time.time()
        next_memory_poll = time.time()
        next_disk_poll = time.time()
        next_process_poll = time.time()
        next_system_poll = time.time()

        while self._running:
            current_time = time.time()

            # Poll CPU if enough time has passed
            if current_time >= next_cpu_poll:
                try:
                    metrics = self.cpu_monitor.get_data()
                    self.metrics_updated_cpu.emit(metrics)
                except Exception as e:
                    logger.error("Error polling CPU: %s", e)
                    self.error.emit(f"CPU monitoring error: {e}")
                next_cpu_poll = current_time + cpu_interval

            # Poll Memory
            if current_time >= next_memory_poll:
                try:
                    metrics = self.memory_monitor.get_data()
                    self.metrics_updated_memory.emit(metrics)
                except Exception as e:
                    logger.error("Error polling Memory: %s", e)
                    self.error.emit(f"Memory monitoring error: {e}")
                next_memory_poll = current_time + memory_interval

            # Poll Disk (less frequently)
            if current_time >= next_disk_poll:
                try:
                    metrics = self.disk_monitor.get_data()
                    self.metrics_updated_disk.emit(metrics)
                except Exception as e:
                    logger.error("Error polling Disk: %s", e)
                    self.error.emit(f"Disk monitoring error: {e}")
                next_disk_poll = current_time + disk_interval

            # Poll Processes
            if current_time >= next_process_poll:
                try:
                    metrics = self.process_monitor.get_data()
                    self.metrics_updated_processes.emit(metrics)
                except Exception as e:
                    logger.error("Error polling Processes: %s", e)
                    self.error.emit(f"Process monitoring error: {e}")
                next_process_poll = current_time + process_interval

            # Poll System (static, less frequently)
            if current_time >= next_system_poll:
                try:
                    metrics = self.system_monitor.get_data()
                    self.metrics_updated_system.emit(metrics)
                except Exception as e:
                    logger.error("Error polling System: %s", e)
                    self.error.emit(f"System monitoring error: {e}")
                next_system_poll = current_time + system_interval

            # Sleep briefly to avoid busy-waiting
            # (if we didn't sleep, this loop would spin 1000s of times/sec, wasting CPU)
            time.sleep(0.1)

        logger.info("WorkerThread.run() stopped")

    def stop(self) -> None:
        """
        Gracefully stop the worker thread.

        Sets the _running flag to False, which causes the run() loop
        to exit on the next iteration.
        """
        logger.info("Stopping WorkerThread...")
        self._running = False