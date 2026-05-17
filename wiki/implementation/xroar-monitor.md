---
name: XRoar monitor protocol — Phase 1 requirements
description: Requirements for a custom JSON-RPC "monitor" server inside XRoar that the Ladybug web backend brokers to MCP-speaking clients.
type: plan
tags: [tooling, xroar, monitor, mcp, debug]
updated: 2026-05-16
---

# XRoar `-monitor` port — Phase 1 requirements

Purpose-built debug control plane added to XRoar source, replacing the gdb stub for our tooling. Enables the Ladybug emulator-monitor-tester initiative ([emulator-monitor-tester.md](emulator-monitor-tester.md)) by eliminating the four documented gdb-stub limitations from the 2026-05-16 lessons-learned entries.

Supersedes the deferred design sketch in [backlog/mcp-xroar-server.md](../backlog/mcp-xroar-server.md).

## Architecture

```
 Claude Code / agent ──MCP (real spec)──▶ Ladybug web backend (web/backend/instance.py)
                                            │
                                            ├──monitor JSON-RPC──▶ XRoar instance A
                                            ├──monitor JSON-RPC──▶ XRoar instance B
                                            └──monitor JSON-RPC──▶ XRoar instance C
```

The XRoar side speaks a project-private JSON-RPC "monitor protocol". The web backend owns the session registry and brokers commands; it is the component that speaks real-spec MCP outward. XRoar is not MCP-aware. The name `-monitor` (not `-mcp`) reflects this in the flag.

## Activation

- Flag: `-monitor [host:]port` — enable monitor server. Default endpoint `127.0.0.1:17654`. Loopback-only by default; binding to non-loopback requires explicit `host` in the flag value.
- Flag: `-monitor-halt-on-start` — pause CPU before first instruction until a client connects and issues `run`. Default: do not halt.
- Default off. No code in XRoar's existing default paths reaches the monitor module unless `-monitor` is present.

## Transport & framing

- TCP listener, line-delimited JSON-RPC 2.0 (one JSON object per `\n`).
- JSON-RPC chosen for: request IDs (interleave async event notifications with replies on one socket), trivial C parser, hand-debuggable, parallels gdb-stub TCP style.
- No auth in v1; loopback is the trust boundary.

## Concurrency with `-gdb`

Both stubs may be enabled simultaneously. Combination is allowed but **unsupported** — each stub maintains its own breakpoint table; cross-stub interactions are undefined. If problems surface, mutual exclusion will be added as a follow-up.

## Address-space model

The CoCo 3 has no MMU in the modern sense. It has the GIME's MMU task register + 8 PARs that map eight 8 KB CPU slots ($0000, $2000, …, $E000) to 8-bit physical-page numbers (up to 512 KB physical). Memory commands therefore take a `space` parameter:

- `"cpu"` (default) — `addr ∈ $0000–$FFFF` resolved through the currently-active PAR set. Matches gdb behavior; matches what executing code sees.
- `"physical"` — `phys_addr ∈ $00000–$7FFFF` (19-bit), bypassing PARs. Required to inspect pages not currently mapped, and to write RAM-under-ROM regions where XRoar's bus decode drops CPU-space writes (see [lessons-learned §XRoar cart-window write decode](lessons-learned.md)).

"Tracking memory allocation" is a client-side derivation from `read_gime_state()` (PARs + active task) plus physical reads — no separate API.

## Run-state contract for state-mutating commands

- **State reads** (`read_memory`, `read_registers`, `read_gime_state`, etc.) — permitted while CPU is running. The monitor snapshots from the emu thread; XRoar is single-threaded relative to monitor commands.
- **State writes** (`write_memory`, `write_registers`, `set_breakpoint` mutations of code memory, etc.) — require CPU `halted`. If CPU is running, return JSON-RPC error `target_running`. Client must `pause`, write, `run`. This eliminates "did my write land before or after the IRQ?" ambiguity surfaced by the WS-A probes.

## Write semantics by address space

- **CPU-space write to a ROM-backed address** (where XRoar's bus decode would route the write to `cart_rom_write` or a read-only bank): return JSON-RPC error `read_only_region`. The monitor pre-checks the bus state (S/RAS signals) before issuing the write.
- **Physical-space write**: always writes the byte directly into XRoar's RAM array at the 19-bit physical address. Bypasses bus decode. This is the right primitive: it lets the monitor honor what real CoCo 3 silicon does (writes always reach DRAM regardless of TY) even where XRoar's bus model diverges. See [lessons-learned §XRoar cart-window write decode](lessons-learned.md) for the root-cause analysis.

## Capabilities

### MUST (v1)

| Method | Notes |
|-|-|
| `read_memory(addr, len, space="cpu")` | Cap at 64 KB per request. |
| `write_memory(addr, bytes, space="cpu")` | Halted-only. Semantics per "Write semantics" above. |
| `read_registers()` | 6809: A, B, D, X, Y, U, S, PC, DP, CC. |
| `write_registers({...})` | Halted-only. |
| `read_gime_state()` | Returns shadow-backed values of `$FF90`, `$FF98–$FF9E`, MMU task, PARs (raw 8-bit), palette (raw 6-bit, no `$C0` OR). Fixes sentinel + palette quirks. |
| `step_instruction(n=1)` | Halted-only. Returns new PC + cycle count. |
| `run()` / `pause()` | `pause` must work mid-run (gdb `-exec-interrupt` does not). |
| `set_breakpoint(addr, kind="exec")` | Must work when current PC == addr (gdb loops; we won't). Returns id. |
| `clear_breakpoint(id)` / `list_breakpoints()` | |
| `wait_for_stop(timeout_ms)` | Long-poll; returns `{reason, pc, ...}`. |
| `get_run_state()` | `running` / `halted` + last stop reason. |
| `reset(kind="soft"\|"hard")` | Mirrors XRoar reset; emits `reset` event; clears breakpoints. |
| `attach()` / `detach()` | Reattach must work repeatedly within a single XRoar process lifetime. |

### SHOULD (v1 if cheap, else v1.1)

| Method | Notes |
|-|-|
| `set_watchpoint(addr, len, kind="r"\|"w"\|"rw")` | Real watchpoints, not BP-at-instruction tricks. |
| `screen_capture(format="raw"\|"png")` | Framebuffer snapshot for golden-image regression. |
| `inject_key(coco_key, kind="down"\|"up"\|"tap", hold_ms?)` | Headless UI driving; replaces test-only keyboard hooks. |
| `snapshot_save(path)` / `snapshot_load(path)` | XRoar's existing snapshot format. |
| `events.subscribe(kinds=[...])` | Async push channel — events: `vbord`, `hsync`, `bp`, `reset`, `state_loaded`, `machine_changed`. |

### NICE (defer)

- `read_disasm(addr, n)` (client can disassemble from memory)
- `read_cycle_counter()`
- Memory-map introspection helper
- Tape/disk image swap

## Lifecycle

| Event | Behavior |
|-|-|
| XRoar start with `-monitor` | Open listener; CPU runs (unless `-monitor-halt-on-start`). |
| Client connects | Send hello: XRoar version, monitor protocol version, machine name. |
| Hard reset | Stub stays up; emit `reset` event; clear breakpoints/watchpoints (tied to running program). |
| Snapshot load | Same as reset: clear BPs, emit `state_loaded`. Run-state inherits from snapshot. |
| Machine switch | Emit `machine_changed`; clients re-discover. |
| Last client disconnects while halted | **CPU stays halted; await reconnection.** The web backend is the persistent session registry; it tracks all running XRoar processes and removes them on confirmed process exit. |
| XRoar shutdown | Send `goodbye`, close listener. |

## Failure modes

- Malformed JSON → JSON-RPC `-32700`; do not drop connection.
- Unknown method → `-32601`.
- Invalid params (bad addr, negative length, oversize read, missing required field) → `-32602` with human-readable `data`.
- Memory reads capped at 64 KB; over-cap → `-32602`.
- Per-connection command serialization; multi-client commands serialize globally on the emu thread.
- BP fires mid-command → command completes, `stopped` event delivered after.
- Client disconnects mid-command → finish command on the emu side, discard reply.
- Write to ROM-backed CPU address → `read_only_region` (see Write semantics).

## Explicitly out of scope (v1)

- Replay / time-travel / reverse-stepping
- Audio buffer capture
- Analog joystick value injection
- Authentication / TLS (loopback trust boundary)
- Real Anthropic MCP-spec compliance inside XRoar (the web backend handles that)
- Persistent BP conditions / scripting
- Hot-reload of the monitor stub

## Open follow-ups (not blockers for Phase 2)

- MAME comparison test of the cart-ROM-to-RAM copy — see [backlog/mame-cart-ram-comparison.md](../backlog/mame-cart-ram-comparison.md). Confirms whether the RAM-under-ROM write-through is faithfully modeled in a second emulator (expected: yes, MAME's CoCo 3 driver is the most thorough open-source model).
- Real-hardware verification of the RAM-under-ROM write contract — deferred to Phase 10 hardware bring-up.

## Phase 2 implementation plan

Approved 2026-05-16. Implementation deferred to Phase 3 milestones, each in its own conversation.

### XRoar repo bring-up

- `docs/reference/xroar/` is a real git checkout of `https://www.6809.org.uk/git/xroar.git`. Current HEAD `1e5e9552` = 4 commits past upstream tag `1.11`. Build system: autotools.
- Bring-up: verify clean tree, `git fetch origin`, pin at `1e5e9552` (or newer release tag if one exists), run baseline `./autogen.sh && ./configure && make`, capture binary at `build/xroar-baseline` for A/B reference. Upstream-sync beyond bring-up is out of scope.

### Branching

- Feature branch `ladybug/monitor` in the XRoar working tree (nested repo; not a submodule). Tag baseline as `ladybug-monitor-base`.
- Local-only branch initially; no GitHub fork until/unless we want to share or upstream.

### Module placement

New files under `docs/reference/xroar/src/`:
- `monitor.c` (est. 1200-1500 LOC) + `monitor.h` — paralleling `gdb.c` (1090 LOC) / `gdb.h`. Threaded BSD-socket listener, JSON-RPC dispatch, command handlers.
- `cJSON.c` / `cJSON.h` — vendored ([cJSON](https://github.com/DaveGamble/cJSON), MIT, single-file). Chosen over jsmn for full object model when building responses.

Threading: mirror `gdb.c`. One blocking-accept thread (`pthread_create`); commands synchronized to the emu thread via `pthread_mutex` + `pthread_cond`. Stays UI-backend-agnostic.

Machine scope: wire into `coco3.c` only (the existing `gdb_interface_new` site at line 675 / free at 696). Other machines (Dragon, CoCo 1/2, MC-10) explicitly not covered — Ladybug is CoCo 3-only.

### File change list (non-invasive principle)

Every change to existing files is gated behind `if MONITOR` (autoconf) plus a runtime `xroar.cfg.debug.monitor != NULL` check. No code path executes when `-monitor` is absent.

| File | Change |
|-|-|
| `src/monitor.c`, `src/monitor.h` | NEW |
| `src/cJSON.c`, `src/cJSON.h` | NEW (vendored, license header preserved) |
| `src/Makefile.am` | Add `if MONITOR` block (~6 lines) near the existing `if GDB` block at lines 562-565 |
| `configure.ac` | `AC_ARG_ENABLE([monitor], …)` + `AM_CONDITIONAL([MONITOR], …)`, ~10 lines |
| `src/xroar.h` | Add `cfg.debug.monitor`, `monitor_port`, `monitor_halt_on_start` fields (~3 lines) |
| `src/xroar.c` | `#include "monitor.h"` (~line 62); three `XC_SET_*` entries in option table (~line 3333); three help-text lines (~3534); three config-print lines (~3737). ~12 lines total |
| `src/coco3.c` | Two lines: `monitor_interface_new(...)` near line 675; `monitor_interface_free(...)` near line 696 |

**Total existing-file delta: ~35 lines across 5 files.** Everything else is additive.

### Build / install workflow

Development on WSL Ubuntu (per [tooling/build-workflow.md](../tooling/build-workflow.md)).

- Per-iteration: `make -j` from `docs/reference/xroar/`. `./autogen.sh && ./configure --enable-monitor` only when `configure.ac` / `Makefile.am` change.
- **Side-by-side install:** patched binary installs as `xroar-monitor` (not replacing the system `/usr/local/bin/xroar`). Ladybug's [scripts/build.sh](../../scripts/build.sh) and [web/backend/instance.py](../../web/backend/instance.py) get an `XROAR_BIN` env-var override so integration tests target the patched binary explicitly. System binary stays as the baseline reference until Phase 3 M2+ smoke-tests pass.

### Address-space representation (locked)

**Flat 19-bit physical address** — `phys_addr ∈ $00000–$7FFFF`. Monitor splits internally: `bank = addr >> 13`, `offset = addr & 0x1FFF`, dispatching through XRoar's `ram->d[bank]` array. Matches CoCo 3 documentation conventions; cleaner client API than exposing the `{bank, offset}` tuple.

### Phase 3 milestones

Each is its own conversation, closing in `qa-reviewer`. Test clients land at `web/scripts/probe_monitor_M*.py`, paralleling [probe_tester_m2.py](../../web/scripts/probe_tester_m2.py).

| M | Scope | Test |
|-|-|-|
| **M1** | Listener boots; hello handshake; `get_run_state` / `run` / `pause`. No memory access yet. | `probe_monitor_m1.py` — connect, read hello, assert `halted`, `run`, assert `running`, `pause`, disconnect. |
| **M2** | `read_memory` / `write_memory` (CPU space); `read_registers` / `write_registers`. Halted-only enforcement. | `probe_monitor_m2.py` — round-trip RAM in `$FE00-$FEFF`; verify `target_running` error on write-while-running. |
| **M3** | `read_gime_state` shadow-backed (no `$1B` sentinel, no `$C0` palette OR). Physical-space memory R/W. | `probe_monitor_m3.py` — write `$5A` to phys page `$3E` via `space="physical"`, flip `TY=1`, CPU-read `$C000`, assert `$5A`. Closes the cart-shadow no-op loop. |
| **M4** | Breakpoints (incl. at-current-PC); `step_instruction`; `wait_for_stop`. | `probe_monitor_m4.py` — BP at known cart entry, step past, run, expect `stopped`. |
| **M5** | `reset`, `attach`/`detach` (multi-reconnect), client-disconnect-leaves-halted. | `probe_monitor_m5.py` — connect/halt/disconnect/reconnect cycle; reset clears BPs. |
| **M6** (SHOULD) | `screen_capture`, `inject_key`, snapshot save/load, `events.subscribe`. | One probe per capability. |

Web-backend ([instance.py](../../web/backend/instance.py)) integration of the monitor is a follow-up after M5/M6, not part of Phase 3.

## Sources

- [lessons-learned.md](lessons-learned.md) — gdb-stub limitations (2026-05-16); XRoar cart-window write decode finding.
- [backlog/mcp-xroar-server.md](../backlog/mcp-xroar-server.md) — superseded design sketch.
- [emulator-monitor-tester.md](emulator-monitor-tester.md) — downstream consumer of the monitor.
- XRoar source under [`docs/reference/xroar/src/`](../../docs/reference/xroar/src/) — `tcc1014/tcc1014.c`, `coco3.c`, `cart.c`, `rombank.h`, existing `gdb.c` for reference shape.
