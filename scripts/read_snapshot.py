#!/usr/bin/env python3
"""Dump bytes at specific CoCo3 addresses from an XRoar v2 snapshot.

XRoar serialises 512K bank 0 RAM as a single 524288-byte uint8 array tagged
RAM_SER_D_DATA=1. The length 0x80000 is encoded as a 3-byte vuint32 (0xC8 0x00
0x00), so the marker we hunt for is `\x01\xC8\x00\x00` followed by exactly
524288 RAM bytes.

Translates each CPU address through the GIME state assumed at the probe point:
  - MMUEN=1, MC3=1, TR=0
  - PAR_EXEC table loaded (PAR0=$38..PAR7=$3F)
  - $FE00-$FEFF: MC3 forces bank = 0x38 | (A>>13), independent of PAR
  - $C000-$FDFF and elsewhere: bank = par_table[A>>13]
"""
import sys

PAR_EXEC = [0x38, 0x30, 0x31, 0x32, 0x33, 0x3D, 0x3E, 0x3F]
RAM_MARKER = b"\x01\xC8\x00\x00"
RAM_LEN = 0x80000


def find_ram(buf):
    idx = buf.find(RAM_MARKER)
    if idx < 0:
        sys.exit("read_snapshot: RAM_SER_D_DATA marker not found")
    start = idx + len(RAM_MARKER)
    if start + RAM_LEN > len(buf):
        sys.exit("read_snapshot: marker found but file truncated before RAM end")
    return buf[start:start + RAM_LEN]


def cpu_to_phys(addr):
    bank_idx = (addr >> 13) & 7
    if 0xFE00 <= addr < 0xFF00:
        bank = 0x38 | bank_idx       # MC3 force-FExx
    else:
        bank = PAR_EXEC[bank_idx]    # MMU on, exec set
    return (bank << 13) | (addr & 0x1FFF)


def main():
    if len(sys.argv) < 3:
        sys.exit("usage: read_snapshot.py FILE ADDR [ADDR ...]   (hex, e.g. 0FFE)")
    path = sys.argv[1]
    with open(path, "rb") as fh:
        buf = fh.read()
    ram = find_ram(buf)
    for raw in sys.argv[2:]:
        addr = int(raw, 16)
        phys = cpu_to_phys(addr)
        b = ram[phys]
        print(f"${addr:04X}  →  phys ${phys:05X}  =  ${b:02X}  ({b})")


if __name__ == "__main__":
    main()
