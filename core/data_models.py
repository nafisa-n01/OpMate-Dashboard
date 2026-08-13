"""
core/data_models.py
-------------------
Canonical data structures for system metrics.

These classes define what information is collected from each monitor
and passed to the UI. By using structured data (not just dicts or tuples),
we get:
    1. Type safety (IDE autocomplete, type checking)
    2. Self-documenting code (fields are explicit)
    3. Easy to extend (add a field, all code sees it)
"""

from dataclasses import dataclass
from typing import List
from datetime import datetime


@dataclass
class CPUMetrics:
    """
    CPU usage snapshot.

    Attributes:
        overall_percent (float): Total CPU usage across all cores, 0-100.
        per_core_percents (List[float]): CPU % for each logical core.
        frequency_ghz (float): Current CPU frequency in GHz.
        core_count (int): Number of logical cores.
        timestamp (datetime): When this snapshot was taken.
    """

    overall_percent: float
    per_core_percents: List[float]
    frequency_ghz: float
    core_count: int
    timestamp: datetime


@dataclass
class MemoryMetrics:
    """
    RAM and Swap memory snapshot.

    Attributes:
        ram_used_mb (float): Physical RAM used, in megabytes.
        ram_total_mb (float): Total installed RAM, in MB.
        ram_available_mb (float): Available RAM (unused + reclaimable), in MB.
        ram_percent (float): RAM usage as percentage, 0-100.
        swap_used_mb (float): Swap space used, in MB.
        swap_total_mb (float): Total swap available, in MB.
        swap_percent (float): Swap usage as percentage, 0-100.
        timestamp (datetime): When this snapshot was taken.
    """

    ram_used_mb: float
    ram_total_mb: float
    ram_available_mb: float
    ram_percent: float
    swap_used_mb: float
    swap_total_mb: float
    swap_percent: float
    timestamp: datetime


@dataclass
class PartitionInfo:
    """
    Info about a single disk partition.

    Attributes:
        device (str): Device name (e.g., "C:", "/dev/sda1", "Macintosh HD").
        mount_point (str): Where the partition is mounted (e.g., "C:\", "/", "/home").
        filesystem_type (str): Filesystem type (e.g., "NTFS", "ext4", "APFS").
        total_gb (float): Total capacity in gigabytes.
        used_gb (float): Used space in gigabytes.
        free_gb (float): Free space in gigabytes.
        percent (float): Usage as percentage, 0-100.
    """

    device: str
    mount_point: str
    filesystem_type: str
    total_gb: float
    used_gb: float
    free_gb: float
    percent: float


@dataclass
class DiskMetrics:
    """
    All mounted partitions snapshot.

    Attributes:
        partitions (List[PartitionInfo]): List of all disk partitions.
        timestamp (datetime): When this snapshot was taken.
    """

    partitions: List[PartitionInfo]
    timestamp: datetime


@dataclass
class ProcessInfo:
    """
    Info about a single process.

    Attributes:
        pid (int): Process ID.
        name (str): Process executable name (e.g., "chrome.exe", "python").
        cpu_percent (float): CPU usage as a percentage (0-100+, can exceed
            100 on multi-core systems if a process uses more than one core).
        memory_mb (float): Memory used in megabytes.
        memory_percent (float): Memory as percentage of total RAM.
        status (str): Process state ("running", "sleeping", "zombie", etc.).
        username (str): User who owns the process.
    """

    pid: int
    name: str
    cpu_percent: float
    memory_mb: float
    memory_percent: float
    status: str
    username: str


@dataclass
class ProcessMetrics:
    """
    Top processes snapshot.

    Attributes:
        processes (List[ProcessInfo]): Top N processes, sorted by memory (highest first).
        total_processes (int): Total number of processes on the system.
        timestamp (datetime): When this snapshot was taken.
    """

    processes: List[ProcessInfo]
    total_processes: int
    timestamp: datetime


@dataclass
class SystemMetrics:
    """
    Static system information.

    Attributes:
        hostname (str): Computer name.
        os_name (str): Operating system name (e.g., "Windows", "Linux", "Darwin").
        os_version (str): OS version/build (e.g., "11", "22.04", "12.6.1").
        os_architecture (str): "x86-64", "arm64", etc.
        uptime_seconds (int): Time since last boot, in seconds.
        boot_time (datetime): When the system last started.
        total_processes (int): Total processes running.
        total_threads (int): Total threads across all processes.
        cpu_model (str): CPU model name.
        cpu_core_count (int): Number of CPU cores.
        ram_total_gb (float): Total RAM in gigabytes.
    """

    hostname: str
    os_name: str
    os_version: str
    os_architecture: str
    uptime_seconds: int
    boot_time: datetime
    total_processes: int
    total_threads: int
    cpu_model: str
    cpu_core_count: int
    ram_total_gb: float