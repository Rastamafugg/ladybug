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
PLAYER_SOURCE_FRAME = 0
PLAYER_PEN_MAP = (BLACK, DARK_RED, GREEN, YELLOW)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--map", type=Path, required=True)
    parser.add_argument("--maze", type=Path, required=True)
    parser.add_argument("--chars", type=Path, required=True)
    parser.add_argument("--sprites", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
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


def compile_player_sprites(path: Path) -> list[bytes]:
    sprites = load_sprites(path)
    frames: list[bytes] = []
    pixels = rotate_cw(rotate_cw(sprites[PLAYER_SOURCE_FRAME]))
    for direction in range(4):  # north, east, south, west
        # Sprite 0 faces down in ROM coordinates.  The runtime order is
        # north/east/south/west.  Shift its collision-safe silhouette one
        # pixel right inside the byte-aligned 16-pixel save rectangle.
        aligned = [[0] + row[:15] for row in pixels]
        packed = bytearray()
        for row in aligned:
            for x in range(0, 16, 2):
                left, right = int(row[x]), int(row[x + 1])
                packed.append((PLAYER_PEN_MAP[left] << 4) | PLAYER_PEN_MAP[right])
        frames.append(bytes(packed))
        pixels = rotate_cw(pixels)
    return frames


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
    player = rotate_cw(rotate_cw(load_sprites(sprites_path)[PLAYER_SOURCE_FRAME]))
    east_player = [[0] + row[:15] for row in rotate_cw(player)]
    life_tiles = {
        (0, 0): [row[:8] for row in east_player[:8]],
        (1, 0): [row[8:] for row in east_player[:8]],
        (0, 1): [row[:8] for row in east_player[8:]],
        (1, 1): [row[8:] for row in east_player[8:]],
    }
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
            quadrant = ((screen_x - 33) % 2, screen_y - 21)
            tile = recolor(life_tiles[quadrant], PLAYER_PEN_MAP)
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
                 player_frames: list[bytes],
                 gate_states: list[list[tuple[int, int, int]]],
                 gate_diagonals: list[list[tuple[int, int, int]]],
                 gate_backgrounds: list[list[int]],
                 gate_neighbors: list[int], maze_dot_tile_id: int) -> None:
    lines = [
        "; Generated by scripts/build_screen.py. Do not edit.",
        f"SCREEN_WIDTH       equ     {SCREEN_WIDTH}",
        f"SCREEN_HEIGHT      equ     {SCREEN_HEIGHT}",
        f"SCREEN_TILE_COUNT  equ     {len(tiles)}",
        f"MAZE_CLEAN_TILE    equ     {clean_tile_id}",
        f"MAZE_DOT_TILE      equ     {maze_dot_tile_id}",
        f"PLAYER_FRAME_COUNT equ     {len(player_frames)}",
        "PLAYER_FRAME_SIZE  equ     128",
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
    lines.extend(["", "; Seven gate-free contextual background tile IDs per gate.",
                  "gate_background_tiles"])
    for records in gate_backgrounds:
        lines.append("        fcb     " + ",".join(f"${tile_id:02X}" for tile_id in records))
    lines.extend(["", "; Overlapping visual-union neighbour ID+1, or zero.",
                  "gate_redraw_neighbors",
                  "        fcb     " + ",".join(f"${value:02X}" for value in gate_neighbors)])
    lines.extend(["", "player_sprites"])
    for frame_index, pixels in enumerate(player_frames):
        lines.append(f"; player frame {frame_index}: transparent packed pixels")
        for row in range(16):
            values = pixels[row * 8:(row + 1) * 8]
            lines.append("        fcb     " + ",".join(f"${value:02X}" for value in values))
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
    emit_include(args.output, screen_map, tiles, clean_tile_id, player_frames,
                 gate_states, gate_diagonals, gate_backgrounds, gate_neighbors,
                 maze_dot_tile_id)

    data_bytes = len(screen_map) + len(tiles) * 32 + len(player_frames) * 128
    print(f"screen: {len(tiles)} unique tiles, {len(player_frames)} player frames, "
          f"{data_bytes} data bytes")


if __name__ == "__main__":
    main()
