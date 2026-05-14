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

### 2026-05-14 — second gdb-mcp pass, much bigger finding

Used the new SWI-trap + snapshot workflow (per [tooling/xroar.md](../tooling/xroar.md)). First found that `swi` opcodes in the cart cause XRoar 1.10 to **segfault** when it tries to snapshot at the trap point — switched to a `bra .` halt loop pattern instead.

Inserted a probe block (`lda #$7E / sta $FEF7 / lda $FEF7 / sta $1000 / ldb $FEF7 / stb $1001 / probe_halt: bra probe_halt`) immediately before `phase24_halt`. Built, launched, attached gdb-mcp. State at attach:

- PC = `$B977` — wild PC in SECB ROM territory. Disassembly there shows `00 00 00 00 FF FF FF FF` decoded as garbage opcodes. **The CPU is wandering uninitialized memory.**
- A=$68, B=$1E — these match our `Init0 = %01101000` and `VRES = $1E` writes, but could equally be coincidence from wild-PC executing BASIC ROM. Cannot trust them as evidence our boot reached those lines.
- `$1000` reads `0x00 0x00` — our probe's persistent sentinel stores **never executed**. Boot did not reach `$C0C6 / $C0CC`.
- `$FEF7` still reads `0x16` (consistent with prior pass).
- **`$C0CF` should contain `20 FE` (`bra probe_halt`); instead reads `00 FF`.** Our probe code is not in RAM at the expected address.
- Reading the whole cart-shadow region: `$C000-$C0FF` is filled with a repeating `00 00 00 00 FF FF FF FF` pattern that does NOT match our cart ROM file.

### The deeper finding: the cart-shadow self-copy doesn't populate RAM

The `00 00 00 00 FF FF FF FF` pattern is XRoar's default DRAM-init fill (see [`ram.c:296-302`](../../docs/reference/xroar/src/ram.c) — `val` flips every 4 bytes per the `loc & tst` test, exactly producing this pattern). So **the RAM at the cart-shadow addresses was never written by the boot — it still holds the emulator's initial DRAM pattern.**

Why? Tracing XRoar's source for our cart-shadow loop ([`src/main.s:102-118`](../../src/main.s)):

1. **Pre-SAM_ALLRAM, with our `Init0 = %10101000` (MMUEN=0, MC3=1):** for A in `$C000-$DFFF`, [`tcc1014.c:716-737`](../../docs/reference/xroar/src/tcc1014/tcc1014.c) computes `bank = 0x38 | (A>>13) = $3E`. The condition `!TY && bank >= 0x3c` is TRUE → ROM mode, S=1 (CTS). **RAS is NOT set** in this branch.
2. In [`coco3.c:1170+`](../../docs/reference/xroar/src/coco3.c) `write_byte`: the `if (RAS)` block at line 1227 is skipped. The cart's write callback IS called with `R2=1`, but [`cart.c:955-959`](../../docs/reference/xroar/src/cart.c) `cart_rom_write` only calls `rombank_d8`, which per [`rombank.h:102-107`](../../docs/reference/xroar/src/rombank.h) is **read-only** (`*d = *p`, never writes `*p`).
3. **Net effect:** the `std ,x` writes inside the cart-shadow loop go to **nowhere observable**. Cart ROM is read-only (correct), and RAM doesn't get written because RAS=0 in the ROM-mode branch.

So our boot-time "cart-to-shadow-RAM self-copy" is fundamentally non-functional under XRoar 1.10's GIME emulation. RAM at `$C000-$FEFF` stays at DRAM init pattern through the entire boot.

### How does the 3-tile render appear to work, then?

Open question. The previous Phase 2.4 build (with `phase24_halt` in place) successfully renders three tiles. That requires post-SAM_ALLRAM code execution: palette load, FB clear, three `blit_tile` calls, `VRES` un-blank. Yet:

- Pre-SAM_ALLRAM: cart-shadow doesn't populate RAM. CPU executes from cart ROM via the CTS path (RAS=0, S=1 → cart_rom_read returns ROM byte).
- Post-SAM_ALLRAM: TY=1 flips the `!TY && bank>=$3C` check → falls through to `else → RAS=1` → RAM access. RAM contains DRAM init pattern.

The CPU should crash the instant it tries to fetch the next instruction after `sta SAM_ALLRAM`. Yet rendering works. **Three possible explanations**, none yet verified:

1. **XRoar's `read_byte` (the gdb path) returns different bytes than the CPU instruction-fetch path** — despite source review showing they share `tcc1014_mem_cycle` → `coco3.c read_byte`. Worth a hard verification with a test that does NOT depend on the gdb stub.
2. **SAM_ALLRAM doesn't fully take effect** under some condition — e.g. the cart's autorun-FIRQ holds some signal that overrides TY for cart-window reads. The cart's `firq_event` ([cart.c:968-974](../../docs/reference/xroar/src/cart.c)) toggles every 100ms — could be related.
3. **The reads in `coco3.c read_byte` execute case-1 (CTS) BEFORE the `if (RAS)` block**, and the RAS block's `ram_d8` call **silently no-ops** for some reason (NULL pointer at line 130). If so, the cart-ROM byte from case-1 persists in `D`. But the gdb-mcp readback shows RAM-init pattern, not cart bytes — so this can't be the full story for our specific addresses.

### Implications

The Phase 2.4 IRQ bug is a SYMPTOM of a much bigger architectural mismatch between our boot model (cart-shadow self-copy → all-RAM execution) and XRoar 1.10's GIME emulation behavior. We should NOT spend more effort on the IRQ vector specifically until we understand:

- Are we **actually executing from cart ROM throughout** (with SAM_ALLRAM effectively a no-op for cart-window reads)? If so, our boot architecture is fine in practice but our mental model is wrong.
- Or is some other mechanism populating RAM that I haven't found? (Possible: snapshot loading does it; cart FIRQ side-effects; some XRoar autorun shortcut.)

### 2026-05-14 — third gdb-mcp pass: probe at copy_done, before SAM_ALLRAM

Inserted `bra .` halt at `copy_done` (i.e. immediately after cart-shadow loop, before `clr $FF91`, par-loop, or `sta SAM_ALLRAM`). Built, ran, attached gdb-mcp — landed cleanly at PC=$C047 (probe address). State at attach: still **pre-SAM_ALLRAM, TY=0, MMUEN=0, MC3=1** (from first `Init0=$A8` write).

**Discriminating reads:**

| Addr range | gdb-mcp read | Cart ROM file bytes | Match? |
|--|--|--|--|
| `$C000-$C00F` | `44 4B 1A 50 10 CE 1F FE 86 02 1F 8B 4F B7 FF 01` | `44 4B 1A 50 10 CE 1F FE 86 02 1F 8B 4F B7 FF 01` | ✅ |
| `$C014-$C01F` | `FF 21 B7 FF 23 B6 FF 00 ...` | `FF 21 B7 FF 23 B6 FF 00 ...` | ✅ |
| `$C040-$C04F` | `84 A7 84 30 04 20 F1 20 FE ...` | `84 A7 84 30 04 20 F1 20 FE ...` | ✅ (the `20 FE` at $C047 is our probe bra) |
| `$C050-$C05F` | `10 8E FF A0 C6 08 A6 80 A7 A0 5A 26 F9 B7 FF DF` | `10 8E FF A0 C6 08 A6 80 A7 A0 5A 26 F9 B7 FF DF` | ✅ |
| `$FEF0-$FEFF` | `0F 16 02 0F 16 02 18 16 02 12 16 02 09 16 02 09` | `FF FF FF FF FF FF FF FF ...` (padding) | ❌ |

### What this actually means

Two different code paths in `coco3.c read_byte` are at play, depending on whether the address is in `$FE00-$FEFF` or not. With our boot state (MC3=1, MMUEN=0, TY=0):

- **`$C000-$FDFF`**: `tcc1014.c` decodes `S=1` (CTS, cart ROM), `RAS=0` ([tcc1014.c:729-731](../../docs/reference/xroar/src/tcc1014/tcc1014.c)). In `coco3.c read_byte`, the case-1 branch calls `cart_rom_read` with `R2=1` — `rombank_d8` reads cart ROM at offset `A^$4000` (slot mask wraps to within the 16K cart). D = cart ROM byte. **The `if (RAS)` block is skipped (RAS=0)** → no RAM overwrite. **So gdb-mcp reads here return cart-ROM bytes directly. They do NOT reflect RAM contents.**
- **`$FE00-$FEFF`**: same outer logic gives S=1, but the **inner check at [tcc1014.c:719-723](../../docs/reference/xroar/src/tcc1014/tcc1014.c)** sets `RAS=1` whenever MC3=1. Now `coco3.c read_byte`'s `if (RAS)` block executes, and `ram_d8` **overwrites D with the RAM contents** after the cart-rom read already loaded it. **So gdb-mcp reads here return RAM contents.**

### What the cart-shadow self-copy actually does

Re-applying this to the write path during the cart-shadow loop:

- **For x in $C000-$FDFE** (the bulk of the copy): `ldd ,x` returns cart ROM bytes (D = cart ROM). `std ,x` calls `cart_rom_write` (a no-op — `rombank_d8` is read-only), and skips `ram_d8` because RAS=0. **Net effect: nothing is written to RAM.**
- **For x in $FE00-$FEFE** (last ~256 bytes): `ldd ,x` returns RAM contents (the cart-rom read is overwritten by ram_d8 read). `std ,x` writes those same RAM contents back via ram_d8 (RAS=1). **Net effect: RAM unchanged — round-trip of whatever was already there.**

### So the cart-shadow self-copy is a no-op on XRoar 1.10

It never actually populates RAM at `$C000-$FEFF`. The bytes we see at `$C000-$C0FF` via gdb-mcp are **cart ROM bytes served directly through the GIME's S=1/CTS decode**, not RAM. The bytes at `$FEF0-$FEFF` are **bank-0 RAM contents — whatever BASIC left there**, which happens to look like SECB-ROM-style data.

### The remaining open question

How does the Phase 2.4 build actually render three tiles? Post-SAM_ALLRAM (TY=1), the GIME's `if (!TY && bank>=$3C)` condition flips to FALSE → `else` branch → `RAS=1` for ALL of `$C000-$FDFF`. Then `coco3.c read_byte` runs `ram_d8` and the result overwrites whatever the case-1 cart_rom_read returned. With RAM uninitialized at those locations, the CPU should immediately fetch garbage.

But it doesn't — Phase 2.4 visibly works. So either:
1. **Source review still has a gap** — there's a code path I haven't found that keeps cart ROM accessible post-SAM_ALLRAM. Could be a separate special case for the cart window, or an XRoar bug where SAM TY doesn't propagate to the decode in our exact state.
2. **The 3-tile render is a stale framebuffer artifact** from a previous run, not actual rendering by this build. Worth checking by clearing XRoar state between runs and verifying the tiles still appear.

### Recommended next probe

The third pass (above) settled "does the cart-shadow self-copy populate RAM?" — **no, it doesn't, and it never did.** Pre-SAM_ALLRAM reads at `$C000+` come straight from cart ROM via the S=1/CTS path; the apparent "copy works" appearance was a misread of the read path.

The next discriminating question is: **how does Phase 2.4 actually render three tiles**, given that the code post-SAM_ALLRAM should be fetching from uninitialized RAM?

Two probes, in order:

1. **Move the `bra .` halt to AFTER `sta SAM_ALLRAM`** (e.g., at line 147). Attach gdb-mcp, read `$C000-$C0FF`. If it now shows DRAM init pattern (`00 00 00 00 FF FF FF FF` repeating) — the post-SAM_ALLRAM state breaks the cart-window read path, yet the boot supposedly continues past this point. Investigate how it does.
2. **Confirm Phase 2.4 actually renders three tiles in a fresh emulator run** (no carry-over state). Clear `~/.xroar/` config and any snapshot files, then run the canonical build with `phase24_halt` in place. If the tiles still appear from a cold start, the rendering is real and there's a third XRoar code path keeping cart bytes accessible. If they DON'T appear, our prior "3 tiles render" observation was contaminated state from a previous run.

Probe 2 is the cheapest discriminator and should be first.

### Implications regardless of (1)/(2) outcome

The "cart-to-shadow-RAM self-copy → all-RAM execution" boot model from [implementation/memory-map.md](../implementation/memory-map.md) is **not actually how XRoar runs our cart**. We've been running directly from cart ROM the whole time. This means:
- Self-modifying code (if any) would have failed silently.
- The `org $C0DC` workaround for the XRoar bad-window assumes RAM-shadow execution and may need revisiting.
- Any data tables we expect to be RAM-resident (e.g., post-Phase 4 game state at `$A000+`) need a different population mechanism.

This is a substantial revision to our mental model of the boot. Worth a wiki update to [implementation/memory-map.md](../implementation/memory-map.md) and possibly [implementation/lessons-learned.md](../implementation/lessons-learned.md) once probes 1 and 2 settle the picture.

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
