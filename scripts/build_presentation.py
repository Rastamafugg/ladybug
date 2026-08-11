#!/usr/bin/env python3
"""Compile the six authored presentation TMX maps into shared cold data."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_screen import (  # noqa: E402
    BLACK,
    BLUE,
    FLIP_D,
    FLIP_H,
    FLIP_V,
    GID_MASK,
    GREEN,
    LIGHT_BLUE,
    LIGHT_GREEN,
    ORANGE,
    PINK,
    PURPLE,
    RED,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    TILE_SIZE,
    WHITE,
    YELLOW,
    char_sheet_code,
    compile_screen,
    load_chars,
    pack_tile,
    parse_csv,
    recolor,
    rotate_ccw,
    sheet_code,
    tileset_ranges,
    transform,
)


MAP_NAMES = (
    "attract",
    "instructions",
    "level-start",
    "high-score",
    "game-over",
    "enter-high-score",
)
MAP_FILES = {
    name: f"coco-{name}-screen.tmx" for name in MAP_NAMES
}
PAGE_BYTES = 0x2000
COLD_PAGE = 0x3A
COLD_PAGE_COUNT = 4
MAP_BYTES = SCREEN_WIDTH * SCREEN_HEIGHT
TILE_BYTES = 32
MAP_OUTPUT_OFFSET = 0x4000
COLD_PAYLOAD_LIMIT = 12939
ATTRACT_ACTOR_COLOURS = {
    (11, 3): (WHITE, GREEN, PINK),
    (35, 4): (WHITE, YELLOW, ORANGE),
    (27, 5): (WHITE, GREEN, PURPLE),
    (3, 9): (WHITE, YELLOW, ORANGE),
    (10, 15): (YELLOW, GREEN, RED),
    (33, 19): (WHITE, LIGHT_GREEN, GREEN),
    (5, 20): (WHITE, YELLOW, ORANGE),
}
ATTRACT_ACTOR_EXPECTED_TILES = {
    (11, 3): 1,
    (35, 4): 5,
    (27, 5): 0,
    (3, 9): 68,
    (10, 15): 32,
    (33, 19): 35,
    (5, 20): 2,
}
ATTRACT_ACTOR_SURFACE_PAGE = 0x3C
ATTRACT_ACTOR_SURFACE_ADDRESS = 0xA000
ATTRACT_ACTOR_BYTES = 128
ATTRACT_ACTOR_PHASES = (0, 1, 2)
ATTRACT_ACTOR_DESTINATION_ADDRESS = 0xAA80
ATTRACT_ACTOR_PHASE_POINTER_ADDRESS = 0xAA8E


def lzss_compress(data: bytes) -> bytes:
    """Encode bounded 12-bit-offset, 4-bit-length LZSS groups."""
    output = bytearray()
    cursor = 0
    while cursor < len(data):
        flag_offset = len(output)
        output.append(0)
        flags = 0
        for bit in range(8):
            if cursor >= len(data):
                break
            best_length = 0
            best_offset = 0
            for candidate in range(max(0, cursor - 4095), cursor):
                length = 0
                distance = cursor - candidate
                while (length < 18 and cursor + length < len(data) and
                       data[candidate + length % distance] == data[cursor + length]):
                    length += 1
                if length >= 3 and length > best_length:
                    best_length = length
                    best_offset = distance
            if best_length >= 3:
                token = (best_offset << 4) | (best_length - 3)
                output.extend(token.to_bytes(2, "big"))
                cursor += best_length
            else:
                flags |= 1 << bit
                output.append(data[cursor])
                cursor += 1
        output[flag_offset] = flags
    return bytes(output)


def sprite_transform(tile: list[list[int]], flags: int) -> list[list[int]]:
    """Apply Tiled's orthogonal diagonal, horizontal, then vertical flags."""
    rows = [row[:] for row in tile]
    if flags & FLIP_D:
        rows = [list(row) for row in zip(*rows)]
    return transform(rows, bool(flags & FLIP_H), bool(flags & FLIP_V))


def title_framebuffer(attract_map: bytes, tiles: list[bytes]) -> bytearray:
    framebuffer = bytearray(0x7800)
    for cell, tile_id in enumerate(attract_map):
        row, column = divmod(cell, SCREEN_WIDTH)
        tile = tiles[tile_id]
        destination = row * TILE_SIZE * 160 + column * 4
        for tile_row in range(8):
            start = destination + tile_row * 160
            framebuffer[start:start + 4] = tile[tile_row * 4:tile_row * 4 + 4]
    return framebuffer


def parse_attract_actors(path: Path) -> list[dict[str, object]]:
    root = ET.parse(path).getroot()
    ranges = tileset_ranges(root, path)
    layer = next((item for item in root.findall("layer")
                  if item.get("name") == "Sprite Animations"), None)
    if layer is None:
        raise ValueError(f"{path}: missing Sprite Animations layer")
    cells = parse_csv(layer.find("data"), layer.get("name", ""))
    actors = []
    for index, gid_with_flags in enumerate(cells):
        gid = gid_with_flags & GID_MASK
        if not gid:
            continue
        x, y = index % SCREEN_WIDTH, index // SCREEN_WIDTH
        tileset = next((item for item in ranges
                        if int(item["firstgid"]) <= gid <= int(item["lastgid"])), None)
        if tileset is None or tileset["name"] != "sprites_raw2bpp":
            raise ValueError(f"{path}: actor ({x},{y}) is not a raw sprite tile")
        tile_id = gid - int(tileset["firstgid"])
        expected = ATTRACT_ACTOR_EXPECTED_TILES.get((x, y))
        if expected is None or tile_id != expected:
            raise ValueError(f"{path}: unexpected actor tile {tile_id} at ({x},{y})")
        actors.append({
            "cell": [x, y],
            "destination": 0x2000 + y * 1280 + x * 4,
            "tile_id": tile_id,
            "sheet_row": tile_id // 16,
            "sheet_column": tile_id % 16,
            "flags": gid_with_flags & ~GID_MASK,
            "colours": list(ATTRACT_ACTOR_COLOURS[(x, y)]),
        })
    if len(actors) != len(ATTRACT_ACTOR_COLOURS):
        raise ValueError(f"{path}: expected seven Sprite Animations cells")
    rectangles = []
    for actor in actors:
        x, y = actor["cell"]
        rect = (x * 8, y * 8, x * 8 + 16, y * 8 + 16)
        if any(rect[0] < other[2] and other[0] < rect[2] and
               rect[1] < other[3] and other[1] < rect[3]
               for other in rectangles):
            raise ValueError(f"{path}: overlapping actor at ({x},{y})")
        rectangles.append(rect)
    return actors


def compile_attract_surfaces(
        attract_map: bytes, tiles: list[bytes], sprites: list[list[list[int]]],
        actors: list[dict[str, object]]) -> bytes:
    framebuffer = title_framebuffer(attract_map, tiles)
    surfaces = bytearray()
    for phase in ATTRACT_ACTOR_PHASES:
        for actor in actors:
            row = int(actor["sheet_row"])
            column = int(actor["sheet_column"])
            phase_rows = ((row + 2) % 8, (row + 1) % 8, row)
            code = sheet_code(phase_rows[phase], column)
            sprite = sprite_transform(rotate_ccw(sprites[code]), int(actor["flags"]))
            colours = [BLACK] + list(actor["colours"])
            destination = int(actor["destination"])
            offset = destination - 0x2000
            actor.setdefault("source_codes", []).append(code)
            composed = bytearray()
            for sprite_row in range(16):
                for x in range(0, 16, 2):
                    underlay = framebuffer[offset + sprite_row * 160 + x // 2]
                    high = colours[sprite[sprite_row][x]] if sprite[sprite_row][x] else underlay >> 4
                    low = colours[sprite[sprite_row][x + 1]] if sprite[sprite_row][x + 1] else underlay & 0x0F
                    composed.append((high << 4) | low)
            surfaces.extend(composed)
    return bytes(surfaces)


def compose_attract_frames(
        attract_map: bytes, tiles: list[bytes], surfaces: bytes,
        actors: list[dict[str, object]]) -> list[bytes]:
    base = title_framebuffer(attract_map, tiles)
    frames = []
    for phase in (0, 1, 2, 1):
        frame = bytearray(base)
        for actor_index, actor in enumerate(actors):
            source = (phase * len(actors) + actor_index) * ATTRACT_ACTOR_BYTES
            destination = int(actor["destination"]) - 0x2000
            for row in range(16):
                frame[destination + row * 160:destination + row * 160 + 8] = (
                    surfaces[source + row * 8:source + row * 8 + 8]
                )
        frames.append(bytes(frame))
    return frames


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tiled-dir", type=Path, required=True)
    parser.add_argument("--chars", type=Path, required=True)
    parser.add_argument("--gameplay-map", type=Path, required=True)
    parser.add_argument("--gameplay-maze", type=Path, required=True)
    parser.add_argument("--gameplay-chars", type=Path, required=True)
    parser.add_argument("--gameplay-sprites", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--include-output", type=Path, required=True)
    parser.add_argument("--manifest-output", type=Path, required=True)
    parser.add_argument("--actor-record-output", type=Path, required=True)
    parser.add_argument("--actor-underlay-output", type=Path, required=True)
    return parser.parse_args()


def flatten_map(path: Path) -> tuple[ET.Element, list[int]]:
    root = ET.parse(path).getroot()
    if (int(root.attrib["width"]), int(root.attrib["height"])) != (
        SCREEN_WIDTH, SCREEN_HEIGHT
    ):
        raise ValueError(f"{path} must be a 40x24 map")
    for tileset in root.findall("tileset"):
        source = tileset.get("source")
        if source and not (path.parent / source).exists():
            local_source = path.parent / Path(source).name
            if local_source.exists():
                tileset.set("source", local_source.name)
    flattened = [0] * MAP_BYTES
    for layer in root.findall("layer"):
        if layer.get("visible", "1") == "0":
            continue
        if layer.get("name") == "Sprite Animations":
            continue
        cells = parse_csv(layer.find("data"), layer.get("name", ""))
        for index, gid in enumerate(cells):
            if gid & GID_MASK:
                flattened[index] = gid
    return root, flattened


def presentation_pen_map(role: str, x: int, y: int) -> tuple[int, int, int, int]:
    """Apply the established CoCo palette adaptation to authored raw chars."""
    if x < 8 and y < 9:
        colour = (RED, YELLOW, BLUE)[y // 3]
        return (BLACK, colour, colour, colour)
    if x >= 32:
        colour = {
            1: LIGHT_GREEN, 2: LIGHT_GREEN,
            4: RED, 5: RED,
            7: WHITE, 8: WHITE,
            10: BLUE, 11: BLUE,
            12: GREEN,
        }.get(y, BLACK)
        return (BLACK, colour, colour, colour)
    if role == "level-start" and 8 <= x < 32:
        return (BLACK, PINK, WHITE, PINK)
    if role in ("game-over", "enter-high-score", "high-score"):
        return (BLACK, WHITE, WHITE, WHITE)
    if 8 <= x < 32:
        return (BLACK, PINK, PURPLE, GREEN)
    return (BLACK, WHITE, WHITE, WHITE)


def compile_map(
    path: Path,
    chars: list[list[list[int]]],
    tiles: list[bytes],
    tile_ids: dict[bytes, int],
) -> tuple[bytes, dict[str, object]]:
    root, flattened = flatten_map(path)
    role = next(
        (item.get("value") for item in root.findall("./properties/property")
         if item.get("name") == "screen-role"),
        path.stem,
    )
    ranges = tileset_ranges(root, path)
    rotated = [rotate_ccw(tile) for tile in chars]
    output = bytearray()
    for index, gid_with_flags in enumerate(flattened):
        x = index % SCREEN_WIDTH
        y = index // SCREEN_WIDTH
        if not (gid_with_flags & GID_MASK):
            packed = bytes(TILE_BYTES)
        else:
            if gid_with_flags & FLIP_D:
                raise ValueError(f"{path}: diagonal tile flips are unsupported")
            gid = gid_with_flags & GID_MASK
            tileset = next(
                (item for item in ranges
                 if int(item["firstgid"]) <= gid <= int(item["lastgid"])),
                None,
            )
            if tileset is None:
                raise ValueError(f"{path}: GID {gid} is not in a tileset")
            if (tileset["name"] != "chars_raw2bpp" or
                    tileset["tilewidth"] != TILE_SIZE or
                    tileset["tileheight"] != TILE_SIZE):
                raise ValueError(f"{path}: unsupported tileset {tileset['name']!r}")
            sheet_index = gid - int(tileset["firstgid"])
            code = (sheet_index % 16) * 32 + (31 - sheet_index // 16)
            tile = transform(
                rotated[code], bool(gid_with_flags & FLIP_H),
                bool(gid_with_flags & FLIP_V),
            )
            packed = pack_tile(tile if role == "attract" else recolor(
                tile, presentation_pen_map(role, x, y)
            ))
        tile_id = tile_ids.setdefault(packed, len(tiles))
        if tile_id == len(tiles):
            tiles.append(packed)
        if tile_id > 255:
            raise ValueError("presentation atlas exceeds one-byte tile IDs")
        output.append(tile_id)
    return bytes(output), {"role": role, "path": str(path)}


def encode_map(data: bytes) -> bytes:
    """Encode a tile-index map as count/value pairs."""
    encoded = bytearray()
    index = 0
    while index < len(data):
        value = data[index]
        end = index + 1
        while end < len(data) and data[end] == value and end - index < 255:
            end += 1
        encoded.extend((end - index, value))
        index = end
    return bytes(encoded)


def coin_tile() -> bytes:
    """Create the small native coin glyph used on the ranking screen."""
    pattern = (
        "..YYYY..",
        ".YWWWWY.",
        "YWWWWWWY",
        "YWWWWWWY",
        "YWWWWWWY",
        "YWWWWWWY",
        ".YWWWWY.",
        "..YYYY..",
    )
    pixels = [[BLACK if value == "." else YELLOW if value == "Y" else WHITE
               for value in row] for row in pattern]
    return pack_tile(pixels)


def emit_include(path: Path, maps: list[bytes], tiles: list[bytes],
                 encoded_maps: list[bytes], manifest: dict[str, object],
                 chars: list[list[list[int]]]) -> None:
    lines = [
        "; Generated by scripts/build_presentation.py; do not edit.",
        f"PRESENTATION_MAP_COUNT equ {len(maps)}",
        f"PRESENTATION_MAP_BYTES equ {MAP_BYTES}",
        f"PRESENTATION_TILE_BYTES equ {TILE_BYTES}",
        f"PRESENTATION_TILE_COUNT equ {len(tiles)}",
        f"PRESENTATION_COLD_PAGE equ ${COLD_PAGE:02X}",
        f"PRESENTATION_COLD_PAGE_COUNT equ {COLD_PAGE_COUNT}",
        f"PRESENTATION_COLD_SIZE equ {manifest['cold_payload']['bytes']}",
        f"PRESENTATION_TILE_ATLAS_OFFSET equ {manifest['tile_atlas_offset']}",
        f"PRESENTATION_TILE_OFFSET equ {manifest['tile_atlas_offset']}",
        f"PRESENTATION_COLD_ONLY_TILE_COUNT equ {manifest['cold_only_tile_count']}",
        f"PRESENTATION_GAMEPLAY_TILE_BASE equ {manifest['gameplay_tile_base']}",
        f"PRESENTATION_GAMEPLAY_LOOKUP_OFFSET equ {manifest['gameplay_lookup_offset']}",
        f"PRESENTATION_GAMEPLAY_LOOKUP_BYTES equ {manifest['gameplay_lookup_bytes']}",
        f"PRESENTATION_ATTRACT_SURFACE_PAGE equ ${ATTRACT_ACTOR_SURFACE_PAGE:02X}",
        f"PRESENTATION_ATTRACT_SURFACE_ADDRESS equ ${ATTRACT_ACTOR_SURFACE_ADDRESS:04X}",
        f"PRESENTATION_ATTRACT_SURFACE_BYTES equ {manifest['attract_actor_surfaces']['bytes']}",
        f"PRESENTATION_ATTRACT_DESTINATION_ADDRESS equ ${ATTRACT_ACTOR_DESTINATION_ADDRESS:04X}",
        f"PRESENTATION_ATTRACT_PHASE_POINTER_ADDRESS equ ${ATTRACT_ACTOR_PHASE_POINTER_ADDRESS:04X}",
        f"PRESENTATION_MAP_OUTPUT_OFFSET equ ${MAP_OUTPUT_OFFSET:04X}",
        "",
    ]
    for index, name in enumerate(MAP_NAMES):
        lines.append(f"PRESENTATION_MAP_{name.upper().replace('-', '_')} equ {index}")
    lines.append("")
    lines.append("; Compressed map stream offsets and lengths in the cold payload.")
    for index, encoded in enumerate(encoded_maps):
        lines.append(
            f"PRESENTATION_MAP_STREAM_{index} equ "
            f"${manifest['map_stream_offsets'][index]:04X}"
        )
        lines.append(
            f"PRESENTATION_MAP_STREAM_{index}_BYTES equ {len(encoded)}"
        )
    lines.append(f"PRESENTATION_COIN_TILE equ {manifest['coin_tile']}")
    rotated = [rotate_ccw(tile) for tile in chars]
    for code in range(37):
        packed = pack_tile(recolor(rotated[code], (BLACK, WHITE, WHITE, WHITE)))
        lines.append(f"PRESENTATION_GLYPH_{code} equ {tiles.index(packed)}")
    for index, destination in enumerate(manifest["coin_destinations"]):
        lines.append(f"PRESENTATION_COIN_DST_{index} equ ${destination:04X}")
    lines.extend((
        "PRESENTATION_COIN_SLOT_COUNT equ 9",
        "; Authored high-score coin overlay positions, row-major cell offsets.",
        "; Compile-time constants avoid placing metadata before the copied entry point.",
    ))
    for index, (row, column) in enumerate(
        ((2, 33), (4, 33), (6, 33), (8, 33),
         (10, 33), (12, 33), (14, 33), (16, 33), (18, 33))
    ):
        lines.append(
            f"PRESENTATION_COIN_SLOT_{index} equ ${row * SCREEN_WIDTH + column:04X}"
        )
    lines.extend((
        "",
        "; Nine fixed seven-character session records live in PAR5 page $34.",
        "PRESENTATION_HIGHSCORE_BASE equ $AF84",
        "PRESENTATION_HIGHSCORE_RECORD_BYTES equ 10",
        "PRESENTATION_HIGHSCORE_SCORE_BYTES equ 3",
        "PRESENTATION_HIGHSCORE_NAME_BYTES equ 7",
        "PRESENTATION_HIGHSCORE_COUNT equ 9",
    ))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="ascii")


def main() -> None:
    args = parse_args()
    chars = load_chars(args.chars)
    sprites = json.loads(args.gameplay_sprites.read_text(encoding="utf-8"))
    if isinstance(sprites, dict):
        sprites = sprites.get("sprites", sprites)
    if not isinstance(sprites, list) or len(sprites) != 128:
        raise ValueError(f"{args.gameplay_sprites} must contain 128 sprites")
    actors = parse_attract_actors(args.tiled_dir / MAP_FILES["attract"])
    _gameplay_map, gameplay_tiles, *_ = compile_screen(
        args.gameplay_map,
        args.gameplay_maze,
        args.gameplay_chars,
        args.gameplay_sprites,
    )
    tiles: list[bytes] = []
    tile_ids: dict[bytes, int] = {}
    maps: list[bytes] = []
    map_info: list[dict[str, object]] = []
    for name in MAP_NAMES:
        map_bytes, info = compile_map(
            args.tiled_dir / MAP_FILES[name], chars, tiles, tile_ids
        )
        maps.append(map_bytes)
        info.update({
            "name": name,
            "bytes": len(map_bytes),
            "sha256": hashlib.sha256(map_bytes).hexdigest(),
        })
        map_info.append(info)

    coin_id = tile_ids.setdefault(coin_tile(), len(tiles))
    if coin_id == len(tiles):
        tiles.append(coin_tile())

    gameplay_tile_ids = {tile: index for index, tile in enumerate(gameplay_tiles)}
    cold_tile_ids = [
        tile_id for tile_id, tile in enumerate(tiles)
        if tile not in gameplay_tile_ids
    ]
    gameplay_match_ids = [
        tile_id for tile_id, tile in enumerate(tiles)
        if tile in gameplay_tile_ids
    ]
    ordered_ids = cold_tile_ids + gameplay_match_ids
    remap = {old_id: new_id for new_id, old_id in enumerate(ordered_ids)}
    maps = [bytes(remap[tile_id] for tile_id in data) for data in maps]
    for info, data in zip(map_info, maps):
        info["sha256"] = hashlib.sha256(data).hexdigest()
    tiles = [tiles[tile_id] for tile_id in ordered_ids]
    coin_id = remap[coin_id]
    cold_only_tiles = tiles[:len(cold_tile_ids)]
    gameplay_lookup = bytes(
        gameplay_tile_ids[tiles[tile_id]]
        for tile_id in range(len(cold_tile_ids), len(tiles))
    )
    encoded_maps = [encode_map(data) for data in maps]
    tile_atlas = b"".join(cold_only_tiles)
    tile_atlas_offset = 0
    gameplay_lookup_offset = len(tile_atlas)
    map_stream_offset = gameplay_lookup_offset + len(gameplay_lookup)
    map_stream_offsets = []
    encoded_stream = bytearray()
    for encoded in encoded_maps:
        map_stream_offsets.append(map_stream_offset + len(encoded_stream))
        encoded_stream.extend(encoded)
    attract_destinations = b"".join(
        int(actor["destination"]).to_bytes(2, "big") for actor in actors
    )
    attract_surfaces = compile_attract_surfaces(maps[0], tiles, sprites, actors)
    attract_frames = compose_attract_frames(maps[0], tiles, attract_surfaces, actors)
    attract_phase_pointers = b"".join(
        (ATTRACT_ACTOR_SURFACE_ADDRESS + phase * 896).to_bytes(2, "big")
        for phase in ATTRACT_ACTOR_PHASES
    )
    attract_compressed = lzss_compress(attract_surfaces)
    attract_metadata = attract_destinations + attract_phase_pointers
    cold_payload = tile_atlas + gameplay_lookup + bytes(encoded_stream)
    if len(cold_payload) > COLD_PAYLOAD_LIMIT:
        raise ValueError(
            f"presentation cold payload is {len(cold_payload)} bytes; "
            f"limit is {COLD_PAYLOAD_LIMIT}"
        )
    manifest = {
        "maps": map_info,
        "map_count": len(maps),
        "map_bytes": MAP_BYTES,
        "tile_count": len(tiles),
        "tile_bytes": TILE_BYTES,
        "tile_atlas_offset": tile_atlas_offset,
        "cold_only_tile_count": len(cold_only_tiles),
        "gameplay_tile_base": len(cold_only_tiles),
        "gameplay_lookup_offset": gameplay_lookup_offset,
        "gameplay_lookup_bytes": len(gameplay_lookup),
        "gameplay_tile_count": len(gameplay_tiles),
        "map_output_offset": MAP_OUTPUT_OFFSET,
        "map_stream_offsets": map_stream_offsets,
        "map_stream_bytes": [len(encoded) for encoded in encoded_maps],
        "map_stream_total_bytes": len(encoded_stream),
        "attract_actor_destinations": {
            "bytes": len(attract_destinations),
            "count": len(actors),
            "storage": "helper-table",
            "sha256": hashlib.sha256(attract_destinations).hexdigest(),
        },
        "attract_actor_surfaces": {
            "bytes": len(attract_surfaces),
            "actor_bytes": ATTRACT_ACTOR_BYTES,
            "unique_phases": len(ATTRACT_ACTOR_PHASES),
            "page": ATTRACT_ACTOR_SURFACE_PAGE,
            "address": ATTRACT_ACTOR_SURFACE_ADDRESS,
            "storage": "loader-copy-to-page-$3C-$A000",
            "sha256": hashlib.sha256(attract_surfaces).hexdigest(),
            "actors": actors,
            "phase_frame_sha256": [hashlib.sha256(frame).hexdigest()
                                   for frame in attract_frames],
            "phase_crop_sha256": [
                [hashlib.sha256(attract_surfaces[
                    (phase * len(actors) + actor_index) * ATTRACT_ACTOR_BYTES:
                    (phase * len(actors) + actor_index + 1) * ATTRACT_ACTOR_BYTES
                ]).hexdigest() for actor_index in range(len(actors))]
                for phase in ATTRACT_ACTOR_PHASES
            ],
        },
        "attract_actor_bundle": {
            "compressed_bytes": len(attract_compressed),
            "expanded_bytes": len(attract_surfaces),
            "destination_address": ATTRACT_ACTOR_SURFACE_ADDRESS,
            "destination_table_address": ATTRACT_ACTOR_DESTINATION_ADDRESS,
            "phase_pointer_address": ATTRACT_ACTOR_PHASE_POINTER_ADDRESS,
            "compressed_sha256": hashlib.sha256(attract_compressed).hexdigest(),
            "metadata_bytes": len(attract_metadata),
            "metadata_sha256": hashlib.sha256(attract_metadata).hexdigest(),
        },
        "coin_tile": coin_id,
        "coin_destinations": [
            0x2000 + row * 1280 + 33 * 8
            for row in (2, 4, 6, 8, 10, 12, 14, 16, 18)
        ],
        "cold_page": COLD_PAGE,
        "cold_page_count": COLD_PAGE_COUNT,
        "cold_payload_limit": COLD_PAYLOAD_LIMIT,
        "cold_payload": {
            "bytes": len(cold_payload),
            "sha256": hashlib.sha256(cold_payload).hexdigest(),
        },
        "coin_slots": [2 * SCREEN_WIDTH + 33, 4 * SCREEN_WIDTH + 33,
                       6 * SCREEN_WIDTH + 33, 8 * SCREEN_WIDTH + 33,
                       10 * SCREEN_WIDTH + 33, 12 * SCREEN_WIDTH + 33,
                       14 * SCREEN_WIDTH + 33, 16 * SCREEN_WIDTH + 33,
                       18 * SCREEN_WIDTH + 33],
        "static_frame_sha256": [hashlib.sha256(title_framebuffer(data, tiles)).hexdigest()
                                for data in maps],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(cold_payload)
    args.actor_record_output.parent.mkdir(parents=True, exist_ok=True)
    args.actor_record_output.write_bytes(attract_metadata)
    args.actor_underlay_output.parent.mkdir(parents=True, exist_ok=True)
    args.actor_underlay_output.write_bytes(attract_compressed)
    args.manifest_output.parent.mkdir(parents=True, exist_ok=True)
    args.manifest_output.write_text(json.dumps(manifest, indent=2) + "\n",
                                    encoding="ascii")
    emit_include(args.include_output, maps, tiles, encoded_maps, manifest, chars)
    print(
        f"presentation: {len(maps)} maps, {len(tiles)} shared tiles, "
        f"{len(cold_payload)} cold bytes, "
        f"{manifest['cold_payload']['sha256']}"
    )


if __name__ == "__main__":
    main()
