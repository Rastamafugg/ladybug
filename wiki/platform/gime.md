---
name: GIME (ACVC) — CoCo 3 video / IRQ controller
description: Register catalog for the Advanced Color Video Chip (ACVC, aka GIME): palette, MMU, video mode/resolution/offset, border, scroll, ACVC IRQ/FIRQ enables, timer, and the legacy SAM control bits. The single chip that controls almost everything new about the CoCo 3.
type: concept
tags: [gime, acvc, video, palette, interrupts]
updated: 2026-05-07
---

# GIME / ACVC

The GIME (Tepolt calls it the **ACVC** — Advanced Color Video Chip) is the master controller of the CoCo 3. It absorbs the old SAM and VDG, contains the MMU, drives 16 palette registers, and adds new IRQ/FIRQ sources plus a programmable timer. Every register is at a dedicated address in `$FF8x..$FFDx`.

## Register catalog

### Init / mode

| Addr | Reg | Bits |
|-|-|-|
| `$FF90` | Init0 | b7 COCO (1=lo-res VDG path, 0=hi-res); b6 MMU enable; b5 ACVC-IRQ enable; b4 ACVC-FIRQ enable; b3 force `$FE00-$FEFF` to phys page `$3F`; b2 SCS enable; b1-b0 ROM map (0x = 16K Ext+Color BASIC + 16K cartridge; 10 = 16K BASIC + 8K reset-init + 8K Super Ext; 11 = 32K cartridge) |
| `$FF91` | Init1 | b5 timer source (0 = 63.5 µs, 1 = 70 ns); b0 PAR set (0 = exec, 1 = task) |
| `$FF98` | Video Mode | b7 BP (0 = text, 1 = graphics); b5 BPI; b4 MOCH (mono); b3 H50 (PAL 50 Hz); b2-b0 LPR (lines-per-row code) |
| `$FF99` | Video Resolution | b6-b5 VRES (00 = 192/24, 01 = 200/25, 11 = 225/28); b4-b2 HRES; b1-b0 CRES |
| `$FF9A` | Border | 6-bit color code (direct, *not* a palette index) |
| `$FF9C` | Vertical Scroll | b3 SCEN (0 = enabled), b2-b0 8-step smooth-scroll value (text mode only) |
| `$FF9D` | Vertical Offset 1 | physical-buffer addr bits Y18..Y11 |
| `$FF9E` | Vertical Offset 0 | physical-buffer addr bits Y10..Y3 (8-byte aligned) |
| `$FF9F` | Horizontal Offset | b7 HE (1 = 256-byte-wide expanded buffer); b6-b0 X-shift (each step = 2 bytes = 4/8/16 pixels by depth) |

### MMU page address registers

| Addr | Reg |
|-|-|
| `$FFA0-$FFA7` | Executive PAR0..7 |
| `$FFA8-$FFAF` | Task PAR0..7 |

Each PAR is 6 bits (a physical page number `$00-$3F`) and supplies bits Y18..Y13 of the expanded address for the corresponding 8 K virtual page. See [memory.md](memory.md).

### Palette

| Addr | Reg |
|-|-|
| `$FFB0-$FFBF` | Palette regs 0..15 |

6 bits each; interpretation differs for composite vs RGB monitors (see [../sources/coco3-asm-tepolt.md](../sources/coco3-asm-tepolt.md) Chapter 2). `$FF98` bit 5 toggles the alternate (rotated) color set used to mimic CoCo-1 artifact phasing.

### ACVC interrupt control

| Addr | Reg | Bits (lower 6) |
|-|-|-|
| `$FF92` | IRQEN  | b5 Timer; b4 Hbord; b3 Vbord (60 Hz); b2 SerIn; b1 Kybd/Jy; b0 Cart |
| `$FF93` | FIRQEN | same layout |
| `$FF94` | Timer1 | upper 4 bits of 12-bit timer reload |
| `$FF95` | Timer0 | lower 8 bits of 12-bit timer reload |

A bit set in `$FF92` enables that IRQ source (Init0 b5 must also be set). Reading `$FF92` acknowledges any pending IRQ and returns a bitmask identifying the source. Symmetric for FIRQ at `$FF93`. See [timing.md](timing.md) for which we use.

### Legacy SAM control bits (still present, behind the GIME)

Each row is two paired addresses; *write anything* to set or clear the underlying bit:

| Bit | Function | Set | Clear |
|-|-|-|-|
| TY    | Memory map (1 = all-RAM, 0 = ROM/RAM)  | `$FFDF` | `$FFDE` |
| M1    | Memory size                            | `$FFDD` | `$FFDC` |
| M0    |                                         | `$FFDB` | `$FFDA` |
| R1    | MPU clock                               | `$FFD9` | `$FFD8` |
| R0    |                                         | `$FFD7` | `$FFD6` |
| P1    | Page                                    | `$FFD5` | `$FFD4` |
| F6..F0| SAM video starting addr                 | `$FFD3..$FFC6` (set/clear paired) |
| V2..V0| SAM (lo-res) video mode                 | `$FFC5..$FFC0` (set/clear paired) |

In hi-res mode the F-bits and V-bits are ignored — the GIME uses Vert-Offset 1/0 instead. TY and the R-bits remain functional. R1 is a no-op on the CoCo 3 (everything runs at the rate selected by R0).

## Programming notes

- All `$FF8x` / `$FF9x` registers are write-only (Table 7-2). Keep a software shadow if you need to modify a single bit.
- `$FFA0-$FFBF` are read-write.
- Bit 6 of the PAR / palette regs reads back as zero in ROM/RAM mode, as one in all-RAM mode. Don't depend on it.
- `$FF22` is split: bits 7-3 → GIME's vestigial VDG mode bits; bits 2-0 → PIA2 side-B (sound DAC enable, cassette motor, joystick selector). Reads/writes still go to PIA2 for bits 2-0.
- Init0 bit 3 set ("force `$FE00-$FEFF` to physical page `$3F`") keeps the primary IRQ jump table reachable regardless of what PAR7 currently maps. Set this bit in our init.

## Sources

- docs/reference/Assembly Language Programming for the CoCo3.md ch. 4, 6, 7 + Cross-Reference
- [../sources/coco3-asm-tepolt.md](../sources/coco3-asm-tepolt.md)
- [../sources/coco-asm-tepolt.md](../sources/coco-asm-tepolt.md) (SAM legacy bits)
