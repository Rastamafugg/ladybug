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
PALETTE = (0x00, 0x30, 0x08, 0x3F, 0x20, 0x10, 0x18, 0x28,
           0x38, 0x04, 0x02, 0x01, 0x06, 0x03, 0x05, 0x07)
PLAYER_SOURCE_FRAME = 0
PLAYER_PEN_MAP = (0, 4, 5, 1)  # sprite attribute 0: transparent, red, green, yellow


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--map", type=Path, required=True)
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


def compile_player_sprites(path: Path) -> list[tuple[bytes, bytes]]:
    sprites = load_sprites(path)
    frames: list[tuple[bytes, bytes]] = []
    for direction in range(4):  # north, east, south, west
        pixels = rotate_ccw(sprites[PLAYER_SOURCE_FRAME])
        for _ in range(direction):
            pixels = rotate_cw(pixels)
        packed = bytearray()
        preserve = bytearray()
        for row in pixels:
            for x in range(0, 16, 2):
                left, right = int(row[x]), int(row[x + 1])
                packed.append((PLAYER_PEN_MAP[left] << 4) | PLAYER_PEN_MAP[right])
                preserve.append((0xF0 if left == 0 else 0) |
                                (0x0F if right == 0 else 0))
        frames.append((bytes(packed), bytes(preserve)))
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


def compile_screen(map_path: Path, chars_path: Path) -> tuple[list[int], list[bytes]]:
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

    for gid_with_flags in flattened:
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
        packed = pack_tile(transform(rotated[code],
                                     bool(gid_with_flags & FLIP_H),
                                     bool(gid_with_flags & FLIP_V)))
        if packed not in tile_ids:
            tile_ids[packed] = len(packed_tiles)
            packed_tiles.append(packed)
            if len(packed_tiles) > 256:
                raise ValueError("screen requires more than 256 unique transformed tiles")
        screen_map.append(tile_ids[packed])

    return screen_map, packed_tiles


def emit_include(path: Path, screen_map: list[int], tiles: list[bytes],
                 clean_tile_id: int,
                 player_frames: list[tuple[bytes, bytes]]) -> None:
    lines = [
        "; Generated by scripts/build_screen.py. Do not edit.",
        f"SCREEN_WIDTH       equ     {SCREEN_WIDTH}",
        f"SCREEN_HEIGHT      equ     {SCREEN_HEIGHT}",
        f"SCREEN_TILE_COUNT  equ     {len(tiles)}",
        f"MAZE_CLEAN_TILE    equ     {clean_tile_id}",
        f"PLAYER_FRAME_COUNT equ     {len(player_frames)}",
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
    lines.extend(["", "player_sprites"])
    for frame_index, (pixels, preserve) in enumerate(player_frames):
        lines.append(f"; player frame {frame_index}: pixels then preserve mask")
        for block in (pixels, preserve):
            for row in range(16):
                values = block[row * 8:(row + 1) * 8]
                lines.append("        fcb     " + ",".join(f"${value:02X}" for value in values))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="ascii")


def main() -> None:
    args = parse_args()
    screen_map, tiles = compile_screen(args.map, args.chars)
    chars = load_chars(args.chars)
    clean = pack_tile(rotate_ccw(chars[255]))
    if clean not in tiles:
        tiles.append(clean)
    clean_tile_id = tiles.index(clean)
    player_frames = compile_player_sprites(args.sprites)
    emit_include(args.output, screen_map, tiles, clean_tile_id, player_frames)
    data_bytes = len(screen_map) + len(tiles) * 32 + len(player_frames) * 256
    print(f"screen: {len(tiles)} unique tiles, {len(player_frames)} player frames, "
          f"{data_bytes} data bytes")


if __name__ == "__main__":
    main()
