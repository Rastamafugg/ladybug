---
name: Cartridge connector & boot
description: 40-pin cartridge edge pinout, the CART → PIA2 CB1 → FIRQ auto-start path, and how Ladybug as a ROM cartridge takes control on power-on.
type: concept
tags: [cartridge, boot, firq, hardware]
updated: 2026-05-07
---

# Cartridge connector

40-pin edge on the right side of the CoCo 3. Pinout (top row odd, bottom row even, viewed from outside the machine — Tepolt Fig. 10-8):

| Pin | Signal | Pin | Signal |
|-|-|-|-|
| 1  | -12 V (CoCo 1 only) | 2  | +12 V |
| 3  | HALT (in)            | 4  | NMI (in) |
| 5  | RESET (out)          | 6  | E clock (out) |
| 7  | Q clock (out)        | 8  | CART (in → PIA2 CB1, FIRQ source) |
| 9  | +5 V (≤300 mA)       | 10 | D0 |
| 11 | D1                   | 12 | D2 |
| 13 | D3                   | 14 | D4 |
| 15 | D5                   | 16 | D6 |
| 17 | D7                   | 18 | R/W̅ |
| 19 | A0                   | 20 | A1 |
| 21 | A2                   | 22 | A3 |
| 23 | A4                   | 24 | A5 |
| 25 | A6                   | 26 | A7 |
| 27 | A8                   | 28 | A9 |
| 29 | A10                  | 30 | A11 |
| 31 | A12                  | 32 | CTS (out, low when MPU accesses `$C000-$FEFF` w/ TY=0) |
| 33 | GND                  | 34 | GND |
| 35 | SND (analog audio in) | 36 | SCS (out, low when MPU accesses `$FF40-$FF5F`) |
| 37 | A13                  | 38 | A14 |
| 39 | A15                  | 40 | SLENB (in, low inhibits SAM/GIME decoding) |

## Boot handshake

1. Cartridge is inserted. The cart's upper 16 K occupies `$C000-$FEFF` while TY=0 (default Init0 ROM map = `0x` = 16 K BASIC + 16 K cart).
2. Hardware reset: PIAs cleared, PC ← `[$FFFE/$FFFF]` = `$8C1B`, BASIC reset-init runs.
3. The reset-init configures PIA2 CB1 to detect the CART line going low and to generate a FIRQ.
4. CART pin is asserted low by the cartridge electronics.
5. FIRQ fires → BASIC's FIRQ handler examines the first three bytes at `$C000`. If they are `"DK"` (the ROM-pack autostart magic) followed by enough additional setup, control jumps to `$C002`/`$C003`.

The simpler convention used by single-purpose game cartridges is to put a `JMP entry` instruction at `$C000` and let the BASIC FIRQ handler dispatch into it. We will use that path. **Verified Phase 0** — `FCC "DK"` followed by entry code at `$C002` works as written under XRoar with `-cart-autorun`.

## Cart size — 16 K (current); 32 K and bank-switched options deferred

**Decision (2026-05-08, revised same day): 16 K cartridge for development.**

Initially retargeted to 32 K (Init0 b1-b0 = `11`) when ROM-budget analysis suggested 4bpp sprite data would push past 16 K, but reverted after Phase 2.1 testing showed XRoar's `-cart-rom` handling of 32 K files is unverified — `-cart-rom` is documented only as "mapped from `$C000`" and our experimental 32 K cart didn't autostart, consistent with XRoar truncating to the lower 16 K of the file. Rather than detour into XRoar source-code investigation or XRoar `-cart-type gmc` rework now, we proceed at 16 K until we have real ROM-size numbers.

**The expansion path is documented and held in reserve:**

- **32 K via Init0 b1-b0 = `11`.** GIME-native 32 K cart mode. Cart visible at `$8000-$FEFF` after our boot enables it. Requires (a) cart hardware that decodes the wider range, and (b) emulator support that we haven't confirmed. Validate at Phase 4 if needed.
- **Software bank-switched cart.** Two or more 16 K banks of ROM, standard `$C000-$FEFF` window. Software writes a bank-select register to swap. Universally supported (XRoar `-cart-type gmc`, CoCoSDC, multi-pak, custom hardware). ~half-day refactor — touches only the boot data-copy phase, since runtime is all-RAM regardless. Default fallback if/when 16 K is insufficient.

**Trigger for the pivot:** Phase 4 sprite-arithmetic gate, when `120 sprites × 128 B at 4bpp` (or compressed equivalent) plus code, tiles, font, palette, maze, and sound is measured against 16 K. Earlier if a phase shows obvious slack overflow. The pivot is documented as ~half-day work because the boot's data-copy phase is the only place cart layout matters — runtime sees RAM only.

**Cart layout in the 16 K image:**

```
file offset   virtual    purpose
$0000-$3EFF   $C000-$FEFF   "DK" magic, entry, code, all data tables
              $FF00-$FFFF   not in cart (dedicated I/O / vectors)
```

Cart hardware: standard 16 K EPROM cart shell. CoCoSDC and similar work natively. The ~256 bytes at `$FF00-$FFFF` aren't cart-visible (dedicated I/O), so the file's last 256 bytes are wasted but harmless.

## What our boot must do

Once we have control at `$C002`:

1. `ORCC #$50` — mask IRQ and FIRQ.
2. Set `S` to the top of our work RAM.
3. Disable PIA-driven interrupts and bleed any pending flags.
4. Configure GIME Init0: clear bit 7 (hi-res), enable MMU, set bit 3 so `$FE00-$FEFF` is always reachable, set bit 5 to enable ACVC IRQs. Then clear/blank the screen buffer with CRES=11 while we initialise.
5. Self-copy `$C000-$FEFF` to shadow RAM beneath the cart (verified 2026-05-08 — see [implementation/memory-map.md](../implementation/memory-map.md) §"Boot data-copy procedure").
6. Switch to all-RAM mode (write to `$FFDF`). Cart ROM disconnects; phys `$3E-$3F` is now the RAM we just wrote.
7. Switch to fast clock (write to `$FFD9`).
8. Load our palette (`$FFB0-$FFBF`).
9. Install our IRQ handler in the primary jump table at `$FEF7` (`JMP` extended), write `$FF92` bit 3 to enable Vbord.
10. `ANDCC #$EF` — unmask IRQ. Enter main loop.

Phase 1 implements steps 1-3 and 6-10 (with a Phase-1 simplification of step 4: no MMU, no hi-res, no palette). Phase 2.2 adds step 5 (the cart-to-RAM self-copy). Phase 2.3+ does the full step 4, plus 8.

Every step has a citation in [../sources/coco3-asm-tepolt.md](../sources/coco3-asm-tepolt.md) chapters 6-7.

## Sources

- [../sources/coco-asm-tepolt.md](../sources/coco-asm-tepolt.md) ch. 10 (cartridge connector pinout, CART/FIRQ wiring)
- [../sources/coco3-asm-tepolt.md](../sources/coco3-asm-tepolt.md) ch. 7 (reset init flow, jump tables)
