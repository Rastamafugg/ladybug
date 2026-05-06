# Wiki Index

Content catalog. Read this first when answering a query to find the right page, then drill in.

## Game design

- [Game design overview](game/overview.md) — full design doc: playfield, entities, scoring, vegetable cycle, open questions for the CoCo 3 port
- `game/maze.md` — playfield, turnstiles, edibles
- `game/enemies.md` — skull and bug AI
- `game/scoring.md` — point values, bonus letters, special-vegetable cycle

## Platform / technology

_(stubs — bare-metal CoCo 3 / 6809, no NitrOS-9)_

- `platform/gime.md` — GIME hardware: palette ($FFB0–$FFBF), MMU/PARs ($FFA0–$FFAF), video modes, IRQ/FIRQ, Vbord (60 Hz), MPU speed
- `platform/memory.md` — CoCo 3 512K memory map, MMU bank layout, ROM/RAM placement, cartridge entry
- `platform/timing.md` — 60 Hz Vbord, frame budget, IRQ-driven scheduling
- `platform/input.md` — keyboard matrix, joystick (PIA), polling
- `platform/sound.md` — 6-bit DAC, sound generation on bare-metal
- `platform/toolchain.md` — assembler choice, build flags, output format (DECB BIN, cartridge ROM, disk image)

## Implementation

- `implementation/roadmap.md` — phase plan
- `implementation/data-structures.md` — entity/sprite/maze representations
- `implementation/lessons-learned.md` — observed-fact findings
- `implementation/build-workflow.md` — assembler invocation, image build, emulator/hardware deploy

## Sources

- `sources/coco3-asm-tepolt.md` — Assembly Language Programming for the CoCo 3 (Tepolt, 1987) _(stub)_
- [Lady Bug arcade — web ingest](sources/ladybug-arcade.md) — aggregated public web sources, with gaps flagged

## Special

- [CLAUDE.md](CLAUDE.md) — wiki schema and workflows
- [log.md](log.md) — chronological activity log
