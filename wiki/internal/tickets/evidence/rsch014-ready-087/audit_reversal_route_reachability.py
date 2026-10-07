#!/usr/bin/env python3
"""Offline reachability audit for the current natural BUG-087 fixture state."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import deque
from pathlib import Path


ROOT = Path(__file__).resolve().parents[5]
DEFAULT_SNAPSHOT = (ROOT / "wiki/internal/tickets/evidence/rsch014-ready-087/"
                    "current-root-legal-reversal-fixture-setup-candidate-v4-20261007.json")
sys.path.insert(0, str(ROOT / "scripts"))
import verify_bug002_enemy_gate_collision as oracle


def runtime_legal(x: int, y: int, direction: int, states: list[int]) -> bool:
    """Mirror enemy_direction_legal's upper slow path and lower fast path."""
    if y < 11:
        return oracle.expected(x, y, direction, states)
    if not (oracle.NAV[y][x] & oracle.EXIT_MASKS[direction]):
        return False
    tx, ty = oracle.target(x, y, direction)
    if not (0 <= tx < 24 and 0 <= ty < 24):
        return False
    return oracle.expected(x, y, direction, states) if oracle.OWNER[ty][tx] else True


def shortest_route(start: tuple[int, int, int], target: tuple[int, int, int],
                   states: list[int]) -> list[tuple[int, int, int]] | None:
    def legal(x: int, y: int, direction: int) -> bool:
        return runtime_legal(x, y, direction, states)

    def successors(node: tuple[int, int, int]):
        x, y, previous_direction = node
        reverse = previous_direction ^ 2
        choices = [direction for direction in range(4)
                   if direction != reverse and legal(x, y, direction)]
        if not choices and legal(x, y, reverse):
            choices = [reverse]
        offsets = ((0, -1), (1, 0), (0, 1), (-1, 0))
        return [(x + offsets[d][0], y + offsets[d][1], d) for d in choices]

    queue = deque([start])
    previous: dict[tuple[int, int, int], tuple[int, int, int] | None] = {start: None}
    while queue:
        node = queue.popleft()
        if node == target:
            result = []
            while node is not None:
                result.append(node)
                node = previous[node]  # type: ignore[assignment]
            return list(reversed(result))
        for successor in successors(node):
            if successor not in previous:
                previous[successor] = node
                queue.append(successor)
    return None


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", type=Path, default=DEFAULT_SNAPSHOT)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    snapshot_path = args.snapshot.resolve(strict=True)
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    record = snapshot.get("initial_enemy_records", [None])[0]
    gate_hex = snapshot.get("initial_gate_bytes_hex")
    if not isinstance(record, dict) or not isinstance(gate_hex, str) or len(gate_hex) != 40:
        raise ValueError("snapshot must retain slot0 and all 20 initial gate bytes")
    states = list(bytes.fromhex(gate_hex))
    if states[0] != 0:
        raise ValueError("reversal predecessor requires initial gate0=0")

    source_text = (ROOT / "src/enemy_runtime.s").read_text(encoding="utf-8")
    for required in ("cmpa    #11\n        blo     edl_slow",
                     "bne     edl_slow         ; target gate state must be authoritative",
                     "bcc     ecd_blocked"):
        if required not in source_text:
            raise RuntimeError("enemy movement source no longer matches this route model")
    start = (int(record["cell_x"]), int(record["cell_y"]), int(record["direction"]))
    target = (6, 4, 0)  # arrive at (6,4) northbound, then choose west at the aligned cell
    path = shortest_route(start, target, states)
    if path is None:
        raise RuntimeError("current slot0 state has no route to the northbound predecessor")

    west = runtime_legal(6, 4, 3, states)
    west_exit = runtime_legal(5, 4, 3, states)
    boundary_exits = [d for d in range(4) if runtime_legal(4, 4, d, states)]
    if not west or not west_exit or boundary_exits != [1]:
        raise RuntimeError("the predecessor cells no longer satisfy the approved reversal contract")

    receipt = {
        "schema": "bug087-reversal-route-reachability-20261007-v1",
        "ticket": "BUG-087",
        "kind": "offline source/maze reachability audit; no runtime acceptance",
        "source_sha256": digest(ROOT / "src/enemy_runtime.s"),
        "maze_sha256": digest(ROOT / "assets/arcade/maze.json"),
        "oracle_sha256": digest(ROOT / "scripts/verify_bug002_enemy_gate_collision.py"),
        "snapshot_sha256": digest(snapshot_path),
        "snapshot_file": snapshot_path.name,
        "candidate_rom_sha256": snapshot.get("rom_sha256"),
        "gate0": states[0],
        "slot0_start": {"cell": list(start[:2]), "direction": start[2]},
        "northbound_arrival": {"cell": [6, 4], "direction": 0,
                                "minimum_cell_transitions": len(path) - 1,
                                "route_states": [list(row) for row in path]},
        "west_turn_at_arrival": {"legal": west, "reverse_of_north": 2,
                                 "west_is_nonreverse": True},
        "approved_reversal_segment": {"cells": [[6, 4], [5, 4], [4, 4]],
                                       "west_legal_at_6_4_and_5_4": west and west_exit,
                                       "only_exit_at_4_4": boundary_exits,
                                       "east_is_reverse_of_west": True},
        "limits": ["existential route only; RNG sequence not simulated",
                   "no callback timing or finite-window guarantee",
                   "does not prove live movement or framebuffer displacement"],
        "runtime_launched": False,
        "status": "pass-offline-route-reachable",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
