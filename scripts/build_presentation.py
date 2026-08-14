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
    DARK_RED,
    FLIP_D,
    FLIP_H,
    FLIP_V,
    GID_MASK,
    GREEN,
    GREY,
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
    compile_death_sprites,
    compile_screen,
    encode_sparse_native,
    expand_sprite,
    load_chars,
    pack_tile,
    pack_sprite_2bpp,
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
DEVELOPMENT_PLACEHOLDER_MAPS = ("game-over", "enter-high-score")
RELEASE_PLACEHOLDER_MAPS = ("instructions",)
PAGE_BYTES = 0x2000
COLD_PAGE = 0x3A
COLD_PAGE_COUNT = 4
MAP_BYTES = SCREEN_WIDTH * SCREEN_HEIGHT
TILE_BYTES = 32
MAP_OUTPUT_OFFSET = 0x4000
COLD_PAYLOAD_LIMIT = 10874
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
    (11, 3): 98,
    (35, 4): 5,
    (27, 5): 65,
    (3, 9): 68,
    (10, 15): 32,
    (33, 19): 35,
    (5, 20): 2,
}
# The (11,3) family crosses to the preceding sheet column for its row-0
# wrap frame. Keys use actor cell and stored phase; values are sheet row/column.
ATTRACT_ACTOR_PHASE_OVERRIDES = {
    ((11, 3), 0): (0, 1),
}
ATTRACT_ACTOR_SURFACE_PAGE = 0x3C
ATTRACT_ACTOR_SURFACE_ADDRESS = 0xA000
ATTRACT_ACTOR_BYTES = 128
ATTRACT_ACTOR_PHASES = (0, 1, 2)
ATTRACT_ACTOR_DESTINATION_ADDRESS = 0xAA80
ATTRACT_ACTOR_PHASE_POINTER_ADDRESS = 0xAA8E
INSTRUCTION_REFERENCE = (
    Path(__file__).resolve().parents[1]
    / "assets" / "arcade" / "instruction_reference.json"
)
INSTRUCTION_STATIC_LAYERS = (
    "Arcade Maze Border",
    "CoCo Side HUD",
    "Instructions Overlay",
)
INSTRUCTION_METADATA_LAYER = "Sprite Locations"
INSTRUCTION_ANCHORS = ((10, 8), (10, 11), (10, 14))
INSTRUCTION_LIFE_ROOT = (28, 7)
INSTRUCTION_COIN_ROOT = (28, 10)
INSTRUCTION_ANGEL_ROOT = (28, 14)
INSTRUCTION_CUCUMBER_MARKER = (32, 13)
INSTRUCTION_MULTIPLIER_ROOTS = ((27, 17), (27, 20))
INSTRUCTION_TARGETS = (
    ((13, 7), (1, 4)), ((15, 7), (2, 4)), ((17, 7), (3, 4)),
    ((19, 7), (4, 4)), ((21, 7), (5, 4)),
    ((13, 10), (1, 1)), ((15, 10), (2, 1)), ((17, 10), (3, 1)),
    ((19, 10), (4, 1)), ((21, 10), (5, 1)), ((23, 10), (6, 1)),
    ((25, 10), (7, 1)),
    ((13, 13), (1, 7)), ((17, 13), (3, 7)), ((21, 13), (5, 7)),
    ((28, 13), (0, 0)),
)
INSTRUCTION_EVENT_BYTES = 12
INSTRUCTION_STOPS = (
    (13, 8), (15, 8), (17, 8), (19, 8), (21, 8),
    (13, 11), (15, 11), (17, 11), (19, 11), (21, 11), (23, 11),
    (25, 11), (13, 14), (17, 14), (21, 14), INSTRUCTION_ANGEL_ROOT,
)
PRESENTATION_LAYER_CONTRACTS = {
    "attract": {
        "static": ("Attract Title and Prompts",),
        "metadata": (),
        "runtime": ("Sprite Animations",),
        "deferred": ("Logo Frame 1", "Logo Frame 2"),
    },
    "instructions": {
        "static": INSTRUCTION_STATIC_LAYERS,
        "metadata": (INSTRUCTION_METADATA_LAYER,),
        "runtime": (),
        "deferred": (),
    },
    "level-start": {
        "static": ("Level Start Panel", "CoCo Side HUD"),
        "metadata": ("Sprite Locations",),
        "runtime": (),
        "deferred": (),
    },
    "high-score": {
        "static": ("High Score Table and Branding",),
        "metadata": ("Coin Positions",),
        "runtime": (),
        "deferred": ("Logo Frame 1", "Logo Frame 2"),
    },
    "game-over": {
        "static": ("Arcade Maze Border", "CoCo Side HUD", "Game Over Overlay"),
        "metadata": (),
        "runtime": (),
        "deferred": (),
    },
    "enter-high-score": {
        "static": (
            "Arcade Maze Border", "CoCo Side HUD", "Enter High Score Overlay",
        ),
        "metadata": (),
        "runtime": (),
        "deferred": (),
    },
}
INSTRUCTION_CHARACTER_METADATA = {
    (28, 7): 456, (29, 7): 440, (28, 8): 488, (29, 8): 472,
    (28, 10): 376, (29, 10): 328, (28, 11): 296, (29, 11): 344,
    (27, 17): 147, (28, 17): 417,
    (27, 20): 147, (28, 20): 417,
}
INSTRUCTION_RAW_SPRITE_MARKERS = {
    **{cell: 0xA0000221 for cell in INSTRUCTION_ANCHORS},
    (13, 8): 593, (15, 8): 593, (17, 8): 593,
    (19, 8): 593, (21, 8): 593,
    (13, 11): 593, (15, 11): 593, (17, 11): 593,
    (19, 11): 593, (21, 11): 593, (23, 11): 593, (25, 11): 593,
    INSTRUCTION_CUCUMBER_MARKER: 633,
    (13, 14): 593, (17, 14): 593, (21, 14): 593,
    INSTRUCTION_ANGEL_ROOT: 636,
}
LEVEL_START_METADATA = {
    **{(x, 2): 497 for x in range(33, 39)},
    **{(x, 6): 497 for x in range(33, 39)},
    (16, 7): 633,
    (19, 7): 481, (20, 7): 497, (21, 7): 497, (22, 7): 497,
    (33, 9): 497,
    (32, 13): 633,
    (35, 13): 481, (36, 13): 497, (37, 13): 497, (38, 13): 497,
}


def lzss_compress(data: bytes) -> bytes:
    """Encode a minimum-byte bounded 12-bit-offset, 4-bit-length LZSS stream."""
    matches: list[dict[int, int]] = []
    for cursor in range(len(data)):
        offsets: dict[int, int] = {}
        for candidate in range(max(0, cursor - 4095), cursor):
            length = 0
            distance = cursor - candidate
            while (length < 18 and cursor + length < len(data) and
                   data[candidate + length % distance] == data[cursor + length]):
                length += 1
            for matched in range(3, length + 1):
                offsets.setdefault(matched, distance)
        matches.append(offsets)

    infinity = len(data) * 3
    costs = [[infinity] * 8 for _ in range(len(data) + 1)]
    choices: list[list[tuple[int, int] | None]] = [
        [None] * 8 for _ in range(len(data))
    ]
    costs[-1] = [0] * 8
    for cursor in range(len(data) - 1, -1, -1):
        for slot in range(8):
            group_byte = 1 if slot == 0 else 0
            next_slot = (slot + 1) % 8
            best_cost = group_byte + 1 + costs[cursor + 1][next_slot]
            best_choice = (1, 0)
            for length, distance in matches[cursor].items():
                cost = group_byte + 2 + costs[cursor + length][next_slot]
                if cost < best_cost or (cost == best_cost and length > best_choice[0]):
                    best_cost = cost
                    best_choice = (length, distance)
            costs[cursor][slot] = best_cost
            choices[cursor][slot] = best_choice

    output = bytearray()
    cursor = 0
    while cursor < len(data):
        flag_offset = len(output)
        output.append(0)
        flags = 0
        for bit in range(8):
            if cursor >= len(data):
                break
            choice = choices[cursor][bit]
            if choice is None:
                raise AssertionError("missing LZSS parse choice")
            length, distance = choice
            if length >= 3:
                token = (distance << 4) | (length - 3)
                output.extend(token.to_bytes(2, "big"))
                cursor += length
            else:
                flags |= 1 << bit
                output.append(data[cursor])
                cursor += 1
        output[flag_offset] = flags
    if len(output) != costs[0][0]:
        raise AssertionError("LZSS parse size differs from dynamic-programming optimum")
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


def blend_native_surface(
    framebuffer: bytearray, destination: int, surface: bytes,
    width: int = 8, rows: int = 16,
) -> None:
    """Blend a packed native surface into a presentation framebuffer."""
    offset = destination - 0x2000
    for row in range(rows):
        for column in range(width):
            source = surface[row * width + column]
            target = framebuffer[offset + row * 160 + column]
            high = source & 0xF0 or target & 0xF0
            low = source & 0x0F or target & 0x0F
            framebuffer[offset + row * 160 + column] = high | low


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
            phase_cell = ATTRACT_ACTOR_PHASE_OVERRIDES.get(
                (tuple(actor["cell"]), phase), (phase_rows[phase], column)
            )
            code = sheet_code(*phase_cell)
            sprite = sprite_transform(rotate_ccw(sprites[code]), int(actor["flags"]))
            # Raw sprite pens are dark grey, light grey, white for 1, 2, 3.
            # The authored triples are specified as white, light grey, dark grey.
            colours = [BLACK, actor["colours"][2], actor["colours"][1],
                       actor["colours"][0]]
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
    parser.add_argument("--demo-route", type=Path, required=True)
    parser.add_argument("--demo-walk", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--include-output", type=Path, required=True)
    parser.add_argument("--manifest-output", type=Path, required=True)
    parser.add_argument("--actor-record-output", type=Path, required=True)
    parser.add_argument("--actor-underlay-output", type=Path, required=True)
    parser.add_argument("--development-profile", type=int, choices=(0, 1), default=0)
    return parser.parse_args()


def screen_role(root: ET.Element, path: Path) -> str:
    return next(
        (item.get("value") for item in root.findall("./properties/property")
         if item.get("name") == "screen-role"),
        path.stem,
    )


def layer_records(layer: ET.Element) -> dict[tuple[int, int], int]:
    cells = parse_csv(layer.find("data"), layer.get("name", ""))
    return {
        (index % SCREEN_WIDTH, index // SCREEN_WIDTH): gid
        for index, gid in enumerate(cells) if gid & GID_MASK
    }


def require_records(
    path: Path, label: str, actual: dict[tuple[int, int], int],
    expected: dict[tuple[int, int], int],
) -> None:
    if actual == expected:
        return
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    wrong = sorted(cell for cell in set(actual) & set(expected)
                   if actual[cell] != expected[cell])
    raise ValueError(
        f"{path}: {label} contract mismatch; "
        f"missing={missing}, extra={extra}, wrong={wrong}"
    )


def validate_layer_tilesets(
    path: Path, root: ET.Element, layer: ET.Element, allowed: tuple[str, ...],
) -> None:
    ranges = tileset_ranges(root, path)
    for cell, gid_with_flags in layer_records(layer).items():
        gid = gid_with_flags & GID_MASK
        tileset = next(
            (item for item in ranges
             if int(item["firstgid"]) <= gid <= int(item["lastgid"])),
            None,
        )
        name = None if tileset is None else str(tileset["name"])
        if name not in allowed:
            raise ValueError(
                f"{path}: layer {layer.get('name')!r} cell {cell} uses "
                f"unsupported tileset {name!r}; expected one of {allowed}"
            )


def validate_presentation_layers(
    root: ET.Element, path: Path,
) -> dict[str, object]:
    role = screen_role(root, path)
    contract = PRESENTATION_LAYER_CONTRACTS.get(role)
    if contract is None:
        raise ValueError(f"{path}: unsupported presentation screen role {role!r}")
    layers = root.findall("layer")
    names = [layer.get("name", "") for layer in layers]
    required = tuple(name for owner in contract.values() for name in owner)
    missing = [name for name in required if names.count(name) != 1]
    unexpected = [name for name in names if name not in required]
    if missing or unexpected:
        raise ValueError(
            f"{path}: {role} layer contract mismatch; "
            f"missing/duplicate={missing}, unexpected={unexpected}"
        )
    by_name = {layer.get("name", ""): layer for layer in layers}
    for name in contract["static"]:
        validate_layer_tilesets(path, root, by_name[name], ("chars_raw2bpp",))
    for name in contract["deferred"]:
        validate_layer_tilesets(path, root, by_name[name], ("chars_raw2bpp",))
    if role == "attract":
        validate_layer_tilesets(
            path, root, by_name["Sprite Animations"], ("sprites_raw2bpp",)
        )
    if role == "high-score":
        validate_layer_tilesets(
            path, root, by_name["Coin Positions"], ("chars_raw2bpp",)
        )
    if role == "instructions":
        records = layer_records(by_name[INSTRUCTION_METADATA_LAYER])
        require_records(
            path, "instruction character and raw-sprite metadata", records,
            {**INSTRUCTION_CHARACTER_METADATA, **INSTRUCTION_RAW_SPRITE_MARKERS},
        )
        validate_layer_tilesets(
            path, root, by_name[INSTRUCTION_METADATA_LAYER],
            ("chars_raw2bpp", "sprites_raw2bpp"),
        )
    if role == "level-start":
        records = layer_records(by_name["Sprite Locations"])
        require_records(path, "level-start metadata", records, LEVEL_START_METADATA)
        validate_layer_tilesets(
            path, root, by_name["Sprite Locations"],
            ("chars_raw2bpp", "sprites_raw2bpp"),
        )
    return {
        "role": role,
        "static_layers": list(contract["static"]),
        "metadata_layers": list(contract["metadata"]),
        "runtime_layers": list(contract["runtime"]),
        "deferred_layers": list(contract["deferred"]),
    }


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
    layer_contract = validate_presentation_layers(root, path)
    layers = root.findall("layer")
    selected = [layer for name in layer_contract["static_layers"]
                for layer in layers if layer.get("name") == name]
    flattened = [0] * MAP_BYTES
    for layer in selected:
        cells = parse_csv(layer.find("data"), layer.get("name", ""))
        for index, gid in enumerate(cells):
            if gid & GID_MASK:
                flattened[index] = gid
    return root, flattened


def presentation_pen_map(role: str, x: int, y: int) -> tuple[int, int, int, int]:
    """Apply the established CoCo palette adaptation to authored raw chars."""
    if x < 8 and y < 9:
        colour = (RED, YELLOW, BLUE)[y // 3]
        if y % 3 == 1 and x != 0:
            colour = GREY
        return (BLACK, colour, colour, colour)
    if x >= 32:
        colour = {
            1: LIGHT_GREEN, 2: WHITE,
            4: RED, 5: RED,
            7: WHITE, 8: WHITE, 9: WHITE,
            10: BLUE, 11: BLUE,
            12: GREEN, 13: WHITE,
        }.get(y, BLACK)
        return (BLACK, colour, colour, colour)
    if role == "level-start" and 8 <= x < 32:
        return (BLACK, PINK, WHITE, PINK)
    if role in ("game-over", "enter-high-score", "high-score"):
        return (BLACK, WHITE, WHITE, WHITE)
    if role == "instructions" and 28 <= x < 30 and 13 <= y < 15:
        return (BLACK, WHITE, WHITE, WHITE)
    if role == "instructions" and 13 <= x < 23 and 13 <= y < 15:
        return (BLACK, PINK, PURPLE, PINK)
    if role == "instructions" and (x in (8, 31) or y in (0, 23)):
        return (BLACK, PINK, WHITE, PINK)
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
    role = screen_role(root, path)
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
    return bytes(output), {
        "role": role,
        "path": str(path),
        "layer_contract": validate_presentation_layers(root, path),
    }


def framebuffer_destination(cell: tuple[int, int]) -> int:
    x, y = cell
    return 0x2000 + y * 1280 + x * 4


def instruction_char_tile(
    root: ET.Element,
    path: Path,
    gid_with_flags: int,
    cell: tuple[int, int],
    chars: list[list[list[int]]],
    pen_map: tuple[int, int, int, int] | None = None,
) -> bytes:
    gid = gid_with_flags & GID_MASK
    ranges = tileset_ranges(root, path)
    tileset = next(
        (item for item in ranges
         if int(item["firstgid"]) <= gid <= int(item["lastgid"])),
        None,
    )
    if tileset is None or tileset["name"] != "chars_raw2bpp":
        raise ValueError(f"{path}: instruction metadata GID {gid} is not a char tile")
    if gid_with_flags & FLIP_D:
        raise ValueError(f"{path}: instruction char metadata uses a diagonal flip")
    sheet_index = gid - int(tileset["firstgid"])
    code = (sheet_index % 16) * 32 + (31 - sheet_index // 16)
    tile = transform(
        rotate_ccw(chars[code]), bool(gid_with_flags & FLIP_H),
        bool(gid_with_flags & FLIP_V),
    )
    x, y = cell
    return pack_tile(recolor(
        tile,
        pen_map if pen_map is not None
        else presentation_pen_map("instructions", x, y),
    ))


def instruction_sprite(
    root: ET.Element, path: Path, gid_with_flags: int,
    sprites: list[list[list[int]]],
) -> tuple[list[list[int]], int]:
    gid = gid_with_flags & GID_MASK
    tileset = next(
        (item for item in tileset_ranges(root, path)
         if int(item["firstgid"]) <= gid <= int(item["lastgid"])),
        None,
    )
    if tileset is None or tileset["name"] != "sprites_raw2bpp":
        raise ValueError(f"{path}: instruction sprite GID {gid} is not raw sprite data")
    tile = gid - int(tileset["firstgid"])
    code = sheet_code(tile // 16, tile % 16)
    pixels = sprite_transform(
        rotate_ccw(sprites[code]), gid_with_flags & ~GID_MASK
    )
    return pixels, code


def register_tile(tile: bytes, tiles: list[bytes], tile_ids: dict[bytes, int]) -> int:
    tile_id = tile_ids.setdefault(tile, len(tiles))
    if tile_id == len(tiles):
        tiles.append(tile)
    if tile_id > 255:
        raise ValueError("presentation atlas exceeds one-byte tile IDs")
    return tile_id


def parse_instruction_contract(
    path: Path,
    chars: list[list[list[int]]],
    sprites: list[list[list[int]]],
    tiles: list[bytes],
    tile_ids: dict[bytes, int],
) -> dict[str, object]:
    root = ET.parse(path).getroot()
    layers = {layer.get("name", ""): layer for layer in root.findall("layer")}
    metadata = layers.get(INSTRUCTION_METADATA_LAYER)
    if metadata is None:
        raise ValueError(f"{path}: missing {INSTRUCTION_METADATA_LAYER} layer")
    cells = parse_csv(metadata.find("data"), INSTRUCTION_METADATA_LAYER)
    records = layer_records(metadata)
    require_records(
        path, "Sprite Locations", records,
        {**INSTRUCTION_CHARACTER_METADATA, **INSTRUCTION_RAW_SPRITE_MARKERS},
    )

    cucumber_gid = records[INSTRUCTION_CUCUMBER_MARKER]
    cucumber_pixels, cucumber_code = instruction_sprite(
        root, path, cucumber_gid, sprites
    )
    cucumber_native = expand_sprite(
        pack_sprite_2bpp(cucumber_pixels), (BLACK, DARK_RED, PURPLE, YELLOW)
    )
    cucumber_root = (
        INSTRUCTION_CUCUMBER_MARKER[0], INSTRUCTION_CUCUMBER_MARKER[1] - 1
    )
    cucumber_stream = encode_sparse_native(cucumber_native, 16, 8)

    overlay = layers["Instructions Overlay"]
    overlay_cells = parse_csv(overlay.find("data"), overlay.get("name", ""))
    hud_layer = layers["CoCo Side HUD"]
    hud_cells = parse_csv(hud_layer.find("data"), hud_layer.get("name", ""))
    for target, hud in INSTRUCTION_TARGETS:
        for dy in range(2):
            for dx in range(2):
                index = (target[1] + dy) * SCREEN_WIDTH + target[0] + dx
                if not overlay_cells[index] & GID_MASK:
                    raise ValueError(f"{path}: incomplete target at {target}")
        if hud != (0, 0):
            index = hud[1] * SCREEN_WIDTH + hud[0]
            if not hud_cells[index] & GID_MASK:
                raise ValueError(f"{path}: missing HUD target at {hud}")

    reward_tiles: dict[str, list[int]] = {}
    reward_pen_maps = {
        "life": (BLACK, GREEN, DARK_RED, YELLOW),
        "coin": (BLACK, WHITE, WHITE, GREY),
    }
    for name, root_cell in (("life", INSTRUCTION_LIFE_ROOT),
                            ("coin", INSTRUCTION_COIN_ROOT)):
        ids = []
        for dy in range(2):
            for dx in range(2):
                cell = (root_cell[0] + dx, root_cell[1] + dy)
                ids.append(register_tile(
                    instruction_char_tile(
                        root, path, records[cell], cell, chars,
                        reward_pen_maps[name],
                    ),
                    tiles, tile_ids,
                ))
        reward_tiles[name] = ids

    rotated = [rotate_ccw(tile) for tile in chars]
    value_tiles: dict[str, list[int]] = {}
    for colour, value in (("red", 1), ("yellow", 2), ("blue", 3)):
        value_tiles[colour] = [register_tile(
            pack_tile(recolor(rotated[digit], (BLACK, value, value, value))),
            tiles, tile_ids,
        ) for digit in (8, 0, 0) if colour == "red"]
        if colour == "yellow":
            value_tiles[colour] = [register_tile(
                pack_tile(recolor(rotated[digit], (BLACK, value, value, value))),
                tiles, tile_ids,
            ) for digit in (3, 0, 0)]
        if colour == "blue":
            value_tiles[colour] = [register_tile(
                pack_tile(recolor(rotated[digit], (BLACK, value, value, value))),
                tiles, tile_ids,
            ) for digit in (1, 0, 0)]
    black_tile = register_tile(bytes(TILE_BYTES), tiles, tile_ids)
    multiplier_tiles = {
        str(value): [register_tile(instruction_char_tile(
            root, path,
            hud_cells[7 * SCREEN_WIDTH + 1], (1, 7), chars,
            (BLACK, BLUE, BLUE, BLUE),
        ), tiles, tile_ids), register_tile(
            pack_tile(recolor(rotated[value], (BLACK, WHITE, WHITE, WHITE))),
            tiles, tile_ids,
        )]
        for value in (2, 3, 5)
    }

    reference = json.loads(INSTRUCTION_REFERENCE.read_text(encoding="ascii"))
    first = int(reference["instruction_interval"]["first_complete_frame"])
    source_targets = [target for row in reference["rows"]
                      for target in row["targets"]]
    source_targets.append(reference["rows"][2]["skull"])
    if len(source_targets) != len(INSTRUCTION_TARGETS):
        raise ValueError("instruction oracle/TMX target counts differ")
    event_table = bytearray()
    event_manifest = []
    target_colour_streams = []
    row_time_offsets = (0, 90, 180)
    for index, (source, (target, hud), stop) in enumerate(
            zip(source_targets, INSTRUCTION_TARGETS, INSTRUCTION_STOPS)):
        row = 0 if index < 5 else 1 if index < 12 else 2
        motion = int(source["motion_first_frame"]) - first + row_time_offsets[row]
        consume_key = "collision_frame" if index == 15 else "consume_frame"
        consume = int(source[consume_key]) - first + row_time_offsets[row]
        # Trigger-sensitive movements begin only after their collectible
        # colour is visible. Rows two and three must also remain at their
        # authored start for at least one complete red/yellow/blue cycle.
        trigger_colour = 2 if index < 5 else 1 if index < 12 else 3
        if index in (0, 5, 12, 13, 14):
            earliest = motion
            if index == 5:
                earliest = event_manifest[4]["consume_tick"] + 90
            elif index == 12:
                earliest = event_manifest[11]["consume_tick"] + 90
            while not (
                motion >= earliest
                and ((motion - 1) % 90) // 30 + 1 == trigger_colour
                and (motion - 1) % 30 == 0
            ):
                motion += 1
        # Sprite Locations records each actor baseline. Convert the authored
        # stop to the 16x16 framebuffer root used by save/draw.
        goal = framebuffer_destination(stop) - 1280
        target_destination = framebuffer_destination(target)
        hud_destination = 0 if hud == (0, 0) else framebuffer_destination(hud)
        hud_tile_id = 0
        hud_tile_2_id = 0
        if hud_destination:
            hud_index = hud[1] * SCREEN_WIDTH + hud[0]
            hud_tile_id = register_tile(instruction_char_tile(
                root, path, hud_cells[hud_index], hud, chars,
                (BLACK, trigger_colour, trigger_colour, trigger_colour),
            ), tiles, tile_ids)
            if 12 <= index < 15:
                second = (hud[0] + 1, hud[1])
                second_index = second[1] * SCREEN_WIDTH + second[0]
                hud_tile_2_id = register_tile(instruction_char_tile(
                    root, path, hud_cells[second_index], second, chars,
                    (BLACK, trigger_colour, trigger_colour, trigger_colour),
                ), tiles, tile_ids)
        record = (
            motion.to_bytes(2, "big") + consume.to_bytes(2, "big")
            + goal.to_bytes(2, "big") + target_destination.to_bytes(2, "big")
            + hud_destination.to_bytes(2, "big")
            + bytes((hud_tile_2_id, hud_tile_id))
        )
        event_table.extend(record)
        event_manifest.append({
            "index": index,
            "name": source.get("name", "skull"),
            "motion_tick": motion,
            "consume_tick": consume,
            "goal_destination": goal,
            "target_destination": target_destination,
            "hud_destination": hud_destination,
            "hud_tile_id": hud_tile_id,
            "hud_tile_2_id": hud_tile_2_id,
        })
        if index < 15:
            operations = []
            cursor = 0
            operation_count = 0
            for dy in range(2):
                row_tiles = [instruction_char_tile(
                    root, path,
                    overlay_cells[(target[1] + dy) * SCREEN_WIDTH + target[0] + dx],
                    (target[0] + dx, target[1] + dy), chars,
                    (BLACK, 1, 2, 3) if index >= 12 else None,
                ) for dx in range(2)]
                for row in range(8):
                    packed_row = (row_tiles[0][row * 4:row * 4 + 4]
                                  + row_tiles[1][row * 4:row * 4 + 4])
                    for column, value in enumerate(packed_row):
                        high, low = value >> 4, value & 15
                        selector = (
                            (2 if (high == 1 if index >= 12 else high != 0) else 0)
                            | (1 if (low == 1 if index >= 12 else low != 0) else 0)
                        )
                        if selector:
                            destination = (dy * 8 + row) * 160 + column
                            delta = destination - cursor
                            if not 0 <= delta <= 0xFFFF:
                                raise ValueError("instruction colour delta is invalid")
                            if delta <= 0xFE:
                                operations.extend((delta, selector))
                            else:
                                operations.extend((0xFF, delta >> 8,
                                                   delta & 0xFF, selector))
                            operation_count += 1
                            cursor = destination
            target_colour_streams.append(
                bytes((operation_count,)) + bytes(operations)
            )

    death_frames = compile_death_sprites(path.parents[1] / "assets" / "arcade" / "sprites.json")
    death_streams = [encode_sparse_native(
        expand_sprite(frame, (0, RED, RED, RED) if index < 7
                      else (0, WHITE, WHITE, WHITE)), 16, 8,
    ) for index, frame in enumerate(death_frames)]
    angel_gid = records[INSTRUCTION_ANGEL_ROOT]
    angel_pixels, angel_code = instruction_sprite(
        root, path, angel_gid, sprites
    )
    angel_frame = pack_sprite_2bpp(angel_pixels)
    angel_stream = encode_sparse_native(
        expand_sprite(angel_frame, (0, WHITE, WHITE, WHITE)), 16, 8
    )
    return {
        "anchors": [framebuffer_destination(cell) - 1280
                    for cell in INSTRUCTION_ANCHORS],
        "reward_destinations": {
            "life": framebuffer_destination(INSTRUCTION_LIFE_ROOT),
            "coin": framebuffer_destination(INSTRUCTION_COIN_ROOT),
        },
        "reward_tile_ids": reward_tiles,
        "cucumber_destination": framebuffer_destination(cucumber_root),
        "cucumber_source_code": cucumber_code,
        "cucumber_stream": cucumber_stream,
        "cucumber_native": cucumber_native,
        "multiplier_destinations": [framebuffer_destination(cell)
                                    for cell in INSTRUCTION_MULTIPLIER_ROOTS],
        "multiplier_tile_ids": multiplier_tiles,
        "value_destination": framebuffer_destination((16, 20)),
        "value_tile_ids": value_tiles,
        "black_tile_id": black_tile,
        "event_table": bytes(event_table),
        "target_colour_streams": target_colour_streams,
        "events": event_manifest,
        "death_streams": death_streams,
        "angel_stream": angel_stream,
        "angel_destination": framebuffer_destination(INSTRUCTION_ANGEL_ROOT) - 1280,
        "angel_source_code": angel_code,
        "death_collision_tick": int(reference["rows"][2]["skull"]["collision_frame"]) - first + 180,
        "angel_tick": int(reference["death_sequence"]["angel_hold"]["first_frame"]) - first + 180,
        "next_screen_tick": int(reference["instruction_interval"]["next_screen_first_partial_frame"]) - first + 180,
        "colour_dwell_frames": int(reference["colour_clock"]["dwell_frames"]),
    }


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


def compile_profile_maps(
    tiled_dir: Path, chars: list[list[list[int]]], tiles: list[bytes],
    tile_ids: dict[bytes, int], development_profile: bool,
) -> tuple[list[bytes], list[dict[str, object]]]:
    """Validate every map while omitting unreachable development-profile maps."""
    maps: list[bytes | None] = []
    map_info: list[dict[str, object]] = []
    placeholder_maps = (
        DEVELOPMENT_PLACEHOLDER_MAPS if development_profile
        else RELEASE_PLACEHOLDER_MAPS
    )
    for name in MAP_NAMES:
        path = tiled_dir / MAP_FILES[name]
        if name in placeholder_maps:
            isolated_tiles: list[bytes] = []
            isolated_ids: dict[bytes, int] = {}
            authored, info = compile_map(
                path, chars, isolated_tiles, isolated_ids
            )
            authored_frame = title_framebuffer(authored, isolated_tiles)
            maps.append(None)
            emission = (
                "development-profile-black-placeholder" if development_profile
                else "release-profile-black-placeholder"
            )
        else:
            authored, info = compile_map(path, chars, tiles, tile_ids)
            authored_frame = title_framebuffer(authored, tiles)
            maps.append(authored)
            emission = "authored"
        info.update({
            "name": name,
            "bytes": len(authored),
            "authored_map_sha256": hashlib.sha256(authored).hexdigest(),
            "authored_frame_sha256": hashlib.sha256(authored_frame).hexdigest(),
            "emission": emission,
        })
        map_info.append(info)
    if placeholder_maps:
        black_tile_id = tile_ids.get(bytes(TILE_BYTES))
        if black_tile_id is None:
            black_tile_id = register_tile(bytes(TILE_BYTES), tiles, tile_ids)
        for name in placeholder_maps:
            maps[MAP_NAMES.index(name)] = bytes((black_tile_id,)) * MAP_BYTES
    if any(data is None for data in maps):
        raise AssertionError("presentation profile left an unresolved map slot")
    return [data for data in maps if data is not None], map_info


def load_demo_route(path: Path) -> tuple[bytes, dict[str, object]]:
    """Validate and convert the arcade ROM direction stream to CoCo ordinals."""
    record = json.loads(path.read_text(encoding="ascii"))
    source = bytes(record["bytes"])
    if len(source) != 188 or source[-1] != 0xFF:
        raise ValueError(f"{path}: demo route must contain 187 actions plus $FF")
    if hashlib.sha256(source).hexdigest() != record["route_sha256"]:
        raise ValueError(f"{path}: demo route SHA-256 differs")
    if record["rom_offset"] != 0x0EF8 or record["action_count"] != 187:
        raise ValueError(f"{path}: demo route provenance differs")
    if source[0] != 0 or any(value not in (1, 2, 4, 8) for value in source[1:-1]):
        raise ValueError(f"{path}: demo route contains an illegal direction")
    conversion = {0: 0xFF, 1: 3, 2: 2, 4: 1, 8: 0}
    converted = bytes(conversion[value] for value in source[:-1])
    return converted, {
        "source": record["source"],
        "program_sha256": record["program_sha256"],
        "rom_offset": record["rom_offset"],
        "source_bytes": len(source),
        "source_sha256": record["route_sha256"],
        "action_count": len(converted),
        "converted_sha256": hashlib.sha256(converted).hexdigest(),
        "encoding": "CoCo ordinals north/east/south/west=0/1/2/3; initial neutral=$FF",
    }


def load_demo_walk(path: Path, route: dict[str, object]) -> tuple[bytes, dict[str, object]]:
    """Validate the explicit CoCo node walk and its arcade provenance link."""
    record = json.loads(path.read_text(encoding="ascii"))
    actions = bytes(record["actions"])
    action_count = int(record["action_count"])
    if len(actions) != action_count + 1 or actions[-1] != 0xFF:
        raise ValueError(f"{path}: demo walk must contain action_count actions plus $FF")
    if any(value not in (0, 1, 2, 3) for value in actions[:-1]):
        raise ValueError(f"{path}: demo walk contains an illegal CoCo ordinal")
    if hashlib.sha256(actions).hexdigest() != record["walk_sha256"]:
        raise ValueError(f"{path}: demo walk SHA-256 differs")
    text = str(record["action_text"])
    if bytes("NESW".index(value) for value in text) != actions[:-1]:
        raise ValueError(f"{path}: demo walk action text differs")
    if (record["source_route_sha256"] != route["source_sha256"] or
            record["source_program_sha256"] != route["program_sha256"] or
            record["source_action_count"] != route["action_count"]):
        raise ValueError(f"{path}: demo walk arcade provenance differs")
    position = list(record["start_cell"])
    movement = ((0, -2), (2, 0), (0, 2), (-2, 0))
    positions = []
    for direction in actions[:-1]:
        positions.append(tuple(position))
        dx, dy = movement[direction]
        position[0] += dx
        position[1] += dy
    if position != record["end_cell"]:
        raise ValueError(f"{path}: demo walk endpoint differs")
    for detour in record["detours"]:
        offset = int(detour["action_offset"])
        detour_text = str(detour["actions"])
        if positions[offset] != tuple(detour["anchor"]):
            raise ValueError(f"{path}: detour anchor differs at action {offset}")
        if text[offset:offset + len(detour_text)] != detour_text:
            raise ValueError(f"{path}: detour actions differ at action {offset}")
        x, y = detour["anchor"]
        for value in detour_text:
            dx, dy = movement["NESW".index(value)]
            x += dx
            y += dy
        if [x, y] != detour["anchor"]:
            raise ValueError(f"{path}: detour does not return to its anchor")
    backbone = text
    for detour in reversed(record["detours"]):
        offset = int(detour["action_offset"])
        count = len(str(detour["actions"]))
        backbone = backbone[:offset] + backbone[offset + count:]
    backbone_bytes = bytes("NESW".index(value) for value in backbone)
    if (backbone != record["arcade_backbone_action_text"] or
            len(backbone) + 1 != record["arcade_node_count"] or
            hashlib.sha256(backbone_bytes).hexdigest() !=
            record["arcade_backbone_sha256"]):
        raise ValueError(f"{path}: arcade backbone relationship differs")
    return actions, {
        "source": route["source"],
        "program_sha256": route["program_sha256"],
        "rom_offset": route["rom_offset"],
        "source_bytes": route["source_bytes"],
        "source_sha256": route["source_sha256"],
        "arcade_action_count": route["action_count"],
        "arcade_converted_sha256": route["converted_sha256"],
        "arcade_node_count": record["arcade_node_count"],
        "arcade_backbone_sha256": record["arcade_backbone_sha256"],
        "action_count": action_count,
        "walk_sha256": record["walk_sha256"],
        "encoding": record["encoding"],
        "start_cell": record["start_cell"],
        "end_cell": record["end_cell"],
        "collectible_cells": record["collectible_cells"],
        "quadrant_order": record["quadrant_order"],
        "detours": record["detours"],
    }


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
    demo_route = manifest["demo_route"]
    lines.extend((
        "",
        "; BUG-012 arcade-derived demo direction stream.",
        f"PRESENTATION_DEMO_ROUTE_OFFSET equ ${demo_route['cold_offset']:04X}",
        f"PRESENTATION_DEMO_ROUTE_ACTIONS equ {demo_route['action_count']}",
    ))
    instruction = manifest["instruction_choreography"]
    lines.extend((
        "",
        "; BUG-011 semantic instruction choreography.",
        f"PRESENTATION_INSTRUCTION_EVENT_OFFSET equ ${instruction['event_table_offset']:04X}",
        f"PRESENTATION_INSTRUCTION_EVENT_BYTES equ {instruction['event_record_bytes']}",
        f"PRESENTATION_INSTRUCTION_EVENT_COUNT equ {len(instruction['events'])}",
        f"PRESENTATION_INSTRUCTION_COLOUR_POINTERS equ ${instruction['colour_pointer_offset']:04X}",
        f"PRESENTATION_INSTRUCTION_CUCUMBER_STREAM equ ${instruction['cucumber_stream_offset']:04X}",
        f"PRESENTATION_INSTRUCTION_CUCUMBER_DST equ ${instruction['cucumber_destination']:04X}",
        f"PRESENTATION_INSTRUCTION_DEATH_POINTERS equ ${instruction['death_pointer_offset']:04X}",
        f"PRESENTATION_INSTRUCTION_DEATH_COUNT equ {len(instruction['death_stream_offsets'])}",
        f"PRESENTATION_INSTRUCTION_DEATH_TICK equ {instruction['death_collision_tick']}",
        f"PRESENTATION_INSTRUCTION_ANGEL_TICK equ {instruction['angel_tick']}",
        f"PRESENTATION_INSTRUCTION_ANGEL_DST equ ${instruction['angel_destination']:04X}",
        f"PRESENTATION_INSTRUCTION_SKULL_DST equ ${instruction['events'][-1]['target_destination']:04X}",
        f"PRESENTATION_INSTRUCTION_NEXT_TICK equ {instruction['next_screen_tick']}",
        f"PRESENTATION_INSTRUCTION_COLOUR_DWELL equ {instruction['colour_dwell_frames']}",
        f"PRESENTATION_INSTRUCTION_BLACK_TILE equ {instruction['black_tile_id']}",
        f"PRESENTATION_INSTRUCTION_VALUE_DST equ ${instruction['value_destination']:04X}",
        f"PRESENTATION_INSTRUCTION_LIFE_DST equ ${instruction['reward_destinations']['life']:04X}",
        f"PRESENTATION_INSTRUCTION_COIN_DST equ ${instruction['reward_destinations']['coin']:04X}",
        f"PRESENTATION_INSTRUCTION_MULTIPLIER_0 equ ${instruction['multiplier_destinations'][0]:04X}",
        f"PRESENTATION_INSTRUCTION_MULTIPLIER_1 equ ${instruction['multiplier_destinations'][1]:04X}",
        f"PRESENTATION_INSTRUCTION_EXTRA_SPAN equ ${framebuffer_destination((13, 7)):04X}",
        f"PRESENTATION_INSTRUCTION_SPECIAL_SPAN equ ${framebuffer_destination((13, 10)):04X}",
        f"PRESENTATION_INSTRUCTION_HEART_SPAN equ ${framebuffer_destination((13, 13)):04X}",
        f"PRESENTATION_INSTRUCTION_ICON_SPAN equ ${framebuffer_destination((13, 19)):04X}",
    ))
    for index, destination in enumerate(instruction["anchors"]):
        lines.append(f"PRESENTATION_INSTRUCTION_ANCHOR_{index} equ ${destination:04X}")
    for name in ("red", "yellow", "blue"):
        for index, tile_id in enumerate(instruction["value_tile_ids"][name]):
            lines.append(
                f"PRESENTATION_INSTRUCTION_VALUE_{name.upper()}_{index} equ {tile_id}"
            )
    for name in ("life", "coin"):
        for index, tile_id in enumerate(instruction["reward_tile_ids"][name]):
            lines.append(
                f"PRESENTATION_INSTRUCTION_{name.upper()}_{index} equ {tile_id}"
            )
    for value in (2, 3, 5):
        for index, tile_id in enumerate(instruction["multiplier_tile_ids"][str(value)]):
            lines.append(
                f"PRESENTATION_INSTRUCTION_X{value}_{index} equ {tile_id}"
            )
    lines.append(f"PRESENTATION_COIN_TILE equ {manifest['coin_tile']}")
    rotated = [rotate_ccw(tile) for tile in chars]
    for code in range(37):
        packed = pack_tile(recolor(rotated[code], (BLACK, WHITE, WHITE, WHITE)))
        if packed not in tiles:
            if not manifest["development_profile"]:
                raise ValueError(f"presentation glyph {code} is absent from atlas")
            continue
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
    development_profile = bool(args.development_profile)
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
    maps, map_info = compile_profile_maps(
        args.tiled_dir, chars, tiles, tile_ids, development_profile
    )
    if development_profile:
        instruction = parse_instruction_contract(
            args.tiled_dir / MAP_FILES["instructions"], chars, sprites,
            tiles, tile_ids,
        )
    else:
        instruction = parse_instruction_contract(
            args.tiled_dir / MAP_FILES["instructions"], chars, sprites, [], {}
        )
    _arcade_route, arcade_route_manifest = load_demo_route(args.demo_route)
    demo_walk, demo_walk_manifest = load_demo_walk(
        args.demo_walk, arcade_route_manifest
    )

    coin_id = tile_ids.setdefault(coin_tile(), len(tiles))
    if coin_id == len(tiles):
        tiles.append(coin_tile())
    if len(tiles) > 256:
        raise ValueError(
            f"presentation atlas contains {len(tiles)} tiles; one-byte limit is 256"
        )

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
    if development_profile:
        instruction["black_tile_id"] = remap[int(instruction["black_tile_id"])]
        for group in ("reward_tile_ids", "multiplier_tile_ids", "value_tile_ids"):
            instruction[group] = {
                name: [remap[int(tile_id)] for tile_id in ids]
                for name, ids in instruction[group].items()
            }
        event_table = bytearray(instruction["event_table"])
        for index, event in enumerate(instruction["events"]):
            hud_tile_id = remap[int(event["hud_tile_id"])] if event["hud_destination"] else 0
            hud_tile_2_id = remap[int(event["hud_tile_2_id"])] if event["hud_tile_2_id"] else 0
            event["hud_tile_id"] = hud_tile_id
            event["hud_tile_2_id"] = hud_tile_2_id
            event_table[index * INSTRUCTION_EVENT_BYTES + 10] = hud_tile_2_id
            event_table[index * INSTRUCTION_EVENT_BYTES + 11] = hud_tile_id
        instruction["event_table"] = bytes(event_table)
    else:
        instruction["event_table"] = b""
        instruction["target_colour_streams"] = []
        instruction["cucumber_stream"] = b""
        instruction["death_streams"] = []
        instruction["angel_stream"] = b""
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
    cold_payload = bytearray(tile_atlas + gameplay_lookup + bytes(encoded_stream))
    event_count = len(instruction["event_table"]) // INSTRUCTION_EVENT_BYTES
    for padding in range(PAGE_BYTES):
        start = len(cold_payload) + padding
        if all(
            (start + index * INSTRUCTION_EVENT_BYTES) % PAGE_BYTES
            <= PAGE_BYTES - INSTRUCTION_EVENT_BYTES
            for index in range(event_count)
        ):
            cold_payload.extend(bytes(padding))
            break
    else:
        raise ValueError("instruction event table cannot be page-aligned")
    instruction_event_offset = len(cold_payload)
    cold_payload.extend(instruction["event_table"])
    instruction_colour_pointer_offset = len(cold_payload)
    colour_streams = instruction["target_colour_streams"]
    cold_payload.extend(bytes(len(colour_streams) * 2))
    colour_stream_offsets = []
    for stream in colour_streams:
        page_offset = len(cold_payload) % PAGE_BYTES
        if page_offset + len(stream) > PAGE_BYTES:
            cold_payload.extend(bytes(PAGE_BYTES - page_offset))
        colour_stream_offsets.append(len(cold_payload))
        cold_payload.extend(stream)
    for index, offset in enumerate(colour_stream_offsets):
        start = instruction_colour_pointer_offset + index * 2
        cold_payload[start:start + 2] = offset.to_bytes(2, "big")
    cucumber_stream = instruction["cucumber_stream"]
    cucumber_page_offset = len(cold_payload) % PAGE_BYTES
    if cucumber_page_offset + len(cucumber_stream) > PAGE_BYTES:
        cold_payload.extend(bytes(PAGE_BYTES - cucumber_page_offset))
    instruction_cucumber_offset = len(cold_payload)
    cold_payload.extend(cucumber_stream)
    instruction_death_pointer_offset = len(cold_payload)
    death_streams = (
        [*instruction["death_streams"], instruction["angel_stream"]]
        if development_profile else []
    )
    cold_payload.extend(bytes(len(death_streams) * 2))
    death_stream_offsets = []
    for stream in death_streams:
        page_offset = len(cold_payload) % PAGE_BYTES
        if page_offset + len(stream) > PAGE_BYTES:
            cold_payload.extend(bytes(PAGE_BYTES - page_offset))
        death_stream_offsets.append(len(cold_payload))
        cold_payload.extend(stream)
    for index, offset in enumerate(death_stream_offsets):
        start = instruction_death_pointer_offset + index * 2
        cold_payload[start:start + 2] = offset.to_bytes(2, "big")
    demo_route_offset = len(cold_payload)
    cold_payload.extend(demo_walk)
    if len(cold_payload) > COLD_PAYLOAD_LIMIT:
        raise ValueError(
            f"presentation cold payload is {len(cold_payload)} bytes; "
            f"limit is {COLD_PAYLOAD_LIMIT}"
        )
    static_frame_hashes = []
    for index, data in enumerate(maps):
        frame = title_framebuffer(data, tiles)
        if development_profile and index == MAP_NAMES.index("instructions"):
            blend_native_surface(
                frame, instruction["cucumber_destination"],
                instruction["cucumber_native"],
            )
        static_frame_hashes.append(hashlib.sha256(frame).hexdigest())
    manifest = {
        "maps": map_info,
        "map_count": len(maps),
        "development_profile": bool(args.development_profile),
        "development_omitted_glyph_codes": [
            code for code in range(37)
            if pack_tile(recolor(
                [row[:] for row in rotate_ccw(chars[code])],
                (BLACK, WHITE, WHITE, WHITE),
            )) not in tiles
        ] if args.development_profile else [],
        "layer_contracts": {
            info["name"]: info["layer_contract"] for info in map_info
        },
        "raw_sprite_markers": {
            "instructions": [
                {"cell": list(cell), "gid": value & GID_MASK,
                 "flags": value & ~GID_MASK}
                for cell, value in sorted(INSTRUCTION_RAW_SPRITE_MARKERS.items())
            ],
            "level-start": [
                {"cell": list(cell), "gid": value & GID_MASK,
                 "flags": value & ~GID_MASK}
                for cell, value in sorted(LEVEL_START_METADATA.items())
                if (value & GID_MASK) == 633
            ],
        },
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
        "instruction_choreography": {
            "emitted": development_profile,
            "metadata_layer": INSTRUCTION_METADATA_LAYER,
            "static_layers": list(INSTRUCTION_STATIC_LAYERS),
            "anchors": instruction["anchors"],
            "reward_destinations": instruction["reward_destinations"],
            "reward_tile_ids": instruction["reward_tile_ids"],
            "multiplier_destinations": instruction["multiplier_destinations"],
            "multiplier_tile_ids": instruction["multiplier_tile_ids"],
            "value_destination": instruction["value_destination"],
            "value_tile_ids": instruction["value_tile_ids"],
            "black_tile_id": instruction["black_tile_id"],
            "event_record_bytes": INSTRUCTION_EVENT_BYTES,
            "event_table_offset": instruction_event_offset,
            "event_table_bytes": len(instruction["event_table"]),
            "event_table_sha256": hashlib.sha256(instruction["event_table"]).hexdigest(),
            "events": instruction["events"],
            "colour_pointer_offset": instruction_colour_pointer_offset,
            "colour_stream_offsets": colour_stream_offsets,
            "colour_stream_bytes": [len(stream) for stream in colour_streams],
            "cucumber_destination": instruction["cucumber_destination"],
            "cucumber_source_code": instruction["cucumber_source_code"],
            "cucumber_stream_offset": instruction_cucumber_offset,
            "cucumber_stream_bytes": len(cucumber_stream),
            "death_pointer_offset": instruction_death_pointer_offset,
            "death_stream_offsets": death_stream_offsets,
            "death_stream_bytes": [len(stream) for stream in death_streams],
            "death_stream_sha256": [hashlib.sha256(stream).hexdigest()
                                    for stream in death_streams],
            "death_collision_tick": instruction["death_collision_tick"],
            "angel_tick": instruction["angel_tick"],
            "angel_destination": instruction["angel_destination"],
            "next_screen_tick": instruction["next_screen_tick"],
            "colour_dwell_frames": instruction["colour_dwell_frames"],
            "angel_source_code": instruction["angel_source_code"],
        },
        "demo_route": {
            **demo_walk_manifest,
            "cold_offset": demo_route_offset,
            "bytes": len(demo_walk),
        },
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
        "static_frame_sha256": static_frame_hashes,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(bytes(cold_payload))
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
