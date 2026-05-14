---
name: Troubleshoot cartridge RAM corruption after IRQ install
description: After removing the Phase 2.4 isolation halt, the boot path through IRQ install + Vbord enable derails the CPU. Wild PC overwrites the cart's RAM image.
type: backlog
tags: [debugging, irq, gime, boot]
updated: 2026-05-14
---

# Troubleshoot cartridge RAM corruption after IRQ install

## Symptoms

Filed 2026-05-14 during the Phase 2.4 "three tile" build-out.

When the Phase 2.4 isolation halt (`post_blit: bra post_blit`) is removed so execution flows into the carried-forward Phase 2.3 IRQ-install + Vbord-enable code, the CPU goes off the rails within milliseconds of `mainloop`. Observed via the `gdb-mcp` bridge attached to XRoar 1.10:

- `$FEF7` (JT_IRQ slot, where `lda #$7E / sta $FEF7 / std $FEF8` was supposed to install a JMP to `irq_handler`) reads back `16 02 12 16` — not the `7E xx xx` we wrote.
- First Vbord IRQ vectors via `$FFF8 = FE F7` to `$FEF7`, executes the garbage there, PC lands in cleared FB RAM (e.g. `$A7EF`) executing `STU $0000` patterns (the `FF 00 00` of uninitialized RAM).
- The wild PC writes to `$C000+` and `$2000+`, corrupting both the cart RAM image and the framebuffer. By the time a debugger attaches, `$C002` reads `$00` and the FB is full of garbage.

## What's already known

- The Phase 2.4 isolation halt was added *before* the IRQ install code, so every build since Phase 2.4 started has skipped that code path entirely. The Phase 2.3 "IRQ ticks worked" verification is from a different layout — it may not have been re-verified after the Phase 2.3-close MMU/PAR rearrangement.
- The current `phase24_halt` in [`src/main.s`](../../src/main.s) is a workaround that re-disables the post-blit path. Removing it reproduces the bug.
- ROM image, `.lst`, and `.map` look correct: `irq_handler = $C0F8`, `JT_IRQ = $FEF7`, the install sequence (`B6 7E B7 FE F7 CC C0 F8 FD FE F8`) is at `$C0C0-$C0CA`.
- The build script does **not** pass `-tv-input rgb`; this is unrelated to the corruption.
- A separate, real XRoar bug exists at `$C0D9-$C0DB` / `$C8B4-$C8BE` / `$E000-$E042` (see [lessons-learned.md §"XRoar cartridge-window reads are not uniformly cart-backed"](../implementation/lessons-learned.md)). The current code routes around `$C0D9-$C0DB` via `copy_around_xroar_bad_window` and an `org $C0DC` before `mainloop`. **This is probably not the cause of the IRQ-install regression** — the IRQ code lives at `$C0C0+` and `$C0F8`, outside that window — but worth ruling out.

## Hypotheses to test

1. **`force-$FExx` write semantics under XRoar 1.10.** With Init0 bit 3 set (force-$FExx = 1), writes to `$FE00-$FEFF` may not land where reads come from. The Phase 1 lessons-learned says this worked once, but that was before the Phase 2.3 MMU rearrangement. Test: store a sentinel to `$FEF7`, read it back BEFORE enabling Vbord, see if writes are reflected.
2. **PAR set selection.** `clr $FF91` selects the executive PAR set, but at SIGINT-time we observed `$FFA0-$FFA7 = 32 33 3D 3E 3F 03 17 17` (only the last 5 of our 8-entry par_table, plus garbage). Either the PAR write loop is being interrupted, or the PAR readback is reflecting a different task than we wrote to. Test: read `$FF91` and both PAR sets immediately before unmasking IRQ.
3. **Stale FIRQ from the cart line.** The boot acks `PIA2_DA/DB` to clear the CART-line FIRQ flag, but if the GIME's force-$FExx routing remaps the FIRQ vector at `$FFF6/$FFF7` to a location we didn't write, the very first unmask might fire a stray FIRQ — not just the Vbord IRQ we expect.
4. **Stack alignment / overflow.** The new `blit_tile` uses `pshs u` / `leas 2,s`. Stack usage is bounded (4 bytes max), but worth confirming SP at entry to `mainloop` is still `$1FFE` and the IRQ-handler doesn't blow past low RAM allocations.
5. **`-tv-input rgb` regression test.** Run the same build under `-tv-input rgb` to rule out an interaction with the monitor mode. (Unlikely but cheap.)

## How to reproduce

```
# In src/main.s, remove or bypass the phase24_halt block:
#   phase24_halt
#           bra     phase24_halt
# Then:
./scripts/build.sh build
# Launch xroar with -gdb -gdb-port 65520, attach via gdb-mcp,
# observe PC wandering outside cart space within ~1 frame of unmask.
```

## Done when

- Root cause identified and documented in [lessons-learned.md](../implementation/lessons-learned.md).
- IRQ install + Vbord enable path runs cleanly: `$FEF7` reads back `7E C0 F8`, `irq_handler` fires at 60 Hz, `FRAMES` counter ticks.
- `phase24_halt` workaround removed from `src/main.s`. The Phase 2.4 isolation build still renders three tiles AND has the IRQ counter ticking, matching the original Phase 2.4 visible-state description.

## Starting prompt for the spin-off session

> Read [wiki/backlog/cart-ram-corruption.md](wiki/backlog/cart-ram-corruption.md). Reproduce the symptom by removing `phase24_halt` from `src/main.s`, then work the hypotheses in order. Use the `gdb-mcp` bridge to inspect `$FEF7`, `$FF91`, `$FFA0-$FFAF`, and `SP` at carefully-placed breakpoints before and after the IRQ install. The fix likely lives in the boot ordering between MMU/PAR enable and `$FE00-$FEFF` writes.

## Sources

- [`src/main.s`](../../src/main.s) — phase24_halt, IRQ install, par_table
- [implementation/lessons-learned.md](../implementation/lessons-learned.md) — Phase 1 IRQ-tick verification, Phase 2.3 boot-path verification, XRoar cart-window read bug
- [platform/gime.md](../platform/gime.md) — Init0 bit semantics, force-$FExx, MMU PAR sets
- [tooling/xroar.md §GDB-MCP round trip](../tooling/xroar.md) — attach workflow
