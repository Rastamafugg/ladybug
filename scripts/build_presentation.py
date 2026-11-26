#!/usr/bin/env python3
"""Compile the six authored presentation TMX maps into shared cold data."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_screen import (  # noqa: E402
    BLACK,
    BLUE,
    DARK_RED,
    DARK_GREEN,
    FLIP_D,
    FLIP_H,
    FLIP_V,
    GID_MASK,
    GAMEPLAY_SPRITE_LOCATIONS,
    GREEN,
    GREY,
    LIGHT_BLUE,
    LIGHT_GREEN,
    MAGENTA,
    ORANGE,
    PART_VEGETABLE_MARKER,
    PINK,
    PURPLE,
    RED,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    TILE_SIZE,
    VIOLET,
    WHITE,
    YELLOW,
    char_sheet_code,
    compile_death_sprites,
    compile_player_sprites,
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
from gmc_lzss import compress as lzss_compress  # noqa: E402


MAP_NAMES = (
    "attract",
    "instructions",
    "level-start",
    "high-score",
    "game-over",
    "enter-high-score",
    "options",
    "credits",
    "keybind-options",
)
MAP_FILES = {
    name: f"coco-{name}-screen.tmx" for name in MAP_NAMES
}
DEVELOPMENT_PLACEHOLDER_MAPS = ("game-over", "enter-high-score")
RELEASE_PLACEHOLDER_MAPS = ("instructions",)
# The historical FEAT-003 harness is being built once for BUG-113's startup
# marker. Keep authored validation for non-marker maps, but do not add their
# unrelated tiles to its shared one-byte presentation atlas.
HIGHSCORE_TEST_PLACEHOLDER_MAPS = (
    "instructions", "level-start", "game-over", "options", "credits",
    "keybind-options",
)
PAGE_BYTES = 0x2000
COLD_PAGE = 0x3A
COLD_PAGE_COUNT = 4
MAP_BYTES = SCREEN_WIDTH * SCREEN_HEIGHT
TILE_BYTES = 32
MAP_OUTPUT_OFFSET = 0x4000
COLD_PAYLOAD_LIMIT = 10874
ATTRACT_ACTOR_COLOURS = {
    (11, 3): (WHITE, DARK_GREEN, MAGENTA),
    (20, 4): (YELLOW, LIGHT_GREEN, ORANGE),
    (35, 4): (WHITE, YELLOW, ORANGE),
    (27, 5): (WHITE, DARK_GREEN, VIOLET),
    (3, 9): (WHITE, YELLOW, ORANGE),
    (10, 15): (YELLOW, DARK_GREEN, DARK_RED),
    (34, 13): (GREEN, DARK_GREEN, LIGHT_BLUE),
    (33, 19): (WHITE, LIGHT_GREEN, DARK_GREEN),
    (5, 20): (WHITE, YELLOW, ORANGE),
}
ATTRACT_ACTOR_EXPECTED_TILES = {
    (11, 3): 98,
    (20, 4): 101,
    (35, 4): 5,
    (27, 5): 65,
    (3, 9): 68,
    (10, 15): 32,
    (34, 13): 38,
    (33, 19): 35,
    (5, 20): 2,
}
# The (11,3) family crosses to the preceding sheet column for its row-0
# wrap frame. Keys use actor cell and stored phase; values are sheet row/column.
ATTRACT_ACTOR_PHASE_OVERRIDES = {
    ((11, 3), 0): (0, 1),
    ((20, 4), 0): (0, 4),
}
ATTRACT_ACTOR_SURFACE_PAGE = 0x3C
ATTRACT_ACTOR_SURFACE_ADDRESS = 0xA000
ATTRACT_ACTOR_BYTES = 128
ATTRACT_ACTOR_PHASES = (0, 1, 2)
ATTRACT_COPY_COUNT = 21  # nine actors and twelve authored logo rectangles
ATTRACT_ACTOR_DESTINATION_ADDRESS = 0xA000 + 3 * ATTRACT_COPY_COUNT * 128
ATTRACT_ACTOR_PHASE_POINTER_ADDRESS = ATTRACT_ACTOR_DESTINATION_ADDRESS + ATTRACT_COPY_COUNT * 2
INSTRUCTION_REFERENCE = (
    Path(__file__).resolve().parents[1]
    / "assets" / "arcade" / "instruction_reference.json"
)
INSTRUCTION_STATIC_LAYERS = (
    "Background",
    "Arcade Maze Border",
    "CoCo Side HUD",
    "Instructions Overlay",
)
INSTRUCTION_METADATA_LAYER = "Sprite Locations"
ENTER_HIGH_SCORE_METADATA_LAYER = "Sprite Locations"
ENTER_HIGH_SCORE_CURSOR_MARKER = {(19, 22): 545}
ENTER_HIGH_SCORE_SPRITE_LOCATIONS = {
    **ENTER_HIGH_SCORE_CURSOR_MARKER, PART_VEGETABLE_MARKER: 633,
}
ENTER_HIGH_SCORE_GRID_ROWS = (
    ((16, 4), (20, 4), (24, 4)),
    ((12, 6), (16, 6), (20, 6), (24, 6), (28, 6)),
    ((12, 8), (16, 8), (20, 8), (24, 8), (28, 8)),
    ((12, 10), (16, 10), (20, 10), (24, 10), (28, 10)),
    ((12, 12), (16, 12), (20, 12), (24, 12), (28, 12)),
    ((12, 14), (16, 14), (20, 14), (24, 14), (28, 14)),
    ((12, 16), (16, 16), (20, 16), (24, 16), (28, 16)),
    ((12, 18), (16, 18), (20, 18), (24, 18), (28, 18)),
)
ENTER_HIGH_SCORE_CL_CELLS = ((11, 4), (27, 4), (11, 20))
ENTER_HIGH_SCORE_END_CELLS = ((27, 20),)
ENTER_HIGH_SCORE_INNER_WALL_CODE = 49
ENTER_HIGH_SCORE_CURSOR_Y_OFFSET = -7 * 160
ENTER_HIGH_SCORE_TIMER_FRAMES = 60
ENTER_HIGH_SCORE_TIMER_COUNT = 92
ENTER_HIGH_SCORE_PENDING_NAME_CELLS = tuple((1 + index, 19) for index in range(7))
ENTER_HIGH_SCORE_TOP_NAME_CELLS = tuple((33 + index, 12) for index in range(7))
ENTER_HIGH_SCORE_DEFAULT_CODES = (21, 10, 13, 34, 11, 30, 16)  # LADYBUG
ENTER_HIGH_SCORE_SCORE_DESTINATIONS = tuple(
    0x2000 + 2 * 1280 + (33 + index) * 4 for index in range(6)
)
ENTER_HIGH_SCORE_TOP_DESTINATIONS = tuple(
    0x2000 + 13 * 1280 + (1 + index) * 4 for index in range(6)
)
ENTER_HIGH_SCORE_TOP_RIGHT_DESTINATIONS = tuple(
    0x2000 + 6 * 1280 + (34 + index) * 4 for index in range(6)
)
HIGH_SCORE_LAYOUT_LAYER = "High Score Data Layout"
HIGH_SCORE_LAYOUT_SLOTS = tuple(f"RANK_{index:02d}" for index in range(1, 10))
HUD_LAYOUT_LAYER = "HUD Field Definitions"
HUD_LAYOUT_SCREEN_SOURCES = {
    "gameplay": ("coco-screen.tmx", "HUD Placeholders"),
    "instructions": ("coco-instructions-screen.tmx", "CoCo Side HUD"),
    "level-start": ("coco-level-start-screen.tmx", "CoCo Side HUD"),
    "game-over": ("coco-game-over-screen.tmx", "CoCo Side HUD"),
    "enter-high-score": ("coco-enter-high-score-screen.tmx", "CoCo Side HUD"),
    "extra": ("coco-extra-screen.tmx", "CoCo Side HUD"),
    "special": ("coco-special-screen.tmx", "CoCo Side HUD"),
}
HUD_LAYOUT_COLOUR_FIELDS = {
    "PART_LABEL": "part",
    "PART_VALUE": "part",
    "P1_LABEL": "score",
    "P1_SCORE": "score",
    "P2_SCORE": "inactive_player",
    "TOP_LABEL": "high_score",
    "TOP_SCORE": "high_score",
    "VEGETABLE_EQUALS": "bonus",
    "VEGETABLE_VALUE": "bonus",
}
HUD_LAYOUT_FIELDS = {
    "PART_LABEL": (4, 1), "PART_VALUE": (3, 1),
    "P1_LABEL": (3, 1), "P1_SCORE": (6, 1),
    "P2_LABEL": (3, 1), "P2_SCORE": (6, 1),
    "TOP_LABEL": (3, 1), "TOP_NAME": (7, 1), "TOP_SCORE": (6, 1),
    "VEGETABLE_ICON": (2, 2), "VEGETABLE_EQUALS": (1, 1),
    "VEGETABLE_VALUE": (4, 1),
    "SPECIAL_PROGRESS": (7, 1), "EXTRA_PROGRESS": (5, 1),
    "MULTIPLIER_X2": (2, 1), "MULTIPLIER_X3": (2, 1),
    "MULTIPLIER_X5": (2, 1),
    **{f"LIFE_{index:02d}": (2, 2) for index in range(1, 13)},
    "INSTRUCTION_EXTRA_VALUE": (2, 1),
    "INSTRUCTION_SPECIAL_VALUE": (2, 1),
}
HIGH_SCORE_DISPLAY_RECORDS = tuple(range(9))
HIGH_SCORE_SCORE_BYTES = 3
HIGH_SCORE_BCD_DIGITS_PER_BYTE = 2
HIGH_SCORE_LOGO_PURPOSES = ("y-descender", "g-descender", "registered-mark")
HIGH_SCORE_LOGO_PURPOSE_COLOURS = {
    "y-descender": LIGHT_BLUE,
    "g-descender": LIGHT_BLUE,
    "registered-mark": RED,
}
HIGH_SCORE_LOGO_LAYERS = ("Logo Base", "Logo Frame 1", "Logo Frame 2")
HIGH_SCORE_LOGO_CELL_LAYERS = ("High Score Table and Title",) + HIGH_SCORE_LOGO_LAYERS
INSTRUCTION_ANCHORS = ((10, 8), (10, 11), (10, 14))
INSTRUCTION_LIFE_ROOT = (28, 7)
INSTRUCTION_COIN_ROOT = (28, 10)
INSTRUCTION_ANGEL_ROOT = (28, 14)
INSTRUCTION_CUCUMBER_MARKER = PART_VEGETABLE_MARKER
INSTRUCTION_TARGETS = (
    (13, 7), (15, 7), (17, 7), (19, 7), (21, 7),
    (13, 10), (15, 10), (17, 10), (19, 10), (21, 10), (23, 10),
    (25, 10),
    (13, 13), (17, 13), (21, 13),
    (28, 13),
)
INSTRUCTION_EVENT_BYTES = 12
INSTRUCTION_STOPS = (
    (13, 8), (15, 8), (17, 8), (19, 8), (21, 8),
    (13, 11), (15, 11), (17, 11), (19, 11), (21, 11), (23, 11),
    (25, 11), (13, 14), (17, 14), (21, 14), INSTRUCTION_ANGEL_ROOT,
)


def instruction_hud_target(hud_layout, event_index):
    """Resolve event HUD cells from the shared named-field layout."""
    extra = hud_layout["EXTRA_PROGRESS"]
    extra_x, extra_y = (int(value) for value in extra["cell"])
    extra_width = int(extra["size"][0])
    if event_index < extra_width:
        return extra_x + event_index, extra_y
    event_index -= extra_width

    special = hud_layout["SPECIAL_PROGRESS"]
    special_x, special_y = (int(value) for value in special["cell"])
    special_width = int(special["size"][0])
    if event_index < special_width:
        return special_x + event_index, special_y
    event_index -= special_width

    multiplier_names = ("MULTIPLIER_X2", "MULTIPLIER_X3", "MULTIPLIER_X5")
    if event_index < len(multiplier_names):
        return tuple(int(value) for value in hud_layout[multiplier_names[event_index]]["cell"])
    if event_index == len(multiplier_names):
        return (0, 0)
    raise ValueError("instruction event has no shared HUD field")
PRESENTATION_LAYER_CONTRACTS = {
    "attract": {
        "static": ("Background", "Attract Title and Prompts"),
        "metadata": (),
        "runtime": ("Sprite Animations", "Logo Frame 1", "Logo Frame 2"),
        "deferred": (),
    },
    "instructions": {
        "static": INSTRUCTION_STATIC_LAYERS,
        "metadata": (INSTRUCTION_METADATA_LAYER,),
        "runtime": (),
        "deferred": (),
    },
    "level-start": {
        "static": (
            "Background", "Arcade Maze Border", "Level Start Panel",
            "CoCo Side HUD",
        ),
        "metadata": ("Sprite Locations",),
        "runtime": (),
        "deferred": (),
    },
    "high-score": {
        "static": (
            "Background", "High Score Table and Title", "Logo Base",
        ),
        "metadata": (),
        "runtime": (),
        "deferred": ("Logo Frame 1", "Logo Frame 2"),
    },
    "options": {"static": ("Options Screen",), "metadata": ("Selected Option",), "runtime": (), "deferred": ()},
    "credits": {
        "static": ("Background", "Credits Screen"),
        "metadata": (),
        "runtime": (),
        "deferred": (),
    },
    "game-over": {
        "static": (
            "Background", "Arcade Maze Border", "CoCo Side HUD",
            "Game Over Overlay",
        ),
        "metadata": ("Sprite Locations",),
        "runtime": (),
        "deferred": (),
    },
    "enter-high-score": {
        "static": (
            "Background", "Arcade Maze Border", "CoCo Side HUD",
            "Enter High Score Overlay",
        ),
        "metadata": (ENTER_HIGH_SCORE_METADATA_LAYER,),
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
LEVEL_START_METADATA = {(16, 7): 633, PART_VEGETABLE_MARKER: 633}
GAME_OVER_SPRITE_LOCATIONS = {PART_VEGETABLE_MARKER: 633}


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
        raise ValueError(f"{path}: expected nine Sprite Animations cells")
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
    logo_roots, logo_frames = compile_logo_frames(framebuffer)
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
        logo = logo_frames[phase & 1]
        for x, y in logo_roots:
            offset = y * 1280 + x * 4
            for row in range(16):
                surfaces.extend(logo[offset + row * 160:offset + row * 160 + 8])
    return bytes(surfaces)


def compile_logo_frames(
        base: bytes, map_name: str = "attract",
        colour_config: dict[str, object] | None = None,
) -> tuple[list[tuple[int, int]], list[bytes]]:
    path = Path(__file__).resolve().parents[1] / "tiled" / MAP_FILES[map_name]
    root = ET.parse(path).getroot()
    chars = load_chars(path.parents[1] / "assets/arcade/chars.json")
    layers = [next(l for l in root.findall("layer") if l.get("name") == name)
              for name in ("Logo Frame 1", "Logo Frame 2")]
    records = [layer_records(layer) for layer in layers]
    roots = sorted({(x // 2 * 2, y // 2 * 2) for record in records for x, y in record})
    if (map_name == "attract" and
            len(roots) + len(ATTRACT_ACTOR_EXPECTED_TILES) != ATTRACT_COPY_COUNT):
        raise ValueError("title copy allocation differs from authored logo rectangles")
    if map_name == "high-score" and len(roots) != 12:
        raise ValueError("high-score logo frames must contain twelve authored 16x16 roots")
    logo_colours = (high_score_logo_cell_colours(colour_config)
                    if map_name == "high-score" and colour_config else {})
    frames = []
    for layer, record in zip(layers, records):
        frame = bytearray(base)
        for (x, y), gid in record.items():
            color = logo_colours.get((x, y))
            # Keep pen 1 white on the light-blue animation cells.
            pen_map = (
                (BLACK, WHITE, color, color) if color == LIGHT_BLUE else
                (BLACK, color, color, color)
            ) if color is not None else (
                BLACK, WHITE, LIGHT_BLUE, LIGHT_BLUE
            )
            tile = instruction_char_tile(root, path, gid, (x, y), chars, pen_map)
            for row in range(8):
                offset = y * 1280 + x * 4 + row * 160
                frame[offset:offset + 4] = tile[row * 4:row * 4 + 4]
        frames.append(bytes(frame))
    return roots, frames


def logo_frame_layout(
        map_name: str,
) -> tuple[tuple[int, int], tuple[tuple[tuple[int, int, int], ...], ...]]:
    """Return the even-cell root and each frame's root-relative authored cells."""
    path = Path(__file__).resolve().parents[1] / "tiled" / MAP_FILES[map_name]
    root = ET.parse(path).getroot()
    layers = [next(l for l in root.findall("layer") if l.get("name") == name)
              for name in ("Logo Frame 1", "Logo Frame 2")]
    frames = [layer_records(layer) for layer in layers]
    cells = [cell for frame in frames for cell in frame]
    if not cells:
        raise ValueError(f"{map_name} logo frame layers contain no cells")
    root_cell = (min(x for x, _ in cells) // 2 * 2,
                 min(y for _, y in cells) // 2 * 2)
    rx, ry = root_cell
    relative = tuple(
        tuple(sorted((x - rx, y - ry, gid) for (x, y), gid in frame.items()))
        for frame in frames
    )
    return root_cell, relative


def high_score_logo_cell_colours(
        colour_config: dict[str, object],
) -> dict[tuple[int, int], int]:
    """Expand the authored semantic High Score logo color groups to cells."""
    groups = colour_config.get("logo_groups")
    if not isinstance(groups, list):
        raise ValueError("text-colours.json must define High Score logo_groups")
    colours: dict[tuple[int, int], int] = {}
    purposes: set[str] = set()
    for group in groups:
        if not isinstance(group, dict) or group.get("screen") != "high-score":
            raise ValueError("High Score logo groups must name screen high-score")
        purpose = group.get("purpose")
        if purpose not in HIGH_SCORE_LOGO_PURPOSES or purpose in purposes:
            raise ValueError(f"invalid or duplicate High Score logo purpose {purpose!r}")
        purposes.add(purpose)
        colour = group.get("colour")
        expected_colour = HIGH_SCORE_LOGO_PURPOSE_COLOURS[str(purpose)]
        if type(colour) is not int or colour != expected_colour:
            raise ValueError(
                f"High Score {purpose} must use palette index {expected_colour}"
            )
        cells = group.get("cells")
        if not isinstance(cells, list) or not cells:
            raise ValueError(f"High Score {purpose} must list at least one cell")
        for cell in cells:
            if (not isinstance(cell, list) or len(cell) != 2 or
                    any(type(value) is not int for value in cell)):
                raise ValueError(f"High Score {purpose} cells must be integer [x,y] pairs")
            x, y = cell
            if not (0 <= x < SCREEN_WIDTH and 0 <= y < SCREEN_HEIGHT):
                raise ValueError(f"High Score {purpose} cell {(x, y)} is outside the screen")
            if (x, y) in colours:
                raise ValueError(f"High Score logo color groups overlap at {(x, y)}")
            colours[(x, y)] = colour
    if purposes != set(HIGH_SCORE_LOGO_PURPOSES):
        missing = sorted(set(HIGH_SCORE_LOGO_PURPOSES) - purposes)
        raise ValueError(f"High Score logo color groups are missing {missing}")
    return colours


def load_text_colours(path: Path | None = None) -> dict[str, object]:
    """Read and validate the project's shared static and dynamic color data."""
    source = path or Path(__file__).resolve().parents[1] / "assets/arcade/text-colours.json"
    config = json.loads(source.read_text(encoding="utf-8"))
    high_score_logo_cell_colours(config)
    return config


def compose_attract_frames(
        attract_map: bytes, tiles: list[bytes], surfaces: bytes,
        actors: list[dict[str, object]]) -> list[bytes]:
    base = title_framebuffer(attract_map, tiles)
    frames = []
    for phase in (0, 1, 2, 1):
        frame = bytearray(base)
        roots, _ = compile_logo_frames(base)
        destinations = actors + [{"destination": framebuffer_destination(root)} for root in roots]
        for actor_index, actor in enumerate(destinations):
            source = (phase * ATTRACT_COPY_COUNT + actor_index) * ATTRACT_ACTOR_BYTES
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
    parser.add_argument("--shared-text", action="store_true")
    parser.add_argument("--text-colours", type=Path, help="Shared text colour data; defaults to assets/arcade/text-colours.json")
    parser.add_argument("--chars", type=Path, required=True)
    parser.add_argument("--gameplay-map", type=Path, required=True)
    parser.add_argument("--gameplay-maze", type=Path, required=True)
    parser.add_argument("--gameplay-chars", type=Path, required=True)
    parser.add_argument("--gameplay-sprites", type=Path, required=True)
    parser.add_argument("--demo-route", type=Path, required=True)
    parser.add_argument("--demo-walk", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--include-output", type=Path, required=True)
    parser.add_argument("--hud-layout-output", type=Path, required=True)
    parser.add_argument("--manifest-output", type=Path, required=True)
    parser.add_argument("--actor-record-output", type=Path, required=True)
    parser.add_argument("--actor-underlay-output", type=Path, required=True)
    parser.add_argument("--tile-patch-output", type=Path, required=True)
    parser.add_argument("--timer-record-output", type=Path, required=True)
    parser.add_argument("--development-profile", type=int, choices=(0, 1), default=0)
    parser.add_argument("--complete-profile", type=int, choices=(0, 1), default=0)
    parser.add_argument("--highscore-test-profile", type=int, choices=(0, 1), default=0)
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


def perimeter_box_cells() -> tuple[tuple[int, int], ...]:
    """Return screen cells for the documented 92-box clockwise circuit."""
    cells: list[tuple[int, int]] = []
    for maze_x in range(12, 24):
        cells.append((8 + maze_x, 0))
    for maze_y in range(1, 24):
        cells.append((31, maze_y))
    for maze_x in range(22, -1, -1):
        cells.append((8 + maze_x, 23))
    for maze_y in range(22, 0, -1):
        cells.append((8, maze_y))
    for maze_x in range(0, 12):
        cells.append((8 + maze_x, 0))
    if len(cells) != ENTER_HIGH_SCORE_TIMER_COUNT:
        raise AssertionError("enter-high-score perimeter must contain 92 boxes")
    return tuple(cells)


def enter_high_score_edge_masks() -> bytes:
    """Encode passable N/E/S/W edges for the 9x5 selectable-node grid."""
    masks = bytearray()
    for row in range(9):
        for column in range(5):
            mask = 0
            if row and column in (0, 4):
                mask |= 1
            if column < 4:
                mask |= 2
            if row < 8 and column in (0, 4):
                mask |= 4
            if column:
                mask |= 8
            masks.append(mask)
    return bytes(masks)


def enter_high_score_full_edge_masks(
    path: Path, chars: list[list[list[int]]], player_frames: list[bytes],
) -> bytes:
    """Encode cardinal edges and six-pixel turn hazards for the 24x24 window."""
    root = ET.parse(path).getroot()
    layers = {layer.get("name"): layer for layer in root.findall("layer")}
    overlay = layers["Enter High Score Overlay"]
    cells = parse_csv(overlay.find("data"), overlay.get("name", ""))
    inner_walls = {
        (x, y): cells[y * SCREEN_WIDTH + x + 8]
        for y in range(24)
        for x in range(24)
        if cells[y * SCREEN_WIDTH + x + 8] & GID_MASK and
        raw_char_code(root, path, cells[y * SCREEN_WIDTH + x + 8] & GID_MASK)
        == ENTER_HIGH_SCORE_INNER_WALL_CODE
    }
    # The sprite extends above and to the right of its logical anchor tile.
    blocked = set(inner_walls) | {
        (x - 1, y) for x, y in inner_walls if 0 < x < 23 and 0 < y < 23
    } | {
        (x, y)
        for y in range(24)
        for x in range(24)
        if x in (0, 22, 23) or y in (0, 1, 23)
    }

    border = layers["Arcade Maze Border"]
    border_cells = parse_csv(border.find("data"), border.get("name", ""))
    wall_gids = {
        (x, y): border_cells[y * SCREEN_WIDTH + x + 8]
        for y in range(24)
        for x in range(24)
        if border_cells[y * SCREEN_WIDTH + x + 8] & GID_MASK
    }
    wall_gids.update(inner_walls)
    wall_pixels = set()
    for (x, y), gid in wall_gids.items():
        tile = instruction_char_tile(
            root, path, gid, (x + 8, y), chars, (BLACK, WHITE, WHITE, WHITE),
        )
        for py in range(8):
            for px in range(8):
                shift = 4 * (1 - px % 2)
                if (tile[py * 4 + px // 2] >> shift) & 0xF:
                    wall_pixels.add((x * 8 + px, y * 8 + py))
    # Union the opaque pixels of all animation frames in all four facings.
    opaque = {
        (x, y) for frame in player_frames for y in range(16) for x in range(16)
        if (frame[y * 4 + x // 4] >> (6 - 2 * (x % 4))) & 3
    }
    directions = ((0, -1), (1, 0), (0, 1), (-1, 0))
    masks = bytearray(24 * 24)
    for y in range(2, 23):
        for x in range(1, 22):
            if (x, y) in blocked:
                continue
            # Both endpoints must be open, so every edge is reciprocal.
            mask = sum(
                1 << direction for direction, (dx, dy) in enumerate(directions)
                if (x + dx, y + dy) not in blocked
            )
            origin_x = x * 8
            origin_y = y * 8 + ENTER_HIGH_SCORE_CURSOR_Y_OFFSET // 160
            for first, (dx, dy) in enumerate(directions):
                second = (first + 1) % 4
                if not (mask & (1 << first) and mask & (1 << second)):
                    continue
                turn_x, turn_y = directions[second]
                # Each tick trades two pixels on the old axis for two on the
                # new axis. Swapping directions traverses these poses in reverse.
                if any(
                    (origin_x + (6 - step) * dx + step * turn_x + px,
                     origin_y + (6 - step) * dy + step * turn_y + py) in wall_pixels
                    for step in (0, 2, 4, 6) for px, py in opaque
                ):
                    mask |= 0x10 << first
            masks[y * 24 + x] = mask
    return bytes(masks)


def raw_char_code(root: ET.Element, path: Path, gid: int) -> int:
    ranges = tileset_ranges(root, path)
    tileset = next(
        (item for item in ranges
         if int(item["firstgid"]) <= gid <= int(item["lastgid"])),
        None,
    )
    if tileset is None or tileset["name"] != "chars_raw2bpp":
        return -1
    sheet_index = gid - int(tileset["firstgid"])
    return (sheet_index % 16) * 32 + (31 - sheet_index // 16)


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
    if role == "options" and path.name == "coco-keybind-options-screen.tmx":
        contract = {
            **contract,
            "static": ("Background", *contract["static"]),
        }
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
    if "Background" in contract["static"]:
        background = parse_csv(by_name["Background"].find("data"), "Background")
        if len(background) != MAP_BYTES or any(gid != 8 for gid in background):
            raise ValueError(
                f"{path}: Background must contain exactly {MAP_BYTES} GID8 blank cells"
            )
    for name in contract["deferred"]:
        validate_layer_tilesets(path, root, by_name[name], ("chars_raw2bpp",))
    if role == "attract":
        validate_layer_tilesets(
            path, root, by_name["Sprite Animations"], ("sprites_raw2bpp",)
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
    if role == "game-over":
        metadata = by_name["Sprite Locations"]
        require_records(
            path, "game-over sprite locations", layer_records(metadata),
            GAME_OVER_SPRITE_LOCATIONS,
        )
        validate_layer_tilesets(path, root, metadata, ("sprites_raw2bpp",))
    if role == "level-start":
        records = layer_records(by_name["Sprite Locations"])
        require_records(path, "level-start sprite locations", records, LEVEL_START_METADATA)
        validate_layer_tilesets(
            path, root, by_name["Sprite Locations"],
            ("sprites_raw2bpp",),
        )
    if role == "enter-high-score":
        metadata_layer = by_name[ENTER_HIGH_SCORE_METADATA_LAYER]
        records = layer_records(metadata_layer)
        require_records(
            path, "enter-high-score cursor metadata", records,
            ENTER_HIGH_SCORE_SPRITE_LOCATIONS,
        )
        if metadata_layer.get("offsety") != "1":
            raise ValueError(
                f"{path}: {ENTER_HIGH_SCORE_METADATA_LAYER} must retain offsety=1"
            )
        validate_layer_tilesets(
            path, root, metadata_layer, ("sprites_raw2bpp",)
        )
    return {
        "role": role,
        "static_layers": list(contract["static"]),
        "metadata_layers": list(contract["metadata"]),
        "runtime_layers": list(contract["runtime"]),
        "deferred_layers": list(contract["deferred"]),
    }


def flatten_map(path: Path) -> tuple[ET.Element, list[int], list[str]]:
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
    sources = [""] * MAP_BYTES
    for layer in selected:
        cells = parse_csv(layer.find("data"), layer.get("name", ""))
        for index, gid in enumerate(cells):
            if gid & GID_MASK:
                flattened[index] = gid
                sources[index] = layer.get("name", "")
    return root, flattened, sources


def presentation_pen_map(
        role: str, x: int, y: int, source_layer: str = "",
        raw_code: int = -1, highscore_test_profile: bool = False,
        colour_config: dict[str, object] | None = None,
        hud_layout: dict[str, dict[str, object]] | None = None,
) -> tuple[int, int, int, int]:
    """Apply the established CoCo palette adaptation to authored raw chars."""
    if source_layer == "CoCo Side HUD" and hud_layout is not None:
        for field_name, colour_name in HUD_LAYOUT_COLOUR_FIELDS.items():
            field = hud_layout[field_name]
            field_x, field_y = (int(value) for value in field["cell"])
            width, height = (int(value) for value in field["size"])
            if field_x <= x < field_x + width and field_y <= y < field_y + height:
                colour = (
                    GREY if colour_name == "inactive_player"
                    else int(colour_config["fields"][colour_name])
                    if colour_config else WHITE
                )
                return (BLACK, colour, colour, colour)
    if role == "high-score" and source_layer in HIGH_SCORE_LOGO_CELL_LAYERS and colour_config:
        colour = high_score_logo_cell_colours(colour_config).get((x, y))
        if colour is not None:
            return (BLACK, colour, colour, colour)
    if role == "high-score" and source_layer in HIGH_SCORE_LOGO_LAYERS:
        return (BLACK, WHITE, LIGHT_BLUE, LIGHT_BLUE)
    if role == "instructions":
        if hud_layout is None:
            inactive_cells = {(column, 7) for column in range(1, 7)}
        else:
            inactive_cells = set()
            for field_name in ("MULTIPLIER_X2", "MULTIPLIER_X3", "MULTIPLIER_X5"):
                field = hud_layout[field_name]
                cell_x, cell_y = (int(value) for value in field["cell"])
                width, height = (int(value) for value in field["size"])
                inactive_cells.update(
                    (cell_x + dx, cell_y + dy)
                    for dy in range(height)
                    for dx in range(width)
                )
        if (x, y) in inactive_cells:
            inactive = int(colour_config["fields"].get(
                "instruction_multiplier_inactive", GREY
            )) if colour_config else BLUE
            return (BLACK, inactive, inactive, inactive)
    if role == "attract":
        if 7 <= y <= 12 and 9 <= x <= 30 and 164 <= raw_code <= 197:
            return (BLACK, WHITE, LIGHT_BLUE, LIGHT_BLUE)
        if (y == 15 and source_layer == "Attract Title and Prompts"
                and 0 <= raw_code <= 35):
            return (BLACK, PURPLE, PURPLE, PURPLE)
        if y == 18 and 13 <= x <= 26:
            colour = YELLOW if raw_code == 1 else WHITE
            return (BLACK, colour, colour, colour)
        return (0, 1, 2, 3)
    if x < 8 and y < 9:
        colour = (RED, YELLOW, BLUE)[y // 3]
        if y % 3 == 1 and x != 0:
            colour = GREY
        return (BLACK, colour, colour, colour)
    if role in ("options", "credits", "keybind-options"):
        return (BLACK, GREY, GREY, GREY)
    if role == "level-start" and (x,y)==(34,13):
        return (BLACK,GREEN,GREEN,GREEN)
    if x >= 32:
        if role == "instructions" and y == 2:
            return (BLACK, LIGHT_GREEN, LIGHT_GREEN, LIGHT_GREEN)
        if role == "instructions" and y == 13 and 34 <= x <= 39:
            return (BLACK, GREEN, GREEN, GREEN)
        colour = {
            1: LIGHT_GREEN, 2: WHITE,
            4: RED, 5: RED,
            7: WHITE, 8: WHITE, 9: WHITE,
            10: BLUE, 11: BLUE,
            12: GREEN, 13: WHITE,
        }.get(y, BLACK)
        return (BLACK, colour, colour, colour)
    if role == "level-start" and 8 <= x < 32:
        if y == 4 and 15 <= x <= 25:
            return (BLACK, BLUE, BLUE, BLUE)
        if y == 7 and 16 <= x <= 26:
            return (BLACK, GREEN, GREEN, GREEN)
        if y == 9 and 10 <= x <= 30:
            return (BLACK, YELLOW, YELLOW, YELLOW)
        if y == 20 and 16 <= x <= 24:
            return (BLACK, RED, RED, RED)
        if 11 <= y <= 18 and 17 <= x <= 22:
            if y <= 12:
                return (BLACK, WHITE, WHITE, PINK)
            return (BLACK, BLUE, WHITE, PINK)
        return (BLACK, PINK, WHITE, PINK)
    if role == "enter-high-score":
        if source_layer == "Arcade Maze Border":
            if (x, y) in perimeter_box_cells():
                return (BLACK, PINK, WHITE, PINK)
            return (BLACK, PINK, PINK, PINK)
        if (source_layer == "Enter High Score Overlay" and
                raw_code == ENTER_HIGH_SCORE_INNER_WALL_CODE):
            return (BLACK, PINK, PINK, PINK)
        return (BLACK, WHITE, WHITE, WHITE)
    if role == "high-score" and highscore_test_profile:
        # The arcade high-score table and footer use the light-blue HUD pen;
        # the central Lady Bug branding remains pink.  The registered mark at
        # the right of the logo is part of the HUD text, not the logo.
        if source_layer in HIGH_SCORE_LOGO_LAYERS:
            return (BLACK, WHITE, LIGHT_BLUE, LIGHT_BLUE)
        return (BLACK, LIGHT_BLUE, LIGHT_BLUE, LIGHT_BLUE)
    if role == "high-score" and source_layer in HIGH_SCORE_LOGO_LAYERS:
        return (BLACK, WHITE, LIGHT_BLUE, LIGHT_BLUE)
    if role == "game-over":
        if source_layer == "Arcade Maze Border":
            if (x, y) in perimeter_box_cells():
                return (BLACK, GREEN, GREEN, GREEN)
            return (BLACK, PINK, PINK, PINK)
        if source_layer == "Game Over Overlay":
            return (BLACK, RED, RED, RED)
    if role in ("game-over", "high-score"):
        return (BLACK, WHITE, WHITE, WHITE)
    if role == "instructions" and 28 <= x < 30 and 13 <= y < 15:
        return (BLACK, WHITE, WHITE, WHITE)
    if role == "instructions" and (y == 5 and 15 <= x <= 25 or y == 17 and 17 <= x <= 25 or y == 20 and 16 <= x <= 25):
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
    highscore_test_profile: bool = False,
    allow_phase_overlay: bool = False,
    colour_config: dict[str, object] | None = None,
    hud_layout: dict[str, dict[str, object]] | None = None,
) -> tuple[list[int] | bytes, dict[str, object]]:
    root, flattened, sources = flatten_map(path)
    role = screen_role(root, path)
    ranges = tileset_ranges(root, path)
    rotated = [rotate_ccw(tile) for tile in chars]
    output: list[int] = []
    for index, gid_with_flags in enumerate(flattened):
        x = index % SCREEN_WIDTH
        y = index // SCREEN_WIDTH
        if role == "level-start" and allow_phase_overlay and (
                y == 9 and 10 <= x <= 30 or y == 4 and 22 <= x <= 24 or
                y == 20 and 16 <= x <= 24):
            gid_with_flags = 0  # complete-profile stage helper owns these cells
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
            packed = pack_tile(recolor(
                tile, presentation_pen_map(
                    role, x, y, sources[index],
                    raw_char_code(root, path, gid), highscore_test_profile,
                    colour_config, hud_layout,
                )
            ))
        tile_id = tile_ids.setdefault(packed, len(tiles))
        if tile_id == len(tiles):
            tiles.append(packed)
        if tile_id > 255 and not allow_phase_overlay:
            raise ValueError("presentation atlas exceeds one-byte tile IDs")
        output.append(tile_id)
    return output if allow_phase_overlay else bytes(output), {
        "role": role,
        "path": str(path),
        "layer_contract": validate_presentation_layers(root, path),
    }


def framebuffer_destination(cell: tuple[int, int]) -> int:
    x, y = cell
    return 0x2000 + y * 1280 + x * 4


def parse_hud_layout(path: Path) -> dict[str, dict[str, object]]:
    """Read named HUD rectangles from the shared CoCo authoring template."""
    root = ET.parse(path).getroot()
    width, height = int(root.attrib["width"]), int(root.attrib["height"])
    tile_width, tile_height = int(root.attrib["tilewidth"]), int(root.attrib["tileheight"])
    if (width, height, tile_width, tile_height) != (40, 24, 8, 8):
        raise ValueError(f"{path}: HUD layout requires a 40x24 8-pixel grid")
    layers = [layer for layer in root.findall("objectgroup")
              if layer.get("name") == HUD_LAYOUT_LAYER]
    if len(layers) != 1:
        raise ValueError(f"{path}: expected one {HUD_LAYOUT_LAYER!r} object layer")
    layer = layers[0]
    if any(float(layer.get(key, "0")) != 0
           for key in ("x", "y", "offsetx", "offsety")):
        raise ValueError(f"{path}: {HUD_LAYOUT_LAYER} may not be offset")

    fields: dict[str, dict[str, object]] = {}
    claimed: set[tuple[int, int]] = set()
    for obj in layer.findall("object"):
        name = obj.get("name", "")
        if name not in HUD_LAYOUT_FIELDS:
            raise ValueError(f"{path}: unexpected HUD field {name!r}")
        if name in fields:
            raise ValueError(f"{path}: duplicate HUD field {name!r}")
        if obj.get("gid") is not None or any(
                obj.find(shape) is not None
                for shape in ("point", "ellipse", "polygon", "polyline", "text")):
            raise ValueError(f"{path}: HUD field {name} must be a rectangle")
        try:
            values = tuple(float(obj.get(key, "nan"))
                           for key in ("x", "y", "width", "height"))
        except ValueError as exc:
            raise ValueError(f"{path}: HUD field {name} has invalid geometry") from exc
        if not all(value == value and abs(value) != float("inf") for value in values):
            raise ValueError(f"{path}: HUD field {name} has invalid geometry")
        x_px, y_px, width_px, height_px = values
        expected_width, expected_height = HUD_LAYOUT_FIELDS[name]
        if (x_px % tile_width or y_px % tile_height
                or width_px != expected_width * tile_width
                or height_px != expected_height * tile_height):
            raise ValueError(f"{path}: HUD field {name} has wrong size or is off-grid")
        x, y = int(x_px // tile_width), int(y_px // tile_height)
        cells = {(column, row)
                 for row in range(y, y + expected_height)
                 for column in range(x, x + expected_width)}
        if (x < 0 or y < 0 or x + expected_width > width
                or y + expected_height > height):
            raise ValueError(f"{path}: HUD field {name} is outside the screen")
        overlap = claimed & cells
        if overlap:
            raise ValueError(f"{path}: HUD fields overlap at {sorted(overlap)}")
        claimed.update(cells)
        fields[name] = {
            "cell": [x, y],
            "size": [expected_width, expected_height],
            "destination": framebuffer_destination((x, y)),
        }
    missing = set(HUD_LAYOUT_FIELDS) - set(fields)
    if missing:
        raise ValueError(f"{path}: missing HUD fields {sorted(missing)}")
    return fields


def parse_hud_screen_layouts(
    tiled_dir: Path, fields: dict[str, dict[str, object]],
) -> dict[str, dict[str, object]]:
    """Bind each consuming map layer to the template's fields and placeholders."""
    layouts: dict[str, dict[str, object]] = {}
    template_path = tiled_dir / "coco-template.tmx"
    template_root = ET.parse(template_path).getroot()
    template_layers = [layer for layer in template_root.findall("layer")
                       if layer.get("name") == "HUD Placeholders"]
    if len(template_layers) != 1:
        raise ValueError(f"{template_path}: expected one 'HUD Placeholders' layer")
    template_cells = parse_csv(
        template_layers[0].find("data"), "HUD Placeholders"
    )
    if len(template_cells) != MAP_BYTES:
        raise ValueError(
            f"{template_path}: HUD Placeholders has {len(template_cells)} cells, expected {MAP_BYTES}"
        )
    for screen, (filename, layer_name) in HUD_LAYOUT_SCREEN_SOURCES.items():
        path = tiled_dir / filename
        root = ET.parse(path).getroot()
        if (int(root.get("width", "0")), int(root.get("height", "0")),
                int(root.get("tilewidth", "0")), int(root.get("tileheight", "0"))) != (40, 24, 8, 8):
            raise ValueError(f"{path}: shared HUD layout requires a 40x24 8-pixel grid")
        layers = [layer for layer in root.findall("layer")
                  if layer.get("name") == layer_name]
        if len(layers) != 1:
            raise ValueError(f"{path}: expected one {layer_name!r} layout layer")
        cells = parse_csv(layers[0].find("data"), layer_name)
        if len(cells) != MAP_BYTES:
            raise ValueError(f"{path}: {layer_name} has {len(cells)} cells, expected {MAP_BYTES}")
        if cells != template_cells:
            raise ValueError(f"{path}: {layer_name} differs from the shared template placeholders")
        layouts[screen] = {
            "source_map": filename,
            "source_layer": layer_name,
            "field_count": len(fields),
            "placeholder_cell_count": len(cells),
            "fields": fields,
        }
    return layouts


def parse_high_score_layout(
        path: Path, colour_config: dict[str, object] | None = None,
) -> list[dict[str, object]]:
    """Read and validate the authored nine-row High Score rectangles."""
    root = ET.parse(path).getroot()
    width, height = int(root.attrib["width"]), int(root.attrib["height"])
    tile_width, tile_height = int(root.attrib["tilewidth"]), int(root.attrib["tileheight"])
    if (width, height, tile_width, tile_height) != (40, 24, 8, 8):
        raise ValueError(f"{path}: High Score layout requires a 40x24 8-pixel grid")
    layers = [layer for layer in root.findall("objectgroup")
              if layer.get("name") == HIGH_SCORE_LAYOUT_LAYER]
    if len(layers) != 1:
        raise ValueError(f"{path}: expected one {HIGH_SCORE_LAYOUT_LAYER!r} object layer")
    layer = layers[0]
    if any(float(layer.get(key, "0")) != 0 for key in ("x", "y", "offsetx", "offsety")):
        raise ValueError(f"{path}: {HIGH_SCORE_LAYOUT_LAYER} may not be offset")

    expected = {
        f"Rank_{slot[-2:]}_{field.title()}"
        for slot in HIGH_SCORE_LAYOUT_SLOTS
        for field in ("NAME", "SCORE")
    }
    markers: dict[str, tuple[int, int]] = {}
    for obj in layer.findall("object"):
        name = obj.get("name", "")
        if name not in expected:
            raise ValueError(f"{path}: unexpected High Score layout marker {name!r}")
        if name in markers:
            raise ValueError(f"{path}: duplicate High Score layout marker {name!r}")
        if obj.get("gid") is not None or any(
                obj.find(shape) is not None
                for shape in ("point", "ellipse", "polygon", "polyline", "text")):
            raise ValueError(f"{path}: marker {name} must be a rectangle object")
        try:
            x_px, y_px = float(obj.get("x", "nan")), float(obj.get("y", "nan"))
            width_px, height_px = float(obj.get("width", "nan")), float(obj.get("height", "nan"))
        except ValueError as exc:
            raise ValueError(f"{path}: marker {name} has invalid rectangle geometry") from exc
        if not all(value == value and abs(value) != float("inf")
                   for value in (x_px, y_px, width_px, height_px)):
            raise ValueError(f"{path}: marker {name} has invalid rectangle geometry")
        if width_px != 56 or height_px != 8:
            raise ValueError(f"{path}: marker {name} must be exactly 56x8 pixels")
        if any(value % grid for value, grid in (
                (x_px, tile_width), (y_px, tile_height),
                (width_px, tile_width), (height_px, tile_height))):
            raise ValueError(f"{path}: marker {name} is off the 8-pixel grid")
        markers[name] = (int(x_px // tile_width), int(y_px // tile_height))
    missing = expected - set(markers)
    if missing:
        raise ValueError(f"{path}: missing High Score layout markers {sorted(missing)}")

    required_layers = ("High Score Table and Title", *HIGH_SCORE_LOGO_LAYERS)
    layer_map: dict[str, ET.Element] = {}
    for layer_name in required_layers:
        found = [item for item in root.findall("layer") if item.get("name") == layer_name]
        if len(found) != 1:
            raise ValueError(f"{path}: expected one authored layer {layer_name!r}")
        layer_map[layer_name] = found[0]

    # High Score name and score cells are runtime-owned. Keep only title and
    # logo artwork in the map and reject field rectangles that cover either.
    occupied: set[tuple[int, int]] = set()
    logo_cells: set[tuple[int, int]] = set()
    for layer_name in ("High Score Table and Title", *HIGH_SCORE_LOGO_LAYERS):
        for index, gid in enumerate(parse_csv(layer_map[layer_name].find("data"), layer_name)):
            if gid & GID_MASK:
                cell = (index % width, index // width)
                occupied.add(cell)
                if layer_name == "High Score Table and Title" or layer_name in HIGH_SCORE_LOGO_LAYERS:
                    logo_cells.add(cell)

    logo_colour_cells = set(high_score_logo_cell_colours(
        colour_config or load_text_colours()
    ))
    missing_logo_cells = logo_colour_cells - logo_cells
    if missing_logo_cells:
        raise ValueError(
            f"{path}: High Score logo color cells are not in an authored title or logo-art layer "
            f"{sorted(missing_logo_cells)}"
        )

    placements = []
    claimed: set[tuple[int, int]] = set()
    for slot_index, slot in enumerate(HIGH_SCORE_LAYOUT_SLOTS):
        prefix = f"Rank_{slot[-2:]}"
        name_cell, score_cell = markers[f"{prefix}_Name"], markers[f"{prefix}_Score"]
        name_cell_width = 7
        score_cell_width = 7
        score_max_digits = HIGH_SCORE_SCORE_BYTES * HIGH_SCORE_BCD_DIGITS_PER_BYTE
        if score_max_digits > score_cell_width:
            raise ValueError(f"{path}: {prefix}_Score is narrower than its packed-decimal capacity")
        for field, (x, y), field_width in (
                ("name", name_cell, name_cell_width),
                ("score", score_cell, score_cell_width)):
            cells = {(column, y) for column in range(x, x + field_width)}
            if x < 0 or y < 0 or x + field_width > width or y >= height:
                raise ValueError(f"{path}: {prefix}_{field.title()} is outside the screen")
            overlap = claimed & cells
            if overlap:
                raise ValueError(f"{path}: High Score name/score fields overlap at {sorted(overlap)}")
            art_overlap = occupied & cells
            if art_overlap:
                raise ValueError(
                    f"{path}: {prefix}_{field.title()} overlaps authored title/logo cells "
                    f"{sorted(art_overlap)}"
                )
            claimed.update(cells)
        record_index = HIGH_SCORE_DISPLAY_RECORDS[slot_index]
        score_draw_cell = (
            score_cell[0] + score_cell_width - score_max_digits, score_cell[1]
        )
        placements.append({
            "slot": slot,
            "record_index": record_index,
            "name_cell": list(name_cell),
            "score_cell": list(score_cell),
            "name_cell_width": name_cell_width,
            "score_cell_width": score_cell_width,
            "score_max_digits": score_max_digits,
            # Compatibility: this field describes capacity, not authored length.
            "score_draw_cells": score_max_digits,
            "name_destination": framebuffer_destination(name_cell),
            "score_destination": framebuffer_destination(score_draw_cell),
        })
    authored = authored_high_score_cells(path, placements)
    for placement, cells in zip(placements, authored):
        placement["authored_score_cells"] = [list(cell) for cell in cells]
    return placements


def authored_high_score_cells(path: Path, placements: list[dict[str, object]]) -> list[list[tuple[int, int]]]:
    """Resolve populated digits inside each authored score rectangle."""
    root, flattened, _ = flatten_map(path)
    result = []
    for placement in placements:
        x, y = placement["score_cell"]
        width = placement["score_cell_width"]
        columns = []
        for column in range(x, x + width):
            code = raw_char_code(root, path, flattened[y * SCREEN_WIDTH + column] & GID_MASK)
            if 0 <= code <= 9:
                columns.append(column)
            elif code not in (-1, 255):
                raise ValueError(f"{path}: {placement['slot']} score contains a non-digit at {(column, y)}")
        if not columns:
            result.append([])
            continue
        if columns != list(range(x + width - len(columns), x + width)):
            raise ValueError(f"{path}: {placement['slot']} score digits must be a contiguous right-aligned suffix")
        if len(columns) > placement["score_max_digits"]:
            raise ValueError(f"{path}: {placement['slot']} authored score exceeds its runtime capacity")
        result.append([(column, y) for column in columns])
    return result


def high_score_field_colour_cells(path: Path, config: dict[str, object]) -> dict[tuple[int, int], int]:
    """Named rules follow Tiled score markers and ignore only their blank padding."""
    rules = config.get("field_runs", [])
    if not rules:
        return {}
    placements = parse_high_score_layout(path, config)
    fields = {f"Rank_{item['slot'][-2:]}_Score": item for item in placements}
    seen = set()
    result = {}
    for rule in rules:
        name = rule.get("field")
        if rule.get("screen") != "high-score" or name not in fields or name in seen:
            raise ValueError(f"invalid or duplicate named High Score colour field: {name!r}")
        colour = rule.get("colour")
        if type(colour) is not int or not 0 <= colour <= 15:
            raise ValueError(f"invalid named High Score colour: {colour!r}")
        seen.add(name)
        for cell in fields[name]["authored_score_cells"]:
            result[tuple(cell)] = colour
    if seen != set(fields):
        raise ValueError("named High Score colour rules must cover all nine score fields")
    return result


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
    return tile_id


def replace_packed_colour(tile: bytes, source: int, target: int) -> bytes:
    output = bytearray()
    for value in tile:
        high = target if value >> 4 == source else value >> 4
        low = target if (value & 0x0F) == source else value & 0x0F
        output.append((high << 4) | low)
    return bytes(output)


def parse_instruction_contract(
    path: Path,
    chars: list[list[list[int]]],
    sprites: list[list[list[int]]],
    tiles: list[bytes],
    tile_ids: dict[bytes, int],
    hud_layout: dict[str, dict[str, object]],
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
        pack_sprite_2bpp(cucumber_pixels), (BLACK, DARK_RED, DARK_GREEN, YELLOW)
    )
    cucumber_root = (
        INSTRUCTION_CUCUMBER_MARKER[0], INSTRUCTION_CUCUMBER_MARKER[1] - 1
    )
    cucumber_stream = encode_sparse_native(cucumber_native, 16, 8)

    overlay = layers["Instructions Overlay"]
    overlay_cells = parse_csv(overlay.find("data"), overlay.get("name", ""))
    hud_layer = layers["CoCo Side HUD"]
    hud_cells = parse_csv(hud_layer.find("data"), hud_layer.get("name", ""))
    multiplier_names = ("MULTIPLIER_X2", "MULTIPLIER_X3", "MULTIPLIER_X5")
    multiplier_roots = tuple(
        tuple(int(v) for v in hud_layout[name]["cell"])
        for name in multiplier_names
    )
    for event_index, target in enumerate(INSTRUCTION_TARGETS):
        hud = instruction_hud_target(hud_layout, event_index)
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
    for colour, value in (("red", WHITE), ("yellow", WHITE), ("blue", WHITE)):
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
            hud_cells[cell[1] * SCREEN_WIDTH + cell[0]], cell, chars,
            (BLACK, BLUE, BLUE, BLUE),
        ), tiles, tile_ids), register_tile(
            pack_tile(recolor(rotated[value], (BLACK, BLUE, BLUE, BLUE))),
            tiles, tile_ids,
        )]
        for value, cell in zip((2, 3, 5), multiplier_roots)
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
    row_time_offsets = (0, 0, 0)
    reference_consumes = []
    instruction_colour_dwell = 32
    for index, (source, target, stop) in enumerate(
            zip(source_targets, INSTRUCTION_TARGETS, INSTRUCTION_STOPS)):
        hud = instruction_hud_target(hud_layout, index)
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
            while not (
                motion >= earliest
                and ((motion - 1) % 90) // 30 + 1 == trigger_colour
                and (motion - 1) % 30 == 0
            ):
                motion += 1
        # Sprite Locations records each actor baseline. Convert the authored
        # stop to the 16x16 framebuffer root used by save/draw.
        goal = framebuffer_destination(stop) - 1280
        reference_consumes.append(consume)
        # Preserve the authored colour-cycle index and within-colour offset.
        cycle, phase_tick = divmod(motion - 1, 90)
        colour, offset = divmod(phase_tick, 30)
        motion = 1 + (cycle * 3 + colour) * instruction_colour_dwell + offset
        origin = (framebuffer_destination(INSTRUCTION_ANCHORS[row]) - 1280
                  if index in (0, 5, 12)
                  else event_manifest[-1]["goal_destination"])
        distance = goal - origin
        first_move = motion + (1 if motion % 2 == 0 else 0)
        consume = first_move + 2 * (distance - 1) + 1
        if index < 15 and ((consume - 1) // instruction_colour_dwell) % 3 + 1 != trigger_colour:
            raise ValueError("instruction arrival outside required colour window")
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
            + bytes((0, 0))  # remapped tile IDs are installed after phase packing
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

    # Last-row X is a persistent demonstration target, not a consumable event.
    operations = bytearray()
    cursor = count = 0
    for dy in range(2):
        pair = [instruction_char_tile(root, path,
                    overlay_cells[(19 + dy) * SCREEN_WIDTH + 13 + dx],
                    (13 + dx, 19 + dy), chars, (0, 1, 1, 1)) for dx in range(2)]
        for row in range(8):
            packed = pair[0][row * 4:row * 4 + 4] + pair[1][row * 4:row * 4 + 4]
            for column, value in enumerate(packed):
                selector = (2 if value & 0xF0 else 0) | (1 if value & 15 else 0)
                if selector:
                    destination = (dy * 8 + row) * 160 + column
                    delta = destination - cursor
                    operations.extend((delta,) if delta < 255 else (255, delta >> 8, delta & 255))
                    operations.append(selector)
                    cursor = destination
                    count += 1
    target_colour_streams.append(bytes((count,)) + operations)

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
    ending_shift = event_manifest[-1]["consume_tick"] - reference_consumes[-1]
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
        "multiplier_destinations": [framebuffer_destination(
            tuple(int(v) for v in hud_layout[name]["cell"])
        ) for name in ("INSTRUCTION_EXTRA_VALUE", "INSTRUCTION_SPECIAL_VALUE")],
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
        "death_collision_tick": event_manifest[-1]["consume_tick"],
        "angel_tick": int(reference["death_sequence"]["angel_hold"]["first_frame"]) - first + row_time_offsets[-1] + ending_shift,
        "next_screen_tick": int(reference["instruction_interval"]["next_screen_first_partial_frame"]) - first + row_time_offsets[-1] + ending_shift,
        "colour_dwell_frames": instruction_colour_dwell,
    }


def parse_enter_high_score_contract(
    path: Path,
    chars: list[list[list[int]]],
    sprites: list[list[list[int]]],
    tiles: list[bytes],
    tile_ids: dict[bytes, int],
) -> dict[str, object]:
    """Compile the authored name-entry keypad and cursor start marker."""
    root = ET.parse(path).getroot()
    layers = {layer.get("name", ""): layer for layer in root.findall("layer")}
    metadata = layers[ENTER_HIGH_SCORE_METADATA_LAYER]
    records = layer_records(metadata)
    require_records(
        path, "enter-high-score cursor metadata", records,
        ENTER_HIGH_SCORE_SPRITE_LOCATIONS,
    )
    cursor_pixels, cursor_code = instruction_sprite(
        root, path, records[(19, 22)], sprites
    )
    cursor_native = expand_sprite(
        pack_sprite_2bpp(cursor_pixels), (BLACK, DARK_RED, GREEN, YELLOW)
    )
    cursor_stream = encode_sparse_native(cursor_native, 16, 8)
    overlay = layers["Enter High Score Overlay"]
    overlay_cells = parse_csv(overlay.find("data"), overlay.get("name", ""))
    grid_tiles: list[int] = []
    grid_cells: list[tuple[int, int]] = []
    for row in ENTER_HIGH_SCORE_GRID_ROWS:
        for cell in row:
            index = cell[1] * SCREEN_WIDTH + cell[0]
            gid = overlay_cells[index]
            if not gid & GID_MASK:
                raise ValueError(f"{path}: missing name-entry character at {cell}")
            grid_cells.append(cell)
            grid_tiles.append(register_tile(
                instruction_char_tile(
                    root, path, gid, cell, chars,
                    (BLACK, WHITE, WHITE, WHITE),
                ),
                tiles, tile_ids,
            ))
    for cell in (*ENTER_HIGH_SCORE_CL_CELLS, *ENTER_HIGH_SCORE_END_CELLS):
        x, y = cell
        if not overlay_cells[y * SCREEN_WIDTH + x] & GID_MASK:
            raise ValueError(f"{path}: missing control marker at {cell}")
    node_cells = []
    node_tile_ids = []
    for row_index, row in enumerate(ENTER_HIGH_SCORE_GRID_ROWS):
        if row_index == 0:
            row_cells = ((11, 4), *row, (27, 4))
            row_tiles = (0xFE, *grid_tiles[:3], 0xFE)
        else:
            start = 3 + (row_index - 1) * 5
            row_cells = row
            row_tiles = tuple(grid_tiles[start:start + 5])
        node_cells.extend(row_cells)
        node_tile_ids.extend(row_tiles)
    node_cells.extend(((11, 20), (15, 20), (19, 20), (23, 20), (27, 20)))
    # Bottom-row actions use the Ladybug node column, while the visible dot
    # and heart are authored in the adjacent right cell. Space is a virtual
    # blank choice. Keep native tile descriptors rather than text codes.
    symbol_tiles = []
    for cell, code in (((16, 20), 45), ((20, 20), 36), ((24, 20), 41)):
        if code == 36:
            native = bytes(32)
        else:
            gid = overlay_cells[cell[1] * SCREEN_WIDTH + cell[0]]
            if raw_char_code(root, path, gid & GID_MASK) != code:
                raise ValueError(f"{path}: unexpected bottom-row symbol at {cell}")
            native = instruction_char_tile(
                root, path, gid, cell, chars, (BLACK, WHITE, WHITE, WHITE)
            )
        symbol_tiles.append(register_tile(native, tiles, tile_ids))
    node_tile_ids.extend((0xFE, *symbol_tiles, 0xFD))
    action_records = [
        (cell, tile_id) for cell, tile_id in zip(node_cells, node_tile_ids)
        if tile_id != 0xFF
    ]
    pending_name_cells = ENTER_HIGH_SCORE_PENDING_NAME_CELLS
    top_name_cells = ENTER_HIGH_SCORE_TOP_NAME_CELLS

    def authored_name_span(layer_name: str, cells: tuple[tuple[int, int], ...]) -> tuple[list[int], list[int]]:
        layer = layers[layer_name]
        layer_cells = parse_csv(layer.find("data"), layer.get("name", ""))
        raw_codes = [
            raw_char_code(root, path, layer_cells[y * SCREEN_WIDTH + x])
            for x, y in cells
        ]
        if raw_codes != list(ENTER_HIGH_SCORE_DEFAULT_CODES):
            raise ValueError(
                f"{path}: {layer_name} authored name span must be LADYBUG, "
                f"got raw codes {raw_codes}"
            )
        span_tile_ids = [
            register_tile(
                instruction_char_tile(
                    root, path, layer_cells[y * SCREEN_WIDTH + x], (x, y), chars,
                    (BLACK, WHITE, WHITE, WHITE),
                ),
                tiles, tile_ids,
            )
            for x, y in cells
        ]
        return span_tile_ids, [framebuffer_destination(cell) for cell in cells]

    pending_name_tile_ids, pending_name_destinations = authored_name_span(
        "Enter High Score Overlay", pending_name_cells
    )
    top_name_tile_ids, top_name_destinations = authored_name_span(
        "CoCo Side HUD", top_name_cells
    )
    if top_name_tile_ids != pending_name_tile_ids:
        raise ValueError(f"{path}: HUD and entry name spans do not share tile IDs")

    default_codes = ENTER_HIGH_SCORE_DEFAULT_CODES
    glyph_by_code = {
        raw_char_code(root, path, overlay_cells[y * SCREEN_WIDTH + x]): tile_id
        for (x, y), tile_id in zip(grid_cells, grid_tiles)
    }
    try:
        default_name_tile_ids = [glyph_by_code[code] for code in default_codes]
    except KeyError as exc:
        raise ValueError(f"{path}: missing LADYBUG fixture glyph code {exc.args[0]}")
    return {
        "cursor_stream": cursor_stream,
        "cursor_source_code": cursor_code,
        "cursor_destination": framebuffer_destination((19, 22)) + ENTER_HIGH_SCORE_CURSOR_Y_OFFSET,
        "cursor_cell": (19, 22),
        "grid_cells": grid_cells,
        "grid_tile_ids": grid_tiles,
        "node_cells": node_cells,
        "node_tile_ids": node_tile_ids,
        "action_records": [
            [cell[0], cell[1], tile_id] for cell, tile_id in action_records
        ],
        "default_name_tile_ids": pending_name_tile_ids,
        "top_name_tile_ids": top_name_tile_ids,
        "node_destinations": [
            framebuffer_destination(cell) + ENTER_HIGH_SCORE_CURSOR_Y_OFFSET
            for cell in node_cells
        ],
        "cl_cells": list(ENTER_HIGH_SCORE_CL_CELLS),
        "end_cells": list(ENTER_HIGH_SCORE_END_CELLS),
        "name_destinations": pending_name_destinations,
        "top_name_destinations": top_name_destinations,
        "score_destinations": list(ENTER_HIGH_SCORE_SCORE_DESTINATIONS),
        "top_destinations": list(ENTER_HIGH_SCORE_TOP_DESTINATIONS),
        "top_right_destinations": list(ENTER_HIGH_SCORE_TOP_RIGHT_DESTINATIONS),
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
    highscore_test_profile: bool = False, complete_profile: bool = False,
    colour_config: dict[str, object] | None = None,
    hud_layout: dict[str, dict[str, object]] | None = None,
) -> tuple[list[bytes], list[dict[str, object]]]:
    """Validate every map while omitting maps unreachable in the selected profile."""
    maps: list[bytes | None] = []
    map_info: list[dict[str, object]] = []
    placeholder_maps = (
        () if complete_profile
        else HIGHSCORE_TEST_PLACEHOLDER_MAPS if highscore_test_profile
        else DEVELOPMENT_PLACEHOLDER_MAPS if development_profile
        else RELEASE_PLACEHOLDER_MAPS
    )
    for name in MAP_NAMES:
        path = tiled_dir / MAP_FILES[name]
        if name in placeholder_maps:
            isolated_tiles: list[bytes] = []
            isolated_ids: dict[bytes, int] = {}
            authored, info = compile_map(
                path, chars, isolated_tiles, isolated_ids,
                colour_config=colour_config, hud_layout=hud_layout,
            )
            authored_frame = title_framebuffer(authored, isolated_tiles)
            maps.append(None)
            emission = (
                "development-profile-black-placeholder" if development_profile
                else "highscore-test-black-placeholder" if highscore_test_profile
                else "release-profile-black-placeholder"
            )
        else:
            authored, info = compile_map(
                path, chars, tiles, tile_ids,
                highscore_test_profile,
                complete_profile,
                colour_config,
                hud_layout,
            )
            authored_frame = title_framebuffer(authored, tiles)
            maps.append(authored)
            emission = "authored"
        info.update({
            "name": name,
            "bytes": len(authored),
            "authored_map_sha256": hashlib.sha256(
                bytes(authored) if max(authored, default=0) <= 255
                else b"".join(int(value).to_bytes(2, "big") for value in authored)
            ).hexdigest(),
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
    removed = record.get("removed_loop")
    expected_removed = {
        "action_offset": 13, "actions": "ESNW", "anchor": [14, 10],
        "original_walk_sha256":
            "c880f79e1c7e4366cd7421f93875940690bf3fbf6d655ae8ed0a0a3fed44557b",
    }
    if removed != expected_removed:
        raise ValueError(f"{path}: demo walk removed-loop provenance differs")
    offset = removed["action_offset"]
    original_text = text[:offset] + removed["actions"] + text[offset:]
    original_actions = bytes("NESW".index(value) for value in original_text) + b"\xff"
    if (len(original_text) != 147 or
            hashlib.sha256(original_actions).hexdigest() !=
            removed["original_walk_sha256"]):
        raise ValueError(f"{path}: original demo walk cannot be reconstructed")
    if (record["source_route_sha256"] != route["source_sha256"] or
            record["source_program_sha256"] != route["program_sha256"] or
            record["source_action_count"] != route["action_count"]):
        raise ValueError(f"{path}: demo walk arcade provenance differs")
    position = list(record["start_cell"])
    movement = ((0, -2), (2, 0), (0, 2), (-2, 0))
    positions = []
    for direction in original_actions[:-1]:
        positions.append(tuple(position))
        dx, dy = movement[direction]
        position[0] += dx
        position[1] += dy
    if position != record["end_cell"]:
        raise ValueError(f"{path}: demo walk endpoint differs")
    if positions[offset] != tuple(removed["anchor"]):
        raise ValueError(f"{path}: removed-loop anchor differs")
    for detour in record["detours"]:
        offset = int(detour["action_offset"])
        detour_text = str(detour["actions"])
        if positions[offset] != tuple(detour["anchor"]):
            raise ValueError(f"{path}: detour anchor differs at action {offset}")
        if original_text[offset:offset + len(detour_text)] != detour_text:
            raise ValueError(f"{path}: detour actions differ at action {offset}")
        x, y = detour["anchor"]
        for value in detour_text:
            dx, dy = movement["NESW".index(value)]
            x += dx
            y += dy
        if [x, y] != detour["anchor"]:
            raise ValueError(f"{path}: detour does not return to its anchor")
    backbone = original_text
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
        "removed_loop": removed,
    }


def emit_include(path: Path, maps: list[bytes], tiles: list[bytes],
                 encoded_maps: list[bytes], manifest: dict[str, object],
                 chars: list[list[list[int]]],
                 high_score_layout: list[dict[str, object]],
                 hud_layout: dict[str, dict[str, object]]) -> None:
    lines = [
        "; Generated by scripts/build_presentation.py; do not edit.",
        f"PRESENTATION_MAP_COUNT equ {len(maps)}",
        f"PRESENTATION_MAP_BYTES equ {MAP_BYTES}",
        f"PRESENTATION_STAGE_PANEL_ENABLED equ {int(manifest['complete_profile'])}",
        f"PRESENTATION_TILE_BYTES equ {TILE_BYTES}",
        f"PRESENTATION_TILE_COUNT equ {len(tiles)}",
        f"PRESENTATION_COLD_PAGE equ ${COLD_PAGE:02X}",
        f"PRESENTATION_COLD_PAGE_COUNT equ {COLD_PAGE_COUNT}",
        f"PRESENTATION_COLD_SIZE equ {manifest['cold_payload']['bytes']}",
        f"PRESENTATION_TILE_ATLAS_OFFSET equ {manifest['tile_atlas_runtime_offset']}",
        f"PRESENTATION_TILE_OFFSET equ {manifest['tile_atlas_runtime_offset']}",
        f"PRESENTATION_TILE_ATLAS_SOURCE_OFFSET equ {manifest['tile_atlas_offset']}",
        f"PRESENTATION_TILE_ATLAS_COMPRESSED_BYTES equ {manifest['tile_atlas_compressed_bytes']}",
        f"PRESENTATION_TILE_ATLAS_EXPANDED_BYTES equ {manifest['tile_atlas_expanded_bytes']}",
        f"PRESENTATION_COLD_ONLY_TILE_COUNT equ {manifest['cold_only_tile_count']}",
        f"PRESENTATION_GAMEPLAY_TILE_BASE equ {manifest['gameplay_tile_base']}",
        f"PRESENTATION_GAMEPLAY_LOOKUP_OFFSET equ {manifest['gameplay_lookup_offset']}",
        f"PRESENTATION_GAMEPLAY_LOOKUP_BYTES equ {manifest['gameplay_lookup_bytes']}",
        f"PRESENTATION_PHASE_TILE_OVERLAY_ENABLED equ {1 if manifest['phase_tile_overlay']['enabled'] else 0}",
        f"PRESENTATION_PHASE_TILE_SLOT_0 equ {manifest['phase_tile_overlay']['slot_ids'][0] if manifest['phase_tile_overlay']['slot_ids'] else 0}",
        f"PRESENTATION_PHASE_TILE_SLOT_1 equ {manifest['phase_tile_overlay']['slot_ids'][1] if manifest['phase_tile_overlay']['slot_ids'] else 0}",
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
        f"PRESENTATION_PART_VEGETABLE_DST equ ${int(hud_layout['VEGETABLE_ICON']['destination']):04X}",
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
    name_entry = manifest["high_score_name_entry"]
    name_dst = name_entry["name_destinations"][0] if name_entry["name_destinations"] else 0
    top_name_dst = name_entry["top_name_destinations"][0] if name_entry["top_name_destinations"] else 0
    score_dst = name_entry["score_destinations"][0] if name_entry["score_destinations"] else 0
    top_dst = name_entry["top_destinations"][0] if name_entry["top_destinations"] else 0
    top_right_dst = (
        name_entry["top_right_destinations"][0]
        if name_entry["top_right_destinations"] else 0
    )
    lines.extend((
        "",
        "; FEAT-003 authored high-score name-entry contract.",
        f"PRESENTATION_NAME_ENTRY_CURSOR_OFFSET equ ${name_entry['cursor_stream_offset']:04X}",
        f"PRESENTATION_NAME_ENTRY_CURSOR_BYTES equ {name_entry['cursor_stream_bytes']}",
        f"PRESENTATION_NAME_ENTRY_CURSOR_DST equ ${name_entry['cursor_destination']:04X}",
        f"PRESENTATION_NAME_ENTRY_CURSOR_CODE equ {name_entry['cursor_source_code']}",
        f"PRESENTATION_NAME_ENTRY_GRID_COUNT equ {len(name_entry['grid_cells'])}",
        f"PRESENTATION_NAME_ENTRY_CL_COUNT equ {len(name_entry['cl_cells'])}",
        f"PRESENTATION_NAME_ENTRY_END_COUNT equ {len(name_entry['end_cells'])}",
        f"PRESENTATION_NAME_ENTRY_NAME_DST equ ${name_dst:04X}",
        f"PRESENTATION_NAME_ENTRY_TOP_NAME_DST equ ${top_name_dst:04X}",
        f"PRESENTATION_NAME_ENTRY_SCORE_DST equ ${score_dst:04X}",
        f"PRESENTATION_NAME_ENTRY_TOP_DST equ ${top_dst:04X}",
        f"PRESENTATION_NAME_ENTRY_TOP_RIGHT_DST equ ${top_right_dst:04X}",
        f"PRESENTATION_NAME_ENTRY_BLACK_TILE equ {manifest['black_tile']}",
        f"PRESENTATION_NAME_ENTRY_TIMER_TABLE equ ${name_entry['timer_table_offset']:04X}",
        f"PRESENTATION_NAME_ENTRY_TIMER_RECORD_BYTES equ 4",
        f"PRESENTATION_NAME_ENTRY_TIMER_FRAMES equ {name_entry['timer_frames_per_box']}",
        f"PRESENTATION_NAME_ENTRY_TIMER_COUNT equ {name_entry['timer_box_count']}",
        f"PRESENTATION_NAME_ENTRY_EDGE_MASK_TABLE equ ${name_entry['edge_mask_table_offset']:04X}",
        f"PRESENTATION_NAME_ENTRY_EDGE_MASK_BYTES equ {name_entry['edge_mask_table_bytes']}",
        f"PRESENTATION_NAME_ENTRY_FULL_EDGE_MASK_TABLE equ ${name_entry['full_edge_mask_table_offset']:04X}",
        f"PRESENTATION_NAME_ENTRY_FULL_EDGE_MASK_BYTES equ {name_entry['full_edge_mask_table_bytes']}",
        f"PRESENTATION_NAME_ENTRY_ACTION_TABLE equ ${name_entry['action_table_offset']:04X}",
        f"PRESENTATION_NAME_ENTRY_ACTION_BYTES equ {name_entry['action_table_bytes']}",
    ))
    lines.append("PRESENTATION_NAME_ENTRY_GRID_TILES")
    lines.append("PRESENTATION_NAME_ENTRY_GRID_CELLS")
    lines.append("PRESENTATION_NAME_ENTRY_NODE_TILES")
    lines.append("        ifne    PRESENTATION_NAME_ENTRY_DATA")
    if name_entry["node_tile_ids"]:
        lines.append("        fcb     " + ",".join(
            f"${int(tile_id):02X}" for tile_id in name_entry["node_tile_ids"]
        ))
    lines.append("PRESENTATION_NAME_ENTRY_NODE_DESTINATIONS")
    lines.append("        endc")
    for index, tile_id in enumerate(name_entry["default_name_tile_ids"]):
        lines.append(
            f"PRESENTATION_HIGHSCORE_DEFAULT_NAME_{index} equ ${int(tile_id):02X}"
        )
    lines.extend((
        "",
        "; FEAT-013 named HUD geometry shared by gameplay and side-HUD screens.",
        f"PRESENTATION_HUD_FIELD_COUNT equ {len(hud_layout)}",
        f"PRESENTATION_HUD_LAYOUT_SCREEN_COUNT equ {manifest['shared_hud_layout']['screen_count']}",
        "PRESENTATION_HUD_DRAW_PRIMARY equ $01",
        "PRESENTATION_HUD_DRAW_LIVES equ $02",
        "PRESENTATION_HUD_DRAW_MULTIPLIER equ $04",
        "PRESENTATION_HUD_DRAW_SPECIAL equ $08",
        "PRESENTATION_HUD_DRAW_EXTRA equ $10",
        "PRESENTATION_HUD_DRAW_ALL equ $1F",
    ))
    for name, field in hud_layout.items():
        x, y = (int(value) for value in field["cell"])
        width, height = (int(value) for value in field["size"])
        prefix = f"PRESENTATION_HUD_{name}"
        lines.extend((
            f"{prefix}_X equ {x}",
            f"{prefix}_Y equ {y}",
            f"{prefix}_WIDTH equ {width}",
            f"{prefix}_HEIGHT equ {height}",
            f"{prefix}_DST equ ${int(field['destination']):04X}",
        ))
    rotated = [rotate_ccw(tile) for tile in chars]
    for code in range(37):
        packed = pack_tile(recolor(rotated[code], (BLACK, WHITE, WHITE, WHITE)))
        if packed not in tiles:
            if not manifest["development_profile"]:
                raise ValueError(f"presentation glyph {code} is absent from atlas")
            continue
        lines.append(f"PRESENTATION_GLYPH_{code} equ {tiles.index(packed)}")
    lines.extend((
        "",
        "; Nine fixed seven-character session records live in PAR5 page $34.",
        "PRESENTATION_HIGHSCORE_BASE equ $AF84",
        "PRESENTATION_HIGHSCORE_RECORD_BYTES equ 10",
        f"PRESENTATION_HIGHSCORE_SCORE_BYTES equ {HIGH_SCORE_SCORE_BYTES}",
        "PRESENTATION_HIGHSCORE_NAME_BYTES equ 7",
        "PRESENTATION_HIGHSCORE_COUNT equ 9",
        f"PRESENTATION_HIGHSCORE_DISPLAY_ROWS equ {len(high_score_layout)}",
        "PRESENTATION_HIGHSCORE_ROW_STRIDE equ 1280",
    ))
    for placement in high_score_layout:
        slot = str(placement["slot"])
        name_destination = int(placement["name_destination"])
        score_destination = int(placement["score_destination"])
        lines.append(
            f"PRESENTATION_HIGHSCORE_{slot}_NAME_DST equ ${name_destination:04X}"
        )
        lines.append(
            f"PRESENTATION_HIGHSCORE_{slot}_SCORE_DST equ ${score_destination:04X}"
        )
    rank_one = high_score_layout[0]
    name_delta = int(rank_one["score_destination"]) - int(rank_one["name_destination"])
    lines.extend((
        f"PRESENTATION_HIGHSCORE_SCORE_NAME_DELTA equ {name_delta}",
        "PRESENTATION_HIGHSCORE_TOP_NAME_DST equ PRESENTATION_HIGHSCORE_RANK_01_NAME_DST",
        "PRESENTATION_HIGHSCORE_TOP_SCORE_DST equ PRESENTATION_HIGHSCORE_RANK_01_SCORE_DST",
        "PRESENTATION_HIGHSCORE_ENTRY_NAME_DST equ PRESENTATION_HIGHSCORE_RANK_01_NAME_DST",
        "PRESENTATION_HIGHSCORE_ENTRY_SCORE_DST equ PRESENTATION_HIGHSCORE_RANK_01_SCORE_DST",
    ))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="ascii")


def emit_hud_layout_include(path: Path, hud_layout: dict[str, dict[str, object]]) -> None:
    """Emit authored field geometry consumed by page-$3D HUD painters."""
    lines = [
        "; Generated by scripts/build_presentation.py from the named HUD layer.",
        f"PRESENTATION_MAP_INSTRUCTIONS equ {MAP_NAMES.index('instructions')}",
        "PRESENTATION_HUD_DRAW_SPECIAL equ $08",
        "PRESENTATION_HUD_DRAW_EXTRA equ $10",
    ]
    for name in ("SPECIAL_PROGRESS", "EXTRA_PROGRESS"):
        field = hud_layout[name]
        x, y = (int(value) for value in field["cell"])
        width, _height = (int(value) for value in field["size"])
        prefix = f"PRESENTATION_HUD_{name}"
        lines.extend((
            f"{prefix}_X equ {x}",
            f"{prefix}_Y equ {y}",
            f"{prefix}_WIDTH equ {width}",
        ))
    for name in ("P1_LABEL", "P1_SCORE"):
        field = hud_layout[name]
        prefix = f"PRESENTATION_HUD_{name}"
        lines.extend((
            f"{prefix}_DST equ ${int(field['destination']):04X}",
            f"{prefix}_WIDTH equ {int(field['size'][0])}",
        ))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="ascii")


def main() -> None:
    args = parse_args()
    development_profile = bool(args.development_profile)
    complete_profile = bool(args.complete_profile)
    highscore_test_profile = bool(args.highscore_test_profile)
    colour_config = load_text_colours(args.text_colours)
    hud_layout = parse_hud_layout(args.tiled_dir / "coco-template.tmx")
    args.hud_layout = hud_layout
    hud_screen_layouts = parse_hud_screen_layouts(args.tiled_dir, hud_layout)
    high_score_layout = parse_high_score_layout(
        args.tiled_dir / MAP_FILES["high-score"], colour_config
    )
    shared = None
    if args.shared_text:
        if not complete_profile:
            raise ValueError('shared text currently requires complete profile')
        import sys
        from shared_text import SharedText
        shared = SharedText(args, sys.modules[__name__])
        if shared.font[-1] != bytes(8):
            raise ValueError("PART HUD requires the final compact glyph to be blank")
    chars = load_chars(args.chars)
    names = ("CUCUMBER", "EGGPLANT", "CARROT", "RADISH", "PARSLEY", "TOMATO",
             "PUMPKIN", "BAMBOO SHOOT", "JAPANESE RADISH", "MUSHROOM", "POTATO",
             "ONION", "CHINESE CABBAGE", "TURNIP", "RED PEPPER", "CELERY",
             "SWEET POTATO", "HORSERADISH")
    panel = ["; BUG-035: game/overview vegetable order; resident sprites remain authoritative.",
             "stage_panel_records"]
    for index, name in enumerate(names):
        text = name.center(16) + str(1000 + index * 500)
        codes = [36 if c == " " else int(c) if c.isdigit() else ord(c) - ord("A") + 10 for c in text]
        panel.append("        fcb     " + ",".join(str(v) for v in codes))
    panel.append("stage_panel_font")
    for code in range(37):
        masks = [sum((1 << (7 - x)) for x, v in enumerate(row) if v)
                 for row in rotate_ccw(chars[code])] if code < 36 else [0] * 8
        panel.append("        fcb     " + ",".join(str(v) for v in masks))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    (args.output.parent / "ladybug_stage_panel.inc").write_text("\n".join(panel) + "\n", encoding="ascii")
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
        args.tiled_dir, chars, tiles, tile_ids, development_profile,
        highscore_test_profile, complete_profile, colour_config, hud_layout,
    )
    if development_profile:
        instruction = parse_instruction_contract(
            args.tiled_dir / MAP_FILES["instructions"], chars, sprites,
            tiles, tile_ids, hud_layout,
        )
    else:
        instruction = parse_instruction_contract(
            args.tiled_dir / MAP_FILES["instructions"], chars, sprites, [], {},
            hud_layout,
        )
    name_entry = (
        parse_enter_high_score_contract(
            args.tiled_dir / MAP_FILES["enter-high-score"], chars, sprites,
            tiles, tile_ids,
        )
        if highscore_test_profile or complete_profile
        else {
            "cursor_stream": b"", "cursor_source_code": 0,
            "cursor_destination": 0, "cursor_cell": (19, 22),
            "grid_cells": [], "grid_tile_ids": [], "cl_cells": [],
            "end_cells": [], "name_destinations": [], "top_name_destinations": [],
            "score_destinations": [], "top_destinations": [],
            "top_right_destinations": [],
            "node_cells": [], "node_tile_ids": [], "node_destinations": [],
            "action_records": [], "default_name_tile_ids": [],
            "timer_base_tile_ids": [], "timer_green_tile_ids": [],
            "timer_table_offset": 0,
            "timer_frames_per_box": ENTER_HIGH_SCORE_TIMER_FRAMES,
            "timer_box_count": ENTER_HIGH_SCORE_TIMER_COUNT,
            "edge_mask_table_offset": 0,
            "edge_mask_table_bytes": 0,
            "edge_masks": [],
            "full_edge_mask_table_offset": 0,
            "full_edge_mask_table_bytes": 0,
            "full_edge_masks": [],
            "action_table_offset": 0,
            "action_table_bytes": 0,
            "action_table": [],
        }
    )
    _arcade_route, arcade_route_manifest = load_demo_route(args.demo_route)
    demo_walk, demo_walk_manifest = load_demo_walk(
        args.demo_walk, arcade_route_manifest
    )

    if len(tiles) > 256 and not complete_profile:
        raise ValueError(
            f"presentation atlas contains {len(tiles)} tiles; one-byte limit is 256"
        )

    if name_entry["grid_tile_ids"]:
        enter_map = maps[MAP_NAMES.index("enter-high-score")]
        timer_base_tile_ids = []
        timer_green_tile_ids = []
        for x, y in perimeter_box_cells():
            base_id = enter_map[y * SCREEN_WIDTH + x]
            timer_base_tile_ids.append(base_id)
            timer_green_tile_ids.append(register_tile(
                replace_packed_colour(tiles[base_id], WHITE, GREEN),
                tiles, tile_ids,
            ))
        name_entry["timer_base_tile_ids"] = timer_base_tile_ids
        name_entry["timer_green_tile_ids"] = timer_green_tile_ids
        if len(tiles) > 256 and not complete_profile:
            raise ValueError(
                f"presentation atlas contains {len(tiles)} tiles; one-byte limit is 256"
            )

    if shared:
        maps = shared.separate_static(maps, tiles, tile_ids)
    gameplay_tile_ids = {tile: index for index, tile in enumerate(gameplay_tiles)}
    timer_green_tiles: list[bytes] = []
    timer_green_indexes: list[int] = []
    for tile_id in name_entry["timer_green_tile_ids"]:
        tile = tiles[int(tile_id)]
        try:
            index = timer_green_tiles.index(tile)
        except ValueError:
            index = len(timer_green_tiles)
            timer_green_tiles.append(tile)
        timer_green_indexes.append(index)
    live_tile_ids = set().union(*(set(data) for data in maps))
    if development_profile:
        live_tile_ids.add(int(instruction["black_tile_id"]))
        for group in ("reward_tile_ids", "multiplier_tile_ids", "value_tile_ids"):
            for ids in instruction[group].values():
                live_tile_ids.update(int(tile_id) for tile_id in ids)
        for event in instruction["events"]:
            if event["hud_destination"]:
                live_tile_ids.add(int(event["hud_tile_id"]))
                if event["hud_tile_2_id"]:
                    live_tile_ids.add(int(event["hud_tile_2_id"]))
    if name_entry["grid_tile_ids"]:
        for key in (
            "grid_tile_ids", "default_name_tile_ids", "top_name_tile_ids",
            "timer_base_tile_ids",
        ):
            live_tile_ids.update(int(tile_id) for tile_id in name_entry[key])
        live_tile_ids.update(
            int(tile_id) for tile_id in name_entry["node_tile_ids"]
            if tile_id not in (0xFD, 0xFE, 0xFF)
        )
        live_tile_ids.update(
            int(tile_id) for _x, _y, tile_id in name_entry["action_records"]
            if tile_id not in (0xFD, 0xFE, 0xFF)
        )
        if complete_profile and name_entry["timer_green_tile_ids"]:
            # Retain one phase-native green perimeter tile in the atlas; the
            # seven additional timer variants live in bounded cold tile data.
            live_tile_ids.add(int(name_entry["timer_green_tile_ids"][0]))
    overlay_pairs: list[tuple[int, int]] = []
    if complete_profile:
        overflow = len(live_tile_ids) - 256
        if overflow > 2:
            raise ValueError(
                f"complete presentation union needs {overflow} overlaid tile slots; "
                "existing phase allocation supports at most two; "
                f"live={len(live_tile_ids)} timer-green="
                f"{len(set(name_entry['timer_green_tile_ids']))}"
            )
        instruction_ids = set(maps[MAP_NAMES.index("instructions")])
        highscore_ids = set().union(*(
            set(maps[MAP_NAMES.index(name)])
            for name in ("game-over", "enter-high-score", "high-score")
        ))
        other_ids = set().union(*(
            set(maps[MAP_NAMES.index(name)])
            for name in ("attract", "level-start")
        ))
        instruction_candidates = sorted(
            tile_id for tile_id in instruction_ids - highscore_ids - other_ids
            if tile_id in live_tile_ids and tiles[tile_id] not in gameplay_tile_ids
        )
        highscore_candidates = sorted(
            tile_id for tile_id in highscore_ids - instruction_ids - other_ids
            if tile_id in live_tile_ids and tiles[tile_id] not in gameplay_tile_ids
        )
        if len(instruction_candidates) < 2 or len(highscore_candidates) < 2:
            raise ValueError("complete presentation lacks two phase-exclusive tile pairs")
        overlay_pairs = list(zip(
            instruction_candidates[:2], highscore_candidates[:2]
        ))
    elif len(live_tile_ids) > 256:
        raise ValueError("presentation atlas exceeds one-byte tile IDs")

    overlay_replacements = {
        highscore_id: instruction_id
        for instruction_id, highscore_id in overlay_pairs
    }
    representative_ids = [
        tile_id for tile_id in sorted(live_tile_ids)
        if tile_id not in overlay_replacements
    ]
    cold_tile_ids = [
        tile_id for tile_id in representative_ids
        if tiles[tile_id] not in gameplay_tile_ids
    ]
    gameplay_match_ids = [
        tile_id for tile_id in representative_ids
        if tiles[tile_id] in gameplay_tile_ids
    ]
    ordered_ids = cold_tile_ids + gameplay_match_ids
    representative_remap = {
        old_id: new_id for new_id, old_id in enumerate(ordered_ids)
    }
    remap = {
        old_id: representative_remap[overlay_replacements.get(old_id, old_id)]
        for old_id in live_tile_ids
    }
    instruction_patch_set = b"".join(
        tiles[instruction_id] for instruction_id, _highscore_id in overlay_pairs
    )
    highscore_patch_set = b"".join(
        tiles[highscore_id] for _instruction_id, highscore_id in overlay_pairs
    )
    overlay_slots = [remap[instruction_id] for instruction_id, _ in overlay_pairs]
    maps = [bytes(remap[tile_id] for tile_id in data) for data in maps]
    for info, data in zip(map_info, maps):
        info["sha256"] = hashlib.sha256(data).hexdigest()
    tiles = [tiles[tile_id] for tile_id in ordered_ids]
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
    if name_entry["grid_tile_ids"]:
        name_entry["grid_tile_ids"] = [
            remap[int(tile_id)] for tile_id in name_entry["grid_tile_ids"]
        ]
        name_entry["node_tile_ids"] = [
            tile_id if tile_id in (0xFD, 0xFE, 0xFF) else remap[int(tile_id)]
            for tile_id in name_entry["node_tile_ids"]
        ]
        name_entry["action_records"] = [
            [x, y, remap[int(tile_id)]]
            if tile_id not in (0xFD, 0xFE, 0xFF)
            else [x, y, tile_id]
            for x, y, tile_id in name_entry["action_records"]
        ]
        name_entry["default_name_tile_ids"] = [
            remap[int(tile_id)] for tile_id in name_entry["default_name_tile_ids"]
        ]
        name_entry["top_name_tile_ids"] = [
            remap[int(tile_id)] for tile_id in name_entry["top_name_tile_ids"]
        ]
        name_entry["timer_base_tile_ids"] = [
            remap[int(tile_id)] for tile_id in name_entry["timer_base_tile_ids"]
        ]
        name_entry["timer_green_tile_ids"] = []
    cold_only_tiles = tiles[:len(cold_tile_ids)]
    gameplay_lookup = bytes(
        gameplay_tile_ids[tiles[tile_id]]
        for tile_id in range(len(cold_tile_ids), len(tiles))
    )
    encoded_maps = [encode_map(data) for data in maps]
    tile_atlas = b"".join(cold_only_tiles)
    stored_tile_atlas = (
        lzss_compress(tile_atlas) if highscore_test_profile else tile_atlas
    )
    tile_atlas_offset = 0
    gameplay_lookup_offset = len(stored_tile_atlas)
    map_stream_offset = gameplay_lookup_offset + len(gameplay_lookup)
    map_stream_offsets = []
    encoded_stream = bytearray()
    for encoded in encoded_maps:
        map_stream_offsets.append(map_stream_offset + len(encoded_stream))
        encoded_stream.extend(encoded)
    attract_destinations = b"".join(
        int(actor["destination"]).to_bytes(2, "big") for actor in actors
    )
    visual_maps, visual_tiles = (shared.visual_maps, shared.visual_tiles) if shared else (maps, tiles)
    logo_roots, _ = compile_logo_frames(title_framebuffer(visual_maps[0], visual_tiles))
    attract_destinations += b"".join(framebuffer_destination(root).to_bytes(2, "big") for root in logo_roots)
    attract_surfaces = compile_attract_surfaces(visual_maps[0], visual_tiles, sprites, actors)
    attract_frames = compose_attract_frames(visual_maps[0], visual_tiles, attract_surfaces, actors)
    attract_phase_pointers = b"".join(
        (ATTRACT_ACTOR_SURFACE_ADDRESS + phase * ATTRACT_COPY_COUNT * 128).to_bytes(2, "big")
        for phase in ATTRACT_ACTOR_PHASES
    )
    attract_compressed = lzss_compress(attract_surfaces)
    attract_metadata = attract_destinations + attract_phase_pointers
    cold_payload = bytearray(
        stored_tile_atlas + gameplay_lookup + bytes(encoded_stream)
    )
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
    name_entry_cursor_offset = len(cold_payload)
    cold_payload.extend(name_entry["cursor_stream"])
    name_entry["cursor_stream_offset"] = name_entry_cursor_offset
    name_entry["cursor_stream_bytes"] = len(name_entry["cursor_stream"])
    demo_route_offset = len(cold_payload)
    cold_payload.extend(demo_walk)
    name_entry_timer_tiles_offset = len(cold_payload)
    cold_payload.extend(b"".join(timer_green_tiles))
    name_entry_timer_offset = len(cold_payload)
    for cell, green_index in zip(perimeter_box_cells(), timer_green_indexes):
        cold_payload.extend(
            framebuffer_destination(cell).to_bytes(2, "big") +
            (name_entry_timer_tiles_offset + green_index * TILE_BYTES).to_bytes(
                2, "big"
            )
        )
    name_entry_edge_mask_offset = len(cold_payload)
    edge_masks = enter_high_score_edge_masks() if name_entry["grid_tile_ids"] else b""
    cold_payload.extend(edge_masks)
    name_entry["edge_mask_table_offset"] = name_entry_edge_mask_offset
    name_entry["edge_mask_table_bytes"] = len(edge_masks)
    name_entry["edge_masks"] = list(edge_masks)
    full_edge_masks = (
        enter_high_score_full_edge_masks(
            args.tiled_dir / MAP_FILES["enter-high-score"],
            chars, compile_player_sprites(args.gameplay_sprites),
        )
        if name_entry["grid_tile_ids"] else b""
    )
    name_entry_full_edge_mask_offset = len(cold_payload)
    cold_payload.extend(full_edge_masks)
    action_table = bytes(
        byte
        for x, y, tile_id in name_entry["action_records"]
        for byte in (x - 8, y, tile_id)
    )
    name_entry_action_offset = len(cold_payload)
    cold_payload.extend(action_table)
    name_entry["full_edge_mask_table_offset"] = name_entry_full_edge_mask_offset
    name_entry["full_edge_mask_table_bytes"] = len(full_edge_masks)
    name_entry["full_edge_masks"] = list(full_edge_masks)
    name_entry["action_table_offset"] = name_entry_action_offset
    name_entry["action_table_bytes"] = len(action_table)
    name_entry["action_table"] = list(action_table)
    effective_cold_limit = PAGE_BYTES * 2 if complete_profile else COLD_PAYLOAD_LIMIT
    if len(cold_payload) > effective_cold_limit:
        raise ValueError(
            f"presentation cold payload is {len(cold_payload)} bytes; "
            f"limit is {effective_cold_limit}"
        )
    static_frame_hashes = []
    highscore_phase_tiles = list(tiles)
    for slot_id, tile in zip(
            overlay_slots,
            (highscore_patch_set[index:index + TILE_BYTES]
             for index in range(0, len(highscore_patch_set), TILE_BYTES))):
        highscore_phase_tiles[slot_id] = tile
    for index, data in enumerate(maps):
        frame = title_framebuffer(
            data,
            highscore_phase_tiles if index in (
                MAP_NAMES.index("game-over"),
                MAP_NAMES.index("enter-high-score"),
                MAP_NAMES.index("high-score"),
            ) else tiles,
        )
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
        "complete_profile": bool(args.complete_profile),
        "highscore_test_profile": highscore_test_profile,
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
        "shared_hud_layout": {
            "source_template": "coco-template.tmx",
            "layer": HUD_LAYOUT_LAYER,
            "grid_pixels": [8, 8],
            "screen_count": len(hud_screen_layouts),
            "screens": list(hud_screen_layouts),
            "layouts": hud_screen_layouts,
            "fields": hud_layout,
        },
        "raw_sprite_markers": {
            "gameplay": [
                {"cell": list(cell), "gid": value & GID_MASK,
                 "flags": value & ~GID_MASK}
                for cell, value in sorted(GAMEPLAY_SPRITE_LOCATIONS.items())
            ],
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
        "tile_atlas_compressed_bytes": len(stored_tile_atlas),
        "tile_atlas_expanded_bytes": len(tile_atlas),
        "tile_atlas_runtime_offset": PAGE_BYTES if highscore_test_profile else 0,
        "phase_tile_overlay": {
            "enabled": bool(overlay_pairs),
            "slot_ids": overlay_slots,
            "instruction_patch_bytes": len(instruction_patch_set),
            "highscore_patch_bytes": len(highscore_patch_set),
            "instruction_patch_sha256": hashlib.sha256(instruction_patch_set).hexdigest(),
            "highscore_patch_sha256": hashlib.sha256(highscore_patch_set).hexdigest(),
        },
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
        "high_score_name_entry": {
            "emitted": bool(name_entry["grid_tile_ids"]),
            "metadata_layer": ENTER_HIGH_SCORE_METADATA_LAYER,
            "cursor_cell": list(name_entry["cursor_cell"]),
            "cursor_destination": name_entry["cursor_destination"],
            "cursor_source_code": name_entry["cursor_source_code"],
            "cursor_stream_offset": name_entry_cursor_offset,
            "cursor_stream_bytes": len(name_entry["cursor_stream"]),
            "cursor_stream_sha256": hashlib.sha256(
                name_entry["cursor_stream"]
            ).hexdigest(),
            "grid_cells": [list(cell) for cell in name_entry["grid_cells"]],
            "grid_tile_ids": name_entry["grid_tile_ids"],
            "node_cells": [list(cell) for cell in name_entry["node_cells"]],
            "node_tile_ids": name_entry["node_tile_ids"],
            "action_records": name_entry["action_records"],
            "default_name_tile_ids": name_entry["default_name_tile_ids"],
            "authored_name_codes": list(ENTER_HIGH_SCORE_DEFAULT_CODES),
            "top_name_tile_ids": name_entry.get("top_name_tile_ids", []),
            "node_destinations": name_entry["node_destinations"],
            "cl_cells": [list(cell) for cell in name_entry["cl_cells"]],
            "end_cells": [list(cell) for cell in name_entry["end_cells"]],
            "name_destinations": name_entry["name_destinations"],
            "top_name_destinations": name_entry["top_name_destinations"],
            "score_destinations": name_entry["score_destinations"],
            "top_destinations": name_entry["top_destinations"],
            "top_right_destinations": name_entry["top_right_destinations"],
            "timer_table_offset": name_entry_timer_offset,
            "timer_table_bytes": len(name_entry["timer_base_tile_ids"]) * 4,
            "timer_tile_data_offset": name_entry_timer_tiles_offset,
            "timer_tile_data_bytes": len(timer_green_tiles) * TILE_BYTES,
            "timer_frames_per_box": ENTER_HIGH_SCORE_TIMER_FRAMES,
            "timer_box_count": ENTER_HIGH_SCORE_TIMER_COUNT,
            "timer_cells": [list(cell) for cell in perimeter_box_cells()],
            "timer_base_tile_ids": name_entry["timer_base_tile_ids"],
            "timer_green_tile_ids": name_entry["timer_green_tile_ids"],
            "edge_mask_table_offset": name_entry_edge_mask_offset,
            "edge_mask_table_bytes": len(edge_masks),
            "edge_masks": list(edge_masks),
            "full_edge_mask_table_offset": name_entry["full_edge_mask_table_offset"],
            "full_edge_mask_table_bytes": name_entry["full_edge_mask_table_bytes"],
            "full_edge_masks": name_entry["full_edge_masks"],
            "action_table_offset": name_entry["action_table_offset"],
            "action_table_bytes": name_entry["action_table_bytes"],
            "action_table": name_entry["action_table"],
        },
        "high_score_table": {
            "layout_layer": HIGH_SCORE_LAYOUT_LAYER,
            "record_count": 9,
            "record_bytes": 10,
            "score_bytes": HIGH_SCORE_SCORE_BYTES,
            "score_max_digits": HIGH_SCORE_SCORE_BYTES * HIGH_SCORE_BCD_DIGITS_PER_BYTE,
            "name_bytes": 7,
            "display_rows": len(high_score_layout),
            "placements": high_score_layout,
        },
        "demo_route": {
            **demo_walk_manifest,
            "cold_offset": demo_route_offset,
            "bytes": len(demo_walk),
        },
        "attract_actor_destinations": {
            "bytes": len(attract_destinations),
            "count": ATTRACT_COPY_COUNT,
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
            "logo_roots": logo_roots,
            "phase_frame_sha256": [hashlib.sha256(frame).hexdigest()
                                   for frame in attract_frames],
            "phase_crop_sha256": [
                [hashlib.sha256(attract_surfaces[
                    (phase * ATTRACT_COPY_COUNT + actor_index) * ATTRACT_ACTOR_BYTES:
                    (phase * ATTRACT_COPY_COUNT + actor_index + 1) * ATTRACT_ACTOR_BYTES
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
        "black_tile": tiles.index(bytes(TILE_BYTES)),
        "cold_page": COLD_PAGE,
        "cold_page_count": COLD_PAGE_COUNT,
        "cold_payload_limit": effective_cold_limit,
        "cold_payload": {
            "bytes": len(cold_payload),
            "sha256": hashlib.sha256(cold_payload).hexdigest(),
        },
        "static_frame_sha256": static_frame_hashes,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(bytes(cold_payload))
    args.actor_record_output.parent.mkdir(parents=True, exist_ok=True)
    args.actor_record_output.write_bytes(attract_metadata)
    args.actor_underlay_output.parent.mkdir(parents=True, exist_ok=True)
    args.actor_underlay_output.write_bytes(attract_compressed)
    args.tile_patch_output.parent.mkdir(parents=True, exist_ok=True)
    args.tile_patch_output.write_bytes(instruction_patch_set + highscore_patch_set)
    timer_record_bytes = len(name_entry["timer_base_tile_ids"]) * 4
    args.timer_record_output.parent.mkdir(parents=True, exist_ok=True)
    timer_records = bytes(cold_payload[
        name_entry_timer_offset:name_entry_timer_offset + timer_record_bytes
    ])
    timer_lines = ["; Generated name-entry timer records for the page-$24 helper."]
    for offset in range(0, len(timer_records), 16):
        timer_lines.append(
            "        fcb     " + ",".join(
                f"${value:02X}" for value in timer_records[offset:offset + 16]
            )
        )
    args.timer_record_output.write_text("\n".join(timer_lines) + "\n", encoding="ascii")
    args.manifest_output.parent.mkdir(parents=True, exist_ok=True)
    args.manifest_output.write_text(json.dumps(manifest, indent=2) + "\n",
                                    encoding="ascii")
    emit_include(args.include_output, maps, tiles, encoded_maps, manifest, chars,
                 high_score_layout, hud_layout)
    emit_hud_layout_include(args.hud_layout_output, hud_layout)
    if shared:
        shared.finish(manifest, tiles, cold_payload, instruction)
        # BUG-052: reuse the High Score map's authored phase-changing logo tiles.
        # Both screens must keep the same authored relative cells and GIDs;
        # only their Tiled roots differ.
        attract_logo_root, attract_logo_layout = logo_frame_layout("attract")
        high_score_logo_root, high_score_logo_layout = logo_frame_layout("high-score")
        if attract_logo_layout != high_score_logo_layout:
            raise ValueError(
                "Attract and High Score logo frames differ relative to their Tiled roots"
            )
        high_score_index = MAP_NAMES.index("high-score")
        _, logo_frames = compile_logo_frames(
            title_framebuffer(visual_maps[high_score_index], visual_tiles),
            "high-score", colour_config,
        )
        payload = bytearray(args.output.read_bytes())
        high_score_root_destination = framebuffer_destination(high_score_logo_root)
        logo_cells = sorted(
            {
                (high_score_logo_root[0] + x, high_score_logo_root[1] + y)
                for frame in high_score_logo_layout
                for x, y, _gid in frame
            },
            key=lambda cell: (cell[1], cell[0]),
        )
        if len(logo_cells) != 12:
            raise ValueError("high-score logo must retain all twelve authored cells")
        # Keep authored cells even when both rendered phase tiles currently match.
        logo_records = []
        logo_frame_pairs = []
        for x, y in logo_cells:
            offset = y * 1280 + x * 4
            pair = [b"".join(frame[offset + row * 160:offset + row * 160 + 4]
                             for row in range(8)) for frame in logo_frames]
            if any(len(tile) != TILE_BYTES for tile in pair):
                raise ValueError(f"invalid high-score logo tile at {(x, y)}")
            logo_frame_pairs.append(pair)
            logo_records.append(
                framebuffer_destination((x, y)) - high_score_root_destination
            )
        base_payload_bytes = len(payload)
        logo_data_bytes = len(logo_cells) * 2 * TILE_BYTES
        logo_data_offset = ((base_payload_bytes + TILE_BYTES - 1) // TILE_BYTES) * TILE_BYTES
        if logo_data_offset % PAGE_BYTES + logo_data_bytes > PAGE_BYTES:
            logo_data_offset = (logo_data_offset // PAGE_BYTES + 1) * PAGE_BYTES
        payload.extend(bytes(logo_data_offset - base_payload_bytes))
        for pair in logo_frame_pairs:
            payload.extend(b"".join(pair))
        if len(payload) > effective_cold_limit:
            raise ValueError("high-score logo exceeds the presentation cold-payload limit")
        args.output.write_bytes(payload)
        manifest["highscore_logo"] = {
            "source_map": "high-score",
            "roots": {
                "attract": {
                    "cell": list(attract_logo_root),
                    "destination": framebuffer_destination(attract_logo_root),
                },
                "high-score": {
                    "cell": list(high_score_logo_root),
                    "destination": high_score_root_destination,
                },
            },
            "relative_offsets": logo_records,
            "records": [[offset] for offset in logo_records],
            "authored_cells": [list(cell) for cell in logo_cells],
            "base_payload_bytes": base_payload_bytes,
            "data_offset": logo_data_offset,
            "data_bytes": logo_data_bytes,
            "data_stride": 2 * TILE_BYTES,
            "frame_bytes": TILE_BYTES,
            "cells": len(logo_records),
            "appended_bytes": len(payload) - base_payload_bytes,
        }
        manifest["cold_payload"] = {
            "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        }
        include = args.include_output.read_text(encoding="ascii")
        include = re.sub(
            r"PRESENTATION_COLD_SIZE equ \d+",
            f"PRESENTATION_COLD_SIZE equ {len(payload)}",
            include,
        )
        args.include_output.write_text(include, encoding="ascii")
        logo_record_lines = [
            "; Generated Tiled roots, root-relative destinations, and logo frame data.",
            f"PRESENTATION_ATTRACT_LOGO_ROOT equ ${framebuffer_destination(attract_logo_root):04X}",
            f"PRESENTATION_HIGH_SCORE_LOGO_ROOT equ ${high_score_root_destination:04X}",
        ]
        logo_record_lines.extend(
            f"        fdb     ${offset:04X}"
            for offset in logo_records
        )
        logo_record_lines.append("highscore_logo_records_end")
        logo_record_lines.extend((
            "highscore_logo_root_screen",
            "        fcb     $FF",
            "highscore_logo_root",
            "        fdb     $0000",
        ))
        args.include_output.with_name("ladybug_highscore_logo.inc").write_text(
            "\n".join(logo_record_lines) + "\n",
            encoding="ascii",
        )
        args.manifest_output.write_text(json.dumps(manifest, indent=2) + "\n",
                                        encoding="ascii")
    # Place the boot-only bundle after the cold records in their second page.
    bundle_address = 0xA000 + max(0, manifest["cold_payload"]["bytes"] - PAGE_BYTES)
    if bundle_address + len(attract_compressed) + len(attract_metadata) > 0xC000:
        raise ValueError("attract bundle exceeds remaining page-$3B cold allocation")
    with args.include_output.open("a", encoding="ascii") as include:
        include.write(f"\nPRESENTATION_ATTRACT_BUNDLE_PAGE equ $3B\n"
                      f"PRESENTATION_ATTRACT_BUNDLE_ADDRESS equ ${bundle_address:04X}\n")
    print(
        f"presentation: {len(maps)} maps, {len(tiles)} native descriptors, "
        f"{manifest['cold_payload']['bytes']} cold bytes, "
        f"{manifest['cold_payload']['sha256']}"
    )


if __name__ == "__main__":
    main()
