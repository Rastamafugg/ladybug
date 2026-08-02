#!/usr/bin/env python3
"""Verify current-address complete gate intervals and report attribution."""

from __future__ import annotations

import json
import hashlib
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
BASELINE = {"A": 37968, "B": 39292}
TARGET = 27000
TRACE_RE = re.compile(r"^[0-9a-f]{4}\|.* dt=(\d+)$")
MAP_RE = re.compile(r"^Symbol: (\w+) .* = ([0-9A-Fa-f]+)$")


def symbols(path: Path) -> dict[str, str]:
    result = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = MAP_RE.match(line)
        if match:
            result[match.group(1)] = match.group(2).lower().zfill(4)
    return result


def sections(path: Path, frame_pc: str) -> list[tuple[list[str], list[int]]]:
    lines = [line for line in path.read_text(encoding="ascii").splitlines() if TRACE_RE.match(line)]
    if lines and lines[0].startswith("0000|"):
        lines[0] = frame_pc + lines[0][4:]
    starts = [index for index, line in enumerate(lines) if line.startswith(frame_pc + "|")]
    result = []
    for position, start in enumerate(starts):
        end = starts[position + 1] if position + 1 < len(starts) else len(lines)
        part = lines[start:end]
        cycles = [int(TRACE_RE.match(line).group(1)) // 8 for line in part]
        cycles[0] = 9
        result.append((part, cycles))
    return result


def calls(lines: list[str], cycles: list[int], entry: str) -> list[int]:
    pcs = [line[:4] for line in lines]
    result = []
    for index, pc in enumerate(pcs):
        if pc != entry or index == 0:
            continue
        return_pc = f"{int(pcs[index - 1], 16) + 3:04x}"
        try:
            end = pcs.index(return_pc, index + 1)
        except ValueError:
            continue
        result.append(sum(cycles[index - 1:end]))
    return result


def main() -> None:
    enemy = symbols(BUILD / "ladybug-enemy-runtime.map")
    resident = symbols(BUILD / "ladybug.map")
    names = {**resident, **enemy}
    wanted = (
        "framebuffer_prepare_back", "actor_closure_restore",
        "framebuffer_project_damage", "frame_render_background",
        "gate_compose_impl", "draw_gate_transition", "draw_gate_entities",
        "mark_gate_enemy_overlap", "actor_closure_draw", "rub_full",
        "rub_horizontal", "rub_vertical", "draw_enemy_fb",
    )
    report = []
    for owner, (lines, cycle_values) in zip(
        ("A", "B"), sections(BUILD / "perf-gate.raw.trace", enemy["frame_render_impl"])
    ):
        sync = sum(value for line, value in zip(lines, cycle_values) if "| 13 " in line)
        item = {"owner": owner, "active_cycles": sum(cycle_values) - sync}
        item["calls"] = {
            name: {"count": len(values), "cycles": values}
            for name in wanted
            if (values := calls(lines, cycle_values, names[name]))
        }
        item["baseline_cycles"] = BASELINE[owner]
        item["improvement_cycles"] = BASELINE[owner] - item["active_cycles"]
        item["target_margin_cycles"] = TARGET - item["active_cycles"]
        item["passes_target"] = item["active_cycles"] <= TARGET
        if item["calls"].get("gate_compose_impl", {}).get("count") != 1:
            raise ValueError(f"owner {owner} did not coalesce to one gate composition")
        if item["calls"].get("draw_gate_entities", {}).get("count") != 1:
            raise ValueError(f"owner {owner} did not use bounded entity selection")
        report.append(item)
    reversed_report = []
    for phase, (lines, cycle_values) in zip(
        ("diagonal/current", "final/pending projection"),
        sections(BUILD / "perf-gate-reversed.raw.trace", enemy["frame_render_impl"]),
    ):
        sync = sum(value for line, value in zip(lines, cycle_values) if "| 13 " in line)
        item = {
            "phase": phase,
            "starting_owner": "reversed (front=B, back=A)",
            "active_cycles": sum(cycle_values) - sync,
        }
        item["calls"] = {
            name: {"count": len(values), "cycles": values}
            for name in wanted
            if (values := calls(lines, cycle_values, names[name]))
        }
        item["target_margin_cycles"] = TARGET - item["active_cycles"]
        item["passes_target"] = item["active_cycles"] <= TARGET
        if item["calls"].get("gate_compose_impl", {}).get("count") != 1:
            raise ValueError(f"reversed {phase} did not coalesce to one gate composition")
        if item["calls"].get("draw_gate_entities", {}).get("count") != 1:
            raise ValueError(f"reversed {phase} did not use bounded entity selection")
        reversed_report.append(item)
    payload = BUILD / "ladybug-gate-transitions.bin"
    if payload.stat().st_size != 832:
        raise ValueError("generated six-stream gate payload changed size")
    output = {
        "measurement_contract": (
            "complete frame_render_impl-to-next-render-call active interval; "
            "only identified SYNC waits excluded; symbols resolved from current maps"
        ),
        "scenario": (
            "gate-0 diagonal on A, alternate-owner final projection on B; "
            "four horizontal enemies and one bounded overlapping static entity"
        ),
        "generated_cases": 168,
        "payload_bytes": payload.stat().st_size,
        "payload_sha256": hashlib.sha256(payload.read_bytes()).hexdigest(),
        "target_cycles": TARGET,
        "target_met": all(item["passes_target"] for item in report + reversed_report),
        "owners": report,
        "reversed_start_owner": reversed_report,
        "reversed_start_trace": "build/perf-gate-reversed.raw.trace",
    }
    (BUILD / "gate-performance.json").write_text(
        json.dumps(output, indent=2) + "\n", encoding="ascii"
    )
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
