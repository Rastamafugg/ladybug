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
- ROM image, `.lst`, and `.map` look correct: `irq_handler = $C0F8`, `JT_IRQ = $FEF7`, the install sequence (`86 7E B7 FE F7 CC C0 F8 FD FE F8`) is at `$C0C0-$C0CA`.
- The build script does **not** pass `-tv-input rgb`; this is unrelated to the corruption.
- A separate, real XRoar bug exists at `$C0D9-$C0DB` / `$C8B4-$C8BE` / `$E000-$E042` (see [lessons-learned.md §"XRoar cartridge-window reads are not uniformly cart-backed"](../implementation/lessons-learned.md)). The current code routes around `$C0D9-$C0DB` via `copy_around_xroar_bad_window` and an `org $C0DC` before `mainloop`. **This is probably not the cause of the IRQ-install regression** — the IRQ code lives at `$C0C0+` and `$C0F8`, outside that window — but worth ruling out.

## 2026-05-14 reframing — XRoar source review (H6 investigation)

The XRoar source (`docs/reference/xroar/`, tag 1.11) was reviewed against this symptom. Findings:

- **No XRoar fix between 1.10 and HEAD/1.11** touches GIME force-$FExx, MMU PAR, or IRQ vector dispatch. The CoCo3-relevant delta is "Update CoCo3 keyboard IRQ state more often" (PIA-only) and a rename of `struct machine_*` (no semantic change). Upgrading to 1.11 will not fix this.
- **XRoar's coco3.c read/write paths for `$FE00-$FEFF` are symmetric for `-cart-type rom`** (which our build uses). [coco3.c:1159](../../docs/reference/xroar/src/coco3.c) (read) and [coco3.c:1231](../../docs/reference/xroar/src/coco3.c) (write) both use the identical guard `(!MMUEN || (MC3 && A>=0xFE00 && A<0xFF00))` → bank 0 in both directions. `cart_rom_read` ([cart.c:948](../../docs/reference/xroar/src/cart.c)) is a no-op for `R2=0` and `cart->EXTMEM=0`, so no cart-side read shadowing. There is **no emulator path that would produce "write $7E, read $16"** under our cart configuration.
- The observation "`$FEF7` reads back `16 02 12 16`" was taken at SIGINT-time, **after wild-PC corruption had occurred**. It is therefore **not evidence that the original `STA $FEF7` failed**. The entire H1–H5 hypothesis tree was built on that unverified premise.

### Reframed question

"Why does the first IRQ go wild despite a correctly-installed vector?" — not "why is `$FEF7` garbage?". `$FEF7` being garbage at SIGINT-time is a *consequence* of the wild PC, not the cause.

### gdb-mcp empirical observations (2026-05-14)

Bypassed `phase24_halt` (two `nop`s preserving downstream addressing), rebuilt, ran under XRoar 1.10 with gdb-mcp attach. Set breakpoint at `$C0CB` — i.e. immediately after `STA $FEF7` / `STD $FEF8` complete, before the unmask.

Observed at the breakpoint:

| Address | Read | Expected | Diff |
|--|--|--|--|
| `$FEF7` | `0x16` | `0x7E` (just stored) | Wrong |
| `$FEF8/$FEF9` | `0x02 0x12` | `0xC0 0xF8` (just stored) | Wrong |
| `$FEF0-$FEFF` | `0F 16 02 0F 16 02 18 16 02 12 16 02 09 16 02 09` | (cart-shadow `$FF` padding or freshly-installed JMP) | Looks like SECB-ROM jump-table contents, NOT what should be there |
| `$FFA0-$FFA7` (exec PAR readback) | `32 33 3D 3E 3F 00 03 17` | par_table `38 30 31 32 33 3D 3E 3F` | Wrong (and PAR reads through XRoar return RAM bleed anyway — see below) |
| `$FFA8-$FFAF` (user PAR readback) | `38 30 31 32 33 3D 35 3F` | (default uninitialised) | Suspiciously close to par_table — suggests par-loop wrote to user set, not executive set |

Repeated with `-ram 1024` (to rule out the DAT-board `dat.enabled` gating, which only applies to >512K configs in [`coco3.c:434`](../../docs/reference/xroar/src/coco3.c)). **Identical readbacks.** The DAT-board path is not the gate.

### Corrected architecture model

Initial source-review misled me: the *real* GIME MMU is fully implemented in [`tcc1014/tcc1014.c`](../../docs/reference/xroar/src/tcc1014/tcc1014.c), independent of the `dat` struct in `coco3.c`. The `dat` struct is only the optional DAT-board memory extension (Disto-style overlay for >512K). At [`tcc1014.c:726-727`](../../docs/reference/xroar/src/tcc1014/tcc1014.c), the address decoder for `A < $FF00` is:

```c
if (A >= 0xfe00 && gime->MC3) use_mmu = 0;
unsigned bank = use_mmu ? gime->mmu_bank[gime->TR | (A >> 13)] : (0x38 | (A >> 13));
```

So for `A=$FEF7` with `MC3=1`, `bank = $3F` regardless of MMU/PAR. Reads and writes use this same decoder → symmetric. There is **no plausible XRoar code path** that produces "write `$7E`, read `$16`" symmetrically — unless the store itself never executed (CPU faulted / didn't run the instruction), the GIME's MC3 wasn't actually set when the store ran, or something overwrote `$FEF7` after our store but before the breakpoint hit at `$C0CB` (only 6 cycles away).

Also note: **`$FFA0-$FFAF` readbacks are NOT diagnostic of live PAR state.** In `tcc1014.c:782-787`, PAR reads return the low 6 bits of `mmu_bank[A&15]`, but in `coco3.c:1146-1148` and `1155-1166`, the `dat` overlay only writes the top 2 bits and the trailing RAM read overwrites D entirely. The bytes we see at `$FFA0+` are RAM-bleed, not PAR contents.

### New leads (replacing H1–H5 as the primary focus)

- **L1.** Does XRoar provide a SECB-equivalent ROM at boot? Our [`scripts/build.sh`](../../scripts/build.sh) launches with `-cart-type rom -cart-rom "$ROM" -cart-autorun` and **no `-bas` flag**. XRoar defaults `extbas_rom = "@coco3"` ([`coco3.c:254-255`](../../docs/reference/xroar/src/coco3.c)) and the SECB ROM loads into `ROM0` if present. Largely ruled out, but worth confirming the actual `ROM0` contents via gdb-mcp once a stable session is achievable.
- **L2.** PIA1 vsync IRQ may fire concurrently with (or instead of) the Vbord IRQ. The boot acks PIA1_DB once at line 90, ~tens of ms before the unmask at line 233 — a new vsync edge can arrive in between.
- **L3.** Cart-shadow self-copy at lines 102-118 may not populate `$FE00-$FEFF` correctly. The copy reads via `ldd ,x` (cart CTS) and writes via `std ,x` (GIME RAS → RAM). The observed `$FEF0-$FEFF = 0F 16 02 ...` is suspicious — those aren't `JMP` opcodes and don't match `$FF` cart padding. They could be SECB ROM bleed or RAM that wasn't written by the copy at all. Worth single-stepping the copy loop to confirm what gets written.
- **L4.** The MC3 bit in the GIME may not be persistently set when `STA $FEF7` executes — even though our `Init0 = %01101000` write should set it. If the GIME's internal state has MC3=0 at the moment of the store, the bank computation falls into the MMU-translated branch with bank = `mmu_bank[7]`. If our PAR-loop writes raced or used the wrong task register, that PAR could be wrong, and the store lands in a bank we never read back from.

### Recommended next steps (when gdb-mcp can be made stable)

1. **Set a breakpoint at `$C0C2` (the STA $FEF7 itself), single-step over it, then read `$FEF7` immediately.** Distinguishes "store never landed" from "store landed but something overwrote it before the breakpoint at `$C0CB`".
2. **Trace MC3 state across the boot.** Add a `monitor` probe (or `info reg` for any debug registers XRoar exposes) before and after each `STA $FF90`. Verify MC3 is actually `1` at the moment of `STA $FEF7`.
3. **Probe the cart-shadow copy.** Set a breakpoint at the end of `copy_done` (line 120), read `$FEF0-$FEFF`. If it's `$FF` padding, the copy worked and something else corrupted it later. If it's `0F 16 02 ...` already, the copy is the culprit.
4. **Try a sentinel test that bypasses the cart shadow:** insert a `LDA #$55 / STA $FEF7 / LDA $FEF7 / CMPA #$55 / BNE fail` immediately after the second `STA GIME_INIT0` (line 172). If sentinel readback fails *at that point*, the problem isn't the IRQ install at all — it's that `$FEF7` writes don't stick from the very first attempt under our boot state.

The gdb-mcp session is not currently stable across multiple breakpoint-set + continue cycles. Two timeout-induced session kills occurred in this run. This may be related to the cart-autorun handshake firing on a 100ms cart-FIRQ edge schedule ([`cart.c:968-974`](../../docs/reference/xroar/src/cart.c)) — long enough that `continue` blocks past gdb-mcp's default timeout. A more reliable workflow may need a longer per-command timeout or a different attach point.

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
