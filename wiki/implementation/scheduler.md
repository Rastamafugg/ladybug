---
name: Cooperative scheduler (candidate pattern)
description: TCB-based round-robin scheduler sketched from DoD's design. Candidate, not committed — revisit when the main loop is implemented.
type: design-candidate
tags: [implementation, scheduler, main-loop, candidate]
updated: 2026-05-08
---

# Cooperative scheduler — candidate design

**Status:** candidate pattern, not yet decided. Filed because DoD uses one and Lady Bug has a handful of independent timed activities (bug spawner, vegetable cycle, score-letter colour flip, skull movement, EXTRA/SPECIAL animation) that map cleanly onto the same shape. Revisit when the main loop reaches implementation.

## What DoD does

Round-robin scheduler over a linked list of Task Control Blocks (TCBs) held in `SCDQUE`. Each task runs to completion on its turn, then returns:

- `A` — countdown ticks until the task should run again
- `B` — pointer to the next queue entry

Initialisation data lives in [`COMDAT.ASM:36-42`](../../docs/reference/DungeonsOfDaggorath-main/COMDAT.ASM) — the original TCB set covers PLAYER, delayed display update, heartrate update, torch decay, and creature regeneration.

The scheduler header lives at [`COMMON.ASM:1-20`](../../docs/reference/DungeonsOfDaggorath-main/COMMON.ASM) (comment block describing the contract). Per-frame display work in [`PUPDAT.ASM:6-9`](../../docs/reference/DungeonsOfDaggorath-main/PUPDAT.ASM) draws to the alternate buffer then issues a `SYNC` and waits for vsync.

## How it would map to Ladybug

Likely TCBs:

| Task | Approximate period | Notes |
|-|-|-|
| Bug AI step | 1–4 frames per bug | Speed scales with stage. |
| Skull AI step | similar to bug | Possibly faster on later stages. |
| Vegetable spawn timer | seconds | Drives the EXTRA/SPECIAL/vegetable cycle on the right HUD. |
| Colour cycle flip | seconds (TBD) | Global; one task flips the shared colour state. |
| Score / extra-life check | per frame | Cheap; could just be inline in the main loop. |
| Sound dispatch | per frame | Drains a queue of pending SFX. |

## Pros vs alternatives

| Approach | Pro | Con |
|-|-|-|
| **DoD-style TCB queue** | Decouples timed activities cleanly; new behaviours just add a TCB. | One indirection per task; small per-tick overhead. |
| **Hand-coded main loop with explicit countdowns** | Zero overhead; one branch per timed activity. | Adding a new timed activity touches the loop. |
| **Slot-based frame schedule (e.g. each sub-system gets a fixed frame slot mod N)** | Most predictable timing. | Awkward when periods aren't multiples. |

For Lady Bug — a small fixed cast of timed activities with reasonably stable cadence — the hand-coded main loop is probably enough. The TCB pattern earns its keep when the *number* of timed activities is open-ended (DoD has variable creature counts and torch-decay dynamics). Decision deferred until the implementation phase.

## Decision criteria

Choose TCBs only if at least one of these is true once we start coding:

1. The list of per-frame jobs grows past ~6 and starts feeling unwieldy in a flat main loop.
2. We need data-driven activation (e.g. enabling/disabling activities from level data).
3. Vegetable / colour-cycle timing turns out to be irregular enough that table-driven countdowns are cleaner than hand-rolled counters.

Otherwise: stick with a flat main loop.

## Sources

- [`COMMON.ASM:1-20`](../../docs/reference/DungeonsOfDaggorath-main/COMMON.ASM) — scheduler contract.
- [`COMDAT.ASM:36-42`](../../docs/reference/DungeonsOfDaggorath-main/COMDAT.ASM) — initial TCB table.
- [`PUPDAT.ASM:6-9`](../../docs/reference/DungeonsOfDaggorath-main/PUPDAT.ASM) — display task vsync handshake.
- [sources/dod-source.md](../sources/dod-source.md), [coding-conventions.md](coding-conventions.md).
