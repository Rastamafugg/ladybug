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

## Cart size — 32 K

**Decision (2026-05-08): 32 K cartridge.** Init0 b1-b0 = `11` puts the cart at `$8000-$FEFF` (full 32 K window) instead of the default `$C000-$FEFF` (16 K window with BASIC ROM at `$8000-$BFFF`). Made when video-mode analysis showed 4bpp sprite/tile ROM footprint pushing past 16 K.

The transition is staged:

- **At reset and during BASIC's reset-init**, Init0 ROM map is the default `0x` — only the upper 16 K of cart (`$C000-$FEFF`) is visible; BASIC ROM occupies `$8000-$BFFF`. Our `"DK"` magic and entry code therefore must live in the upper 16 K, addressed at `$C002` onwards.
- **After we take control via FIRQ**, our boot writes Init0 with b1-b0 = `11` to switch to 32 K cart mode. BASIC ROM at `$8000-$BFFF` disappears; the lower 16 K of our cart appears there. From this point on we have the full 32 K of cart accessible.
- **Then we write `$FFDF`** to enter all-RAM mode. In all-RAM mode the cart ROM is hidden entirely and the address space is RAM. Tables we want from cart ROM must be copied into RAM **before** this step, while still in ROM/RAM 32 K mode.

Cart layout in the 32 K image:

```
file offset   virtual    purpose
$0000-$3FFF   $8000-$BFFF   data tables (tiles, sprites, palette, fonts, maze, sound)
$4000-$7EFF   $C000-$FEFF   "DK" magic, entry code, code, more data tables
              $FF00-$FFFF   not in cart (dedicated I/O / vectors)
```

Cart hardware: needs a 32 K EPROM and a cart shell that decodes the `$8000-$FEFF` range when CTS-equivalent is asserted in 32 K mode. Standard 16 K EPROM cart shells will not work. CoCoSDC, RetroCloud cart, and similar bank-switched/SD cart hardware emulate larger ROMs transparently.

If 32 K turns out to be insufficient, the next step is a bank-switched cart — software-driven page swap into a fixed window. Deferred unless we hit the limit.

## What our boot must do

Once we have control at `$C002`:

1. `ORCC #$50` — mask IRQ and FIRQ.
2. Set `S` to the top of our work RAM.
3. Disable PIA-driven interrupts and bleed any pending flags.
4. Configure GIME Init0: clear bit 7 (hi-res), enable MMU, set bit 3 so `$FE00-$FEFF` is always reachable, set bit 5 to enable ACVC IRQs, **set b1-b0 = `11` for 32 K cart mode** so our cart's lower 16 K appears at `$8000-$BFFF`. Then clear/blank the screen buffer with CRES=11 while we initialise.
5. Load our palette (`$FFB0-$FFBF`) — sourced from a table now reachable in the lower 16 K of cart.
6. Copy any cart-ROM tables we'll need post-all-RAM into RAM. (Don't strictly need to copy palette tables if we only load them once; do need to copy any tables read at runtime if they live in cart ROM — they vanish when we go all-RAM.)
7. Switch to all-RAM mode (write to `$FFDF`).
8. Switch to fast clock (write to `$FFD9`).
9. Install our IRQ handler in the primary jump table at `$FEF7` (LBRA / JMP to handler), write `$FF92` bit 3 to enable Vbord.
10. `ANDCC #$EF` — unmask IRQ. Enter main loop.

Phase 1 implements steps 1-3, a partial step 4 (no MMU, no hi-res, no 32 K mode yet), 7-10. Steps 4 (full GIME config), 5, 6 land in Phase 2.

Every step has a citation in [../sources/coco3-asm-tepolt.md](../sources/coco3-asm-tepolt.md) chapters 6-7.

## Sources

- [../sources/coco-asm-tepolt.md](../sources/coco-asm-tepolt.md) ch. 10 (cartridge connector pinout, CART/FIRQ wiring)
- [../sources/coco3-asm-tepolt.md](../sources/coco3-asm-tepolt.md) ch. 7 (reset init flow, jump tables)
