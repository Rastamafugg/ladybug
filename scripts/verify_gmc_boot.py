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
        "runtime bank selected": "0323| b7ff50" in text,
        "all-RAM handoff": "0358| b7ffdf" in text,
        "runtime main loop": text.count(f"{mainloop}| 13") >= 2,
    }
    failed = [name for name, passed in required.items() if not passed]
    if failed:
        raise SystemExit("gmc proof failed: " + ", ".join(failed))
    print("gmc proof: banks 2/3, bank-1 load, TY=1 handoff, and relocated main loop verified")


if __name__ == "__main__":
    main()
