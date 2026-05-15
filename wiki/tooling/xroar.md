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

There are three launch contexts to keep separate:

- **PowerShell sandbox** — may report that no WSL distributions are installed. Do not assume `wsl.exe` is usable from here.
- **GDB-MCP Linux host** — the already-running `gdb-mcp` process can run Linux shell commands through GDB's `shell` command. This has been the reliable Codex path for launching `/usr/local/bin/xroar`.
- **Windows desktop XRoar** — useful for manual visual runs, but its GDB listener must be reachable from the Linux-hosted GDB client.

Preferred Codex path: start XRoar from a GDB-MCP session using GDB's `shell` command. This does not require PowerShell `wsl.exe` to work:

```gdb
shell cd /mnt/d/retro/ladybug && nohup /usr/local/bin/xroar -machine coco3 -ram 512 -cart ladybug -cart-type rom -cart-rom build/ladybug.rom -cart-autorun -gdb -gdb-ip 127.0.0.1 -gdb-port 65520 > /tmp/ladybug-xroar.log 2>&1 & echo $!
```

Then attach from a fresh GDB-MCP session with `target remote :65520`.

If XRoar is launched from an interactive Linux/WSL shell in the same environment as `gdb-mcp`, loopback binding is enough:

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

If XRoar is launched on Windows and `gdb-mcp` runs under its Linux host, bind the stub to all interfaces:

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

## Reaching specific boot points reliably

The cart-autorun handshake fires on a 100 ms cart-FIRQ schedule ([../../docs/reference/xroar/src/cart.c:968-974](../../docs/reference/xroar/src/cart.c)) and is gated by BASIC's keyboard-polling latency, so several wall-clock seconds elapse before our cart entry at `$C000` runs. That clashes with gdb-mcp's default 30 s per-command timeout, which kills the entire session — losing breakpoints. Three workarounds, in increasing order of effort:

### 1. Bump per-command timeouts

Pass `timeout: 60` (or higher) explicitly on `mcp__gdb-mcp__continue_exec` and `mcp__gdb-mcp__exec_command` calls that may block past the handshake. Cheapest fix; should be the default for any `continue` issued before the cart entry has been reached.

### 2. Insert a temporary halt loop in source

Software breakpoints set via `break *0xC0xx` are unreliable during early boot because the gdb stub may resolve the address before the cart RAM-shadow is populated. The cheapest deterministic-stop pattern is a self-branch:

```
inspect_halt
        bra     inspect_halt    ; gdb-mcp attaches; PC parks here
```

Attach gdb-mcp, `interrupt` to stop the CPU (it'll be in the `bra .` loop), then `info reg` / `x/16xb` to read state. Remove the halt before committing.

**Do NOT use `swi`** for this purpose. Empirically, XRoar 1.10 segfaults when it tries to snapshot at a `swi` trap point (see [backlog/cart-ram-corruption.md](../backlog/cart-ram-corruption.md) for the failure mode). `bra .` is safer.

### 3. Snapshot a stable boot state, then re-launch from it

XRoar supports save/restore via `-trap`, `-trap-snap`, and `-load` ([xroar.1.in:427-460](../../docs/reference/xroar/doc/xroar.1.in)). The pattern:

```bash
# One-time snapshot capture (run once, then reuse):
xroar -machine coco3 -ram 512 \
      -cart ladybug -cart-type rom -cart-rom build/ladybug.rom -cart-autorun \
      -trap 0xC0DC \
      -trap-snap /tmp/ladybug-mainloop.sna \
      -trap-timeout 1
```

After the cart enters `mainloop` ($C0DC), XRoar writes a snapshot and exits. Subsequent debug sessions skip the autorun entirely:

```bash
xroar -machine coco3 -ram 512 \
      -cart ladybug -cart-type rom -cart-rom build/ladybug.rom \
      -load /tmp/ladybug-mainloop.sna \
      -gdb -gdb-ip 127.0.0.1 -gdb-port 65520
```

Note: snapshots are tied to the ROM image. **Rebuild the ROM → re-capture the snapshot.** Worth scripting alongside `scripts/build.sh` when the iteration loop slows down.

## Limits of the current GDB-stub workflow

XRoar's gdb stub exposes the CPU view: registers, memory, breakpoints, single-step. It does **not** expose:

- **GIME internal state.** `MC3`, `MMUEN`, `mmu_bank[]`, `TR`, `S`, `RAS` are not memory-mapped readable. To verify "is `MC3` set right now?" we have to write a sentinel through the `$FExx` constant region and read it back — `$FExx` reads behave differently depending on `MC3`, so the readback discriminates the state indirectly.
- **Cycle-level stepping.** GDB-stub `step` is per-instruction.
- **Video / palette state.** Not addressable through CPU memory.

Concrete inspection of GIME state is the largest current gap; if it becomes a blocker, see [../backlog/mcp-xroar-server.md](../backlog/mcp-xroar-server.md) for the build-our-own-server option.

### Reverse execution / `record full` — not viable on this stack

Probed 2026-05-15. **gdb's `record full` does not work for the m6809 + XRoar stack**, and the failure is in two independent layers — both would have to be addressed to fix it:

- **gdb side.** `record full` refuses to start with `Process record: the current architecture doesn't support record function.` m6809 is not in gdb's list of architectures with a record-mode implementation. This errors before any packet reaches the stub, so XRoar can't fix it.
- **stub side.** `reverse-stepi` and `reverse-continue` return `Target remote does not support this command`. `record btrace` returns `Target does not support branch tracing`. XRoar's stub doesn't speak the reverse-protocol packets (`bs`, `bc`, `bt`) that gdb-managed record would otherwise use.

Forward stepping (`stepi`) works as expected. The limitation is specific to reversal / record.

**Practical consequence:** any time-travel feature in the web/ retro-dev app must be implemented by the backend recording state per step itself — there's no gdb-mediated path. See [../backlog/retro-dev-web-app.md](../backlog/retro-dev-web-app.md) scope decisions for how this constrains design.

## Iteration workflow

`scripts/build.sh run` builds the ROM and launches xroar with the canonical invocation above. To kill: close the xroar window or `Ctrl-C` the script (xroar handles SIGINT).

For headless / CI-style smoke tests (none today), add `-no-ratelimit -fskip 100` and pipe trace output.

## Known XRoar 1.10 limitations

- **`-load <snapshot>` + `-gdb` together fails to bind the gdb listener.** XRoar logs `[gdb] WARNING: bind 127.0.0.1:PORT failed` (drowned among Gtk-CRITICAL UI noise, easy to miss — earlier wiki framing as "silent" was inaccurate). Root cause: `gdb_interface_new` runs twice when `-load` is given — once in initial `coco3_init`, once after `read_snapshot` frees and replaces the machine — and the listening socket lacks `SO_REUSEADDR`, so the kernel's `TIME_WAIT` blocks the second bind. Workaround: launch fresh (without `-load`) and let autorun run, then attach. Or capture a fresh snapshot mid-debug instead of round-tripping through one. Fix is a single-line patch documented in [../backlog/xroar-load-gdb-patch.md](../backlog/xroar-load-gdb-patch.md).
- **`swi` (opcode `$3F`) at a `-trap` point makes XRoar segfault** when it tries to write the snapshot. Use `bra .` halt loops instead. (Also noted in [Reaching specific boot points reliably](#reaching-specific-boot-points-reliably).)
- **`-trap` succeeds at writing the snapshot, but XRoar segfaults right after.** The snapshot file is fully valid and usable for reload. The segfault is post-write.
- **The stub answers `vMustReplyEmpty` with the literal string `"timeout"`.** Modern gdb (14.x) considers this a fatal protocol error when reported via MI (`-target-select remote …`, `-interpreter-exec console "target remote …"`, and `-ex "target remote …"` all surface it as `^error,msg="Remote replied unexpectedly to 'vMustReplyEmpty': timeout"`). The same `target remote …` typed as a plain CLI line into gdb's stdin after gdb is up reduces the error to a non-fatal warning and the attach succeeds — that's the only path that works for an MI-driven session against this stub. Observed building the web/ retro-dev backend.
- **The stub gets wedged by probe-connect+disconnect.** A TCP `connect()` immediately followed by `close()` (e.g. a port-readiness check) appears to drive the stub into the same degraded state that elicits the `"timeout"` reply above. **Do not probe the GDB port** — sleep ~4 s after launching XRoar and connect with gdb directly. Observed: with a probe, every subsequent gdb attach failed; without the probe, attaches are clean.
- **`info registers` always trails with `^error,msg="Register 12 is not available"`.** m6809-gdb knows 13 registers; the stub exposes 12. The accumulated console-stream output for the first 12 (PC, S, U, Y, X, DP, B, A, CC and three padding entries) is valid and complete — the trailing error must be tolerated by any consumer.

## Gotchas

- **Cart ROM must be a power of 2.** XRoar will load any size but mapping behaviour for non-pow2 ROMs is undefined. Build script always pads to 16 KB.
- **`-cart-rom` is documented only as "mapped from `$C000`."** XRoar's handling of 32 KB cart files (whether for Init0 b1-b0 = `11` mode or otherwise) is unverified — observed behaviour in Phase 2.1 testing was consistent with XRoar mapping the *lower* 16 K of a 32 K file to `$C000` and the upper half being inaccessible. If/when we need >16 K cart, plan to use `-cart-type gmc` (Games Master Cartridge — software bank-switching) rather than rely on Init0=11.
- **Default machine config carries state across runs.** If a previous session changed PAR/palette in a weird way and you suspect emulator state pollution, clear `~/.xroar/` (config) — but normally a clean cart load resets the GIME via the boot path.
- **WSL display** — XRoar opens an X11/Wayland window. WSL2 with WSLg (Win11 default) handles this transparently. If no window appears, check `echo $DISPLAY` inside WSL.

## Sources

- Manual: https://www.6809.org.uk/xroar/doc/xroar.shtml
- Local install: `~/coco-tools/xroar` (source), `/usr/local/bin/xroar`
- `xroar --help` for the full flag list.
