---
type: source
tags: [arcade, graphics, mame, palette, sprites]
updated: 2026-05-08
---

# Arcade graphics extraction

Pipeline for pulling pixel-precise tile/sprite data and the authoritative palette from the original Lady Bug arcade ROM, decoded via the MAME `ladybug` driver's gfx layouts and palette PROMs.

## Why ROM extraction, not screenshots

A screenshot is the arcade's pixel data after scaling, filtering, and image compression. The ROM stores the *exact* original bytes: tile/sprite shapes as planar pixel data, colors as resistor-network palette values. Extracting from ROM gives indexed pixel grids that map cleanly onto whatever target palette the CoCo 3 port uses.

## Pipeline

`scripts/extract_arcade_gfx.py` reads `~/mame/roms/ladybug.zip` and writes to `assets/arcade/`:

- `chars.json` / `sprites.json` — raw 2bpp pixel grids (512 × 8×8 chars, 128 × 16×16 sprites). **Authoritative shape data.**
- `palette.json` — 32 RGB triples, decoded from PROM `10-2.k1`.
- `char_lookup.json` — char `lut[attr][pixval] -> palette index`, computed by formula (no PROM).
- `sprite_lookup_a.json` / `sprite_lookup_b.json` — sprite `lut[attr][pixval] -> palette index` for the two sprite color sets.
- `chars_attr0..7.png`, `sprites_setA_attr0..7.png`, `sprites_setB_attr0..7.png` — colorized sheet previews.
- `chars_raw2bpp.png`, `sprites_raw2bpp.png` — greyscale raw-pixval sheets for shape verification.

Run: `python3 scripts/extract_arcade_gfx.py --rom ~/mame/roms/ladybug.zip --out assets/arcade/`

## Observed correspondences

- **Maze / playfield / HUD text** comes from `chars_attr0.png` (and other char attrs for variant colorings).
- **Enemies** (skull, varieties of ladybug-shaped bugs) each render in one of the Set A attrs.
- **Vegetable pickups** also use Set A attrs.
- **Death animation** (angel wings) uses one of the Set B attrs.

## Gotchas (lessons learned)

These each cost an iteration; record so we don't repeat them:

1. **Palette PROM is `10-2.k1`, not `10-1.f4`.** The MAME ROM list orders files alphabetically by chip name, but the proms region offsets put `10-2.k1` at offset 0 (palette) and `10-1.f4` at offset 0x20 (sprite color lookup). Filename ≠ region role.
2. **Char "color lookup" is a formula, not a PROM.** MAME computes `palette_idx = ((i << 3) & 0x18) | ((i >> 2) & 0x07)` for `i = attr*4 + pixval`. No PROM read involved.
3. **Sprite color lookup uses both nibbles of `10-1.f4`.** Low nibble (bitswapped) → set A pens; high nibble → set B pens. Two sprite color sets exist on real hardware; both must be exposed for accurate sprite coloring.
4. **Palette PROM bit layout is inverted and 2-bit-per-channel:** byte is `~`-flipped, then R = bits {0, 5}, G = bits {2, 6}, B = bits {4, 7}, with 470Ω/220Ω resistor weights.
5. **MAME `gfx_layout` plane ordering convention is MSB-first.** `planes: { 1, 0 }` in the source means `planes[0]=1` is the *MSB* plane of the resulting pixval, not the LSB. Getting this backwards swaps pixel values 1↔2 (visible as red↔green in attr 0).
6. **Sprite layout has scrambled y-row offsets.** 16×16 sprites are 64 bytes total: top-half rows live in bytes 32..47 in *reverse* y order, bottom-half rows in bytes 0..15 in reverse y order. Pixel x coords step by 2 bits within bytes (planes packed two-bits-per-pixel). Don't try to reason about it; encode the `xoffset`/`yoffset` arrays verbatim from MAME.
7. **Char layout is straightforward.** 8×8 chars, 8 bytes per char per plane, plane 0 in first 0x1000 of `gfx1`, plane 1 in second 0x1000. MSB = leftmost pixel.

## Sources

- MAME `ladybug.cpp` driver: <https://github.com/mamedev/mame/blob/master/src/mame/universal/ladybug.cpp>
  - `charlayout` and `spritelayout` gfx_layouts
  - `ladybug_palette()` — PROM bit weights, lookup-table computation
- ROM set: `ladybug.zip` (gfx ROMs `l9.f7`, `l0.h7`, `l8.l7`, `l7.m7`; PROMs `10-1.f4`, `10-2.k1`, `10-3.c4`)
- Extraction script: `scripts/extract_arcade_gfx.py`
- Decoded outputs: `assets/arcade/`
