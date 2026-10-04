#!/usr/bin/env python3
"""Compare BUG-062 helper layout semantics across all twelve authored roots."""
from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
main = (root / "src/main.s").read_text(encoding="utf-8")
shared = (root / "src/shared_text_runtime.inc").read_text(encoding="utf-8")
catalog = (root / "wiki/internal/implementation/routine-catalog.html").read_text(encoding="utf-8")
helper = shared.split("life_marker_position\n", 1)[1].split("asset_draw_two_digits\n", 1)[0]
mirror = "; DOC-002 source-contract mirror contract life_marker_position profile=render: Map reserve slots 0-11 to authored HUD tile roots; write HUD_X and HUD_Y only."
assert mirror in main
assert 'id="routine-resident-runtime-life-marker-position"' in catalog
assert "jsr     life_marker_position" in main
assert "bsr     life_marker_position" not in main
assert "asset_draw_life_count" not in main + shared
assert all(token not in helper for token in ("LIVES", "ENTITY_WORK", "PLAYER_", "GAME_STATE"))
assert "sta     HUD_X" in helper and "stb     HUD_Y" in helper
ordered = [
    "ldb     #21", "cmpa    #3", "suba    #3", "subb    #2",
    "lsla", "adda    #33", "sta     HUD_X", "stb     HUD_Y", "rts",
]
positions = [helper.index(op) for op in ordered]
assert positions == sorted(positions), positions
loop = main.split("draw_lives\n", 1)[1].split("\nclear_life_marker\n", 1)[0]
assert "cmpa    LIVES" in loop and "cmpa    #12" in loop and "inc     ENTITY_WORK" in loop
complete, legacy = loop.split("        else\n", 1)
assert "ifne COMPLETE_PROFILE" in complete
assert "cmpa    #12" in complete and "jsr     life_marker_position" in complete
assert "cmpa    #3" in legacy
assert "bsr    draw_life_marker" in legacy and "bsr    clear_life_marker" in legacy
assert "life_marker_position" not in legacy
assert "asset_draw_life_count" not in main + shared

def old_position(slot):
    a, y = slot, 21
    while a >= 3:
        a -= 3
        y -= 1
        y -= 1
    return 33 + 2 * a, y

def new_position(slot):
    a, b = slot, 21
    while a >= 3:
        a -= 3
        b -= 2
    return 33 + 2 * a, b

expected = [(33 + 2 * (i % 3), 21 - 2 * (i // 3)) for i in range(12)]
old = [old_position(i) for i in range(12)]
new = [new_position(i) for i in range(12)]
assert old == new == expected, (old, new, expected)
print("PASS: old and relocated helper yield identical roots for slots 0..11")
print("roots=" + repr(new))
print("PASS: source-contract mirror is authored in main.s and catalog anchor is present")
print("PASS: call is absolute JSR; helper stores HUD_X/HUD_Y and does not mention reserve/game state")
print("PASS: excluded-profile else branch keeps the three-slot marker draw/clear fallback")
print("PASS: numeric fallback symbol removed from runtime sources")
