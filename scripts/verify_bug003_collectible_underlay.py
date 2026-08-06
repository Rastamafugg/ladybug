#!/usr/bin/env python3
"""Verify full stage rendering clears collectible underlays before sprites."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "src/enemy_runtime.s").read_text(encoding="utf-8")
MAIN = (ROOT / "src/main.s").read_text(encoding="utf-8")


def section(source: str, start: str, end: str) -> str:
    return source[source.index(start) : source.index(end, source.index(start))]


def main() -> int:
    stage_start = "fri_stage_background\n        jsr     draw_screen\n"
    stage = section(SOURCE, stage_start, "\n        ifeq    PERSISTENT_FB\n")
    order = [
        stage.index("jsr     draw_screen"),
        stage.index("jsr     erase_entity_footprints"),
        stage.index("jsr     draw_all_gates"),
        stage.index("jsr     draw_entities"),
    ]
    if order != sorted(order):
        raise SystemExit("BUG-003 stage order does not clear underlays before entity draw")

    placement = section(MAIN, "place_entity\n", "\nrng_next\n")
    if "anda    #$7F" not in placement:
        raise SystemExit("BUG-003 placement no longer clears the occupied dot bit")

    restore = section(MAIN, "draw_maze_state_cell\n", "\n;==============================================================================\n; draw_cell_tile")
    if "cmpb    #MAZE_DOT_TILE" not in restore or "ldb     #MAZE_CLEAN_TILE" not in restore:
        raise SystemExit("BUG-003 restore path does not map consumed authored dots to clean tiles")

    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    report = {
        "source_commit": commit,
        "stage_order": ["draw_screen", "erase_entity_footprints", "draw_all_gates", "draw_entities"],
        "placement_clears_dot_bit": True,
        "consumed_dot_restores_clean_tile": True,
        "pass": True,
    }
    output = ROOT / "build" / "bug-003-collectible-underlay.json"
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("BUG-003 collectible underlay: stage order and maze-state restore pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
