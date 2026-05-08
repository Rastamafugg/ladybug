---
name: CoCo 3 memory map (bare-metal, no NitrOS-9)
description: Physical/virtual memory model, MMU/PAR layout, ROM/RAM modes, and the dedicated-address landing zone in $FF00-$FFFF.
type: concept
tags: [memory, mmu, par, dedicated-addresses]
updated: 2026-05-07
---

# Memory map

## Two address spaces

- **Virtual** = the 16-bit address space the MPU sees: `$0000-$FFFF`, divided into eight 8 K virtual pages (page # = top three address bits).
- **Physical** = up to 512 K of installed memory, divided into sixty-four 8 K **physical pages** numbered `$00-$3F`. RAM is populated from the top down: a 128 K machine has only pages `$30-$3F`; a 512 K machine has all 64.

The MMU (inside the GIME) translates each virtual access by replacing the top three address bits with a 6-bit physical page number drawn from the appropriate PAR register. Bit 6 of `$FF90` enables the MMU; with it disabled, the virtual extent always maps to physical pages `$38-$3F` (the top 64 K). See [gime.md](gime.md) for the registers.

## PAR sets

Two complete sets of eight 6-bit page registers:

| Set | Addresses | When live |
|-|-|-|
| Executive | `$FFA0-$FFA7` | Bit 0 of `$FF91` = 0 |
| Task      | `$FFA8-$FFAF` | Bit 0 of `$FF91` = 1 |

Storing a physical-page number `pp` (`$00-$3F`) into the dedicated address of PAR *n* points virtual page *n* (covering virtual `n*$2000 .. n*$2000+$1FFF`) at physical `pp*$2000`. Write order doesn't matter; the change takes effect on the next memory access through that virtual page.

Convention from BASIC's reset init: the controller (kernel) lives in the executive set and the application in the task set, with a small overlap that contains the interrupt jump tables and any cross-task interface code. **Ladybug, as a single bare-metal cartridge, will use the executive set only and ignore the task set.**

## ROM/RAM modes

The SAM `TY` bit selects:

- **TY=0 (ROM/RAM mode, default after reset).** Physical pages `$3C-$3F` come from ROM rather than RAM. Bits 0-1 of Init0 (`$FF90`) sub-select among three layouts: `0x` = 16 K Ext+Color BASIC at `$3C/$3D` plus 16 K cartridge at `$3E/$3F`; `10` = 16 K BASIC + 8 K reset-init + 8 K Super Extended BASIC; `11` = full 32 K cartridge.
- **TY=1 (all-RAM mode).** The whole `$30-$3F` range is RAM. Reach by writing anything to `$FFDF`.

For Ladybug we will operate in all-RAM mode after we've copied any ROM data we need (palette tables, font glyphs, etc.) — it removes the special case from PAR planning and frees pages `$3C-$3F` for game data.

## Dedicated addresses

Virtual `$FF00-$FFFF` is *never* MMU-translated. It always lands on the dedicated I/O / control space. That gives 8 K minus 256 of usable virtual page 7. Cross-reference (consolidated from both Tepolt manuals):

| Range | Owner |
|-|-|
| `$FF00-$FF03` | PIA 1 (keyboard, joystick fire, sound enable, selector switch CA2/CB2) |
| `$FF20-$FF23` | PIA 2 (DAC bits 7-2, joystick selector CB2 master, motor CA2, serial); `$FF22` bits 7-3 also drive the GIME VDG-mode register |
| `$FF40, $FF48-$FF4B` | Disk controller (cartridge slot) |
| `$FF90-$FF9F` | GIME init / mode / video / scroll / offset / border |
| `$FFA0-$FFAF` | GIME MMU PARs |
| `$FFB0-$FFBF` | GIME palette registers |
| `$FFC0-$FFC5` | SAM V2/V1/V0 mode (legacy lo-res) |
| `$FFC6-$FFD3` | SAM F6..F0 video starting address (legacy lo-res) |
| `$FFD4-$FFD5` | SAM page bit P1 |
| `$FFD6-$FFD9` | SAM R1/R0 MPU clock (`$FFD9` = fast, `$FFD8` = slow) |
| `$FFDA-$FFDD` | SAM M1/M0 memory size |
| `$FFDE-$FFDF` | SAM TY (`$FFDF` = all-RAM, `$FFDE` = ROM/RAM) |
| `$FFF2-$FFFF` | 6809 vector table (mirrored from ROM `$BFF2-$BFFF`): SWI3, SWI2, FIRQ, IRQ, SWI, NMI, RESET (high addr last) |

The SAM register pairs use *write anything to set vs. clear* semantics — the data on the bus is irrelevant.

## Cartridge boot

When a cartridge is plugged into the right-side slot, its upper 16 K occupies physical `$3E-$3F` at virtual `$C000-$FEFF` while TY=0 and Init0 ROM-map = default. Pin 8 (CART) of the cartridge edge is wired to PIA 2 CB1, which generates a FIRQ during BASIC's reset routine — the FIRQ handler examines `$C000` for a magic and, if present, jumps there. **This is Ladybug's entry point: the first bytes of the cartridge ROM at virtual `$C000` are our boot.** See [cartridge.md](cartridge.md).

**Ladybug uses a 32 K cart** (decision 2026-05-08): after taking control, our boot writes Init0 b1-b0 = `11` to switch to "32 K cartridge" mode. BASIC ROM at `$8000-$BFFF` disappears and our cart's lower 16 K appears there. Tables (tiles, sprites, palette, fonts, maze, sound) live in that lower-16 K region; code and the autostart magic live in the upper 16 K (`$C000-$FEFF`) where the BASIC FIRQ handler dispatches. After we copy whatever cart-ROM data we need into RAM, we set TY=1 and the cart is gone for the rest of the run.

## CoCo 3 quirks worth knowing

- **128 K aliasing.** On a 128 K machine, the two top expanded-address bits Y18/Y17 are unused, so physical pages `$30-$3F` alias through `$00-$0F`, `$10-$1F`, `$20-$2F`. Don't write code that depends on the alias — it breaks on a 512 K machine.
- **`$FE00-$FEFF` jump table.** Init0 bit 3 set forces this 256-byte slice to always come from physical page `$3F` regardless of PAR7. We will set this bit so the primary jump table at `$FEEE-$FEFF` is always reachable while we re-map other pages.
- **Vertical-offset registers point at physical RAM directly**, bypassing the MMU. The GIME reads the screen buffer using the expanded address it builds from `$FF9D/$FF9E`, so screen RAM doesn't need to be currently mapped into a virtual page unless the MPU also wants to update it.

## Sources

- [../sources/coco-asm-tepolt.md](../sources/coco-asm-tepolt.md) ch. 9, App. E
- [../sources/coco3-asm-tepolt.md](../sources/coco3-asm-tepolt.md) ch. 3, 7
