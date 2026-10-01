#!/usr/bin/env python3
"""Capture concise RSCH-014 step-A TMX and compiler-prototype evidence."""
from __future__ import annotations
import hashlib
import json
import pathlib
import sys
import types
import xml.etree.ElementTree as ET
from collections import Counter
from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parents[5]
OUT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "scripts"))
import build_presentation as bp
import build_screen as bs

TMX = ROOT / "tiled"
ASSET = ROOT / "assets" / "arcade"
MAP_NAMES = (
    "coco-screen.tmx", "coco-attract-screen.tmx", "coco-credits-screen.tmx",
    "coco-enter-high-score-screen.tmx", "coco-game-over-screen.tmx",
    "coco-high-score-screen.tmx", "coco-instructions-screen.tmx",
    "coco-keybind-options-screen.tmx", "coco-level-start-screen.tmx",
)

def layer_values(layer: ET.Element) -> list[int]:
    data = layer.find("data")
    return [int(value.strip()) for value in (data.text or "").replace("\n", "").split(",") if value.strip()]

def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def render_static(role: str, filename: str) -> dict[str, str]:
    path = TMX / bp.MAP_FILES[role]
    tiles: list[bytes] = []
    ids: dict[bytes, int] = {}
    tile_map, info = bp.compile_map(path, bs.load_chars(ASSET / "chars.json"), tiles, ids)
    # Label the compiled pen indices with their conventional review colours.
    # The packed pen-frame SHA below remains the exact evidence; display RGB
    # conversion is monitor-dependent on the CoCo 3.
    palette = [
        (0, 0, 0), (255, 0, 0), (255, 255, 0), (0, 0, 255),
        (255, 0, 255), (0, 255, 0), (255, 255, 255), (128, 128, 128),
        (144, 238, 144), (160, 32, 240), (0, 100, 0), (135, 206, 250),
        (139, 0, 0), (255, 165, 0), (255, 255, 255), (0, 0, 0),
    ]
    image = Image.new("RGB", (40 * 8, 24 * 8))
    pixels = image.load()
    for cell, tile_id in enumerate(tile_map):
        x0, y0 = (cell % 40) * 8, (cell // 40) * 8
        packed = tiles[tile_id]
        for ty in range(8):
            row = packed[ty * 4:ty * 4 + 4]
            for bi, byte in enumerate(row):
                for pi, shift in enumerate((4, 0)):
                    pen = (byte >> shift) & 15
                    rgb = tuple(palette[pen])
                    pixels[x0 + bi * 2 + pi, y0 + ty] = rgb
    image.save(OUT / filename, optimize=False)
    pen_frame = bp.title_framebuffer(bytes(tile_map), tiles)
    return {
        "compiled_map_sha256": hashlib.sha256(bytes(tile_map)).hexdigest(),
        "static_frame_packed_pen_sha256": hashlib.sha256(pen_frame).hexdigest(),
        "static_frame_pixel_rgb_sha256": hashlib.sha256(image.tobytes()).hexdigest(),
        "static_frame_png_sha256": digest(OUT / filename),
        "static_frame_png": filename,
        "layer_contract": json.dumps(bp.validate_presentation_layers(ET.parse(path).getroot(), path), sort_keys=True),
    }

inventory = {"source_revision": "fe160ae389145d24083218ded05ba9cdca781474", "maps": {}, "life_grid": {}, "gameplay_border_composition": {}, "instruction_row_wait": {}, "static_screens": {}}
for name in MAP_NAMES:
    path = TMX / name
    root = ET.parse(path).getroot()
    width, height = int(root.get("width", "0")), int(root.get("height", "0"))
    inventory["maps"][name] = {
        "sha256": digest(path), "dimensions": [width, height],
        "layers": [{"name": layer.get("name", ""), "nonzero_cells": sum(v != 0 for v in layer_values(layer))}
                   for layer in root.findall("layer")],
    }

# Current TMX authors twelve marker quadrants in the 3-column by 4-row grid.
root = ET.parse(TMX / "coco-screen.tmx").getroot()
hud = next(layer for layer in root.findall("layer") if layer.get("name") == "HUD Placeholders")
hud_values = layer_values(hud)
quad_gid = {"tl": 456, "tr": 440, "bl": 488, "br": 472}
roots = []
for i, value in enumerate(hud_values):
    if value != quad_gid["tl"]:
        continue
    x, y = i % 40, i // 40
    if hud_values[y * 40 + x + 1] == quad_gid["tr"] and hud_values[(y + 1) * 40 + x] == quad_gid["bl"] and hud_values[(y + 1) * 40 + x + 1] == quad_gid["br"]:
        roots.append((x, y))
expected_roots = [(x, y) for y in (15, 17, 19, 21) for x in (33, 35, 37)]
inventory["life_grid"] = {
    "authored_quadrant_gids": quad_gid, "marker_roots_top_to_bottom": roots,
    "expected_slot_count": 12, "quadrant_cells": 48,
    "exact_3x4_grid": roots == expected_roots,
}

# The compiler's gameplay skip is guarded by a separate exact map contract;
# exercise the valid layer and four malformed shapes without touching TMX.
import copy
game_root = ET.parse(TMX / "coco-screen.tmx").getroot()
game_path = TMX / "coco-screen.tmx"
game_sprite_layer = next(layer for layer in game_root.findall("layer")
                         if layer.get("name") == "Sprite Locations")
game_checks = {"valid": "pass"}
bp_like = bs.validate_gameplay_sprite_locations(game_root, game_path)
game_checks["valid_layer_identity"] = bp_like is game_sprite_layer
cases = {}
missing = copy.deepcopy(game_root)
missing.remove(next(layer for layer in missing.findall("layer")
                    if layer.get("name") == "Sprite Locations"))
cases["missing"] = missing
duplicate = copy.deepcopy(game_root)
duplicate.append(copy.deepcopy(next(layer for layer in duplicate.findall("layer")
                                    if layer.get("name") == "Sprite Locations")))
cases["duplicate"] = duplicate
extra = copy.deepcopy(game_root)
extra_layer = next(layer for layer in extra.findall("layer")
                   if layer.get("name") == "Sprite Locations")
extra_cells = layer_values(extra_layer)
extra_cells[13 * 40 + 33] = 633
extra_layer.find("data").text = ",".join(map(str, extra_cells))
cases["extra_marker"] = extra
wrong_gid = copy.deepcopy(game_root)
wrong_layer = next(layer for layer in wrong_gid.findall("layer")
                   if layer.get("name") == "Sprite Locations")
wrong_cells = layer_values(wrong_layer)
wrong_cells[13 * 40 + 32] = 8
wrong_layer.find("data").text = ",".join(map(str, wrong_cells))
cases["wrong_tileset_gid"] = wrong_gid
for label, candidate in cases.items():
    try:
        bs.validate_gameplay_sprite_locations(candidate, game_path)
    except ValueError as exc:
        game_checks[label] = {"rejected": True, "diagnostic": str(exc)}
    else:
        game_checks[label] = {"rejected": False}
inventory["gameplay_sprite_locations_contract"] = game_checks

screen_result = bs.compile_screen(
    TMX / "coco-screen.tmx", ASSET / "maze.json",
    ASSET / "chars.json", ASSET / "sprites.json",
)
inventory["gameplay_compiler_prototype"] = {
    "result": "pass", "screen_cells": len(screen_result[0]),
    "unique_static_tiles": len(screen_result[1]),
    "source_role": "coco-screen.tmx", "sprite_locations_omitted_after_validation": True,
}

# In-memory candidate only: partition exact outer-ring source cells into an
# overlay while replacing those cells with the authored blank GID in the base.
maze_layer = next(layer for layer in root.findall("layer") if layer.get("name") == "Maze and Panel Background")
source = layer_values(maze_layer)
border_cells = [(x, y) for y in range(24) for x in range(40)
                if 8 <= x < 32 and (y in (0, 23) or x in (8, 31))]
base, border = source[:], [0] * 960
for x, y in border_cells:
    i = y * 40 + x
    border[i] = source[i]
    base[i] = 8
composite = [border[i] or base[i] for i in range(960)]
inventory["gameplay_border_composition"] = {
    "source_layer": "Maze and Panel Background", "candidate_names_are_not_selected": True,
    "outer_ring_cell_count": len(border_cells), "overlay_nonzero_count": sum(v != 0 for v in border),
    "base_blank_gid": 8, "composite_equals_source": composite == source,
    "source_map_sha256": digest(TMX / "coco-screen.tmx"),
}

# Actual current schedule vs two in-memory variants. Only the explicit +90
# earliest gates are removed in the candidate; no source file is written.
source_code = (ROOT / "scripts" / "build_presentation.py").read_text(encoding="utf-8")
chars = bs.load_chars(ASSET / "chars.json")
sprites = bs.load_sprites(ASSET / "sprites.json")
def run_schedule(label: str, row_offsets: tuple[int, int, int], extra_wait: bool) -> dict[str, object]:
    modified = source_code.replace("row_time_offsets = (0, 90, 180)", f"row_time_offsets = {row_offsets}")
    if not extra_wait:
        modified = modified.replace("reference_consumes[4] + 90", "reference_consumes[4]")
        modified = modified.replace("reference_consumes[11] + 90", "reference_consumes[11]")
    module = types.ModuleType("rsch014_" + label)
    module.__file__ = str(ROOT / "scripts" / "build_presentation.py")
    exec(compile(modified, module.__file__, "exec"), module.__dict__)
    contract = module.parse_instruction_contract(TMX / "coco-instructions-screen.tmx", chars, sprites, [], {})
    return {"label": label, "next_screen_tick": contract["next_screen_tick"],
            "events": [{"index": e["index"], "name": e["name"], "motion_tick": e["motion_tick"], "consume_tick": e["consume_tick"]}
                       for e in contract["events"]]}
base_schedule = run_schedule("current", (0, 90, 180), True)
no_gate_schedule = run_schedule("remove_explicit_90_gates", (0, 90, 180), False)
no_row_offsets = run_schedule("remove_arcade_row_offsets", (0, 0, 0), True)
inventory["instruction_row_wait"] = {
    "current_equals_after_removing_explicit_90_gates": base_schedule["events"] == no_gate_schedule["events"],
    "current_next_screen_tick": base_schedule["next_screen_tick"],
    "without_row_offsets_next_screen_tick": no_row_offsets["next_screen_tick"],
    "current_events": [e for e in base_schedule["events"] if e["index"] in (0, 4, 5, 11, 12, 14, 15)],
    "no_gate_events": [e for e in no_gate_schedule["events"] if e["index"] in (0, 4, 5, 11, 12, 14, 15)],
    "rejected_variant_events": [e for e in no_row_offsets["events"] if e["index"] in (0, 4, 5, 11, 12, 14, 15)],
}

# Static-only compiler frames: Sprite Locations and all runtime sprite layers
# are excluded by the active layer contracts. No natural runtime is claimed.
inventory["static_screens"]["attract"] = render_static("attract", "attract-static.png")
inventory["static_screens"]["instructions"] = render_static("instructions", "instructions-static.png")
inventory["static_screens"]["level-start"] = render_static("level-start", "level-start-static.png")

# Fail closed if this receipt stops exercising the exact snapshot contracts.
assert len(roots) == 12 and roots == expected_roots
assert game_checks["valid_layer_identity"] is True
assert all(game_checks[name]["rejected"] is True for name in cases)
assert inventory["gameplay_compiler_prototype"]["screen_cells"] == 960
assert len(border_cells) == 92 and composite == source
assert inventory["instruction_row_wait"]["current_equals_after_removing_explicit_90_gates"] is True
assert base_schedule["next_screen_tick"] == no_gate_schedule["next_screen_tick"] == 1896
assert no_row_offsets["events"] != base_schedule["events"]
(OUT / "snapshot.json").write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"receipt": "snapshot.json", "static_screens": inventory["static_screens"],
                  "life_grid": inventory["life_grid"],
                  "gameplay_border_composition": inventory["gameplay_border_composition"],
                  "instruction_row_wait": inventory["instruction_row_wait"]}, indent=2))
