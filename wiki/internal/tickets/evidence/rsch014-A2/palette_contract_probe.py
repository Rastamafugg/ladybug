import hashlib
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'scripts'))
import build_presentation as bp
import build_screen as bs

source_path = ROOT / 'scripts/build_presentation.py'
map_path = ROOT / 'tiled/coco-attract-screen.tmx'
source_bytes = source_path.read_bytes()
map_bytes = map_path.read_bytes()
source = source_bytes.decode('utf-8')
root, flat, layers = bp.flatten_map(map_path)
row = []
for i, gid in enumerate(flat):
    x, y = i % 40, i // 40
    if y != 15 or not (gid & bp.GID_MASK):
        continue
    code = bp.raw_char_code(root, map_path, gid & bp.GID_MASK)
    if 0 <= code <= 35:
        row.append({'x': x, 'code': code, 'char': str(code) if code < 10 else chr(code + 55),
                    'source_layer': layers[i],
                    'current_pens': bp.presentation_pen_map('attract', x, y, layers[i], code)})
by_x = {item['x']: item for item in row}
authored_text = ''.join(by_x[x]['char'] if x in by_x else ' ' for x in range(13, 28))
assert authored_text == 'PRESS 5 OR 6 TO'
assert [v['x'] for v in row] == [13, 14, 15, 16, 17, 19, 21, 22, 24, 26, 27]
assert all(v['source_layer'] == 'Attract Title and Prompts' for v in row)
old = bp.presentation_pen_map

def derived_prompt_map(role, x, y, source_layer='', raw_code=-1, highscore_test_profile=False):
    if (role == 'attract' and y == 15 and source_layer == 'Attract Title and Prompts'
            and 0 <= raw_code <= 35):
        return (bp.BLACK, bp.PURPLE, bp.PURPLE, bp.PURPLE)
    return old(role, x, y, source_layer, raw_code, highscore_test_profile)

def compile_attract(palette_fn):
    bp.presentation_pen_map = palette_fn
    tiles, ids = [], {}
    mapping, _ = bp.compile_map(map_path, bs.load_chars(ROOT / 'assets/arcade/chars.json'), tiles, ids)
    return bytes(bp.title_framebuffer(mapping, tiles)), mapping, tiles

current_frame, current_map, current_tiles = compile_attract(old)
candidate_frame, candidate_map, candidate_tiles = compile_attract(derived_prompt_map)
bp.presentation_pen_map = old
changed = [i for i, (a, b) in enumerate(zip(current_frame, candidate_frame)) if a != b]
allowed_cells = set(row[i]['x'] for i in (0, 1, 9, 10))
allowed_bytes = set()
for y in range(15 * 8, 16 * 8):
    for x in allowed_cells:
        cell_byte = y * 160 + x * 4
        allowed_bytes.update(range(cell_byte, cell_byte + 4))
assert changed and set(changed) <= allowed_bytes
# Confirm all prompt glyph pixels use exactly the documented purple pen.
char_img = bs.load_chars(ROOT / 'assets/arcade/chars.json')
for item in row:
    x, code = item['x'], item['code']
    tile = bp.rotate_ccw(char_img[code])
    pens = {derived_prompt_map('attract', x, 15, item['source_layer'], code)[pen]
            for line in tile for pen in line if pen}
    assert pens == {bp.PURPLE}

def digest(data):
    return hashlib.sha256(data).hexdigest()

def png(frame, path):
    from PIL import Image
    palette = [
        (0, 0, 0), (255, 0, 0), (255, 255, 0), (0, 0, 255),
        (255, 0, 255), (0, 255, 0), (255, 255, 255), (128, 128, 128),
        (144, 238, 144), (160, 32, 240), (0, 100, 0), (135, 206, 250),
        (139, 0, 0), (255, 165, 0), (255, 255, 255), (0, 0, 0),
    ]
    image = Image.new('RGB', (320, 192))
    pix = image.load()
    for cell in range(960):
        cx, cy = cell % 40, cell // 40
        for ty in range(8):
            rowbytes = frame[(cy * 8 + ty) * 160 + cx * 4:(cy * 8 + ty) * 160 + cx * 4 + 4]
            for bi, byte in enumerate(rowbytes):
                pix[cx * 8 + bi * 2, cy * 8 + ty] = palette[byte >> 4]
                pix[cx * 8 + bi * 2 + 1, cy * 8 + ty] = palette[byte & 15]
    image.save(path, optimize=False)

png(candidate_frame, OUT / 'attract-map-derived-purple-candidate.png')
audit = {
    'source_revision': '4364785',
    'source_file_sha256': digest(source_bytes),
    'map_sha256': digest(map_bytes),
    'map_snapshot_unchanged': True,
    'row15_visible_text': authored_text,
    'row15_text_cells': row,
    'candidate_rule': 'Attract Title and Prompts layer, row 15, actual alphanumeric glyph cells only; derive cell extent from authored non-space GIDs; map all glyph pens to pen 9 (PURPLE).',
    'current_pen_by_text_cell': {str(v['x']): bp.presentation_pen_map('attract', v['x'], 15, v['source_layer'], v['code']) for v in row},
    'candidate_pen_by_text_cell': {str(v['x']): [0, 9, 9, 9] for v in row},
    'changed_cell_x': sorted(allowed_cells),
    'changed_packed_frame_bytes': len(changed),
    'changed_bytes_confined_to_four_edge_glyph_cells': set(changed) <= allowed_bytes,
    'middle_glyphs_already_pen9': [v['x'] for v in row if v['x'] not in allowed_cells],
    'candidate_static_frame_sha256': digest(candidate_frame),
    'candidate_png_sha256': digest((OUT / 'attract-map-derived-purple-candidate.png').read_bytes()),
    'runtime_or_full_build_claimed': False,
}
(OUT / 'bug063-palette-contract.json').write_text(json.dumps(audit, indent=2) + '\n', encoding='utf-8')
print(json.dumps({k: audit[k] for k in ('source_revision','map_sha256','row15_visible_text','row15_text_cells','changed_cell_x','changed_packed_frame_bytes','candidate_static_frame_sha256','candidate_png_sha256','runtime_or_full_build_claimed')}, indent=2))
