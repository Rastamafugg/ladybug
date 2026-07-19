#!/usr/bin/env python3
"""Derive Ladybug's static 24x24 semantic maze from the MAME capture."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import deque
from pathlib import Path


WIDTH = 24
HEIGHT = 24
EXPECTED_RAW_SHA256 = "d8129bb9f57ce51b0355101115af7eab538b854d31771f6f51917fa072f686f3"
DOT_CODE = 229
BLANK_CODE = 255
HORIZONTAL_GATE_ANCHOR = 57
VERTICAL_GATE_ANCHOR = 64

NAV_N = 0x01
NAV_E = 0x02
NAV_S = 0x04
NAV_W = 0x08
NAV_GATE = 0x10
NAV_NEST = 0x20
NAV_PERIMETER = 0x40

# The stable MAME frame contains seven 2x2 background-character overlays for
# stage objects.  Each replacement is the visible maze character beneath that
# overlay, determined by separating the object's non-maze pens from the
# repeated wall/blank pattern around it.
OVERLAY_BASE_CODES = {
    90: BLANK_CODE,
    91: BLANK_CODE,
    96: BLANK_CODE,
    98: BLANK_CODE,
    99: BLANK_CODE,
    100: 49,
    103: BLANK_CODE,
    111: BLANK_CODE,
    113: BLANK_CODE,
    114: 49,
    115: 49,
    117: 49,
    118: 50,
    134: 50,
    138: 50,
    141: 49,
    143: 49,
    146: 50,
    149: BLANK_CODE,
    158: 50,
    160: 50,
    163: BLANK_CODE,
}

HORIZONTAL_FOOTPRINT = ((0, 0), (-1, 1), (0, 1), (1, 1))
VERTICAL_FOOTPRINT = ((0, 0), (1, -1), (1, 0), (1, 1))

# The central two-cell release lane is the captured nest navigation region.
NEST_CELLS = ((12, 11), (12, 12))

# The stable capture contains stage objects over these otherwise blank
# navigation nodes. They are ordinary dot-bearing placement candidates in the
# clean maze; randomized skulls and bonuses replace their dots at stage load.
OBJECT_CANDIDATE_CELLS = {
    (10, 2), (12, 2), (12, 8), (18, 10),
    (2, 12), (10, 12), (22, 16), (6, 18),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--capture", type=Path, default=Path("assets/arcade/maze_capture.json")
    )
    parser.add_argument(
        "--raw", type=Path, default=Path("assets/arcade/maze_capture.bin")
    )
    parser.add_argument(
        "--output", type=Path, default=Path("assets/arcade/maze.json")
    )
    parser.add_argument(
        "--include", type=Path, default=Path("build/ladybug_maze.inc")
    )
    return parser.parse_args()


def require_grid(name: str, value: object) -> list[list[int]]:
    if not isinstance(value, list) or len(value) != HEIGHT:
        raise ValueError(f"{name}: expected {HEIGHT} rows")
    if any(not isinstance(row, list) or len(row) != WIDTH for row in value):
        raise ValueError(f"{name}: expected {WIDTH} columns per row")
    if any(type(cell) is not int for row in value for cell in row):
        raise ValueError(f"{name}: all cells must be integers")
    return value


def normalize_capture(codes: list[list[int]], attributes: list[list[int]]):
    base_codes: list[list[int]] = []
    base_attributes: list[list[int]] = []
    for y in range(HEIGHT):
        code_row: list[int] = []
        attr_row: list[int] = []
        for x in range(WIDTH):
            code = codes[y][x]
            if code in OVERLAY_BASE_CODES:
                code = OVERLAY_BASE_CODES[code]
                attribute = 0
            else:
                attribute = attributes[y][x]
            code_row.append(code)
            attr_row.append(attribute)
        base_codes.append(code_row)
        base_attributes.append(attr_row)
    return base_codes, base_attributes


def derive_walkable(codes: list[list[int]]) -> set[tuple[int, int]]:
    walkable = {(x, y) for y in range(2, 23, 2) for x in range(2, 23, 2)}
    walkable.update(
        (x, y)
        for y in range(2, 23, 2)
        for x in range(3, 22, 2)
        if codes[y][x] in (BLANK_CODE, HORIZONTAL_GATE_ANCHOR)
    )
    walkable.update(
        (x, y)
        for y in range(3, 22, 2)
        for x in range(2, 23, 2)
        if codes[y][x] in (BLANK_CODE, VERTICAL_GATE_ANCHOR)
    )
    return walkable


def derive_gates(codes: list[list[int]]) -> list[dict[str, object]]:
    gates: list[dict[str, object]] = []
    for y in range(HEIGHT):
        for x in range(WIDTH):
            code = codes[y][x]
            if code == HORIZONTAL_GATE_ANCHOR:
                orientation = "horizontal"
                footprint_id = 0
                offsets = HORIZONTAL_FOOTPRINT
                pivot = [x, y + 1]
            elif code == VERTICAL_GATE_ANCHOR:
                orientation = "vertical"
                footprint_id = 1
                offsets = VERTICAL_FOOTPRINT
                pivot = [x + 1, y]
            else:
                continue
            cells = [[x + dx, y + dy] for dx, dy in offsets]
            if any(cx < 0 or cx >= WIDTH or cy < 0 or cy >= HEIGHT for cx, cy in cells):
                raise ValueError(f"gate at {x},{y} has an out-of-bounds footprint")
            gates.append(
                {
                    "id": len(gates),
                    "anchor": [x, y],
                    "anchor_offset": y * WIDTH + x,
                    "footprint_id": footprint_id,
                    "initial_orientation": orientation,
                    "pivot": pivot,
                    "affected_cells": cells,
                    "rotation_cells": [
                        [pivot[0], pivot[1] - 1],
                        [pivot[0] - 1, pivot[1]],
                        [pivot[0], pivot[1]],
                        [pivot[0] + 1, pivot[1]],
                        [pivot[0], pivot[1] + 1],
                    ],
                }
            )
    if len(gates) != 20:
        raise ValueError(f"expected 20 gates, derived {len(gates)}")
    if sum(gate["initial_orientation"] == "horizontal" for gate in gates) != 10:
        raise ValueError("expected 10 initially horizontal gates")
    if sum(gate["initial_orientation"] == "vertical" for gate in gates) != 10:
        raise ValueError("expected 10 initially vertical gates")
    return gates


def connected_size(cells: set[tuple[int, int]]) -> int:
    if not cells:
        return 0
    remaining = set(cells)
    queue = deque([remaining.pop()])
    count = 0
    while queue:
        x, y = queue.popleft()
        count += 1
        for neighbor in ((x, y - 1), (x + 1, y), (x, y + 1), (x - 1, y)):
            if neighbor in remaining:
                remaining.remove(neighbor)
                queue.append(neighbor)
    if remaining:
        raise ValueError(f"navigation has disconnected regions: {len(remaining)} cells")
    return count


def derive_styles(
    codes: list[list[int]], attributes: list[list[int]]
) -> tuple[list[dict[str, object]], list[list[int]], list[list[int]]]:
    clean_blank = (BLANK_CODE, 0)
    pairs = {
        (codes[y][x], attributes[y][x])
        for y in range(HEIGHT)
        for x in range(WIDTH)
        if codes[y][x] != DOT_CODE
    }
    ordered = [clean_blank] + sorted(pairs - {clean_blank}, key=lambda item: (item[1], item[0]))
    if len(ordered) > 128:
        raise ValueError(f"visual style count {len(ordered)} exceeds 128")
    style_ids = {pair: index for index, pair in enumerate(ordered)}
    styles: list[dict[str, object]] = []
    for style_id, (code, attribute) in enumerate(ordered):
        style: dict[str, object] = {
            "id": style_id,
            "clean": {"code": code, "attribute": attribute},
            "dotted": None,
        }
        if (code, attribute) == clean_blank:
            style["dotted"] = {"code": DOT_CODE, "attribute": 2}
        styles.append(style)

    maze_cells: list[list[int]] = []
    dot_mask: list[list[int]] = []
    for y in range(HEIGHT):
        cell_row: list[int] = []
        dot_row: list[int] = []
        for x in range(WIDTH):
            dot = codes[y][x] == DOT_CODE or (x, y) in OBJECT_CANDIDATE_CELLS
            pair = clean_blank if dot else (codes[y][x], attributes[y][x])
            cell_row.append(style_ids[pair] | (0x80 if dot else 0))
            dot_row.append(1 if dot else 0)
        maze_cells.append(cell_row)
        dot_mask.append(dot_row)
    return styles, maze_cells, dot_mask


def derive_navigation(
    walkable: set[tuple[int, int]], gates: list[dict[str, object]]
) -> list[list[int]]:
    gate_cells = {
        tuple(cell) for gate in gates for cell in gate["affected_cells"]  # type: ignore[index]
    }
    nest = set(NEST_CELLS)
    if not nest <= walkable:
        raise ValueError("nest cells must be walkable")
    perimeter = {
        (x, y)
        for y in range(HEIGHT)
        for x in range(WIDTH)
        if x in (0, WIDTH - 1) or y in (0, HEIGHT - 1)
    }
    rows: list[list[int]] = []
    directions = ((0, -1, NAV_N), (1, 0, NAV_E), (0, 1, NAV_S), (-1, 0, NAV_W))
    for y in range(HEIGHT):
        row: list[int] = []
        for x in range(WIDTH):
            value = 0
            if (x, y) in walkable:
                for dx, dy, bit in directions:
                    if (x + dx, y + dy) in walkable:
                        value |= bit
            if (x, y) in gate_cells:
                value |= NAV_GATE
            if (x, y) in nest:
                value |= NAV_NEST
            if (x, y) in perimeter:
                value |= NAV_PERIMETER
            row.append(value)
        rows.append(row)

    # The capture contains only each gate's initial orientation. Add the
    # reciprocal external edges for every possible passage segment so that a
    # player can leave a segment after rotating it. Runtime gate-state parity
    # decides whether the north/south or west/east passage pair is active.
    passage_segments = (
        (0, -1, ((1, 0, NAV_E, NAV_W), (-1, 0, NAV_W, NAV_E))),
        (-1, 0, ((0, -1, NAV_N, NAV_S), (0, 1, NAV_S, NAV_N))),
        (0, 1, ((1, 0, NAV_E, NAV_W), (-1, 0, NAV_W, NAV_E))),
        (1, 0, ((0, -1, NAV_N, NAV_S), (0, 1, NAV_S, NAV_N))),
    )
    for gate in gates:
        pivot_x, pivot_y = gate["pivot"]  # type: ignore[misc]
        for passage_dx, passage_dy, edges in passage_segments:
            passage_x = pivot_x + passage_dx
            passage_y = pivot_y + passage_dy
            for dx, dy, bit, reciprocal in edges:
                neighbor_x = passage_x + dx
                neighbor_y = passage_y + dy
                if (neighbor_x, neighbor_y) not in walkable:
                    raise ValueError(
                        f"gate {gate['id']} passage exits into a wall at "
                        f"{neighbor_x},{neighbor_y}"
                    )
                rows[passage_y][passage_x] |= bit
                rows[neighbor_y][neighbor_x] |= reciprocal

    opposites = ((NAV_N, 0, -1, NAV_S), (NAV_E, 1, 0, NAV_W))
    for y in range(HEIGHT):
        for x in range(WIDTH):
            for bit, dx, dy, opposite in opposites:
                if rows[y][x] & bit:
                    nx, ny = x + dx, y + dy
                    if not (0 <= nx < WIDTH and 0 <= ny < HEIGHT):
                        raise ValueError(f"navigation exits grid at {x},{y}")
                    if not rows[ny][nx] & opposite:
                        raise ValueError(f"non-reciprocal navigation at {x},{y}")
    return rows


def format_fcb(values: list[int]) -> str:
    return "        fcb     " + ",".join(f"${value:02X}" for value in values)


def render_include(document: dict[str, object]) -> str:
    stats = document["statistics"]
    lines = [
        "; Generated by scripts/derive_maze.py. Do not edit.",
        "; Source: assets/arcade/maze_capture.bin + maze_capture.json",
        "",
        f"MAZE_WIDTH          equ     {WIDTH}",
        f"MAZE_HEIGHT         equ     {HEIGHT}",
        f"MAZE_STYLE_COUNT    equ     {stats['style_count']}",  # type: ignore[index]
        f"MAZE_DOT_COUNT      equ     {stats['dot_count']}",  # type: ignore[index]
        f"MAZE_GATE_COUNT     equ     {stats['gate_count']}",  # type: ignore[index]
        "",
        "; bits 0-6 style ID; bit 7 initial dot",
        "maze_cells",
    ]
    lines.extend(format_fcb(row) for row in document["maze_cells"])  # type: ignore[arg-type]
    lines.extend(["", "; bits 0-3 N/E/S/W; bit4 gate; bit5 nest; bit6 perimeter", "maze_nav"])
    lines.extend(format_fcb(row) for row in document["maze_nav"])  # type: ignore[arg-type]
    lines.extend(["", "; gate owner ID+1 for each cell in a gate's five-cell rotation cross", "maze_gate_owner"])
    lines.extend(format_fcb(row) for row in document["gate_owner"])  # type: ignore[arg-type]
    lines.extend(["", "; pivot x, pivot y, initial state (0=horizontal, 1=vertical)", "maze_gates"])
    for gate in document["gates"]:  # type: ignore[assignment]
        orientation = 0 if gate["initial_orientation"] == "horizontal" else 1
        lines.append(f"        fcb     ${gate['pivot'][0]:02X},${gate['pivot'][1]:02X},${orientation:02X}")
    lines.extend(
        [
            "",
            "; Initial gate footprint offsets as signed dx,dy byte pairs.",
            "gate_footprints",
            "        fcb     4,$00,$00,$FF,$01,$00,$01,$01,$01",
            "        fcb     4,$00,$00,$01,$FF,$01,$00,$01,$01",
            "",
        ]
    )
    return "\n".join(lines)


def write_if_changed(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return
    with path.open("w", encoding="utf-8", newline="\n") as output:
        output.write(content)


def main() -> int:
    args = parse_args()
    raw = args.raw.read_bytes()
    raw_sha256 = hashlib.sha256(raw).hexdigest()
    if len(raw) != 2048 or raw_sha256 != EXPECTED_RAW_SHA256:
        raise ValueError("raw MAME capture size or SHA-256 does not match the approved source")
    capture = json.loads(args.capture.read_text(encoding="utf-8"))
    if capture.get("mapping", {}).get("coco_maze_rows_inclusive") != [2, 25]:
        raise ValueError("capture must use the complete maze at visible rows 2-25")
    codes = require_grid("coco_maze_codes", capture.get("coco_maze_codes"))
    attributes = require_grid("coco_maze_attributes", capture.get("coco_maze_attributes"))
    codes, attributes = normalize_capture(codes, attributes)
    gates = derive_gates(codes)
    walkable = derive_walkable(codes)
    connected = connected_size(walkable)
    styles, maze_cells, dot_mask = derive_styles(codes, attributes)
    maze_nav = derive_navigation(walkable, gates)
    gate_owner = [[0 for _ in range(WIDTH)] for _ in range(HEIGHT)]
    for gate in gates:
        for x, y in gate["rotation_cells"]:
            if gate_owner[y][x]:
                raise ValueError(f"gate rotation crosses overlap at {x},{y}")
            gate_owner[y][x] = gate["id"] + 1
    dots = [[x, y] for y in range(HEIGHT) for x in range(WIDTH) if dot_mask[y][x]]
    if len(dots) != 117 or any(tuple(dot) not in walkable for dot in dots):
        raise ValueError("expected 117 placement dots, all on walkable navigation nodes")
    affected = [tuple(cell) for gate in gates for cell in gate["affected_cells"]]
    if len(set(affected)) != 80:
        raise ValueError("the 20 four-cell gate footprints must not overlap")
    for gate in gates:
        x, y = gate["anchor"]
        expected_mask = 0x0A if gate["initial_orientation"] == "horizontal" else 0x05
        if maze_nav[y][x] & 0x0F != expected_mask:
            raise ValueError(f"gate {gate['id']} navigation disagrees with its orientation")

    document: dict[str, object] = {
        "schema": "ladybug-semantic-maze-v1",
        "provenance": {
            "capture_schema": capture["schema"],
            "raw_sha256": raw_sha256,
            "visible_rows_inclusive": [2, 25],
            "overlay_base_codes": {str(k): v for k, v in sorted(OVERLAY_BASE_CODES.items())},
        },
        "dimensions": [WIDTH, HEIGHT],
        "encoding": {
            "maze_cells": "bits 0-6 style ID; bit 7 initial dot",
            "maze_nav": "bits 0-3 N/E/S/W; bit 4 gate; bit 5 nest; bit 6 perimeter",
        },
        "base_codes": codes,
        "base_attributes": attributes,
        "styles": styles,
        "maze_cells": maze_cells,
        "maze_nav": maze_nav,
        "gate_owner": gate_owner,
        "dots": dots,
        "nest_cells": [list(cell) for cell in NEST_CELLS],
        "perimeter_cells": [
            [x, y]
            for y in range(HEIGHT)
            for x in range(WIDTH)
            if x in (0, WIDTH - 1) or y in (0, HEIGHT - 1)
        ],
        "gate_footprints": [
            {"id": 0, "name": "horizontal-down", "offsets": [list(v) for v in HORIZONTAL_FOOTPRINT]},
            {"id": 1, "name": "vertical-right", "offsets": [list(v) for v in VERTICAL_FOOTPRINT]},
        ],
        "gates": gates,
        "statistics": {
            "style_count": len(styles),
            "dot_count": len(dots),
            "gate_count": len(gates),
            "walkable_cell_count": connected,
            "nest_cell_count": len(NEST_CELLS),
            "perimeter_cell_count": 2 * WIDTH + 2 * (HEIGHT - 2),
            "compiled_table_bytes": WIDTH * HEIGHT * 2 + len(gates) * 4 + 18,
        },
    }
    write_if_changed(args.output, json.dumps(document, indent=2) + "\n")
    write_if_changed(args.include, render_include(document))
    print(
        f"maze: {len(styles)} styles, {len(dots)} dots, {len(gates)} gates, "
        f"{connected} walkable cells -> {args.output}, {args.include}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
