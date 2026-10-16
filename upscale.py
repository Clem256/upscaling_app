"""
Upscale logic: planning the AI passes, final resize/crop, and the full
image pipeline.
"""

import tempfile
from pathlib import Path

from PIL import Image, ImageOps

from config import MAX_SIDE, MODELS, WEBP_MAX_SIDE
from engine import run_pass
from i18n import tr

# Upscaled images can be huge; disable Pillow's decompression-bomb guard.
# This module is imported by gui.py, so the setting is applied before any
# image is opened anywhere in the application.
Image.MAX_IMAGE_PIXELS = None


def needed_factor(w, h, tw, th, mode):
    """Return the enlargement factor required to reach the target size.

    Args:
        w, h: source size.
        tw, th: target size.
        mode: "fill" (image must cover the target) or "fit" (image must fit inside it).
    """
    sx, sy = tw / w, th / h
    return max(sx, sy) if mode == "fill" else min(sx, sy)


def plan_passes(needed, allowed):
    """Choose the chain of AI scales that reaches at least `needed` (3 passes max).

    At each step the smallest allowed scale covering what remains is picked,
    or the largest one if none is big enough.

    Args:
        needed: total enlargement factor required.
        allowed: scales supported by the model, e.g. [2, 3, 4].

    Returns:
        List of scales to apply in order, e.g. [4, 2].
    """
    passes, current = [], 1.0
    while current < needed - 1e-6 and len(passes) < 3:
        remaining = needed / current
        candidates = [s for s in allowed if s >= remaining]
        s = min(candidates) if candidates else max(allowed)
        passes.append(s)
        current *= s
    return passes


def finalize(img, tw, th, mode):
    """Resize (Lanczos) then crop or letterbox so the result is exactly tw x th.

    Args:
        img: PIL image, already upscaled by the AI passes.
        tw, th: exact target size.
        mode: "fill" crops the overflow; "fit" adds black bars.
    """
    w, h = img.size
    if mode == "fill":
        # Scale so the image covers the target, then crop the center.
        scale = max(tw / w, th / h)
        nw, nh = max(tw, round(w * scale)), max(th, round(h * scale))
        img = img.resize((nw, nh), Image.LANCZOS)
        left, top = (nw - tw) // 2, (nh - th) // 2
        return img.crop((left, top, left + tw, top + th))
    # "fit": scale so the image fits inside, then center it on a black canvas.
    scale = min(tw / w, th / h)
    nw, nh = max(1, round(w * scale)), max(1, round(h * scale))
    img = img.resize((nw, nh), Image.LANCZOS)
    canvas = Image.new("RGB", (tw, th), (0, 0, 0))
    canvas.paste(img, ((tw - nw) // 2, (th - nh) // 2))
    return canvas


def upscale_image(exe, src, dst, tw, th, model_key, device, mode, ctl, progress_cb, status_cb):
    """Full pipeline: load, AI pass(es), final resize/crop, save.

    Args:
        exe: path to the engine executable.
        src: source image path.
        dst: destination path. The format follows the extension: .jpg/.jpeg and
            .webp are saved at quality 95, anything else (PNG) is lossless.
        tw, th: target width and height.
        model_key: key of MODELS (displayed name).
        device: "auto", "cpu", or a GPU index as a string.
        mode: "fill" or "fit" (see FIT_MODES).
        ctl: Control object for cancellation.
        progress_cb: callable(float) receiving overall progress, 0-100.
        status_cb: callable(str) receiving status messages.

    Raises:
        RuntimeError: if the intermediate resolution would exceed MAX_SIDE,
            if the target exceeds the WebP limit (WebP output only),
            or if the engine fails.
        Cancelled: if the user cancelled.
    """
    model, allowed, _ = MODELS[model_key]
    dst = Path(dst)

    # Checked first so the user doesn't wait for the AI passes just to fail on save.
    if dst.suffix.lower() == ".webp" and (tw > WEBP_MAX_SIDE or th > WEBP_MAX_SIDE):
        raise RuntimeError(tr("webp_limit_target", n=WEBP_MAX_SIDE))

    # The image is re-read with Pillow: it handles EXIF orientation and formats
    # the engine cannot always read (BMP, TIFF, WebP...).
    img = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
    w, h = img.size

    needed = needed_factor(w, h, tw, th, mode)
    passes = plan_passes(needed, allowed) if needed > 1.0 else []

    # Refuse early if the chain of passes would create an oversized image.
    if passes:
        total = 1
        for s in passes:
            total *= s
        if w * total > MAX_SIDE or h * total > MAX_SIDE:
            raise RuntimeError(tr("inter_too_large"))

    with tempfile.TemporaryDirectory(prefix="upscaler_") as tmp:
        current = Path(tmp) / "step0.png"
        img.save(current)
        n = len(passes)
        for i, s in enumerate(passes, 1):
            out = Path(tmp) / f"step{i}.png"
            # Map this pass's 0-100 progress into its slice of the overall bar.
            base, span = (i - 1) * 100 / n, 100 / n
            run_pass(exe, current, out, model, s, device, ctl,
                     lambda p, b=base, sp=span: progress_cb(b + p * sp / 100),
                     status_cb, tr("ai_pass", i=i, n=n, s=s))
            current = out

        status_cb(tr("adjusting"))
        result = Image.open(current)
        result.load()  # read pixels now: the temp folder is deleted on exit

    result = finalize(result, tw, th, mode)
    suffix = dst.suffix.lower()
    if suffix in (".jpg", ".jpeg"):
        result.save(dst, quality=95, subsampling=0)
    elif suffix == ".webp":
        # method=6 is the slowest/best compression setting; quality 95 is near-lossless to the eye.
        result.save(dst, quality=95, method=6)
    else:
        result.save(dst)
    progress_cb(100)