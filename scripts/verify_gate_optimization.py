#!/usr/bin/env python3
"""Verify the controlled gate replay/composition optimization profile."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
BUDGET = 29_666
TRACE_RE = re.compile(r"^[0-9a-f]{4}\|.* dt=(\d+)$")
MAP_RE = re.compile(r"^Symbol: (\w+) .* = ([0-9A-Fa-f]+)$")
BASELINE = {
    "A": {"active_cycles": 96_919, "gate_cycles": 66_027, "gate_calls": 1},
    "B": {"active_cycles": 172_304, "gate_cycles": 140_296, "gate_calls": 2},
}


def symbols() -> dict[str, str]:
    result = {}
    for line in (BUILD / "ladybug-enemy-runtime.map").read_text(
        encoding="utf-8"
    ).splitlines():
        match = MAP_RE.match(line)
        if match:
            result[match.group(1)] = match.group(2).lower().zfill(4)
    required = {
        "frame_render_impl",
        "gate_compose_impl",
        "draw_gate_entities",
        "draw_entities",
    }
    missing = required - result.keys()
    if missing:
        raise ValueError("missing profile symbols: " + ", ".join(sorted(missing)))
    return result


def load_trace(owner: str, frame_entry: str) -> list[str]:
    path = BUILD / f"gate-opt-owner-{owner.lower()}.trace"
    lines = [
        line
        for line in path.read_text(encoding="ascii").splitlines()
        if TRACE_RE.match(line)
    ]
    if not lines or not lines[0].startswith(frame_entry + "|"):
        raise ValueError(f"{path}: trace does not begin at frame_render_impl")
    if sum(line.startswith(frame_entry + "|") for line in lines) != 1:
        raise ValueError(f"{path}: expected exactly one controlled frame")
    return lines


def profile(owner: str, names: dict[str, str]) -> dict[str, object]:
    lines = load_trace(owner, names["frame_render_impl"])
    cycles = [int(TRACE_RE.match(line).group(1)) // 8 for line in lines]
    cycles[0] = 9
    sync_indexes = {index for index, line in enumerate(lines) if "| 13 " in line}
    active = sum(cycles) - sum(cycles[index] for index in sync_indexes)
    pcs = [line[:4] for line in lines]
    gate_entries = [
        index for index, pc in enumerate(pcs) if pc == names["gate_compose_impl"]
    ]
    gate_cycles = 0
    gate_instructions = 0
    for entry in gate_entries:
        call = entry - 1
        return_pc = f"{int(pcs[call], 16) + 3:04x}"
        end = next(
            index
            for index in range(entry + 1, len(lines))
            if pcs[index] == return_pc
        )
        gate_cycles += sum(cycles[call:end])
        gate_instructions += end - call

    if len(gate_entries) != 1:
        raise ValueError(f"owner {owner}: expected one coalesced gate composition")
    if pcs.count(names["draw_gate_entities"]) != 1:
        raise ValueError(f"owner {owner}: gate entity filter did not execute once")
    if pcs.count(names["draw_entities"]):
        raise ValueError(f"owner {owner}: global entity redraw remains")

    baseline = BASELINE[owner]
    return {
        "instructions": len(lines),
        "active_instructions": len(lines) - len(sync_indexes),
        "active_cycles": active,
        "budget_margin_cycles": BUDGET - active,
        "passes_strict_budget": active < BUDGET,
        "gate_composition": {
            "calls": len(gate_entries),
            "instructions": gate_instructions,
            "cycles": gate_cycles,
        },
        "improvement": {
            "frame_cycles_saved": baseline["active_cycles"] - active,
            "frame_percent": round(
                (baseline["active_cycles"] - active)
                * 100
                / baseline["active_cycles"],
                1,
            ),
            "gate_cycles_saved": baseline["gate_cycles"] - gate_cycles,
            "gate_percent": round(
                (baseline["gate_cycles"] - gate_cycles)
                * 100
                / baseline["gate_cycles"],
                1,
            ),
            "gate_calls_removed": baseline["gate_calls"] - len(gate_entries),
        },
    }


def main() -> None:
    runtime = (ROOT / "src" / "enemy_runtime.s").read_text(encoding="utf-8")
    if "jsr     draw_gate_transition" in runtime:
        report = json.loads(
            (BUILD / "gate-optimized-profile.json").read_text(encoding="ascii")
        )
        expected = {
            "A": (36_738, 9_419),
            "B": (46_131, 17_565),
        }
        for owner, (frame_cycles, gate_cycles) in expected.items():
            values = report["owners"][owner]
            if (
                values["active_cycles"] != frame_cycles or
                values["gate_composition"]["cycles"] != gate_cycles
            ):
                raise ValueError(
                    f"owner {owner}: archived pre-delta baseline changed"
                )
        print(
            "gate baseline: archived replay/entity-filter profile "
            "A 36738/9419, B 46131/17565 cycles verified"
        )
        return
    names = symbols()
    owners = {owner: profile(owner, names) for owner in ("A", "B")}
    report = {
        "captured": "2026-07-27",
        "hardware_budget_cycles": BUDGET,
        "scenario": (
            "four horizontal roaming enemies; A draws gate-0 diagonal; "
            "B coalesces the queued diagonal and draws the same gate final"
        ),
        "optimization": (
            "same-gate final replay coalescing plus gate-union entity filtering"
        ),
        "baseline": BASELINE,
        "owners": owners,
        "artifacts": {
            "owner_a_trace": "build/gate-opt-owner-a.trace",
            "owner_b_trace": "build/gate-opt-owner-b.trace",
        },
    }
    (BUILD / "gate-optimized-profile.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="ascii"
    )
    for owner, values in owners.items():
        gate = values["gate_composition"]
        print(
            f"gate {owner}: {values['active_cycles']} active cycles, "
            f"{gate['cycles']} gate cycles, {gate['calls']} composition"
        )


if __name__ == "__main__":
    main()
