#!/usr/bin/env python3
"""Run a bounded headless XRoar trace and verify the GMC loader handoff."""

from __future__ import annotations

import argparse
import re
import subprocess
import tempfile
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--xroar", default="/usr/local/bin/xroar")
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--map", type=Path, required=True)
    args = parser.parse_args()

    map_text = args.map.read_text(encoding="utf-8")
    match = re.search(r"^Symbol: mainloop .* = ([0-9A-Fa-f]+)$", map_text, re.M)
    if not match:
        raise SystemExit("gmc proof: mainloop missing from map")
    mainloop = match.group(1).lower()
    rom = args.rom.read_bytes()
    boot = rom[:0x4000]
    jump = boot.find(bytes((0x7E, 0x03, 0x00)))
    if jump < 0:
        raise SystemExit("gmc proof: relocated-loader jump missing")
    loader_start = jump + 3

    def relocated_pc(opcode: bytes, occurrence: int = 0) -> str:
        positions = []
        cursor = loader_start
        while True:
            cursor = boot.find(opcode, cursor)
            if cursor < 0:
                break
            positions.append(cursor)
            cursor += 1
        if occurrence >= len(positions):
            raise SystemExit(f"gmc proof: loader opcode {opcode.hex()} missing")
        return f"{0x0300 + positions[occurrence] - loader_start:04x}"

    bank_writes = []
    cursor = loader_start
    while True:
        cursor = boot.find(bytes((0xB7, 0xFF, 0x50)), cursor)
        if cursor < 0:
            break
        bank_writes.append(f"{0x0300 + cursor - loader_start:04x}")
        cursor += 1
    if len(bank_writes) < 4:
        raise SystemExit("gmc proof: expected four loader bank writes")
    allram = relocated_pc(bytes((0xB7, 0xFF, 0xDF)))

    command = [
        "timeout", "2", args.xroar,
        "-ui", "null", "-ao", "null",
        "-machine", "coco3", "-ram", "512",
        "-cart-type", "gmc", "-cart-rom", str(args.rom),
        "-cart-autorun", "-no-ratelimit", "-trace",
    ]
    with tempfile.TemporaryFile(mode="w+t", encoding="utf-8") as trace:
        subprocess.run(command, stdout=trace, stderr=subprocess.STDOUT, check=False)
        trace.seek(0)
        text = trace.read()

    required = {
        "bank 2 signature": "0305| fcc010" in text and "a=b2 b=02" in text,
        "bank 3 signature": "0313| fcc010" in text and "a=b3 b=03" in text,
        "bank-3 module selected": f"{bank_writes[2]}| b7ff50" in text,
        "runtime bank selected": f"{bank_writes[3]}| b7ff50" in text,
        "all-RAM handoff": f"{allram}| b7ffdf" in text,
        "bank-3 module payload": rom[0xC800:0xC80C] != bytes((0xA3,)) * 12,
        "enemy module entered": "0800| 7e" in text,
        "runtime main loop": text.count(f"{mainloop}| 13") >= 2,
    }
    failed = [name for name, passed in required.items() if not passed]
    if failed:
        raise SystemExit("gmc proof failed: " + ", ".join(failed))
    print("gmc proof: banks 2/3, bank-1 load, TY=1 handoff, and relocated main loop verified")


if __name__ == "__main__":
    main()
