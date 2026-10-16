"""
System monitoring (CPU, RAM, GPU, network), meant to run in a separate thread
so it never blocks the interface. Requires psutil, which is optional: check
HAS_PSUTIL before starting monitor_loop().
"""

import shutil
import subprocess
import time

from config import NO_WINDOW
from i18n import tr


import psutil


HAS_PSUTIL = psutil is not None


def read_gpu_stats():
    """Return a one-line description of NVIDIA GPU usage (or why it is unavailable)."""
    if not shutil.which("nvidia-smi"):
        return tr("mon_no_nvidia")
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.total",
             "--format=csv,noheader,nounits"],
            text=True, timeout=3, creationflags=NO_WINDOW).strip().splitlines()[0]
        name, util, used, tot = [x.strip() for x in out.split(",")]
        return tr("mon_gpu_line", name=name, util=util, used=used, tot=tot)
    except Exception:
        return tr("mon_nv_unavail")


def monitor_loop(q, stop):
    """Sample system metrics every 2 seconds and push them to the UI queue.

    Runs in a background thread and requires psutil.

    Args:
        q: queue.Queue receiving ("metrics", dict) messages.
        stop: threading.Event; the loop exits when it is set.
    """
    last_net = psutil.net_io_counters()
    last_t = time.time()
    psutil.cpu_percent()  # primes the measurement (first call always returns 0)
    while not stop.wait(2.0):
        now = time.time()
        net = psutil.net_io_counters()
        dt = max(now - last_t, 1e-6)  # avoid division by zero
        down = (net.bytes_recv - last_net.bytes_recv) / dt / 1024
        up = (net.bytes_sent - last_net.bytes_sent) / dt / 1024
        last_net, last_t = net, now
        ram = psutil.virtual_memory()
        q.put(("metrics", {
            "cpu": psutil.cpu_percent(),
            "ram_pct": ram.percent,
            "ram_txt": f"{ram.used // 2**20} MB / {ram.total // 2**20} MB ({ram.percent} %)",
            "gpu": read_gpu_stats(),
            "net": f"↓ {down:.1f} KB/s | ↑ {up:.1f} KB/s",
        }))
