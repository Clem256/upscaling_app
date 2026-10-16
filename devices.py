"""
Device selection: labels for the device dropdown and the ordered list of
devices to try (with fallback) when running the engine.
"""

import shutil
import subprocess

from config import NO_WINDOW, NVIDIA_RE, SOFTWARE_RE, SYSTEM
from i18n import tr


def nvidia_smi_name():
    """Return the name of the first NVIDIA GPU reported by nvidia-smi, or None.

    Returns None if nvidia-smi is not installed, times out, or fails.
    """
    if not shutil.which("nvidia-smi"):
        return None
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            text=True, timeout=3, creationflags=NO_WINDOW)
        return out.strip().splitlines()[0].strip() or None
    except Exception:
        return None


def auto_label(gpus, nv_name):
    """Build the label of the "Auto" device entry.

    When we can tell which GPU Auto mode will target, its name is included.

    Args:
        gpus: list of (index, name) tuples detected by the engine.
        nv_name: GPU name from nvidia-smi, or None.

    Returns:
        The text displayed in the device dropdown for Auto mode.
    """
    target = None
    if SYSTEM == "Linux" and shutil.which("nvidia-smi"):
        # Same logic as device_attempts(): the NVIDIA driver is tried first.
        target = next((n for _, n in gpus if NVIDIA_RE.search(n)), nv_name)
    else:
        # Elsewhere, Auto uses the system default: only name it if there is
        # exactly one real (non-software) GPU, so the choice is unambiguous.
        real = [n for _, n in gpus if not SOFTWARE_RE.search(n)]
        if len(real) == 1:
            target = real[0]
    if target:
        return tr("dev_auto_named", name=target)
    return tr("dev_auto")


def build_devices(gpus, nv_name=None):
    """Build the dropdown content as {displayed label: device identifier}.

    Identifiers are "auto", a GPU index as a string ("0", "1"...), or "cpu".
    Labels follow the current interface language, so rebuild after a language change.
    If no GPU was detected (yet), only Auto and CPU are offered.

    Args:
        gpus: list of (index, name) tuples detected by the engine.
        nv_name: GPU name from nvidia-smi, or None.
    """
    devices = {auto_label(gpus, nv_name): "auto"}
    for idx, name in gpus:
        devices[f"GPU {idx}: {name}"] = str(idx)
    devices[tr("dev_cpu")] = "cpu"
    return devices


def device_attempts(choice):
    """Return the ordered list of devices to try for a given user choice.

    Each attempt is a tuple (label, engine "-g" arguments, extra environment
    variables). engine.run_pass() tries them one after the other until one works.

    Args:
        choice: "auto", "cpu", or a GPU index as a string.
    """
    plain = (tr("dev_default_gpu"), [], {})
    if choice == "cpu":
        return [("CPU", ["-g", "-1"], {})]
    if choice.isdigit():
        return [(f"GPU {choice}", ["-g", choice], {}), plain]

    # Auto mode.
    attempts = []
    # Linux: on a hybrid laptop, force the NVIDIA driver. With this filter only
    # the NVIDIA GPU is visible to Vulkan, so it is always index 0.
    if SYSTEM == "Linux" and shutil.which("nvidia-smi"):
        env = {
            "VK_LOADER_DRIVERS_SELECT": "*nvidia*",
            "__NV_PRIME_RENDER_OFFLOAD": "1",
            "__VK_LAYER_NV_optimus": "NVIDIA_only",
        }
        attempts.append(("NVIDIA GPU", ["-g", "0"], env))
    attempts.append(plain)
    return attempts
