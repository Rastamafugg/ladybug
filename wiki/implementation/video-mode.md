---
name: Video mode decision
description: Phase 2 mode-selection analysis. Picks the GIME hi-res mode, framebuffer layout, and pixel/tile/sprite formats for the rest of the project.
type: decision
tags: [video, gime, decision, phase-2]
updated: 2026-05-08
---

# Video mode — decision

**Decision (2026-05-08): 320 × 192, 16 colours, format C, single buffer.**

GIME settings: `$FF98` BP=1 GR=1, `$FF99` VRES=00 HRES=111 CRES=10. Row stride 160 bytes. Framebuffer 30 720 bytes.

This page records why, and the implications that follow. Implementation lands in Phase 2.

## Inputs to the decision

From the locked design ([game/overview.md](../game/overview.md)):

- Single non-scrolling playfield per stage.
- HUD on **side panels**: left = score / lives / level; right = `EXTRA` / `SPECIAL` letters + vegetable indicator.
- Three-colour cycle (blue / yellow / red) drives the letter / heart / vegetable subsystem; every coloured item on the playfield flips together.
- ~24×24 tile maze area is the natural scale for the playfield.
- 8-direction joystick read; constant player speed.

From the platform ([platform/gime.md](../platform/gime.md), [platform/timing.md](../platform/timing.md)):

- Frame budget at 1.78 MHz, 60 Hz: ≈ 29 666 cycles. Roadmap baseline render allocation: ≈ 18 000 cycles.
- 16 palette registers, 6-bit colour codes, freely re-loadable.
- 16-colour mode = 4 bits/pixel = 2 pixels/byte ("format C").
- Vertical Offset registers point the GIME at any 8-byte-aligned physical-page address ([platform/memory.md](../platform/memory.md)) — framebuffer can live wherever we put it.

## Mode catalogue (relevant subset)

`$FF99` HRES values vs row stride at 16-colour CRES=10 ([sources/coco3-asm-tepolt.md §"Hi-res graphics"](../sources/coco3-asm-tepolt.md)):

| HRES | bytes / row | 16-col px / row | FB at 192 rows | Notes |
|-|-|-|-|-|
| 4 | 64  | 128 | 12 288 | Chunky pixels; below arcade horizontal. |
| 5 | 80  | 160 | 15 360 | Square pixels-ish; tight HUD margins. |
| 6 | 128 | 256 | 24 576 | Closest to arcade 240 wide. |
| **7** | **160** | **320** | **30 720** | **Selected.** Standard "320×192×16" mode. |

Lower colour depths (CRES=00 mono, CRES=01 4-colour) cut the framebuffer 2-4× but force the entire palette through 2 or 4 slots, which collides with the cycle-of-three colour subsystem (we'd have one slot left for *all* static art). Skipped.

Hi-res text mode skipped — no per-pixel control, wrong shape for sprite work.

## Why 320 × 192 × 16 over 256 × 192 × 16

Both modes are technically viable. The 320-wide mode wins on three counts:

1. **HUD layout.** 320 − 192 (square maze) = 128 px = **64 px per side panel**. Comfortable room for 8-tile-wide score bands, the EXTRA / SPECIAL letter rows, and the vegetable icon. 256 − 192 = **32 px per side**: 4 tiles per panel — too tight for the design.
2. **Aspect.** 320×192 displays at 4:3 PAR ≈ 1.66:1 effective; 256×192 sits awkwardly between modes when stretched. Arcade is 5:4 portrait, so neither is "right" — we have already accepted that adaptation; pick the one with HUD room.
3. **Familiarity.** 320×192×16 is the canonical CoCo 3 graphics-mode demo target; XRoar, hardware monitors, and most CoCo 3 game ROMs assume it. Less off-the-beaten-path debugging.

The cost over 256-wide is 6 144 extra framebuffer bytes (one 8 K page extra) and ~25 % more sprite-blit work per draw. We have 512 K of RAM and a frame budget that already requires a dirty-rect strategy — neither cost changes the architecture.

## Layout

```
╔══════════ 320 px ══════════╗
║ ┌───┬───────────┬───┐      ║
║ │   │           │   │      ║
║ │ L │   MAZE    │ R │  192 ║
║ │ 64│  192×192  │ 64│   px ║
║ │   │  24×24 t. │   │      ║
║ │   │           │   │      ║
║ └───┴───────────┴───┘      ║
╚════════════════════════════╝
   left   centre        right
```

- **Centre:** 192 × 192 px = 24 × 24 tiles at 8 × 8 px. Holds maze, dots, all moving entities.
- **Left panel:** 64 × 192 px = 8 × 24 tiles. Score numerals, lives icons, level number.
- **Right panel:** 64 × 192 px = 8 × 24 tiles. EXTRA row, SPECIAL row, heart count, vegetable icon.

Tile origin in the framebuffer: byte offset = `row * 160 + col * 4` (since one 8-px-wide tile = 4 bytes in 16-colour mode). Both centre and panels are 8-px-aligned.

## Pixel / tile / sprite format

- **Pixel:** 4 bits, packed two-per-byte, hi-nibble = leftmost pixel.
- **Tile:** 8 × 8 px = 32 bytes. Stored as 8 rows of 4 bytes. Tile data lives in cartridge ROM.
- **Sprite (entity, e.g. Lady Bug):** 16 × 16 px = 128 bytes. Same packing.
- **Glyph (HUD digit, letter):** likely 8 × 8 = 32 bytes. May add a 16 × 16 large-digit set for the score; decided when the HUD lands.

A 2-byte sprite blit (`STD ,X++`) writes 4 pixels per ~6 cycles. Full 16 × 16 sprite ≈ 64 STDs ≈ 384 cycles plus address arithmetic — ballpark **~600 cycles per sprite**. With the largest expected on-screen entity count (player + 4 bugs + 1 skull + 2-3 letters/vegetables ≈ 9 sprites) the per-frame sprite cost is ~5 400 cycles — fits the 18 000-cycle render budget with room for HUD updates.

## Framebuffer placement

30 720 bytes = 3.75 × 8 KB MMU pages. Will occupy 4 contiguous physical pages, mapped where the rest of the memory layout (Phase 2 task) decides. Vertical-Offset registers `$FF9D/$FF9E` will point to the start of the first page. The framebuffer does *not* have to be MMU-mapped to be visible; the GIME reads it via expanded address. We only need it mapped when the CPU writes to it (which we'll arrange).

## Things deferred to Phase 2 implementation

1. **Exact `$FF98` value.** BP=1 (graphics), other bits TBD when we decide blink, mono, PAL, lines-per-row. Default LPR=001 / PAL=0 / MOCH=0 likely fine.
2. **Exact `$FF99` value.** VRES=00 HRES=111 CRES=10 = `%00011110` = `$1E` is the candidate; double-check against [sources/coco3-asm-tepolt.md §Hi-res graphics](../sources/coco3-asm-tepolt.md) Table 4-10 once the code is being written.
3. **Memory map.** Where in physical RAM does the framebuffer live? Where does code execute from in virtual space? Coding-architect task at the start of Phase 2.
4. **Palette load.** 16 entries × 6-bit codes. Initial palette (greens for the maze, primary RGB for the cycle, white/grey for HUD) gets a small data table. Not yet authored.
5. **Border colour.** `$FF9A` 6-bit code. Likely matches the maze background.
6. **CRES=11 blanking trick.** Tepolt notes `CRES=11` blanks the screen — useful for setting up the framebuffer without showing tearing. Use it during init.
7. **Single-buffer vs double-buffer.** Single is cheap (30 KB). Double would be 60 KB and let us draw the next frame while displaying the current one, avoiding sprite tearing — but needs an extra page set + a swap. **Default: single buffer with sprite save-restore.** Revisit at the Phase 4 (sprite) review gate if tearing is visible.

## Risks

- **Frame-budget margin is thin.** 5 400 cycles (sprites) + dirty HUD updates + AI + input + sound ≈ 17 000 cycles + IRQ overhead ≈ 17 100. Anything sloppy in the renderer eats the whole margin. Keep blits tight.
- **Sprite save-restore footprint.** Saving the background under each 16×16 sprite costs another 128 bytes copied per sprite; with 9 sprites that's 1 152 bytes/frame just for save, doubled if restore happens too. We may end up wanting a tile-aligned-blit fast path that re-blits the affected tiles from the static maze rather than per-sprite save-restore. Decide at Phase 4.
- **The stale Tepolt-source claim** (line 84) about HRES=4 byte counts contradicts the same file's mode-table at line 54. Fix the source page.

## ROM-budget update — 2026-05-08

Cart was retargeted to 32 K (Init0 b1-b0 = `11`); see [../platform/cartridge.md §"Cart size — 32 K"](../platform/cartridge.md). Sprite ROM at full 4bpp now fits comfortably (≈ 10 K of 32 K) and 2bpp+attr is no longer required up-front to fit the budget. Default sprite path: pre-converted 4bpp at build time.

## Sources

- [game/overview.md](../game/overview.md) — locked HUD layout.
- [platform/gime.md](../platform/gime.md) — Init0 / video / palette registers.
- [platform/timing.md](../platform/timing.md) — frame budget at 1.78 MHz.
- [platform/memory.md](../platform/memory.md) — MMU and physical-page layout.
- [sources/coco3-asm-tepolt.md](../sources/coco3-asm-tepolt.md) §"Hi-res graphics" — HRES / CRES tables.
- [roadmap.md](roadmap.md) §Phase 2.
