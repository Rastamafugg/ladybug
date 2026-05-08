---
name: lwtools / lwasm
description: 6809 cross-assembler — invocation, flags, output formats, and the canonical Ladybug build command.
type: tool
tags: [tooling, lwtools, lwasm, assembler]
updated: 2026-05-08
---

# lwasm — 6809 cross-assembler

Part of [lwtools](https://www.lwtools.ca/manual/manual.html) by William Astle. Installed at `/usr/local/bin/lwasm` (built from `~/coco-tools/lwtools`). Version: **4.24**.

## Why this assembler

- Modern, actively maintained, native cross-assembler (no DOS/CoCo round-trip).
- First-class 6809 *and* 6309 support; we lock to 6809 mode (`-9`) since the CoCo 3 ships with a 68B09E.
- Multiple output formats — we use `raw` for the cartridge ROM.
- Macros, conditionals, sections, listings, symbol dumps.

## Canonical invocation

```bash
lwasm -9 \
      --format=raw \
      --output=build/ladybug.rom \
      --list=build/ladybug.lst \
      --symbols \
      --map=build/ladybug.map \
      src/main.s
```

Flag-by-flag:

| Flag | Why |
|-|-|
| `-9` / `--6809` | Reject 6309-only opcodes — the CoCo 3 CPU is a 68B09E. |
| `--format=raw` | Emit a flat binary starting at the assembled ORG. No DECB header, no OS-9 module header. Ready for cart padding. |
| `--output=FILE` | Output binary path. |
| `--list=FILE` | Listing file with addresses, opcodes, source side-by-side. Crucial for cycle counting and cross-referencing crash addresses. |
| `--symbols` | Include symbol table in listing. |
| `--map=FILE` | Separate symbol/address map — easier to grep than the listing. |

Source convention: top-level entry assembled with `ORG $C000` so the raw output drops straight into the cart window (see [../platform/cartridge.md](../platform/cartridge.md) and [../platform/memory.md](../platform/memory.md)).

## Other output formats (reference)

`--format=` accepts: `raw`, `decb` (Disk BASIC `.bin` with load/exec headers), `os9` (NitrOS-9 module), `ihex`, `srec`, `obj` (proprietary linkable), `dragon`, `abs`, `basic`. We only use `raw` today; `decb` is the fallback if we ever switch to a `LOADM` deploy path.

## Padding to cart size

`raw` output is exactly the assembled byte count. Cartridge ROMs need to be a power of two; Ladybug uses a 16 KB cart at `$C000-$FEFF` ([../platform/cartridge.md §"Cart size — 16 K (current)"](../platform/cartridge.md)). Note the top `$FF00-$FFFF` is the I/O window, not cart-visible, so the cart's last 256 bytes are effectively unused. The build script pads with `0xFF` to 16384 bytes after assembly:

```bash
python3 -c "
import sys
data = open('build/ladybug.rom','rb').read()
pad = 16384 - len(data)
assert pad >= 0, f'ROM is {len(data)} bytes — exceeds 16KB'
open('build/ladybug.rom','wb').write(data + b'\\xff'*pad)
"
```

## Errors / gotchas

- **No `ORG`?** Output starts at `0` — useless for a cart. Always `ORG $C000` at the top.
- **Branch out of range** — `lwasm` will error with the exact source line; switch `BRA`→`LBRA`, `BEQ`→`LBEQ`, etc.
- **Implicit direct page** — by default DP is `0`; if we set DPR via `SETDP` pseudo-op, the assembler trusts us. A mismatch between `SETDP` and the actual `TFR a,dp` at runtime silently corrupts addressing.
- **Listing line numbers** off by include depth — use `--list-nofiles` to suppress filenames if grepping hot inner loops.

## Sources

- Manual: https://www.lwtools.ca/manual/manual.html
- Local install: `~/coco-tools/lwtools` (source), `/usr/local/bin/lwasm`
- `lwasm --help` for the full flag list.
