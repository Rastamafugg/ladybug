#!/usr/bin/env python3
"""Capture current-map gate-transition traces for the transition-profile verifier."""

from pathlib import Path
import re

from capture_performance_baseline import capture_snapshot, capture_trace, symbol
from patch_snapshot_state import patch_snapshot
from read_snapshot import find_ram


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
FB_A_PHYSICAL = 0x58000
FB_BYTES = 320 * 192 // 2


def write_frame(snapshot: Path, output: Path) -> None:
    ram = find_ram(snapshot.read_bytes())
    output.write_bytes(ram[FB_A_PHYSICAL:FB_A_PHYSICAL + FB_BYTES])


def normalize_trace(path: Path, frame_pc: int) -> None:
    lines = path.read_text(encoding="ascii").splitlines()
    for index, line in enumerate(lines):
        if re.match(r"^[0-9a-f]{4}\|", line):
            if line.startswith("0000|"):
                lines[index] = f"{frame_pc:04x}" + line[4:]
            break
    path.write_text("\n".join(lines) + "\n", encoding="ascii")


def main() -> None:
    frame_pc = symbol(BUILD / "ladybug-enemy-runtime.map", "frame_render_impl")
    stop_pc = symbol(BUILD / "ladybug.map", "main_render")
    hydrated = BUILD / "perf-four-hydrated.sna"
    diagonal = BUILD / "gate-delta-owner-a.sna"
    patch_snapshot(
        hydrated,
        diagonal,
        [
            "0018=01", "0019=00",
            "0088=01", "0089=00", "008A=00", "008B=00",
            "008D=00", "008E=00", "A240=01",
        ],
    )
    capture_trace(diagonal, BUILD / "gate-delta-owner-a.trace", stop_pc, 1)
    normalize_trace(BUILD / "gate-delta-owner-a.trace", frame_pc)
    capture_snapshot(BUILD / "gate-delta-diagonal.sna", frame_pc, 1, diagonal)

    final = BUILD / "gate-delta-owner-b.sna"
    patch_snapshot(
        diagonal,
        final,
        ["0088=01", "0089=01", "008A=00", "008B=00", "008D=00", "008E=00"],
    )
    capture_trace(final, BUILD / "gate-delta-owner-b.trace", stop_pc, 1)
    normalize_trace(BUILD / "gate-delta-owner-b.trace", frame_pc)
    capture_snapshot(BUILD / "gate-delta-final.sna", frame_pc, 1, final)

    write_frame(diagonal, BUILD / "gate-delta-before.bin")
    write_frame(BUILD / "gate-delta-diagonal.sna", BUILD / "gate-delta-diagonal.bin")
    write_frame(BUILD / "gate-delta-final.sna", BUILD / "gate-delta-final.bin")
    print("gate transition profile: current-map traces and frame captures written")


if __name__ == "__main__":
    main()
