#!/usr/bin/env python3
"""
Extract Lady Bug arcade graphics from the MAME `ladybug` romset.

Decodes per MAME's ladybug.cpp gfxlayouts and palette/lookup PROMs:
  gfx1 (l9.f7 + l0.h7) -> 8x8 chars, 2bpp, 512 tiles
  gfx2 (l8.l7 + l7.m7) -> 16x16 sprites, 2bpp, 64 sprites
  proms:
    10-1.f4 -> 32-entry palette (resistor-weighted RGB)
    10-2.k1 -> char color lookup (256 entries: 64 attrs x 4 pixel-values)
    10-3.c4 -> sprite color lookup

Outputs (under --out, default assets/arcade/):
  chars_indexed.png        all 512 chars on a sheet, palette 0 applied
  sprites_indexed.png      all 64 sprites on a sheet, palette 0 applied
  chars_raw2bpp.png        raw 2bpp values (0..3) before color-lookup, x64 grey
  sprites_raw2bpp.png      same for sprites
  palette.json             32 RGB entries (0..255)
  char_lookup.json         [attr][pixval]=palette_index
  sprite_lookup.json       same for sprites
  chars.json               raw 2bpp pixel grids per tile (list of 8x8 arrays)
  sprites.json             raw 2bpp pixel grids per sprite (list of 16x16)

Run:
  python3 scripts/extract_arcade_gfx.py \
      --rom ~/mame/roms/ladybug.zip --out assets/arcade/
"""
from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    sys.exit("This script needs Pillow: pip install pillow")


# Region layout per MAME ladybug.cpp:
#   proms[0x00..0x1F] = 10-2.k1 = palette PROM (32 entries)
#   proms[0x20..0x3F] = 10-1.f4 = sprite color lookup (low+high nibble)
#   proms[0x40..0x5F] = 10-3.c4 = (unused for char/sprite color in base set)
ROM_FILES = {
    "l9.f7":   ("gfx1",       0x0000, 0x1000),
    "l0.h7":   ("gfx1",       0x1000, 0x1000),
    "l8.l7":   ("gfx2",       0x0000, 0x1000),
    "l7.m7":   ("gfx2",       0x1000, 0x1000),
    "10-2.k1": ("palette",    0,      32),
    "10-1.f4": ("sprite_lut", 0,      32),
    "10-3.c4": ("aux_lut",    0,      32),
}


def load_roms(zip_path: Path) -> dict[str, bytearray]:
    regions = {
        "gfx1": bytearray(0x2000),
        "gfx2": bytearray(0x2000),
        "palette": bytearray(32),
        "sprite_lut": bytearray(32),
        "aux_lut": bytearray(32),
    }
    with zipfile.ZipFile(zip_path) as zf:
        names = {n.lower(): n for n in zf.namelist()}
        for fname, (region, off, size) in ROM_FILES.items():
            real = names.get(fname.lower())
            if real is None:
                raise SystemExit(f"missing {fname} in {zip_path}")
            data = zf.read(real)
            if len(data) != size:
                raise SystemExit(f"{fname}: expected {size} bytes, got {len(data)}")
            regions[region][off:off + size] = data
    return regions


def decode_palette(prom: bytes) -> list[tuple[int, int, int]]:
    """
    Per MAME ladybug.cpp palette init: each PROM byte is INVERTED, then
      R = bits 0 (470Ω) + 5 (220Ω)
      G = bits 2 (470Ω) + 6 (220Ω)
      B = bits 4 (470Ω) + 7 (220Ω)
    2 bits per channel, resistor-weighted into 0..255.
    """
    def weighted(b0: int, b1: int) -> int:
        # Two resistors to Vcc (470Ω, 220Ω). Output is voltage-divider sum.
        on = b0 / 470.0 + b1 / 220.0
        total = 1.0 / 470.0 + 1.0 / 220.0
        return int(round(255.0 * on / total))

    pal: list[tuple[int, int, int]] = []
    for byte in prom:
        b = ~byte & 0xFF
        r = weighted((b >> 0) & 1, (b >> 5) & 1)
        g = weighted((b >> 2) & 1, (b >> 6) & 1)
        bl = weighted((b >> 4) & 1, (b >> 7) & 1)
        pal.append((r, g, bl))
    return pal


def decode_gfx(rom: bytes, layout: dict) -> list[list[list[int]]]:
    """
    Generic MAME gfx_layout decoder. layout fields:
      width, height, total, planes (list of bit offsets),
      xoffset (per-x bit offsets), yoffset (per-y bit offsets),
      char_bits (bits per tile, MAME's `charincrement`).
    Bit-address-to-byte: byte = addr//8, bit_in_byte = 7 - (addr%8) (MSB-first).
    Plane index p contributes (bit << p) to the pixel value.
    """
    w, h = layout["width"], layout["height"]
    total = layout["total"]
    planes = layout["planes"]
    xoff = layout["xoffset"]
    yoff = layout["yoffset"]
    stride = layout["char_bits"]
    out = []
    for ti in range(total):
        base = ti * stride
        tile = [[0] * w for _ in range(h)]
        for y in range(h):
            for x in range(w):
                px = 0
                for p, po in enumerate(planes):
                    addr = base + yoff[y] + xoff[x] + po
                    bit = (rom[addr >> 3] >> (7 - (addr & 7))) & 1
                    px |= bit << p
                tile[y][x] = px
        out.append(tile)
    return out


# MAME ladybug.cpp charlayout
CHAR_LAYOUT = {
    "width": 8, "height": 8, "total": 512,
    "planes": [0, 512 * 8 * 8],
    "xoffset": [7, 6, 5, 4, 3, 2, 1, 0],
    "yoffset": [0 * 8, 1 * 8, 2 * 8, 3 * 8, 4 * 8, 5 * 8, 6 * 8, 7 * 8],
    "char_bits": 8 * 8,
}

# MAME ladybug.cpp spritelayout (16x16). Planes packed two-bits-per-pixel,
# y rows are not contiguous - top half rows occupy upper 32 bytes in a
# reversed order, bottom half rows occupy lower 32 bytes also reversed.
SPRITE_LAYOUT = {
    "width": 16, "height": 16, "total": 128,
    "planes": [0, 1],
    "xoffset": [0, 2, 4, 6, 8, 10, 12, 14,
                8 * 16 + 0, 8 * 16 + 2, 8 * 16 + 4, 8 * 16 + 6,
                8 * 16 + 8, 8 * 16 + 10, 8 * 16 + 12, 8 * 16 + 14],
    "yoffset": [23 * 16, 22 * 16, 21 * 16, 20 * 16,
                19 * 16, 18 * 16, 17 * 16, 16 * 16,
                 7 * 16,  6 * 16,  5 * 16,  4 * 16,
                 3 * 16,  2 * 16,  1 * 16,  0 * 16],
    "char_bits": 64 * 8,
}


def char_lookup() -> list[list[int]]:
    """
    Per MAME ladybug.cpp: chars have no PROM lookup. For each pen index
    i = attr*4 + pixval (i in 0..0x1F), palette index =
      ((i << 3) & 0x18) | ((i >> 2) & 0x07).
    Returns lut[attr][pixval] -> palette index (0..31).
    """
    lut = [[0] * 4 for _ in range(8)]
    for attr in range(8):
        for pv in range(4):
            i = (attr << 2) | pv
            lut[attr][pv] = ((i << 3) & 0x18) | ((i >> 2) & 0x07)
    return lut


def _bitswap4(v: int) -> int:
    """Reverse low 4 bits: bit0<->bit3, bit1<->bit2."""
    return ((v & 1) << 3) | ((v & 2) << 1) | ((v & 4) >> 1) | ((v & 8) >> 3)


def sprite_lookup(prom: bytes, high_nibble: bool = False) -> list[list[int]]:
    """
    Per MAME ladybug.cpp: sprite pen i = attr*4 + pixval (i in 0..0x1F).
    palette index = bitswap<4>(prom[i] >> shift, 0,1,2,3) where shift=0 (set A)
    or shift=4 (set B). Each entry yields a 4-bit palette index (0..15).
    """
    shift = 4 if high_nibble else 0
    lut = [[0] * 4 for _ in range(8)]
    for attr in range(8):
        for pv in range(4):
            i = (attr << 2) | pv
            nib = (prom[i] >> shift) & 0x0F
            lut[attr][pv] = _bitswap4(nib)
    return lut


def render_sheet(tiles, tile_w, tile_h, lut_attr, palette, cols=16):
    rows = (len(tiles) + cols - 1) // cols
    img = Image.new("RGB", (cols * tile_w, rows * tile_h), (0, 0, 0))
    px = img.load()
    for i, tile in enumerate(tiles):
        ox = (i % cols) * tile_w
        oy = (i // cols) * tile_h
        for y in range(tile_h):
            for x in range(tile_w):
                pal_idx = lut_attr[tile[y][x]]
                px[ox + x, oy + y] = palette[pal_idx]
    return img


def render_raw_sheet(tiles, tile_w, tile_h, cols=16):
    rows = (len(tiles) + cols - 1) // cols
    img = Image.new("L", (cols * tile_w, rows * tile_h), 0)
    px = img.load()
    for i, tile in enumerate(tiles):
        ox = (i % cols) * tile_w
        oy = (i // cols) * tile_h
        for y in range(tile_h):
            for x in range(tile_w):
                px[ox + x, oy + y] = tile[y][x] * 85  # 0,85,170,255
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rom", required=True, help="path to ladybug.zip")
    ap.add_argument("--out", default="assets/arcade", help="output directory")
    ap.add_argument("--char-attr", type=int, default=0,
                    help="char color attr (0..7) for the indexed PNG preview")
    ap.add_argument("--sprite-attr", type=int, default=0,
                    help="sprite color attr (0..7) for the indexed PNG preview")
    args = ap.parse_args()

    rom_path = Path(args.rom).expanduser()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    regions = load_roms(rom_path)
    palette = decode_palette(bytes(regions["palette"]))
    char_lut = char_lookup()
    sprite_lut = sprite_lookup(bytes(regions["sprite_lut"]), high_nibble=False)
    sprite_lut_b = sprite_lookup(bytes(regions["sprite_lut"]), high_nibble=True)
    chars = decode_gfx(bytes(regions["gfx1"]), CHAR_LAYOUT)
    sprites = decode_gfx(bytes(regions["gfx2"]), SPRITE_LAYOUT)

    (out / "palette.json").write_text(json.dumps(palette, indent=2))
    (out / "char_lookup.json").write_text(json.dumps(char_lut, indent=2))
    (out / "sprite_lookup_a.json").write_text(json.dumps(sprite_lut, indent=2))
    (out / "sprite_lookup_b.json").write_text(json.dumps(sprite_lut_b, indent=2))
    (out / "chars.json").write_text(json.dumps(chars))
    (out / "sprites.json").write_text(json.dumps(sprites))

    for a in range(8):
        render_sheet(chars, 8, 8, char_lut[a], palette, cols=32) \
            .save(out / f"chars_attr{a}.png")
        render_sheet(sprites, 16, 16, sprite_lut[a], palette, cols=8) \
            .save(out / f"sprites_setA_attr{a}.png")
        render_sheet(sprites, 16, 16, sprite_lut_b[a], palette, cols=8) \
            .save(out / f"sprites_setB_attr{a}.png")
    render_sheet(chars, 8, 8, char_lut[args.char_attr], palette, cols=32) \
        .save(out / "chars_indexed.png")
    render_sheet(sprites, 16, 16, sprite_lut[args.sprite_attr], palette, cols=8) \
        .save(out / "sprites_indexed.png")
    render_raw_sheet(chars, 8, 8, cols=32).save(out / "chars_raw2bpp.png")
    render_raw_sheet(sprites, 16, 16, cols=8).save(out / "sprites_raw2bpp.png")

    print(f"wrote {len(chars)} chars, {len(sprites)} sprites, "
          f"{len(palette)} palette entries to {out}")


if __name__ == "__main__":
    main()
