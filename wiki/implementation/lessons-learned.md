---
name: Lessons learned
description: Observed-fact findings — hardware quirks, register gotchas, patterns to avoid, and explicit decisions to skip otherwise-tempting precedents.
type: finding
tags: [implementation, lessons, gotchas]
updated: 2026-05-15
---

# Lessons learned

Append-only. Each entry: a short claim, the *why*, and (where applicable) a concrete citation.

---

## DoD anti-patterns we will NOT copy

Filed 2026-05-08 alongside ingest of the DoD cartridge source. See [sources/dod-source.md](../sources/dod-source.md) and [coding-conventions.md](coding-conventions.md) for what we *are* adopting.

### Tape (cassette) I/O

DoD carries a substantial cassette save/load layer in [`COMMON.ASM:24-96`](../../docs/reference/DungeonsOfDaggorath-main/COMMON.ASM) (GETBUF, PIATAP, SAVE, LOAD) plus the entire [`PZTAPE.ASM`](../../docs/reference/DungeonsOfDaggorath-main/PZTAPE.ASM) module. **Skip entirely.** We are cartridge-only with no persistence in v1 (decision locked 2026-05-07; see log entry of that date and [platform/cartridge.md](../platform/cartridge.md)).

### CoCo 1/2 SAM and legacy PIA initialisation

DoD's [`ONCE.ASM:31-49`](../../docs/reference/DungeonsOfDaggorath-main/ONCE.ASM) writes a hard-coded SAM/PIA configuration aimed at CoCo 1/2 hardware. The CoCo 3's GIME (ACVC) supersedes the SAM and the PIA layout is largely the same but with extensions ([`platform/gime.md`](../platform/gime.md), [`platform/input.md`](../platform/input.md)). **Do not adapt this routine line-for-line.** Re-derive boot init from the GIME register catalog and our cartridge boot strategy ([`platform/cartridge.md`](../platform/cartridge.md)).

### 3D vector-graphics macros

[`VCTLST.ASM`](../../docs/reference/DungeonsOfDaggorath-main/VCTLST.ASM) and the `SVORG` / `SVECT` / `SVEND` macros in [`missing-macros.asm`](../../docs/reference/DungeonsOfDaggorath-main/missing-macros.asm) implement DoD's first-person dungeon-vector renderer. Lady Bug is tile-based 2D — none of this applies.

### 24-bit fixed-point shift chains

[`HUPDAT.ASM:29-67`](../../docs/reference/DungeonsOfDaggorath-main/HUPDAT.ASM) does multi-byte LSL/ROL chains for heartbeat-rate scaling. Elegant but specific to DoD's analogue-feeling timing. Unless we add fade effects or analogue-feeling animations, integer counters are simpler and faster.

### BASIC ROM trampolines

Various DoD spots dispatch into BASIC ROM (`BLKIN`/`BLKOUT`, SWI2 to BASIC). We've already locked **all-RAM mode** post-boot ([`platform/cartridge.md`](../platform/cartridge.md), 2026-05-07 boot decision), so anything that re-enters BASIC ROM after init is unavailable to us by design. Don't borrow patterns that assume it's there.

---

---

## Phase 0 verified — `"DK"` autostart works as documented

Filed 2026-05-08 at the Phase 0 review gate (see [roadmap.md](roadmap.md)).

A 22-byte stub at `$C000` with the layout `FCC "DK"` + entry code took control on XRoar with `-cart-autorun`. The screen showed our 32-byte `$AA` marker on row 0 and BASIC's default `$60` green fill below — confirming BASIC reset-init runs to its screen-clear step but our FIRQ-dispatched code grabs control before any banner or `OK` prompt prints.

**Why it matters:** confirms the boot path described in [../platform/cartridge.md](../platform/cartridge.md) is correct as written. `"DK"` magic + entry at `$C002` is the convention; no tweaking needed.

**Applies to:** every future cartridge build — keep `FCC "DK"` as the first emitted bytes at `$C000`.

**Citation:** [src/main.s](../../src/main.s) at the Phase 0 commit; [platform/cartridge.md §Boot handshake](../platform/cartridge.md).

### SG4 byte semantics — for sanity

While debugging the marker rendering: a CoCo VDG byte with bit 7 set is interpreted as semigraphic-4 (SG4), with bits 6-4 selecting one of 8 colors and bits 3-0 lighting the four 2x2-pixel quadrants of the cell. `$AA = 10101010` = SG4, color blue (`010`), quadrants top-right + bottom-left lit. That's why `$AA` reads as diagonal blue stripes rather than a uniform block. Worth knowing if we ever fall back to the legacy text screen for a debug HUD.

---

---

## Phase 1 verified — boot init + 60 Hz Vbord IRQ

Filed 2026-05-08 at the Phase 1 review gate.

A 95-byte boot sequence (`src/main.s`) takes us from the Phase 0 takeover to a stable 60 Hz tick: DP=$02, all-RAM, 1.78 MHz, IRQ handler installed at the `$FEF7` jump-table slot, only Vbord enabled in `$FF92`. Visible signal: a 16-bit IRQ-incremented counter rendered to `$0400/$0401` on the legacy VDG text screen — high byte advances every ~4.27 s, low byte flickers fast. Both behaviours observed on XRoar.

**Why it matters:** confirms the boot recipe in [../platform/cartridge.md §What our boot must do](../platform/cartridge.md) is correct *as a starting point*, with the Phase-1 simplification of leaving COCO legacy mode on (`Init0` b7=1) so the existing $0400 text screen remains usable without configuring GIME hi-res video.

**Applies to:** every cartridge build until Phase 2 supersedes the video path. The PIA-quieting + IRQ-install sequence carries forward unchanged.

**Citation:** [`src/main.s`](../../src/main.s) at the Phase 1 commit.

### SWI / IRQ vector collision — RESOLVED

Filed 2026-05-08 at the Phase 1 review gate, deferred from [coding-conventions.md §4](coding-conventions.md).

Concern was whether using `SWI` (and `SWI2`/`SWI3`) as a syscall trap could collide with the GIME's IRQ/FIRQ paths. **No collision.** SWI is a CPU instruction — software-only — with hardware vectors at `$FFFA/$FFFB` (SWI), `$FFF4/$FFF5` (SWI2), `$FFF2/$FFF3` (SWI3). The GIME's IRQ uses `$FFF8/$FFF9`, FIRQ uses `$FFF6/$FFF7`. Disjoint. BASIC ROM uses SWI2/SWI3 internally for floating-point and monitor calls, but once we're in all-RAM mode and not entering BASIC, all six vector slots and their `$FE00-$FEFF` jump-table indirections are ours.

**Applies to:** the syscall-layer plan in [coding-conventions.md §4](coding-conventions.md) — go ahead and use `SWI` (and `SWI2`/`SWI3` if needed) as service traps when the implementation gets there.

---

---

## Phase 2.1 verified — shadow-RAM-during-write at phys `$3E`

Filed 2026-05-08 at the Phase 2.1 sub-gate.

Wrote `$5A` ('Z') to `$C000` while in TY=0 (cart ROM mode), then set TY=1 (all-RAM), then read `$C000` — got `$5A` back. Confirms that writes to cart-ROM-shadowed virtual addresses land in the underlying RAM, even though reads come from ROM. This is the load-bearing assumption for the boot data-copy procedure in [memory-map.md](memory-map.md).

**Why it matters:** the boot can self-copy the cart's contents to RAM (`ldd ,x` / `std ,x` over `$C000-$FEFF`) and then enter all-RAM mode, with the same bytes still at the same virtual addresses. Code keeps running. No PAR juggling, no separate copy buffer.

**Applies to:** every cartridge boot from here on.

**Citation:** [src/main.s](../../src/main.s) at the Phase 2.1 commit (since superseded by Phase 2.2's integrated boot).

## XRoar `-cart-rom` handling of 32 K files — UNVERIFIED

Filed 2026-05-08 alongside Phase 2.1.

Built a 32 K cart with data section at lwasm `$8000` (file offset 0, intended for visibility once Init0 b1-b0 = `11`) and code section at lwasm `$C000` (file offset `$4000`). Boot didn't autostart — landed at the BASIC `OK` prompt. Symptom is consistent with XRoar mapping the lower 16 K of the file to virtual `$C000` regardless of file size, which would put our data byte (`$31`) at `$C000` instead of the `"DK"` magic.

XRoar's manual only documents `-cart-rom` as "mapped from `$C000`" — silent on 32 K behaviour. Source-code inspection or experimental probing would be needed to confirm. **Not done.** Reverted to a 16 K cart for development and recorded the unknown.

**Why it matters:** if we hit the 16 K limit (Phase 4), the planned expansion path cannot rely on Init0 b1-b0 = `11` working under XRoar. Use `-cart-type gmc` (software bank-switching) instead — that's universally supported, and the architecture is the same as CoCoSDC and other real-hardware cart shells.

**Applies to:** the cart-size pivot path in [../platform/cartridge.md §"Cart size — 16 K (current)"](../platform/cartridge.md). Use bank-switched, not Init0=11.

---

---

## Phase 2.2 + 2.3 verified — full Phase 2 boot path through to GIME hi-res

Filed 2026-05-08 at the Phase 2.3 close.

The full boot sequence works end-to-end on XRoar:

1. ORCC IRQ-mask, set DP=$02, stack at $1FFE.
2. Quiet PIA interrupts.
3. Init0 = legacy / ACVC-IRQ on / force-$FExx.
4. Self-copy `$C000-$FEFF` (cart ROM) to shadow RAM via `LDD ,X / STD ,X`.
5. TY=1 (`$FFDF`) — cart disconnects, code now runs from RAM at phys $3E-$3F.
6. R1=1 (`$FFD9`) — fast clock (1.78 MHz).
7. `$FF91` cleared so executive PAR set is active.
8. PARs loaded — `$38, $30, $31, $32, $33, $3D, $3E, $3F` — virtual `$2000-$9FFF` now points to phys `$30-$33` (FB).
9. `$FF98` BP=1, `$FF99` = `$1F` (CRES=11 blanked) so we can clear silently.
10. Vert-offset `$FF9D=$C0`, `$FF9E=$00` — GIME reads FB from physical address `$060000` (phys page $30).
11. Init0 changed to MMU=1 + COCO=0 (hi-res). Display still blanked due to CRES=11.
12. Palette loaded into `$FFB0-$FFBF`.
13. FB written.
14. `$FF99` = `$1E` — un-blank, 16-color graphics live.
15. IRQ handler installed at `$FEF7`.
16. Vbord enabled, I-mask cleared.
17. Mainloop runs, IRQ ticks at 60 Hz, mainloop's FB writes are visible.

Visible signal: full 16-stripe palette test + bright border + IRQ-driven flashing block on top of stripes.

**Why it matters:** every subsequent phase builds on this exact sequence. Don't reorder steps without re-verifying — particularly the cart self-copy must happen before TY=1, and PAR loads must happen before MMU enable.

**Citation:** [src/main.s](../../src/main.s) at the Phase 2.3-close commit.

## XRoar RGB monitor palette mapping (current default)

Filed 2026-05-16. Canonical mapping for the project — XRoar is invoked with
`-tv-input rgb` by [`scripts/build.sh`](../../scripts/build.sh) and
[`web/backend/instance.py`](../../web/backend/instance.py), and the
[`src/main.s`](../../src/main.s) `palette_table` is tuned to it.

Empirically derived using a minimal-from-scratch 16-stripe diagnostic
([`src/diag_minimal.s`](../../src/diag_minimal.s) — needed because the
full Phase 2.x main.s pipeline currently renders the FB as noise; see
[backlog/phase2-fb-render-regression.md](../backlog/phase2-fb-render-regression.md)).
16 stripes, one palette idx each, sampled visually under `-tv-input rgb`:

| `$xx` | Bits R'G'B' rgb | Observed colour |
|-|-|-|
| `$00` | 000 000 | black |
| `$20` | 100 000 | dark/medium red (R-bright only) |
| `$10` | 010 000 | medium green |
| `$08` | 001 000 | medium blue |
| `$30` | 110 000 | dark yellow / olive |
| `$18` | 011 000 | cyan / teal |
| `$28` | 101 000 | magenta |
| `$38` | 111 000 | light grey / silver — **not white** |
| `$04` | 000 100 | dim red |
| `$02` | 000 010 | dim green |
| `$01` | 000 001 | dim blue |
| `$06` | 000 110 | dark olive |
| `$03` | 000 011 | dark teal |
| `$05` | 000 101 | dark purple |
| `$07` | 000 111 | dark grey |
| `$3F` | 111 111 | bright white |

**Key surprise:** full white is `$3F` (all 6 bits), not `$38` (just the upper 3).
The "bright" channels alone (`R'G'B' = 111`) produce a desaturated light grey;
you have to also turn on the "dim" channels to push to full white. Same
principle for fully-saturated bright primaries: `$24` (R' + dim B) is a
*pinker* red than `$20` (R' alone) because the dim-R bit adds bottom-end
saturation.

**Why it matters:** when we ingest the arcade palette
([sources/arcade-gfx-extraction.md](../sources/arcade-gfx-extraction.md))
we map each arcade RGB triple to the nearest 6-bit GIME code by treating
the code as 2-bit-per-channel `R[1:0] G[1:0] B[1:0]` (high bit = bright,
low bit = dim). The 64-entry CoCo 3 RGB palette is regular enough that
the nearest-match search is mechanical.

**Citation:** [`src/diag_minimal.s`](../../src/diag_minimal.s) 16-stripe
test; user-observed colour names recorded in the 2026-05-16 session log.

---

## Composite NTSC palette mapping (historical, pre-RGB switch)

Filed 2026-05-08 alongside Phase 2.3. **Superseded** by the RGB table
above for the project's canonical use; preserved here because real CoCo 3
owners may run on a composite monitor and want this reference.

Phase 2.3's 16-stripe palette diagnostic under XRoar's default (composite NTSC)
showed the 6-bit palette codes do **not** map via the conventional `RGBrgb`
interpretation — instead, chroma + luma encoding produces different colours
and several codes alias (e.g. `$30` and `$3F` both render as white).

Empirical composite-NTSC 6-bit → colour table:

| `$xx` | Observed colour (composite) |
|-|-|
| `$00` | black |
| `$3F` | white |
| `$30` | white (alias of `$3F`) |
| `$0C` | blue |
| `$03` | green-brown |
| `$33` | yellow |
| `$0F` | forest green |
| `$3C` | baby blue |
| `$20` | grey |
| `$08` | fuchsia / purple |
| `$02` | darker green |
| `$22` | saturated light green |
| `$0A` | purple |
| `$28` | pink |
| `$15` | orange |
| `$24` | orange-yellow |

**Citation:** [src/main.s](../../src/main.s) Phase 2.3 stripe-test commit
(`2593d36`); user-observed colour names recorded in the 2026-05-08 session log.

---

## `LDD ,Y++` clobbers B — never use B as a loop counter alongside it

Filed 2026-05-08.

In the Phase 2.4 `blit_tile` routine the obvious shape was `ldb #8` outside the loop, `decb`/`bne` at the end. Inside the body, `ldd ,y++` reads tile data into D — and **D is A:B**, so every `ldd ,y++` overwrites the loop counter with whatever low byte was just loaded. For a solid-`$33` tile the counter resets to `$33` every iteration, decrements to `$32`, and the loop never terminates (or terminates non-deterministically based on tile content). The bug was invisible to static reading and produced confusing partial-render symptoms that varied by tile data.

**Fix used in `blit_tile`:** compute `leau 32,y` before the loop (sentinel = end of tile data), `pshs u`, then `cmpy ,s` / `blo btrow` for loop control. Y is the natural cursor and Y vs ,s is unaffected by `ldd`. Costs 2 stack bytes, returns them with `leas 2,s`.

**Why:** the 6809 D register is the concatenation A|B; any 16-bit load through D destroys both halves.
**Applies to:** any tight blit/copy loop that uses `ldd ,y++` or `ldd ,x++` for the data and B for iteration counting. Use a stack/memory sentinel or use Y/X comparison instead.
**Citation:** [src/main.s](../../src/main.s) `blit_tile`; debugged in the 2026-05-08 session.

---

## XRoar cartridge-window reads are not uniformly cart-backed

Filed 2026-05-10; expanded 2026-05-12.

Under XRoar 1.10, a minimal cartridge probe that read `$C000-$C0FF` before writing that range found exactly three bad reads: `$C0D9` expected `$00` but read `$7E`, `$C0DA` expected `$00` but read `$E2`, and `$C0DB` expected `$00` but read `$9D`. The main boot copy showed the same failure shape: the copy loop loaded `02 7E` at `$C0D8` and `E2 9D` at `$C0DA`, so the RAM-under-ROM copy faithfully stored bad source bytes. Patching Init0, using explicit `-cart-type rom`, and changing `LDD/STD` to byte `LDA/STA` did not change the result.

On 2026-05-12, `src/rom_probe.s` was extended to read the full `$C000-$FEFF` range. With a 16 KB probe ROM padded with `$FF`, XRoar/GDB reported `$50` mismatches: the known `$C0D9-$C0DB` bytes, `$C8B4-$C8BE` reading `$12` instead of `$FF`, and `$E000-$E042` reading non-cart ROM bytes instead of `$FF`. Live GDB reads confirmed `$C14B+` cartridge padding is visible as `$FF`, so the later mismatches are not a probe-padding error.

**Why:** confirmed as XRoar cartridge-window mapping/read behaviour on this boot path, not a post-copy overwrite and not a word-copy instruction issue.
**Applies to:** boot self-copy from `$C000-$FEFF`. Keep `$C0D9-$C0DB` unused as before; do not assume `$E000+` is cart-backed under this XRoar `-cart-type rom` path without further emulator/source investigation.
**Citation:** [src/rom_probe.s](../../src/rom_probe.s); [src/main.s](../../src/main.s) boot copy skip; debugged with XRoar GDB traps on 2026-05-10.

---

## Cart-shadow self-copy is a no-op under XRoar 1.10 — we execute from cart ROM throughout

Filed 2026-05-15. Four-pass gdb-mcp investigation in [backlog/cart-ram-corruption.md](../backlog/cart-ram-corruption.md) settled this empirically.

The boot model from [memory-map.md](memory-map.md) — "self-copy `$C000-$FEFF` to shadow RAM, flip TY=1, run from RAM" — does not describe how XRoar 1.10 actually runs our cart. Cold-start probes show cart bytes accessible at `$C000-$FDFF` from before the self-copy runs and continuing past `sta SAM_ALLRAM`. The self-copy's `std ,x` writes for x in `$C000-$FDFE` go to `cart_rom_write` (a no-op on a read-only `rombank_d8`) and skip the RAM-write path because the GIME decode returns RAS=0 for that range pre-SAM_ALLRAM. We have been running directly from cart ROM through both halves of the boot. The Phase 2.1 "wrote a marker, flipped TY, read it back" verification is consistent with this — it cannot distinguish "shadow RAM works" from "XRoar serves cart bytes regardless of TY".

`$FE00-$FEFF` is the exception: MC3=1 forces RAS=1 in the inner decode, so reads and writes hit bank-0 RAM symmetrically. The IRQ jump-table slots ARE RAM-backed.

**Why:** XRoar's `coco3.c read_byte` / `write_byte` use a `S=1 (CTS), RAS=0` path for the cart window under our boot state; the `if (RAS)` RAM-overlay block is skipped on reads and writes. `cart_rom_write → rombank_d8` is read-only. So nothing the boot does to `$C000-$FDFF` ever reaches RAM, and the bytes we read there come straight from cart ROM.

**Applies to:**
- Don't put self-modifying code at `$C000-$FDFF` — it will silently fail on XRoar.
- Don't expect runtime-mutable data tables in that range under emulation.
- The `org $C0DC` workaround for the XRoar bad-window quirk is still correct, but its rationale shifts: those bad bytes are bad in cart space, not in some post-copy RAM image.
- Real-hardware behavior is unverified. The arcade-fidelity boot design is preserved in source — leave the self-copy in place so it works correctly on hardware (Phase 10) — but treat it as dead code when reasoning about XRoar runs.
- Trust empirical gdb-mcp probes over XRoar source review for GIME questions; the source has a known decode gap we couldn't fully resolve (see [memory-map.md §Open items](memory-map.md)).

**Citation:** [backlog/cart-ram-corruption.md](../backlog/cart-ram-corruption.md) (third and fourth gdb-mcp passes); [src/main.s](../../src/main.s) cart-shadow loop at lines 102-118; XRoar source under `docs/reference/xroar/src/{tcc1014/tcc1014.c, coco3.c, cart.c, rombank.h}`.

---

## XRoar gdb readback of GIME write-only registers

Filed 2026-05-16.

XRoar's gdb stub does **not** snoop write-only register writes. Reads of `$FF90` and `$FF98..$FF9E` all return the same fixed sentinel byte `$1B` regardless of what the program wrote — confirmed against a running `build/diag.rom` (built from [diag_minimal.s](../../src/diag_minimal.s)) after it wrote `$FF90=$08, $FF98=$80, $FF99=$1E, $FF9A=$28, $FF9D=$E4, $FF9E=$00` and halted in its `bra halt` self-loop. The gdb channel itself is sound: the 16-byte palette at `$FFB0..$FFBF` reads back byte-for-byte, and the PARs at `$FFA0..$FFA7` return the GIME reset state `38 39 3A 3B 3C 3D 3E 3F` (linear-64K mapping; PARs are R/W).

**Why:** real GIME registers in the `$FF90/$FF98..$FF9E` block are write-only; XRoar's stub does not maintain a shadow on the host side, so reads pass through to whatever the emulator returns for inaccessible bus addresses (here, a fixed `$1B`). Same as on real hardware — there is no readback path in silicon either.

**Applies to:** WS-A of the [emulator-monitor-tester](emulator-monitor-tester.md) initiative — the decision gate between strategy options 1/2/3 for GIME-state visibility. **Option 1 (DirectReadStrategy) is not viable on XRoar.** Decision: WS-A adopts **Option 2 (ProgramStateStrategy)** — the tester ROM exports `tester_mode_idx` + `tester_mode_table` symbols and the backend reads program state via those symbols. Option 3 (software shadow block) remains available for future generalization but is not needed for the tester.

**Citation:** probe script [web/scripts/probe_gime_readback.py](../../web/scripts/probe_gime_readback.py); writes performed at [src/diag_minimal.s:39-93](../../src/diag_minimal.s); strategy table in [emulator-monitor-tester.md §WS-A](emulator-monitor-tester.md).

---

## Format for future entries

```
### <Short title>

Filed YYYY-MM-DD.

<One-paragraph claim — what was learned, what surprised us, what to avoid or repeat.>

**Why:** <root cause or rationale>
**Applies to:** <code area / decision / module>
**Citation:** <file:line or wiki page>
```
