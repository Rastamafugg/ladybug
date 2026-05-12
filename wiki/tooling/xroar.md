---
name: xroar
description: CoCo 3 emulator — invocation profile for booting the Ladybug cart, plus debug/trace flags.
type: tool
tags: [tooling, xroar, emulator]
updated: 2026-05-12
---

# XRoar — CoCo 3 emulator

By Ciaran Anscomb. Installed at `/usr/local/bin/xroar`. Version: **1.10**. Reference: https://www.6809.org.uk/xroar/doc/xroar.shtml.

XRoar emulates the GIME, MMU, PIAs, ACVC IRQs, and the cartridge port — everything the boot sequence in [../platform/cartridge.md](../platform/cartridge.md) depends on.

## Canonical invocation (Ladybug cart)

```bash
xroar \
  -machine coco3 \
  -ram 512 \
  -cart ladybug \
  -cart-type rom \
  -cart-rom build/ladybug.rom \
  -cart-autorun
```

| Flag | Why |
|-|-|
| `-machine coco3` | NTSC CoCo 3, 1.78 MHz fast clock available, GIME present. |
| `-ram 512` | 512 KB — matches our target hardware spec. |
| `-cart ladybug` | Define a named cart profile (just a label). |
| `-cart-type rom` | Plain ROM cartridge (no Becker port, no MPI). |
| `-cart-rom FILE` | Path to the 16 KB padded ROM image from `lwasm` + pad step. |
| `-cart-autorun` | Triggers the CART → FIRQ handshake on startup so BASIC dispatches into our `JMP entry` at `$C000` without a manual `EXEC`. |

Default keymap is fine for now (PC keyboard mapped to CoCo 3 layout). Joystick mapping deferred until [../platform/input.md](../platform/input.md) work begins.

## Debug / iteration flags

| Flag | Use |
|-|-|
| `-gdb` | Enable GDB target on `127.0.0.1:65520`. Connect with a 6809-aware GDB build for register inspection / breakpoints. |
| `-gdb-ip ADDRESS` | Bind the GDB listener to an interface. Default is `127.0.0.1`; use `0.0.0.0` when Windows-hosted XRoar must be reachable from WSL-hosted `gdb-mcp`. |
| `-gdb-port N` | Override port. |
| `-debug-gdb FLAGS` | Log GDB remote-stub traffic. Use `-debug-gdb -1` when debugging attach failures. |
| `-trace` | Start with instruction trace dumping to stderr. Massive output — pair with shell redirect (`2>trace.log`) and `-trap-trace` if possible. |
| `-trace-timing` | Add cycle counts to trace output — useful for verifying the 60 Hz Vbord budget from [../platform/timing.md](../platform/timing.md). |
| `-no-ratelimit` | Run as fast as possible — for batch/headless test runs. Don't use for visual checks. |
| `-fskip N` | Frameskip — combine with `-no-ratelimit` for fast smoke tests. |

## GDB-MCP round trip

Use this workflow when Codex needs to inspect the live cartridge through the `gdb-mcp` MCP server.

### 1. Build the cartridge

```bash
cd /mnt/d/retro/ladybug
./scripts/build.sh build
```

### 2. Start XRoar with the GDB stub

If XRoar is launched inside the same WSL environment as `gdb-mcp`, loopback binding is enough:

```bash
cd /mnt/d/retro/ladybug
xroar \
  -machine coco3 \
  -ram 512 \
  -cart ladybug \
  -cart-type rom \
  -cart-rom build/ladybug.rom \
  -cart-autorun \
  -gdb \
  -gdb-ip 127.0.0.1 \
  -gdb-port 65520
```

If XRoar is launched on Windows and `gdb-mcp` runs under WSL, bind the stub to all interfaces:

```powershell
xroar -machine coco3 -ram 512 `
      -cart ladybug -cart-type rom `
      -cart-rom build/ladybug.rom `
      -cart-autorun `
      -gdb -gdb-ip 0.0.0.0 -gdb-port 65520
```

For attach diagnostics, add:

```text
-debug-gdb -1
```

### 3. Attach through GDB-MCP

The Codex MCP config starts `gdb-mcp` through WSL. `gdb` should resolve to the 6809 GDB:

```text
/home/rastamafugg/.local/bin/gdb -> /usr/local/bin/m6809-gdb
```

Start a GDB-MCP session, then run:

```gdb
show architecture
target remote :65520
```

Expected architecture:

```text
The target architecture is set to "auto" (currently "m6809").
```

Successful attach looks like:

```text
Remote debugging using :65520
0x0000c0a6 in ?? ()
```

The exact PC depends on the current ROM. For the current isolation build, `$C0A6` is `post_blit`, an intentional `bra post_blit` halt.

Useful first commands:

```gdb
info registers
x/8i $pc
x/16xb $pc
```

### Troubleshooting

| Symptom | Meaning / fix |
|-|-|
| `Truncated register ... in remote 'g' packet` | `gdb-mcp` launched host `/usr/bin/gdb` instead of the 6809 GDB. Ensure `~/.local/bin/gdb` resolves to `/usr/local/bin/m6809-gdb`, then start a fresh GDB-MCP session. |
| `Connection timed out` from `target remote :65520` | XRoar is not listening where `gdb-mcp` can reach it. Check the XRoar process and use `-gdb-ip 0.0.0.0` for Windows-hosted XRoar reached from WSL. |
| Raw TCP connects but GDB does not attach | Restart XRoar and attach directly without prior `/dev/tcp` probes; the stub behaves as a single active GDB endpoint. Add `-debug-gdb -1` if it repeats. |
| `set architecture m6809` fails | The GDB binary is not a 6809 build. `m6809-gdb --version` should report `--target=m6809`. |

## Iteration workflow

`scripts/build.sh run` builds the ROM and launches xroar with the canonical invocation above. To kill: close the xroar window or `Ctrl-C` the script (xroar handles SIGINT).

For headless / CI-style smoke tests (none today), add `-no-ratelimit -fskip 100` and pipe trace output.

## Gotchas

- **Cart ROM must be a power of 2.** XRoar will load any size but mapping behaviour for non-pow2 ROMs is undefined. Build script always pads to 16 KB.
- **`-cart-rom` is documented only as "mapped from `$C000`."** XRoar's handling of 32 KB cart files (whether for Init0 b1-b0 = `11` mode or otherwise) is unverified — observed behaviour in Phase 2.1 testing was consistent with XRoar mapping the *lower* 16 K of a 32 K file to `$C000` and the upper half being inaccessible. If/when we need >16 K cart, plan to use `-cart-type gmc` (Games Master Cartridge — software bank-switching) rather than rely on Init0=11.
- **Default machine config carries state across runs.** If a previous session changed PAR/palette in a weird way and you suspect emulator state pollution, clear `~/.xroar/` (config) — but normally a clean cart load resets the GIME via the boot path.
- **WSL display** — XRoar opens an X11/Wayland window. WSL2 with WSLg (Win11 default) handles this transparently. If no window appears, check `echo $DISPLAY` inside WSL.

## Sources

- Manual: https://www.6809.org.uk/xroar/doc/xroar.shtml
- Local install: `~/coco-tools/xroar` (source), `/usr/local/bin/xroar`
- `xroar --help` for the full flag list.
