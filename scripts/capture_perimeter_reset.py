#!/usr/bin/env python3
"""Capture the approved PERF-004 reset worklists using the shared harness."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from capture_performance_baseline import BUILD, capture_snapshot, symbol


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    command = [sys.executable, str(ROOT / "scripts" / "capture_death_reset.py"),
               "--prefix", "perf004", *sys.argv[1:]]
    subprocess.run(command, cwd=ROOT, check=True)
    published = symbol(BUILD / "ladybug-enemy-runtime.map", "perimeter_reset_published")
    for scenario in ("zero", "four", "vegetable"):
        for owner in ("a", "b"):
            capture_snapshot(
                BUILD / f"perf004-{scenario}-{owner}-published.sna",
                published, 1, BUILD / f"perf004-{scenario}-{owner}.sna",
            )


if __name__ == "__main__":
    main()
