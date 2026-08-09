"""
core.monitors package
---------------------
System metric monitors (CPU, RAM, Disk, Processes, System info).

Each monitor is independent and provides:
    - get_data(): Fetch current metrics
    - Error handling: Graceful failures
    - Cross-platform: Works on Windows, Linux, macOS
"""