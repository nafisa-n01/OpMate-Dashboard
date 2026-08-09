"""
core/monitors/disk_monitor.py
-----------------------------
Disk partition and storage monitoring using psutil.

What we measure:
    1. All mounted partitions/drives (C:, D:, /, /home, etc.)
    2. For each partition: total space, used space, free space, percentage used
    3. Filesystem type (NTFS, ext4, APFS, tmpfs, etc.)
    4. Mount point (where the partition is accessible in the filesystem)

Partitions we skip:
    - Virtual filesystems: tmpfs, sysfs, devfs, proc, cgroup, etc.
      (These are OS memory-based, not real disk storage)
    - Very small partitions: /dev, /sys, /run (typically <1 GB)
    - We only care about real disk storage
"""

import logging
from datetime import datetime
from typing import List

import psutil

from core.monitors.base_monitor import BaseMonitor
from core.data_models import DiskMetrics, PartitionInfo
from core.exceptions import MonitorException


logger = logging.getLogger(__name__)

# Virtual filesystems to skip (OS-managed, not real disk storage)
VIRTUAL_FILESYSTEMS = {
    "tmpfs",
    "devtmpfs",
    "sysfs",
    "proc",
    "cgroup",
    "cgroup2",
    "pstore",
    "securityfs",
    "debugfs",
    "tracefs",
    "fuse.gvfsd-fuse",
}


class DiskMonitor(BaseMonitor):
    """
    Monitors disk partition usage.

    Attributes:
        None (all data fetched fresh each poll)
    """

    def __init__(self) -> None:
        """Initialize disk monitor."""
        super().__init__()
        logger.debug("DiskMonitor initialized")

    def get_data(self) -> DiskMetrics:
        """
        Fetch current disk usage metrics for all partitions.

        Process:
            1. Call psutil.disk_partitions() to get list of mounted partitions
            2. For each partition:
               a. Skip virtual filesystems (tmpfs, sysfs, etc.)
               b. Call psutil.disk_usage(mount_point) to get usage stats
               c. Convert bytes to gigabytes (GB) for readability
               d. Create PartitionInfo dataclass
            3. Collect all partitions into a list
            4. Return DiskMetrics with timestamp

        Returns:
            DiskMetrics: Snapshot of all disk partitions at this moment.

        Raises:
            MonitorException: If disk data cannot be retrieved (rare).
        """
        try:
            partitions: List[PartitionInfo] = []

            # Get all mounted partitions
            # Returns list of: (device, mountpoint, fstype, opts)
            # Example: ('/dev/sda1', '/', 'ext4', 'rw,relatime,errors=remount-ro')
            all_partitions = psutil.disk_partitions(all=False)

            for partition in all_partitions:
                # Skip virtual filesystems (memory-based, not real disk)
                if partition.fstype in VIRTUAL_FILESYSTEMS:
                    logger.debug(
                        "Skipping virtual filesystem: %s (%s)",
                        partition.device,
                        partition.fstype,
                    )
                    continue

                try:
                    # Get usage stats for this partition
                    # Returns: disk_usage(total, used, free, percent)
                    usage = psutil.disk_usage(partition.mountpoint)

                    # Convert bytes to gigabytes (1 GB = 1,024 MB = 1,073,741,824 bytes)
                    total_gb = usage.total / (1024**3)
                    used_gb = usage.used / (1024**3)
                    free_gb = usage.free / (1024**3)
                    percent = usage.percent

                    # Create PartitionInfo for this drive
                    partition_info = PartitionInfo(
                        device=partition.device,
                        mount_point=partition.mountpoint,
                        filesystem_type=partition.fstype,
                        total_gb=total_gb,
                        used_gb=used_gb,
                        free_gb=free_gb,
                        percent=percent,
                    )

                    partitions.append(partition_info)

                    logger.debug(
                        "Partition %s: %.1f%% used (%.1f/%.1f GB)",
                        partition.device,
                        percent,
                        used_gb,
                        total_gb,
                    )

                except PermissionError:
                    logger.warning(
                        "Permission denied accessing partition %s", partition.device
                    )
                    continue

                except OSError as e:
                    logger.warning(
                        "Cannot access partition %s: %s", partition.device, e
                    )
                    continue

            # Create and return the metric snapshot
            metrics = DiskMetrics(
                partitions=partitions,
                timestamp=datetime.now(),
            )

            logger.debug("Disk metrics: %d partitions scanned", len(partitions))
            return metrics

        except Exception as e:
            logger.error("Failed to get disk metrics: %s", e)
            raise MonitorException(f"Disk monitoring failed: {e}") from e