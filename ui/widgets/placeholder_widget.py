"""
ui/widgets/placeholder_widget.py
--------------------------------
Placeholder widget for tabs under construction.

Used temporarily in MainWindow so you can run the app
without all tabs being fully implemented yet.
"""

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont


class PlaceholderWidget(QWidget):
    """
    A simple placeholder widget showing "Tab name under construction".

    Attributes:
        name (str): The name of the tab (e.g., "Dashboard", "Processes").
    """

    def __init__(self, name: str) -> None:
        """
        Initialize placeholder.

        Args:
            name: Display name of this tab.
        """
        super().__init__()
        self.name = name

        layout = QVBoxLayout()
        self.setLayout(layout)

        label = QLabel(f"{self.name}\n(under construction)")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        font = QFont()
        font.setPointSize(18)
        font.setBold(True)
        label.setFont(font)
        label.setStyleSheet("color: #888888;")

        layout.addStretch()
        layout.addWidget(label)
        layout.addStretch()

        self.setStyleSheet("background-color: #2a2a3e;")