---
name: Memory map
description: Physical-page allocation, virtual MMU layout, cart ROM image structure, and the boot data-copy procedure. Phase 2 base; Phase 4 will refine the data-table half once sprite count is concrete.
type: design
tags: [memory, mmu, par, cart, boot, phase-2]
updated: 2026-05-08
---

# Memory map

## Constraints recap

- **8 MMU PARs**, each maps an 8 K virtual page to a 6-bit physical-page number ([platform/memory.md](../platform/memory.md), [platform/gime.md](../platform/gime.md)).
- **64 physical pages** of RAM on a 512 K machine, numbered `$00-$3F`. RAM is populated top-down — `$3F` is highest.
- **Framebuffer** = 30 720 bytes = 4 pages (3.75 actually used). GIME reads it via physical address, bypassing the MMU.
- **Code** lives in cart ROM at virtual `$C000-$FEFF` initially. After self-copy + all-RAM, it's RAM at phys `$3E-$3F`.
- **Cart data tables** (lower 16 K of the 32 K cart) live at virtual `$8000-$BFFF` in 32 K cart mode. After self-copy + all-RAM, they're RAM at phys `$3C-$3D`.
- **`$FF00-$FFFF` is dedicated I/O**, not cart-visible. **`$FE00-$FEFF` is forced** to phys `$3F` regardless of PAR7 when Init0 b3 is set ([platform/memory.md §quirks](../platform/memory.md)) — the primary jump table stays reachable.

## Page-budget arithmetic

What we want simultaneously mapped after boot:

| Use | Pages | Why |
|-|-|-|
| Low RAM (system, DP, stack, scratch) | 1 | Always-on; DP at `$0200`, stack near `$1FFE`. |
| Framebuffer | 4 | Need CPU write access while drawing. Could be 1 with a sliding window, but per-blit PAR juggling adds renderer cost. |
| Game-state RAM | 1 | Entity tables, score, frame counters, input state — Phase 4+ stuff that doesn't fit in low RAM. |
| Data tables (sprites, tiles, font, maze, palette) | 1-2 | 16 K of cart data ends up here. |
| Code | 1-2 | 16 K of cart code ends up here. |
| **Total wanted** | **8-10** | |

**8 PARs is tight; 9 wanted is one over.** This problem doesn't bite until Phase 4 when sprite data is loaded. Phase 2 mapping has spare slots.

## Phase 2 mapping (current target)

```
Virtual          PAR  Phys  Bytes  Use
$0000-$1FFF      0    $38   8 K    Low RAM (DP, stack, scratch)
$2000-$3FFF      1    $30   8 K    Framebuffer page 0
$4000-$5FFF      2    $31   8 K    Framebuffer page 1
$6000-$7FFF      3    $32   8 K    Framebuffer page 2
$8000-$9FFF      4    $33   8 K    Framebuffer page 3
$A000-$BFFF      5    $34   8 K    Reserved — game state from Phase 4+
$C000-$DFFF      6    $3E   8 K    Code (lower half)
$E000-$FFFF      7    $3F   8 K    Code (upper half) + jump table at $FE00 + I/O at $FF00
```

GIME `$FF9D/$FF9E` (vertical-offset) points at physical address of phys page `$30` = `$30 << 13 = $060000`. So the framebuffer's first byte is physical `$060000`. The CPU writes to the FB through virtual `$2000-$9FFF`, accessing the same physical bytes through the MMU.

`$9800-$9FFF` is the 2 K of slack at the end of FB page 3 (192 rows × 160 bytes/row = 30 720 = `$7800`; FB occupies virtual `$2000-$97FF`). Free for use as scratch / sprite save-restore buffer.

## Cart ROM image (32 K)

```
file offset   virtual          purpose
$0000-$3FFF   $8000-$BFFF      DATA SECTION — gfx, palette, font, maze, sound
$4000-$7EFF   $C000-$FEFF      CODE SECTION — autostart magic, entry, code, more data
              $FF00-$FFFF      (not in cart — dedicated I/O)
$7F00-$7FFF   (file padding)   $FF bytes; never read by hardware
```

The lwasm source uses two `org` blocks:

```asm
        org     $8000           ; data section
        ; INCLUDEBIN tile_gfx, sprite_gfx, palette, font, maze, ...

        org     $C000
        fcc     "DK"            ; autostart magic (BASIC FIRQ -> $C002)
        ; entry, code, ...
```

Build script pads the resulting raw output to 32768 bytes ([scripts/build.sh](../../scripts/build.sh)).

## Boot data-copy procedure

Goal: get cart ROM contents into RAM at the same physical pages, so all-RAM mode is transparent.

The CoCo 3 has **shadow RAM** at physical `$3C-$3F` even when those pages are sourced from ROM (TY=0): writes go to the RAM, reads come from ROM. This is what BASIC's reset-init relies on to seed the `$FExx` jump table before going all-RAM, and what we use here. Confirm against Tepolt CoCo 3 §3 / §7 at code time — flagged as an assumption to validate.

Sequence:

```
1. (Cart entered at $C002, ORCC #$50, LDS #$7FFE — Phase 1 already does this.)

2. Switch Init0 to enable 32 K cart mode (b1-b0 = 11). Cart's lower 16 K
   appears at $8000-$BFFF. (BASIC's ROM at $8000-$BFFF disappears.)

3. Self-copy $8000-$FEFF:
        ldx     #$8000
   loop ldd     ,x
        std     ,x
        leax    2,x
        cmpx    #$FF00
        blt     loop
   Reads come from cart ROM; writes go to RAM at physical $3C-$3F.

4. Switch TY = 1 (write $FFDF). Cart hardware disconnects.
   Virtual $8000-$FEFF now reads RAM at phys $3C-$3F — the data we just
   wrote. Code at $C000-$FEFF continues to execute, oblivious to the swap.

5. (Phase 2 continues: configure GIME video mode, load palette, render.)
```

Approximate cost: ~28 K bytes copied two-at-a-time = ~14 K iterations × ~10 cycles ≈ 140 K cycles ≈ 80 ms at 1.78 MHz. Boot-time-only, never observed by the player.

## Phase 4 problem: sprite data won't fit in 1 PAR

Sprite ROM at full 4bpp: ~120 sprites × 128 B = 15 K. Doesn't fit in the 8 K window we've reserved for data tables (PAR5 in the post-Phase-4 layout, when game state takes a slot).

Resolution options, in increasing cost — **decide at Phase 4**:

1. **Compress sprites to 2bpp + per-sprite attribute byte.** Halves to ~7.5 K, fits in one PAR. Inline expand during blit (~30 % cost). Closest to arcade hardware's native layout.
2. **Bank-switch the sprite PAR.** Map phys `$34` for "common" sprites, phys `$35` for "rare" sprites; switch PAR5 between the two as needed. ~10 cycles per switch.
3. **Drop one FB page, use a sliding write window.** Free one PAR for sprite data; renderer gets more complex.
4. **Move some code out of `$E000-$FFFF`** (currently using it for code). Free PAR7 for data; code lives only in `$C000-$DFFF` (8 K). Tight but might suffice.

Default plan: **(1) sprite compression**, since it also matches the arcade source data shape we already have ([sources/arcade-gfx-extraction.md](../sources/arcade-gfx-extraction.md)). Switch to (2) only if profiling shows the inline expansion is costing too many cycles.

## Direct-page allocation (`$0200-$02FF`)

Holding a page at `$02xx` for hot variables (set 2026-05-08, [coding-conventions.md §1](coding-conventions.md)). Current allocation:

| Offset | Variable | Width | Owner |
|-|-|-|-|
| `$00` | `FRAMES` | u16 | Phase 1 frame counter |
| `$02` | (free) | | Phase 2+ |

Plenty of room. Maintain this table as variables land.

## Stack

Top of stack at `$1FFE` (in PAR0, phys `$38`). Grows down. Max realistic depth a few hundred bytes — interrupts push 12 (IRQ) or 3 (FIRQ) bytes plus whatever the handler reserves. 6 K of stack space is excessive but harmless.

## Open items

1. **Validate shadow-RAM-during-write assumption** at first Phase 2 implementation — read after writing during a test boot, confirm RAM holds expected values once TY=1.
2. **Confirm Init0 b1-b0=11 boot sequence on XRoar** — does XRoar correctly map a 32 K cart image at `$8000-$FEFF` once Init0 is set, given the file is supplied as `-cart-rom`? Test at first Phase 2 boot.
3. **Phase 4 sprite-data resolution** — see options above.
4. **Game-state PAR (`$A000-$BFFF`) layout** — entity tables, score, etc. Defer until Phase 4 when entity records are designed.

## Sources

- [platform/memory.md](../platform/memory.md) — virtual/physical, PARs, ROM/RAM modes.
- [platform/gime.md](../platform/gime.md) — Init0 register catalog, MMU enable bit, jump-table forcing.
- [platform/cartridge.md](../platform/cartridge.md) — boot handshake, 32 K cart mode, staged Init0 transition.
- [video-mode.md](video-mode.md) — 320×192×16 framebuffer chosen.
- [sources/coco3-asm-tepolt.md](../sources/coco3-asm-tepolt.md) — to verify shadow-RAM-during-write semantics.
- [roadmap.md](roadmap.md) — Phase 2 + Phase 4 review-gate questions.
