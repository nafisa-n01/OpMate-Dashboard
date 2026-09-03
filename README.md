OpMate — An Operational Dashboard
=====================================
CSE323- Operating Systems 

A lightweight, cross-platform desktop application for real-time system
monitoring, storage analysis, and safe cache cleanup — built with Python
and PyQt6.


OVERVIEW
--------
OptiMate gives you an at-a-glance view of your computer's health: live
CPU, RAM, disk, and process activity, presented in a clean, pixel-art
styled dashboard. Beyond monitoring, it includes a Storage Analyzer to
find out which folders are eating up your disk space, and a Cleanup
Advisor that safely detects and removes regenerable cache/temp files —
only after you explicitly confirm what gets deleted.

Built as part of an Operating Systems course project, OptiMate is
designed to be responsive on low-end hardware, fully offline (no cloud,
no accounts, no database), and safe by default.


FEATURES
--------

Dashboard
  - CPU Usage: overall load + per-core breakdown, frequency, core count
  - RAM Usage: used/available memory with swap space tracking
  - Disk Usage: per-partition usage cards, color-coded by severity
  - PC Health: aggregate status combining CPU/RAM/Disk into a single
    "how's my PC doing?" summary
  - System Overview: OS, hostname, CPU model, uptime, process count

Processes
  - Live table of the top 10 processes by memory usage
  - Shows PID, name, user, CPU %, memory, and status

Storage Analyzer
  - Pick a disk, drill down through folders to see what's consuming space
  - Depth-limited, on-demand scanning — stays fast even on large drives
  - 4-tier severity classification (Safe / Watch / Consider / Clean Up)
  - Animated companion GIF that reacts to hovered folders

Cleanup Advisor
  - Detects safe-to-delete categories: temp files, recycle bin, browser
    cache, and OS-specific caches
  - Every category is checked for existence on your OS before being shown
  - Nothing is ever deleted without an explicit confirmation dialog
    listing exactly what will be removed
  - Best-effort, per-file deletion — one locked file won't abort the
    whole cleanup


TECH STACK
----------
Language            Python 3.10+
GUI Framework        PyQt6
System Metrics       psutil (https://psutil.readthedocs.io/)
Filesystem Access    Python standard library (os, platform, tempfile, shutil)
Fonts                Custom pixel font (Press Start 2P)


PROJECT STRUCTURE
------------------
OpMate Dashboard/
|-- main.py                      Entry point
|-- assets/
|   |-- fonts/                   Pixel font
|   |-- icons/                   Card icons, screws, corner decorations
|   `-- gifs/                    Storage Analyzer companion animations
|-- core/
|   |-- worker_thread.py         Persistent background monitoring thread
|   |-- data_models.py           Shared dataclasses (CPUMetrics, ProcessInfo, etc.)
|   |-- exceptions.py
|   |-- monitors/                CPU, Memory, Disk, Process, System monitors
|   |-- storage/                 Storage Analyzer models + recursive scanner
|   |-- storage_worker_thread.py
|   |-- cleanup/                 Cleanup Advisor models, scanner, deleter
|   `-- cleanup_worker_thread.py
|-- ui/
|   |-- main_window.py           Main window, tabs, signal wiring
|   |-- styles/
|   |   `-- fonts.py              Pixel font loader
|   `-- widgets/                 One widget per dashboard card/tab
`-- requirements.txt


GETTING STARTED
----------------

Prerequisites
  - Python 3.10 or newer
  - Windows, macOS, or Linux

Installation

  # Clone or download the project
  cd "OpMate Dashboard"

  # Create a virtual environment
  python -m venv venv

  # Activate it
  # Windows:
  .\venv\Scripts\Activate.ps1
  # macOS/Linux:
  source venv/bin/activate

  # Install dependencies
  pip install PyQt6 psutil

Running the App

  python main.py


ARCHITECTURE HIGHLIGHTS
-------------------------
- Layered design: core monitors query the OS and return immutable
  dataclass snapshots; the UI layer never touches system APIs directly.

- Signal-driven concurrency: a single persistent WorkerThread polls
  CPU/RAM/Disk/Process/System monitors at tiered intervals (1s-10s) and
  emits Qt signals; the Storage Analyzer and Cleanup Advisor use
  separate, on-demand threads for scanning and deletion, so the UI
  never freezes.

- Safety-first cleanup: deletion is isolated to a single module
  (core/cleanup/cleaner.py), operates file-by-file with individual
  error handling, and always requires explicit user confirmation
  before running.



NOTES
-----
- All data stays local — no network calls, no telemetry, no accounts.
- Cross-platform by design: OS-specific paths (Recycle Bin, browser
  caches, etc.) are detected at runtime via platform.system() rather
  than hardcoded.
