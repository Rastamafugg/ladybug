#!/usr/bin/env bash
# Launch the Ladybug retro-dev web app.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

HOST="${LADYBUG_WEB_HOST:-127.0.0.1}"
PORT="${LADYBUG_WEB_PORT:-8765}"

exec python3 -m uvicorn backend.main:app --host "$HOST" --port "$PORT" --loop asyncio --reload
