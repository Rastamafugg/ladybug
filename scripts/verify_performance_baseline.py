#!/usr/bin/env python3
"""Verify and summarize current-revision complete-frame performance traces."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
HARDWARE_BUDGET = 29_666
ENGINEERING_TARGET = 27_000
TRACE_RE = re.compile(r"^[0-9a-f]{4}\|.* dt=(\d+)$")
MAP_RE = re.compile(r"^Symbol: (\w+) .* = ([0-9A-Fa-f]+)$")


def symbols(path: Path) -> dict[str, str]:
    result = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = MAP_RE.match(line)
        if match:
            result[match.group(1)] = match.group(2).lower().zfill(4)
    return result


def trace_sections(path: Path, frame_pc: str) -> list[dict[str, object]]:
    lines = [
        line
        for line in path.read_text(encoding="ascii", errors="strict").splitlines()
        if TRACE_RE.match(line)
    ]
    # XRoar 1.10 reports the first restored-snapshot instruction at PC $0000,
    # while decoding and executing the saved frame_render_impl instruction.
    if lines and lines[0].startswith("0000|"):
        lines[0] = frame_pc + lines[0][4:]
    starts = [index for index, line in enumerate(lines) if line.startswith(frame_pc + "|")]
    if not starts:
        raise ValueError(f"{path}: frame_render_impl was not traced")
    sections = []
    for position, start in enumerate(starts):
        end = starts[position + 1] if position + 1 < len(starts) else len(lines)
        section = lines[start:end]
        cycles = [int(TRACE_RE.match(line).group(1)) // 8 for line in section]
        cycles[0] = 9
        sync = sum(cycle for cycle, line in zip(cycles, section) if "| 13 " in line)
        sections.append(
            {
                "instructions": len(section),
                "active_cycles": sum(cycles) - sync,
                "sync_wait_cycles": sync,
                "pcs": [line[:4] for line in section],
            }
        )
    return sections


def measured(section: dict[str, object], owner: str) -> dict[str, object]:
    active = int(section["active_cycles"])
    return {
        "owner": owner,
        "instructions": section["instructions"],
        "active_cycles": active,
        "hardware_margin_cycles": HARDWARE_BUDGET - active,
        "engineering_margin_cycles": ENGINEERING_TARGET - active,
        "passes_hardware_budget": active < HARDWARE_BUDGET,
        "passes_engineering_target": active <= ENGINEERING_TARGET,
    }


def alternating_sections(path: Path, frame_pc: str, initial_back: int) -> list[dict[str, object]]:
    result = []
    for index, section in enumerate(trace_sections(path, frame_pc)):
        interval = measured(
            section,
            "A" if (initial_back + index) % 2 == 0 else "B",
        )
        interval["pcs"] = section["pcs"]
        result.append(interval)
    return result


def without_pcs(value: dict[str, object]) -> dict[str, object]:
    return {key: item for key, item in value.items() if key != "pcs"}


def hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    enemy_symbols = symbols(BUILD / "ladybug-enemy-runtime.map")
    frame_pc = enemy_symbols["frame_render_impl"]
    required = {
        "rub_horizontal",
        "rub_vertical",
        "rub_full",
        "compose_enemy_zone",
        "gate_compose_impl",
    }
    missing = required - enemy_symbols.keys()
    if missing:
        raise ValueError("missing baseline symbols: " + ", ".join(sorted(missing)))

    horizontal = alternating_sections(
        BUILD / "perf-four-horizontal.raw.trace", frame_pc, 0
    )
    for interval in horizontal:
        pcs = interval["pcs"]
        interval["horizontal_captures"] = pcs.count(enemy_symbols["rub_horizontal"])
        interval["full_captures"] = pcs.count(enemy_symbols["rub_full"])

    vertical = alternating_sections(BUILD / "perf-four-vertical.raw.trace", frame_pc, 0)
    vertical += alternating_sections(
        BUILD / "perf-four-vertical-a.raw.trace", frame_pc, 1
    )
    for interval in vertical:
        pcs = interval["pcs"]
        interval["vertical_captures"] = pcs.count(enemy_symbols["rub_vertical"])
        interval["full_captures"] = pcs.count(enemy_symbols["rub_full"])

    player = alternating_sections(BUILD / "perf-player.raw.trace", frame_pc, 0)
    animation = alternating_sections(BUILD / "perf-animation.raw.trace", frame_pc, 0)
    animation = [
        interval
        for interval in animation
        if interval["pcs"].count(enemy_symbols["compose_enemy_zone"])
    ]
    popup = alternating_sections(BUILD / "perf-popup.raw.trace", frame_pc, 0)[-2:]
    death = [
        measured(trace_sections(BUILD / f"perf-death-{owner.lower()}.raw.trace", frame_pc)[0], owner)
        for owner in ("A", "B")
    ]
    death_reset = [
        measured(trace_sections(
            BUILD / f"perf-death-reset-{owner.lower()}.raw.trace", frame_pc
        )[0], owner)
        for owner in ("A", "B")
    ]
    gate = alternating_sections(BUILD / "perf-gate.raw.trace", frame_pc, 0)[:2]
    for interval in gate:
        interval["gate_compositions"] = interval["pcs"].count(
            enemy_symbols["gate_compose_impl"]
        )

    horizontal_movement = [
        interval
        for interval in horizontal
        if interval["horizontal_captures"] == 4 and interval["full_captures"] == 0
    ]
    vertical_movement = [
        interval
        for interval in vertical
        if interval["vertical_captures"] == 4 and interval["full_captures"] == 0
    ]
    discontinuities = [
        interval
        for interval in horizontal + vertical
        if interval["full_captures"]
    ]

    report = {
        "captured": date.today().isoformat(),
        "source_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "source_sha256": {
            path.as_posix(): hash_file(ROOT / path)
            for path in (
                Path("src/main.s"),
                Path("src/enemy_runtime.s"),
                Path("scripts/build_screen.py"),
                Path("scripts/build_sparse_sprites.py"),
            )
        },
        "measurement_contract": (
            "complete frame_render_impl-to-next-render-call active interval; "
            "only identified SYNC waits excluded"
        ),
        "hardware_budget_cycles": HARDWARE_BUDGET,
        "engineering_target_cycles": ENGINEERING_TARGET,
        "scenarios": {
            "player": [without_pcs(item) for item in player],
            "horizontal_four_enemy": [without_pcs(item) for item in horizontal_movement],
            "vertical_four_enemy": [without_pcs(item) for item in vertical_movement],
            "movement_discontinuity": [without_pcs(item) for item in discontinuities],
            "movement_plus_nest_animation": [without_pcs(item) for item in animation],
            "blue_x5_popup": [without_pcs(item) for item in popup],
            "death_angel": death,
            "death_reset_with_nest": death_reset,
            "gate_diagonal_final": [without_pcs(item) for item in gate],
        },
        "acceptance": {
            "current_revision_complete_frame_evidence": True,
            "all_steady_paths_below_hardware_budget": False,
            "all_normal_paths_at_engineering_target": False,
        },
        "artifacts": {
            "horizontal": "build/perf-four-horizontal.raw.trace",
            "vertical": [
                "build/perf-four-vertical.raw.trace",
                "build/perf-four-vertical-a.raw.trace",
            ],
            "player": "build/perf-player.raw.trace",
            "animation": "build/perf-animation.raw.trace",
            "popup": "build/perf-popup.raw.trace",
            "death": [
                "build/perf-death-a.raw.trace",
                "build/perf-death-b.raw.trace",
            ],
            "death_reset_with_nest": [
                "build/perf-death-reset-a.raw.trace",
                "build/perf-death-reset-b.raw.trace",
            ],
            "gate": "build/perf-gate.raw.trace",
        },
    }

    output = BUILD / "performance-baseline.json"
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="ascii")
    summary = {
        name: max(item["active_cycles"] for item in values)
        for name, values in report["scenarios"].items()
        if values
    }
    print("performance baseline: " + ", ".join(f"{k}={v}" for k, v in summary.items()))


if __name__ == "__main__":
    main()
