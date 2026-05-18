"""Render an XRoar framebuffer snapshot to PNG bytes.

v0 supports CoCo 3 hi-res 320x192x16 only (CRES=10 HRES=111 VRES=00).
Each FB byte holds two 4-bit palette indices — high nibble = left
pixel, low nibble = right pixel. Other modes return a placeholder PNG
whose text reports the rejected mode/resolution/depth.

The render path is pure-Python + Pillow: a precomputed 256-entry lookup
of (left_rgb, right_rgb) pairs collapses the per-byte decode to two
6-byte memcpys; one pass over the ~30 KB FB produces the RGB buffer
that Pillow encodes to PNG. ~ms-range cost on commodity hardware.
"""
from __future__ import annotations
import io

from PIL import Image, ImageDraw

from .gime_state import VideoState, is_supported


def placeholder_png(text: str = "no framebuffer yet") -> bytes:
    img = Image.new("RGB", (320, 192), (16, 16, 24))
    d = ImageDraw.Draw(img)
    d.text((8, 8), text, fill=(180, 180, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _unsupported_text(state: VideoState) -> str:
    m = state.mode
    return (f"Unsupported mode: CRES={m.cres} HRES={m.hres} VRES={m.vres} "
            f"BP={int(m.bp)} COCO={int(m.coco)}")


def render(state: VideoState, fb_bytes: bytes) -> bytes:
    """Render fb_bytes through state.palette_rgb to a PNG. v0: 320x192x16."""
    if not is_supported(state.mode):
        return placeholder_png(_unsupported_text(state))

    m = state.mode
    expected = m.bytes_per_row * m.height
    if len(fb_bytes) < expected:
        return placeholder_png(
            f"short FB read: got {len(fb_bytes)} bytes, need {expected}"
        )

    # Precompute the 256-entry decode table once per render. Each entry
    # is the concatenation of the two RGB triples — six bytes — ready
    # for direct bytearray slicing.
    palette = state.palette_rgb
    lookup = bytearray(256 * 6)
    for byte_val in range(256):
        lr, lg, lb = palette[(byte_val >> 4) & 0x0F]
        rr, rg, rb = palette[byte_val & 0x0F]
        off = byte_val * 6
        lookup[off + 0] = lr
        lookup[off + 1] = lg
        lookup[off + 2] = lb
        lookup[off + 3] = rr
        lookup[off + 4] = rg
        lookup[off + 5] = rb

    rgb = bytearray(m.width * m.height * 3)
    out = 0
    for byte_val in fb_bytes[:expected]:
        off = byte_val * 6
        rgb[out:out + 6] = lookup[off:off + 6]
        out += 6

    img = Image.frombytes("RGB", (m.width, m.height), bytes(rgb))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
