---
name: xroar
description: CoCo 3 emulator — invocation profile for booting the Ladybug cart, plus debug/trace flags.
type: tool
tags: [tooling, xroar, emulator]
updated: 2026-05-08
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
| `-gdb-port N` | Override port. |
| `-trace` | Start with instruction trace dumping to stderr. Massive output — pair with shell redirect (`2>trace.log`) and `-trap-trace` if possible. |
| `-trace-timing` | Add cycle counts to trace output — useful for verifying the 60 Hz Vbord budget from [../platform/timing.md](../platform/timing.md). |
| `-no-ratelimit` | Run as fast as possible — for batch/headless test runs. Don't use for visual checks. |
| `-fskip N` | Frameskip — combine with `-no-ratelimit` for fast smoke tests. |

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
