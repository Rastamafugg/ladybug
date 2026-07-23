#!/usr/bin/env python3
"""Compile a layered 40x24 Tiled map into packed CoCo 3 screen data."""

from __future__ import annotations

import argparse
import json
import xml.etree.ElementTree as ET
from pathlib import Path


SCREEN_WIDTH = 40
SCREEN_HEIGHT = 24
TILE_SIZE = 8
FLIP_H = 0x80000000
FLIP_V = 0x40000000
FLIP_D = 0x20000000
GID_MASK = 0x0FFFFFFF
BLACK = 0
RED = 1
YELLOW = 2
BLUE = 3
PINK = 4
GREEN = 5
WHITE = 6
GREY = 7
LIGHT_GREEN = 8
PURPLE = 9
DARK_GREEN = 10
LIGHT_BLUE = 11
DARK_RED = 12
ORANGE = 13

# Canonical Universal RGB names expressed as CoCo 3 six-bit GIME values.
# Slots 14 and 15 are reserved until later levels require more colours.
PALETTE = (0x00, 0x26, 0x36, 0x19, 0x3D, 0x17, 0x3F, 0x38,
           0x3A, 0x39, 0x12, 0x3B, 0x24, 0x34, 0x00, 0x00)
PLAYER_PEN_MAP = (BLACK, DARK_RED, GREEN, YELLOW)
LIFE_PEN_MAP = (BLACK, GREEN, DARK_RED, YELLOW)


def sheet_code(row: int, column: int) -> int:
    """Resolve an RrCc PNG reference into the rotated ROM sprite order."""
    if not 0 <= row < 8 or not 0 <= column < 16:
        raise ValueError(f"sprite R{row}C{column} is outside the 8x16 sheet")
    return column * 8 + (7 - row)


def sheet_coordinates(code: int) -> tuple[int, int]:
    """Return the PNG-reference row and column for a ROM sprite code."""
    return 7 - (code % 8), code // 8


def char_sheet_code(row: int, column: int) -> int:
    """Resolve RrCc on the 16-column by 32-row rotated character PNG."""
    if not 0 <= row < 32 or not 0 <= column < 16:
        raise ValueError(f"character R{row}C{column} is outside the 32x16 sheet")
    return column * 32 + (31 - row)


PLAYER_CODES = tuple(sheet_code(row, 0) for row in (2, 3, 4, 3))
DEATH_CODES = (
    tuple(sheet_code(row, 7) for row in range(6, -1, -1)) +
    tuple(sheet_code(row, 10) for row in range(5, -1, -1)) +
    (sheet_code(7, 11),)
)
SCORE_CODES = (sheet_code(1, 6), sheet_code(0, 6), sheet_code(7, 7))
VEGETABLE_CODES = (
    tuple(sheet_code(row, 8) for row in range(7, -1, -1)) +
    tuple(sheet_code(row, 9) for row in range(7, -1, -1)) +
    (sheet_code(7, 10), sheet_code(6, 10))
)
ENEMY_CODE_SETS = (
    tuple(sheet_code(row, 1) for row in (4, 5, 6, 5)),
    (sheet_code(6, 2), sheet_code(7, 2),
     sheet_code(0, 1), sheet_code(7, 2)),
    tuple(sheet_code(row, 3) for row in (2, 3, 4, 3)),
    tuple(sheet_code(row, 2) for row in (0, 1, 2, 1)),
    tuple(sheet_code(row, 4) for row in (4, 5, 6, 5)),
    (sheet_code(6, 5), sheet_code(7, 5),
     sheet_code(0, 4), sheet_code(7, 5)),
    tuple(sheet_code(row, 5) for row in (0, 1, 2, 1)),
    tuple(sheet_code(row, 6) for row in (2, 3, 4, 3)),
)
ENEMY_CODES = tuple(code for group in ENEMY_CODE_SETS for code in group)
MULTIPLIER_CHAR_CODES = tuple(char_sheet_code(row, 6) for row in (5, 4, 2))

OBJECT_NAMES = ("skull", "heart", "A", "C", "E", "I", "L", "P", "R", "S", "T", "X")
# Exact four-character object composites from the arcade program table at
# main-ROM offset $0CA5.  The ROM order is bottom-right, top-right, top-left,
# bottom-left.  Codes below select the context-free variants of each quadrant.
OBJECT_CHAR_CODES = {
    "heart": (139, 113, 161, 98),
    "skull": (143, 115, 163, 99),
    "A": (119, 103, 155, 94),
    "E": (119, 101, 149, 91),
    "S": (119, 101, 145, 89),
    "P": (119, 103, 147, 90),
    "C": (119, 101, 151, 92),
    "I": (123, 105, 153, 93),
    "L": (127, 107, 151, 92),
    "X": (131, 109, 157, 95),
    "T": (135, 111, 159, 96),
    "R": (119, 103, 147, 97),
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--map", type=Path, required=True)
    parser.add_argument("--maze", type=Path, required=True)
    parser.add_argument("--chars", type=Path, required=True)
    parser.add_argument("--sprites", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resident-output", type=Path, required=True)
    parser.add_argument("--enemy-output", type=Path, required=True)
    return parser.parse_args()


def load_chars(path: Path) -> list[list[list[int]]]:
    document = json.loads(path.read_text(encoding="utf-8"))
    raw = document.get("characters", document) if isinstance(document, dict) else document
    if isinstance(raw, dict):
        raw = [raw[str(index)] for index in range(512)]
    if not isinstance(raw, list) or len(raw) != 512:
        raise ValueError(f"{path} must contain 512 character tiles")
    tiles: list[list[list[int]]] = []
    for index, tile in enumerate(raw):
        if not isinstance(tile, list) or len(tile) != TILE_SIZE:
            raise ValueError(f"character {index} must have eight rows")
        rows = []
        for row in tile:
            if not isinstance(row, list) or len(row) != TILE_SIZE:
                raise ValueError(f"character {index} rows must have eight pixels")
            pixels = [int(pixel) for pixel in row]
            if any(pixel < 0 or pixel > 3 for pixel in pixels):
                raise ValueError(f"character {index} has a pixel outside 0..3")
            rows.append(pixels)
        tiles.append(rows)
    return tiles


def rotate_ccw(tile: list[list[int]]) -> list[list[int]]:
    size = len(tile)
    return [[tile[x][size - 1 - y] for x in range(size)] for y in range(size)]


def rotate_cw(tile: list[list[int]]) -> list[list[int]]:
    size = len(tile)
    return [[tile[size - 1 - x][y] for x in range(size)] for y in range(size)]


def transform(tile: list[list[int]], horizontal: bool,
              vertical: bool) -> list[list[int]]:
    rows = [row[:] for row in tile]
    if horizontal:
        rows = [list(reversed(row)) for row in rows]
    if vertical:
        rows.reverse()
    return rows


def pack_tile(tile: list[list[int]]) -> bytes:
    return bytes((row[x] << 4) | row[x + 1]
                 for row in tile for x in range(0, TILE_SIZE, 2))


def strip_gate_pens(tile: bytes) -> bytes:
    """Remove dynamic Green/Purple gate pixels while preserving background."""
    result = bytearray()
    for value in tile:
        high, low = value >> 4, value & 0x0F
        if high in (GREEN, PURPLE):
            high = BLACK
        if low in (GREEN, PURPLE):
            low = BLACK
        result.append((high << 4) | low)
    return bytes(result)


def gime_rgb(code: int) -> tuple[int, int, int]:
    return (
        (170 if code & 0x20 else 0) + (85 if code & 0x04 else 0),
        (170 if code & 0x10 else 0) + (85 if code & 0x02 else 0),
        (170 if code & 0x08 else 0) + (85 if code & 0x01 else 0),
    )


def nearest_palette_index(rgb: list[int]) -> int:
    return min(range(len(PALETTE)), key=lambda index: sum(
        (component - target) ** 2
        for component, target in zip(rgb, gime_rgb(PALETTE[index]))
    ))


def recolor(tile: list[list[int]], pen_map: tuple[int, int, int, int]) -> list[list[int]]:
    return [[pen_map[int(pixel)] for pixel in row] for row in tile]


def load_sprites(path: Path) -> list[list[list[int]]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or len(raw) != 128:
        raise ValueError(f"{path} must contain 128 sprite grids")
    for index, sprite in enumerate(raw):
        if (not isinstance(sprite, list) or len(sprite) != 16 or
                any(not isinstance(row, list) or len(row) != 16 for row in sprite)):
            raise ValueError(f"sprite {index} must be 16x16 pixels")
        if any(int(pixel) < 0 or int(pixel) > 3
               for row in sprite for pixel in row):
            raise ValueError(f"sprite {index} has a pixel outside 0..3")
    return raw


def pack_sprite_2bpp(pixels: list[list[int]]) -> bytes:
    """Pack four source pixels per byte for runtime palette expansion."""
    return bytes((int(row[x]) << 6) | (int(row[x + 1]) << 4) |
                 (int(row[x + 2]) << 2) | int(row[x + 3])
                 for row in pixels for x in range(0, 16, 4))


def compile_sprite_codes(path: Path, codes: tuple[int, ...],
                         align_right: bool = False) -> list[bytes]:
    sprites = load_sprites(path)
    frames = []
    for code in codes:
        pixels = rotate_ccw(sprites[code])
        if align_right:
            pixels = [[0] + row[:15] for row in pixels]
        frames.append(pack_sprite_2bpp(pixels))
    return frames


def compile_player_sprites(path: Path) -> list[bytes]:
    # Use one authored north-facing animation set. Derive E/S/W clockwise.
    sprites = load_sprites(path)
    north = [rotate_ccw(sprites[code]) for code in PLAYER_CODES]
    frames = []
    direction = north
    for _ in range(4):
        frames.extend(direction)
        direction = [rotate_cw(frame) for frame in direction]
    return [pack_sprite_2bpp([[0] + row[:15] for row in frame])
            for frame in frames]


def compile_enemy_sprites(path: Path) -> list[bytes]:
    """Build type-major N/E/S/W animations using the player rotation rule."""
    sprites = load_sprites(path)
    frames = []
    for codes in ENEMY_CODE_SETS:
        north = [rotate_ccw(sprites[code]) for code in codes]
        direction = north
        for _ in range(4):
            frames.extend(direction)
            direction = [rotate_cw(frame) for frame in direction]
    return [pack_sprite_2bpp([[0] + row[:15] for row in frame])
            for frame in frames]


def compile_death_sprites(path: Path) -> list[bytes]:
    return compile_sprite_codes(path, DEATH_CODES)


def emit_packed_sprite_group(lines: list[str], label: str,
                             frames: list[bytes], codes: tuple[int, ...]) -> None:
    lines.extend(["", label])
    for index, frame in enumerate(frames):
        code = codes[index]
        row, column = sheet_coordinates(code)
        lines.append(
            f"        ; frame {index}: R{row}C{column} / ROM code {code}"
        )
        for offset in range(0, len(frame), 8):
            lines.append("        fcb     " + ",".join(
                f"${value:02X}" for value in frame[offset:offset + 8]))


def write_resident_include(path: Path, player_sprites: list[bytes],
                           death_sprites: list[bytes],
                           vegetable_sprites: list[bytes]) -> None:
    lines = [
        "; Generated by scripts/build_screen.py; do not edit.",
        f"PLAYER_FRAME_COUNT equ    {len(player_sprites)}",
        "PACKED_SPRITE_SIZE equ    64",
        f"DEATH_FRAME_COUNT equ     {len(death_sprites)}",
        "DEATH_WING_FIRST equ      7",
        f"DEATH_ANGEL_FRAME equ     {len(death_sprites) - 1}",
        f"VEGETABLE_COUNT equ       {len(vegetable_sprites)}",
    ]
    emit_packed_sprite_group(lines, "player_sprites", player_sprites,
                             PLAYER_CODES * 4)
    emit_packed_sprite_group(lines, "death_sprites", death_sprites, DEATH_CODES)
    emit_packed_sprite_group(lines, "vegetable_sprites", vegetable_sprites,
                             VEGETABLE_CODES)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines) + "\n")


def compile_hud_digits(chars_path: Path) -> list[bytes]:
    """Compile arcade digits 0-9 as colour-1 masks for runtime recolouring."""
    chars = load_chars(chars_path)
    return [pack_tile(recolor(rotate_ccw(chars[code]), (BLACK, 1, 1, 1)))
            for code in range(10)]


def pack_object_mask(pixels: list[list[int]]) -> bytes:
    """Pack four 2-bit object categories per byte."""
    return bytes((row[x] << 6) | (row[x + 1] << 4) |
                 (row[x + 2] << 2) | row[x + 3]
                 for row in pixels for x in range(0, 16, 4))


def compile_object_masks(chars_path: Path) -> list[bytes]:
    """Compile the arcade's exact 2x2 character objects into runtime masks."""
    chars = load_chars(chars_path)
    masks: list[bytes] = []
    for name in OBJECT_NAMES:
        top_left, top_right, bottom_left, bottom_right = OBJECT_CHAR_CODES[name]
        quadrants = [rotate_ccw(chars[code]) for code in
                     (top_left, top_right, bottom_left, bottom_right)]
        pixels = [quadrants[(y // 8) * 2][y % 8] +
                  quadrants[(y // 8) * 2 + 1][y % 8]
                  for y in range(16)]
        mask = []
        for row in pixels:
            converted = []
            for pen in row:
                if name == "skull":
                    converted.append(2 if pen == 2 else 0)
                elif name == "heart":
                    converted.append(3 if pen == 3 else (2 if pen == 1 else 0))
                else:
                    converted.append(2 if pen == 1 else 0)
            mask.append(converted)
        masks.append(pack_object_mask(mask))
    return masks


def parse_csv(data: ET.Element, layer_name: str) -> list[int]:
    if data.get("encoding") != "csv":
        raise ValueError(f"layer {layer_name!r} must use CSV encoding")
    values = [field.strip() for field in (data.text or "").split(",")]
    if any(not field for field in values):
        raise ValueError(f"layer {layer_name!r} contains an empty CSV field")
    if len(values) != SCREEN_WIDTH * SCREEN_HEIGHT:
        raise ValueError(
            f"layer {layer_name!r} has {len(values)} cells; expected 960"
        )
    return [int(field) for field in values]


def tileset_ranges(root: ET.Element, map_path: Path) -> list[dict[str, object]]:
    ranges: list[dict[str, object]] = []
    nodes = root.findall("tileset")
    for position, node in enumerate(nodes):
        firstgid = int(node.attrib["firstgid"])
        source = node.get("source")
        if source:
            tsx_path = (map_path.parent / source).resolve()
            tsx = ET.parse(tsx_path).getroot()
        else:
            tsx = node
        count = int(tsx.attrib["tilecount"])
        next_first = int(nodes[position + 1].attrib["firstgid"]) if position + 1 < len(nodes) else firstgid + count
        ranges.append({
            "firstgid": firstgid,
            "lastgid": min(firstgid + count, next_first) - 1,
            "name": tsx.get("name", ""),
            "tilewidth": int(tsx.attrib["tilewidth"]),
            "tileheight": int(tsx.attrib["tileheight"]),
        })
    return ranges


def compile_screen(map_path: Path, maze_path: Path, chars_path: Path,
                   sprites_path: Path) -> tuple[
                       list[int], list[bytes], list[list[tuple[int, int, int]]],
                       list[list[tuple[int, int, int]]], list[list[int]], list[int], int
                   ]:
    root = ET.parse(map_path).getroot()
    if (int(root.attrib["width"]), int(root.attrib["height"])) != (SCREEN_WIDTH, SCREEN_HEIGHT):
        raise ValueError(f"{map_path} must be a 40x24 map")
    if (int(root.attrib["tilewidth"]), int(root.attrib["tileheight"])) != (TILE_SIZE, TILE_SIZE):
        raise ValueError(f"{map_path} must use 8x8 map cells")

    flattened = [0] * (SCREEN_WIDTH * SCREEN_HEIGHT)
    layers = root.findall("layer")
    if not layers:
        raise ValueError(f"{map_path} contains no tile layers")
    for layer in layers:
        if layer.get("visible", "1") == "0":
            continue
        cells = parse_csv(layer.find("data"), layer.get("name", ""))
        for index, gid in enumerate(cells):
            if gid & GID_MASK:
                flattened[index] = gid
    if any((gid & GID_MASK) == 0 for gid in flattened):
        raise ValueError("visible tile layers do not cover all 960 screen cells")

    ranges = tileset_ranges(root, map_path)
    chars = load_chars(chars_path)
    rotated = [rotate_ccw(tile) for tile in chars]
    packed_tiles: list[bytes] = []
    tile_ids: dict[bytes, int] = {}
    screen_map: list[int] = []

    for screen_index, gid_with_flags in enumerate(flattened):
        screen_x = screen_index % SCREEN_WIDTH
        screen_y = screen_index // SCREEN_WIDTH
        if gid_with_flags & FLIP_D:
            raise ValueError("diagonal Tiled tile flips are not supported")
        gid = gid_with_flags & GID_MASK
        tileset = next((item for item in ranges
                        if int(item["firstgid"]) <= gid <= int(item["lastgid"])), None)
        if tileset is None:
            raise ValueError(f"GID {gid} does not belong to a declared tileset")
        if (tileset["name"] != "chars_raw2bpp" or
                tileset["tilewidth"] != TILE_SIZE or
                tileset["tileheight"] != TILE_SIZE):
            raise ValueError(
                f"active GID {gid} uses unsupported tileset {tileset['name']!r} "
                f"({tileset['tilewidth']}x{tileset['tileheight']})"
            )

        sheet_index = gid - int(tileset["firstgid"])
        code = (sheet_index % 16) * 32 + (31 - sheet_index // 16)
        tile = transform(rotated[code], bool(gid_with_flags & FLIP_H),
                         bool(gid_with_flags & FLIP_V))

        if 8 <= screen_x < 32:
            maze_x = screen_x - 8
            if code == 229:
                # Arcade flower: four Light Blue corners and a White centre.
                tile = recolor(tile, (BLACK, WHITE, LIGHT_BLUE, PINK))
            elif maze_x in (0, 23) or screen_y in (0, 23):
                # Outer timer boxes are White; pen 3 is the Pink inner edge
                # present in the bottom/right corner glyphs.
                tile = recolor(tile, (BLACK, PINK, WHITE, PINK))
            else:
                # Regular walls are Pink. Gate bars use pen 3 (Green) and
                # their centre/pivot highlights use pen 2 (Purple).
                tile = recolor(tile, (BLACK, PINK, PURPLE, GREEN))
        elif screen_x < 8 and screen_y < 9:
            # Three descending arcade bonus panels: SPECIAL, EXTRA, x2x3x5.
            panel = screen_y // 3
            color = (RED, YELLOW, BLUE)[panel]
            if screen_y % 3 == 1:
                tile = recolor(tile, (BLACK, GREY, GREY, GREY))
                if screen_x == 0:
                    tile = recolor(transform(rotated[code],
                                             bool(gid_with_flags & FLIP_H),
                                             bool(gid_with_flags & FLIP_V)),
                                   (BLACK, color, color, color))
            else:
                tile = recolor(tile, (BLACK, color, color, color))
        elif 33 <= screen_x < 39 and 21 <= screen_y < 23:
            # Preserve the life-marker character tiles authored in the TMX;
            # swap their Red/Green source pens to match the arcade markers.
            tile = recolor(tile, LIFE_PEN_MAP)
        elif screen_x >= 32:
            hud_color = {
                1: LIGHT_GREEN, 2: LIGHT_GREEN,
                4: RED, 5: RED,
                7: WHITE, 8: WHITE,
                10: BLUE, 11: BLUE,
                12: GREEN,
            }.get(screen_y, BLACK)
            tile = recolor(tile, (BLACK, hud_color, hud_color, hud_color))

        packed = pack_tile(tile)
        if packed not in tile_ids:
            tile_ids[packed] = len(packed_tiles)
            packed_tiles.append(packed)
            if len(packed_tiles) > 256:
                raise ValueError("screen requires more than 256 unique transformed tiles")
        screen_map.append(tile_ids[packed])

    # Gate records contain only the dynamic Purple/Green pixels.  Per-gate
    # background records below preserve contextual Pink wall variants.
    gate_pen_map = (BLACK, BLACK, PURPLE, GREEN)
    source_states = (
        ((0, -1, 57), (-2, 0, 52), (-1, 0, 53), (0, 0, 54), (1, 0, 55)),
        ((-1, 0, 64), (0, -2, 59), (0, -1, 61), (0, 0, 62), (0, 1, 63)),
    )
    gate_states: list[list[tuple[int, int, int]]] = []
    for state in range(4):
        # The turnstile has four logical passage states but only two visible
        # orientations.  A 180-degree state reuses the same arcade tiles;
        # rotating the individual 8x8 cells displaces the art from its pivot.
        source = source_states[state & 1]
        records: list[tuple[int, int, int]] = []
        for dx, dy, code in source:
            pixels = recolor(rotated[code], gate_pen_map)
            packed = pack_tile(pixels)
            if packed not in tile_ids:
                tile_ids[packed] = len(packed_tiles)
                packed_tiles.append(packed)
            records.append((dx, dy, tile_ids[packed]))
        gate_states.append(records)

    # MAME frame 729 supplies the backslash intermediate.  The adjacent ROM
    # table at $0CD5 supplies the slash intermediate.  Zero entries mean that
    # the existing background cell is left untouched.
    diagonal_sources = (
        ((0, -1, 71), (1, -1, 70), (-1, 0, 73), (0, 0, 72),
         (1, 0, 255), (-1, 1, 74), (0, 1, 255)),
        ((-1, -1, 65), (0, -1, 57), (-1, 0, 64), (0, 0, 66),
         (1, 0, 67), (0, 1, 68), (1, 1, 69)),
    )
    gate_diagonals: list[list[tuple[int, int, int]]] = []
    for source in diagonal_sources:
        records = []
        for dx, dy, code in source:
            packed = pack_tile(recolor(rotated[code],
                                       (BLACK, PINK, PURPLE, GREEN)))
            if packed not in tile_ids:
                tile_ids[packed] = len(packed_tiles)
                packed_tiles.append(packed)
            records.append((dx, dy, tile_ids[packed]))
        gate_diagonals.append(records)

    maze = json.loads(maze_path.read_text(encoding="utf-8"))
    gates = maze["gates"]
    if len(gates) != 20:
        raise ValueError(f"{maze_path} must contain 20 gates")
    dot_tile_ids = {
        screen_map[y * SCREEN_WIDTH + x + 8] for x, y in maze["dots"]
    }
    if len(dot_tile_ids) != 1:
        raise ValueError("all maze dots must use one compiled screen tile")
    maze_dot_tile_id = dot_tile_ids.pop()
    union_offsets = ((0, -2), (0, -1), (-2, 0), (-1, 0),
                     (0, 0), (1, 0), (0, 1))
    gate_backgrounds: list[list[int]] = []
    gate_unions: list[set[tuple[int, int]]] = []
    for gate in gates:
        pivot_x, pivot_y = gate["pivot"]
        cells = {(pivot_x + dx, pivot_y + dy) for dx, dy in union_offsets}
        gate_unions.append(cells)
        backgrounds: list[int] = []
        for dx, dy in union_offsets:
            x, y = pivot_x + dx, pivot_y + dy
            tile = strip_gate_pens(packed_tiles[screen_map[y * SCREEN_WIDTH + x + 8]])
            if tile not in tile_ids:
                tile_ids[tile] = len(packed_tiles)
                packed_tiles.append(tile)
            backgrounds.append(tile_ids[tile])
        gate_backgrounds.append(backgrounds)

    gate_neighbors: list[int] = []
    for gate_id, cells in enumerate(gate_unions):
        overlaps = [other + 1 for other, other_cells in enumerate(gate_unions)
                    if other != gate_id and cells & other_cells]
        if len(overlaps) > 1:
            raise ValueError(f"gate {gate_id} overlaps multiple visual unions")
        gate_neighbors.append(overlaps[0] if overlaps else 0)

    return (screen_map, packed_tiles, gate_states, gate_diagonals,
            gate_backgrounds, gate_neighbors, maze_dot_tile_id)


def emit_include(path: Path, screen_map: list[int], tiles: list[bytes],
                 clean_tile_id: int,
                 hud_digits: list[bytes],
                 gate_states: list[list[tuple[int, int, int]]],
                 gate_diagonals: list[list[tuple[int, int, int]]],
                 gate_backgrounds: list[list[int]],
                 gate_neighbors: list[int], maze_dot_tile_id: int,
                 object_masks: list[bytes], score_sprites: list[bytes],
                 multiplier_graphics: list[bytes]) -> None:
    unique_gate_backgrounds: list[list[int]] = []
    gate_background_index: list[int] = []
    for records in gate_backgrounds:
        if records not in unique_gate_backgrounds:
            unique_gate_backgrounds.append(records)
        gate_background_index.append(unique_gate_backgrounds.index(records))

    lines = [
        "; Generated by scripts/build_screen.py. Do not edit.",
        f"SCREEN_WIDTH       equ     {SCREEN_WIDTH}",
        f"SCREEN_HEIGHT      equ     {SCREEN_HEIGHT}",
        f"SCREEN_TILE_COUNT  equ     {len(tiles)}",
        f"MAZE_CLEAN_TILE    equ     {clean_tile_id}",
        f"MAZE_DOT_TILE      equ     {maze_dot_tile_id}",
        "HUD_DIGIT_COUNT    equ     10",
        "HUD_DIGIT_SIZE     equ     32",
        f"OBJECT_MASK_COUNT equ     {len(object_masks)}",
        "OBJECT_MASK_SIZE  equ     64",
        "PICKUP_MULTIPLIER_SIZE equ 32",
        "",
        "palette_table",
        "        fcb     " + ",".join(f"${value:02X}" for value in PALETTE),
        "",
        "screen_map",
    ]
    for row in range(SCREEN_HEIGHT):
        values = screen_map[row * SCREEN_WIDTH:(row + 1) * SCREEN_WIDTH]
        lines.append("        fcb     " + ",".join(f"${value:02X}" for value in values))
    lines.extend(["", "screen_tiles"])
    for tile_index, tile in enumerate(tiles):
        lines.append(f"; tile {tile_index}")
        for row in range(TILE_SIZE):
            values = tile[row * 4:(row + 1) * 4]
            lines.append("        fcb     " + ",".join(f"${value:02X}" for value in values))
    lines.extend(["", "; Four gate states; each record is signed dx, signed dy, tile ID.",
                  "gate_state_tiles"])
    for state, records in enumerate(gate_states):
        lines.append(f"; state {state}")
        for dx, dy, tile_id in records:
            lines.append(f"        fcb     ${dx & 0xff:02X},${dy & 0xff:02X},${tile_id:02X}")
    lines.extend(["", "; Slash then backslash one-Vbord gate intermediates.",
                  "gate_diagonal_tiles"])
    for style, records in enumerate(gate_diagonals):
        lines.append(f"; diagonal style {style}")
        for dx, dy, tile_id in records:
            lines.append(f"        fcb     ${dx & 0xff:02X},${dy & 0xff:02X},${tile_id:02X}")
    lines.extend(["", "; Unique seven-cell gate-free contextual backgrounds.",
                  "; Each gate selects one record through gate_background_index.",
                  "gate_background_index",
                  "        fcb     " + ",".join(
                      f"${value:02X}" for value in gate_background_index),
                  "gate_background_tiles"])
    for records in unique_gate_backgrounds:
        lines.append("        fcb     " + ",".join(f"${tile_id:02X}" for tile_id in records))
    lines.extend(["", "; Overlapping visual-union neighbour ID+1, or zero.",
                  "gate_redraw_neighbors",
                  "        fcb     " + ",".join(f"${value:02X}" for value in gate_neighbors)])
    lines.extend(["", "hud_digit_tiles"])
    for digit, pixels in enumerate(hud_digits):
        lines.append(f"; digit {digit}: colour-1 mask")
        for row in range(8):
            values = pixels[row * 4:(row + 1) * 4]
            lines.append("        fcb     " + ",".join(f"${value:02X}" for value in values))
    lines.extend(["", "object_masks"])
    for index, pixels in enumerate(object_masks):
        lines.append(f"; object {index}: {OBJECT_NAMES[index]}")
        for row in range(16):
            values = pixels[row * 4:(row + 1) * 4]
            lines.append("        fcb     " + ",".join(f"${value:02X}" for value in values))
    lines.extend(["", "pickup_multiplier_graphics"])
    for index, graphic in enumerate(multiplier_graphics):
        code = MULTIPLIER_CHAR_CODES[index]
        row = 31 - (code % 32)
        column = code // 32
        lines.append(f"; x{(2, 3, 5)[index]}: R{row}C{column} / ROM code {code}")
        for offset in range(0, len(graphic), 8):
            lines.append("        fcb     " + ",".join(
                f"${value:02X}" for value in graphic[offset:offset + 8]))
    emit_packed_sprite_group(lines, "score_sprites", score_sprites, SCORE_CODES)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="ascii")


def main() -> None:
    args = parse_args()
    (screen_map, tiles, gate_states, gate_diagonals,
     gate_backgrounds, gate_neighbors, maze_dot_tile_id) = compile_screen(
        args.map, args.maze, args.chars, args.sprites
    )
    chars = load_chars(args.chars)
    clean = pack_tile(rotate_ccw(chars[255]))
    if clean not in tiles:
        tiles.append(clean)
    clean_tile_id = tiles.index(clean)
    player_frames = compile_player_sprites(args.sprites)
    hud_digits = compile_hud_digits(args.chars)
    object_masks = compile_object_masks(args.chars)
    death_sprites = compile_death_sprites(args.sprites)
    vegetable_sprites = compile_sprite_codes(args.sprites, VEGETABLE_CODES)
    score_sprites = compile_sprite_codes(args.sprites, SCORE_CODES)
    enemy_sprites = compile_enemy_sprites(args.sprites)
    args.enemy_output.parent.mkdir(parents=True, exist_ok=True)
    args.enemy_output.write_bytes(b"".join(enemy_sprites))
    multiplier_graphics = [
        pack_tile(recolor(rotate_ccw(chars[code]), (BLACK, WHITE, WHITE, WHITE)))
        for code in MULTIPLIER_CHAR_CODES
    ]
    emit_include(args.output, screen_map, tiles, clean_tile_id, hud_digits,
                 gate_states, gate_diagonals, gate_backgrounds, gate_neighbors,
                 maze_dot_tile_id, object_masks, score_sprites,
                 multiplier_graphics)
    write_resident_include(args.resident_output, player_frames, death_sprites,
                           vegetable_sprites)

    data_bytes = (len(screen_map) + len(tiles) * 32 +
                  len(hud_digits) * 32 + len(object_masks) * 64 +
                  len(score_sprites) * 64 +
                  len(multiplier_graphics) * 32)
    print(f"screen: {len(tiles)} unique tiles, {len(player_frames)} player frames, "
          f"{data_bytes} data bytes")


if __name__ == "__main__":
    main()
