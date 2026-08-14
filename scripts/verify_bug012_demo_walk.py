#!/usr/bin/env python3
"""Verify BUG-012 route provenance, gate legality, and full maze coverage."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RAW_ROUTE_SHA256 = "69d29e65ad0199f28e0e0d955fa4e5cf24077201d8cc189cfde6916047bcf7f4"
WALK_SHA256 = "c880f79e1c7e4366cd7421f93875940690bf3fbf6d655ae8ed0a0a3fed44557b"
BACKBONE_SHA256 = "bbe843387cf29a486aca0cb0a09555012570c224e679f2741eda12aed1cb264c"
MOVEMENT = ((0, -1), (1, 0), (0, 1), (-1, 0))
ENTRY_MASKS = (0x04, 0x08, 0x01, 0x02)
EXPECTED_DETOURS = (
    ((16, 12), 9, "NWSNES"),
    ((16, 2), 24, "WE"),
    ((8, 18), 70, "NENNSWSSWWEE"),
    ((2, 8), 108, "ENENWESSEEWNWWWS"),
)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def can_move(
    maze: dict[str, object], gate_states: list[int],
    x: int, y: int, direction: int,
) -> bool:
    """Model current 6809 can_move, including legal endpoint gate rotation."""
    dx, dy = MOVEMENT[direction]
    target_x, target_y = x + dx, y + dy
    if not (0 <= target_x < 24 and 0 <= target_y < 24):
        return False
    gate_owner = maze["gate_owner"][target_y][target_x]
    if not gate_owner:
        return bool(maze["maze_nav"][target_y][target_x] & ENTRY_MASKS[direction])

    gate_id = gate_owner - 1
    gate = maze["gates"][gate_id]
    pivot_x, pivot_y = gate["pivot"]
    state = gate_states[gate_id]
    if not state & 1:
        if (target_x == pivot_x and target_y in (pivot_y - 1, pivot_y + 1)
                and direction in (1, 3)):
            return True
    elif (target_y == pivot_y and target_x in (pivot_x - 1, pivot_x + 1)
          and direction in (0, 2)):
        return True

    if not state & 1:
        if direction not in (0, 2) or target_y != pivot_y or target_x == pivot_x:
            return False
        gate_states[gate_id] = 1 if target_x < pivot_x else 3
        return True
    if direction not in (1, 3) or target_x != pivot_x or target_y == pivot_y:
        return False
    gate_states[gate_id] = 0 if target_y < pivot_y else 2
    return True


def main() -> None:
    route = json.loads((ROOT / "assets/arcade/demo_route.json").read_text(encoding="ascii"))
    walk = json.loads((ROOT / "assets/arcade/demo_walk.json").read_text(encoding="ascii"))
    maze = json.loads((ROOT / "assets/arcade/maze.json").read_text(encoding="ascii"))

    raw_bytes = bytes(route["bytes"])
    if (len(raw_bytes) != 188 or raw_bytes[-1] != 0xFF or
            digest(raw_bytes) != RAW_ROUTE_SHA256 or
            route["route_sha256"] != RAW_ROUTE_SHA256):
        raise SystemExit("BUG-012 walk proof: immutable arcade route differs")
    if (walk["source_route_sha256"] != RAW_ROUTE_SHA256 or
            walk["source_program_sha256"] != route["program_sha256"] or
            walk["source_action_count"] != route["action_count"]):
        raise SystemExit("BUG-012 walk proof: arcade provenance link differs")

    stored = bytes(walk["actions"])
    if (len(stored) != 148 or stored[-1] != 0xFF or
            digest(stored) != WALK_SHA256 or walk["walk_sha256"] != WALK_SHA256):
        raise SystemExit("BUG-012 walk proof: stored walk identity differs")
    action_text = walk["action_text"]
    if (len(action_text) != 147 or
            bytes("NESW".index(value) for value in action_text) != stored[:-1]):
        raise SystemExit("BUG-012 walk proof: action text differs from stored ordinals")

    detours = tuple(
        (tuple(item["anchor"]), item["action_offset"], item["actions"])
        for item in walk["detours"]
    )
    if detours != EXPECTED_DETOURS:
        raise SystemExit("BUG-012 walk proof: exact detours differ")
    backbone = action_text
    for _anchor, offset, actions in reversed(detours):
        if backbone[offset:offset + len(actions)] != actions:
            raise SystemExit(f"BUG-012 walk proof: detour differs at action {offset}")
        backbone = backbone[:offset] + backbone[offset + len(actions):]
    backbone_bytes = bytes("NESW".index(value) for value in backbone)
    if (len(backbone) != 111 or walk["arcade_node_count"] != 112 or
            digest(backbone_bytes) != BACKBONE_SHA256 or
            walk["arcade_backbone_sha256"] != BACKBONE_SHA256 or
            backbone != walk["arcade_backbone_action_text"]):
        raise SystemExit("BUG-012 walk proof: 112-node arcade backbone differs")

    gate_states = [
        0 if gate["initial_orientation"] == "horizontal" else 1
        for gate in maze["gates"]
    ]
    x, y = walk["start_cell"]
    visited = {(x, y)}
    boundaries = [{"cell": [x, y], "gate_states": gate_states.copy()}]
    records = []
    for action_index, direction in enumerate(stored[:-1]):
        start = [x, y]
        gate_states_before = gate_states.copy()
        calls = []
        for unit_step in range(2):
            first = can_move(maze, gate_states, x, y, direction)
            second = can_move(maze, gate_states, x, y, direction)
            calls.append([first, second])
            if not first or not second:
                raise SystemExit(
                    "BUG-012 walk proof: blocked edge at "
                    f"action {action_index}, unit {unit_step}, cell {(x, y)}"
                )
            dx, dy = MOVEMENT[direction]
            x, y = x + dx, y + dy
            visited.add((x, y))
        records.append({
            "action": action_index,
            "direction": "NESW"[direction],
            "start": start,
            "end": [x, y],
            "can_move_calls": calls,
            "gate_states_before": gate_states_before,
            "gate_states_after": gate_states.copy(),
        })
        boundaries.append({"cell": [x, y], "gate_states": gate_states.copy()})

    if [x, y] != walk["end_cell"] or [x, y] != [6, 2]:
        raise SystemExit("BUG-012 walk proof: final cell differs")
    collectible_cells = {
        (cell_x, cell_y)
        for cell_y, row in enumerate(maze["maze_cells"])
        for cell_x, value in enumerate(row)
        if value & 0x80
    }
    collected = visited & collectible_cells
    remaining = collectible_cells - visited
    if len(collectible_cells) != 117 or len(collected) != 117 or remaining:
        raise SystemExit(
            f"BUG-012 walk proof: coverage {len(collected)}/117, "
            f"remaining {sorted(remaining)}"
        )

    detour_evidence = []
    for anchor, offset, actions in detours:
        end = offset + len(actions)
        before, after = boundaries[offset], boundaries[end]
        if tuple(before["cell"]) != anchor or before["cell"] != after["cell"]:
            raise SystemExit(f"BUG-012 walk proof: detour {offset} does not return")
        if before["gate_states"] != after["gate_states"]:
            raise SystemExit(f"BUG-012 walk proof: detour {offset} changes gate state")
        detour_evidence.append({
            "anchor": list(anchor), "action_offset": offset, "actions": actions,
            "gate_states_before": before["gate_states"],
            "gate_states_after": after["gate_states"],
        })

    report = {
        "schema": "ladybug-bug012-demo-walk-proof-v1",
        "result": "pass",
        "raw_route_sha256": RAW_ROUTE_SHA256,
        "walk_sha256": WALK_SHA256,
        "backbone_sha256": BACKBONE_SHA256,
        "arcade_nodes": 112,
        "actions": len(records),
        "start_cell": walk["start_cell"],
        "end_cell": walk["end_cell"],
        "visited_maze_cells": len(visited),
        "collectible_cells": len(collectible_cells),
        "collected_cells": len(collected),
        "remaining_cells": [],
        "detours": detour_evidence,
        "final_gate_states": gate_states,
        "action_records": records,
    }
    output = ROOT / "build/bug012-demo-walk.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="ascii")
    print(
        "BUG-012 walk proof: 147/147 legal node actions, 117/117 collectible "
        f"cells, zero remaining, end (6,2), SHA-256 {WALK_SHA256}"
    )


if __name__ == "__main__":
    main()
