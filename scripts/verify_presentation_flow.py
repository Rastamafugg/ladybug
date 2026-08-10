#!/usr/bin/env python3
"""Verify FEAT-002 dynamic presentation structure and capacity guards."""

from __future__ import annotations

import json
import hashlib
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/presentation_runtime.s"
HELPER_SOURCE = ROOT / "src/perimeter_reset_helper.s"
PRESENTATION_MAP = ROOT / "build/ladybug-presentation-runtime.map"
MODULE = ROOT / "build/ladybug-presentation-runtime.bin"
LAYOUT = ROOT / "build/ladybug-sparse-layout.json"
PRESENTATION_LAYOUT = ROOT / "build/ladybug-presentation.json"
ACTOR_REFERENCE = ROOT / "assets/arcade/attract_actor_reference.json"
SOUND_SOURCE_BUDGET = 1536
SOUND_RELEASE_RESERVE = 512
COLD_HARD_LIMIT = 10874
COLD_PREFERRED_TARGET = 9989


def symbol_map(text: str) -> dict[str, int]:
    return {
        name: int(value, 16)
        for name, value in re.findall(
            r"^Symbol: (\w+) .* = ([0-9A-Fa-f]+)$", text, re.MULTILINE
        )
    }


def main() -> None:
    source = SOURCE.read_text(encoding="ascii")
    helper_source = HELPER_SOURCE.read_text(encoding="ascii")
    symbols = symbol_map(PRESENTATION_MAP.read_text(encoding="ascii"))
    layout = json.loads(LAYOUT.read_text(encoding="ascii"))
    presentation_layout = json.loads(PRESENTATION_LAYOUT.read_text(encoding="ascii"))
    actor_reference = json.loads(ACTOR_REFERENCE.read_text(encoding="ascii"))
    module_bytes = len(MODULE.read_bytes())
    cold = layout["presentation_cold"]["bytes"]
    combined = module_bytes + cold
    source_spare = layout["gmc"]["spare_bytes"]

    required_symbols = (
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
        "SPARSE_ENEMY_INDEX_ADDR equ $A000",
        "SPARSE_PLAYER_INDEX_ADDR equ $A000",
        "SPARSE_ENEMY_PAYLOAD_PAGE equ $35",
        "SPARSE_PLAYER_PAYLOAD_PAGE equ $39",
        "instruction_phase_colors",
        "fcb     1,2,3,1,2,3",
        "PRES_DEMO_CAUSE",
        "ENTITY_TABLE equ $A380",
        "jsr     $0809",
        "inc     <$AF",
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

    if actor_reference.get("schema") != "ladybug-mame-attract-actor-reference-v2":
        raise SystemExit("presentation flow proof: attract oracle schema is stale")
    actor_destinations = {
        name: actor["presentation_destination"]
        for name, actor in actor_reference["actors"].items()
    }
    if "PRES_ACTOR_TABLE equ $B200" not in source or "PRES_ACTOR_UNDERLAY equ $B000" not in source:
        raise SystemExit("presentation flow proof: four-actor ownership buffers are not wired")
    attract_source = helper_source
    if "jsr     PRES_MAIN_FB_PREPARE" not in attract_source or "PRES_MAIN_FB_FINISH" not in attract_source:
        raise SystemExit("presentation flow proof: attract owner publication is incomplete")
    actor_draw_source = helper_source
    if "PRES_MAIN_RESTORE_PLAYER" not in actor_draw_source or "PRES_MODULE_DRAW_ACTOR" not in actor_draw_source:
        raise SystemExit("presentation flow proof: attract restore/draw order is incomplete")
    if "inflate_maps" in source or "cold_write_byte" in source:
        raise SystemExit("presentation flow proof: all-map inflation remains active")
    if "leax    map_stream_offsets,pcr" not in source:
        raise SystemExit("presentation flow proof: selected-screen stream is not initialized")
    load_source = source[source.index("\nload_tick\n"):source.index("\nload_done\n")]
    if "sta     PRES_ROWS" not in load_source or "dec     PRES_ROWS" not in load_source:
        raise SystemExit("presentation flow proof: load budget is not memory-backed")
    if "decb" in load_source:
        raise SystemExit("presentation flow proof: load budget still uses clobbered B")
    preemption = source[source.index("\npft_mode\n"):source.index("\npft_dispatch\n")]
    for fragment in (
        "bita    #1", "tst     PRES_CREDITS", "dec     PRES_CREDITS",
        "PRESENTATION_MAP_LEVEL_START",
    ):
        if fragment not in preemption:
            raise SystemExit(
                "presentation flow proof: global start pre-emption is incomplete"
            )
    if source.index("clr     PRES_ACTOR_FRAME") > source.index("\npft_ready\n"):
        raise SystemExit("presentation flow proof: actor frame is not initialized")
    if "sta     PRES_ACTOR_PHASE" not in attract_source:
        raise SystemExit("presentation flow proof: attract phase selection is absent")
    cold_manifest = presentation_layout
    if cold_manifest.get("gameplay_tile_base") != cold_manifest.get(
        "cold_only_tile_count"
    ):
        raise SystemExit("presentation flow proof: gameplay tile partition is ambiguous")
    if cold_manifest.get("gameplay_lookup_bytes", 0) <= 0:
        raise SystemExit("presentation flow proof: gameplay tile lookup is absent")
    for name, actor in actor_reference["actors"].items():
        raw_x, raw_y = actor["raw_top_left"]
        logical_x = raw_y + 40
        logical_y = 192 - raw_x - 16
        expected = 0x2000 + logical_y * 160 + logical_x // 2
        if f"${expected:04X}" != actor["presentation_destination"]:
            raise SystemExit(
                f"presentation flow proof: {name} capture transform is inconsistent"
            )

    helper_bytes = len((ROOT / "build/ladybug-perimeter-reset-helper.bin").read_bytes())
    if module_bytes > 1280:
        raise SystemExit(f"presentation flow proof: module is {module_bytes}/1280 bytes")
    if helper_bytes > 334:
        raise SystemExit(f"presentation flow proof: helper is {helper_bytes}/334 bytes")
    if cold > COLD_HARD_LIMIT:
        raise SystemExit(f"presentation flow proof: cold payload is {cold}/{COLD_HARD_LIMIT} bytes")
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
        "capture-backed title coordinates, direct selected-screen streaming, bounded loading, "
        "global credit/start pre-emption, actor underlay restore, skull/enemy demo forcing, "
        f"module {module_bytes}/1280, helper {helper_bytes}/334, cold {cold}/{COLD_HARD_LIMIT} "
        f"(preferred {COLD_PREFERRED_TARGET}), "
        f"combined {combined}/14219, future-sound margin {sound_margin}/{SOUND_RELEASE_RESERVE}"
    )


if __name__ == "__main__":
    main()
