#!/usr/bin/env python3
"""
Wallpaper maker for low-quality sources (YouTube thumbnails, small JPEGs...).

Put this file next to app.py (it reuses config.py, engine.py, upscale.py).

    python wallpaper.py "https://www.youtube.com/watch?v=XXXXXXXXXXX"
    python wallpaper.py cover.jpg -r 2560x1440 --model "Anime - max quality"
    python wallpaper.py VIDEO_ID -r 1440x3120 --focus-x 0.3     # phone, subject on the left

Why a dedicated pipeline? A thumbnail is a 1280x720 (at best) JPEG that already
went through YouTube's compression. Feeding it straight to Real-ESRGAN makes the AI
treat JPEG blocks, mosquito noise and black bars as real details and enlarge them.
So, in order:

  1. get the best thumbnail YouTube has (maxresdefault, hq720, ...)
  2. remove letterbox bars (4:3 thumbnails contain black bars)
  3. crop to the target ratio BEFORE upscaling (no pixels wasted on what gets cropped)
  4. light denoise / de-JPEG BEFORE upscaling
  5. ONE AI pass (chaining x4 then x2 amplifies artifacts), Lanczos for the remainder
  6. add a very fine grain at the end (hides the "plastic" look of AI output)

Optional dependencies: numpy + opencv-python-headless (steps 2 and 4, 6).
"""

import argparse
import re
import sys
import tempfile
import urllib.request
from pathlib import Path

from PIL import Image, ImageFilter, ImageOps

from config import MAX_SIDE, MODELS, PRESETS
from control import Control
from cleanup import CleanOptions, ZONE_PRESETS, clean_image
from engine import download_engine, find_engine, run_pass
from i18n import tr
from upscale import finalize, needed_factor, plan_passes

Image.MAX_IMAGE_PIXELS = None

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None
try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None


# --------------------------------------------------------------------------- #
# 1. Fetching the best YouTube thumbnail
# --------------------------------------------------------------------------- #

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_URL_ID_RE = re.compile(r"(?:v=|youtu\.be/|/shorts/|/embed/|/live/)([A-Za-z0-9_-]{11})")

# Best first. hq720 exists for many videos that have no maxresdefault;
# sddefault / hqdefault are 4:3 with black bars (removed later by autocrop_bars).
THUMB_VARIANTS = ["maxresdefault.jpg", "hq720.jpg", "sddefault.jpg", "hqdefault.jpg"]


def video_id(text):
    """Return the 11-character YouTube id from a URL or a bare id, or None."""
    text = text.strip()
    if _ID_RE.match(text):
        return text
    m = _URL_ID_RE.search(text)
    return m.group(1) if m else None


def fetch_thumbnail(vid, dest_dir, status=print):
    """Download the largest available thumbnail of a video. Returns its path."""
    best = None
    for name in THUMB_VARIANTS:
        url = f"https://i.ytimg.com/vi/{vid}/{name}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=20) as r:
                data = r.read()
        except Exception:
            continue  # 404 = this size does not exist for this video
        path = Path(dest_dir) / f"{vid}_{name}"
        path.write_bytes(data)
        with Image.open(path) as im:
            size = im.size
        # 120x90 is YouTube's grey "no thumbnail" placeholder.
        if size[0] <= 120:
            continue
        status(tr("thumb_found", name=name, w=size[0], h=size[1]))
        if best is None or size[0] * size[1] > best[1][0] * best[1][1]:
            best = (path, size)
        if name in ("maxresdefault.jpg", "hq720.jpg"):
            break  # 16:9 without bars: nothing better to look for
    if best is None:
        raise RuntimeError(tr("no_thumb", vid=vid))
    return best[0]


# --------------------------------------------------------------------------- #
# 2-4. Preparation of the source
# --------------------------------------------------------------------------- #

def autocrop_bars(img, dark=22, min_frac=0.03, inset=2):
    """Remove black letterbox/pillarbox bars on the four sides (needs numpy).

    A row/column is a "bar" if it is dark on average and has no bright pixel.
    The crop is applied only if the bars are at least `min_frac` of the side, and
    `inset` extra pixels are removed because JPEG blurs the bar edge.
    """
    if np is None:
        return img
    a = np.asarray(img.convert("L"), dtype=np.uint8)
    h, w = a.shape

    def run(mask):  # length of the leading run of True
        n = 0
        for v in mask:
            if not v:
                break
            n += 1
        return n

    row_bar = (a.mean(axis=1) < dark) & (a.max(axis=1) < 70)
    col_bar = (a.mean(axis=0) < dark) & (a.max(axis=0) < 70)
    top, bottom = run(row_bar), run(row_bar[::-1])
    left, right = run(col_bar), run(col_bar[::-1])
    if top + bottom >= h or left + right >= w:  # fully dark image: leave it alone
        return img
    top = top + inset if top >= min_frac * h else 0
    bottom = bottom + inset if bottom >= min_frac * h else 0
    left = left + inset if left >= min_frac * w else 0
    right = right + inset if right >= min_frac * w else 0
    if not (top or bottom or left or right):
        return img
    return img.crop((left, top, w - right, h - bottom))


def crop_to_ratio(img, tw, th, focus_x=0.5, focus_y=0.5):
    """Crop to the ratio tw:th. focus_x/y (0..1) choose which part is kept."""
    w, h = img.size
    target = tw / th
    if abs(w / h - target) < 0.005:
        return img
    if w / h > target:  # too wide: cut left/right
        nw = round(h * target)
        left = round((w - nw) * focus_x)
        return img.crop((left, 0, left + nw, h))
    nh = round(w / target)  # too tall: cut top/bottom
    top = round((h - nh) * focus_y)
    return img.crop((0, top, w, top + nh))


def deblock(img, strength=3.0):
    """Light edge-preserving denoise to smooth JPEG blocks before the AI sees them.

    strength 0 disables it; 2-4 is subtle; above 6 it starts to erase fine lines.
    Needs opencv; silently skipped otherwise.
    """
    if strength <= 0 or cv2 is None or np is None:
        return img
    bgr = cv2.cvtColor(np.asarray(img.convert("RGB")), cv2.COLOR_RGB2BGR)
    out = cv2.fastNlMeansDenoisingColored(bgr, None, strength, strength, 7, 21)
    return Image.fromarray(cv2.cvtColor(out, cv2.COLOR_BGR2RGB))


def add_grain(img, sigma=2.0, seed=0):
    """Add very fine luminance noise (8-bit units). Makes AI output look natural."""
    if sigma <= 0 or np is None:
        return img
    rng = np.random.default_rng(seed)
    a = np.asarray(img.convert("RGB"), dtype=np.float32)
    a += rng.normal(0.0, sigma, a.shape[:2] + (1,)).astype(np.float32)
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def choose_passes(needed, allowed, max_passes=0, w=0, h=0):
    """Pick the AI scales to chain. max_passes: 0 = auto, 1-3 = at most that many.

    Auto adds a second pass only when one pass would leave more than 25% to be
    filled by plain interpolation (which blurs), never beyond 2 passes, and never
    if the result would exceed MAX_SIDE or about 70 megapixels.
    """
    if needed <= 1.0:
        return []
    full = plan_passes(needed, allowed)
    if max_passes > 0:
        return full[:max_passes]
    out, prod = [], 1
    for s in full:
        nxt = prod * s
        if out and (w * nxt > MAX_SIDE or h * nxt > MAX_SIDE or (w * nxt) * (h * nxt) > 70e6):
            break
        out.append(s)
        prod = nxt
        if needed / prod <= 1.25 or len(out) == 2:
            break
    return out


def sharpen(img, amount):
    """Final sharpening, amount 0-100. Fine unsharp mask + a broad one that restores
    the micro-contrast the AI flattens ("oil painting" look). Radii scale with size."""
    if amount <= 0:
        return img
    w = img.size[0]
    fine = ImageFilter.UnsharpMask(radius=max(0.8, w / 1900), percent=int(amount * 1.2), threshold=2)
    broad = ImageFilter.UnsharpMask(radius=max(4.0, w / 320), percent=int(amount * 0.45), threshold=0)
    return img.filter(broad).filter(fine)


# --------------------------------------------------------------------------- #
# 5. Pipeline
# --------------------------------------------------------------------------- #

def make_wallpaper(exe, src, dst, tw, th, model_key, device="auto", mode="fill",
                   denoise=0.0, grain=2.0, max_passes=0, focus_x=0.5, focus_y=0.5,
                   status=print, ctl=None, progress=None, clean=None, sharp=40.0, shrink=1.0):
    """Full pipeline: clean -> crop -> AI pass(es) -> exact size -> grain -> save.

    ctl: optional Control (cancel from another thread -> Cancelled is raised).
    progress: optional callable(float 0-100).
    clean: optional cleanup.CleanOptions (erase text / logos / sound bars before upscaling).
    max_passes: 0 = auto. sharp: final sharpening 0-100. shrink: reduce the source by this
    factor before the AI (use ~2 when YouTube enlarged a tiny thumbnail itself).
    """
    model, allowed, _ = MODELS[model_key]
    ctl = ctl or Control()
    progress = progress or (lambda p: None)

    img = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
    status(tr("wp_source", w=img.size[0], h=img.size[1]))
    img = autocrop_bars(img)
    if mode == "fill":
        img = crop_to_ratio(img, tw, th, focus_x, focus_y)
    if clean is not None and clean.active:
        img = clean_image(img, clean, status)  # BEFORE upscaling: the AI would sharpen the letters
    if shrink > 1.0:
        sw, sh = img.size
        img = img.resize((max(16, round(sw / shrink)), max(16, round(sh / shrink))), Image.LANCZOS)
    img = deblock(img, denoise)
    w, h = img.size
    status(tr("wp_prepared", w=w, h=h))
    if w < 900:
        status(tr("wp_small_source", w=w, h=h))

    needed = needed_factor(w, h, tw, th, mode)
    passes = choose_passes(needed, allowed, max_passes, w, h)
    total = 1
    for s in passes:
        total *= s
    if passes and (w * total > MAX_SIDE or h * total > MAX_SIDE):
        raise RuntimeError(tr("inter_too_large"))

    with tempfile.TemporaryDirectory(prefix="wallpaper_") as tmp:
        current = Path(tmp) / "step0.png"
        img.save(current)
        n = len(passes)
        for i, s in enumerate(passes, 1):
            out = Path(tmp) / f"step{i}.png"
            base, span = (i - 1) * 100 / n, 100 / n
            run_pass(exe, current, out, model, s, device, ctl,
                     lambda p, b=base, sp=span: progress(b + p * sp / 100),
                     status, tr("ai_pass", i=i, n=n, s=s))
            current = out
        result = Image.open(current)
        result.load()

    result = finalize(result, tw, th, mode)
    result = sharpen(result, sharp)
    result = add_grain(result, grain)

    dst = Path(dst)
    if dst.suffix.lower() in (".jpg", ".jpeg"):
        result.save(dst, quality=95, subsampling=0)
    elif dst.suffix.lower() == ".webp":
        result.save(dst, quality=95, method=6)
    else:
        result.save(dst)
    progress(100)
    status(tr("wp_saved_status", dst=dst, w=tw, h=th))


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def parse_size(text):
    for name, v in PRESETS.items():
        if v and text.lower() in name.lower():
            return v
    m = re.match(r"^(\d{2,5})\s*[xX]\s*(\d{2,5})$", text.strip())
    if not m:
        raise argparse.ArgumentTypeError("use WIDTHxHEIGHT, e.g. 3840x2160")
    return int(m.group(1)), int(m.group(2))


def main():
    ap = argparse.ArgumentParser(description="Make a clean wallpaper from a YouTube thumbnail or any small image.")
    ap.add_argument("source", help="YouTube URL, video id, or image path")
    ap.add_argument("-o", "--output", help="output file (default: <name>_<w>x<h>.png)")
    ap.add_argument("-r", "--resolution", type=parse_size, default=(3840, 2160),
                    help="target size WIDTHxHEIGHT (default 3840x2160)")
    ap.add_argument("--model", default="Anime - max quality", choices=list(MODELS),
                    help="AI model (default: Anime - max quality)")
    ap.add_argument("--device", default="auto", help="auto, cpu, or a GPU index")
    ap.add_argument("--mode", choices=["fill", "fit"], default="fill")
    ap.add_argument("--denoise", type=float, default=0.0, help="pre-AI denoise 0-8 (default 0 = off; it removes micro-contrast)")
    ap.add_argument("--grain", type=float, default=2.0, help="final grain 0-6 (default 2, 0 = off)")
    ap.add_argument("--passes", type=int, default=0, choices=[0, 1, 2, 3],
                    help="max AI passes, 0 = auto (default)")
    ap.add_argument("--sharpen", type=float, default=40.0, help="final sharpening 0-100 (default 40)")
    ap.add_argument("--shrink", type=float, default=1.0,
                    help="reduce the source by this factor before the AI, e.g. 2 if YouTube enlarged a tiny thumbnail")
    ap.add_argument("--focus-x", type=float, default=0.5, help="0..1: which horizontal part to keep when cropping")
    ap.add_argument("--focus-y", type=float, default=0.5, help="0..1: which vertical part to keep when cropping")
    ap.add_argument("--erase-text", action="store_true",
                    help="erase titles/credits with OCR + LaMa (see cleanup.INSTALL_HINT)")
    ap.add_argument("--ocr-conf", type=float, default=0.15, help="text detection confidence, 0.05-0.8 (lower = erases more)")
    ap.add_argument("--zone", help="area to erase as x0,y0,x1,y1 in percent (e.g. 0,66,100,100), "
                                   "or a preset name from cleanup.ZONE_PRESETS")
    ap.add_argument("--zone-mode", choices=["whole", "bright"], default="whole",
                    help="whole zone, or only its bright pixels (sound bars)")
    ap.add_argument("--zone-bright", type=int, default=200, help="brightness threshold for --zone-mode bright")
    ap.add_argument("--keep-source", action="store_true", help="keep the downloaded thumbnail next to the output")
    a = ap.parse_args()

    if np is None or cv2 is None:
        print("Note: install numpy and opencv-python-headless for bar removal, denoise and grain "
              "(pip install numpy opencv-python-headless).", file=sys.stderr)

    exe = find_engine()
    if exe is None:
        exe, _ = download_engine(Control(), print, lambda p: None)

    tw, th = a.resolution
    zone = None
    if a.zone:
        zone = ZONE_PRESETS.get(a.zone) or tuple(float(v) for v in a.zone.split(","))
        if len(zone) != 4:
            ap.error("--zone needs 4 values: x0,y0,x1,y1")
    clean = CleanOptions(text=a.erase_text, ocr_conf=a.ocr_conf, zone=zone, zone_mode=a.zone_mode, bright=a.zone_bright)
    with tempfile.TemporaryDirectory(prefix="thumb_") as tmp:
        vid = video_id(a.source) if not Path(a.source).exists() else None
        if vid:
            src = fetch_thumbnail(vid, tmp)
            stem = vid
        else:
            src, stem = Path(a.source), Path(a.source).stem
        out = Path(a.output) if a.output else Path(f"{stem}_{tw}x{th}.png")
        if vid and a.keep_source:
            Path(f"{stem}_source.jpg").write_bytes(Path(src).read_bytes())
        make_wallpaper(exe, src, out, tw, th, a.model, a.device, a.mode, a.denoise, a.grain,
                       a.passes, a.focus_x, a.focus_y, clean=clean, sharp=a.sharpen, shrink=a.shrink)


if __name__ == "__main__":
    main()
