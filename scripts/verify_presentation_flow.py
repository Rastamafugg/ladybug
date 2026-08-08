#!/usr/bin/env python3
"""Verify FEAT-002 dynamic presentation structure and capacity guards."""

from __future__ import annotations

import json
import hashlib
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/presentation_runtime.s"
PRESENTATION_MAP = ROOT / "build/ladybug-presentation-runtime.map"
MODULE = ROOT / "build/ladybug-presentation-runtime.bin"
LAYOUT = ROOT / "build/ladybug-sparse-layout.json"
ACTOR_REFERENCE = ROOT / "assets/arcade/attract_actor_reference.json"
SOUND_SOURCE_BUDGET = 1536
SOUND_RELEASE_RESERVE = 512


def symbol_map(text: str) -> dict[str, int]:
    return {
        name: int(value, 16)
        for name, value in re.findall(
            r"^Symbol: (\w+) .* = ([0-9A-Fa-f]+)$", text, re.MULTILINE
        )
    }


def main() -> None:
    source = SOURCE.read_text(encoding="ascii")
    symbols = symbol_map(PRESENTATION_MAP.read_text(encoding="ascii"))
    layout = json.loads(LAYOUT.read_text(encoding="ascii"))
    actor_reference = json.loads(ACTOR_REFERENCE.read_text(encoding="ascii"))
    module_bytes = len(MODULE.read_bytes())
    cold = layout["presentation_cold"]["bytes"]
    combined = module_bytes + cold
    source_spare = layout["gmc"]["spare_bytes"]

    required_symbols = (
        "attract_overlay",
        "instructions_overlay",
        "highlight_phase",
        "draw_actor_overlay",
        "demo_drive",
        "demo_force_death",
        "demo_force_enemy_death",
    )
    missing = [name for name in required_symbols if name not in symbols]
    if missing:
        raise SystemExit("presentation flow proof: missing symbols: " + ", ".join(missing))

    required_source = (
        "SPARSE_ENEMY_INDEX_ADDR equ $0500",
        "SPARSE_PLAYER_INDEX_ADDR equ $0680",
        "instruction_phase_colors",
        "fcb     1,2,3,1,2,3",
        "PRES_DEMO_CAUSE",
        "ENTITY_TABLE equ $A380",
        "jsr     $0809",
        "inc     PRES_DST+1",
        "PRESENTATION_MAP_LEVEL_START",
        "PRESENTATION_MAP_INSTRUCTIONS",
        "PRESENTATION_MAP_ATTRACT",
        "ATTRACT_PLAYER_DST equ $661C",
        "ATTRACT_ENEMY_DST equ $2CA4",
        "PLAYER_BG_PTR equ $00A2",
        "PLAYER_BG_VALID equ $006A",
        "PRES_MAIN_SAVE_PLAYER",
        "PRES_MAIN_RESTORE_PLAYER",
        "restore_actor_underlay",
        "present_actor_overlay",
    )
    missing_source = [fragment for fragment in required_source if fragment not in source]
    if missing_source:
        raise SystemExit(
            "presentation flow proof: source contract missing: " +
            ", ".join(missing_source)
        )

    phase_match = re.search(
        r"instruction_phase_starts\s+fdb\s+\$3940,\$4834,\$5234,\$7540,\$7F34,\$8434",
        source,
    )
    if not phase_match:
        raise SystemExit("presentation flow proof: five instruction row destinations missing")

    capture = ROOT / actor_reference["provenance"]["capture"]
    capture_hash = hashlib.sha256(capture.read_bytes()).hexdigest().upper()
    if capture_hash != actor_reference["provenance"]["capture_sha256"]:
        raise SystemExit("presentation flow proof: attract capture hash mismatch")
    actor_destinations = {
        name: actor["presentation_destination"]
        for name, actor in actor_reference["actors"].items()
    }
    source_labels = {"player": "ATTRACT_PLAYER_DST", "enemy": "ATTRACT_ENEMY_DST"}
    for name, destination in actor_destinations.items():
        if f"{source_labels[name]} equ {destination}" not in source:
            raise SystemExit(
                f"presentation flow proof: {name} capture destination is not wired"
            )
    present_source = source.split("present_actor_overlay", 1)[1]
    restore_index = present_source.index("lbsr    restore_actor_underlay")
    save_index = present_source.index("jsr     PRES_MAIN_SAVE_PLAYER")
    draw_index = present_source.index("lbsr    draw_actor_overlay")
    if not restore_index < save_index < draw_index:
        raise SystemExit("presentation flow proof: actor restore/save/draw order is invalid")
    if "ldd     #PLAYER_BG\n        std     PLAYER_BG_PTR" not in source:
        raise SystemExit("presentation flow proof: presentation save-under pointer is not initialized")
    if "clr     PLAYER_BG_VALID" not in source:
        raise SystemExit("presentation flow proof: presentation save-under validity is not reset")
    for name, actor in actor_reference["actors"].items():
        raw_x, raw_y = actor["raw_top_left"]
        logical_x = raw_y + 40
        logical_y = 192 - raw_x - 16
        expected = 0x2000 + logical_y * 160 + logical_x // 2
        if f"${expected:04X}" != actor["presentation_destination"]:
            raise SystemExit(
                f"presentation flow proof: {name} capture transform is inconsistent"
            )

    if module_bytes > 1280:
        raise SystemExit(f"presentation flow proof: module is {module_bytes}/1280 bytes")
    if cold > 12939:
        raise SystemExit(f"presentation flow proof: cold payload is {cold}/12939 bytes")
    if combined > 14219:
        raise SystemExit(f"presentation flow proof: module+cold is {combined}/14219 bytes")
    sound_margin = source_spare - SOUND_SOURCE_BUDGET
    if sound_margin < SOUND_RELEASE_RESERVE:
        raise SystemExit(
            f"presentation flow proof: future-sound margin is {sound_margin}; "
            f"required reserve is {SOUND_RELEASE_RESERVE}"
        )

    phases = {min(frame >> 5, 5) for frame in range(192)}
    if phases != {0, 1, 2, 3, 4, 5}:
        raise SystemExit("presentation flow proof: instruction phase schedule is incomplete")

    print(
        "presentation flow proof: title actor overlays, six instruction phases, "
        "capture-backed title coordinates, actor underlay restore, skull/enemy demo forcing, "
        f"module {module_bytes}/1280, cold {cold}/12939, "
        f"combined {combined}/14219, future-sound margin {sound_margin}/{SOUND_RELEASE_RESERVE}"
    )


if __name__ == "__main__":
    main()
