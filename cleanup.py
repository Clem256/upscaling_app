"""
Optional "erase" step of the wallpaper pipeline: removes titles / credits (OCR),
logos and sound-bar visualizers from the picture BEFORE it is upscaled.

Why before: the upscaler sharpens letter edges and makes them part of the picture,
which makes them much harder to erase cleanly afterwards.

How:
  1. build a mask (white = to erase) from
       - the text found by EasyOCR (English + Japanese): only the LETTER STROKES inside
         each detected box are masked, not the whole box (so the artwork behind is kept), and/or
       - a rectangular zone you choose (logo corner, bottom band where the
         visualizer is...), either the whole zone or only its bright pixels (bars).
         In "bright" mode only thin, bar-like shapes are kept: big bright areas of the
         artwork (white clothes, legs, clouds...) are left alone.
  2. grow the mask a couple of pixels (drop shadows, outlines, anti-aliasing)
  3. let LaMa (large-mask inpainting) rebuild the background, one local crop per
     cluster of the mask (context around it) instead of the whole picture at once

Heavy optional dependencies (PyTorch, ~2 GB on Windows/Linux):
    pip install torch torchvision easyocr
    pip install --no-deps simple-lama-inpainting
`--no-deps` on purpose: that package pins very old numpy (<2) and Pillow (<10) and
would downgrade or break the rest of the project; its code works fine with recent ones.
They use the GPU automatically when PyTorch can see a CUDA GPU, otherwise the CPU.
Model files are downloaded on first use (OCR ~100 MB, LaMa ~200 MB).
"""

import importlib.util
from dataclasses import dataclass
from typing import Optional, Tuple

from PIL import Image

from i18n import tr

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None
try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None

OCR_LANGS = ["en", "ja"]  # EasyOCR can combine Japanese with English only
INSTALL_HINT = "pip install torch torchvision easyocr  &&  pip install --no-deps simple-lama-inpainting"

# Zone presets, as percentages (x0, y0, x1, y1) of the picture that will be kept.
ZONE_PRESETS = {
    "No zone": (0, 0, 0, 0),
    "Bottom third (visualizer)": (0, 66, 100, 100),
    "Bottom half (visualizer)": (0, 50, 100, 100),
    "Middle band (visualizer)": (0, 35, 100, 70),
    "Top-left corner (logo)": (0, 0, 25, 20),
    "Top-right corner (logo)": (75, 0, 100, 20),
    "Bottom-left corner (logo)": (0, 80, 25, 100),
    "Bottom-right corner (logo)": (75, 80, 100, 100),
    "Custom": None,
}
ZONE_MODES = {
    "Whole zone": "whole",
    "Bright pixels only (sound bars)": "bright",
}


@dataclass
class CleanOptions:
    """What to erase. `zone` is (x0, y0, x1, y1) in percent, or None."""
    text: bool = False
    ocr_conf: float = 0.15       # min. detection confidence (stylised fonts score low)
    zone: Optional[Tuple[float, float, float, float]] = None
    zone_mode: str = "whole"      # "whole" or "bright"
    bright: int = 200             # luminance threshold for "bright"

    @property
    def active(self):
        return self.text or self.zone_valid

    @property
    def zone_valid(self):
        z = self.zone
        return bool(z) and z[2] > z[0] and z[3] > z[1]


def available():
    """True if EasyOCR and LaMa are installed (the maths part only needs numpy + cv2)."""
    return all(importlib.util.find_spec(m) for m in ("easyocr", "simple_lama_inpainting"))


# --------------------------------------------------------------------------- #
# Masks
# --------------------------------------------------------------------------- #

def zone_mask(img, zone, mode="whole", bright=200):
    """Mask (PIL 'L', 255 = erase) of a percent rectangle, optionally bright pixels only."""
    w, h = img.size
    x0, y0, x1, y1 = zone
    box = (round(w * x0 / 100), round(h * y0 / 100), round(w * x1 / 100), round(h * y1 / 100))
    mask = Image.new("L", (w, h), 0)
    if box[2] <= box[0] or box[3] <= box[1]:
        return mask
    if mode == "whole" or np is None or cv2 is None:
        mask.paste(255, box)
        return mask

    lum = np.asarray(img.convert("L"))
    out = np.zeros((h, w), dtype=np.uint8)
    region = lum[box[1]:box[3], box[0]:box[2]]
    k = max(3, round(min(w, h) / 200) | 1)
    found = np.zeros(region.shape, dtype=np.uint8)
    # Bars glued to a pale part of the artwork only separate at a higher threshold, so also
    # try a few stricter levels (bars are usually blown out to pure white); at those levels
    # only compact, rectangular shapes are accepted to avoid catching small highlights.
    levels = [bright] + [t for t in (235, 248, 254) if t > bright]
    for i, t in enumerate(levels):
        sub = (region >= t).astype(np.uint8) * 255
        # Close small holes so each bar becomes one solid shape, drop isolated specks.
        sub = cv2.morphologyEx(sub, cv2.MORPH_CLOSE, np.ones((k, k), np.uint8))
        sub = cv2.morphologyEx(sub, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
        found |= _keep_thin_shapes(sub, min(w, h), w * h, min_extent=0.0 if i == 0 else 0.6)
    out[box[1]:box[3], box[0]:box[2]] = found
    return Image.fromarray(out)


def _keep_thin_shapes(binary, ref, img_area, min_extent=0.0):
    """Keep only the connected shapes whose THICKEST part is thin (bars, lines, waveforms).

    Sound bars are thin whatever their layout (separate bars, a comb sharing a baseline,
    a wave). Bright parts of the artwork (a white cape, legs, clouds) contain thick regions,
    so the whole shape is rejected. `ref` = min(width, height) of the picture.
    """
    n, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
    if n <= 1:
        return binary
    dist = cv2.distanceTransform(binary, cv2.DIST_L2, 3)
    max_radius = np.zeros(n, dtype=np.float32)
    np.maximum.at(max_radius, labels.ravel(), dist.ravel())
    limit = 0.03 * ref  # inscribed radius: bars up to ~6 % of the short side thick
    keep = np.zeros(n, dtype=bool)
    for i in range(1, n):
        area = stats[i, cv2.CC_STAT_AREA]
        extent = area / max(1, stats[i, cv2.CC_STAT_WIDTH] * stats[i, cv2.CC_STAT_HEIGHT])
        if area >= max(30, 1e-4 * img_area) and max_radius[i] <= limit and area <= 0.15 * img_area and extent >= min_extent:
            keep[i] = True
    return (keep[labels] * 255).astype(np.uint8)


_reader = None


def glyph_mask(gray, poly, h_img):
    """Mask (uint8, same size as `gray`) of the letter strokes inside one OCR box.

    Letters are thin compared to the box height, so a top-hat (light strokes) or a
    black-hat (dark strokes) with a kernel a bit wider than a stroke isolates them without
    touching the smooth artwork behind. One polarity is chosen per box (white titles are by
    far the most common; using both would also select the dark gaps BETWEEN white letters),
    then the strokes are grown a little to take the outline / drop shadow with them.
    If nothing sensible is found (or nearly the whole box), the box itself is the fallback.
    """
    h, w = gray.shape
    x, y, bw, bh = cv2.boundingRect(poly)
    pad = max(2, int(bh * 0.15))
    x0, y0, x1, y1 = max(0, x - pad), max(0, y - pad), min(w, x + bw + pad), min(h, y + bh + pad)
    roi = gray[y0:y1, x0:x1]
    inside = np.zeros_like(roi, dtype=np.uint8)
    cv2.fillPoly(inside, [poly - [x0, y0]], 255)
    inner = inside > 0

    k = max(5, int(min(bh, bw) * 0.35) | 1)
    ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    light = cv2.morphologyEx(roi, cv2.MORPH_TOPHAT, ker)
    dark = cv2.morphologyEx(roi, cv2.MORPH_BLACKHAT, ker)

    def strokes(hat, polarity):
        # Thin enough (hat) AND close to the text colour (the extreme luminance of the box):
        # this keeps the lettering and drops the textured art that merely has local contrast.
        t = max(18.0, 0.4 * float(np.percentile(hat[inner], 99)))
        vals = roi[inner]
        if polarity == "light":
            near = roi >= float(np.percentile(vals, 98)) - 25
        else:
            near = roi <= float(np.percentile(vals, 2)) + 25
        return ((hat > t) & near & inner).astype(np.uint8) * 255

    s_light, s_dark = strokes(light, "light"), strokes(dark, "dark")
    white = (roi[inner] >= 225).mean()
    black = (roi[inner] <= 35).mean()
    if white >= 0.015:
        chosen = s_light
    elif black >= 0.015:
        chosen = s_dark
    else:
        chosen = s_light if s_light.sum() <= s_dark.sum() else s_dark
    r = max(2, round(bh * 0.07))
    ker_r = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
    chosen = cv2.dilate(cv2.morphologyEx(chosen, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8)), ker_r)
    chosen &= cv2.dilate(inside, ker_r)

    frac = (chosen > 0).sum() / max(inner.sum(), 1)
    out = np.zeros_like(gray, dtype=np.uint8)
    if frac < 0.03 or frac > 0.75:
        # Nothing sensible found. Erasing the whole box is acceptable for a small box, but a
        # big one would wipe real artwork (LaMa then smears it): better to leave it alone.
        if bw * bh <= 0.015 * w * h:
            cv2.fillPoly(out, [poly], 255)
    else:
        out[y0:y1, x0:x1] = chosen
    return out


def text_mask(img, conf=0.15, status=print):
    """Mask (PIL 'L') of the text found by EasyOCR (letter strokes only). Needs easyocr."""
    global _reader
    try:
        import easyocr
    except ImportError:
        raise RuntimeError(tr("need_easyocr", hint=INSTALL_HINT))
    if _reader is None:
        status(tr("loading_detector"))
        _reader = easyocr.Reader(OCR_LANGS, gpu=True, verbose=False)  # falls back to CPU by itself
    status(tr("detecting_text"))
    w, h = img.size
    rgb = np.asarray(img.convert("RGB"))
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    mask = np.zeros((h, w), dtype=np.uint8)
    found = 0
    for box, _text, score in _reader.readtext(rgb):
        pts = np.array(box, dtype=np.int32)
        # Skip weak detections (anime art is full of text-like patterns) and tiny boxes.
        if score < conf or (pts[:, 1].max() - pts[:, 1].min()) < 0.015 * h:
            continue
        mask = np.maximum(mask, glyph_mask(gray, pts, h))
        found += 1
    status(tr("text_found", n=found))
    return Image.fromarray(mask)


def grow(mask, radius=2):
    """Dilate the mask so shadows, outlines and anti-aliasing are covered too.

    `radius` is in pixels at 720p and scales with the picture (2 = about 2 px at 720p).
    Kept small on purpose: every grown pixel is real artwork that LaMa has to invent.
    """
    if np is None or cv2 is None or radius <= 0:
        return mask
    w, h = mask.size
    r = max(1, round(radius * min(w, h) / 720))
    ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
    return Image.fromarray(cv2.dilate(np.asarray(mask), ker))


# --------------------------------------------------------------------------- #
# Inpainting
# --------------------------------------------------------------------------- #

_lama = None


def _load_lama(status):
    global _lama
    if _lama is None:
        try:
            from simple_lama_inpainting import SimpleLama
        except ImportError:
            raise RuntimeError(tr("need_lama", hint=INSTALL_HINT))
        status(tr("loading_erase"))
        _lama = SimpleLama()
    return _lama


def _lama_run(lama, img_rgb, mask_l):
    return lama(Image.fromarray(img_rgb), Image.fromarray(mask_l)).convert("RGB")


def _extend(lo, hi, size, min_len):
    """Widen [lo, hi) to at least min_len inside [0, size)."""
    need = min_len - (hi - lo)
    if need > 0:
        lo, hi = lo - need // 2, hi + need - need // 2
        if lo < 0:
            lo, hi = 0, hi - lo
        if hi > size:
            lo, hi = lo - (hi - size), size
        lo = max(lo, 0)
    return lo, hi


def inpaint(img, mask, status=print):
    """Fill the masked area with LaMa, one local crop per cluster of the mask.

    LaMa works best on a few hundred pixels of context around a hole. Nearby mask pieces
    (letters of one title, bars of one visualizer) are merged into a cluster; each cluster is
    inpainted in a crop with generous context, then blended back (feathered edge) so that
    untouched pixels stay exactly as they were. Falls back to the whole picture when the
    mask is huge or made of very many pieces.
    """
    lama = _load_lama(status)
    status(tr("erasing"))
    base = np.asarray(img.convert("RGB")).copy()
    m = (np.asarray(mask.convert("L")) > 127).astype(np.uint8) * 255
    h, w = m.shape
    short = min(w, h)

    gap = max(5, round(short * 0.04))
    merged = cv2.dilate(m, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * gap + 1, 2 * gap + 1)))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(merged, connectivity=8)
    clusters = n - 1
    bx, by, bw, bh = cv2.boundingRect(cv2.findNonZero(m))
    if clusters > 40 or (clusters == 1 and bw * bh > 0.5 * w * h):
        return _lama_run(lama, base, m)

    remaining = m.copy()
    min_side = min(short, 384)
    for i in range(1, n):
        part = ((lab == i) & (m > 0)).astype(np.uint8) * 255
        if not part.any():
            continue
        x, y, cw, ch = cv2.boundingRect(cv2.findNonZero(part))
        pad = max(96, int(0.6 * max(cw, ch)))
        x0, y0, x1, y1 = max(0, x - pad), max(0, y - pad), min(w, x + cw + pad), min(h, y + ch + pad)
        x0, x1 = _extend(x0, x1, w, min_side)  # crop at least min_side wide / high
        y0, y1 = _extend(y0, y1, h, min_side)
        crop = base[y0:y1, x0:x1]
        out = np.asarray(_lama_run(lama, crop, remaining[y0:y1, x0:x1]))
        out = out[:crop.shape[0], :crop.shape[1]]
        # Feathered blend of this cluster only; the rest of `remaining` is for the other turns.
        soft = cv2.GaussianBlur(cv2.dilate(part[y0:y1, x0:x1], np.ones((3, 3), np.uint8)), (0, 0), 1.2)
        a = (soft.astype(np.float32) / 255.0)[..., None]
        base[y0:y1, x0:x1] = (crop * (1 - a) + out * a).round().astype(np.uint8)
        remaining[lab == i] = 0
    return Image.fromarray(base)


def clean_image(img, opts, status=print):
    """Apply CleanOptions to a PIL image and return the cleaned image."""
    if not opts.active:
        return img
    if np is None or cv2 is None:
        raise RuntimeError(tr("need_np_cv"))
    mask = np.zeros((img.size[1], img.size[0]), dtype=np.uint8)
    if opts.text:
        # Letter strokes only: a thin margin is enough for shadows and anti-aliasing.
        mask = np.maximum(mask, np.asarray(grow(text_mask(img, opts.ocr_conf, status), 2)))
    if opts.zone_valid:
        zm = zone_mask(img, opts.zone, opts.zone_mode, opts.bright)
        # "bright" = thin bars with glow / JPEG halo around them; "whole" is already generous.
        zm = grow(zm, 3 if opts.zone_mode == "bright" else 0)
        mask = np.maximum(mask, np.asarray(zm))
    if not mask.any():
        status(tr("nothing_erase"))
        return img
    cover = mask.mean() / 255
    if cover > 0.10:
        status(tr("mask_warn", pct=f"{cover:.0%}"))
    return inpaint(img, Image.fromarray(mask), status)