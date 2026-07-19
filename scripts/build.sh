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
LST="$BUILD_DIR/ladybug.lst"
MAP="$BUILD_DIR/ladybug.map"
TESTER_ROM="$BUILD_DIR/tester.rom"
TESTER_LST="$BUILD_DIR/tester.lst"
TESTER_MAP="$BUILD_DIR/tester.map"
CART_BYTES=16384
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
          --output="$ROM" \
          --list="$LST" \
          --symbols \
          --map="$MAP" \
          -I "$BUILD_DIR" \
          "$SRC_MAIN"

    guard_layout "$MAP" "$ROM"
    pad_cart "$ROM"
}

cmd_run() {
    cmd_build
    exec xroar \
        -machine coco3 \
        -ram 512 \
        -cart ladybug \
        -cart-type rom \
        -cart-rom "$ROM" \
        -cart-autorun \
        -tv-input rgb \
        -joy-right kjoy0 \
        ${XROAR_EXTRA:-}
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
    run)         cmd_run ;;
    tester)      cmd_tester ;;
    tester-run)  cmd_tester_run ;;
    clean)       cmd_clean ;;
    *)           echo "usage: $0 {build|run|tester|tester-run|clean}" >&2; exit 2 ;;
esac
