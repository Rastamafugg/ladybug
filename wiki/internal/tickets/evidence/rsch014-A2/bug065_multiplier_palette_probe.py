import hashlib
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "scripts"))
import build_presentation as p
import build_screen as s

path = ROOT / "tiled/coco-instructions-screen.tmx"
raw_map = path.read_bytes()
root = ET.parse(path).getroot()
layer = next(l for l in root.findall("layer") if l.get("name") == "CoCo Side HUD")
records = p.layer_records(layer)
cells = []
for x, expected in zip(range(1, 7), (86, 2, 86, 3, 86, 5)):
    gid = records[(x, 7)]
    code = p.raw_char_code(root, path, gid)
    assert code == expected, (x, gid, code, expected)
    current = p.presentation_pen_map("instructions", x, 7, "CoCo Side HUD", code)
    assert current == (p.BLACK, p.GREY, p.GREY, p.GREY), (x, current)
    cells.append({"x": x, "y": 7, "gid": gid, "raw_code": code,
                  "current_pen": current, "candidate_pen": (p.BLACK, p.BLUE, p.BLUE, p.BLUE)})

old = p.presentation_pen_map
def candidate(role, x, y, source_layer="", raw_code=-1, highscore_test_profile=False):
    if role == "instructions" and source_layer == "CoCo Side HUD" and y == 7 and 1 <= x <= 6:
        return (p.BLACK, p.BLUE, p.BLUE, p.BLUE)
    return old(role, x, y, source_layer, raw_code, highscore_test_profile)

chars = s.load_chars(ROOT / "assets/arcade/chars.json")
def render(palette):
    p.presentation_pen_map = palette
    tiles, ids = [], {}
    mapping, _ = p.compile_map(path, chars, tiles, ids, False, True)
    return bytes(p.title_framebuffer(mapping, tiles))
try:
    before = render(old)
    after = render(candidate)
finally:
    p.presentation_pen_map = old
changed = [i for i, (a, b) in enumerate(zip(before, after)) if a != b]
allowed = set()
for cell in cells:
    x, y = cell["x"], cell["y"]
    for py in range(y * 8, (y + 1) * 8):
        start = py * 160 + x * 4
        allowed.update(range(start, start + 4))
assert changed and set(changed) <= allowed
digits = {}
for value in (2, 3, 5):
    rotated = p.rotate_ccw(chars[value])
    white = p.pack_tile(p.recolor(rotated, (p.BLACK, p.WHITE, p.WHITE, p.WHITE)))
    blue = p.pack_tile(p.recolor(rotated, (p.BLACK, p.BLUE, p.BLUE, p.BLUE)))
    assert white != blue
    digits[str(value)] = {"current_nonzero_pen": p.WHITE, "candidate_nonzero_pen": p.BLUE}
audit = {
    "source_revision": "436478586482afb0457357b4fddbbf05a7b9c52a",
    "map_sha256": hashlib.sha256(raw_map).hexdigest(),
    "template_layer": "CoCo Side HUD",
    "template_cells": cells,
    "template_current_common_pen": p.GREY,
    "template_candidate_common_pen": p.BLUE,
    "generated_runtime_digits": digits,
    "generated_destinations": [[27, 17], [27, 20]],
    "changed_packed_frame_bytes": len(changed),
    "changed_bytes_confined_to_template_multiplier_cells": set(changed) <= allowed,
    "template_tmx_changed": False,
    "runtime_or_full_build_claimed": False,
}
(OUT / "bug065-multiplier-palette-contract.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"map_sha256": audit["map_sha256"], "template_cells": cells,
                  "generated_runtime_digits": digits,
                  "changed_packed_frame_bytes": len(changed),
                  "template_tmx_changed": False, "runtime_or_full_build_claimed": False}, indent=2))
