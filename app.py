#!/usr/bin/env python3
"""
AI Upscale Studio (ex Anime Upscaler & Monitor)
===============================================

Upscales an image to any resolution (PC wallpapers, ultrawide, phones...)
using Real-ESRGAN (the realesrgan-ncnn-vulkan engine, running on Vulkan).
The interface is built with PyQt6 (dark "studio" theme), in English or French
(EN | FR switch in the top bar, English by default).

Dependencies: PyQt6 and pillow (required), psutil (Monitoring tab),
numpy + opencv-python-headless (Wallpaper maker)
    pip install PyQt6 pillow psutil numpy opencv-python-headless

The engine (~30 MB) is downloaded automatically on first use into ./upscaler
(next to this file) from the official xinntao/Real-ESRGAN release. Its SHA-256
is computed and stored in config.json; if a later download yields a different
file, it is rejected. See README.md for the full documentation.

Usage:  python app.py

Project layout
--------------
app.py          Entry point (this file).
config.py       Constants (platform, paths, URLs, models, presets) and config.json I/O.
i18n.py         Interface language (English / French): tr(), tr_name(), all texts.
control.py      Cancellation helpers (Cancelled, Control).
devices.py      GPU/CPU labels for the dropdown and the device fallback order.
engine.py       Real-ESRGAN engine: install (download + SHA-256 + extract) and run.
upscale.py      Pass planning, final resize/crop, full image pipeline.
monitor.py      Background CPU / RAM / GPU / network monitoring.
wallpaper.py    Wallpaper pipeline (thumbnail, crop, clean, upscale, grain).
cleanup.py      Optional text / logo erasing (OCR + LaMa).
theme.py        Dark Fusion palette + stylesheet (QSS).
export.py       Saves the previewed (temporary PNG) result in the chosen format.
widgets.py      Reusable widgets: CompareView, SegmentedControl, SliderRow, dialogs...
gui.py          Main window (class App), Upscaler tab, Monitoring tab.
gui_wallpaper.py  "Wallpaper maker" tab.

Dependency direction (no cycles):
    config <- i18n, control, devices, monitor
    i18n   <- devices, monitor, engine, upscale, wallpaper, cleanup, export, widgets, gui*
    engine  -> config, control, devices
    upscale -> config, engine
    widgets -> config
    export  -> config
    gui_wallpaper -> widgets + everything above
    gui     -> gui_wallpaper + everything above
    app     -> gui, theme
"""

import sys

from PyQt6.QtWidgets import QApplication

from gui import App
from theme import apply_theme


def main():
    qt_app = QApplication(sys.argv)
    apply_theme(qt_app)
    window = App()
    window.show()
    sys.exit(qt_app.exec())


if __name__ == "__main__":
    main()
