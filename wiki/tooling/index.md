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

Cartridge ROM image (16 KB, mapped at `$C000-$FEFF` on a real CoCo 3, boots via the CART → FIRQ handshake — see [../platform/cartridge.md](../platform/cartridge.md)). No floppy, no NitrOS-9. 32 K (Init0=11) and software bank-switched (CoCoSDC / `-cart-type gmc`) are documented next-step expansion paths if 16 K turns out insufficient — see [../platform/cartridge.md §"Cart size — 16 K (current)"](../platform/cartridge.md).

## WSL access

The host (Windows) Claude session can drive WSL directly with `wsl -d Ubuntu -- bash -lc "..."`. The build script uses this to keep a single source of truth for invocations.
