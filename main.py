"""
main.py
--------
Entry point for the SystemWatch application.

Responsibilities:
    - Configure application-wide logging
    - Create the Qt Application instance
    - Load the main window
    - Start the Qt event loop
"""

import sys
import logging

# Pylint cannot properly inspect some PyQt6 modules
# even though the imports work correctly.
# pylint: disable=no-name-in-module
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon

from ui.main_window import MainWindow


def setup_logging() -> None:
    """
    Configure basic logging for the whole application.

    Every module can create its own logger with:
        logger = logging.getLogger(__name__)

    and messages will automatically follow this same
    format, with the module name attached, so you know
    exactly where a log line came from.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def main() -> int:
    """
    Application entry point.

    Creates the QApplication (the object that manages the
    whole GUI runtime), builds the main window, and starts
    the Qt event loop.

    Returns:
        int: Process exit code, passed to sys.exit().
    """
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Starting SystemWatch...")

    app = QApplication(sys.argv)
    app.setApplicationName("SystemWatch")

    # Window/taskbar icon — see asset instructions below
    app.setWindowIcon(QIcon("assets/icons/app_icon.png"))

    window = MainWindow()
    window.show()

    logger.info("Main window displayed. Entering event loop.")
    exit_code = app.exec()

    logger.info("SystemWatch closed with exit code %s", exit_code)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
