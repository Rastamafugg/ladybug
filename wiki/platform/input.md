---
name: Input — keyboard and joysticks
description: PIA1 keyboard matrix scanning, joystick fire buttons (now two each), and joystick X/Y read via the PIA2 DAC + comparator successive-approximation A/D loop.
type: concept
tags: [input, pia, keyboard, joystick]
updated: 2026-05-07
---

# Input

## Keyboard

The keyboard is a passive 8-column × 8-row switch matrix. The MPU drives one column low at a time on PIA1 PB0-PB7 (output) and reads the row on PIA1 PA0-PA6 (input). Every closed switch in the active column pulls its row line low.

Layout (CoCo 3, with new keys folded into row PB6 — see Fig 7-3 of the CoCo 3 manual):

```
                     PB7  PB6  PB5  PB4  PB3  PB2  PB1  PB0
PA6  shift           ----  F2   F1  CTRL  ALT  brk  clr  enter
PA5   /     .   -    ,     ;    :    9    8
PA4   7     6   5    4     3    2    1    0
PA3  sp     →   ←    ↓     ↑    Z    Y    X
PA2   W     V   U    T     S    R    Q    P
PA1   O     N   M    L     K    J    I    H
PA0   G     F   E    D     C    B    A    @
```

PA7 is *not* used for keyboard sensing — it's the joystick comparator output. Read PIA1 DRA (`$FF00`) with CRA configured for direct-data-register access (CRA bit 2 = 1, set by BASIC's init or by us).

### Scan algorithm

```
for col in 0..7:
    write ~(1<<col) to DRB ($FF02)             ; one zero, rest ones
    a = read DRA ($FF00)                       ; rows
    for row_bit in 0..6:
        if (a & (1<<row_bit)) == 0: key (col,row) is pressed
```

For a single-key game like Ladybug we only care about four directions + start/pause + the two fire buttons; eight column drives = ~80 cycles total, easily under our per-frame budget.

### Kybd/Jy IRQ

If we set IRQEN bit 1 (`$FF92`), any keypress or fire-button press triggers an ACVC IRQ — but only after we drive all PB0-PB7 low simultaneously. Useful for a "press any key to start" screen but generally not for in-game movement (we want to scan deliberately).

## Joystick fire buttons

Each CoCo 3 joystick has two fire buttons (CoCo 1/2 had one). They land on previously-unused row positions:

- Right joystick button 1 → PIA1 PA0 column ?? — already PA0 wired to fire-button pin 4 of the right jack.
- Left joystick button 1 → PIA1 PA1 — wired to pin 4 of the left jack.
- Button 2 (both sticks) → row PB6 / extra PA bits per Fig 7-3 — consult the figure.

Active low: a clear bit means pressed. Read PIA1 DRA after driving the appropriate column.

## Joystick X / Y position

Each joystick output is two analog voltages (0..4.5 V) representing left/right and forward/back. The CoCo's "ADC" is software successive-approximation built from:

1. **6-bit DAC** on PIA2 PA7-PA2 (`$FF20` bits 7-2). Output voltage = sum of bit-weights.
2. **Selector switch** controlled by PIA1 CA2 (b0) + CB2 (b1) — picks one of four analog sources (R-X, R-Y, L-X, L-Y) into the comparator's `(+)` input.
3. **Master enable** = PIA2 CB2.
4. **Comparator** output = PIA1 PA7 (high if DAC < analog, low otherwise).

Algorithm (mirrors `JOYIN` ROM):

```
write CA2/CB2 to select desired axis (CRA/CRB of PIA1)
clear B
loop:
    write B to $FF20                  ; DAC output
    read $FF00                        ; PA7 = comparator
    if PA7 == 0: break                ; DAC just exceeded analog
    add 4 to B                        ; next 6-bit code (bits 7..2)
    if B == $FC: break                ; saturated
result = B >> 2                       ; 0..63 position
```

Lady Bug uses 4-direction joystick input only, so we likely binarise: x < threshold → left, x > threshold → right, similarly for Y. We can also skip the ADC entirely and use the keyboard arrows. Decision deferred.

## Sources

- [../sources/coco-asm-tepolt.md](../sources/coco-asm-tepolt.md) ch. 10 (keyboard, fire buttons, joystick A/D)
- [../sources/coco3-asm-tepolt.md](../sources/coco3-asm-tepolt.md) ch. 7 (extended keyboard matrix Fig 7-3, button 2)
