# Wiki Index

Content catalog. Read this first when answering a query to find the right page, then drill in.

## Game design

- [Game design overview](game/overview.md) — full design doc: playfield, entities, scoring, vegetable cycle, open questions for the CoCo 3 port
- `game/maze.md` — playfield, turnstiles, edibles _(stub)_
- `game/enemies.md` — skull and bug AI _(stub)_
- `game/scoring.md` — point values, bonus letters, special-vegetable cycle _(stub)_

## Platform / technology

_(bare-metal CoCo 3 / 6809, no NitrOS-9)_

- [6809.md](platform/6809.md) — MC6809E / MC68B09E programming model, addressing modes, interrupt sequences, clock-rate envelope
- [gime.md](platform/gime.md) — GIME (ACVC) register catalog: Init0/1, video mode/res, palette ($FFB0-$FFBF), MMU PARs ($FFA0-$FFAF), border, scroll, ACVC IRQ/FIRQ enables, legacy SAM bits
- [memory.md](platform/memory.md) — virtual/physical memory, MMU, PAR sets, ROM/RAM modes, dedicated-address map, cartridge boot window
- [timing.md](platform/timing.md) — MPU clock options, Vbord/Hbord/Timer/PIA1 IRQ sources, 60 Hz frame budget at 1.78 MHz
- [input.md](platform/input.md) — keyboard matrix scan, fire buttons, joystick X/Y via PIA2 DAC + comparator
- [sound.md](platform/sound.md) — 6-bit DAC + 1-bit PB1 square-wave audio paths, selector-switch setup
- [cartridge.md](platform/cartridge.md) — 40-pin pinout, CART → PIA2 CB1 → FIRQ auto-start, our boot sequence
## Tooling

- [tooling/index.md](tooling/index.md) — catalog of build/deploy tools (lwasm, xroar, toolshed) and the WSL-driven workflow
- [tooling/lwtools.md](tooling/lwtools.md) — `lwasm` 6809 cross-assembler: invocation, flags, output formats
- [tooling/xroar.md](tooling/xroar.md) — XRoar CoCo 3 emulator: cart boot profile, debug/trace flags
- [tooling/toolshed.md](tooling/toolshed.md) — `decb`/`os9` disk utilities: standby, fallback for a future `.dsk` deploy mode
- [tooling/build-workflow.md](tooling/build-workflow.md) — runbook: source → ROM → emulator (driven by `scripts/build.sh`)
- [tooling/web-app-architecture.md](tooling/web-app-architecture.md) — locally-hosted retro-dev web app: module split, data conventions, schemas (v2 design)

## Implementation

- [implementation/roadmap.md](implementation/roadmap.md) — phased plan from empty `src/` to finished game; POCs + review gates per phase
- `implementation/data-structures.md` — entity/sprite/maze representations _(stub)_
- [implementation/coding-conventions.md](implementation/coding-conventions.md) — project assembly conventions (DP discipline, module split, table-driven dispatch, SWI syscalls, header contracts)
- [implementation/video-mode.md](implementation/video-mode.md) — chosen GIME mode (320×192×16) + layout + pixel/tile/sprite formats
- [implementation/memory-map.md](implementation/memory-map.md) — physical/virtual page layout, 32 K cart image structure, boot data-copy procedure, Phase 4 sprite-data open question
- [implementation/scheduler.md](implementation/scheduler.md) — TCB round-robin scheduler — _candidate pattern, not committed_
- [implementation/lessons-learned.md](implementation/lessons-learned.md) — observed-fact findings; DoD anti-patterns we won't copy
- [implementation/emulator-monitor-tester.md](implementation/emulator-monitor-tester.md) — requirements for the 4-WS tester+webapp initiative (tester ROM, live FB, mapped regions, mode matrix)
- `implementation/build-workflow.md` — _(superseded by [tooling/build-workflow.md](tooling/build-workflow.md))_

## Sources

- [coco-asm-tepolt.md](sources/coco-asm-tepolt.md) — Assembly Language Programming for the Color Computer (Tepolt, ~1985) — 6809 ISA, addressing modes, SAM, PIAs, VDG, cartridge connector
- [coco3-asm-tepolt.md](sources/coco3-asm-tepolt.md) — Assembly Language Programming for the CoCo 3 (Tepolt, 1987) — GIME (ACVC), MMU, palette regs, hi-res displays, ACVC interrupts, reset init
- [ladybug-arcade.md](sources/ladybug-arcade.md) — Lady Bug arcade — aggregated public web sources, with gaps flagged
- [arcade-gfx-extraction.md](sources/arcade-gfx-extraction.md) — pipeline for ROM-extracting tiles/sprites/palette via MAME gfx layouts; gotchas log
- [dod-source.md](sources/dod-source.md) — Dungeons of Daggorath cartridge source (1983, lwasm-compatible 2022 reconstruction) — mined for transferable 6809 idioms

## Backlog

- [backlog/rgb-tv-input-palette.md](backlog/rgb-tv-input-palette.md) — switch XRoar to RGB monitor mode and re-derive the empirical palette table (mostly done; 3-tile acceptance blocked)
- [backlog/phase2-fb-render-regression.md](backlog/phase2-fb-render-regression.md) — Phase 2.x main.s shows FB as red+green noise; minimal-MMU-off cart works; bug is in MMU/PAR/self-copy chain
- [backlog/cart-ram-corruption.md](backlog/cart-ram-corruption.md) — Phase 2.3 IRQ-install path derails the CPU under the post-2.3 MMU layout; cart RAM gets overwritten
- [backlog/retro-dev-web-app.md](backlog/retro-dev-web-app.md) — wrap lwasm + XRoar + gdb-mcp + LLM into a browser-based retro dev environment
- [backlog/mcp-xroar-server.md](backlog/mcp-xroar-server.md) — cost/benefit of a purpose-built XRoar MCP server vs. the current gdb-mcp stack; deferred until sentinel probes hit a wall
- [backlog/xroar-load-gdb-patch.md](backlog/xroar-load-gdb-patch.md) — feasibility report: one-line `SO_REUSEADDR` patch fixes the `-load + -gdb` bind failure; ~2-3 h to apply + verify + upstream

## Special

- [CLAUDE.md](CLAUDE.md) — wiki schema and workflows
- [log.md](log.md) — chronological activity log
