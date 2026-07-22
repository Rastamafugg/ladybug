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
    main_source = (Path(__file__).resolve().parents[1] / "src/main.s").read_text(
        encoding="utf-8"
    )
    loader_source = (Path(__file__).resolve().parents[1] / "src/gmc_bootstrap.s").read_text(
        encoding="utf-8"
    )
    if "sta     SAM_FAST" not in main_source or "SAM_FAST   equ  $FFD9" not in main_source:
        raise SystemExit("gmc proof: resident fast-clock selection missing")
    if "sta     SAM_FAST" not in loader_source or "SAM_FAST    equ $FFD9" not in loader_source:
        raise SystemExit("gmc proof: bootstrap fast-clock selection missing")
    resident_copy = loader_source[loader_source.index("; Bank 1 contains"):
                                  loader_source.index("copy_resident\n")]
    if "lda     #$3E\n        sta     PAR_EXEC+5" not in resident_copy:
        raise SystemExit("gmc proof: resident copy does not restore PAR5 to physical page $3E")
    if bytes((0xB7, 0xFF, 0xD9)) not in boot:
        raise SystemExit("gmc proof: assembled bootstrap fast-clock write missing")
    if bytes((0xB7, 0xFF, 0xD9)) not in rom[0x4000:0x8000]:
        raise SystemExit("gmc proof: assembled resident fast-clock write missing")
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
    if len(bank_writes) < 5:
        raise SystemExit("gmc proof: expected five loader bank writes")
    bank2_signature = relocated_pc(bytes((0xFC, 0xC0, 0x10)), 0)
    bank3_signature = relocated_pc(bytes((0xFC, 0xC0, 0x10)), 1)
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
        "bank 2 signature": f"{bank2_signature}| fcc010" in text and "a=b2 b=02" in text,
        "bank 3 signature": f"{bank3_signature}| fcc010" in text and "a=b3 b=03" in text,
        "bank-2 sprites selected": f"{bank_writes[2]}| b7ff50" in text,
        "bank-3 module selected": f"{bank_writes[3]}| b7ff50" in text,
        "runtime bank selected": f"{bank_writes[4]}| b7ff50" in text,
        "all-RAM handoff": f"{allram}| b7ffdf" in text,
        "bank-3 module payload": rom[0xC800:0xC80C] != bytes((0xA3,)) * 12,
        "bank-2 sprite payload": rom[0x8800:0xA800] != bytes((0xA2,)) * 0x2000,
        "enemy module entered": "0800| 7e" in text,
        "runtime main loop": text.count(f"{mainloop}| 13") >= 2,
    }
    failed = [name for name, passed in required.items() if not passed]
    if failed:
        raise SystemExit("gmc proof failed: " + ", ".join(failed))
    print("gmc proof: bank-2 sprites, bank-3 module, bank-1 load, TY=1 handoff, and relocated main loop verified")


if __name__ == "__main__":
    main()
