"""
Save a finished result in the format the user picked.

The upscale / wallpaper jobs first write a lossless PNG into a temporary folder so the
result can be previewed (before / after slider) BEFORE anything is saved. When the user
clicks "Download", this module writes that temporary file to the chosen destination,
with the same quality settings as upscale.upscale_image.
"""

import shutil
from pathlib import Path

from PIL import Image

from config import WEBP_MAX_SIDE
from i18n import tr

Image.MAX_IMAGE_PIXELS = None  # results can be huge; same setting as upscale.py


def export_image(src, dst):
    """Write the temporary PNG `src` to `dst`; the format follows dst's extension.

    PNG is a plain file copy (no re-encoding). .jpg/.jpeg and .webp use quality 95.
    Raises RuntimeError for a WebP image beyond the format's size limit.
    """
    src, dst = Path(src), Path(dst)
    suffix = dst.suffix.lower()
    if suffix == ".png":
        shutil.copyfile(src, dst)
        return
    with Image.open(src) as im:
        im.load()
        if suffix == ".webp" and max(im.size) > WEBP_MAX_SIDE:
            raise RuntimeError(tr("webp_limit_export", n=WEBP_MAX_SIDE))
        if suffix in (".jpg", ".jpeg"):
            im.convert("RGB").save(dst, quality=95, subsampling=0)
        elif suffix == ".webp":
            im.save(dst, quality=95, method=6)
        else:
            im.save(dst)
