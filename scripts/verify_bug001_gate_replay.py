#!/usr/bin/env python3
"""Verify BUG-001 gate-style replay convergence and stack locality."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
sys.path.insert(0, str(ROOT / "scripts"))

from capture_performance_baseline import capture_snapshot, symbol  # noqa: E402
from patch_snapshot_state import patch_snapshot  # noqa: E402
from read_snapshot import cpu_to_phys, find_ram  # noqa: E402


def gate_records() -> list[tuple[int, int, int]]:
    text = (BUILD / "ladybug_maze.inc").read_text(encoding="utf-8")
    values: list[int] = []
    for line in text.split("\nmaze_gates\n", 1)[1].splitlines():
        if "fcb" not in line:
            break
        values.extend(int(item.strip().replace("$", "0x"), 0)
                      for item in line.split("fcb", 1)[1].split(","))
    return [tuple(values[index:index + 3]) for index in range(0, 60, 3)]


def region_difference(ram: bytes, gx: int, gy: int) -> int:
    bases = (0x60000, 0x58000)
    difference = 0
    for cell_y in range(max(0, gy - 2), min(24, gy + 3)):
        for cell_x in range(max(0, gx - 2), min(24, gx + 3)):
            start = cell_y * 8 * 160 + (cell_x + 8) * 4
            for row in range(8):
                for column in range(4):
                    offset = start + row * 160 + column
                    difference += ram[bases[0] + offset] != ram[bases[1] + offset]
    return difference


def main() -> None:
    base = BUILD / "perf-four-hydrated.sna"
    if not base.exists():
        raise SystemExit("BUG-001 verifier: recapture perf-four-hydrated.sna first")
    frame_pc = symbol(BUILD / "ladybug-enemy-runtime.map", "frame_render_impl")
    failures: list[dict[str, int]] = []
    with tempfile.TemporaryDirectory(prefix="ladybug-bug001-") as directory:
        directory = Path(directory)
        for gate, (gx, gy, initial_state) in enumerate(gate_records()):
            for style in (0, 1):
                source = directory / f"gate-{gate:02d}-style-{style}.sna"
                result = directory / f"gate-{gate:02d}-style-{style}-done.sna"
                patch_snapshot(
                    base,
                    source,
                    [
                        "0006=FF", "000F=FF", "005B=FF", "005C=FF", "006B=00",
                        f"0019={gate + 1:02X}", f"001A={style:02X}",
                        f"0088={gate + 1:02X}", "0089=00", "008A=00", "008B=00",
                        f"008D={style:02X}", "008E=00",
                        f"{0xA240 + gate:04X}={initial_state ^ 1:02X}",
                    ],
                )
                capture_snapshot(result, frame_pc, 5, source)
                difference = region_difference(find_ram(result.read_bytes()), gx, gy)
                if difference:
                    failures.append({"gate": gate, "style": style, "different_bytes": difference})

        canaries: list[str] = []
        for style in (0, 1):
            source = directory / f"canary-{style}.sna"
            result = directory / f"canary-{style}-done.sna"
            patch_snapshot(
                base,
                source,
                [
                    "0006=FF", "000F=FF", "005B=FF", "005C=FF", "006B=00",
                    "007F=00", "0080=00", "0087=00", "0019=01", "001A=01",
                    "0088=01", "0089=00", "008A=00", "008B=00", "008C=0A",
                    f"008D={style:02X}", "008E=00", "A240=01", "1D00=5A", "1D01=A5",
                ],
            )
            capture_snapshot(result, frame_pc, 5, source)
            ram = find_ram(result.read_bytes())
            canaries.append(ram[cpu_to_phys(0x1D00):cpu_to_phys(0x1D00) + 2].hex())

    report = {
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "cases": 40,
        "convergence_failures": failures,
        "stack_canary_address": "$1D00",
        "stack_canary_values_style_0_style_1": canaries,
        "pass": not failures and canaries == ["5aa5", "5aa5"],
    }
    (BUILD / "bug-001-gate-style.json").write_text(json.dumps(report, indent=2) + "\n", encoding="ascii")
    print(json.dumps(report, indent=2))
    if not report["pass"]:
        raise SystemExit("BUG-001 verifier: failure")


if __name__ == "__main__":
    main()
