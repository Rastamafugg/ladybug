---
name: Sound — DAC + 1-bit square-wave paths
description: How the CoCo 3 generates audio — 6-bit DAC on PIA2 (selector switch position 0), 1-bit square wave on PIA2 PB1, and the cassette / cartridge inputs we won't use. Choosing between them for Ladybug.
type: concept
tags: [sound, dac, pia]
updated: 2026-05-07
---

# Sound

The CoCo's audio mixer accepts four sources, gated by a "selector switch" implemented on PIA1's CA2 and CB2 plus a master enable on PIA2 CB2:

| Selector A pos | Source |
|-|-|
| 0 | 6-bit DAC on PIA2 PA7-PA2 |
| 1 | Cassette playback |
| 2 | Cartridge SND pin 35 |
| 3 | Hard-wired low (silence) |

Plus an independent 1-bit square-wave source on PIA2 PB1 that's always summed into the path (when the master is on).

For Ladybug, only sources 0 and the PB1 square wave matter.

## 6-bit DAC (selector position 0)

- PIA2 DRA `$FF20` bits 7-2 form the 6-bit value (PA7 = MSB).
- Output range 0 .. 4.5 V in approximately 0.07 V steps (PA7 = 2.25 V, PA6 = 1.125, PA5 = 0.563, PA4 = 0.281, PA3 = 0.140, PA2 = 0.070).
- Setup: configure PIA1 CRA so CA2 outputs low and PIA1 CRB so CB2 outputs low (= position 0); then set PIA2 CB2 high (master on); ensure PIA2 DDRA bits 7-2 = 1 (output) and CRA bit 2 = 1 (DR access).
- To play a tone, write a sine-wave-like sequence of values to `$FF20` at a regular cadence. Pitch = inverse of write period; timbre = waveform shape.

The DAC also drives the cassette write path (via the attenuator on pin 4 of the CASS jack) — we won't be writing cassette, so the path is ours to drive freely.

## 1-bit square wave on PB1

- PIA2 PB1 (bit 1 of `$FF22`). Configure DDRB bit 1 = 1 (output), then toggle PB1.
- Limited timbre but very cheap — no DAC table to feed; just an `EORA #$02 / STA $FF22` pair plus a delay loop. The CoCo 1/2 manual's `SLTON` listing demonstrates exactly this for a sliding-pitch tone.
- Sums with whatever the selector switch routes.

## Choosing for Ladybug

The original arcade Lady Bug has melody snippets (during attract, between stages, when collecting heart, on death) and many short SFX (eat dot, eat vegetable, enemy moves through gate, death). A first pass:

- **PB1 square wave** for short SFX — cheap, fast, doesn't need a sample table.
- **6-bit DAC** driven from the Vbord IRQ for one melody voice (a stepped-sine table). One channel of melody is faithful to the arcade's mono audio output.

Decision deferred to coding-architect. Both share the same IRQ context, which is the constraint that matters: anything we do in sound has to fit in the 60 Hz Vbord handler's slack budget — see [timing.md](timing.md).

## Selector setup gotcha

The selector switch state is split across two PIAs (PIA1's CA2/CB2 select the position; PIA2's CB2 is the master). Both PIAs need their CR bits configured for "CA2/CB2 = output, hold value = bit 3 of the CR". From a cold reset, BASIC sets up usable defaults; we will *not* rely on those — we'll initialise both PIAs explicitly.

## Sources

- [../sources/coco-asm-tepolt.md](../sources/coco-asm-tepolt.md) ch. 10 (DAC, selector, comparator, listings 10-2 SLTON)
- [../sources/coco3-asm-tepolt.md](../sources/coco3-asm-tepolt.md) ch. 7 ("split FF22": bits 2-0 still drive PB1/CB2/etc.)
