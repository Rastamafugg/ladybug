#!/usr/bin/env python3
"""Reject enemy-frame writes outside the old/new 16x16 sprite rectangles."""

import argparse
from pathlib import Path

from read_snapshot import cpu_to_phys, find_ram


parser = argparse.ArgumentParser()
parser.add_argument("before", type=Path)
parser.add_argument("after", type=Path)
parser.add_argument("--rect", action="append", required=True, type=lambda s: int(s, 16))
args = parser.parse_args()

before = find_ram(args.before.read_bytes())
after = find_ram(args.after.read_bytes())
changed = [
    address for address in range(0x2000, 0x9800)
    if before[cpu_to_phys(address)] != after[cpu_to_phys(address)]
]
allowed = set()
for base in args.rect:
    for row in range(16):
        allowed.update(range(base + row * 160, base + row * 160 + 8))
outside = [address for address in changed if address not in allowed]
if outside:
    sample = ", ".join(f"${address:04X}" for address in outside[:8])
    raise SystemExit(
        f"enemy framebuffer proof failed: {len(outside)} changed bytes outside rectangles; {sample}"
    )
print(f"enemy framebuffer proof: {len(changed)} changed bytes, 0 outside actor rectangles")
