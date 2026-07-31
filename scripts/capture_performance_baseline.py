#!/usr/bin/env python3
"""Capture reproducible current-revision performance scenarios in XRoar."""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
from pathlib import Path

from patch_snapshot_state import patch_snapshot


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
ROM = BUILD / "ladybug.rom"
ENEMY_TABLE = BUILD / "four-enemy-delta-enemy-table.bin"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="reuse the existing canonical build outputs",
    )
    return parser.parse_args()


def symbol(path: Path, name: str) -> int:
    pattern = re.compile(rf"^Symbol: {re.escape(name)} .* = ([0-9A-Fa-f]+)$")
    for line in path.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if match:
            return int(match.group(1), 16)
    raise ValueError(f"{path}: missing symbol {name}")


def xroar_base() -> list[str]:
    executable = shutil.which("xroar")
    if not executable:
        raise SystemExit("capture baseline: xroar is not installed")
    return [
        executable,
        "-ui", "null",
        "-ao", "null",
        "-machine", "coco3",
        "-ram", "512",
        "-cart-type", "gmc",
        "-cart-rom", str(ROM),
        "-no-ratelimit",
    ]


def run_xroar(arguments: list[str], output: Path) -> None:
    with output.open("w", encoding="ascii") as stream:
        result = subprocess.run(
            xroar_base() + arguments,
            cwd=ROOT,
            stdout=stream,
            stderr=subprocess.STDOUT,
            check=False,
        )
    if result.returncode:
        raise SystemExit(
            f"capture baseline: XRoar returned {result.returncode}; see {output}"
        )


def capture_snapshot(output: Path, frame_pc: int, count: int, source: Path | None = None) -> None:
    arguments = []
    if source is None:
        arguments += ["-ram-init", "0", "-cart-autorun"]
    else:
        arguments += ["-load", str(source)]
    arguments += [
        "-trap", f"pc=0x{frame_pc:04x}",
        "-trap-range", str(count),
        "-trap-snap", str(output),
        "-trap-timeout", "1",
    ]
    run_xroar(arguments, BUILD / f"{output.stem}.log")


def capture_trace(snapshot: Path, output: Path, stop_pc: int, intervals: int) -> None:
    # A snapshot is taken at frame_render_impl, after main_render's call site.
    # The Nth following main_render therefore closes N complete active intervals.
    run_xroar(
        [
            "-load", str(snapshot),
            "-trace",
            "-trace-timing",
            "-trap", f"pc=0x{stop_pc:04x}",
            "-trap-range", str(intervals),
            "-trap-no-trace",
            "-trap-timeout", "1",
        ],
        output,
    )


COMMON_PATCHES = [
    "0030=7F", "0031=FF",  # keep bonus-colour work outside the sample
    "004A=FF",              # keep perimeter work outside the sample
    "0050=FF",              # keep player animation outside enemy-only cases
    "0055=40",              # keep nest animation outside movement cases
    "0058=04", "0059=04", "005A=02",
    "0060=01", "0061=01", "007F=01", "0080=00", "0087=0A",
    "A908=00", "AA08=00",
    "A92C=00", "A92D=00", "A92E=00", "A92F=00",
    "AA2C=00", "AA2D=00", "AA2E=00", "AA2F=00",
]


def moving_patch(directions: tuple[int, int, int, int]) -> list[str]:
    result = [
        "A473=01", "A47B=01", "A483=01", "A48B=01",
        "0055=40", "0060=00", "0061=00", "0087=00",
    ]
    for address, direction in zip((0xA477, 0xA47F, 0xA487, 0xA48F), directions):
        result.append(f"{address:04X}={direction:02X}")
    return result


def main() -> None:
    args = parse_args()
    if not args.skip_build:
        subprocess.run([str(ROOT / "scripts" / "build.sh"), "build"], cwd=ROOT, check=True)

    frame_pc = symbol(BUILD / "ladybug-enemy-runtime.map", "frame_render_impl")
    stop_pc = symbol(BUILD / "ladybug.map", "main_render")

    baseline = BUILD / "perf-baseline.sna"
    capture_snapshot(baseline, frame_pc, 20)

    static = BUILD / "perf-four-static.sna"
    patch_snapshot(
        baseline,
        static,
        COMMON_PATCHES + [
            "A477=FF", "A47F=FF", "A487=FF", "A48F=FF",
        ],
        [f"A470={ENEMY_TABLE}"],
    )
    hydrated = BUILD / "perf-four-hydrated.sna"
    capture_snapshot(hydrated, frame_pc, 5, static)

    horizontal = BUILD / "perf-four-horizontal.sna"
    patch_snapshot(hydrated, horizontal, moving_patch((1, 1, 3, 3)))
    capture_trace(horizontal, BUILD / "perf-four-horizontal.raw.trace", stop_pc, 7)

    vertical = BUILD / "perf-four-vertical.sna"
    patch_snapshot(hydrated, vertical, moving_patch((0, 0, 2, 2)))
    capture_trace(vertical, BUILD / "perf-four-vertical.raw.trace", stop_pc, 5)
    vertical_a = BUILD / "perf-four-vertical-a.sna"
    patch_snapshot(
        vertical,
        vertical_a,
        ["008F=00", "0090=01"],
    )
    capture_trace(
        vertical_a,
        BUILD / "perf-four-vertical-a.raw.trace",
        stop_pc,
        3,
    )

    capture_trace(baseline, BUILD / "perf-player.raw.trace", stop_pc, 8)

    animation = BUILD / "perf-animation.sna"
    patch_snapshot(
        hydrated,
        animation,
        moving_patch((1, 1, 3, 3)) + ["0055=01"],
    )
    capture_trace(animation, BUILD / "perf-animation.raw.trace", stop_pc, 4)

    popup = BUILD / "perf-popup.sna"
    patch_snapshot(
        hydrated,
        popup,
        ["0051=1E", "0052=02", "0053=05", "0080=01", "0055=40"],
    )
    capture_trace(popup, BUILD / "perf-popup.raw.trace", stop_pc, 4)

    for owner, front, back in (("a", 1, 0), ("b", 0, 1)):
        death = BUILD / f"perf-death-{owner}.sna"
        patch_snapshot(
            hydrated,
            death,
            [
                "003A=00", "004D=02", "004E=0D", "0062=02",
                "0060=00", "0087=00", "007F=80", "0080=00",
                "A901=00", "AA01=00", "A9A8=00", "AAA8=00",
                f"008F={front:02X}", f"0090={back:02X}",
            ],
        )
        capture_trace(
            death,
            BUILD / f"perf-death-{owner}.raw.trace",
            stop_pc,
            1,
        )
        death_reset = BUILD / f"perf-death-reset-{owner}.sna"
        patch_snapshot(
            hydrated,
            death_reset,
            [
                "003A=00", "004D=02", "004E=0D", "0062=02",
                "0060=01", "0087=08", "007F=80", "0080=00",
                f"008F={front:02X}", f"0090={back:02X}",
            ],
        )
        capture_trace(
            death_reset,
            BUILD / f"perf-death-reset-{owner}.raw.trace",
            stop_pc,
            1,
        )

    gate = BUILD / "perf-gate.sna"
    patch_snapshot(
        hydrated,
        gate,
        moving_patch((1, 1, 3, 3)) + [
            "0018=01", "0019=00",
            "0088=01", "0089=00", "008A=00", "008B=00",
            "008D=00", "008E=00", "A240=01",
        ],
    )
    capture_trace(gate, BUILD / "perf-gate.raw.trace", stop_pc, 3)

    print("performance capture: current-revision scenarios written to build/")


if __name__ == "__main__":
    main()
