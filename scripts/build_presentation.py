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
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--include-output", type=Path, required=True)
    parser.add_argument("--manifest-output", type=Path, required=True)
    parser.add_argument("--actor-record-output", type=Path, required=True)
    parser.add_argument("--actor-underlay-output", type=Path, required=True)
    return parser.parse_args()


def screen_role(root: ET.Element, path: Path) -> str:
    return next(
        (item.get("value") for item in root.findall("./properties/property")
         if item.get("name") == "screen-role"),
        path.stem,
    )


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
    role = screen_role(root, path)
    layers = root.findall("layer")
    if role == "instructions":
        names = [layer.get("name", "") for layer in layers]
        missing = [name for name in (*INSTRUCTION_STATIC_LAYERS,
                                     INSTRUCTION_METADATA_LAYER)
                   if names.count(name) != 1]
        extras = [name for name in names
                  if name not in (*INSTRUCTION_STATIC_LAYERS,
                                  INSTRUCTION_METADATA_LAYER)]
        if missing or extras:
            raise ValueError(
                f"{path}: instruction layer contract mismatch; "
                f"missing/duplicate={missing}, unexpected={extras}"
            )
        selected = [layer for name in INSTRUCTION_STATIC_LAYERS
                    for layer in layers if layer.get("name") == name]
    else:
        selected = [layer for layer in layers
                    if layer.get("visible", "1") != "0"
                    and layer.get("name") != "Sprite Animations"]
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
    return bytes(output), {"role": role, "path": str(path)}


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


def register_tile(tile: bytes, tiles: list[bytes], tile_ids: dict[bytes, int]) -> int:
    tile_id = tile_ids.setdefault(tile, len(tiles))
    if tile_id == len(tiles):
        tiles.append(tile)
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
    records = {
        (index % SCREEN_WIDTH, index // SCREEN_WIDTH): gid
        for index, gid in enumerate(cells) if gid & GID_MASK
    }
    expected = {
        **{cell: 0xA0000221 for cell in INSTRUCTION_ANCHORS},
        (28, 7): 456, (29, 7): 440, (28, 8): 488, (29, 8): 472,
        (28, 10): 376, (29, 10): 328, (28, 11): 296, (29, 11): 344,
        INSTRUCTION_ANGEL_ROOT: 523,
        (27, 17): 147, (28, 17): 417,
        (27, 20): 147, (28, 20): 417,
    }
    if records != expected:
        missing = sorted(set(expected) - set(records))
        extra = sorted(set(records) - set(expected))
        wrong = sorted(cell for cell in set(records) & set(expected)
                       if records[cell] != expected[cell])
        raise ValueError(
            f"{path}: Sprite Locations contract mismatch; "
            f"missing={missing}, extra={extra}, wrong={wrong}"
        )

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
    for name, root_cell in (("life", INSTRUCTION_LIFE_ROOT),
                            ("coin", INSTRUCTION_COIN_ROOT)):
        ids = []
        for dy in range(2):
            for dx in range(2):
                cell = (root_cell[0] + dx, root_cell[1] + dy)
                ids.append(register_tile(
                    instruction_char_tile(root, path, records[cell], cell, chars),
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
    multiplier_x = register_tile(
        instruction_char_tile(root, path, records[(27, 17)], (27, 17), chars),
        tiles, tile_ids,
    )
    multiplier_tiles = {
        str(value): [multiplier_x, register_tile(
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
    for index, (source, (target, hud)) in enumerate(
            zip(source_targets, INSTRUCTION_TARGETS)):
        motion = int(source["motion_first_frame"]) - first
        consume_key = "collision_frame" if index == 15 else "consume_frame"
        consume = int(source[consume_key]) - first
        # Sprite Locations records the actor baseline cell. Convert it to the
        # 16x16 framebuffer root used by save/draw, then end one packed byte
        # left of the target so the Lady Bug overlaps it.
        goal = framebuffer_destination(target) - 1
        target_destination = framebuffer_destination(target)
        hud_destination = 0 if hud == (0, 0) else framebuffer_destination(hud)
        hud_tile_id = 0
        if hud_destination:
            trigger_colour = 2 if index < 5 else 1 if index < 12 else 3
            hud_index = hud[1] * SCREEN_WIDTH + hud[0]
            hud_tile_id = register_tile(instruction_char_tile(
                root, path, hud_cells[hud_index], hud, chars,
                (BLACK, trigger_colour, trigger_colour, trigger_colour),
            ), tiles, tile_ids)
        record = (
            motion.to_bytes(2, "big") + consume.to_bytes(2, "big")
            + goal.to_bytes(2, "big") + target_destination.to_bytes(2, "big")
            + hud_destination.to_bytes(2, "big") + bytes((index, hud_tile_id))
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
                ) for dx in range(2)]
                for row in range(8):
                    packed_row = (row_tiles[0][row * 4:row * 4 + 4]
                                  + row_tiles[1][row * 4:row * 4 + 4])
                    for column, value in enumerate(packed_row):
                        high, low = value >> 4, value & 15
                        selector = (
                            (2 if high and not (index >= 12 and high == PINK) else 0)
                            | (1 if low and not (index >= 12 and low == PINK) else 0)
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
    angel_pixels = rotate_ccw(sprites[10])
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
        "angel_destination": framebuffer_destination(INSTRUCTION_ANGEL_ROOT),
        "angel_source_code": 10,
        "death_collision_tick": int(reference["rows"][2]["skull"]["collision_frame"]) - first,
        "angel_tick": int(reference["death_sequence"]["angel_hold"]["first_frame"]) - first,
        "next_screen_tick": int(reference["instruction_interval"]["next_screen_first_partial_frame"]) - first,
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
    instruction = manifest["instruction_choreography"]
    lines.extend((
        "",
        "; BUG-011 semantic instruction choreography.",
        f"PRESENTATION_INSTRUCTION_EVENT_OFFSET equ ${instruction['event_table_offset']:04X}",
        f"PRESENTATION_INSTRUCTION_EVENT_BYTES equ {instruction['event_record_bytes']}",
        f"PRESENTATION_INSTRUCTION_EVENT_COUNT equ {len(instruction['events'])}",
        f"PRESENTATION_INSTRUCTION_COLOUR_POINTERS equ ${instruction['colour_pointer_offset']:04X}",
        f"PRESENTATION_INSTRUCTION_DEATH_POINTERS equ ${instruction['death_pointer_offset']:04X}",
        f"PRESENTATION_INSTRUCTION_DEATH_COUNT equ {len(instruction['death_stream_offsets'])}",
        f"PRESENTATION_INSTRUCTION_DEATH_TICK equ {instruction['death_collision_tick']}",
        f"PRESENTATION_INSTRUCTION_ANGEL_TICK equ {instruction['angel_tick']}",
        f"PRESENTATION_INSTRUCTION_ANGEL_DST equ ${instruction['angel_destination']:04X}",
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

    instruction = parse_instruction_contract(
        args.tiled_dir / MAP_FILES["instructions"], chars, sprites, tiles, tile_ids
    )

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
    instruction["black_tile_id"] = remap[int(instruction["black_tile_id"])]
    for group in ("reward_tile_ids", "multiplier_tile_ids", "value_tile_ids"):
        instruction[group] = {
            name: [remap[int(tile_id)] for tile_id in ids]
            for name, ids in instruction[group].items()
        }
    event_table = bytearray(instruction["event_table"])
    for index, event in enumerate(instruction["events"]):
        hud_tile_id = remap[int(event["hud_tile_id"])] if event["hud_destination"] else 0
        event["hud_tile_id"] = hud_tile_id
        event_table[index * INSTRUCTION_EVENT_BYTES + 11] = hud_tile_id
    instruction["event_table"] = bytes(event_table)
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
    instruction_event_offset = len(cold_payload)
    cold_payload.extend(instruction["event_table"])
    instruction_colour_pointer_offset = len(cold_payload)
    colour_streams = instruction["target_colour_streams"]
    cold_payload.extend(bytes(len(colour_streams) * 2))
    colour_stream_offsets = []
    for stream in colour_streams:
        colour_stream_offsets.append(len(cold_payload))
        cold_payload.extend(stream)
    for index, offset in enumerate(colour_stream_offsets):
        start = instruction_colour_pointer_offset + index * 2
        cold_payload[start:start + 2] = offset.to_bytes(2, "big")
    instruction_death_pointer_offset = len(cold_payload)
    death_streams = [*instruction["death_streams"], instruction["angel_stream"]]
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
        "instruction_choreography": {
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
