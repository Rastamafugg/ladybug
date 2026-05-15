---
name: Memory map
description: Physical-page allocation, virtual MMU layout, cart ROM image structure, and the boot data-copy procedure. Phase 2 base; Phase 4 will refine the data-table half once sprite count is concrete.
type: design
tags: [memory, mmu, par, cart, boot, phase-2]
updated: 2026-05-15
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

## Cart ROM image (16 K)

```
file offset   virtual          purpose
$0000-$3EFF   $C000-$FEFF      autostart magic, entry, code, all data tables
              $FF00-$FFFF      (not in cart — dedicated I/O)
$3F00-$3FFF   (file padding)   $FF bytes; never read by hardware
```

The lwasm source uses a single `org` block:

```asm
        org     $C000
        fcc     "DK"            ; autostart magic (BASIC FIRQ -> $C002)
        ; entry, code, data tables, ...
```

Build script pads the resulting raw output to 16384 bytes ([scripts/build.sh](../../scripts/build.sh)).

If 16 K becomes insufficient, expansion options are documented in [../platform/cartridge.md §"Cart size — 16 K (current)"](../platform/cartridge.md). The pivot is local to the boot data-copy step below — runtime is unaffected because it runs from RAM.

## Boot data-copy procedure

Goal (on real hardware): get cart ROM contents into RAM at the same physical pages, so all-RAM mode is transparent.

The CoCo 3 has **shadow RAM** at physical `$3C-$3F` even when those pages are sourced from ROM (TY=0): writes go to the RAM, reads come from ROM. The boot self-copy depends on that semantic. The Phase 2.1 "wrote `$5A` to `$C000`, flipped TY=1, read it back" test passed under XRoar, but see the **important caveat** below — that test result is consistent with both "shadow-RAM-during-write works" AND with "XRoar serves cart bytes through the cart-window read path regardless of TY". The two are indistinguishable from CPU-visible behavior alone.

### ⚠️ Important: under XRoar 1.10 the self-copy is a no-op

Empirically established 2026-05-14 (four-pass gdb-mcp investigation, see [backlog/cart-ram-corruption.md](../backlog/cart-ram-corruption.md)). Under XRoar 1.10's GIME emulation:

- Pre-SAM_ALLRAM (MC3=1, MMUEN=0, TY=0), the GIME's address decoder routes `$C000-$FDFF` through `S=1`/CTS (cart ROM) with **RAS=0**. `coco3.c read_byte`'s `if (RAS)` RAM-overlay block is skipped → reads return cart-ROM bytes. `coco3.c write_byte` calls `cart_rom_write` (read-only no-op) and likewise skips the RAS RAM-write block → writes go nowhere. **`std ,x` in the self-copy loop neither populates RAM nor errors.**
- Post-SAM_ALLRAM (TY=1), reads at `$C000-$FDFF` still come back as cart bytes. The exact code path was not pinned down (source-review gap acknowledged at [log.md 2026-05-14](../log.md)), but the empirical fact stands: cart bytes are accessible at `$C000-$FDFF` throughout the boot, pre- and post-SAM_ALLRAM, with or without the self-copy.
- `$FE00-$FEFF` is different: MC3=1 forces RAS=1 in the inner decode, so reads/writes hit bank 0 RAM symmetrically. The jump-table region IS RAM-backed.

**Net:** on XRoar, execution at `$C000-$FDFF` is always from cart ROM. The self-copy is dead code. On real hardware, the self-copy is expected to work as originally designed — but that's unverified until hardware bring-up (Phase 10).

### Implications for code that assumes RAM-shadowing

- **Self-modifying code** at `$C000-$FDFF` will silently fail on XRoar (writes don't land; subsequent reads return the original cart byte).
- **Runtime data tables** at `$C000-$FDFF` are read-only on XRoar. The jump table at `$FE00-$FEFF` is the only RAM-backed window inside the cart range under emulation.
- **Game-state RAM at `$A000-$BFFF`** is below the cart window; once PAR5 maps it to a normal phys page, ordinary read/write works on both XRoar and hardware.
- **The `org $C0DC` workaround** for [the XRoar bad-window quirk](lessons-learned.md#xroar-cartridge-window-reads-are-not-uniformly-cart-backed) was originally rationalized against a RAM-shadow model. Since we're actually executing from cart ROM in XRoar, the workaround is still correct (those addresses really do read garbage from cart space), but the *reasoning* in our heads needs updating.

Sequence:

```
1. (Cart entered at $C002, ORCC #$50, LDS, DP setup — Phase 1 base.)

2. Self-copy $C000-$FEFF:
        ldx     #$C000
   loop ldd     ,x
        std     ,x
        leax    2,x
        cmpx    #$FF00
        blo     loop
   Reads come from cart ROM; writes go to RAM at physical $3E-$3F.

3. Switch TY = 1 (write $FFDF). Cart hardware disconnects.
   Virtual $C000-$FEFF now reads RAM at phys $3E-$3F — the same bytes we
   just wrote. Code continues to execute, oblivious to the swap.

4. (Phase 2 continues: configure GIME hi-res mode, MMU + PARs, palette,
   framebuffer clear, render.)
```

Approximate cost: 16 K bytes copied two-at-a-time = ~8 K iterations × ~10 cycles ≈ 80 K cycles ≈ 45 ms at 1.78 MHz. Boot-time-only, never observed by the player.

## Phase 4 problem: sprite ROM at full 4bpp likely doesn't fit in 16 K cart

Sprite ROM at full 4bpp: ~120 sprites × 128 B = 15 K. Plus tile gfx (~1.6 K), font (~3 K), code (~6-8 K), maze (~1 K), palette (~0.5 K), sound (~1-3 K) ≈ 28-31 K total — overflows the 16 K cart window. **Decide at the Phase 4 review gate** against measured numbers:

1. **Compress sprites to 2bpp + per-sprite attribute byte** — halves sprite ROM to ~7.5 K. Inline expand during blit (~30 % cost). Closest to arcade hardware's native layout. **Default plan.**
2. **Curate the sprite set** — drop direction-flip frames; mirror at blit time. Probably reduces 120 → 60-80 frames.
3. **Pivot to a software bank-switched cart** — see [../platform/cartridge.md §"Cart size — 16 K (current)"](../platform/cartridge.md). Universal hardware support; ~half-day refactor; touches only the boot data-copy phase.

Once a cart holds enough data, the in-RAM data layout still has the same constraint: 8 PARs vs 8-10 wanted (1 system + 4 FB + 1 game state + 2 data + 2 code). Resolution options for *that*, in increasing cost:

a. **Bank-switch the data PAR** — map phys `$34` for "common" sprites, phys `$35` for "rare"; switch PAR5 between as needed. ~10 cycles per switch.
b. **Drop one FB page, use a sliding write window** — frees one PAR for data; renderer gets more complex.
c. **Move some code out of `$E000-$FFFF`** — frees PAR7. Code lives only in `$C000-$DFFF` (8 K). Tight.

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

1. **Shadow-RAM-during-write** — partially verified. Phase 2.1 sentinel test passed under XRoar but is not discriminating (see caveat above). The self-copy itself is empirically a no-op on XRoar 1.10. **Hardware verification deferred to Phase 10.**
2. **XRoar's handling of 32 K cart files** — observed inconsistent with naive `$8000-$FEFF` mapping; deferred until/unless we need the larger cart. See [../tooling/xroar.md "Gotchas"](../tooling/xroar.md).
3. **Phase 4 sprite-data resolution** — see Phase 4 problem section above.
4. **Game-state PAR (`$A000-$BFFF`) layout** — entity tables, score, etc. Defer until Phase 4 when entity records are designed.
5. **XRoar source-review gap** — `tcc1014.c` decode trace predicts certain `$E000+` reads should return cart padding (`$FF`) but they empirically return SECB-style bytes. There is a path through `coco3.c read_byte` we haven't fully reconstructed. Not blocking, but it means we can't reason confidently about exact GIME state from source review alone; trust empirical probes. See [backlog/cart-ram-corruption.md](../backlog/cart-ram-corruption.md).

## Sources

- [platform/memory.md](../platform/memory.md) — virtual/physical, PARs, ROM/RAM modes.
- [platform/gime.md](../platform/gime.md) — Init0 register catalog, MMU enable bit, jump-table forcing.
- [platform/cartridge.md](../platform/cartridge.md) — boot handshake, 32 K cart mode, staged Init0 transition.
- [video-mode.md](video-mode.md) — 320×192×16 framebuffer chosen.
- [sources/coco3-asm-tepolt.md](../sources/coco3-asm-tepolt.md) — to verify shadow-RAM-during-write semantics.
- [roadmap.md](roadmap.md) — Phase 2 + Phase 4 review-gate questions.
