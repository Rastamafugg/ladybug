---
name: Tepolt — Assembly Language Programming for the Color Computer
description: 1985 Tepolt manual covering the MC6809E, addressing modes, instruction set, SAM, PIAs, VDG, interrupts, and the cartridge connector. The CoCo 3 inherits all of this hardware (PIAs, cartridge slot, 6809 ISA); only the SAM/VDG are now embedded in the GIME and the SAM-mode bits are still writable.
type: source
tags: [6809, sam, pia, vdg, cartridge, hardware]
updated: 2026-05-07
---

# Assembly Language Programming for the Color Computer (Tepolt, TEPCO)

Author Laurence A. Tepolt. Covers the original CoCo 1 / CoCo 2 hardware. The CoCo 3 manual (also Tepolt) refers to this volume as "The Book"; almost everything in this book is still load-bearing for bare-metal CoCo 3 programming except where superseded by the GIME (ACVC) — see [coco3-asm-tepolt.md](coco3-asm-tepolt.md).

Raw OCR text: [docs/reference/Assembly Language Programming for the Color Computer.md](../../docs/reference/Assembly%20Language%20Programming%20for%20the%20Color%20Computer.md).

## What we extracted

**Chapter 3 — MC6809E.** Programming model: X, Y, U, S (16-bit pointer regs); PC (16-bit); A, B (8-bit accumulators) concatenable as D; DP (8-bit direct page); CC (`E F H I N Z V C`). U and S are stack pointers; S is the hardware stack used by interrupts. RESET clears DP, sets I and F, fetches PC from `$FFFE/$FFFF`. Hardware vectors: see Appendix E table below.

**Chapter 3 — Interrupts (6809 sequence).**
- IRQ: completes current instruction, sets E, pushes all regs (PC, U, Y, X, DP, B, A, CC) onto S, sets I, vectors via `$FFF8/$FFF9`. Maskable via I bit.
- FIRQ: clears E, pushes only PC and CC, sets F and I, vectors via `$FFF6/$FFF7`. Maskable via F bit. Higher priority than IRQ (FIRQ is not masked during IRQ).
- NMI: like IRQ but non-maskable; first NMI ignored until S is loaded after reset; vector `$FFFC/$FFFD`.
- SWI/SWI2/SWI3: software interrupts, vectors `$FFFA-FFFB`, `$FFF4-FFF5`, `$FFF2-FFF3`.
- RTI inspects E on the popped CC: full unstack if set, only PC+CC if clear.

**Chapter 4 — Addressing modes.** Inherent, immediate (`#`), extended (16-bit absolute), extended indirect (`[$nnnn]`), register (TFR/EXG/PSH/PUL postbyte), indexed (zero offset, 5/8/16-bit constant offset, A/B/D-register offset, autoinc/dec by 1 or 2, all with optional indirect via `[ ]`), relative (short ±127, long ±32767, all branches PC-relative), direct (DP + 8-bit, single-byte operand), PC-relative (`,PCR` — supports position independence). Indexed postbyte tables 4-1/4-2/4-3 captured. Push/pull postbyte bit map: bit0=CC, 1=A, 2=B, 3=DP, 4=X, 5=Y, 6=S/U, 7=PC. TFR/EXG nibble codes: 0=D, 1=X, 2=Y, 3=U, 4=S, 5=PC, 8=A, 9=B, A=CC, B=DP. **For Ladybug, prefer DP-relative for hot per-frame state and PC-relative within position-independent code blocks.**

**Chapter 5 / Appendix B — Instruction set table.** Full op-code / addressing / cycle / byte-count / CC-effect grid; 59 instructions. Use Appendix B as the canonical cycle-count reference for budget calculations.

**Chapter 9 — SAM (MC6883).** 16 control bits, set/cleared by writing to paired addresses in the `$FFC0-$FFDF` range. **In the CoCo 3 the SAM is absorbed into the GIME but the same dedicated-address bit-flip semantics still apply.**

| Bits | Function | Set / Clear |
|-|-|-|
| TY    | Memory map mode (0 = ROM/RAM, 1 = all-RAM) | FFDF / FFDE |
| M1,M0 | Memory size | FFDD/DC, FFDB/DA |
| R1,R0 | MPU clock rate | FFD9/D8, FFD7/D6 |
| P1    | Page number | FFD5 / FFD4 |
| F6..F0| Video display starting address (×512 byte boundary) | FFD3..FFC6 |
| V2..V0| VDG buffer-size mode | FFC5..FFC0 |

R0/R1 control speed: `00`=0.89 MHz everywhere, `01`=1.78 MHz outside `$FF00-$FF1F` and outside RAM (i.e. ROM-only fast), `1x`=1.78 MHz everywhere ("all-fast", needs MC68B09E). Cassette/serial/disk ROM I/O depends on the slow rate.

**Chapter 9 — PIA (MC6821).** Each PIA has six registers in 4 dedicated bytes:

| Address | PIA 1 (keyboard, joystick fire, sound out) | Address | PIA 2 (VDG-mode bits, DAC, serial, cassette) |
|-|-|-|-|
| `$FF00` | DRA / DDRA (selected by CRA bit 2) | `$FF20` | DRA / DDRA |
| `$FF01` | CRA                                | `$FF21` | CRA |
| `$FF02` | DRB / DDRB                         | `$FF22` | DRB / DDRB (bits 7-3 → VDG; on CoCo 3 those go to GIME) |
| `$FF03` | CRB                                | `$FF23` | CRB |

CRA/CRB layout: bit7=CA(B)1 flag (RO; cleared by reading DRA/DRB), bit6=CA(B)2 flag, bits5-3=CA(B)2 control, bit2=DR/DDR select (1=DR), bits1-0=CA(B)1 control (bit1 transition select, bit0 IRQ enable). DDR bit 1=output, 0=input.

BASIC's PIA init (Table 9-8): PIA1 DDRA=$00, CRA=$34, DDRB=$FF, CRB=$35. PIA2 DDRA=$FE, CRA=$30, DDRB=$F8, CRB=$30. **For Ladybug we will reset and reinitialise the PIAs ourselves rather than trusting BASIC's setup, since we boot from cartridge.**

**Chapter 9 — Interrupt sources (CoCo 1/2):**
- IRQ from PIA1 CA1 = HSYNC (63.5 µs, ~15.7 kHz) and CB1 = VSYNC (16.7 ms, 60 Hz).
- FIRQ from PIA2 CA1 = serial RS-232 READY and CB1 = cartridge pin 8.
- NMI direct from cartridge pin 4.

To arm a PIA-driven interrupt: read CRx, OR `$05` (set bit 0 = enable interrupt, bit 2 = DR access), write CRx back, then read DRx to clear the flag bit. The interrupt handler must read DRx before RTI to acknowledge.

**Chapter 10 — Devices.**
- *Keyboard:* 7×8 matrix on PIA1 PB7-PB0 (column drive, output low) × PA6-PA0 (row sense, input). PA7 is wired to the joystick comparator. Drop one PB column low, all others high, then read DRA — any 0 in PA0..PA6 marks pressed keys in that column. Layout matrix in Fig 10-1. CoCo 3 adds F1/F2/CTRL/ALT and joystick button 2 — see [coco3-asm-tepolt.md](coco3-asm-tepolt.md) Fig 7-3.
- *Joystick fire buttons:* PA0 (right), PA1 (left), active low.
- *Joystick X/Y:* analog, digitised via successive-approximation A/D = 6-bit DAC on PIA2 PA7-PA2 + comparator into PIA1 PA7. Selector switch (PIA1 CA2 + CB2) picks one of four analog sources; CB2 of PIA2 is the master enable.
- *Sound paths:* (a) 6-bit DAC on PIA2 PA7-PA2 (selector switch position 0, CB2 PIA2 master high); (b) cassette playback (sw pos 1); (c) cartridge SND pin 35 (sw pos 2); (d) 1-bit square wave from PIA2 PB1. All routed to TV speaker via attenuator. **For Ladybug v1, plan on the 6-bit DAC for tones/effects and PB1 for simple beeps. See [../platform/sound.md](../platform/sound.md).**
- *Cassette motor relay:* PIA2 CA2.
- *RS-232 serial:* TX on PIA2 PA1 (inverted), RX on PIA2 PB0 (inverted), READY on PIA2 CA1 → FIRQ.

**Chapter 10 — Cartridge connector.** 40-pin. Power: -12V (1, CoCo1 only), +12V (2), +5V (9, up to 300 mA), GND (33, 34). Data D0-D7 (10-17), R/W (18), address A0-A15 (19-31, 37-39). Control: HALT (3, in), NMI (4, in), RESET (5, out), E (6, out), Q (7, out), CART/CARTRIDGE (8 → PIA2 CB1, FIRQ source), CTS (32 — low when MPU accesses `$C000-$FEFF` with TY clear, i.e. cartridge ROM select), SCS (36 — low when MPU accesses `$FF40-$FF5F`, i.e. cartridge I/O select), SND (35, analog audio in), SLENB (40 — when low inhibits SAM decoding).

**Cartridge auto-start (critical for Ladybug).** When a cartridge is inserted, the ROM at the cartridge slot occupies `$C000-$FEFF` (TY=0, ROM/RAM mode). Pin 8 = CART line is wired to PIA2 CB1 → FIRQ. The BASIC reset routine arms the cartridge FIRQ; on FIRQ it jumps to `$C000`. So a cartridge ROM whose first three bytes are a `JMP $Cxxx` (or, more commonly, `"DK"` magic followed by a JMP) gets control on power-on — this is the Ladybug entry mechanism for native-hardware boot.

**Appendix E — Dedicated address summary.** Captured in [../platform/memory.md](../platform/memory.md) and [../platform/gime.md](../platform/gime.md).

## What we did NOT ingest in detail

- Chapters 1, 2 (binary/hex math and BASIC data formats) — assumed.
- Chapter 6 (EDTASM+) — we are not using EDTASM+ as our toolchain.
- Chapter 7's BASIC-style flow primer — assumed.
- Chapter 8 (BASIC ROM call interface) — Ladybug runs without BASIC.
- Memory-size sense / cassette I/O / RS-232 fine detail — out of scope for a cartridge-resident game.

## Where this propagates in the wiki

- [../platform/6809.md](../platform/6809.md) — MPU programming model, addressing modes, interrupt sequences.
- [../platform/memory.md](../platform/memory.md) — dedicated address map, SAM TY mode.
- [../platform/gime.md](../platform/gime.md) — SAM register set (now inside the GIME).
- [../platform/timing.md](../platform/timing.md) — HSYNC / VSYNC interrupt sources, MPU clock rate.
- [../platform/input.md](../platform/input.md) — keyboard matrix, joystick read.
- [../platform/sound.md](../platform/sound.md) — DAC / square-wave paths.
- [../platform/cartridge.md](../platform/cartridge.md) — pinout and auto-start handshake.
