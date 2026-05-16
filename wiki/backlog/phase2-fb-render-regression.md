---
name: Phase 2.x main.s renders FB as noise (not the documented 3 tiles)
description: The full Phase 2.x boot path (MMU on, PARs loaded, cart self-copy) produces an unintelligible red/green-or-pink/green tight-stripe pattern instead of the 3-tile-on-black image lessons-learned claims it produces. A minimal-MMU-off cart produces correct hi-res output, so the bug is somewhere in the MMU / PAR / self-copy chain.
type: backlog
tags: [video, gime, mmu, bug, regression, phase-2]
updated: 2026-05-16
---

# Phase 2.x main.s FB render regression

## Observed facts

Building `src/main.s` at its current `main` HEAD (commit `57333f0`, Phase 2.4
with three test tiles) and running under either `-tv-input rgb` or
`-tv-input cmp`:

- **Expected** (per [implementation/lessons-learned.md](../implementation/lessons-learned.md)
  and the Phase 2.4 commit message): black FB with three identical
  arcade-char-432 tiles spaced across the top row.
- **Observed**: tight 2-colour grid pattern (red+green under RGB, pink+green
  under composite) over the entire FB area, with a magenta border. Three
  tiny lighter spots are barely visible roughly mid-screen — possibly the
  tiles but at the wrong vertical position and obscured by background noise.

The pattern is **stable**, not transient: same image after the cart halts
on `phase24_halt: bra phase24_halt`. The pattern is **independent of FB
content**: replacing the 3-tile render with a stripe diagnostic or a solid
`$11` fill produces visually identical noise, so writes to the FB are not
landing where the GIME reads from (or the GIME is in a different mode than
we believe).

## Discriminating test that isolates the bug

[`src/diag_minimal.s`](../../src/diag_minimal.s) — a from-scratch hi-res
diagnostic with **no MMU, no cart self-copy, no PARs**:

- `$FF90` Init0 = `%00001000` (CoCo3 mode, MMU OFF, force `$FExx`)
- `$FF98` BP=1, `$FF99` = `$1E` (VRES=0, HRES=7, CRES=2 — 320×192×16)
- VOFF = phys `$072000` (= virt `$2000` because MMU-off maps the 64 K
  virtual range onto the topmost 64 K physical)
- Load 16 distinct palette codes
- Fill FB with 16 horizontal stripes (12 rows each)
- Unblank → halt

**Result under `-tv-input rgb`:** 16 clean horizontal stripes, all distinct
colours, exactly as drawn. Confirmed the empirical RGB palette mapping now
recorded in [implementation/lessons-learned.md](../implementation/lessons-learned.md)
§"XRoar RGB monitor palette mapping".

So:
- ✅ GIME 320×192×16 mode works.
- ✅ XRoar `-tv-input rgb` rendering works.
- ✅ Palette load to `$FFB0-$FFBF` works.
- ✅ FB writes to phys `$072000` work.
- ❌ Something between `diag_minimal.s` (MMU off, no copy) and `main.s`
  (MMU on with executive PARs, cart self-copy active) breaks FB display.

## Candidate causes (ordered by suspicion)

1. **Cart self-copy is corrupting the FB or executing wrong code.** The
   self-copy at `entry` runs while MMU is OFF, so `ldd ,x / std ,x` to
   `$C000-$FEFF` writes to phys `$07C000-$07FEFF`. That range is *also*
   where execution is happening. The known XRoar 1.10 cart-window
   corruption at `$C0D9-$C0DB` has a workaround, but the workaround skips
   four bytes — if any branch / `LBSR` offset lands in that gap, control
   flow is destroyed once we switch to SAM_ALLRAM and execution moves to
   RAM.

2. **MMU PAR setup or order has a hole.** Current main.s sets `clr $FF91`
   (force exec PAR set) **after** the cart copy but **before** loading the
   par_table into `$FFA0-$FFA7`. PAR1 is supposed to be `$30` (FB page 0).
   If the PARs aren't reaching the executive bank — or if the wrong bank
   is active at the moment writes land — then virtual `$2000` writes go
   to whatever RAM the (possibly uninitialised) PAR1 points at, and the
   display continues to read phys `$060000` (which is uninitialised RAM
   that happens to contain the noise pattern we see).

3. **VOFF + PAR mismatch.** main.s configures VOFF for phys `$060000`
   (`$FF9D = $C0`, `$FF9E = $00`) AND PAR1 = `$30`. Both point at phys
   `$060000`. But VOFF is written **before** Init0 enables the MMU, while
   PAR1 is loaded into `$FFA1` **before** SAM_ALLRAM and **before** the
   MMU is enabled in Init0. There may be a sequencing issue where the
   GIME latches VOFF against the wrong physical page.

4. **The wiki claim that Phase 2.4 "renders 3 tiles" was never empirically
   verified.** Possibility that the lessons-learned table and the Phase
   2.3 / 2.4 commit messages describe intended-but-unobserved behaviour.
   The composite-NTSC stripe table in lessons-learned (16 named colours)
   *was* presumably observed at some point — but the 3-tile render may
   have been broken from the start. Worth checking the git history for
   a recorded user-observed-success moment.

## Suggested investigation order

1. Reproduce the noise pattern on commit `2593d36` (Phase 2.3 close —
   the commit where the 16-stripe diagnostic was *claimed* to work and
   the composite palette table was derived). If 2.3 also shows noise,
   the regression has been latent the entire time and the composite
   palette table was likely from an earlier intermediate state.
2. Bisect: from `diag_minimal.s` (works), add features one at a time
   until display breaks. Order: enable MMU → add PAR load → add cart
   self-copy → move FB to phys `$060000`. The breaking change is the
   bug.
3. Once the breaking change is identified, fix it minimally — don't
   refactor surrounding code.

## Done when

- `./scripts/build.sh run` boots `main.s` and shows three clean tiles
  on a black background, in palette indices 0-3 under
  `-tv-input rgb`.
- Root cause is captured in [implementation/lessons-learned.md](../implementation/lessons-learned.md).
- The "Phase 2.4 isolation build renders 3 tiles correctly under RGB"
  acceptance criterion in [rgb-tv-input-palette.md](rgb-tv-input-palette.md)
  is now satisfiable.

## Sources

- [`src/diag_minimal.s`](../../src/diag_minimal.s) — the working baseline.
- [`src/main.s`](../../src/main.s) — the broken pipeline; specifically
  `entry` through `phase24_halt`.
- [implementation/lessons-learned.md](../implementation/lessons-learned.md)
  — XRoar bad-window note + 3-tile render claim.
- 2026-05-16 session log — observed-fact capture during the
  rgb-tv-input-palette task.
