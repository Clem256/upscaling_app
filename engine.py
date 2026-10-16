"""
Real-ESRGAN engine: installation (download, SHA-256 check, extraction) and
execution (one upscale pass, GPU detection).
"""

import hashlib
import os
import re
import subprocess
import tempfile
import threading
import urllib.request
import zipfile
from collections import deque
from pathlib import Path

from PIL import Image

from config import (BIN_DIR, BIN_NAME, ENGINE_ZIPS, IS_WINDOWS, NO_WINDOW, RELEASE_URL,
                    SYSTEM, load_config, save_config)
from i18n import tr
from control import Cancelled
from devices import device_attempts


# --------------------------------------------------------------------------- #
# Installation
# --------------------------------------------------------------------------- #

def find_engine():
    """Return the path of the engine executable inside BIN_DIR, or None if absent."""
    if BIN_DIR.exists():
        for p in BIN_DIR.rglob(BIN_NAME):
            if p.is_file():
                return p
    return None


def download_engine(ctl, status_cb, progress_cb):
    """Download, verify and extract the engine for the current platform.

    The SHA-256 of the zip is compared with the one remembered in config.json
    from a previous install (if any); a mismatch aborts the installation.
    On success the new hash is stored in config.json.

    Args:
        ctl: Control object, checked during the download to allow cancelling.
        status_cb: callable(str) receiving status messages.
        progress_cb: callable(float) receiving download progress, 0-100.

    Returns:
        (path to the executable, SHA-256 hex digest of the downloaded zip).

    Raises:
        Cancelled: if the user cancelled during the download.
        RuntimeError: unsupported system, hash mismatch, or missing binary.
    """
    if SYSTEM not in ENGINE_ZIPS:
        raise RuntimeError(tr("unsupported_system", system=SYSTEM))

    BIN_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = BIN_DIR / "engine.zip"
    url = RELEASE_URL + ENGINE_ZIPS[SYSTEM]

    status_cb(tr("dl_engine"))
    sha = hashlib.sha256()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "anime-upscaler"})
        with urllib.request.urlopen(req, timeout=30) as resp, open(zip_path, "wb") as out:
            total = int(resp.headers.get("Content-Length") or 0)
            done = 0
            while True:
                if ctl.cancelled:
                    raise Cancelled()
                chunk = resp.read(1 << 16)  # 64 KiB at a time
                if not chunk:
                    break
                out.write(chunk)
                sha.update(chunk)
                done += len(chunk)
                if total:
                    progress_cb(done * 100 / total)

        # Compare with the hash remembered from a previous installation.
        digest = sha.hexdigest()
        remembered = load_config().get("sha256", {}).get(SYSTEM)
        if remembered and digest != remembered:
            raise RuntimeError(tr("hash_mismatch", old=remembered, new=digest))

        status_cb(tr("extracting"))
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(BIN_DIR)
    finally:
        # The zip is never kept, whether the install succeeded or not.
        zip_path.unlink(missing_ok=True)

    exe = find_engine()
    if exe is None:
        raise RuntimeError(tr("engine_not_found"))
    if not IS_WINDOWS:
        exe.chmod(exe.stat().st_mode | 0o111)  # make it executable

    cfg = load_config()
    cfg.setdefault("sha256", {})[SYSTEM] = digest
    save_config(cfg)
    return exe, digest


# --------------------------------------------------------------------------- #
# Execution
# --------------------------------------------------------------------------- #

def run_pass(exe, src, dst, model, scale, device, ctl, progress_cb, status_cb, tag):
    """Run one Real-ESRGAN pass, falling back from device to device on failure.

    Args:
        exe: path to the engine executable.
        src: input PNG path.
        dst: output PNG path (removed if a pass fails or is cancelled).
        model: engine model name (e.g. "realesr-animevideov3").
        scale: upscale factor for this pass (2, 3 or 4).
        device: "auto", "cpu", or a GPU index as a string.
        ctl: Control object used to cancel and to track the subprocess.
        progress_cb: callable(float) receiving this pass's progress, 0-100.
        status_cb: callable(str) receiving status messages.
        tag: prefix for status messages (e.g. "AI pass 1/2 (x4)").

    Raises:
        Cancelled: if the user cancelled.
        RuntimeError: if every device attempt failed (includes the engine's last output).
    """
    last_tail = ""
    for label, gpu_args, extra_env in device_attempts(device):
        status_cb(tr("pass_on", tag=tag, label=label))
        progress_cb(0)
        cmd = [str(exe), "-i", str(src), "-o", str(dst), "-n", model, "-s", str(scale),
               "-m", str(exe.parent / "models"), "-f", "png"] + gpu_args
        env = os.environ.copy()
        env.update(extra_env)

        proc = subprocess.Popen(
            cmd, cwd=exe.parent, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, errors="replace", creationflags=NO_WINDOW)
        ctl.proc = proc

        log = deque(maxlen=10)  # last engine lines, shown if everything fails
        # At startup the engine lists ALL GPUs, e.g. "[0 NVIDIA GeForce ...]".
        # Only announce the one we targeted with -g (no name for the default GPU).
        target = gpu_args[1] if len(gpu_args) == 2 and gpu_args[1] != "-1" else None
        announced = False
        for line in proc.stdout:
            log.append(line.rstrip())
            if target is not None and not announced:
                m = re.match(r"\s*\[(\d+) (.+?)\]", line)
                if m and m.group(1) == target:
                    status_cb(f"{tag} on {m.group(2).strip()}...")
                    announced = True
            # The engine prints progress as e.g. "37.50%".
            m = re.search(r"(\d+(?:\.\d+)?)%", line)
            if m:
                progress_cb(float(m.group(1)))
        proc.wait()
        ctl.proc = None

        if ctl.cancelled:
            Path(dst).unlink(missing_ok=True)
            raise Cancelled()
        if proc.returncode == 0 and Path(dst).exists():
            return  # success
        Path(dst).unlink(missing_ok=True)
        last_tail = "\n".join(log)
        status_cb(tr("dev_unavailable", label=label))

    raise RuntimeError(tr("all_failed", tail=last_tail))


def detect_gpus(exe, timeout=60):
    """List the Vulkan GPUs seen by the engine as [(index, name), ...].

    The engine has no "list GPUs" option: it prints them when it starts a real
    job. So we make it process a tiny 16x16 image and parse those lines. The
    indexes are the ones that `-g` expects.

    Args:
        exe: path to the engine executable.
        timeout: seconds before the probe process is killed.

    Returns:
        Sorted list of (index, name); empty if the engine could not be started.
    """
    gpus = {}
    with tempfile.TemporaryDirectory(prefix="upscaler_probe_") as tmp:
        src, dst = Path(tmp) / "probe.png", Path(tmp) / "probe_out.png"
        Image.new("RGB", (16, 16), (128, 128, 128)).save(src)
        cmd = [str(exe), "-i", str(src), "-o", str(dst), "-n", "realesr-animevideov3",
               "-s", "2", "-m", str(exe.parent / "models"), "-f", "png"]
        try:
            proc = subprocess.Popen(
                cmd, cwd=exe.parent, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, errors="replace", creationflags=NO_WINDOW)
        except OSError:
            return []
        # Safety net: kill the probe if it hangs (e.g. broken Vulkan driver).
        timer = threading.Timer(timeout, proc.kill)
        timer.start()
        try:
            for line in proc.stdout:
                m = re.match(r"\s*\[(\d+) (.+?)\]", line)
                if m:
                    gpus.setdefault(int(m.group(1)), m.group(2).strip())
            proc.wait()
        finally:
            timer.cancel()
            if proc.poll() is None:
                proc.kill()
    return sorted(gpus.items())
