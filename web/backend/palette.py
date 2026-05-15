"""GIME palette ($FFB0-$FFBF) read + decode.

Each palette register holds a 6-bit color code. The CoCo 3 produces a different
output color for the same code depending on the monitor type (composite TV vs
RGB monitor) -- the GIME drives both outputs from the same 6-bit value.

RGB monitor decode (exact):
    bit layout = R1 G1 B1 R0 G0 B0   (bit 5 .. bit 0)
    per channel: c = (high << 1) | low   -> 0..3 -> scale to 0..255

Composite decode (approximation):
    bits 5..4 = luma (0..3), bits 3..0 = chroma phase (0..15).
    Phase 0 and phase 15 are grayscale; the other 14 phases sample a hue wheel.
    We approximate via the standard YIQ -> RGB conversion. For arcade-accurate
    composite hues see wiki/backlog/rgb-tv-input-palette.md -- the long-term
    plan is to switch XRoar to RGB output and derive an empirical table.

Source: docs/reference/Assembly Language Programming for the CoCo3.md ch. 2;
        wiki/platform/gime.md.
"""
from __future__ import annotations
import math

PALETTE_BASE = 0xFFB0
PALETTE_LEN = 16


def decode_rgb_monitor(code: int) -> tuple[int, int, int]:
    code &= 0x3F
    r_hi = (code >> 5) & 1
    g_hi = (code >> 4) & 1
    b_hi = (code >> 3) & 1
    r_lo = (code >> 2) & 1
    g_lo = (code >> 1) & 1
    b_lo = (code >> 0) & 1
    r = (r_hi << 1) | r_lo
    g = (g_hi << 1) | g_lo
    b = (b_hi << 1) | b_lo
    scale = [0, 85, 170, 255]
    return scale[r], scale[g], scale[b]


def decode_composite(code: int) -> tuple[int, int, int]:
    code &= 0x3F
    luma = (code >> 4) & 0x3
    phase = code & 0x0F
    y = luma / 3.0
    if phase == 0:
        # Phase 0 == pure luma (grayscale).
        v = int(round(y * 255))
        return v, v, v
    # Phase 1..15 spread evenly around the color wheel; phase 15 leans
    # toward white at high luma in real hardware, but the simple cosine
    # model below is close enough for a first-cut decode.
    angle = 2.0 * math.pi * (phase - 1) / 15.0
    # Chroma amplitude is reduced at the luma extremes (NTSC behavior).
    chroma = 0.5 * (1.0 - abs(2.0 * y - 1.0))
    i = chroma * math.cos(angle)
    q = chroma * math.sin(angle)
    r = y + 0.956 * i + 0.621 * q
    g = y - 0.272 * i - 0.647 * q
    b = y - 1.106 * i + 1.703 * q
    return (
        max(0, min(255, int(round(r * 255)))),
        max(0, min(255, int(round(g * 255)))),
        max(0, min(255, int(round(b * 255)))),
    )


def decode_all(raw: bytes) -> dict:
    if len(raw) != PALETTE_LEN:
        raise ValueError(f"expected {PALETTE_LEN} palette bytes, got {len(raw)}")
    return {
        "raw": [b & 0x3F for b in raw],
        "rgb_monitor": [list(decode_rgb_monitor(b)) for b in raw],
        "composite": [list(decode_composite(b)) for b in raw],
    }
