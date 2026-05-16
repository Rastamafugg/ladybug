---
name: Convert to RGB tv-input and rebuild palette tables
description: Switch XRoar from composite NTSC to RGB monitor mode and re-derive the empirical 6-bit palette → color table that main.s depends on.
type: backlog
status: mostly-done (3-tile-render acceptance criterion blocked on FB regression — see phase2-fb-render-regression.md)
tags: [tooling, xroar, palette, video]
updated: 2026-05-16
---

# Convert to RGB tv-input and rebuild palette tables

## Status (2026-05-16)

**Mostly complete.** `-tv-input rgb` is wired into both launch sites
([scripts/build.sh](../../scripts/build.sh) + [web/backend/instance.py](../../web/backend/instance.py)),
the empirical 6-bit → colour table has been derived under RGB and recorded
in [implementation/lessons-learned.md](../implementation/lessons-learned.md)
§"XRoar RGB monitor palette mapping", and `palette_table` in
[src/main.s](../../src/main.s) has been updated to use RGB-canonical codes
for indices 0-3 (black `$00`, yellow `$30`, blue `$08`, white `$3F`).

**Blocked acceptance criterion:** "Phase 2.4 isolation build renders three
test tiles correctly under RGB" cannot be verified because the existing
Phase 2.x main.s pipeline renders the FB as a 2-colour noise grid under
either RGB *or* composite — independent of FB content. Bug isolated to the
MMU / PAR / cart-self-copy chain via a from-scratch minimal hi-res cart
([src/diag_minimal.s](../../src/diag_minimal.s)) that displays 16 clean
stripes. Full investigation lives in
[phase2-fb-render-regression.md](phase2-fb-render-regression.md).

## Why

`scripts/build.sh` currently launches XRoar with no `-tv-input` flag, so XRoar defaults to **composite NTSC**. The empirical 6-bit-code → color table in [implementation/lessons-learned.md §"XRoar's CoCo-3 monitor is composite NTSC by default"](../implementation/lessons-learned.md) was derived under that default, and the palette in [`src/main.s`](../../src/main.s) `palette_table` uses those composite-tuned codes (e.g. `$30` and `$3F` both render as white under composite — useless under RGB; `$33` is yellow under composite but a completely different hue under RGB).

Real CoCo 3 hardware that targets an RGB monitor (the more common modern setup, and the cleaner colour signal) needs a different table. Continuing on composite is fine for emulator-only work, but it locks us into colour choices that won't match RGB hardware in Phase 10.

## Scope

- Add `-tv-input rgb` to the canonical `xroar` invocation in [`scripts/build.sh`](../../scripts/build.sh).
- Update the canonical-invocation snippet in [tooling/xroar.md](../tooling/xroar.md) and [tooling/build-workflow.md](../tooling/build-workflow.md).
- Re-run a stripe-test ROM (revive the Phase 2.3 16-stripe diagnostic from the git history at the Phase 2.3-close commit) and visually record the 6-bit-code → color mapping under `-tv-input rgb`.
- Replace the empirical table in [lessons-learned.md](../implementation/lessons-learned.md) with a new entry "XRoar RGB monitor palette mapping" — keep the composite table too, clearly labelled, since real CoCo 3 owners may pick either monitor.
- Update `palette_table` in `src/main.s` so indices 0-3 (black / yellow / blue / white) still render correctly under RGB. Audit remaining entries for any duplicates that resolve to the same RGB triple.

## Done when

- `./scripts/build.sh run` boots into RGB mode by default.
- A stripe-test build under the new tv-input shows 16 visually distinct stripes (no duplicates).
- The Phase 2.4 isolation build (three test tiles) renders with the intended 0/1/2/3 colours under RGB.
- Wiki: lessons-learned has both palette tables, clearly labelled by tv-input mode.

## Open questions

- Is there a reason to keep composite as an option for any test? (Real composite hardware exists; some users may not have RGB monitors. Possibly add an `XROAR_TV=cmp` env override to the build script.)
- Does `cmp-br` vs `cmp-rb` produce different colour mappings worth documenting? Probably out of scope until someone asks.

## Starting prompt for the spin-off session

> Read [wiki/backlog/rgb-tv-input-palette.md](wiki/backlog/rgb-tv-input-palette.md). Execute that backlog item. Start by reviving the Phase 2.3 16-stripe palette diagnostic (it lived in `src/main.s` before the Phase 2.4 isolation commit — recover from git history). Then re-derive the empirical 6-bit → colour mapping under `-tv-input rgb` and update everything the backlog item lists.

## Sources

- [tooling/xroar.md](../tooling/xroar.md)
- [tooling/build-workflow.md](../tooling/build-workflow.md)
- [implementation/lessons-learned.md](../implementation/lessons-learned.md) — composite table to preserve
- [`src/main.s`](../../src/main.s) — `palette_table`
