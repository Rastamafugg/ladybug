#!/usr/bin/env python3
"""Copy an XRoar snapshot while patching CPU-visible RAM bytes."""

import argparse
from pathlib import Path

from read_snapshot import RAM_MARKER, cpu_to_phys


parser = argparse.ArgumentParser()
parser.add_argument("source", type=Path)
parser.add_argument("target", type=Path)
parser.add_argument("patch", nargs="+", help="ADDR=BYTE, both hexadecimal")
args = parser.parse_args()

snapshot = bytearray(args.source.read_bytes())
marker = snapshot.find(RAM_MARKER)
if marker < 0:
    raise SystemExit("patch snapshot: RAM marker not found")
ram_start = marker + len(RAM_MARKER)
for assignment in args.patch:
    raw_addr, raw_value = assignment.split("=", 1)
    address = int(raw_addr, 16)
    value = int(raw_value, 16)
    if not 0 <= value <= 0xFF:
        raise SystemExit(f"patch snapshot: byte out of range: {assignment}")
    snapshot[ram_start + cpu_to_phys(address)] = value
args.target.write_bytes(snapshot)
