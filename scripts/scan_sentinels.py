#!/usr/bin/env python3
"""Scan an XRoar snapshot's RAM for our probe sentinels.

We wrote $55 to virtual $FEF7 (suspect IRQ-vector slot) and $AA to virtual
$0FFF (liveness marker). If those writes landed in unexpected physical banks,
they should still appear somewhere in the 512K block. This script reports every
$55 and every $AA in RAM, grouped by 8K bank, so we can see whether the writes
ended up in PAR0/PAR1/etc. instead of where the par_table expects.
"""
import sys
from collections import Counter

RAM_MARKER = b"\x01\xC8\x00\x00"
RAM_LEN = 0x80000


def find_ram(buf):
    idx = buf.find(RAM_MARKER)
    if idx < 0:
        sys.exit("scan_sentinels: RAM marker not found")
    return buf[idx + len(RAM_MARKER):idx + len(RAM_MARKER) + RAM_LEN]


def hits(ram, val, *, exclude_padding=True):
    found = []
    for i, b in enumerate(ram):
        if b == val:
            found.append(i)
    return found


def summarise(label, val, locs):
    bank_counts = Counter(loc >> 13 for loc in locs)
    print(f"{label}: {len(locs)} hits across {len(bank_counts)} banks")
    # Show banks with <=8 hits (likely meaningful), aggregate the rest
    rare = [(b, c) for b, c in sorted(bank_counts.items()) if c <= 8]
    busy = [(b, c) for b, c in sorted(bank_counts.items()) if c > 8]
    for b, c in rare:
        offsets = [loc & 0x1FFF for loc in locs if (loc >> 13) == b]
        offsets_s = ", ".join(f"${o:04X}" for o in offsets[:8])
        print(f"  bank ${b:02X}: {c} hits → {offsets_s}")
    if busy:
        total_busy = sum(c for _, c in busy)
        print(f"  (busy banks ${busy[0][0]:02X}-${busy[-1][0]:02X}: {total_busy} hits)")


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: scan_sentinels.py FILE")
    with open(sys.argv[1], "rb") as fh:
        buf = fh.read()
    ram = find_ram(buf)
    summarise("$55", 0x55, hits(ram, 0x55))
    print()
    summarise("$AA", 0xAA, hits(ram, 0xAA))


if __name__ == "__main__":
    main()
