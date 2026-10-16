"""
Configuration: platform detection, paths, engine download URLs, models,
resolution presets, and config.json read/write.

This module has no dependency on the other modules of the project, so any of
them can import from it without risking a circular import.
"""

import json
import platform
import re
import subprocess
from pathlib import Path

# --------------------------------------------------------------------------- #
# Platform
# --------------------------------------------------------------------------- #

# platform.system() returns "Darwin" on Mac: translate it once, here.
SYSTEM = {"Darwin": "macOS"}.get(platform.system(), platform.system())  # "Windows", "Linux" or "macOS"
IS_WINDOWS = SYSTEM == "Windows"
BIN_NAME = "realesrgan-ncnn-vulkan.exe" if IS_WINDOWS else "realesrgan-ncnn-vulkan"

# Hides console windows when launching subprocesses on Windows (0 elsewhere).
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #

APP_DIR = Path(__file__).resolve().parent
BIN_DIR = APP_DIR / "upscaler"         # where the engine is extracted
CONFIG_FILE = APP_DIR / "config.json"  # stores the known-good SHA-256 per platform

# --------------------------------------------------------------------------- #
# Engine download
# --------------------------------------------------------------------------- #

RELEASE_URL = "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/"
ENGINE_ZIPS = {
    "Windows": "realesrgan-ncnn-vulkan-20220424-windows.zip",
    "Linux": "realesrgan-ncnn-vulkan-20220424-ubuntu.zip",
    "macOS": "realesrgan-ncnn-vulkan-20220424-macos.zip",
}

# --------------------------------------------------------------------------- #
# Models, presets, modes
# --------------------------------------------------------------------------- #

# Displayed name -> (engine model name, supported scales, description shown in the UI)
MODELS = {
    "Anime - fast (recommended)": (
        "realesr-animevideov3", [2, 3, 4],
        "Compact SRVGGNet architecture (16 convolutions), x2/x3/x4. Very fast, "
        "ideal for anime series and recent drawings."),
    "Anime - max quality": (
        "realesrgan-x4plus-anime", [4],
        "Lightweight RRDBNet architecture (6 blocks), x4 only. Stronger restoration "
        "of fine lines and illustration textures. Slower."),
    "Photo / realistic": (
        "realesrgan-x4plus", [4],
        "Full RRDBNet architecture (23 blocks), x4 only. For photos: reduces blur "
        "and digital noise. The slowest."),
}

# Special entries of the resolution dropdown (also used as keys in the logic).
SCREEN_PRESET = "My screen resolution"
CUSTOM_PRESET = "Custom"

# Displayed name -> (width, height). None means "custom": the user types the values.
PRESETS = {
    # --- PC screens / TVs ---
    "Full HD - 1920x1080": (1920, 1080),
    "2K / QHD - 2560x1440": (2560, 1440),
    "4K / UHD - 3840x2160": (3840, 2160),
    "Ultrawide - 2560x1080": (2560, 1080),
    "Ultrawide QHD - 3440x1440": (3440, 1440),
    "Super ultrawide - 5120x1440": (5120, 1440),
    "8K - 7680x4320": (7680, 4320),
    # --- Phones (vertical wallpapers) ---
    "Mobile: FHD+ (1080x2400)": (1080, 2400),
    "Mobile: QHD+ (1440x3120)": (1440, 3120),
    "Mobile: iPhone Standard (1179x2556)": (1179, 2556),
    "Mobile: iPhone Pro Max / Plus (1290x2796)": (1290, 2796),
    "Mobile: Samsung Galaxy Ultra (1440x3088)": (1440, 3088),
    "Mobile: Standard 9:16 (1080x1920)": (1080, 1920),
    # --- Custom ---
    CUSTOM_PRESET: None,
}

# Displayed name -> internal mode used by needed_factor() and finalize().
FIT_MODES = {
    "Fill the screen (crops if the ratio differs)": "fill",
    "Whole image (black bars if the ratio differs)": "fit",
}

# Output format shown in the UI -> file extension.
OUTPUT_FORMATS = {
    "PNG": ".png",
    "JPG": ".jpg",
    "WEBP": ".webp",
}

# Output format -> label shown in the file type list of the "Save as" dialog.
SAVE_DIALOG_LABELS = {
    "PNG": "PNG",
    "JPG": "JPEG",
    "WEBP": "WebP",
}

# --------------------------------------------------------------------------- #
# Devices and limits
# --------------------------------------------------------------------------- #

CPU_LABEL = "CPU (very slow)"
NVIDIA_RE = re.compile(r"nvidia|geforce|rtx|gtx|quadro", re.I)
SOFTWARE_RE = re.compile(r"llvmpipe|lavapipe|swiftshader|software", re.I)

MAX_SIDE = 16384  # maximum width/height accepted, for the target and intermediate passes
WEBP_MAX_SIDE = 16383  # hard limit of the WebP format itself (one pixel less than MAX_SIDE)


# --------------------------------------------------------------------------- #
# config.json
# --------------------------------------------------------------------------- #

def load_config():
    """Read config.json and return it as a dict ({} if missing or invalid)."""
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_config(cfg):
    """Write the config dict to config.json."""
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")