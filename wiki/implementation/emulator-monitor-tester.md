---
name: Emulator-monitor tester — requirements
description: Four-workstream initiative pairing a switchable 6809 tester ROM with web-app features (live FB rendering, mapped memory regions, step-synchronized panels) to drive emulator/hardware bring-up and palette/mode experiments.
type: decision
tags: [tester, web-app, video, framebuffer, regions, gime, requirements]
updated: 2026-05-16
---

# Emulator-monitor tester — requirements

A development platform — *not* the Ladybug game — for exercising the CoCo 3 hardware envelope and the web-app monitor in parallel. Seeded from [src/diag_minimal.s](../../src/diag_minimal.s) (the working 16-stripe minimal hi-res cart from 2026-05-16). Lives alongside the game ROM; does not modify it.

## Why a separate tester

- Phase 2.x main.s has a confirmed FB-render regression ([../backlog/phase2-fb-render-regression.md](../backlog/phase2-fb-render-regression.md)). A clean minimal cart side-steps that while we iterate on the web app.
- The mode/palette/pattern space is large and not arcade-relevant for most of it. Exercising it inside main.s would bloat the game ROM.
- The web app needs a reliable, *known-state* target to validate live FB rendering, mode resolution, and the regions feature against. The tester is that target.

## Workstreams

Sequenced so each downstream piece has something concrete to test against. Each WS has its own architect → implement → QA cycle.

### WS-A — Tester ROM v0 + GIME-state visibility probe

**Goal.** A single-mode tester evolved from `diag_minimal.s`, with the smallest amount of structure needed to support the web-app workstreams.

**DECIDED.**
- Input: **keyboard, key-per-option**. Distinct keys map directly to modes and patterns (number row for modes, letter row for patterns). No mode/pattern cycling.
- HUD: **none on-screen**. Current selection is visible only in the web app. Keeps pattern rendering clean.
- Run model: **continuous main loop + 60 Hz Vbord IRQ.** Keyboard polled in the IRQ handler; main loop redraws the current pattern. Closest to real game-loop structure; exercises the IRQ path.
- v0 pattern catalogue: **horizontal bars + checkerboard.** Bars carry forward from `diag_minimal.s`; checkerboard adds an 8×8 pixel-alignment check.
- v0 mode: **320×192×16 only** (CRES=10, HRES=7, VRES=00). The mode matrix expands in WS-D.

**GIME-state visibility — empirical probe required before design commits.**
The earlier draft of this initiative assumed a software "shadow block" for the write-only `$FF98/99/9D/9E` regs. That's one option of three; not a hardware fact. Decision deferred pending a 10-minute gdb-mcp probe:

| Option | If probe says... | Cost |
|-|-|-|
| 1. Direct read of `$FF9x` via gdb-mcp | XRoar returns last-written values for write-only regs | free; XRoar-only; would need 2 or 3 for real hardware |
| 2. Read tester program state (mode-index + table at known symbol) | XRoar returns garbage | small (~per-instance variable + table); real-hardware-compatible; tester-specific until other ROMs adopt the same pattern |
| 3. Software shadow block written by macro on every `sta $FF9x` | (always available) | most invasive; touches every register-write site; real-hardware-compatible; most general |

**Probe procedure.** Against a running Phase 2.4 (or `diag_minimal`) instance: `read_memory(0xFF98, 8)` after a known write sequence has set those regs to specific values; compare returned bytes to written bytes. Record finding in [lessons-learned.md](lessons-learned.md). Architect picks option 1/2/3 against the result.

**OPEN.** Exact key bindings (number-row mode-select, letter-row pattern-select — but which letter is which pattern? Decided at v0 build time, documented in the tester's own README block).

### WS-B — Live framebuffer renderer

**Goal.** Replace `placeholder_png` in [web/backend/framebuffer.py](../../web/backend/framebuffer.py) with a live renderer that derives the current mode dynamically (via whichever option WS-A's probe selects) and produces a PNG matching what XRoar is displaying.

**DECIDED.**
- Palette decode: **RGB monitor** (`palette.decode_rgb_monitor`). Composite path closed — XRoar canonical invocation is `-tv-input rgb` since 2026-05-16.
- New backend module: **`web/backend/gime_state.py`** approved. Reads palette + PARs + (mode via probed mechanism) and returns a `VideoState` dataclass.
- Trigger: **on `ws:halt`**, frontend already polls `/api/instances/{id}/framebuffer.png`. No new endpoints; PNG wire shape unchanged.
- Free-run rendering: **optional poll** — a UI toggle enables `/framebuffer.png` polling at ~500 ms during free-run. Default off. Torn frames labeled as such in the meta line.
- MMU stitching: read FB via virtual addresses, with the virtual base computed from PAR contents (not hard-coded to the Phase 2.3 mapping).
- Unsupported modes: return placeholder PNG whose text reports the unsupported mode/resolution/depth.

**DEFERRED to WS-D landings.** Mode-specific decoders (4-color, monochrome, text) — added as WS-D enables them.

### WS-C — Mapped memory regions

**Goal.** User-defined named address ranges, displayed and refreshed per halt, with extensible viewers.

**DECIDED.**
- Persistence: **per-config** (regions attach to `web/configs/<id>.json`). Tester config and Ladybug config get independent region sets.
- Definition modes: **all three** are supported.
  - Fixed `addr + length`.
  - `Symbol + offset + length` — resolved via `build/<rom>.map` at instance start (and re-resolved on rebuild).
  - `Follow pointer at addr` — region base = the 16-bit word at the given address, re-resolved on every halt. Useful for stack/heap inspection.
- Auto-refresh: **every halt (including each `-exec-step`).** Visible regions only — collapsed regions don't fetch. No throttling in v1; revisit if perceived sluggish.
- Max size: **32 KB per region.** Big enough to cover a full framebuffer-as-region or a full MMU page. Reads chunked by the backend if needed.
- Viewer formats: **extensible plugin convention.** Hex dump is the always-on baseline. Additional viewers (ASCII, disassembly, bitmap-as-image, palette-as-swatches) are separate small frontend components added per documented use case rather than enumerated upfront. New module `web/backend/regions.py` (CRUD + resolution); new component `web/frontend/components/memory-regions.js` (container) + per-viewer subcomponents.

**OPEN.** v0 viewer set: hex-dump confirmed. Additional v0 viewers (or all-deferred-to-use-case) — decide at WS-C architect handoff.

### WS-D — Tester mode/pattern matrix expansion

**Goal.** Expand WS-A's single mode/two-pattern v0 into the full switchable matrix.

**DECIDED.**
- Mode families in scope (eventual): **all four** — hi-res 16-color (CRES=10), hi-res 4-color (CRES=01), hi-res monochrome (CRES=00), hi-res text (BP=0).
- Resolution sweep: implied by mode-family scope — HRES 4-7, VRES 192/200/225 where applicable.
- Mode-switch atomicity: **blank via CRES=11** during reconfiguration, unblank after. Matches the Phase 2.3 boot recipe. Costs ~3 extra register writes per switch.
- Pattern catalogue (eventual): horizontal bars, checkerboard (v0); 16-color stripe diagnostic (revive from git history at the Phase 2.3-close commit); per-color solid fill sweep; additional patterns as use cases warrant.

**DEFERRED.** Composite-mode regression testing — XRoar is RGB-canonical now; revisit only if real-hardware testing exposes a composite-specific need.

### Cross-cutting — step-sync

**DECIDED.** All reactive panels refresh on every `ws:halt`, including each `-exec-step`. The 30 KB FB read per step is accepted; if rapid stepping becomes uncomfortable, throttling is the v1.1 mitigation. Confirms the existing `ws:halt` plumbing is the integration point — no new event types needed.

## Scope approvals (granted by user)

- New build target: **`build/tester.rom`** via a `tester` action in [scripts/build.sh](../../scripts/build.sh). Does not touch the Ladybug build path.
- New backend module: **`web/backend/regions.py`** (distinct from the static `web/data/6809-regions.json` map).
- New backend module: **`web/backend/gime_state.py`**.
- New frontend component: **`web/frontend/components/memory-regions.js`** + viewer-plugin subcomponents added per use case.

## Explicitly out of scope

- Modifications to Ladybug game ROM behavior. Tester runs in parallel.
- Composite-NTSC palette rendering (closed; RGB is canonical).
- Time-travel / reverse-step (already deferred in v2 web-app architecture).
- Native-hardware verification of the tester (XRoar-only for v1).
- Snapshot save/load integration with the tester (rides existing infra unchanged).
- Project-wide application of the shadow-register convention to Ladybug-proper. Tester-only until and unless option 3 is selected by the probe outcome and Ladybug-proper's mode handling matures to need it.

## Sequencing

1. **Probe** (gates everything): empirical `$FF98/9` read test → record finding → pick option 1/2/3.
   **Resolved 2026-05-16: Option 2 (ProgramStateStrategy).** XRoar's gdb stub returns sentinel `$1B` for every read of `$FF90` and `$FF98..$FF9E` regardless of writes; palette and PARs read back correctly so the channel is sound. See [lessons-learned.md §"XRoar gdb readback of GIME write-only registers"](lessons-learned.md). Probe artifact: [web/scripts/probe_gime_readback.py](../../web/scripts/probe_gime_readback.py).
2. **WS-A**: tester v0 ROM, single mode, two patterns, IRQ-driven keyboard, mode-visibility per probe outcome.
3. **WS-B**: live FB renderer using WS-A's mode-visibility mechanism, single mode supported.
4. **WS-C**: regions feature, hex-viewer baseline. Can parallelize with WS-D after WS-A.
5. **WS-D**: mode-matrix expansion. WS-B grows decoders as new modes land.

Each WS closes in `qa-reviewer`.

## WS-A architect-pass decisions (2026-05-16)

Approved by user. Implementation may proceed against these.

### Probe

- **Tool:** new throwaway script `web/scripts/probe_gime_readback.py` (~50 lines), uses `web.backend.gdb_session.GdbSession`.
- **Stimulus:** an already-running `diag_minimal.rom` instance. That ROM writes `$FF98=$80`, `$FF99=$1E`, `$FF9A=$28`, `$FF9D=$E4`, `$FF9E=$00` then halts at the `bra halt` self-loop ([../../src/diag_minimal.s](../../src/diag_minimal.s)). No new ROM required.
- **Reads:** `$FF98-$FF9E` (the question), `$FFB0-$FFBF` palette and `$FFA0-$FFA7` PARs (controls — the gdb channel itself).
- **Pass criteria → strategy mapping:**
  - Returns the exact bytes written → **Option 1** (`DirectReadStrategy`).
  - Returns consistent garbage or inconsistent values → **Option 2** (`ProgramStateStrategy`). The tester ROM exports `tester_mode_idx` and `tester_mode_table` regardless of probe outcome so option 2 remains available as a fallback.
  - Read-transport error → stop and debug the channel, not the registers.
- **Output:** an entry in [lessons-learned.md](lessons-learned.md) titled "XRoar gdb readback of GIME write-only registers" with observed bytes + chosen strategy.

### WS-A tester ROM v0 — structure

**Subtree from day one:** `src/tester/`.

```
src/tester/
├── tester.s          top-level: boot, mainloop, includes the rest
├── dp.inc            DP slot equates ($0200..)
├── input.s           kbd_scan_and_dispatch, key_table
├── render.s          redraw_with_blank, draw_current_pattern, pattern jump table
├── pat_bars.s        horizontal-bar renderer (lift from diag_minimal)
├── pat_check.s       checkerboard renderer
└── modes.inc         tester_mode_table (one entry in v0; grows in WS-D)
```

**Operating envelope** (inherited from diag_minimal):
- No MMU (`$FF90` bit 6 = 0). Virtual = physical $07xxxx.
- Cart bytes execute from cart ROM at `$C000-$FDFF` (no self-copy — sidesteps the cart-window-writability gotcha in [lessons-learned.md](lessons-learned.md)).
- RW state at virtual `$0000-$1FFE`, FB at `$2000`, IRQ jump table at `$FE00-$FEFF` (RAM-backed via `Init0` bit 3 = 1).

**DP page** ($02): 13 bytes, all named symbols emitted to `build/tester.map`:

| Symbol | Addr | Size | Notes |
|-|-|-|-|
| `tester_mode_idx` | `$0200` | 1 | read by web app (option 2) |
| `tester_pattern_idx` | `$0201` | 1 | |
| `tester_selection_dirty` | `$0202` | 1 | IRQ sets, mainloop clears |
| `tester_kbd_prev` | `$0203-$020A` | 8 | edge-detection state, one byte per column |
| `tester_frame_ctr` | `$020B-$020C` | 2 | 60 Hz tick, debug |

**Boot:** mirror diag_minimal through palette load; then init DP slots, install IRQ at `$FEF7`, enable Vbord in `$FF92` (b3) plus ACVC-IRQ in `$FF90` (b5), unblank (`$FF99=$1E`), clear I-mask, fall into mainloop.

**Mainloop:** spin on `tester_selection_dirty`. When set: blank (CRES=11), draw, unblank (CRES=10), clear flag.

**Vbord ISR:** ACK via `ldb $FF92`, bump `tester_frame_ctr`, run `kbd_scan_and_dispatch`, RTI. <200 cycles per frame — comfortable against the 29 666-cycle budget.

**Keyboard scan with edge detection:** standard 8-column drive loop ([../platform/input.md](../platform/input.md)); compare DRA to per-column `tester_kbd_prev[col]`; new-press = bit went low. Dispatch via a `key_table` of `(col_mask, row_mask, handler)` records per [coding-conventions.md §3](coding-conventions.md). v0 honors: `1` (PB1,PA4) → mode 0; `B` (PB2,PA0) → pattern 0 (bars); `C` (PB3,PA0) → pattern 1 (checker). Other keys ignored. Every dispatch sets dirty even on redundant press (useful during bring-up).

**Renderers:** bars lifted from diag_minimal's stripe loop; checkerboard emits alternating `$01 $10` bytes with row-direction flip every 8 scanlines.

**Inter-pattern blank:** every selection change blanks via CRES=11 → redraws → unblanks. Approved with caveat that this is revisitable after testing.

### Build target

Add to [`scripts/build.sh`](../../scripts/build.sh):
- `cmd_tester` — assembles `src/tester/tester.s` → `build/tester.rom` + `.map` + `.lst`, pads to 16 KB.
- `cmd_tester_run` — `cmd_tester` then `xroar -machine coco3 -ram 512 -cart ladybug -cart-type rom -cart-rom build/tester.rom -cart-autorun -tv-input rgb`.
- New `tester` and `tester-run` cases in the bottom dispatch. Game-ROM `build` / `run` / `clean` untouched.

The 16 KB padder is duplicated for now; promote to a shared helper if a third ROM is added.

### WS-B forward-compatibility

`web/backend/gime_state.py` defines a `ReadStrategy` Protocol with three implementations: `DirectReadStrategy` (option 1), `ProgramStateStrategy(mode_idx_addr, mode_table_addr)` (option 2), `ShadowBlockStrategy(addr)` (option 3). `VideoState.source` records which one ran. Strategy chosen by backend config after the probe; both option 1 and option 2 supported simultaneously because WS-A exports the required symbols.

## Wiki gaps flagged (not blocking)

- Exact `Init0` bit 5 × bit 7 interaction (ACVC-IRQ enable + CoCo3 mode on the same byte). Assumed independent; Tepolt Ch. 7 supports this. Re-read if IRQ install misbehaves.
- Whether `$FF92` read is well-defined when ACVC-IRQ is disabled. We always read it inside the active ISR so this doesn't bite.

## Open items at next architect handoff (WS-B, then WS-C/D)

- v0 region viewers beyond hex dump — author upfront vs defer per use case (decide at WS-C architect time).
- Naming for the option-2 mode-table entries' field layout (proposed: 5-byte records of `vmode, vres, border, voff1, voff0`).

## Sources

- [../tooling/web-app-architecture.md](../tooling/web-app-architecture.md) — v2 web-app design this initiative extends
- [../platform/gime.md](../platform/gime.md) — write-only register catalog + shadow programming note
- [./video-mode.md](video-mode.md) — current 320×192×16 baseline mode
- [./lessons-learned.md](lessons-learned.md) — XRoar empirical findings; probe results land here
- [../backlog/phase2-fb-render-regression.md](../backlog/phase2-fb-render-regression.md) — why we don't iterate on main.s for this
- [../../src/diag_minimal.s](../../src/diag_minimal.s) — seed for the tester ROM
- log entry 2026-05-16 — RGB switch + minimal-cart construction
