# Ladybug

Ladybug is a 6809 assembly-language port of Universal's 1981 arcade game for the Tandy Color Computer 3 with 512 KiB of RAM. It targets native CoCo 3 hardware and runs without NitrOS-9.

## Project status

**Status as of 2026-09-23:** Active development in Phase 9, which covers polish, attract mode, high scores, and level progression. Recent current-ROM captures document attract and level-start presentation and gameplay animation. Open work includes credit and TOP-score accounting, demo-route coverage, and SPECIAL/EXTRA display between levels; full natural acceptance remains incomplete. Physical CoCo 3 hardware bring-up has not been completed. See the [current gameplay review](wiki/internal/tickets/rsch-013-20260923-visual-gameplay-intake.html) for findings and evidence.

The complete profile builds a 64 KiB ROM image for the four-bank GMC cartridge layout. A prebuilt image for the current `1.0.0-alpha` tag is available at [`roms/1.0.0-alpha.rom`](roms/1.0.0-alpha.rom).

- Size: 65,536 bytes (64 KiB)
- SHA-256: `9bd7daa97e8ad93f08b31e0258afb20d21593bf6189e34926ee7fcc0ddaea1a9`

## Download the source

You need Git and a Linux shell. On Windows, use Ubuntu under WSL. From that shell, clone the repository:

```sh
git clone https://github.com/Rastamafugg/ladybug.git
cd ladybug
```

## Build

Install Python 3 and LWTOOLS (`lwasm`). The [build runbook](wiki/internal/tooling/build-workflow.html) includes toolchain notes. Then build the complete game profile:

```sh
LADYBUG_PROFILE=complete bash scripts/build.sh build
```

The ROM is written to `build/ladybug.rom`. The build script also runs its asset, layout, and ROM verification steps.

## Run in XRoar

Install XRoar and make its `xroar` command available in the same Linux or WSL environment. Then run:

```sh
LADYBUG_PROFILE=complete bash scripts/build.sh run
```

This command builds the ROM and launches XRoar configured as a CoCo 3 with 512 KiB RAM and a GMC cartridge. The default build uses keyboard input.

For the full build workflow and project background, see the [build runbook](wiki/internal/tooling/build-workflow.html), [project wiki](wiki/index.html), and [implementation roadmap](wiki/internal/implementation/roadmap.html).