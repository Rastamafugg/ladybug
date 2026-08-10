#!/usr/bin/env python3
"""Capture the approved PERF-004 reset worklists using the shared harness."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from capture_performance_baseline import BUILD


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    skip_build = "--skip-build" in sys.argv[1:]
    for index, scenario in enumerate(("zero", "four", "vegetable")):
        command = [
            sys.executable,
            str(ROOT / "scripts" / "capture_death_reset.py"),
            "--prefix", "perf004", "--case", scenario,
        ]
        if skip_build or index:
            command.append("--skip-build")
        subprocess.run(command, cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
