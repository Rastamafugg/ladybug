---
name: Build a purpose-built mcp-xroar server for emulator state introspection
description: Cost/benefit of replacing gdb-mcp + m6809-gdb + XRoar GDB stub with a direct XRoar control plane.
type: backlog
tags: [tooling, xroar, mcp, deferred]
updated: 2026-05-14
---

# Build a purpose-built `mcp-xroar` server

## Why this might be worth doing

The current debug stack — `gdb-mcp` driving `m6809-gdb` connected to XRoar's built-in GDB remote stub — gives us CPU-visible memory, register reads, breakpoints, and instruction stepping. That's sufficient for ~80% of bring-up debugging.

The remaining 20% is genuinely hard to reach via the GDB protocol:

- **GIME internal state.** `MC3`, `MMUEN`, `mmu_bank[0..15]`, `TR` (task register), the current `S` and `RAS` decode signals, IRQ-source masks. None of these are exposed as memory-mapped reads on real hardware *or* through XRoar's gdb stub. We can only infer them via store/load sentinel probes — indirect and slow.
- **Cycle-accurate stepping.** GDB stub steps per-instruction. We can't single-cycle through a memory bus transaction to see what the GIME does on each clock edge.
- **Deterministic re-runs.** Without snapshots, every gdb session re-runs the full BASIC boot + cart-autorun handshake (multiple wall-clock seconds). Iteration cost compounds.
- **Framebuffer / video state dumps.** GIME palette, scanline counters, current VOFF, sub-pixel position. Useful for visual-regression diffing.

The [cart-RAM-corruption investigation](cart-ram-corruption.md) hit exactly this wall: the discriminating question "is `MC3` actually set when `STA $FEF7` executes?" cannot be answered directly through the gdb stub. We have to write a sentinel, read it back, and infer.

## Why we're not doing it yet

XRoar is a substantial C codebase. A purpose-built MCP server would either:

1. **Fork XRoar** and add a JSON-RPC / stdio control plane that exposes internal state. Pro: full access. Con: divergent fork, must rebase on upstream releases.
2. **Patch XRoar with a small instrumentation socket** (a few hundred lines added to `main_unix.c` and `tcc1014.c`) gated behind a build flag. Pro: minimal diff, can upstream. Con: still a C build to maintain.
3. **LD_PRELOAD-style shim** that hooks specific symbols. Pro: no XRoar fork. Con: fragile against XRoar internals changing.

All three are a multi-day project. Before paying that cost, the [current-stack improvements](#current-stack-improvements-that-defer-this-work) below should be exhausted.

## Current-stack improvements that defer this work

These are the cheap wins that make the gdb-mcp path bearable for most investigations:

1. **Use XRoar's `-trap <addr> -trap-snap <file>` flags** to save a snapshot at a known boot point ([xroar.1.in:427-441](../../docs/reference/xroar/doc/xroar.1.in)), then re-launch with `-load <file>` to skip the cart-autorun handshake entirely. Recovers seconds per iteration cycle.
2. **Insert temporary `SWI` opcodes** in `src/main.s` at inspection points. The GDB stub reports `SWI` as a stop event, eliminating the race between "set breakpoint" and "address mapped into cart RAM".
3. **Pass explicit `timeout: 60` or higher** on `mcp__gdb-mcp__continue_exec` / `mcp__gdb-mcp__exec_command` calls that wait for autorun. The default 30 s gets killed by the autorun's 100 ms cart-FIRQ schedule × BASIC keyboard polling latency.
4. **Sentinel probes for GIME state.** Write a known byte to `$FExx` (constant region under MC3), read it back, infer MC3 state from the result. Document the probe patterns once and reuse.

These are captured in the updated [tooling/xroar.md](../tooling/xroar.md) workflow.

## Concrete trigger for revisiting this

Build the MCP server when **all three** are true:

- An investigation requires direct GIME / MMU / cycle-level inspection that sentinel probes cannot answer.
- That investigation has blocked progress for >1 day.
- The investigation is on the critical path of a milestone, not a side question.

Until then, the cost of building, maintaining, and rebasing a custom XRoar fork is not justified.

## Sources

- [docs/reference/xroar/doc/xroar.1.in](../../docs/reference/xroar/doc/xroar.1.in) — `-trap`, `-trap-snap`, `-trap-timeout`, `-load` flags
- [docs/reference/xroar/doc/xroar.texi §Snapshots](../../docs/reference/xroar/doc/xroar.texi) — snapshot format and persistence rules
- [backlog/cart-ram-corruption.md](cart-ram-corruption.md) — the investigation that exposed the limitation
- [tooling/xroar.md](../tooling/xroar.md) — current debug workflow
