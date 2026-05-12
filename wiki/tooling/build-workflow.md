---
name: Build workflow
description: End-to-end runbook — source → ROM → emulator. Driven by scripts/build.sh; every step is also documented as a manual command.
type: runbook
tags: [tooling, build, workflow, runbook]
updated: 2026-05-12
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
   │  pad with 0xFF to 16384 bytes
   ▼
build/ladybug.rom    (16 KB cart-ready)
   │
   │  xroar -machine coco3 -ram 512 -cart-type rom -cart-rom ... -cart-autorun
   ▼
emulated CoCo 3      (real hardware: write ROM to a 16K EPROM, drop into cart shell)
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

### 2. Pad to 16 KB

```bash
python3 -c "
data = open('build/ladybug.rom','rb').read()
pad  = 16384 - len(data)
assert pad >= 0, f'ROM is {len(data)} bytes — exceeds 16 KB'
open('build/ladybug.rom','wb').write(data + b'\xff'*pad)
print(f'padded {16384-pad} → 16384 bytes')
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

There are multiple execution contexts in Codex. The Windows PowerShell sandbox may report no installed WSL distributions even though the already-running `gdb-mcp` MCP server has a Linux host environment with `/mnt/d/retro/ladybug`, `/usr/local/bin/xroar`, and `/usr/local/bin/m6809-gdb`.

If PowerShell `wsl.exe` works, a Windows-side session can launch the normal run flow with:

```powershell
wsl -d Ubuntu -- bash -lc 'cd /mnt/d/retro/ladybug && ./scripts/build.sh run'
```

Inside WSL, paths to the project work via `/mnt/d/retro/ladybug` (the script `cd`s itself there). Inside Linux directly, run `./scripts/build.sh run` from the project root.

If PowerShell reports no WSL distributions, do not conclude that runtime launch is impossible. Use the GDB-MCP-hosted Linux shell instead:

```gdb
shell cd /mnt/d/retro/ladybug && ./scripts/build.sh build
shell cd /mnt/d/retro/ladybug && nohup /usr/local/bin/xroar -machine coco3 -ram 512 -cart ladybug -cart-type rom -cart-rom build/ladybug.rom -cart-autorun -gdb -gdb-ip 127.0.0.1 -gdb-port 65520 > /tmp/ladybug-xroar.log 2>&1 & echo $!
```

Then start a fresh GDB-MCP session and attach with:

```gdb
target remote :65520
```

## Debug variants

| Need | Command |
|-|-|
| GDB stub on `127.0.0.1:65520` | append `-gdb` to the xroar call (or set `XROAR_EXTRA="-gdb"` env var if the script supports it) |
| GDB stub reachable from WSL-hosted `gdb-mcp` when XRoar runs on Windows | append `-gdb -gdb-ip 0.0.0.0 -gdb-port 65520` |
| GDB remote-stub diagnostics | append `-debug-gdb -1` |
| Instruction trace | append `-trace 2>build/trace.log` |
| Run as fast as possible (smoke test) | append `-no-ratelimit -fskip 100` |

For the full XRoar plus GDB-MCP attach workflow, see [xroar.md §GDB-MCP round trip](xroar.md#gdb-mcp-round-trip).

## Probe ROM variant

`scripts/build.sh` always builds `src/main.s` into `build/ladybug.rom`. To run a one-off diagnostic source such as `src/rom_probe.s`, use the same WSL-hosted assemble, pad, and xroar sequence with the input and output names changed:

```powershell
wsl -- bash -lc 'cd /mnt/d/retro/ladybug && mkdir -p build && lwasm -9 --format=raw --output=build/rom_probe.rom --list=build/rom_probe.lst --symbols --map=build/rom_probe.map src/rom_probe.s && python3 - build/rom_probe.rom 16384 <<'"'"'PY'"'"'
import sys
path, target = sys.argv[1], int(sys.argv[2])
data = open(path, "rb").read()
pad = target - len(data)
if pad < 0:
    sys.exit(f"probe: ROM is {len(data)} bytes — exceeds {target} byte cart window")
open(path, "wb").write(data + b"\xff" * pad)
print(f"probe: padded {len(data)} → {target} bytes ({path})")
PY
xroar -machine coco3 -ram 512 -cart ladybug-probe -cart-type rom -cart-rom build/rom_probe.rom -cart-autorun -gdb -gdb-ip 127.0.0.1 -gdb-port 65520'
```

If XRoar runs on Windows and `gdb-mcp` runs under WSL, use `-gdb-ip 0.0.0.0` instead of `127.0.0.1`.

## When this runbook breaks

- **`lwasm: command not found`** — WSL `~/coco-tools/lwtools` not built/installed. Reinstall: `cd ~/coco-tools/lwtools && make && sudo make install`.
- **`xroar: command not found`** — same pattern under `~/coco-tools/xroar`; check its `INSTALL` for SDL/GTK build deps.
- **`build: ROM is 16385 bytes — exceeds 16 KB`** — code+data overflowed the 16 KB cart window. Expansion path documented in [../platform/cartridge.md §"Cart size — 16 K (current); 32 K and bank-switched options deferred"](../platform/cartridge.md).
- **No xroar window from Windows host** — WSLg should hand off automatically on Win 11. Test with `wsl -d Ubuntu -- bash -lc "xeyes"` to confirm GUI passthrough; if blank, restart WSL: `wsl --shutdown`.
- **xroar boots to BASIC OK prompt instead of our cart** — `-cart-autorun` missing, or our `JMP` at `$C000` isn't where BASIC's FIRQ handler expects (see boot handshake in [../platform/cartridge.md](../platform/cartridge.md)).

## Sources

- [lwtools.md](lwtools.md), [xroar.md](xroar.md), [toolshed.md](toolshed.md)
- [../platform/cartridge.md](../platform/cartridge.md) — boot handshake
- [../platform/memory.md](../platform/memory.md) — cart window placement
