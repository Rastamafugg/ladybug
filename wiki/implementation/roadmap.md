---
name: Implementation roadmap
description: Phased plan from empty src/ to finished game. Each phase has a proof-of-concept exit criterion and a review gate. Living document — adjust at every gate.
type: roadmap
tags: [implementation, roadmap, planning]
updated: 2026-05-08
---

# Implementation roadmap

From the current state (tooling validated, design + boot strategy locked, `src/` empty) to a finished single-cart Lady Bug for the CoCo 3.

## How to use this document

- Phases are **sequential** by default — each one's exit criterion gates the next.
- Each phase ends with a **review gate** where we re-read this roadmap, update it from what we learned, and decide whether the next phase still makes sense as written.
- Every gate also triggers an append to [lessons-learned.md](lessons-learned.md). New conventions go to [coding-conventions.md](coding-conventions.md). Anti-patterns go to lessons-learned.
- A POC is "minimum thing that proves the phase works." It's allowed to be ugly.

## Current state (start of Phase 0)

- Wiki: design [game/overview.md](../game/overview.md), platform pages, tooling pages, DoD-derived [coding-conventions.md](coding-conventions.md).
- Tooling: `scripts/build.sh build|run|clean` validated end-to-end against the DoD source as a smoke test. lwasm 4.24 + xroar 1.10 in WSL.
- Boot strategy locked: cart at `$C000`, BASIC's CART → FIRQ handshake to take control, then all-RAM mode + 1.78 MHz + ACVC Vbord IRQ at 60 Hz ([platform/cartridge.md](../platform/cartridge.md)).
- `src/` does not exist.

---

## Phase 0 — Hello cart (boot handshake) ✅ DONE 2026-05-08

**Goal:** smallest possible cartridge that takes control from BASIC and proves we own the machine.

**POC tasks:**
1. Create `src/main.s` with a 3-line stub: `ORG $C000`, an entry vector compatible with the BASIC CART/FIRQ handshake, an infinite `BRA *` (or write a known byte to a known screen address before the loop, so we can see the takeover).
2. Build, autorun under XRoar, confirm the screen shows our marker (or remains frozen on a non-BASIC display).

**Exit criterion:** `scripts/build.sh run` boots straight to our stub on XRoar without dropping to the BASIC `OK` prompt.

**Review gate Q's:**
- Did the FIRQ handshake work as documented in [platform/cartridge.md](../platform/cartridge.md)? Any gotchas to record?
- Is `scripts/build.sh` ergonomic for daily edit-build-run, or does it need a watch mode?
- Does our cartridge header layout match what we expect to flash to a 16K EPROM later?

---

## Phase 1 — Boot init: all-RAM, DP, vsync IRQ ✅ DONE 2026-05-08

**Goal:** establish the runtime environment our code will assume forever afterward.

**POC tasks:**
1. Set MMU to all-RAM mode (no ROM in the address space).
2. Set DP to the chosen page (decision: pick the page now and document in [coding-conventions.md](coding-conventions.md) §1).
3. Switch CPU to 1.78 MHz.
4. Initialise PIA1/PIA2 ourselves (don't trust BASIC's leftovers).
5. Install Vbord IRQ handler that does nothing but increment a frame counter. Print/poke the counter to a fixed memory location so we can watch it tick on screen.
6. `BRA *` main loop.

**Exit criterion:** XRoar shows the frame counter incrementing at 60 Hz. Confirm in the trace log that no FIRQ/IRQ from any other source fires.

**Review gate Q's:**
- Is our IRQ enable mask actually masking everything but Vbord? (Re-check against [platform/timing.md](../platform/timing.md).)
- Does `SWI` collide with anything we'll need later? — pending question from [coding-conventions.md §4](coding-conventions.md). **Resolve at this gate** before any further code uses SWI.
- Capacity check: how many bytes did we burn on init? Project that against the 16 KB cart budget.

---

## Phase 2 — Display foundation: video mode + char output (in progress 2026-05-08)

**Substep status:**
- 2.1 ✅ shadow-RAM-during-write at phys $3E verified
- 2.2 ✅ cart self-copy + all-RAM transition; IRQ ticks from RAM
- 2.3 ✅ GIME hi-res 320×192×16 + MMU + PARs + framebuffer writes + palette load + IRQ-driven FB writes from mainloop
- 2.4 — render an arcade tile from `assets/arcade/chars.json` (next)
- 2.5 — automate tile/palette pipeline with `build_gfx.py` (deferred until 2.4 hand-validation passes)


**Goal:** pick the GIME video mode, get a stable framebuffer, render text reliably.

**POC tasks:**
1. Pick a video mode (decision point — write the chosen mode + rationale to a new `wiki/implementation/video-mode.md`). Candidates per [platform/gime.md](../platform/gime.md): 320×192 16-color, 256×192 16-color, or a hi-res text mode.
2. Configure GIME to that mode in init; clear the framebuffer to a known colour.
3. Implement `SVC_PUTC` (or a regular `JSR` equivalent) — render a single character glyph from a font table at a tile coordinate.
4. Print "LADYBUG" at the top of the screen.

**Exit criterion:** stable picture in XRoar, no flicker, "LADYBUG" visible.

**Review gate Q's:**
- Does the chosen mode have enough resolution and palette for the playfield + HUD as described in [game/overview.md](../game/overview.md)?
- Memory cost of the framebuffer — does it fit comfortably alongside our code?
- Is our font/glyph format what we want for the HUD numbers and letters too, or do we need separate large/small fonts?

---

## Phase 3 — Tile renderer + static maze

**Goal:** render the playfield from data, no entities yet. Validates the data-driven approach.

**POC tasks:**
1. Define a tile format (8×8? 8×16? — record decision).
2. Author the maze layout as a 2D array of tile indices in a new data module (`DAT_MAZE.S` or similar). Includes turnstile gates and dot positions.
3. Implement the tile renderer: walk the maze array, blit each tile.
4. Render once at boot and stop.

**Exit criterion:** the full Lady Bug playfield is visible and correct against the design doc — outer walls, inner walls, turnstiles, all 20 gates, dots in their starting positions.

**Review gate Q's:**
- Render time budget — how many cycles did the full maze take? Project that against the 60 Hz frame budget if we re-render every frame vs only dirty tiles.
- Does the maze layout *look* right at this resolution? (User judgement call.)
- Is the tile format tractable for both static maze tiles and animated entities, or do we need a separate sprite format?

---

## Phase 4 — Input + Lady Bug sprite (joystick walking)

**Goal:** a controllable Lady Bug sprite walks the maze, no AI yet.

**POC tasks:**
1. Joystick X/Y read via PIA2 DAC + comparator ([platform/input.md](../platform/input.md)).
2. Define the Lady Bug sprite frames (animation table).
3. Sprite renderer that XORs / saves-restores the background under the sprite.
4. Movement code: discrete tile-aligned movement with intermediate animation, blocked by walls, redirected by turnstiles.

**Exit criterion:** Lady Bug walks the maze under joystick control, can rotate turnstiles, can eat dots (dot disappears, no scoring yet).

**Review gate Q's:**
- Does the movement *feel right* against arcade footage? If not — root cause: wrong tile pacing, wrong frame timing, wrong input deadzone? Record the finding.
- Sprite renderer cost — sustainable when we have skulls + bugs + letters all moving?
- Decision point: do we still want the [scheduler.md](scheduler.md) TCB pattern, or is the flat main loop fine? Re-evaluate now that we've seen the per-frame work.

---

## Phase 5 — Scoring HUD + maze logic

**Goal:** complete the no-enemy game loop. Eating all dots advances to the next stage.

**POC tasks:**
1. Score, lives, level counters in DP.
2. HUD layout per [game/overview.md](../game/overview.md): left panel (score/lives/level), right panel (placeholder for EXTRA/SPECIAL/vegetable — implemented in Phase 7).
3. Dot-eating awards points; HUD updates.
4. Stage-clear detection: all dots gone → reset maze, increment level.
5. Death → life lost (placeholder, since no enemies yet — can be triggered by a debug key for now).

**Exit criterion:** loop of clear-stage → next-stage works indefinitely. Score and HUD accurate.

**Review gate Q's:**
- Is the HUD update path fast enough to do per-frame, or do we need dirty-rect tracking?
- Stage progression structure good for adding the difficulty curve later?

---

## Phase 6 — Enemies: bug spawner + skull AI

**Goal:** the game becomes Lady Bug.

**POC tasks:**
1. Bug entity record (`BUG.X`, `BUG.Y`, `BUG.STATE`, `BUG.LEN`); fixed-size pool.
2. Border-circuit spawn timer driving bug entry through the gates.
3. Bug AI — start with simple "head toward Lady Bug, redirected by turnstile state" behaviour. Refine against arcade reference at the gate.
4. Skull entity + simple movement.
5. Collision → life lost; reset positions.

**Exit criterion:** playable. You can lose the game. Multiple bugs on screen at once.

**Review gate Q's:**
- AI behaviour against arcade reference — what's authentic, what's our adaptation? Update [game/overview.md](../game/overview.md) decisions block.
- Per-frame cost with full enemy load — still meeting 60 Hz?
- Does the entity-pool size need tuning? Memory budget check.

---

## Phase 7 — Letters + vegetable cycle + colour cycle

**Goal:** the EXTRA/SPECIAL/vegetable system from the design doc.

**POC tasks:**
1. Global colour-cycle state in DP, advanced by a timed task.
2. Letter entities (E, X, T, R, A / S, P, E, C, I, A, L), placement and collection logic.
3. Vegetable spawn timer + the 18-vegetable cycle ordered table.
4. Heart entity (×2 / ×3 / ×5 multiplier when colour matches).
5. SPECIAL completion → 10,000-point award.
6. EXTRA completion → +1 life.

**Exit criterion:** the right HUD panel cycles correctly; collecting at the right colour advances the right target; all three reward paths trigger.

**Review gate Q's:**
- Cycle period and colour-to-target mapping — these were deferred decisions ([log.md 2026-05-05 decision](../log.md)). Lock them now based on play feel.
- Any visual hierarchy problems with so many simultaneously-cycling colours?

---

## Phase 8 — Sound

**Goal:** SFX + minimal melody.

**POC tasks:**
1. SFX engine — DAC samples or square waves on PB1 ([platform/sound.md](../platform/sound.md)).
2. SFX descriptor table; queue dispatched per frame.
3. Sounds for: dot eat, letter collect, vegetable collect, life lost, stage clear, extra life.
4. Optional: short title-screen melody.

**Exit criterion:** every game event has audible feedback; no audible glitching during heavy enemy load.

**Review gate Q's:**
- Cycle cost of sound dispatch — fits in the frame budget?
- Are we using the 6-bit DAC, the 1-bit PB1, or both? Document final choice.

---

## Phase 9 — Polish, attract mode, high score, level progression

**Goal:** finished game.

**POC tasks:**
1. Title / attract screen.
2. Difficulty curve (skull count or bug speed scaling per stage — pick one and document).
3. 30,000-point bonus-life award (one-time, per locked decision).
4. Game-over flow → back to title.
5. High-score display (session-only — no battery-backed RAM).
6. Final maze/sprite/colour polish pass.

**Exit criterion:** plays start-to-finish, looks and feels like Lady Bug, no obvious bugs, fits in cart (16 K target; 32 K / banked acceptable if the expansion was triggered earlier).

**Review gate Q's:**
- ROM size — actual vs 16 KB budget. If we overflowed: compress sprites (2bpp+attr / RLE), curate harder, or pivot to bank-switched cart (see [../platform/cartridge.md §"Cart size — 16 K (current)"](../platform/cartridge.md)).
- What's the dev-loop pain we'd fix if we did this again? File to lessons-learned.

---

## Phase 10 — Real hardware bring-up

**Goal:** runs on a physical CoCo 3 from a 16K EPROM in a cart shell.

**POC tasks:**
1. Burn the ROM to EPROM.
2. Boot on real hardware.
3. Compare against XRoar — note any divergences (timing, palette, sound).

**Exit criterion:** hardware run matches XRoar. Any divergences are explained or fixed.

**Review gate Q's:**
- Emulator-vs-hardware divergences — file each one to lessons-learned with the cause.
- **Cart-shell compatibility check.** Does the target cart shell (CoCoSDC, RetroCloud, custom 32 K PCB, etc.) actually respond to the GIME's `$8000-$BFFF` accesses when Init0 b1-b0 = `11` is set? If not, pivot to a software bank-switched cart (~half-day refactor — bank-switching only matters during the boot-time RAM copy, since runtime is all-RAM). See [../platform/cartridge.md §"Cart size — 32 K"](../platform/cartridge.md).

---

## Standing review checklist (every gate)

At each gate, run through these — not optional:

1. **Wiki updates.** Any new lesson, decision, hardware quirk, or convention discovered → file it. Don't let it stay in chat history.
2. **Roadmap drift check.** Re-read this document. Does the next phase's POC and exit criterion still describe the right next step? If not, edit *this file* and append a log entry explaining the change.
3. **Budget check.** ROM bytes used / 16384. Cycles per frame used / ~29800 (1.78 MHz / 60 Hz). Surface the trend, don't wait until we're pinned.
4. **Scope check.** Anything we *added* that wasn't in the design doc? Anything we *cut*? Update [game/overview.md](../game/overview.md) decisions block.

## Risks the plan won't surface on its own

- **GIME mode choice in Phase 2** is load-bearing for everything visual. Don't rush the review at that gate.
- **Tile vs sprite format coupling** in Phase 3/4 — getting the boundary wrong forces a rewrite later. Sketch both formats together, not sequentially.
- **Per-frame budget under enemy load** in Phase 6 is the most likely place we discover we need the TCB scheduler or dirty-rect tracking. Plan a contingency phase at that gate, not after.
- **EPROM/cart-shell hardware logistics** in Phase 10 — sourcing a programmer, blank EPROM (16 K 27C128, or larger if we expanded earlier), and a working cart shell is *not* a code task. CoCoSDC removes most of this. Start sourcing in parallel during Phase 6 or 7.

## Sources

- [game/overview.md](../game/overview.md) — locked design.
- [platform/cartridge.md](../platform/cartridge.md), [platform/gime.md](../platform/gime.md), [platform/timing.md](../platform/timing.md), [platform/input.md](../platform/input.md), [platform/sound.md](../platform/sound.md) — hardware reference.
- [coding-conventions.md](coding-conventions.md), [scheduler.md](scheduler.md), [lessons-learned.md](lessons-learned.md).
- [tooling/build-workflow.md](../tooling/build-workflow.md).
