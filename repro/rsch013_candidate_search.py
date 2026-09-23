#!/usr/bin/env python3
"""Bounded offline search for a BUG-045 prefix replacing actions 0..17."""
import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from verify_bug012_demo_walk import MOVEMENT, can_move

maze = json.loads((ROOT / "assets/arcade/maze.json").read_text())
walk = json.loads((ROOT / "assets/arcade/demo_walk.json").read_text())
original = walk["action_text"]
dots = {tuple(cell) for cell in maze["dots"]}
initial_gates = tuple(0 if gate["initial_orientation"] == "horizontal" else 1
                      for gate in maze["gates"])
deadline = time.monotonic() + 25


def step(cell, states, direction):
    gates = list(states)
    x, y = cell
    passed = []
    for _ in range(2):
        if not can_move(maze, gates, x, y, direction):
            return None
        if not can_move(maze, gates, x, y, direction):
            return None
        dx, dy = MOVEMENT[direction]
        x += dx
        y += dy
        passed.append((x, y))
    return (x, y), tuple(gates), passed


def trace(actions, start=(12, 18), gates=initial_gates):
    cells = {start}
    edges = []
    cell = start
    for action in actions:
        result = step(cell, gates, "NESW".index(action))
        if result is None:
            return None
        end, gates, passed = result
        edges.append(tuple(sorted((cell, end))))
        cells.update(passed)
        cell = end
    return cell, gates, cells, edges


baseline = trace(original)
assert baseline and len(baseline[2] & dots) == 117
cutoff = 25
prefix = trace(original[:cutoff])
suffix = trace(original[cutoff:], prefix[0], prefix[1])
assert prefix and suffix
target, target_gates = prefix[:2]
required = dots - suffix[2]
suffix_edges = Counter(suffix[3])
baseline_repeats = {edge for edge, count in Counter(baseline[3]).items() if count > 1}
reported_edges = set(baseline[3][12:15])
expanded = 0
found = None


def visit(cell, gates, cells, edges, path, limit):
    global expanded, found
    expanded += 1
    if expanded % 10000 == 0 and time.monotonic() >= deadline:
        raise TimeoutError(f"search expanded {expanded} states")
    if cell == target and gates == target_gates and required <= cells:
        candidate = trace(path + original[cutoff:])
        if candidate and len(candidate[2] & dots) == 117 and candidate[0] == (6, 2):
            repeats = {edge for edge, count in Counter(candidate[3]).items() if count > 1}
            if not repeats - baseline_repeats and not repeats & reported_edges:
                found = path
                return True
    if len(path) >= limit:
        return False
    for d, letter in enumerate("NESW"):
        result = step(cell, gates, d)
        if result is None:
            continue
        end, next_gates, passed = result
        edge = tuple(sorted((cell, end)))
        if ((edge in edges or suffix_edges[edge])
                and (edge not in baseline_repeats or edge in reported_edges)):
            continue
        if visit(end, next_gates, cells | set(passed), edges | {edge}, path + letter, limit):
            return True
    return False


try:
    for limit in range(10, 41):
        if visit(tuple(walk["start_cell"]), initial_gates, {tuple(walk["start_cell"])},
                 set(), "", limit):
            break
except TimeoutError as exc:
    print(str(exc))
report = {"target": target, "cutoff_action": cutoff, "required_dots": len(required),
          "expanded": expanded, "candidate": found, "search_limit_at_stop": limit,
          "deadline_seconds": 25,
          "interpretation": "No candidate within completed depth limits; not an impossibility proof"}
(ROOT / "repro/rsch013-route-search.json").write_text(json.dumps(report, indent=2) + "\n")
print(json.dumps(report))
