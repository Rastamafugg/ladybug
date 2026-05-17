---
name: MAME comparison test for cart-ROM-to-RAM write-through
description: Run the same cart-ROM-to-RAM self-copy under MAME's CoCo 3 driver and compare against XRoar 1.10's broken cart-window write path.
type: backlog
tags: [tooling, xroar, mame, emulator-fidelity, bus-model]
updated: 2026-05-16
---

# MAME cart-ROM-to-RAM comparison test

Cross-check whether XRoar's cart-window write-suppression is unique to XRoar or whether MAME's CoCo 3 driver exhibits the same divergence from documented hardware behavior.

## Context

XRoar 1.10 does not write RAM-under-ROM for CPU-space writes in `$C000-$FDFF` when `TY=0`. Root cause is source-confirmed at [`coco3.c:1170-1240`](../../docs/reference/xroar/src/coco3.c) — the `RAS=0` gate skips the RAM-overlay write while `S=1` routes the write to the read-only cart bank. See [implementation/lessons-learned.md §XRoar cart-window write decode](../implementation/lessons-learned.md).

The documented real-hardware contract is that writes pass through to DRAM regardless of TY. Before locking that interpretation we want a second-emulator opinion. MAME's CoCo 3 driver is the most thorough open-source model in active use; the user has it set up under Ubuntu WSL.

## Test plan

Goal: replay the boot-time self-copy and observe whether the underlying RAM page is written.

1. Build a minimal cart (~16 KB) with:
   - `"DK"` magic + entry stub at `$C000` (per [platform/cartridge.md](../platform/cartridge.md)).
   - Code that, with `TY=0` still in effect, writes a known sentinel (e.g. `$5A`) to `$C100`, then flips TY=1 via `STA $FFDF`, then reads `$C100` and stores the result at a known RAM observation address (e.g. `$0400` so it shows up on the legacy text screen, or `$FE00-$FEFF` which is RAM-backed in both emulators).
   - Halt loop afterward.

2. Run under MAME: `mame coco3 -cart <path>.rom` (exact invocation TBD — record working command in [tooling/](../tooling/) when figured out). Use MAME's debugger (`-debug`) to inspect the observation byte, and to dump the physical RAM page that backs `$C100` via the GIME's PAR mapping.

3. Run the same ROM under XRoar for direct A/B comparison — expected to show the sentinel **not** present in RAM.

4. Record outcome in this page, then propagate findings:
   - If MAME shows the sentinel landed in RAM: confirms XRoar is the outlier; the hardware-contract interpretation in [xroar-monitor.md](../implementation/xroar-monitor.md) (physical-space write is the right primitive) stands unchanged.
   - If MAME also drops the write: re-open the question — either both emulators are wrong (unlikely; document research from MAME's CoCo 3 driver source), or our reading of the hardware spec is wrong. Update [platform/memory.md](../platform/memory.md) and the monitor design accordingly.

## Effort

Small. Cart build reuses existing lwasm + [`scripts/build.sh`](../../scripts/build.sh) pipeline; MAME debug session is interactive. Estimate: 1-2 hours including writing up the result.

## Priority

Not blocking the XRoar monitor Phase 2 implementation plan — the physical-space write API is correct under either MAME outcome (it writes the emulator's RAM array directly, bypassing whatever bus model the host emulator implements). But the result feeds the eventual Phase 10 hardware bring-up: if MAME confirms the hardware contract, we can ship the Ladybug ROM to real CoCo 3 with higher confidence that the documented self-copy path actually works there.

## Sources

- [implementation/lessons-learned.md §XRoar cart-window write decode](../implementation/lessons-learned.md)
- [implementation/lessons-learned.md §Cart-shadow self-copy is a no-op under XRoar 1.10](../implementation/lessons-learned.md)
- [implementation/xroar-monitor.md §Address-space model](../implementation/xroar-monitor.md)
- [platform/cartridge.md](../platform/cartridge.md)
- MAME source: `src/mame/trs/coco3.cpp` (and related drivers; not yet ingested into wiki)
