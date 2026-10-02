#!/usr/bin/env python3
"""Audit a natural Part-1 dot-coverage route against the authored maze graph."""

from __future__ import annotations

import collections
import hashlib
import json
import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MAZE = ROOT / "assets/arcade/maze.json"
START = (5, 22)  # MAME player origin (41,208) mapped onto 8-pixel maze cells.
DIRECTIONS = (
    # MAME ROT270 makes cabinet Up advance raw-video/maze x by +1.
    (0, -1, 0x01, 0x04, "north"),
    (1, 0, 0x02, 0x08, "east"),
    (0, 1, 0x04, 0x01, "south"),
    (-1, 0, 0x08, 0x02, "west"),
)
CONTROL_FOR_DIRECTION = {"north": "left", "east": "up", "south": "right", "west": "down"}
FRAME_PER_CELL = 8
FIRST_MOVE_FRAME = 550


def shortest_paths(graph: dict[tuple[int, int], list[tuple[int, int]]], start):
    parent = {start: None}
    queue = collections.deque([start])
    while queue:
        node = queue.popleft()
        for neighbor in graph[node]:
            if neighbor not in parent:
                parent[neighbor] = node
                queue.append(neighbor)
    return parent


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan-out", type=Path)
    args = parser.parse_args()
    raw = MAZE.read_bytes()
    maze = json.loads(raw)
    nav = maze["maze_nav"]
    nodes = {
        (x, y)
        for y, row in enumerate(nav)
        for x, value in enumerate(row)
        if value & 0x0F
    }
    gates = {
        (x, y)
        for y, row in enumerate(nav)
        for x, value in enumerate(row)
        if value & 0x10
    }
    skulls = {
        (x, y)
        for y, row in enumerate(maze["base_codes"])
        for x, value in enumerate(row)
        if value == 63
    }
    dots = {tuple(point) for point in maze["dots"]}

    def make_graph(allowed: set[tuple[int, int]]):
        graph = {node: [] for node in allowed}
        for x, y in allowed:
            mask = nav[y][x] & 0x0F
            for dx, dy, bit, reverse, _name in DIRECTIONS:
                neighbor = (x + dx, y + dy)
                if (neighbor in allowed and mask & bit
                        and nav[neighbor[1]][neighbor[0]] & reverse):
                    graph[(x, y)].append(neighbor)
        return graph

    graph = make_graph(nodes - skulls)
    no_gate_graph = make_graph(nodes - gates)
    reached = shortest_paths(graph, START)
    no_gate_reached = shortest_paths(no_gate_graph, START)

    # Greedily visit the nearest unvisited dot with exact BFS paths. This is a
    # route-feasibility lower-cost audit, not a claim that the joystick plan
    # has been executed or that dynamic gates will accept every turn.
    remaining = set(dots)
    path = [START]
    current = START
    while remaining:
        parent = shortest_paths(graph, current)
        candidates = [dot for dot in remaining if dot in parent]
        if not candidates:
            break
        target = min(candidates, key=lambda point: (distance(parent, point), point))
        segment = unwind(parent, target)
        path.extend(segment[1:])
        current = target
        remaining.remove(target)

    edge_count = max(0, len(path) - 1)
    turns = sum(direction(path[i - 1], path[i]) != direction(path[i], path[i + 1])
                for i in range(1, len(path) - 1))
    gate_edges = sum(node in gates for node in path[1:])
    result = {
        "schema": "rsch014-b5-natural-maze-route-audit-v1",
        "maze_sha256": hashlib.sha256(raw).hexdigest(),
        "start_cell_xy": list(START),
        "start_basis": "retained gameplay_reference.json player origin x=41,y=208; screen transform x=8*cell_x+1,y=8*cell_y+32",
        "graph": {
            "nodes_with_edges": len(nodes),
            "gated_nodes": len(gates),
            "static_edges": sum(map(len, graph.values())) // 2,
            "reachable_nodes_from_start": len(reached),
            "reachable_dots_from_start": len(dots & reached.keys()),
            "dots_total": len(dots),
            "fixed_skull_cells_excluded": [list(point) for point in sorted(skulls)],
            "skull_avoiding_nodes": len(nodes - skulls),
            "nodes_without_gates": len(nodes - gates),
            "reachable_without_gates": len(no_gate_reached),
            "dots_reachable_without_gates": len(dots & no_gate_reached.keys()),
        },
        "route": {
        "method": "greedy nearest unvisited dot using shortest paths in authored static nav graph with fixed skull cells excluded",
            "visited_dots": len(dots) - len(remaining),
            "missing_dots": sorted([list(point) for point in remaining]),
            "grid_edges": edge_count,
            "estimated_mame_frames_at_1_pixel_per_frame_and_8_pixels_per_cell": edge_count * 8,
            "direction_changes": turns,
            "path_cells": [list(point) for point in path],
            "gate_cells_entered": gate_edges,
            "warning": "Static reachability does not prove dynamic gate timing, joystick turn acceptance, live enemy avoidance, or natural stage-clear behavior.",
        },
    }
    route_directions = [direction(path[index], path[index + 1])
                        for index in range(len(path) - 1)]
    actions = [
        {"frame": 300, "control": "coin1", "pressed": True},
        {"frame": 303, "control": "coin1", "pressed": False},
        {"frame": 360, "control": "start1", "pressed": True},
        {"frame": 365, "control": "start1", "pressed": False},
    ]
    active_control = None
    for edge, map_direction in enumerate(route_directions):
        control = CONTROL_FOR_DIRECTION[map_direction]
        frame = FIRST_MOVE_FRAME + edge * FRAME_PER_CELL
        if control != active_control:
            if active_control is not None:
                actions.append({"frame": frame, "control": active_control, "pressed": False})
            actions.append({"frame": frame, "control": control, "pressed": True})
            active_control = control
    if active_control is not None:
        actions.append({"frame": FIRST_MOVE_FRAME + edge_count * FRAME_PER_CELL,
                        "control": active_control, "pressed": False})
    actions.sort(key=lambda action: action["frame"])
    plan = {
        "description": "Natural Part-1 maze dot sweep from the retained start coordinate; generated from authored static maze_nav, then capture Part counter and enemy timer/rate bytes.",
        "route_basis": "repro/rsch014-B5/route_model.py",
        "actions": actions,
    }
    result["plan"] = {
        "path": str(args.plan_out) if args.plan_out else None,
        "first_move_frame": FIRST_MOVE_FRAME,
        "edge_interval_frames": FRAME_PER_CELL,
        "last_input_release_frame": FIRST_MOVE_FRAME + edge_count * FRAME_PER_CELL,
        "input_transitions": len(actions) - 4,
    }
    if args.plan_out:
        args.plan_out.parent.mkdir(parents=True, exist_ok=True)
        args.plan_out.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


def distance(parent, target):
    steps = 0
    node = target
    while parent[node] is not None:
        steps += 1
        node = parent[node]
    return steps


def unwind(parent, target):
    result = []
    node = target
    while node is not None:
        result.append(node)
        node = parent[node]
    result.reverse()
    return result


def direction(a, b):
    delta = (b[0] - a[0], b[1] - a[1])
    return next(name for dx, dy, _bit, _reverse, name in DIRECTIONS
                if delta == (dx, dy))


if __name__ == "__main__":
    main()
