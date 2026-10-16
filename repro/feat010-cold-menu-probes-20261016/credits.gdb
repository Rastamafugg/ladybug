# Parent releases a separate owned cold process after reviewing Options. The
# 45-second deadline starts at this cold launch; each stop/continue call is at
# most 10 seconds and total observations are capped at 12. Do not source/run as
# an unattended script.
# First case observation: while the guest runs, user presses Down, releases,
# presses Down, releases, presses Return, then releases. A=7 selects Credits.
tbreak *0x1a78 if $a == 7
continue
p/x $pc
p/x $a
x/2xb 0x00a5
x/11xb 0x008f
x/8xb $pc
x/8xb $s

# These are subsequent mapped callback/publication observations. At each stop
# capture PC bytes and stack continuation bytes before interpreting the label.
tbreak *0x1ace
continue
p/x $pc
x/2xb 0x00a5
x/11xb 0x008f
x/8xb $pc
x/8xb $s
tbreak *0x1b48
continue
p/x $pc
x/2xb 0x00a5
x/11xb 0x008f
x/8xb $pc
x/8xb $s
tbreak *0x1bc1
continue
p/x $pc
x/2xb 0x00a5
x/11xb 0x008f
x/8xb $pc
x/8xb $s
# Record actual progress/input response, frame/commit values, and missed-commit
# baseline/delta. No zero-miss gate. User must witness the reported defect.

# Optional helper note only: if a separately approved observation naturally
# reaches 0x1a21 within this same deadline, classify X/U/A against instruction
# (0xa422/0x03aa/0x23), demo (0xa7cc/0x008f/0x23), or high-score
# (0xa880/0x0395/0x23). High-score is a legitimate owner. No helper breakpoint,
# wait, or copy inspection is part of this Credits sequence.
