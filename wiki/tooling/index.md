---
name: Tooling index
description: Catalog of build/deploy tools used for Ladybug — lwtools, toolshed, xroar — plus the end-to-end build workflow.
type: index
tags: [tooling, build, lwtools, toolshed, xroar]
updated: 2026-05-08
---

# Tooling

All tools are installed in WSL Ubuntu under `~/coco-tools/`. The host `scripts/build.sh` shells out to WSL so building is one command from either side.

| Tool | Role | Active in build? | Page |
|-|-|-|-|
| **lwasm** (lwtools 4.24) | 6809 cross-assembler — produces the cartridge ROM image | yes | [lwtools.md](lwtools.md) |
| **xroar** (1.10) | CoCo 3 emulator — boots the cart for iteration | yes | [xroar.md](xroar.md) |
| **toolshed** (`decb`, `os9`) | DECB/OS-9 disk image manipulation | **not currently** — kept on hand if we add a `.dsk` deploy path later | [toolshed.md](toolshed.md) |

## Build workflow

[build-workflow.md](build-workflow.md) — the full runbook: source → ROM → emulator. Driven by `scripts/build.sh`.

## Deploy target

Cartridge ROM image (32 KB, mapped at `$8000-$FEFF` on a real CoCo 3 once Init0 b1-b0 is set to `11`; entry point at `$C002` via the CART → FIRQ handshake — see [../platform/cartridge.md](../platform/cartridge.md)). No floppy, no NitrOS-9. Cart-size decision logged 2026-05-08; reconsider only if a bank-switched cart becomes necessary.

## WSL access

The host (Windows) Claude session can drive WSL directly with `wsl -d Ubuntu -- bash -lc "..."`. The build script uses this to keep a single source of truth for invocations.
