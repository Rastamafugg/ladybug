---
name: Tepolt — Assembly Language Programming for the CoCo 3
description: 1987 Tepolt addendum that documents only the CoCo 3-specific additions over The Book (CoCo 1/2 manual). Covers the GIME (ACVC), MMU + 19-bit physical memory, palette registers, hi-res text and graphics modes, the new ACVC interrupt sources, and reset initialisation.
type: source
tags: [gime, mmu, palette, interrupts, hires, coco3]
updated: 2026-05-07
---

# Assembly Language Programming for the CoCo 3 (Tepolt, TEPCO, 1987)

Author Laurence A. Tepolt. Written as an addendum to the CoCo 1/2 manual ("The Book") — see [coco-asm-tepolt.md](coco-asm-tepolt.md). Only describes the *deltas* introduced by the CoCo 3, so both books are needed.

Raw OCR text: [docs/reference/Assembly Language Programming for the CoCo3.md](../../docs/reference/Assembly%20Language%20Programming%20for%20the%20CoCo3.md).

## What we extracted

**Chapter 1 — Overview.** MPU is the MC68B09E (same ISA as MC6809E, certified for the high 1.78 MHz clock). 128 K or 512 K RAM; 32 K of ROM (Color BASIC, Extended Color BASIC, Super Extended BASIC, Reset Init). The new component is the **ACVC** (Advanced Color Video Chip), aka the **GIME** chip, which absorbs SAM + VDG and adds the MMU, palette registers, new control registers, and new interrupt sources. New I/O jacks: Audio (line out), Composite Video, RGB. Joystick connectors gain a second fire button per stick.

**Chapter 2 — Colors and palette.** Sixteen palette registers at `$FFB0-$FFBF`, six bits each. Each register is referenced indirectly (pixel data selects a palette index 0..15; that register holds the 6-bit color code). Two color sets:
- *Composite* (TV / composite monitor): bits encode `S1 S0 A3 A2 A1 A0` = brightness/saturation pair (S1S0: 00=low/high, 01=med/med, 10=high/low, 11=very-high/very-low) + 4-bit hue angle (0=gray, 1=green, 2=greenish-yellow, 3=yellow, 4=yellowish-orange, 5=orange, 6=reddish-orange, 7=red, 8=reddish-magenta, 9=magenta, 10=indigo, 11=blue, 12=bluish-cyan, 13=cyan, 14=greenish-cyan, 15=bluish-green). Code `$3F` is white (special case).
- *RGB* (analog RGB monitor): bits encode `R1 G1 B1 R0 G0 B0`; each primary intensity is 2-bit (00 none, 01 low, 10 medium, 11 high).

Bit 5 of `$FF98` toggles the **alternate color set** (rotates the hue wheel 180° to mimic CoCo-1 artifact-color phase flips).

**Chapter 3 — Physical & virtual memory / MMU.**
- Virtual = the 64 K MPU address space, divided into eight 8 K pages (page # = top three address bits).
- Physical = up to 512 K, divided into sixty-four 8 K pages numbered `$00-$3F`. Physical RAM in a 128 K machine populates pages `$30-$3F`; in a 512 K machine, all 64 pages.
- MMU has two PAR sets, **executive** (`$FFA0-$FFA7`) and **task** (`$FFA8-$FFAF`); each PAR is a 6-bit physical-page number that supplies bits Y18..Y13 of the expanded address. Bit 0 of `$FF91` selects which set is live (0 = exec, 1 = task). Bit 6 of `$FF90` enables the MMU; when disabled, virtual maps to the top 64 K of physical (pages `$38-$3F`).
- Dedicated addresses `$FF00-$FFFF` always bypass the MMU.
- **128 K wrap-around quirk:** physical pages `$00-$2F` are unused, so the MMU's two top expanded-address bits are unused; the contents of pages `$30-$3F` are aliased through pages `$00-$0F`, `$10-$1F`, and `$20-$2F` as well. Don't rely on this aliasing in 512 K code.

ROM / RAM mapping is still controlled by the SAM TY bit (`$FFDF` set = all-RAM, `$FFDE` clear = ROM/RAM). In ROM/RAM mode, physical pages `$3C-$3F` are ROM, and bits 0-1 of `$FF90` select among three configurations (16K Ext+Color BASIC + 16K cartridge / 16K Ext+Color BASIC + 8K reset-init + 8K Super Ext / all 32K cartridge).

**Chapter 4 — High-resolution displays.** GIME control registers (all write-only, see Table 7-2):

| Address | Register | Purpose |
|-|-|-|
| `$FF90` | Init0 | bit7 COCO (1=lo-res VDG, 0=hi-res), bit6 MMU enable, bit5 IRQ enable (ACVC), bit4 FIRQ enable (ACVC), bit3 vector ROM (1=force `$FE00-$FEFF` to phys page `$3F`), bit2 SCS enable, bits1-0 ROM map |
| `$FF91` | Init1 | bit5 timer clock (0=63.5 µs, 1=70 ns), bit0 task/exec PAR select |
| `$FF92` | IRQEN  | enable + ack for ACVC IRQ sources (read also identifies source) |
| `$FF93` | FIRQEN | same shape, FIRQ |
| `$FF94/95` | Timer1 / Timer0 | 12-bit reload, decrements at Init1 bit5 rate |
| `$FF98` | Video Mode    | bit7 BP (0=text, 1=graphics), bit5 BPI, bit4 MOCH (mono mode), bit3 H50 (50 Hz PAL), bits2-0 LPR (lines-per-row) |
| `$FF99` | Video Resolution | bits6-5 VRES (00=192/24, 01=200/25, 11=225/28), bits4-2 HRES, bits1-0 CRES |
| `$FF9A` | Border        | 6-bit color code (direct, NOT via palette register) |
| `$FF9C` | Vertical Scroll | bit3 SCEN, bits2-0 8-step smooth scroll |
| `$FF9D/9E` | Vertical Offset 1 / 0 | high 16 bits of physical buffer address (Y18..Y3) — buffer must be 8-byte aligned |
| `$FF9F` | Horizontal Offset | bit7 HE (1 = 256-byte-wide buffer), bits6-0 X-shift in 2-byte units |
| `$FFA0-FFAF` | PARs | MMU |
| `$FFB0-FFBF` | Palette regs | 6-bit color codes |

Hi-res text (BP=0, COCO=0): each character is two bytes — byte 0 = video code (Appendix A; codes 32-127 match ASCII), byte 1 = attribute (bit7 blink, bit6 underline, bits5-3 foreground = palette regs 8-15, bits2-0 background = palette regs 0-7). Column counts 32/40/64/80 selected via HRES; row counts 24/25/28 via VRES; buffer size = 2 × cols × rows (or 256 × rows when HE=1).

Hi-res graphics (BP=1): three byte formats determined by CRES — A = 8 pixels × 1 bit (palette regs 0-1, 2 colors), B = 4 pixels × 2 bits (regs 0-3, 4 colors), C = 2 pixels × 4 bits (regs 0-15, 16 colors). HRES selects buffer width 16 / 20 / 32 / 40 / 64 / 80 / 128 / 160 bytes/row; CRES=11 blanks the screen (a useful trick for double-buffer-style updates). Full mode table is Table 4-10.

Vertical scrolling: in text use the Vertical Scroll register (`$FF9C`) for sub-line smoothness, then bump the buffer address by one row when SC reaches 7. In graphics, scroll by adding/subtracting one row's byte width to the Vert-Offset registers. Horizontal scrolling resolution is 4 / 8 / 16 pixels per X-step depending on color depth (HE=1 + multiple offset buffers gets you single-pixel smooth scroll).

**Chapter 5 — Low-resolution displays.** In COCO mode (Init0 bit7=1) the original CoCo VDG modes (Text/SG4/G1C/G1R/G2C/G2R/G3C/G3R/G6C/G6R) are available with palette registers replacing the original fixed colors. The SAM V2-V0 mode bits (`$FFC0-$FFC5`) and the F6-F0 vertical-offset bits (`$FFC6-$FFD3`) still apply via dedicated-address-flip writes; the GIME ignores those when in hi-res mode. VDG mode is still selected via the upper bits of `$FF22`. Palette mapping in low-res:
- Text C=0: char=palette 12, bg=palette 13. C=1: char=palette 14, bg=palette 15.
- Graphics with-resolution (GxR): pixel bit picks regs 8/9 (C=0) or 10/11 (C=1).
- Graphics with-color (GxC): pixel pair picks regs 0-3 (C=0) or 4-7 (C=1).

**Chapter 6 — ACVC interrupts.** New IRQ/FIRQ sources, all routed through the GIME and OR'd with the existing PIA-driven IRQ/FIRQ. Both `$FF92` (IRQEN) and `$FF93` (FIRQEN) share this layout (lower six bits): bit5 Timer (Timer1/0 underflow), bit4 Hbord (right-border H scan), bit3 Vbord (bottom-border V scan, 60 Hz), bit2 SerIn (RS-232 input edge), bit1 Kybd/Jy (any keypress or fire button — requires writing zeros to PIA1 PB7-0 first), bit0 Cart (cartridge CART pin low). Set the bit to enable; read the register to ack and identify the cause. Init0 bits 5/4 globally enable ACVC IRQ / FIRQ generation respectively.

Skeleton init sequence (Fig 6-2): mask ints (`ORCC #$50`), set up S, disable PIA ints by writing `$34` to all four CR registers and read the DRs to bleed pending flags, set Init0 to enable ACVC IRQs, set IRQEN to choose the sources, read `$FF92`/`$FF93` to bleed ACVC pending, install jump-table entry, then `ANDCC #$EF` to unmask IRQ.

Vector table is in ROM at `$BFF2-BFFF` mirrored to `$FFF2-FFFF`. Primary jump table sits in RAM at `$FEEE-FEFF` (long branches); secondary jump table in RAM at `$0100-$010F` (legacy CoCo-1 layout). Init0 bit3 set forces virtual `$FE00-$FEFF` to physical page `$3F` regardless of PAR7, so the primary jump table always remains reachable.

**Chapter 7 — Reset init & odds and ends.**
- After hardware reset: PIAs, ACVC registers, MPU DP all cleared; CC I and F set; PC ← `[$FFFE/$FFFF]` = `$8C1B`.
- ROM init copies itself to `$4000-$436C`, then runs out of RAM, sets up palette and PARs, copies ROM to RAM, lays the primary jump table at `$FEEE-FEFF`, selects all-RAM mode, jumps to BASIC's init at `$A027`. F1 held → alternate color set; CTRL+ALT held → Hawkins/Harris/Earles photo via G6R + bytes from C405.
- Default palette after reset: `12 24 0B 07 3F 1F 09 26 00 12 00 3F 00 12 00 26`.
- MPU speed: write anything to `$FFD8` for 0.89 MHz, `$FFD9` for 1.78 MHz. The MC68B09E in the CoCo 3 is rated for the fast clock; only cassette/serial BASIC ROM calls require the slow clock.
- Split `$FF22`: bits 7-3 go to the GIME (replaces VDG select), bits 2-0 are still PIA2 side-B (sound, motor, joystick selector — unchanged).
- Redundant dedicated addresses (Table 7-1) — same as CoCo 1/2; not recommended for new code.
- Keyboard layout extension: the new F1, F2, CTRL, ALT keys land on the previously-unused row PB6 in the matrix; joystick button 2 lands on previously-unused PA columns (Fig 7-3).
- Smooth horizontal pixel scrolling: maintain N pre-shifted buffers (N = 16 / 4-color-mode, 8 / 4-color, 4 / 16-color) and select among them by combining horizontal-offset with vertical-offset register changes.

## What this means for Ladybug

- We will boot as a cartridge → on power-on the FIRQ from CART pin 8 fires; our ROM at `$C000` takes control before BASIC's normal entry. We then init the GIME ourselves and ignore Super Extended BASIC entirely.
- 60 Hz frame tick = ACVC Vbord IRQ (`$FF92` bit 3) — preferred over PIA1 CB1 because it's already on the GIME path and is the documented "vertical sync" interrupt. See [../platform/timing.md](../platform/timing.md).
- The MMU is critical for putting our 240×192-equivalent playfield buffer somewhere sensible without trampling the ROM area; see [../platform/memory.md](../platform/memory.md).
- Hi-res CRES=10 (16-color, format C, 4 bits/pixel) at HRES=4 gives 128×N at 32 bytes/row — a good candidate for Lady Bug's tile maze. Decision deferred to coding-architect.
- We can fast-clock the MPU (`$FFD9`) since we're not using BASIC ROM I/O.

## What we did NOT ingest in detail

- Chapter 2's color theory primer.
- Most of the Listing 4-1 demo program — used as a reference but not transcribed.
- Appendix A character codes — kept as-is in the source file; `$20-$7F` matches ASCII.
- Cross-Reference of dedicated addresses (back of book) — superseded by our own [../platform/memory.md](../platform/memory.md).

## Where this propagates in the wiki

- [../platform/gime.md](../platform/gime.md) — full register catalog.
- [../platform/memory.md](../platform/memory.md) — MMU, PARs, 128K vs 512K, dedicated address map.
- [../platform/timing.md](../platform/timing.md) — Vbord/Hbord/Timer interrupts, MPU clock.
- [../platform/input.md](../platform/input.md) — extended keyboard matrix, second fire button.
- [../platform/cartridge.md](../platform/cartridge.md) — cartridge boot via FIRQ.
- [../platform/6809.md](../platform/6809.md) — MC68B09E speed envelope.
