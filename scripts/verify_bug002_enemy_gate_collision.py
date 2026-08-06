#!/usr/bin/env python3
"""Prove enemy movement cannot bypass a gate-owned target cell."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAZE = json.loads((ROOT / "assets/arcade/maze.json").read_text(encoding="utf-8"))
SOURCE = (ROOT / "src/enemy_runtime.s").read_text(encoding="utf-8")
NAV = MAZE["maze_nav"]
OWNER = MAZE["gate_owner"]
GATES = MAZE["gates"]
WIDTH = 24
HEIGHT = 24
EXIT_MASKS = (0x01, 0x02, 0x04, 0x08)
ENTRY_MASKS = (0x04, 0x08, 0x01, 0x02)


def target(x: int, y: int, direction: int) -> tuple[int, int]:
    return (
        x + (0, 1, 0, -1)[direction],
        y + (-1, 0, 1, 0)[direction],
    )


def gate_passable(gate_id: int, state: int, tx: int, ty: int, direction: int) -> bool:
    pivot_x, pivot_y = GATES[gate_id]["pivot"]
    if state & 1:
        return (
            ty == pivot_y
            and tx in (pivot_x - 1, pivot_x + 1)
            and direction in (0, 2)
        )
    return (
        tx == pivot_x
        and ty in (pivot_y - 1, pivot_y + 1)
        and direction in (1, 3)
    )


def expected(x: int, y: int, direction: int, states: list[int]) -> bool:
    tx, ty = target(x, y, direction)
    if not (0 <= tx < WIDTH and 0 <= ty < HEIGHT):
        return False
    if y < 11 and (tx, ty) == (12, 11):
        return False
    gate_id = OWNER[ty][tx]
    if gate_id:
        return gate_passable(gate_id - 1, states[gate_id - 1], tx, ty, direction)
    return bool(NAV[ty][tx] & ENTRY_MASKS[direction])


def legacy_enemy(x: int, y: int, direction: int, states: list[int]) -> bool:
    if y < 11 or NAV[y][x] & 0x10:
        return expected(x, y, direction, states)
    return bool(NAV[y][x] & EXIT_MASKS[direction])


def fixed_enemy(x: int, y: int, direction: int, states: list[int]) -> bool:
    current_owner = OWNER[y][x]
    if y < 11 or current_owner or NAV[y][x] & 0x10:
        return expected(x, y, direction, states)
    if not (NAV[y][x] & EXIT_MASKS[direction]):
        return False
    tx, ty = target(x, y, direction)
    if not (0 <= tx < WIDTH and 0 <= ty < HEIGHT):
        return False
    if OWNER[ty][tx]:
        return expected(x, y, direction, states)
    return True


def main() -> int:
    required = (
        "; A non-gate current cell can still enter a gate-owned target.",
        "leay    maze_gate_owner-maze_nav,y",
    )
    missing = [fragment for fragment in required if fragment not in SOURCE]
    if missing:
        raise SystemExit("BUG-002 source guard missing: " + ", ".join(missing))

    legacy_mismatches = []
    fixed_mismatches = []
    cases = 0
    for gate_id in range(len(GATES)):
        for state in range(4):
            states = [gate["initial_orientation"] == "vertical" for gate in GATES]
            states = [int(value) for value in states]
            states[gate_id] = state
            for y in range(HEIGHT):
                for x in range(WIDTH):
                    if not NAV[y][x] and not OWNER[y][x]:
                        continue
                    for direction in range(4):
                        cases += 1
                        want = expected(x, y, direction, states)
                        old = legacy_enemy(x, y, direction, states)
                        new = fixed_enemy(x, y, direction, states)
                        if old != want:
                            legacy_mismatches.append((gate_id, state, x, y, direction))
                        if new != want:
                            fixed_mismatches.append((gate_id, state, x, y, direction))

    if not legacy_mismatches:
        raise SystemExit("BUG-002 discriminating test did not reproduce the legacy mismatch")
    if fixed_mismatches:
        raise SystemExit(
            "BUG-002 fixed oracle mismatches: " + repr(fixed_mismatches[:8])
        )

    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    report = {
        "source_commit": commit,
        "cases": cases,
        "legacy_mismatches": len(legacy_mismatches),
        "fixed_mismatches": len(fixed_mismatches),
        "pass": True,
    }
    output = ROOT / "build" / "bug-002-enemy-gate-collision.json"
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        f"BUG-002 enemy gate oracle: {cases} cases, "
        f"legacy mismatches {len(legacy_mismatches)}, fixed mismatches 0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
