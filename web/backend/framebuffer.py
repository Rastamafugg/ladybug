"""Render the GIME framebuffer to a PNG by reading FB RAM + palette + mode regs.

TODO: implement. For Ladybug's chosen mode (320x192x16) the pipeline is:
    1. Read GIME video mode regs to confirm resolution + bpp.
    2. Read the 16-entry palette at $FFB0-$FFBF.
    3. Read FB RAM at the address indicated by the MMU + V-PAR.
    4. Decode 4-bpp packed pixels through the palette.
    5. Encode PNG with Pillow.

For now this returns a placeholder PNG so the frontend canvas has something
to display.
"""
from __future__ import annotations
import io
from PIL import Image, ImageDraw


def placeholder_png(text: str = "no framebuffer yet") -> bytes:
    img = Image.new("RGB", (320, 192), (16, 16, 24))
    d = ImageDraw.Draw(img)
    d.text((8, 8), text, fill=(180, 180, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
