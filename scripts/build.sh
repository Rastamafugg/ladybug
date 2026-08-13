#!/usr/bin/env bash
# Ladybug build / run / clean, plus emulator-monitor tester ROM target.
# See wiki/internal/tooling/build-workflow.html for the full runbook.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_MAIN="$ROOT/src/main.s"
SRC_TESTER="$ROOT/src/tester/tester.s"
BUILD_DIR="$ROOT/build"
SCREEN_INC="$BUILD_DIR/ladybug_screen.inc"
RESIDENT_INC="$BUILD_DIR/ladybug_resident.inc"
SPARSE_ENEMY="$BUILD_DIR/ladybug-enemy-sparse.bin"
SPARSE_PLAYER="$BUILD_DIR/ladybug-player-sparse.bin"
GATE_TRANSITIONS="$BUILD_DIR/ladybug-gate-transitions.bin"
PRESENTATION_SPARSE="$BUILD_DIR/ladybug-presentation-sparse.bin"
PRESENTATION_COLD="$BUILD_DIR/ladybug-presentation-cold.bin"
PRESENTATION_ACTOR_RECORDS="$BUILD_DIR/ladybug-attract-actor-records.bin"
PRESENTATION_ACTOR_UNDERLAYS="$BUILD_DIR/ladybug-attract-actor-underlays.bin"
PRESENTATION_INC="$BUILD_DIR/ladybug_presentation.inc"
PRESENTATION_MANIFEST="$BUILD_DIR/ladybug-presentation.json"
PRESENTATION_MODULE="$BUILD_DIR/ladybug-presentation-runtime.bin"
PRESENTATION_MODULE_SRC="$ROOT/src/presentation_runtime.s"
PRESENTATION_MODULE_LST="$BUILD_DIR/ladybug-presentation-runtime.lst"
PRESENTATION_MODULE_MAP="$BUILD_DIR/ladybug-presentation-runtime.map"
PRESENTATION_SYMBOLS="$BUILD_DIR/ladybug_presentation_symbols.inc"
INSTRUCTION_RUNTIME="$BUILD_DIR/ladybug-instruction-runtime.bin"
INSTRUCTION_RUNTIME_SRC="$ROOT/src/instruction_runtime.s"
INSTRUCTION_RUNTIME_LST="$BUILD_DIR/ladybug-instruction-runtime.lst"
INSTRUCTION_RUNTIME_MAP="$BUILD_DIR/ladybug-instruction-runtime.map"
SPARSE_BANK2="$BUILD_DIR/ladybug-sparse-bank2.bin"
SPARSE_BANK3="$BUILD_DIR/ladybug-sparse-bank3.bin"
SPARSE_BANK0="$BUILD_DIR/ladybug-gmc-bank0-overflow.bin"
SPARSE_LOADER="$BUILD_DIR/ladybug-sparse-loader.inc"
SPARSE_MANIFEST="$BUILD_DIR/ladybug-sparse-layout.json"
PERIMETER_RESET="$BUILD_DIR/ladybug-perimeter-reset.bin"
PERIMETER_HELPER="$BUILD_DIR/ladybug-perimeter-reset-helper.bin"
PERIMETER_HELPER_LST="$BUILD_DIR/ladybug-perimeter-reset-helper.lst"
PERIMETER_HELPER_MAP="$BUILD_DIR/ladybug-perimeter-reset-helper.map"
MAZE_INC="$BUILD_DIR/ladybug_maze.inc"
ROM="$BUILD_DIR/ladybug.rom"
RUNTIME_ROM="$BUILD_DIR/ladybug-runtime.rom"
BOOT_ROM="$BUILD_DIR/ladybug-gmc-boot.rom"
BOOT_SRC="$ROOT/src/gmc_bootstrap.s"
PERIMETER_BOOT_INC="$BUILD_DIR/ladybug-perimeter-boot.inc"
BOOT_LST="$BUILD_DIR/ladybug-gmc-boot.lst"
BOOT_MAP="$BUILD_DIR/ladybug-gmc-boot.map"
ENEMY_SRC="$ROOT/src/enemy_runtime.s"
ENEMY_ROM="$BUILD_DIR/ladybug-enemy-runtime.rom"
ENEMY_LST="$BUILD_DIR/ladybug-enemy-runtime.lst"
ENEMY_MAP="$BUILD_DIR/ladybug-enemy-runtime.map"
PERIMETER_HELPER_SRC="$ROOT/src/perimeter_reset_helper.s"
RUNTIME_SYMBOLS="$BUILD_DIR/ladybug_runtime_symbols.inc"
LST="$BUILD_DIR/ladybug.lst"
MAP="$BUILD_DIR/ladybug.map"
TESTER_ROM="$BUILD_DIR/tester.rom"
TESTER_LST="$BUILD_DIR/tester.lst"
TESTER_MAP="$BUILD_DIR/tester.map"
CART_BYTES=16384
GMC_BYTES=65536
RESIDENT_LIMIT=0xE000
ASSET_LIMIT=0xFE00
BOOT_OVERFLOW_START=0xC800
PRESENTATION_MODULE_START=0x1900
PRESENTATION_MODULE_LIMIT=0x1E00
PRESENTATION_HELPER_START=0x06B2
PRESENTATION_HELPER_LIMIT=0x0800
INSTRUCTION_RUNTIME_START=0x0300
INSTRUCTION_RUNTIME_LIMIT=0x06AA
LADYBUG_PROFILE="${LADYBUG_PROFILE:-development}"
case "$LADYBUG_PROFILE" in
    development) BUG011_DEVELOPMENT_PROFILE=1 ;;
    release) BUG011_DEVELOPMENT_PROFILE=0 ;;
    *) echo "build: LADYBUG_PROFILE must be development or release" >&2; exit 2 ;;
esac

guard_layout() {
    local map="$1"
    local rom="$2"
    python3 - "$map" "$rom" "$RESIDENT_LIMIT" "$ASSET_LIMIT" <<'PY'
import re
import sys

map_path, rom_path = sys.argv[1], sys.argv[2]
resident_limit, asset_limit = int(sys.argv[3], 0), int(sys.argv[4], 0)
symbols = {}
pattern = re.compile(r"^Symbol: (resident_end|asset_start|asset_end) .* = ([0-9A-Fa-f]+)$")
with open(map_path, encoding="utf-8") as handle:
    for line in handle:
        match = pattern.match(line.rstrip())
        if match:
            symbols[match.group(1)] = int(match.group(2), 16)

missing = {"resident_end", "asset_start", "asset_end"} - symbols.keys()
if missing:
    sys.exit(f"build: layout map is missing {', '.join(sorted(missing))}")
if symbols["resident_end"] > resident_limit:
    sys.exit(
        f"build: resident region ends at ${symbols['resident_end']:04X}; "
        f"limit is ${resident_limit:04X}"
    )
if symbols["asset_start"] != resident_limit:
    sys.exit(
        f"build: asset region starts at ${symbols['asset_start']:04X}; "
        f"expected ${resident_limit:04X}"
    )
if symbols["asset_end"] > asset_limit:
    sys.exit(
        f"build: asset region ends at ${symbols['asset_end']:04X}; "
        f"limit is ${asset_limit:04X}"
    )

raw_size = len(open(rom_path, "rb").read())
expected_size = symbols["asset_end"] - 0xC000
if raw_size != expected_size:
    sys.exit(
        f"build: raw ROM is {raw_size} bytes; layout requires {expected_size}"
    )

resident_used = symbols["resident_end"] - 0xC000
asset_used = symbols["asset_end"] - symbols["asset_start"]
print(
    f"build: resident {resident_used}/{resident_limit - 0xC000} bytes; "
    f"assets {asset_used}/{asset_limit - resident_limit} bytes"
)
PY
}

pad_cart() {
    local rom="$1"
    python3 - "$rom" "$CART_BYTES" <<'PY'
import sys
path, target = sys.argv[1], int(sys.argv[2])
data = open(path, 'rb').read()
pad = target - len(data)
if pad < 0:
    sys.exit(f"build: ROM is {len(data)} bytes — exceeds {target} byte cart window")
open(path, 'wb').write(data + b'\xff' * pad)
print(f"build: padded {len(data)} → {target} bytes ({path})")
PY
}

guard_boot_overflow() {
    local map="$1"
    python3 - "$map" "$BOOT_OVERFLOW_START" <<'PY'
import re
import sys
path, limit = sys.argv[1], int(sys.argv[2], 0)
text = open(path, encoding="utf-8").read()
match = re.search(r"^Symbol: loader_end .* = ([0-9A-Fa-f]+)$", text, re.MULTILINE)
if not match:
    raise SystemExit("build: boot map is missing loader_end")
end = int(match.group(1), 16)
if end > limit:
    raise SystemExit(
        f"build: loader ends at ${end:04X}; bank-0 overflow starts at ${limit:04X}"
    )
print(f"build: boot loader ends at ${end:04X}; overflow starts at ${limit:04X}")
PY
}

guard_presentation_module() {
    local module="$1"
    python3 - "$module" "$PRESENTATION_MODULE_START" "$PRESENTATION_MODULE_LIMIT" <<'PY'
import sys
path, start, limit = sys.argv[1], int(sys.argv[2], 0), int(sys.argv[3], 0)
size = len(open(path, 'rb').read())
if start + size > limit:
    raise SystemExit(
        f"build: presentation module ends at ${start + size:04X}; "
        f"limit is ${limit:04X}"
    )
print(f"build: presentation module {size}/{limit - start} bytes")
PY
}

guard_presentation_helper() {
    local helper="$1"
    python3 - "$helper" "$PRESENTATION_HELPER_START" "$PRESENTATION_HELPER_LIMIT" <<'PY'
import sys
path, start, limit = sys.argv[1], int(sys.argv[2], 0), int(sys.argv[3], 0)
size = len(open(path, 'rb').read())
if start + size > limit:
    raise SystemExit(
        f"build: presentation helper ends at ${start + size:04X}; "
        f"limit is ${limit:04X}"
    )
print(f"build: presentation helper {size}/{limit - start} bytes")
PY
}

guard_instruction_runtime() {
    local helper="$1"
    python3 - "$helper" "$INSTRUCTION_RUNTIME_START" "$INSTRUCTION_RUNTIME_LIMIT" <<'PY'
import sys
path, start, limit = sys.argv[1], int(sys.argv[2], 0), int(sys.argv[3], 0)
size = len(open(path, 'rb').read())
if start + size > limit:
    raise SystemExit(
        f"build: instruction runtime ends at ${start + size:04X}; "
        f"limit is ${limit:04X}"
    )
print(f"build: instruction runtime {size}/{limit - start} bytes")
PY
}

cmd_build() {
    [[ -f "$SRC_MAIN" ]] || { echo "build: $SRC_MAIN not found" >&2; exit 1; }
    mkdir -p "$BUILD_DIR"

    echo "build: profile $LADYBUG_PROFILE"

    python3 "$ROOT/scripts/derive_maze.py" \
        --capture "$ROOT/assets/arcade/maze_capture.json" \
        --raw "$ROOT/assets/arcade/maze_capture.bin" \
        --output "$ROOT/assets/arcade/maze.json" \
        --include "$MAZE_INC"

    python3 "$ROOT/scripts/build_screen.py" \
        --map "$ROOT/tiled/coco-screen.tmx" \
        --maze "$ROOT/assets/arcade/maze.json" \
        --chars "$ROOT/assets/arcade/chars.json" \
        --sprites "$ROOT/assets/arcade/sprites.json" \
        --output "$SCREEN_INC" \
        --resident-output "$RESIDENT_INC" \
        --gate-output "$GATE_TRANSITIONS" \
        --presentation-output "$PRESENTATION_SPARSE"

    python3 "$ROOT/scripts/build_presentation.py" \
        --tiled-dir "$ROOT/tiled" \
        --chars "$ROOT/assets/arcade/chars.json" \
        --gameplay-map "$ROOT/tiled/coco-screen.tmx" \
        --gameplay-maze "$ROOT/assets/arcade/maze.json" \
        --gameplay-chars "$ROOT/assets/arcade/chars.json" \
        --gameplay-sprites "$ROOT/assets/arcade/sprites.json" \
        --output "$PRESENTATION_COLD" \
        --include-output "$PRESENTATION_INC" \
        --manifest-output "$PRESENTATION_MANIFEST" \
        --actor-record-output "$PRESENTATION_ACTOR_RECORDS" \
        --actor-underlay-output "$PRESENTATION_ACTOR_UNDERLAYS"

    python3 "$ROOT/scripts/verify_presentation.py" \
        --tiled-dir "$ROOT/tiled" \
        --chars "$ROOT/assets/arcade/chars.json" \
        --gameplay-map "$ROOT/tiled/coco-screen.tmx" \
        --gameplay-maze "$ROOT/assets/arcade/maze.json" \
        --gameplay-chars "$ROOT/assets/arcade/chars.json" \
        --gameplay-sprites "$ROOT/assets/arcade/sprites.json" \
        --payload "$PRESENTATION_COLD" \
        --manifest "$PRESENTATION_MANIFEST"

    lwasm -9 --format=raw \
          -DBUG011_DEVELOPMENT_PROFILE="$BUG011_DEVELOPMENT_PROFILE" \
          --output="$RUNTIME_ROM" \
          --list="$LST" \
          --symbols \
          --map="$MAP" \
          -I "$BUILD_DIR" \
          "$SRC_MAIN"

    guard_layout "$MAP" "$RUNTIME_ROM"
    pad_cart "$RUNTIME_ROM"

    python3 - "$MAP" "$RUNTIME_SYMBOLS" <<'PY'
import re
import sys
source, output = sys.argv[1:]
wanted = {
    'blit_packed_sprite', 'draw_hud', 'restore_player',
    'draw_death_frame', 'draw_entities', 'draw_lives', 'draw_maze_state_cell',
    'draw_multiplier_hud', 'draw_perimeter_box', 'draw_player',
    'draw_recolored_map_tile', 'draw_score_popup', 'draw_screen',
    'erase_entity_footprints', 'perimeter_box_coordinates', 'save_player',
    'draw_gate', 'draw_gate_diagonal', 'draw_gate_entities',
    'draw_gate_transition', 'draw_all_gates', 'framebuffer_project_gate_only',
    'mark_gate_enemy_overlap',
    'draw_word_progress_hud', 'gate_redraw_neighbors',
    'gate_render_hidden', 'maze_gate_owner',
    'maze_gates', 'maze_nav',
    'restore_entity_footprint', 'sprite_attr0_pairs',
    'reload_enemy_box_timer', 'reset_enemy_state',
    'restore_gate_diagonal_dots', 'vegetable_sprites',
}
symbols = {}
for line in open(source, encoding='utf-8'):
    match = re.match(r'^Symbol: (\w+) .* = ([0-9A-Fa-f]+)$', line.rstrip())
    if match and match.group(1) in wanted:
        symbols[match.group(1)] = match.group(2)
missing = wanted - symbols.keys()
if missing:
    raise SystemExit('build: enemy module symbols missing: ' + ', '.join(sorted(missing)))
with open(output, 'w', encoding='ascii') as handle:
    for name in sorted(symbols):
        handle.write(f'{name} equ ${symbols[name]}\n')
PY

    python3 - "$MAP" "$PRESENTATION_SYMBOLS" <<'PY'
import re
import sys
source, output = sys.argv[1:]
wanted = {
    'init_game_state': 'PRES_MAIN_INIT',
    'init_maze_state': 'PRES_MAIN_MAZE',
    'init_gate_state': 'PRES_MAIN_GATES',
    'init_entities': 'PRES_MAIN_ENTITIES',
    'init_player': 'PRES_MAIN_PLAYER',
    'init_enemy': 'PRES_MAIN_ENEMY',
    'read_joystick': 'PRES_MAIN_READ_JOY',
    'player_tick': 'PRES_MAIN_PLAYER_TICK',
    'enemy_tick': 'PRES_MAIN_ENEMY_TICK',
    'death_tick': 'PRES_MAIN_DEATH',
    'render_frame': 'PRES_MAIN_RENDER',
    'next_stage': 'PRES_MAIN_NEXT_STAGE',
    'save_player': 'PRES_MAIN_SAVE_PLAYER',
    'restore_player': 'PRES_MAIN_RESTORE_PLAYER',
    'blit_tile': 'PRES_MAIN_BLIT_TILE',
}
symbols = {}
for line in open(source, encoding='utf-8'):
    match = re.match(r'^Symbol: (\w+) .* = ([0-9A-Fa-f]+)$', line.rstrip())
    if match and match.group(1) in wanted:
        symbols[wanted[match.group(1)]] = match.group(2)
missing = set(wanted.values()) - symbols.keys()
if missing:
    raise SystemExit('build: presentation symbols missing: ' + ', '.join(sorted(missing)))
with open(output, 'w', encoding='ascii') as handle:
    for name in sorted(symbols):
        handle.write(f'{name} equ ${symbols[name]}\n')
PY

    lwasm -9 --format=raw \
          --output="$ENEMY_ROM" \
          --list="$ENEMY_LST" \
          --symbols \
          --map="$ENEMY_MAP" \
          -I "$BUILD_DIR" \
          "$ENEMY_SRC"

    python3 - "$ENEMY_MAP" "$PRESENTATION_SYMBOLS" <<'PY'
import re
import sys
source, output = sys.argv[1:]
wanted = {
    'framebuffer_prepare_back': 'PRES_MAIN_FB_PREPARE',
    'framebuffer_finish_back': 'PRES_MAIN_FB_FINISH',
    'framebuffer_capture_back': 'PRES_MAIN_FB_CAPTURE',
}
symbols = {}
for line in open(source, encoding='utf-8'):
    match = re.match(r'^Symbol: (\w+) .* = ([0-9A-Fa-f]+)$', line.rstrip())
    if match and match.group(1) in wanted:
        symbols[wanted[match.group(1)]] = match.group(2)
missing = set(wanted.values()) - symbols.keys()
if missing:
    raise SystemExit('build: enemy framebuffer symbols missing: ' + ', '.join(sorted(missing)))
with open(output, 'a', encoding='ascii') as handle:
    for name in sorted(symbols):
        handle.write(f'{name} equ ${symbols[name]}\n')
PY

    lwasm -9 --format=raw \
          -DBUG011_DEVELOPMENT_PROFILE="$BUG011_DEVELOPMENT_PROFILE" \
          --output="$PRESENTATION_MODULE" \
          --list="$PRESENTATION_MODULE_LST" \
          --symbols \
          --map="$PRESENTATION_MODULE_MAP" \
          -I "$BUILD_DIR" \
          "$PRESENTATION_MODULE_SRC"
    guard_presentation_module "$PRESENTATION_MODULE"

    python3 - "$PRESENTATION_MODULE_MAP" "$PRESENTATION_SYMBOLS" <<'PY'
import re
import sys
source, output = sys.argv[1:]
symbols = {}
wanted = {
    'draw_actor_overlay': 'PRES_MODULE_DRAW_ACTOR',
    'map_back': 'PRES_MODULE_MAP_BACK',
    'draw_tile_id': 'PRES_MODULE_DRAW_TILE',
    'cold_ptr': 'PRES_MODULE_COLD_PTR',
    'colour_tile': 'PRES_MODULE_COLOUR_TILE',
    'colour_surface': 'PRES_MODULE_COLOUR_SURFACE',
}
for line in open(source, encoding='utf-8'):
    match = re.match(r'^Symbol: (\w+) .* = ([0-9A-Fa-f]+)$', line.rstrip())
    if match and match.group(1) in wanted:
        symbols[wanted[match.group(1)]] = match.group(2)
required = {
    'PRES_MODULE_DRAW_ACTOR', 'PRES_MODULE_MAP_BACK',
    'PRES_MODULE_DRAW_TILE', 'PRES_MODULE_COLD_PTR',
    'PRES_MODULE_COLOUR_TILE', 'PRES_MODULE_COLOUR_SURFACE',
}
if set(symbols) != required:
    raise SystemExit('build: presentation module symbols missing: ' + ', '.join(sorted(required - set(symbols))))
with open(output, 'a', encoding='ascii') as handle:
    for name, value in symbols.items():
        handle.write(f'{name} equ ${value}\n')
PY

    lwasm -9 --format=raw \
          --output="$INSTRUCTION_RUNTIME" \
          --list="$INSTRUCTION_RUNTIME_LST" \
          --symbols \
          --map="$INSTRUCTION_RUNTIME_MAP" \
          -I "$BUILD_DIR" \
          "$INSTRUCTION_RUNTIME_SRC"
    guard_instruction_runtime "$INSTRUCTION_RUNTIME"

    lwasm -9 --format=raw \
          --output="$PERIMETER_HELPER" \
          --list="$PERIMETER_HELPER_LST" \
          --symbols \
          --map="$PERIMETER_HELPER_MAP" \
          -I "$BUILD_DIR" \
          "$PERIMETER_HELPER_SRC"
    guard_presentation_helper "$PERIMETER_HELPER"

    python3 "$ROOT/scripts/build_sparse_sprites.py" \
        --sprites "$ROOT/assets/arcade/sprites.json" \
        --enemy-runtime "$ENEMY_ROM" \
        --enemy-output "$SPARSE_ENEMY" \
        --player-output "$SPARSE_PLAYER" \
        --gate-input "$GATE_TRANSITIONS" \
        --presentation-input "$PRESENTATION_SPARSE" \
        --perimeter-map "$ROOT/tiled/coco-screen.tmx" \
        --perimeter-maze "$ROOT/assets/arcade/maze.json" \
        --perimeter-chars "$ROOT/assets/arcade/chars.json" \
        --perimeter-reset-output "$PERIMETER_RESET" \
        --perimeter-helper "$PERIMETER_HELPER" \
        --presentation-cold "$PRESENTATION_COLD" \
        --actor-records "$PRESENTATION_ACTOR_RECORDS" \
        --actor-underlays "$PRESENTATION_ACTOR_UNDERLAYS" \
        --presentation-module "$PRESENTATION_MODULE" \
        --instruction-runtime "$INSTRUCTION_RUNTIME" \
        --bank0-output "$SPARSE_BANK0" \
        --bank2-output "$SPARSE_BANK2" \
        --bank3-output "$SPARSE_BANK3" \
        --loader-output "$SPARSE_LOADER" \
        --manifest-output "$SPARSE_MANIFEST"

    python3 "$ROOT/scripts/verify_sparse_sprites.py" \
        --sprites "$ROOT/assets/arcade/sprites.json" \
        --enemy-runtime "$ENEMY_ROM" \
        --enemy-payload "$SPARSE_ENEMY" \
        --player-payload "$SPARSE_PLAYER" \
        --gate-payload "$GATE_TRANSITIONS" \
        --presentation-payload "$PRESENTATION_SPARSE" \
        --perimeter-reset-payload "$PERIMETER_RESET" \
        --perimeter-helper "$PERIMETER_HELPER" \
        --presentation-cold "$PRESENTATION_COLD" \
        --actor-records "$PRESENTATION_ACTOR_RECORDS" \
        --actor-underlays "$PRESENTATION_ACTOR_UNDERLAYS" \
        --presentation-module "$PRESENTATION_MODULE" \
        --instruction-runtime "$INSTRUCTION_RUNTIME" \
        --bank0 "$SPARSE_BANK0" \
        --bank2 "$SPARSE_BANK2" \
        --bank3 "$SPARSE_BANK3" \
        --loader "$SPARSE_LOADER" \
        --manifest "$SPARSE_MANIFEST"

    python3 "$ROOT/scripts/verify_gmc_overflow.py"

    python3 "$ROOT/scripts/verify_presentation_sparse.py"

    python3 - "$MAP" "$PERIMETER_BOOT_INC" <<'PY'
import re
import sys

source, output = sys.argv[1:]
symbols = {}
for line in open(source, encoding="utf-8"):
    match = re.match(r"^Symbol: (screen_map|screen_tiles) .* = ([0-9A-Fa-f]+)$", line.rstrip())
    if match:
        symbols[match.group(1)] = int(match.group(2), 16)
if set(symbols) != {"screen_map", "screen_tiles"}:
    raise SystemExit("build: runtime map is missing authored screen assets")
if not (0xE000 <= symbols["screen_map"] < symbols["screen_tiles"] < 0xFE00):
    raise SystemExit("build: authored screen assets are outside the PAR7 source window")
with open(output, "w", encoding="ascii") as handle:
    handle.write("; Generated from the current authored screen asset map.\n")
    handle.write(f"PERIMETER_SCREEN_MAP equ ${symbols['screen_map']:04X}\n")
    handle.write(f"PERIMETER_SCREEN_TILES equ ${symbols['screen_tiles']:04X}\n")
PY

    local boot_rom_tmp="${BOOT_ROM}.tmp"
    local boot_lst_tmp="${BOOT_LST}.tmp"
    local boot_map_tmp="${BOOT_MAP}.tmp"
    lwasm -9 --format=raw \
          --output="$boot_rom_tmp" \
          --list="$boot_lst_tmp" \
          --symbols \
          --map="$boot_map_tmp" \
          -I "$BUILD_DIR" \
          "$BOOT_SRC"
    python3 - "$boot_rom_tmp" "$BOOT_ROM" "$boot_lst_tmp" "$BOOT_LST" "$boot_map_tmp" "$BOOT_MAP" <<'PY'
import os
import sys
for source, destination in zip(sys.argv[1::2], sys.argv[2::2]):
    os.replace(source, destination)
PY
    guard_boot_overflow "$BOOT_MAP"
    python3 "$ROOT/scripts/verify_perimeter_allocation.py" \
        --manifest "$SPARSE_MANIFEST" \
        --bootstrap "$BOOT_SRC" \
        --helper "$PERIMETER_HELPER"
    pad_cart "$BOOT_ROM"

    python3 - "$BOOT_ROM" "$SPARSE_BANK0" "$RUNTIME_ROM" "$ENEMY_ROM" "$SPARSE_BANK2" "$SPARSE_BANK3" "$SPARSE_MANIFEST" "$ROM" "$GMC_BYTES" <<'PY'
import hashlib
import json
import os
import sys
boot_path, bank0_path, runtime_path, enemy_path, bank2_path, bank3_path, manifest_path, output_path, target = sys.argv[1:9] + [int(sys.argv[9])]
with open(boot_path, 'rb') as stream:
    boot = bytearray(stream.read())
with open(bank0_path, 'rb') as stream:
    bank0 = stream.read()
with open(runtime_path, 'rb') as stream:
    runtime = stream.read()
with open(enemy_path, 'rb') as stream:
    enemy = stream.read()
with open(bank2_path, 'rb') as stream:
    bank2 = stream.read()
with open(bank3_path, 'rb') as stream:
    bank3 = stream.read()
with open(manifest_path, encoding='ascii') as stream:
    manifest = json.load(stream)
if any(len(bank) != 0x4000 for bank in (boot, bank0, runtime, bank2, bank3)):
    raise SystemExit('build: GMC bank input is not exactly 16 KiB')
if len(enemy) > 0x1000:
    raise SystemExit(f'build: bank-3 enemy module is {len(enemy)} bytes; limit is 4096')
if bank3[0x800:0x800 + len(enemy)] != enemy:
    raise SystemExit('build: sparse bank-3 runtime payload differs from assembled module')
for segment in manifest['gmc']['segments']:
    if segment['bank'] != 0:
        continue
    start = segment['source_offset']
    end = start + segment['count']
    if start < 0x0800 or end > 0x3E00:
        raise SystemExit('build: bank-0 overflow segment is outside $0800-$3DFF')
    if any(value != 0xFF for value in boot[start:end]):
        raise SystemExit('build: bank-0 overflow segment overlaps assembled boot bytes')
    boot[start:end] = bank0[start:end]
with open(boot_path, 'wb') as stream:
    stream.write(boot)
image = bytes(boot) + runtime + bank2 + bank3
if len(image) != target:
    raise SystemExit(f'build: GMC image is {len(image)} bytes, expected {target}')
with open(output_path, 'wb') as stream:
    stream.write(image)
digest = lambda data: hashlib.sha256(data).hexdigest()
manifest['gmc']['final_bank0_sha256'] = digest(bytes(boot))
manifest['gmc']['bank1_sha256'] = digest(runtime)
manifest['gmc']['final_image_sha256'] = digest(image)
manifest_temp_path = manifest_path + '.tmp'
with open(manifest_temp_path, 'w', encoding='ascii') as stream:
    stream.write(json.dumps(manifest, indent=2) + '\n')
os.replace(manifest_temp_path, manifest_path)
print(f'build: GMC banks 4 x 16384 -> {len(image)} bytes ({output_path})')
PY
}

cmd_run() {
    cmd_build
    exec xroar \
        -machine coco3 \
        -ram 512 \
        -ram-init random \
        -cart-type gmc \
        -cart-rom "$ROM" \
        -cart-autorun \
        -tv-input rgb \
        -joy-right kjoy0 \
        ${XROAR_EXTRA:-}
}

cmd_verify_gmc() {
    cmd_build
    python3 "$ROOT/scripts/verify_presentation_flow.py"
    python3 "$ROOT/scripts/verify_gmc_boot.py" --rom "$ROM" --map "$MAP" --manifest "$SPARSE_MANIFEST"
    python3 "$ROOT/scripts/verify_enemy_runtime.py"
}

cmd_tester() {
    [[ -f "$SRC_TESTER" ]] || { echo "tester: $SRC_TESTER not found" >&2; exit 1; }
    mkdir -p "$BUILD_DIR"

    lwasm -9 --format=raw \
          --output="$TESTER_ROM" \
          --list="$TESTER_LST" \
          --symbols \
          --map="$TESTER_MAP" \
          -I "$ROOT/src/tester" \
          "$SRC_TESTER"

    pad_cart "$TESTER_ROM"
}

cmd_tester_run() {
    cmd_tester
    exec xroar \
        -machine coco3 \
        -ram 512 \
        -cart ladybug \
        -cart-type rom \
        -cart-rom "$TESTER_ROM" \
        -cart-autorun \
        -tv-input rgb \
        ${XROAR_EXTRA:-}
}

cmd_clean() {
    rm -rf "$BUILD_DIR"
    echo "clean: removed $BUILD_DIR"
}

case "${1:-build}" in
    build)       cmd_build ;;
    verify-gmc)  cmd_verify_gmc ;;
    run)         cmd_run ;;
    tester)      cmd_tester ;;
    tester-run)  cmd_tester_run ;;
    clean)       cmd_clean ;;
    *)           echo "usage: $0 {build|verify-gmc|run|tester|tester-run|clean}" >&2; exit 2 ;;
esac
