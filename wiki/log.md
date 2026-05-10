# Wiki Log

Append-only chronological record of ingests, queries, and lints. Each entry prefixed `## [YYYY-MM-DD] <type> | <title>` so the log is grep-parseable.

---

## [2026-05-10] finding | XRoar cartridge-window read quirk at `$C0D9-$C0DB`

Created and ran a minimal ROM probe (`src/rom_probe.s`) that reads `$C000-$C0FF` before writing that range and logs mismatches to `$01FF/$0200`. Under XRoar 1.10 it reported exactly three bad reads: `$C0D9=$7E`, `$C0DA=$E2`, `$C0DB=$9D` where the cartridge image has `$00,$00,$00`. XRoar GDB traps showed the main boot `copyloop` reads those bad bytes directly, so the broad ROM-to-RAM copy stores bad source bytes rather than suffering a later overwrite. Patched `src/main.s` to skip `$C0D9-$C0DB` during the boot copy and keep that absolute range as unused padding; documented the quirk in `implementation/lessons-learned.md`.

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

## [2026-05-08] ingest | Arcade gfx extraction pipeline

Built `scripts/extract_arcade_gfx.py` to decode arcade Lady Bug graphics from `ladybug.zip` (MAME romset) into indexed pixel grids + palette JSON + per-attr PNG previews under `assets/arcade/`. Decoder mirrors MAME `ladybug.cpp` `charlayout`/`spritelayout`/`ladybug_palette()` exactly. Output: 512 × 8×8 chars, 128 × 16×16 sprites, 32-color palette, 8 char color attrs, 2×8 sprite color attrs (set A from low nibble of PROM `10-1.f4`, set B from high nibble). User-confirmed colorizations: maze/HUD = char attr 0, enemies + vegetables = various Set A attrs, death-angel-wings animation = a Set B attr. Created [`sources/arcade-gfx-extraction.md`](sources/arcade-gfx-extraction.md) with the pipeline and 7-item gotchas list (palette PROM filename ≠ role, char lookup is a formula not a PROM, sprite lookup PROM serves both color sets via low/high nibbles, palette is inverted 2bpc, MAME `planes` list is MSB-first, sprite y-offsets are scrambled).

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

## [2026-05-08] phase | Phase 2.3 — GIME hi-res 320×192×16 + MMU + FB end-to-end — passed

After Path A (16 K cart) was committed, drove Phase 2 through three sub-gates: (2.1) shadow-RAM-during-write at phys $3E verified by writing a marker pre-TY=1 and reading it back post-TY=1 (got 'Z'); (2.2) full Phase 1 boot + cart self-copy + all-RAM, IRQ-driven frame counter still ticked from RAM-resident code; (2.3) GIME hi-res mode + MMU + PARs (`$38, $30..$33, $3D, $3E, $3F`) + vert-offset `$FF9D=$C0/$FF9E=$00` → FB at phys page $30 + palette load + CRES=11 blanking trick during init + IRQ-driven mainloop FB writes. Final visible: 16-stripe palette test with bright border + flashing IRQ-driven block on top of mid-screen stripe.

**Surprise:** XRoar's default CoCo 3 monitor renders the 6-bit palette via composite NTSC encoding, not the textbook RGB `RGBrgb` 2-bits-per-channel layout. `$3F` and `$30` both display as white (different luma, same chroma point); `$0C` is blue not green-ish; etc. Recorded the empirical 6-bit-value → colour mapping in [`implementation/video-mode.md`](implementation/video-mode.md) §"XRoar palette colours — empirical (composite NTSC)" and [`implementation/lessons-learned.md`](implementation/lessons-learned.md).

**Surprise (lesser):** the IRQ-driven mainloop write at row 96 produced visible tearing on the bottom edge (~7 pixels of next-row colour mid-frame). Cause is the unsynchronised fill loop racing the GIME raster — not a bug. Vsync-aware rendering will be addressed when the renderer matures.

Filed Phase 2.2 + 2.3 boot-sequence playbook to [`implementation/lessons-learned.md`](implementation/lessons-learned.md). Updated [`implementation/roadmap.md`](implementation/roadmap.md) Phase 2 with substep status (2.1, 2.2, 2.3 done; 2.4 = render arcade tile; 2.5 = automate `build_gfx.py`).

**One iteration cost:** lwasm rejected `fcb $38, $30, $31, ...` with spaces after commas — needed `fcb $38,$30,$31,...`. Filed mentally; the `coding-conventions` page should pick this up during a future lint pass.

---

## [2026-05-08] decision | Reverted to 16 K cart after XRoar boot gate failed

Phase 2 step 1 (assumption validation) caught two issues. **(1) Shadow-RAM-during-write at phys `$3E` works** — verified by writing a marker to `$C000`, going TY=1, reading it back. Boot data-copy procedure is sound. **(2) XRoar's handling of 32 K cart files via `-cart-rom` is unverified** — built a 32 K cart with the planned `$8000-$BFFF` data + `$C000-$FEFF` code split; boot landed at BASIC `OK`, consistent with XRoar mapping only the lower 16 K of the file at `$C000` regardless of size. XRoar's manual documents `-cart-rom` only as "mapped from `$C000`" — no 32 K behaviour described.

User decision: **Path A — revert to 16 K cart for now**, defer the cart-size question until Phase 4 sprite arithmetic gives real numbers. If we then need >16 K, pivot to **software bank-switched** (XRoar `-cart-type gmc` + CoCoSDC + multi-pak — universal hardware support, ~half-day refactor, only touches boot data-copy because runtime is all-RAM regardless). Not Init0 b1-b0 = `11`, since that mode is rare in actual cart hardware AND unverified in XRoar.

Reverted: `scripts/build.sh` → `CART_BYTES=16384`. Updated [`platform/cartridge.md`](platform/cartridge.md) §"Cart size — 16 K (current); 32 K and bank-switched options deferred", boot-sequence steps; [`platform/memory.md`](platform/memory.md) cart-boot section; [`tooling/build-workflow.md`](tooling/build-workflow.md), [`tooling/xroar.md`](tooling/xroar.md) (gotcha about `-cart-rom` / 32 K), [`tooling/index.md`](tooling/index.md), [`tooling/lwtools.md`](tooling/lwtools.md); [`implementation/video-mode.md`](implementation/video-mode.md) ROM-budget update (2bpp+attr sprites back as default), [`implementation/memory-map.md`](implementation/memory-map.md) cart layout + boot data-copy procedure simplified to single-org 16 K, Phase 4 sprite-data section revised; [`implementation/roadmap.md`](implementation/roadmap.md) standing-budget denominator + Phase 1/9/10 review-gate questions. Filed both findings to [`implementation/lessons-learned.md`](implementation/lessons-learned.md).

---

## [2026-05-08] decision | Memory map for Phase 2 + Phase 10 cart-shell gate

**Memory map.** Created [`implementation/memory-map.md`](implementation/memory-map.md) covering: 8-PAR allocation post-boot (1 system, 4 FB at phys `$30-$33`, 1 game-state placeholder, 2 code at phys `$3E-$3F`); 32 K cart-ROM image structure (data section at virtual `$8000-$BFFF`, code section at `$C000-$FEFF`); boot data-copy procedure relying on shadow-RAM-during-write semantics (Init0 b1-b0=11 → self-copy `$8000-$FEFF` → TY=1; ~80 ms boot-time cost). DP at `$0200-$02FF` allocation table started.

**Tight page budget surfaced.** 8 PARs vs 8-10 wanted post-Phase-4 (sprite data is the pinch point: ~15 K of sprites won't fit in 1 PAR alongside game state + FB + code + system). Documented four resolution options — (1) sprite 2bpp+attr compression — default, (2) bank-switch sprite PAR, (3) sliding FB write window, (4) shrink code to 8 K. Decision deferred to Phase 4 when real sprite count is known.

**Two open Phase-2 implementation validations** to do at first boot: shadow-RAM-during-write actually populates phys `$3C-$3F` with cart contents; XRoar correctly maps a 32 K cart image when Init0 b1-b0=11 is set.

**Phase 10 review-gate question added** (separate from memory map): does the chosen cart shell — CoCoSDC, RetroCloud, custom — actually respond to `$8000-$BFFF` accesses in Init0=11 mode? If not, half-day pivot to a software-bank-switched cart, since bank-switching only matters during boot's data-copy phase. Updated [`implementation/roadmap.md`](implementation/roadmap.md) Phase 10.

---

## [2026-05-08] decision | Cart retargeted to 32 K (Init0 b1-b0 = 11)

User pushed back on the implicit 16 K cart limit during Phase 2 ROM-budget analysis. Reviewed real options: (1) 16 K with 2bpp+attr sprite packing — fits but ties storage format to performance, (2) 32 K cart via Init0 b1-b0 = `11` — same boot model, requires 32 K EPROM + cart shell, (3) bank-switched cart — more complex, (4) floppy — reverses locked cart-only decision. Chose **(2) 32 K cart**: removes ROM pressure for full 4bpp sprite path, keeps boot model intact, defers bank-switching as a fallback if ever needed.

Updated `scripts/build.sh` (`CART_BYTES=32768`); rebuilt — Phase 1 cart still autostarts under XRoar (16 K of code/padding + 16 K trailing $FF padding). Updated wiki: [`platform/cartridge.md`](platform/cartridge.md) §"Cart size — 32 K" + revised boot sequence (Init0 b1-b0 = `11` switch comes before all-RAM, after we take control); [`platform/memory.md`](platform/memory.md) cart-boot section; [`tooling/build-workflow.md`](tooling/build-workflow.md) (32 KB pad, updated overflow guidance); [`implementation/video-mode.md`](implementation/video-mode.md) (ROM-budget update — 4bpp sprite path now default); [`implementation/roadmap.md`](implementation/roadmap.md) (Phase-9 review-gate question + standing budget-check denominator).

Cart-shell hardware implication: standard 16 K EPROM cart shells won't work. CoCoSDC, RetroCloud cart, and similar bank-switched / SD-cart hardware emulate larger ROMs transparently — likely target for development. Real-hardware bring-up at Phase 10 needs a 32 K-capable cart shell.

---

## [2026-05-08] decision | Video mode chosen — 320×192×16

Phase 2 first task: decided GIME mode for the rest of the project. Compared 320×192 vs 256×192 at 16 colours (depths below 16 ruled out by the 3-colour-cycle subsystem, hi-res text ruled out by per-pixel needs). 320×192 wins on HUD layout (64 px per side panel = 8 tiles, vs 32 px = 4 tiles in 256-wide), aspect, and familiarity in CoCo 3 ecosystem. Cost: extra 6 144 framebuffer bytes (one MMU page) and ~25 % more sprite-blit work — accepted; we have 512 K and a dirty-rect strategy regardless.

Locked formats: 8×8 px tiles (32 bytes), 16×16 px sprites (128 bytes), framebuffer at 160 bytes/row × 192 rows = 30 720 bytes. Estimated sprite-blit budget 5 400 cycles for ~9 simultaneous entities — fits the 18 000-cycle render allocation with margin. GIME register values noted as candidates (`$FF99`=`$1E`); Tepolt Table 4-10 to be re-verified at code time. Single-buffer with sprite save-restore is the default; double-buffer reconsidered at Phase 4 only if tearing is visible.

Created [`implementation/video-mode.md`](implementation/video-mode.md) with the full analysis, layout diagram, format definitions, six deferred sub-decisions, and three named risks. Fixed a stale claim in [`sources/coco3-asm-tepolt.md`](sources/coco3-asm-tepolt.md) line 84 about HRES=4 byte counts. Updated [`index.md`](index.md).

---

## [2026-05-08] phase | Phase 1 — Boot init + 60 Hz Vbord — passed

`src/main.s` grew to 95 bytes: DP=$02, PIA interrupts quieted, GIME `Init0=$A8` (COCO legacy, MMU off, ACVC-IRQ on, force-`$FExx`=$3F), TY=1 all-RAM, R1=1 fast clock, JMP-handler installed at `$FEF7`, Vbord enabled via `$FF92` b3, I-mask cleared. IRQ handler increments a 16-bit `FRAMES` counter at `$0202` and acks via `$FF92` read. Main loop renders both bytes to `$0400/$0401` on the legacy VDG screen — observed on XRoar at expected rates (high byte ~4.27 s/cycle, low byte fast flicker). No stray IRQ/FIRQ from PIA or other GIME sources.

**Resolved deferred question:** SWI/IRQ vector collision (flagged in [`coding-conventions.md §4`](implementation/coding-conventions.md) at ingest, gated to Phase 1). No collision — SWI vectors `$FFFA/$FFF4/$FFF2` are disjoint from IRQ/FIRQ at `$FFF8/$FFF6`, and BASIC's SWI2/SWI3 use is moot in all-RAM mode. Updated coding-conventions.md to remove the warning. Filed both Phase 1 results and the SWI resolution to [`implementation/lessons-learned.md`](implementation/lessons-learned.md). Roadmap Phase 1 marked done.

---

## [2026-05-08] phase | Phase 0 — Hello cart — passed

22-byte stub at `$C000` with `FCC "DK"` autostart magic + entry code took control under XRoar via the BASIC CART/FIRQ handshake. Screen showed our 32-byte `$AA` marker on row 0 over BASIC's default `$60` green fill — no banner, no `OK` prompt. Confirmed [`platform/cartridge.md`](platform/cartridge.md)'s boot handshake description is correct as written. Filed Phase-0 finding to [`implementation/lessons-learned.md`](implementation/lessons-learned.md), including a sanity-note on CoCo VDG SG4 byte semantics. Roadmap Phase 0 marked done. Created [`src/main.s`](../src/main.s) (first source file in `src/`).

---

## [2026-05-08] phase | Phase 2.4 — first arcade tile rendered (after debugging session)

Hand-converted arcade `chars.json[432]` (dense tile that uses all four pixvals 0/1/2/3) to 32 bytes of 4bpp GIME tile data with direct pixval→palette mapping. Reassigned palette idx 0-3 to a 4-colour sub-palette (black/yellow/blue/white) per the empirical XRoar table in [video-mode.md](implementation/video-mode.md). Wrote `blit_tile` and rendered three copies on a black-cleared FB at tile coords (2,4), (10,20), (20,36). Replaced the FRAMES ticker with `sync; bra *` so the tiles remain stable while IRQ continues. ROM size 294 bytes / 16384.

**Bug found and fixed during the session:** the obvious `ldb #8` / `decb` / `bne` loop in `blit_tile` is broken because `ldd ,y++` clobbers B (D=A:B). The counter gets overwritten with tile-data low bytes each iteration. Fixed by switching to a `cmpy ,s` against an end-of-tile sentinel pushed onto the stack at entry. Filed in [implementation/lessons-learned.md](implementation/lessons-learned.md) as a recurring 6809 idiom-trap to avoid in future blit/copy loops.

A separate observation during a 64×64 solid-block diagnostic: identical write code at three FB positions produced a clean rectangle at top-left (PAR1) and bottom-right (PAR4) but a partially-striped rectangle at the middle position (PAR2). Cause unknown; probably an interaction between specific scan-line ranges and XRoar's composite-NTSC artifacting, since the 8×8 tiles render correctly. Flag for follow-up if Phase 2.5's automated tile pipeline reproduces the symptom.

Phase 2.5 will automate the chars.json → GIME tile-data conversion via `build_gfx.py`.

---

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
