#!/usr/bin/env python3
"""Create the 40x24 CoCo screen map with centered maze and side HUD."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


SCREEN_WIDTH = 40
SCREEN_HEIGHT = 24
PANEL_WIDTH = 8
MAZE_WIDTH = 24
BLANK_CODE = 255

SPECIAL = (28, 25, 14, 12, 18, 10, 21)
EXTRA = (14, 33, 29, 27, 10)
MULTIPLIERS = (86, 2, 86, 3, 86, 5)
FIRST = (1, 28, 29)
TOP = (29, 24, 25)
CREDIT = (12, 27, 14, 13, 18, 29)
ZERO_SCORE = (0, 0, 0, 0, 0, 0)
LIFE_ICON = ((227, 228), (225, 226))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--maze",
        type=Path,
        default=Path("assets/arcade/maze.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("tiled/coco-screen.tmx"),
    )
    return parser.parse_args()


def rotated_sheet_gid(code: int) -> int:
    """Return the one-based GID in the counter-clockwise-rotated char sheet."""
    return (31 - (code % 32)) * 16 + (code // 32) + 1


def place_vertical(
    layer: list[list[int]], x: int, y: int, codes: tuple[int, ...]
) -> None:
    for offset, code in enumerate(codes):
        place(layer, x, y + offset, code)


def place(layer: list[list[int]], x: int, y: int, code: int) -> None:
    if not (0 <= x < SCREEN_WIDTH and 0 <= y < SCREEN_HEIGHT):
        raise ValueError(f"HUD tile outside 40x24 screen at {x},{y}")
    if PANEL_WIDTH <= x < PANEL_WIDTH + MAZE_WIDTH:
        raise ValueError(f"HUD tile overlaps maze at {x},{y}")
    if layer[y][x] != 0:
        raise ValueError(f"HUD tile placement overlaps another tile at {x},{y}")
    layer[y][x] = rotated_sheet_gid(code)


def place_life(layer: list[list[int]], x: int, y: int) -> None:
    for dy, row in enumerate(LIFE_ICON):
        for dx, code in enumerate(row):
            place(layer, x + dx, y + dy, code)


def csv_layer(rows: list[list[int]]) -> str:
    if len(rows) != SCREEN_HEIGHT or any(len(row) != SCREEN_WIDTH for row in rows):
        raise ValueError("layer must be 40 columns by 24 rows")
    text_rows = [",".join(str(value) for value in row) for row in rows]
    return ",\n".join(text_rows)


def build_layers(maze: dict[str, object]) -> tuple[list[list[int]], list[list[int]]]:
    codes = maze.get("base_codes")
    if not isinstance(codes, list) or len(codes) != MAZE_WIDTH:
        raise ValueError("semantic source must contain a 24x24 maze")
    if any(not isinstance(row, list) or len(row) != MAZE_WIDTH for row in codes):
        raise ValueError("semantic source must contain a 24x24 maze")

    blank_gid = rotated_sheet_gid(BLANK_CODE)
    background = [[blank_gid] * SCREEN_WIDTH for _ in range(SCREEN_HEIGHT)]
    for y, row in enumerate(codes):
        for x, code in enumerate(row):
            background[y][PANEL_WIDTH + x] = rotated_sheet_gid(int(code))

    hud = [[0] * SCREEN_WIDTH for _ in range(SCREEN_HEIGHT)]

    # Left: three arcade top-band labels rotated into descending columns.
    place_vertical(hud, 0, 1, SPECIAL)
    place_vertical(hud, 3, 1, EXTRA)
    place_vertical(hud, 6, 1, MULTIPLIERS)

    # Three captured 16x16 life icons below the vertical labels.
    for x in (0, 3, 6):
        place_life(hud, x, 10)

    # Right: essential bottom-band data. UNIVERSAL is intentionally omitted.
    place_vertical(hud, 33, 1, FIRST)
    place_vertical(hud, 35, 1, ZERO_SCORE)
    place_vertical(hud, 33, 9, TOP)
    place_vertical(hud, 35, 9, ZERO_SCORE)
    place_vertical(hud, 33, 17, CREDIT)
    place(hud, 35, 22, 0)

    return background, hud


def render_map(background: list[list[int]], hud: list[list[int]]) -> str:
    return f'''<?xml version="1.0" encoding="UTF-8"?>
<map version="1.10" tiledversion="1.12.2" orientation="orthogonal" renderorder="right-down" width="40" height="24" tilewidth="8" tileheight="8" infinite="0" nextlayerid="3" nextobjectid="1">
 <tileset firstgid="1" source="chars_raw2bpp.tsx"/>
 <layer id="1" name="Maze and Panel Background" width="40" height="24">
  <data encoding="csv">
{csv_layer(background)}
</data>
 </layer>
 <layer id="2" name="HUD Placeholders" width="40" height="24">
  <data encoding="csv">
{csv_layer(hud)}
</data>
 </layer>
</map>
'''


def main() -> int:
    args = parse_args()
    maze = json.loads(args.maze.read_text(encoding="utf-8"))
    background, hud = build_layers(maze)
    content = render_map(background, hud)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as output:
        output.write(content)
    print(f"tiled: wrote 40x24 CoCo screen map to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
