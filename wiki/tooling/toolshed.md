---
name: toolshed
description: DECB / OS-9 disk image utilities — installed but NOT in the active build path; fallback for a future .dsk deploy mode.
type: tool
tags: [tooling, toolshed, decb, os9]
updated: 2026-05-08
---

# Toolshed (`decb`, `os9`, friends)

The CoCo cross-development utility suite (originally by Boisy Pitre, now maintained at https://github.com/n6il/toolshed). Installed at `/usr/local/bin/{decb,os9}` from `~/coco-tools/toolshed`. Reference: https://github.com/n6il/toolshed/blob/master/doc/ToolShed.md.

## Status: standby

**Not currently invoked by the build.** Ladybug deploys as a [cartridge ROM image](../platform/cartridge.md), so we go directly from `lwasm` raw output → padded ROM → xroar `-cart-rom`. No disk image is built.

Toolshed is documented here so we can switch over quickly if iteration becomes painful (e.g. if we want to load via Disk BASIC `LOADM` instead of rebuilding/restarting the cart, or if we ship a `.dsk` for floppy distribution).

## If we switch to a `.dsk` deploy path (Disk BASIC, NOT OS-9)

Reassemble with DECB header so the binary carries its load and exec addresses:

```bash
lwasm -9 --format=decb --output=build/ladybug.bin --list=build/ladybug.lst src/main.s
```

Build a fresh DECB-format disk image and copy the binary in:

```bash
decb dskini -3 build/ladybug.dsk          # init a 35-track single-sided disk
decb copy -2 -b -r build/ladybug.bin build/ladybug.dsk,LADYBUG.BIN
decb dir build/ladybug.dsk                # verify
```

Flag notes:
- `-2` selects DECB filesystem on the destination.
- `-b` binary mode (no LF/CR translation).
- `-r` replace if exists.

Run via xroar:
```bash
xroar -machine coco3 -ram 512 -load-fd0 build/ladybug.dsk
# at the BASIC prompt: LOADM"LADYBUG":EXEC
```

## OS-9 path (`os9` tool) — explicitly out of scope

`os9` formats and manipulates **OS-9 / NitrOS-9** filesystem images. File permissions (`os9 attr`) are an OS-9 filesystem concept. Ladybug runs bare-metal, so there's nothing on the target to mount an OS-9 disk. Do not use this path unless we revisit the no-NitrOS-9 decision in [../../CLAUDE.md](../../CLAUDE.md).

## Sources

- Doc: https://github.com/n6il/toolshed/blob/master/doc/ToolShed.md
- Local install: `~/coco-tools/toolshed` (source), `/usr/local/bin/{decb,os9}`
- `decb --help` and `os9 --help` for full subcommand lists.
