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

1. Cartridge is inserted. Its ROM occupies `$C000-$FEFF` while TY=0 (default).
2. Hardware reset: PIAs cleared, PC ← `[$FFFE/$FFFF]` = `$8C1B`, BASIC reset-init runs.
3. The reset-init configures PIA2 CB1 to detect the CART line going low and to generate a FIRQ.
4. CART pin is asserted low by the cartridge electronics.
5. FIRQ fires → BASIC's FIRQ handler examines the first three bytes at `$C000`. If they are `"DK"` (the ROM-pack autostart magic) followed by enough additional setup, control jumps to `$C002`/`$C003`.

The simpler convention used by single-purpose game cartridges is to put a `JMP entry` instruction at `$C000` and let the BASIC FIRQ handler dispatch into it. We will use that path.

## What our boot must do

Once we have control at `$C000`-ish:

1. `ORCC #$50` — mask IRQ and FIRQ.
2. Set `S` to the top of our work RAM.
3. Disable PIA-driven interrupts and bleed any pending flags.
4. Configure GIME: clear Init0 bit 7 (hi-res), enable MMU, install our PARs, clear/blank the screen buffer with CRES=11 while we initialise.
5. Load our palette (`$FFB0-$FFBF`).
6. Switch to all-RAM mode (write to `$FFDF`) — we keep ROM long enough to copy any tables we want, then go all-RAM.
7. Switch to fast clock (write to `$FFD9`).
8. Install our IRQ handler in the primary jump table at `$FEF7` (LBRA to handler), set Init0 bit 3 so `$FE00-$FEFF` is always reachable, set Init0 bit 5 to enable ACVC IRQs, write `$FF92` bit 3 to enable Vbord.
9. `ANDCC #$EF` — unmask IRQ. Enter main loop.

Every step has a citation in [../sources/coco3-asm-tepolt.md](../sources/coco3-asm-tepolt.md) chapters 6-7.

## Sources

- [../sources/coco-asm-tepolt.md](../sources/coco-asm-tepolt.md) ch. 10 (cartridge connector pinout, CART/FIRQ wiring)
- [../sources/coco3-asm-tepolt.md](../sources/coco3-asm-tepolt.md) ch. 7 (reset init flow, jump tables)
