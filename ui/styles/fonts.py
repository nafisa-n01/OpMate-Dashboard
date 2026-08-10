"""
ui/styles/fonts.py
-------------------
Custom pixel font loading.

Loads a pixel-art style .ttf font into Qt's font database once at
startup, so any widget can request it by family name. Falls back
gracefully to the system default font if the file is missing —
so the app never crashes just because an asset hasn't been added yet.
"""

import logging
import os

from PyQt6.QtGui import QFontDatabase


logger = logging.getLogger(__name__)

# Path to the pixel font file (relative to project root)
PIXEL_FONT_PATH = "assets/fonts/PressStart2P-Regular.ttf"

# Cached family name once loaded (avoids re-registering the font every call)
_pixel_font_family: str = ""


def get_pixel_font_family() -> str:
    """
    Get the font family name for the pixel font, loading it if needed.

    On first call, registers the .ttf file with Qt's font database.
    On later calls, returns the cached family name instantly.

    Returns:
        str: Font family name to use in QFont(family_name). Falls back
             to "Arial" if the pixel font file couldn't be found/loaded.
    """
    global _pixel_font_family

    if _pixel_font_family:
        return _pixel_font_family

    if not os.path.exists(PIXEL_FONT_PATH):
        logger.warning(
            "Pixel font not found at %s — using fallback font. "
            "Add a .ttf file there to enable the pixel-art look.",
            PIXEL_FONT_PATH,
        )
        _pixel_font_family = "Arial"
        return _pixel_font_family

    font_id = QFontDatabase.addApplicationFont(PIXEL_FONT_PATH)

    if font_id == -1:
        logger.warning("Failed to load pixel font from %s", PIXEL_FONT_PATH)
        _pixel_font_family = "Arial"
        return _pixel_font_family

    families = QFontDatabase.applicationFontFamilies(font_id)
    if not families:
        logger.warning("Pixel font loaded but no font family found")
        _pixel_font_family = "Arial"
        return _pixel_font_family

    _pixel_font_family = families[0]
    logger.info("Pixel font loaded: %s", _pixel_font_family)
    return _pixel_font_family