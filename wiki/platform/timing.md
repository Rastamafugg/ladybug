---
name: Timing — clock rates, IRQ sources, frame budget
description: MPU clock options, the four candidate periodic interrupt sources (Vbord, Hbord, ACVC Timer, PIA1 CB1), and the per-frame instruction budget that follows.
type: concept
tags: [timing, irq, vbord, hbord, frame-budget]
updated: 2026-05-07
---

# Timing

## MPU clock

- **0.89 MHz (slow).** Default after reset. Required by BASIC ROM cassette/serial/disk routines. Write anything to `$FFD8`.
- **1.78 MHz (fast).** Doubles instruction throughput. The MC68B09E in the CoCo 3 is rated for it. Write anything to `$FFD9`.

Ladybug will run fast — we don't enter BASIC ROM I/O. Decision rationale: doubling the budget halves the cost of every cycle-counting decision and brings Lady Bug's 60-Hz arcade frame within easy reach.

## Periodic interrupt sources

| Source | Rate | Path | Where to enable |
|-|-|-|-|
| **Vbord (vertical sync)** | 60 Hz (16.67 ms) | GIME ACVC | `$FF92` bit 3, plus Init0 bit 5 |
| **Hbord (horizontal sync)** | ~15.7 kHz (63.5 µs) | GIME ACVC | `$FF92` bit 4 |
| **Timer (programmable)** | 12-bit reload at 63.5 µs or 70 ns ticks | GIME ACVC | `$FF94/95` reload, `$FF92` bit 5 |
| PIA1 CB1 (legacy 60 Hz VSYNC) | 60 Hz | PIA1, Tepolt-Book skeleton | `$FF03` bit 0 |
| PIA1 CA1 (legacy ~15.7 kHz HSYNC) | ~15.7 kHz | PIA1 | `$FF01` bit 0 |

The PIA1 CA1/CB1 paths still work on the CoCo 3 but the GIME-native equivalents (Hbord/Vbord) are preferred:

1. They share the GIME's interrupt-ack mechanism (read `$FF92` to clear), so an interrupt handler only has one ack point regardless of which source fired.
2. They don't disturb the keyboard/joystick code path that reuses PIA1.

**Decision: Ladybug's main game tick = ACVC Vbord IRQ.** That gives us a clean 60 Hz frame interrupt; everything else (animation, AI, input poll, sound dispatch) runs from the same handler.

A few µs of jitter to account for: an FIRQ for serial / cartridge can preempt the main IRQ; that's intentional and matches the IRQ < FIRQ < NMI priority order.

## Frame budget at 1.78 MHz

- 16.67 ms × 1 780 000 cycles/s ≈ **29 666 cycles per frame**. A typical 6809 instruction takes 4-7 cycles, so call it ≈ 5 000 useful instructions per frame.
- IRQ entry: ~21 cycles (push 12 bytes onto S, vector fetch, jump-table LBRA). RTI: ~15 cycles. Round-trip overhead ~36 cycles per frame. Negligible at 60 Hz; non-trivial if we tried to use Hbord.
- FIRQ entry: ~12 cycles (push only PC+CC). RTI: ~6 cycles. Use FIRQ for any tight inner-loop interrupt where we can keep state in registers we choose to preserve manually.

Rough partition for first-pass design (will be revisited by coding-architect):

| Phase | Target cycles | What |
|-|-|-|
| Input poll | 1 000 | Joystick + fire buttons via PIA1 (could be done at user-level rather than in the IRQ) |
| AI / game logic | 8 000 | 8 enemies + skull + player + collision |
| Render / sprite blit | 18 000 | Update only changed cells/tiles |
| Sound update | 1 500 | Step DAC tone or PB1 toggle |
| Slack | 1 000 | Headroom |

If the render exceeds budget we drop to 30 Hz logic + 60 Hz render, or vice versa. None of these numbers are firm yet — they are the planning baseline.

## Sources

- [../sources/coco3-asm-tepolt.md](../sources/coco3-asm-tepolt.md) ch. 6 (Vbord/Hbord/Timer), ch. 7 (clock select)
- [../sources/coco-asm-tepolt.md](../sources/coco-asm-tepolt.md) ch. 9 (PIA-driven HS/FS interrupts)
