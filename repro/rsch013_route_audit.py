#!/usr/bin/env python3
"""Reproduce the BUG-045 offline splice comparisons without editing a route."""
import collections
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from verify_bug012_demo_walk import MOVEMENT, can_move

maze = json.loads((ROOT / "assets/arcade/maze.json").read_text())
walk = json.loads((ROOT / "assets/arcade/demo_walk.json").read_text())
original = walk["action_text"]
dot_set = {tuple(cell) for cell in maze["dots"]}


def simulate(actions):
    gates = [0 if gate["initial_orientation"] == "horizontal" else 1
             for gate in maze["gates"]]
    x, y = walk["start_cell"]
    visited = {(x, y)}
    edges = []
    for index, action in enumerate(actions):
        start = (x, y)
        direction = "NESW".index(action)
        dx, dy = MOVEMENT[direction]
        for step in range(2):
            if not can_move(maze, gates, x, y, direction):
                raise AssertionError((index, step, "first", (x, y)))
            if not can_move(maze, gates, x, y, direction):
                raise AssertionError((index, step, "second", (x, y)))
            x += dx
            y += dy
            visited.add((x, y))
        edges.append(tuple(sorted((start, (x, y)))))
    counts = collections.Counter(edges)
    return {"actions": len(actions), "collectibles": len(visited & dot_set),
            "end_cell": [x, y], "final_gate_states": gates,
            "repeated_action_edges": sum(count - 1 for count in counts.values()),
            "repeated_edges": {str(edge) for edge, count in counts.items() if count > 1}}


baseline = simulate(original)
assert baseline["actions"] == 147 and baseline["collectibles"] == 117
assert baseline["end_cell"] == [6, 2]
cases = [
    ("NWSSWWNNEEN", 9, 18, "Shifts repeated edges to the left of the spawner and violates the current return-detour provenance rule."),
    ("NWSSSENENW", 9, 15, "Returns to the anchor but repeats more of the earlier lower-right path."),
]
report = {"schema": "ladybug-rsch013-route-audit-v1",
          "baseline_rom_sha256": hashlib.sha256((ROOT / "build/ladybug.rom").read_bytes()).hexdigest(),
          "baseline_walk_sha256": walk["walk_sha256"],
          "method": "Offline action-level maze and gate simulation; no production file changed",
          "baseline": {key: value for key, value in baseline.items() if key != "repeated_edges"},
          "rejected_candidates": []}
for replacement, start, stop, reason in cases:
    candidate = simulate(original[:start] + replacement + original[stop:])
    assert candidate["collectibles"] == 117 and candidate["end_cell"] == [6, 2]
    assert candidate["final_gate_states"] == baseline["final_gate_states"]
    report["rejected_candidates"].append({
        "replacement": replacement, "replaces_action_offsets": [start, stop - 1],
        **{key: value for key, value in candidate.items() if key != "repeated_edges"},
        "new_repeated_edges": sorted(candidate["repeated_edges"] - baseline["repeated_edges"]),
        "reason": reason})
report["ready_gap"] = "No accepted route avoids a new visible retrace; provenance and cold capacity need a revised design."
output = ROOT / "repro/rsch013-route-audit.json"
output.write_text(json.dumps(report, indent=2) + "\n")
print("BUG-045 offline candidate audit: 117/117 coverage, both candidates rejected")
