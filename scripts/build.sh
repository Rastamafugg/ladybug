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
MAZE_INC="$BUILD_DIR/ladybug_maze.inc"
ROM="$BUILD_DIR/ladybug.rom"
RUNTIME_ROM="$BUILD_DIR/ladybug-runtime.rom"
BOOT_ROM="$BUILD_DIR/ladybug-gmc-boot.rom"
BOOT_SRC="$ROOT/src/gmc_bootstrap.s"
BOOT_LST="$BUILD_DIR/ladybug-gmc-boot.lst"
BOOT_MAP="$BUILD_DIR/ladybug-gmc-boot.map"
ENEMY_SRC="$ROOT/src/enemy_runtime.s"
ENEMY_ROM="$BUILD_DIR/ladybug-enemy-runtime.rom"
ENEMY_LST="$BUILD_DIR/ladybug-enemy-runtime.lst"
ENEMY_MAP="$BUILD_DIR/ladybug-enemy-runtime.map"
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

cmd_build() {
    [[ -f "$SRC_MAIN" ]] || { echo "build: $SRC_MAIN not found" >&2; exit 1; }
    mkdir -p "$BUILD_DIR"

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
        --resident-output "$RESIDENT_INC"

    lwasm -9 --format=raw \
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
    'blit_packed_sprite', 'draw_hud', 'enemy_sprites', 'restore_player',
    'player_sprites', 'restore_entity_footprint', 'sprite_attr0_pairs',
    'vegetable_sprites',
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

    lwasm -9 --format=raw \
          --output="$ENEMY_ROM" \
          --list="$ENEMY_LST" \
          --symbols \
          --map="$ENEMY_MAP" \
          -I "$BUILD_DIR" \
          "$ENEMY_SRC"

    lwasm -9 --format=raw \
          --output="$BOOT_ROM" \
          --list="$BOOT_LST" \
          --symbols \
          --map="$BOOT_MAP" \
          "$BOOT_SRC"
    pad_cart "$BOOT_ROM"

    python3 - "$BOOT_ROM" "$RUNTIME_ROM" "$ENEMY_ROM" "$ROM" "$GMC_BYTES" <<'PY'
import sys
boot_path, runtime_path, enemy_path, output_path, target = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], int(sys.argv[5])
boot = open(boot_path, 'rb').read()
runtime = open(runtime_path, 'rb').read()
enemy = open(enemy_path, 'rb').read()
if len(boot) != 0x4000 or len(runtime) != 0x4000:
    raise SystemExit('build: GMC bank input is not exactly 16 KiB')
if len(enemy) > 0x800:
    raise SystemExit(f'build: bank-3 enemy module is {len(enemy)} bytes; limit is 2048')
bank2 = bytearray([0xA2] * 0x4000)
bank3 = bytearray([0xA3] * 0x4000)
bank2[0x10:0x12] = bytes((0xB2, 0x02))
bank3[0x10:0x12] = bytes((0xB3, 0x03))
bank3[0x800:0x800 + len(enemy)] = enemy
image = boot + runtime + bank2 + bank3
if len(image) != target:
    raise SystemExit(f'build: GMC image is {len(image)} bytes, expected {target}')
open(output_path, 'wb').write(image)
print(f'build: GMC banks 4 x 16384 -> {len(image)} bytes ({output_path})')
PY
}

cmd_run() {
    cmd_build
    exec xroar \
        -machine coco3 \
        -ram 512 \
        -cart-type gmc \
        -cart-rom "$ROM" \
        -cart-autorun \
        -tv-input rgb \
        -joy-right kjoy0 \
        ${XROAR_EXTRA:-}
}

cmd_verify_gmc() {
    cmd_build
    python3 "$ROOT/scripts/verify_gmc_boot.py" --rom "$ROM" --map "$MAP"
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
