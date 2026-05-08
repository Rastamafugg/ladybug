---
name: Build workflow
description: End-to-end runbook — source → ROM → emulator. Driven by scripts/build.sh; every step is also documented as a manual command.
type: runbook
tags: [tooling, build, workflow, runbook]
updated: 2026-05-08
---

# Build & deploy runbook

## Overview

```
src/*.s                              (hand-written 6809 assembly)
   │
   │  lwasm -9 --format=raw --output=build/ladybug.rom
   ▼
build/ladybug.rom    (raw binary, exact size)
   │
   │  pad with 0xFF to 32768 bytes
   ▼
build/ladybug.rom    (32 KB cart-ready)
   │
   │  xroar -machine coco3 -ram 512 -cart-type rom -cart-rom ... -cart-autorun
   ▼
emulated CoCo 3      (real hardware: write ROM to a 32K EPROM in a 32K-capable cart shell)
```

## One-command interface

`scripts/build.sh` is the entry point. Run from anywhere — it routes to WSL automatically when invoked from the Windows host.

| Command | What it does |
|-|-|
| `scripts/build.sh build` | Assemble + pad. Output: `build/ladybug.rom`, `build/ladybug.lst`, `build/ladybug.map`. |
| `scripts/build.sh run` | `build`, then launch xroar with the canonical cart profile. |
| `scripts/build.sh clean` | `rm -rf build/`. |

Source layout the script assumes:
```
src/main.s          (top of build, ORG $C000)
build/              (created if missing; everything generated lands here)
scripts/build.sh
```

## Manual equivalents

If the script is broken or you want to invoke a step in isolation, all three steps work standalone:

### 1. Assemble

```bash
mkdir -p build
lwasm -9 --format=raw \
      --output=build/ladybug.rom \
      --list=build/ladybug.lst \
      --symbols \
      --map=build/ladybug.map \
      src/main.s
```

### 2. Pad to 32 KB

```bash
python3 -c "
data = open('build/ladybug.rom','rb').read()
pad  = 32768 - len(data)
assert pad >= 0, f'ROM is {len(data)} bytes — exceeds 32 KB'
open('build/ladybug.rom','wb').write(data + b'\xff'*pad)
print(f'padded {32768-pad} → 32768 bytes')
"
```

### 3. Run

```bash
xroar -machine coco3 -ram 512 \
      -cart ladybug -cart-type rom \
      -cart-rom build/ladybug.rom \
      -cart-autorun
```

## Cross-platform invocation

The Windows-side Claude session shells into WSL with:

```powershell
wsl -d Ubuntu -- bash -lc 'cd /mnt/d/retro/ladybug && ./scripts/build.sh run'
```

Inside WSL, paths to the project work via `/mnt/d/retro/ladybug` (the script `cd`s itself there). Inside Linux directly, run `./scripts/build.sh run` from the project root.

## Debug variants

| Need | Command |
|-|-|
| GDB stub on `127.0.0.1:65520` | append `-gdb` to the xroar call (or set `XROAR_EXTRA="-gdb"` env var if the script supports it) |
| Instruction trace | append `-trace 2>build/trace.log` |
| Run as fast as possible (smoke test) | append `-no-ratelimit -fskip 100` |

## When this runbook breaks

- **`lwasm: command not found`** — WSL `~/coco-tools/lwtools` not built/installed. Reinstall: `cd ~/coco-tools/lwtools && make && sudo make install`.
- **`xroar: command not found`** — same pattern under `~/coco-tools/xroar`; check its `INSTALL` for SDL/GTK build deps.
- **`build: ROM is 32769 bytes — exceeds 32 KB`** — code+data overflowed the 32 KB cart window. Options, in cost order: (1) compress sprites (2bpp+attr or RLE), (2) curate the asset set harder, (3) move to a bank-switched cart — see [../platform/cartridge.md §"Cart size — 32 K"](../platform/cartridge.md).
- **No xroar window from Windows host** — WSLg should hand off automatically on Win 11. Test with `wsl -d Ubuntu -- bash -lc "xeyes"` to confirm GUI passthrough; if blank, restart WSL: `wsl --shutdown`.
- **xroar boots to BASIC OK prompt instead of our cart** — `-cart-autorun` missing, or our `JMP` at `$C000` isn't where BASIC's FIRQ handler expects (see boot handshake in [../platform/cartridge.md](../platform/cartridge.md)).

## Sources

- [lwtools.md](lwtools.md), [xroar.md](xroar.md), [toolshed.md](toolshed.md)
- [../platform/cartridge.md](../platform/cartridge.md) — boot handshake
- [../platform/memory.md](../platform/memory.md) — cart window placement
