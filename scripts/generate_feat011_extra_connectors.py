#!/usr/bin/env python3
"""Generate the twelve source-controlled EXTRA reserve-life route connectors."""

from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import NoReturn

MAP_WIDTH = 40
MAP_HEIGHT = 24
TILE_WIDTH = 8
TILE_HEIGHT = 8
MARKER_GID = 545
GID_MASK = 0x0FFFFFFF
FLIP_H = 0x80000000
FLIP_V = 0x40000000
FLIP_D = 0x20000000
HEX_ROTATE_120 = 0x10000000
SHARED_ENDPOINT = (240, 88)
ENTRY_CELL = (19, 1)
TURN_COLUMN = 29
SLOT_COLUMNS = (33, 35, 37)
SLOT_ROWS_TOP_TO_BOTTOM = (16, 18, 20, 22)
CONNECTOR_GROUP = "EXTRA Life Connectors"
CONNECTOR_GROUP_ID = 8
CONNECTOR_OBJECT_ID_BASE = 1001
COORDINATE_SPACE = (
    "CoCo screen pixels; Tiled polyline vertices are object-local and add the object x/y to form screen positions."
)
PATH_ROLE = "Shared EXTRA route; final vertex is the common start for reserve-slot connectors."


def fail(message: str) -> NoReturn:
    raise ValueError(message)


def _root_and_contract(source: str) -> ET.Element:
    try:
        root = ET.fromstring(source)
    except ET.ParseError as exc:
        fail(f"invalid TMX XML: {exc}")
    if root.tag != "map" or root.get("orientation") != "orthogonal":
        fail("expected an orthogonal Tiled map")
    if (int(root.get("width", "-1")) != MAP_WIDTH or
            int(root.get("height", "-1")) != MAP_HEIGHT or
            int(root.get("tilewidth", "-1")) != TILE_WIDTH or
            int(root.get("tileheight", "-1")) != TILE_HEIGHT):
        fail("map dimensions or 8x8 screen-pixel tile size changed")
    props = {
        node.get("name"): node.get("value")
        for node in root.findall("./properties/property")
    }
    if props.get("path-coordinate-space") != COORDINATE_SPACE:
        fail("path-coordinate-space metadata differs from the approved contract")
    if props.get("path-role") != PATH_ROLE:
        fail("path-role metadata differs from the approved contract")
    for node in root.findall("./layer") + root.findall("./objectgroup"):
        if (node.get("id") == str(CONNECTOR_GROUP_ID) and
                node.get("name") != CONNECTOR_GROUP):
            fail(f"Tiled layer id {CONNECTOR_GROUP_ID} is already owned")
    connector_ids = {str(CONNECTOR_OBJECT_ID_BASE + slot) for slot in range(12)}
    for group in root.findall("./objectgroup"):
        if group.get("name") == CONNECTOR_GROUP:
            continue
        for obj in group.findall("object"):
            if obj.get("id") in connector_ids:
                fail(f"Tiled object id {obj.get('id')} is already owned")
    return root


def _absolute_shared_endpoint(root: ET.Element) -> tuple[int, int]:
    groups = [node for node in root.findall("objectgroup")
              if node.get("name") == "Ladybug Path"]
    if len(groups) != 1:
        fail("expected exactly one Ladybug Path object group")
    objects = [node for node in groups[0].findall("object")
               if node.get("name") == "EXTRA Shared Route"]
    if len(objects) != 1:
        fail("expected exactly one EXTRA Shared Route object")
    obj = objects[0]
    polyline = obj.find("polyline")
    if polyline is None:
        fail("EXTRA Shared Route has no polyline")
    points = polyline.get("points", "").split()
    if len(points) < 2:
        fail("EXTRA Shared Route has fewer than two vertices")
    try:
        parts = [point.split(",") for point in points]
        if any(len(point) != 2 for point in parts):
            fail("EXTRA Shared Route vertex must contain exactly x,y")
        origin_x_value = float(obj.get("x", "0"))
        origin_y_value = float(obj.get("y", "0"))
        if (origin_x_value != int(origin_x_value) or
                origin_y_value != int(origin_y_value)):
            fail("EXTRA Shared Route object origin must use integer screen pixels")
        origin_x = int(origin_x_value)
        origin_y = int(origin_y_value)
        vertices = [tuple(int(float(value)) for value in point) for point in parts]
    except (ValueError, TypeError) as exc:
        fail(f"EXTRA Shared Route contains a non-integer coordinate: {exc}")
    if any(float(value) != int(float(value)) for point in parts for value in point):
        fail("EXTRA Shared Route contains a fractional coordinate")
    if any(x1 != x2 and y1 != y2
           for (x1, y1), (x2, y2) in zip(vertices, vertices[1:])):
        fail("EXTRA Shared Route contains a diagonal leg")
    last_x, last_y = vertices[-1]
    endpoint = (origin_x + last_x, origin_y + last_y)
    if endpoint != SHARED_ENDPOINT:
        fail(f"shared route endpoint is {endpoint}; expected {SHARED_ENDPOINT}")
    return endpoint


def _marker_layer(root: ET.Element) -> tuple[list[int], int, int]:
    layers = [node for node in root.findall("layer")
              if node.get("name") == "CoCo Event Sprite Locations"]
    if len(layers) != 1:
        fail("expected exactly one CoCo Event Sprite Locations tile layer")
    layer = layers[0]
    width = int(layer.get("width", "-1"))
    height = int(layer.get("height", "-1"))
    data = layer.find("data")
    if data is None or data.get("encoding") != "csv":
        fail("marker layer must use CSV-encoded tile data")
    cells = [int(value.strip()) for value in (data.text or "").replace("\n", "").split(",")
             if value.strip()]
    if width != MAP_WIDTH or height != MAP_HEIGHT or len(cells) != width * height:
        fail("marker-layer dimensions or cell count differ from the map")
    return cells, width, height


def _cell_gid(cells: list[int], width: int, cell: tuple[int, int], label: str) -> int:
    x, y = cell
    if not 0 <= x < width or not 0 <= y < MAP_HEIGHT:
        fail(f"{label} cell {cell} lies outside the map")
    encoded = cells[y * width + x]
    gid = encoded & GID_MASK
    if gid != MARKER_GID:
        fail(f"{label} cell {cell} uses GID {gid}; expected marker GID {MARKER_GID}")
    return encoded


def _facing(encoded_gid: int) -> str:
    if encoded_gid & HEX_ROTATE_120:
        fail("orthogonal marker uses Tiled's hexagonal rotation flag")
    # The source marker tile faces north. Tiled applies the diagonal swap,
    # then horizontal and vertical flips to its direction vector.
    dx, dy = 0, -1
    if encoded_gid & FLIP_D:
        dx, dy = dy, dx
    if encoded_gid & FLIP_H:
        dx = -dx
    if encoded_gid & FLIP_V:
        dy = -dy
    return {(0, -1): "north", (1, 0): "east",
            (0, 1): "south", (-1, 0): "west"}.get((dx, dy), "invalid")


def _validate_markers(root: ET.Element) -> None:
    cells, width, _ = _marker_layer(root)
    entry = _cell_gid(cells, width, ENTRY_CELL, "top entry")
    if _facing(entry) != "south":
        fail("top entry marker at (19,1) must face down/South")
    for row in SLOT_ROWS_TOP_TO_BOTTOM:
        turn = _cell_gid(cells, width, (TURN_COLUMN, row), f"turn row {row}")
        if _facing(turn) != "east":
            fail(f"left-of-HUD turn marker at (29,{row}) must face right/East")
        for column in SLOT_COLUMNS:
            slot = _cell_gid(cells, width, (column, row), f"reserve slot ({column},{row})")
            if _facing(slot) != "east":
                fail(f"reserve marker at ({column},{row}) must face right/East")


def connector_points(slot: int, endpoint: tuple[int, int] = SHARED_ENDPOINT) -> tuple[tuple[int, int], ...]:
    if not 0 <= slot < 12:
        fail(f"reserve slot index {slot} is outside 0..11")
    row = slot // 3
    column = slot % 3
    target = (272 + 16 * column, 176 - 16 * row)
    if endpoint[0] != 240:
        fail("shared endpoint x-coordinate must align with the four turn markers")
    return endpoint, (endpoint[0], target[1]), target


def _group_xml(newline: str) -> str:
    rows = [
        f'<objectgroup id="{CONNECTOR_GROUP_ID}" name="{CONNECTOR_GROUP}">'
    ]
    for slot in range(12):
        points = " ".join(f"{x},{y}" for x, y in connector_points(slot))
        rows.append(
            f' <object id="{CONNECTOR_OBJECT_ID_BASE + slot}" '
            f'name="slot-{slot:02d}" x="0" y="0">'
            f'<polyline points="{points}"/></object>'
        )
    rows.append("</objectgroup>")
    return newline.join(rows)


def _replace_group(source: str, group: str) -> str:
    pattern = re.compile(
        r'<objectgroup\b(?=[^>]*\bname=["\']EXTRA Life Connectors["\'])[^>]*>.*?</objectgroup>',
        re.DOTALL,
    )
    matches = list(pattern.finditer(source))
    if len(matches) > 1:
        fail("map contains duplicate EXTRA Life Connectors groups")
    if matches:
        match = matches[0]
        return source[:match.start()] + group + source[match.end():]
    path_group = re.search(
        r'<objectgroup\b(?=[^>]*\bname=["\']Ladybug Path["\'])[^>]*>.*?</objectgroup>',
        source,
        re.DOTALL,
    )
    if path_group is None:
        fail("cannot locate Ladybug Path group for generated-group insertion")
    newline = "\r\n" if "\r\n" in source else "\n"
    insertion = newline + " " + group
    return source[:path_group.end()] + insertion + source[path_group.end():]


def prepare_map(source: str) -> str:
    root = _root_and_contract(source)
    endpoint = _absolute_shared_endpoint(root)
    _validate_markers(root)
    generated = _replace_group(source, _group_xml("\r\n" if "\r\n" in source else "\n"))
    generated_root = _root_and_contract(generated)
    if _absolute_shared_endpoint(generated_root) != endpoint:
        fail("generated-group update changed the authored shared route")
    _validate_markers(generated_root)
    groups = [node for node in generated_root.findall("objectgroup")
              if node.get("name") == CONNECTOR_GROUP]
    if len(groups) != 1:
        fail("generated output does not contain exactly one connector group")
    objects = groups[0].findall("object")
    if len(objects) != 12:
        fail("generated output does not contain exactly twelve connectors")
    for slot, obj in enumerate(objects):
        expected = connector_points(slot)
        polyline = obj.find("polyline")
        actual = tuple(tuple(int(part) for part in point.split(","))
                       for point in (polyline.get("points", "").split()
                                     if polyline is not None else []))
        if obj.get("name") != f"slot-{slot:02d}" or actual != expected:
            fail(f"generated connector slot-{slot:02d} differs from its route oracle")
        if any(x1 != x2 and y1 != y2
               for (x1, y1), (x2, y2) in zip(actual, actual[1:])):
            fail(f"generated connector slot-{slot:02d} contains a diagonal leg")
    return generated


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--map", type=Path, required=True)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--write", action="store_true")
    action.add_argument("--check", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    original = args.map.read_bytes()
    try:
        source = original.decode("utf-8")
        expected = prepare_map(source).encode("utf-8")
    except (UnicodeError, ValueError) as exc:
        print(f"FEAT-011 connector source error: {exc}", file=sys.stderr)
        return 2
    if args.check:
        if original != expected:
            print("FEAT-011 connectors are absent or differ from the map oracle", file=sys.stderr)
            return 1
        print("FEAT-011 connectors match the authored route and marker contract")
        return 0
    if original != expected:
        args.map.write_bytes(expected)
    print(f"wrote {args.map}: only the EXTRA Life Connectors group was generated")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
