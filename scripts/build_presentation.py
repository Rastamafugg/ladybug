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
ATTRACT_ACTOR_RECORDS = (
    (0x661C, (66, 65, 64, 65)),
    (0x2F24, (128, 129, 12, 129)),
    (0x7F34, (22, 21, 20, 21)),
    (0x5238, (34, 33, 32, 33)),
)
ATTRACT_ACTOR_UNDERLAY_BYTES = 128


def compile_attract_underlays(attract_map: bytes, tiles: list[bytes]) -> bytes:
    framebuffer = bytearray(0x8000)
    for cell, tile_id in enumerate(attract_map):
        row, column = divmod(cell, SCREEN_WIDTH)
        tile = tiles[tile_id]
        destination = row * 160 + column * 4
        for tile_row in range(8):
            start = destination + tile_row * 160
            framebuffer[start:start + 4] = tile[tile_row * 4:tile_row * 4 + 4]
    underlays = bytearray()
    for destination, _indexes in ATTRACT_ACTOR_RECORDS:
        offset = destination - 0x2000
        for row in range(16):
            underlays.extend(framebuffer[offset + row * 160:offset + row * 160 + 8])
    return bytes(underlays)


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
        f"PRESENTATION_ATTRACT_ACTOR_OFFSET equ ${manifest['attract_actor_records']['offset']:04X}",
        f"PRESENTATION_ATTRACT_ACTOR_BYTES equ {manifest['attract_actor_records']['bytes']}",
        f"PRESENTATION_ATTRACT_UNDERLAY_BYTES equ {manifest['attract_actor_underlays']['bytes']}",
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
    attract_actor_records = b"".join(
        destination.to_bytes(2, "big") + bytes(indexes)
        for destination, indexes in ATTRACT_ACTOR_RECORDS
    )
    attract_actor_offset = map_stream_offset + len(encoded_stream)
    attract_underlays = compile_attract_underlays(maps[0], tiles)
    cold_payload = tile_atlas + gameplay_lookup + bytes(encoded_stream) + attract_actor_records
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
        "attract_actor_records": {
            "offset": attract_actor_offset,
            "bytes": len(attract_actor_records),
            "count": len(ATTRACT_ACTOR_RECORDS),
            "record_bytes": 6,
            "records": [
                {"destination": destination, "sparse_indexes": list(indexes)}
                for destination, indexes in ATTRACT_ACTOR_RECORDS
            ],
        },
        "attract_actor_underlays": {
            "offset": None,
            "bytes": len(attract_underlays),
            "actor_bytes": ATTRACT_ACTOR_UNDERLAY_BYTES,
            "storage": "loader-copy-to-$B000",
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
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(cold_payload)
    args.actor_record_output.parent.mkdir(parents=True, exist_ok=True)
    args.actor_record_output.write_bytes(attract_actor_records)
    args.actor_underlay_output.parent.mkdir(parents=True, exist_ok=True)
    args.actor_underlay_output.write_bytes(attract_underlays)
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
