#!/usr/bin/env bash
# Ladybug web app container entrypoint.
set -euo pipefail

mkdir -p /var/log/supervisor

# Clear any stale X lock from a previous (unclean) run so Xvfb can bind :99.
rm -f /tmp/.X99-lock /tmp/.X11-unix/X99 2>/dev/null || true

# Warn loudly if the copyrighted CoCo 3 system ROMs are missing. XRoar's
# `-machine coco3` + `-cart-autorun` boots through Tandy BASIC and will not
# dispatch into the cartridge without these. They are NOT shipped in the
# image — mount your own into /root/.xroar (see web/docker/README.md).
missing=0
for rom in coco3.rom extbas11.rom; do
    if [[ ! -f "/root/.xroar/${rom}" ]]; then
        echo "WARNING: /root/.xroar/${rom} not found — XRoar coco3 autorun will not work." >&2
        missing=1
    fi
done
if [[ "${missing}" -eq 1 ]]; then
    echo "         Drop coco3.rom (32K) and extbas11.rom (8K) into the mounted roms/ dir." >&2
fi

exec "$@"
