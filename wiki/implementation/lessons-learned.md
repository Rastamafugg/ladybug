---
name: Lessons learned
description: Observed-fact findings — hardware quirks, register gotchas, patterns to avoid, and explicit decisions to skip otherwise-tempting precedents.
type: finding
tags: [implementation, lessons, gotchas]
updated: 2026-05-08
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

## Format for future entries

```
### <Short title>

Filed YYYY-MM-DD.

<One-paragraph claim — what was learned, what surprised us, what to avoid or repeat.>

**Why:** <root cause or rationale>
**Applies to:** <code area / decision / module>
**Citation:** <file:line or wiki page>
```
