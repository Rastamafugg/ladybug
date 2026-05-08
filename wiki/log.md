# Wiki Log

Append-only chronological record of ingests, queries, and lints. Each entry prefixed `## [YYYY-MM-DD] <type> | <title>` so the log is grep-parseable.

---

## [2026-05-05] seed | Initial wiki instantiation

Created wiki scaffolding under `wiki/` for the Ladybug project (6809 assembly port of the 1981 *Lady Bug* arcade game, targeting bare-metal CoCo 3 — no NitrOS-9). Configuration adapted from the Planet Pioneers project:

- `CLAUDE.md` schema (three-layer architecture: raw sources / wiki / schema; relative-link convention; ingest/query/lint workflows).
- `index.md` content catalog with stub entries for game / platform / implementation / sources sections.
- `log.md` (this file).
- Project-root `CLAUDE.md` adapted to Ladybug.
- `.claude/skills/` role skills (project-management, business-analyst, coding-architect, debugger, qa-reviewer) copied and adapted — references to MULE/GDD/NitrOS-9/DCC replaced with Ladybug/arcade-reference/GIME/6809-toolchain.
- `.claude/settings.local.json` permissions copied (git/gh + read access under `D:/retro/`).

No raw sources ingested yet. Next steps when work begins: pick the assembler (lwasm vs asm6809 vs EDTASM), commit a `docs/` folder with arcade reference material and a CoCo 3 hardware reference, and ingest both into corresponding `sources/` pages.

---

## [2026-05-05] ingest | Lady Bug arcade — web reference

User asked for a design doc seeded from public web sources. Searched + fetched Wikipedia, Pixelated Arcade tech specs, C64-Wiki (port reference), bitvint.com, and miscellaneous web aggregations. Created [`sources/ladybug-arcade.md`](sources/ladybug-arcade.md) cataloguing what was extracted from each source and what remains uncertain. Created [`game/overview.md`](game/overview.md) — full design doc covering: playfield (240×192 arcade → CoCo 3 horizontal with HUD relocated to side panels), 20 turnstile gates, border-circuit enemy-release timer, 8 enemy types + skull hazards, scoring table (dot 10 / blue 100 / yellow 300 / red 800 / vegetables 1000–9500), heart ×2/×3/×5 multiplier, EXTRA/SPECIAL letter cycle, full 18-vegetable cycle. Ten open questions logged for user/MAME-source resolution. Two source documents could not be fetched (arcade-museum manual PDF returned binary data; StrategyWiki blocked the fetcher).

---

## [2026-05-05] decision | Design-doc scope locked for first release

User answered the 10 open questions in [`game/overview.md`](game/overview.md). Locked: HUD split panels (left = score/lives/level; right = EXTRA/SPECIAL/vegetable); `SPECIAL` reward = 10,000 points (no bonus round in v1); 3 lives + one-time 30K bonus life; single fixed maze across all stages; fixed skull count per stage. Explicitly skipped: MAME-source ingest, arcade-manual PDF ingest.

**Hearts and letters / colour cycle** (clarified across two follow-ups): hearts and letters are separate maze entities. The colour cycle is **global and instantaneous** — every coloured item on the playfield shares one colour state that flips together. Each of the three targets (EXTRA word, SPECIAL word, heart multiplier) is bound to a distinct one of the three colours; an item advances its target only when collected at the matching colour. E and A apply to whichever of EXTRA/SPECIAL is currently active. No tie-break is needed because the global single-colour state plus distinct target-colour assignments make ties structurally impossible. Specific colour-to-target mapping deferred.

Five items deferred to implementation tuning: cycle period/reset, colour-to-target mapping, enemy AI, sound design, input fallback. Rewrote `game/overview.md` HUD section, hearts-vs-letters section (twice), stage-flow, and the Decisions-locked + Deferred blocks.

---

## [2026-05-07] ingest | Tepolt — Assembly Language Programming for the Color Computer (CoCo 1/2)

Read the full Tepolt CoCo 1/2 manual (`docs/reference/Assembly Language Programming for the Color Computer.md`, ~14.7K lines). Focused on the chapters Ladybug needs: ch. 3 (MC6809E architecture, programming model, interrupt sequences), ch. 4 (addressing modes + postbyte tables), ch. 5 / Appendix B (instruction set + cycle counts), ch. 9 (SAM control bits, PIA architecture, VDG modes, IRQ/FIRQ wiring), ch. 10 (keyboard matrix, joystick fire + analog A/D loop, sound paths, cartridge connector pinout), Appendix E (dedicated-address map). Skipped chapters 1-2 (binary/hex primer), 6 (EDTASM+ — not our toolchain), 7-8 (BASIC interop).

Created [`sources/coco-asm-tepolt.md`](sources/coco-asm-tepolt.md) summarising what was extracted and what was deliberately skipped.

## [2026-05-07] ingest | Tepolt — Assembly Language Programming for the CoCo 3

Read the full Tepolt CoCo 3 addendum (`docs/reference/Assembly Language Programming for the CoCo3.md`, ~1.8K lines). Captured: GIME (ACVC) overview, palette + alternate color set, virtual/physical memory and MMU PAR sets, all hi-res text and graphics modes (CRES/HRES/VRES tables, byte formats A/B/C, scrolling), low-res mode parity with the original CoCo, ACVC interrupt sources (Vbord/Hbord/Timer/SerIn/Kybd/Cart) and IRQEN/FIRQEN registers, reset-init flow, the FF22 split, the keyboard-matrix extension for F1/F2/CTRL/ALT and joystick button 2.

Created [`sources/coco3-asm-tepolt.md`](sources/coco3-asm-tepolt.md). The earlier stub for this page never existed as a file — only as an index entry — so this is a fresh write.

## [2026-05-07] propagate | Platform pages from both Tepolt manuals

Wrote/created seven platform pages from the two Tepolt source pages:

- [`platform/6809.md`](platform/6809.md) — programming model, addressing modes, interrupt sequence summary, clock-rate selection.
- [`platform/gime.md`](platform/gime.md) — full ACVC register catalog (`$FF90-$FF9F`, `$FFA0-$FFAF`, `$FFB0-$FFBF`) plus the legacy SAM bit-flip pairs.
- [`platform/memory.md`](platform/memory.md) — virtual vs physical, PAR sets, ROM/RAM modes, dedicated address map, 128 K aliasing quirk, `$FE00-$FEFF` jump-table guarantee.
- [`platform/timing.md`](platform/timing.md) — MPU clock options, IRQ source comparison, decision to use ACVC Vbord at 60 Hz, frame-budget partition at 1.78 MHz.
- [`platform/input.md`](platform/input.md) — keyboard matrix scan, fire buttons (now two each), joystick X/Y successive-approximation A/D.
- [`platform/sound.md`](platform/sound.md) — 6-bit DAC vs PB1 square wave, selector-switch setup, planned use for melody vs SFX.
- [`platform/cartridge.md`](platform/cartridge.md) — 40-pin pinout, CART/FIRQ auto-start, the boot-time sequence Ladybug must execute.

Updated [`index.md`](index.md) to list all seven new platform pages and both source pages.

## [2026-05-08] ingest | Tooling — lwtools, xroar, toolshed + build script

User requested full build/deploy runbooks for the WSL toolchain at `~/coco-tools/{lwtools,toolshed,xroar}` plus an automation script. Created a new `wiki/tooling/` section: [`index.md`](tooling/index.md), [`lwtools.md`](tooling/lwtools.md) (lwasm 4.24, `--format=raw` invocation, padding to 16 KB, gotchas), [`xroar.md`](tooling/xroar.md) (XRoar 1.10, canonical `-machine coco3 -ram 512 -cart-rom ... -cart-autorun` profile, GDB/trace flags), [`toolshed.md`](tooling/toolshed.md) (decb/os9 — explicitly **standby**, not in active build), [`build-workflow.md`](tooling/build-workflow.md) (end-to-end runbook with manual fallbacks). Wrote [`scripts/build.sh`](../scripts/build.sh) with `build`/`run`/`clean` subcommands; smoke-tested end-to-end against a 3-byte stub (`ORG $C000 / JMP entry` → 16384-byte padded ROM). Verified Windows-host Claude can drive WSL via `wsl -d Ubuntu -- bash -lc ...`.

**Decision:** deploy is **cartridge ROM image only** (option A); toolshed kept documented but unused. Rationale: matches existing cartridge boot strategy locked 2026-05-07. Reconsider if iteration becomes cumbersome — the toolshed page documents the `.dsk`/`LOADM` fallback path so the switch is fast. OS-9 path explicitly out of scope (conflicts with bare-metal constraint in `CLAUDE.md`).

`wiki/index.md` updated: new Tooling section; old `platform/toolchain.md` and `implementation/build-workflow.md` stubs marked superseded.

## [2026-05-08] decision | Implementation roadmap committed

User asked for a phased plan from current state to finished game with POCs and review gates. Wrote [`implementation/roadmap.md`](implementation/roadmap.md) — 11 phases (0: hello cart, 1: boot init, 2: display, 3: tile/maze, 4: input/sprite, 5: HUD/maze logic, 6: enemies, 7: letters+veg+colour cycle, 8: sound, 9: polish, 10: real hardware). Each phase has POC tasks, exit criterion, and review-gate questions. Ties to existing locked decisions ([game/overview.md](game/overview.md), [platform/cartridge.md](platform/cartridge.md), [coding-conventions.md](implementation/coding-conventions.md)) and surfaces deferred items (cycle period + colour-to-target mapping at Phase 7, scheduler choice at Phase 4, SWI/IRQ collision check at Phase 1) at the gates where they need to land. Documented standing review checklist (wiki updates, roadmap drift, ROM/cycle budget, scope) and four named risks the plan won't surface on its own.

---

## [2026-05-08] ingest | Dungeons of Daggorath cartridge source — coding idioms

User requested a scan of the DoD source under `docs/reference/DungeonsOfDaggorath-main/` (47 `.ASM` files, lwasm-compatible reconstruction by MJS over Kiyohara's 1983 original) for transferable 6809 conventions. Verified end-to-end build of the source first: `lwasm DAGGORATH.ASM` → 8192 bytes ORG `$C000`, padded to 16 KB, autoruns under XRoar via the same flow as `scripts/build.sh`. Spawned an Explore agent to extract patterns; approved findings list with the user before filing.

Created [`sources/dod-source.md`](sources/dod-source.md) (provenance, module map, naming conventions). Created [`implementation/coding-conventions.md`](implementation/coding-conventions.md) adopting six DoD idioms as Ladybug project conventions: static DP set once at boot, domain-based module split with 6-char prefixed names, table-driven dispatch with `EQU` offset records, SWI as syscall layer (with a flag to verify against GIME IRQ choices), routine header contract format (`Inputs:` / `Returns:`), banner comment style. Created [`implementation/scheduler.md`](implementation/scheduler.md) as a *candidate* pattern — DoD's TCB round-robin scheduler sketched and weighed against a flat main loop, decision deferred to implementation. Created [`implementation/lessons-learned.md`](implementation/lessons-learned.md) (was index-only, never written) with the "DoD anti-patterns we won't copy" list: tape I/O, CoCo 1/2 SAM/PIA legacy init, 3D vector-graphics macros, 24-bit fixed-point shift chains, BASIC ROM trampolines (incompatible with our locked all-RAM mode).

Updated [`index.md`](index.md) for the new pages.

---

## [2026-05-07] decision | Bare-metal boot strategy locked

Documented the Ladybug boot path: cartridge ROM at `$C000`, control taken via the BASIC reset-init's CART → PIA2 CB1 → FIRQ handshake, then immediate switch to all-RAM mode + 1.78 MHz clock + ACVC Vbord IRQ for the 60 Hz tick. We will not depend on BASIC's PIA initialisation; we re-init both PIAs ourselves. Init0 bit 3 will be set so the primary IRQ jump table at `$FEEE-$FEFF` remains reachable independently of PAR7. Rationale captured in [`platform/cartridge.md`](platform/cartridge.md).
