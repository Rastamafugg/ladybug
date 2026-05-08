#!/usr/bin/env bash
# Ladybug build / run / clean.
# See wiki/tooling/build-workflow.md for the full runbook.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_MAIN="$ROOT/src/main.s"
BUILD_DIR="$ROOT/build"
ROM="$BUILD_DIR/ladybug.rom"
LST="$BUILD_DIR/ladybug.lst"
MAP="$BUILD_DIR/ladybug.map"
CART_BYTES=32768

cmd_build() {
    [[ -f "$SRC_MAIN" ]] || { echo "build: $SRC_MAIN not found" >&2; exit 1; }
    mkdir -p "$BUILD_DIR"

    lwasm -9 --format=raw \
          --output="$ROM" \
          --list="$LST" \
          --symbols \
          --map="$MAP" \
          "$SRC_MAIN"

    python3 - "$ROM" "$CART_BYTES" <<'PY'
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

cmd_run() {
    cmd_build
    exec xroar \
        -machine coco3 \
        -ram 512 \
        -cart ladybug \
        -cart-type rom \
        -cart-rom "$ROM" \
        -cart-autorun \
        ${XROAR_EXTRA:-}
}

cmd_clean() {
    rm -rf "$BUILD_DIR"
    echo "clean: removed $BUILD_DIR"
}

case "${1:-build}" in
    build) cmd_build ;;
    run)   cmd_run ;;
    clean) cmd_clean ;;
    *)     echo "usage: $0 {build|run|clean}" >&2; exit 2 ;;
esac
