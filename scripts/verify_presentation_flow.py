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
BOOT_SOURCE = ROOT / "src/gmc_bootstrap.s"
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
    boot_source = BOOT_SOURCE.read_text(encoding="ascii")
    symbols = symbol_map(PRESENTATION_MAP.read_text(encoding="ascii"))
    layout = json.loads(LAYOUT.read_text(encoding="ascii"))
    presentation_layout = json.loads(PRESENTATION_LAYOUT.read_text(encoding="ascii"))
    actor_reference = json.loads(ACTOR_REFERENCE.read_text(encoding="ascii"))
    module_bytes = len(MODULE.read_bytes())
    cold = layout["presentation_cold"]["bytes"]
    combined = module_bytes + cold
    source_spare = layout["gmc"]["spare_bytes"]
    development = bool(presentation_layout.get("development_profile"))
    complete = bool(presentation_layout.get("complete_profile"))
    highscore_test = bool(presentation_layout.get("highscore_test_profile"))
    if complete:
        aux = layout.get("aux_runtime", {})
        instruction_runtime = layout.get("instruction_runtime", {})
        demo_runtime = layout.get("demo_runtime", {})
        if aux.get("role") != "complete":
            raise SystemExit("presentation flow proof: complete profile manifest role is missing")
        if instruction_runtime.get("role") != "instructions":
            raise SystemExit("presentation flow proof: instruction runtime is not staged")
        if demo_runtime.get("role") != "demo-route":
            raise SystemExit("presentation flow proof: demo runtime is not staged")
        if demo_runtime.get("stage_address") != (
                instruction_runtime.get("stage_address", 0) +
                instruction_runtime.get("bytes", 0)):
            raise SystemExit("presentation flow proof: auxiliary stage order is not contiguous")
        if aux.get("staged_bytes") != (
                instruction_runtime.get("bytes", 0) + demo_runtime.get("bytes", 0)):
            raise SystemExit("presentation flow proof: auxiliary staged size is inconsistent")

    required_symbols = [
        "install_aux_runtime",
        "draw_actor_overlay",
        "draw_tile_id",
        "cold_ptr",
        "colour_tile",
    ]
    if development:
        required_symbols.append("instructions_tick")
    if highscore_test:
        required_symbols.extend(("demo_tick", "name_tick", "module_commit_name"))
    elif not development or complete:
        required_symbols.extend(("demo_tick", "demo_run"))
    missing = [name for name in required_symbols if name not in symbols]
    if missing:
        raise SystemExit("presentation flow proof: missing symbols: " + ", ".join(missing))

    required_source = (
        "SPARSE_ENEMY_INDEX_ADDR equ $A000",
        "SPARSE_PLAYER_INDEX_ADDR equ $A000",
        "SPARSE_ENEMY_PAYLOAD_PAGE equ $35",
        "SPARSE_PLAYER_PAYLOAD_PAGE equ $39",
        "PRESENTATION_MAP_LEVEL_START",
        "PRESENTATION_MAP_INSTRUCTIONS",
        "PRESENTATION_MAP_ATTRACT",
        "ATTRACT_PLAYER_DST equ $661C",
        "ATTRACT_ENEMY_DST equ $2CA4",
        "PLAYER_BG_PTR equ $00A2",
        "PLAYER_BG_VALID equ $006A",
        "install_aux_runtime",
        "ldy     #$0300",
        "lda     #$23",
    )
    if development:
        required_source += (
            "INSTRUCTION_RUNTIME_TICK equ $0300",
            "install_aux_runtime",
            "PRESENTATION_INSTRUCTION_RUNTIME_ADDRESS",
            "PRESENTATION_INSTRUCTION_RUNTIME_BYTES",
        )
    if not development or complete:
        required_source += (
            "DEMO_RUNTIME_TICK equ $0300",
            "install_demo_runtime",
            "PRESENTATION_DEMO_RUNTIME_ADDRESS",
            "PRESENTATION_DEMO_RUNTIME_BYTES",
        )
    missing_source = [fragment for fragment in required_source if fragment not in source]
    if missing_source:
        raise SystemExit(
            "presentation flow proof: source contract missing: " +
            ", ".join(missing_source)
        )

    actor_surfaces = presentation_layout.get("attract_actor_surfaces", {})
    if (actor_surfaces.get("bytes") != 2688 or
            len(actor_surfaces.get("actors", [])) != 7):
        raise SystemExit("presentation flow proof: seven authored actor surfaces are not wired")
    attract_source = helper_source
    if "jsr     PRES_MAIN_FB_PREPARE" not in attract_source or "PRES_MAIN_FB_FINISH" not in attract_source:
        raise SystemExit("presentation flow proof: attract owner publication is incomplete")
    for fragment in ("lda     #$3C", "ldx     #$AA8E", "ldx     #$AA80",
                     "lda     #7", "lda     #16", "leay    152,y"):
        if fragment not in attract_source:
            raise SystemExit("presentation flow proof: attract surface-copy worklist is incomplete")
    if "inflate_maps" in source or "cold_write_byte" in source:
        raise SystemExit("presentation flow proof: all-map inflation remains active")
    if "ldx     #PRES_MAIN_MAP_STREAM_OFFSETS" not in source:
        raise SystemExit("presentation flow proof: selected-screen stream is not initialized")
    for fragment in (
        "decompress_presentation_atlas",
        "PRESENTATION_TILE_ATLAS_EXPANDED_BYTES",
        "lda     #PRESENTATION_COLD_PAGE",
        "sta     PAR_EXEC+4",
        "lda     #PRESENTATION_COLD_PAGE+1",
        "sta     PAR_EXEC+5",
        "ldu     #$8000+PRESENTATION_TILE_ATLAS_SOURCE_OFFSET",
        "cmpy    #$A000+PRESENTATION_TILE_ATLAS_EXPANDED_BYTES",
    ):
        if fragment not in boot_source:
            raise SystemExit(
                "presentation flow proof: boot atlas expansion is incomplete"
            )
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
    expected_cells = [[11, 3], [35, 4], [27, 5], [3, 9],
                      [10, 15], [33, 19], [5, 20]]
    if [actor["cell"] for actor in actor_surfaces["actors"]] != expected_cells:
        raise SystemExit("presentation flow proof: authored TMX actor cells differ")

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
    if not development and sound_margin < SOUND_RELEASE_RESERVE:
        raise SystemExit(
            f"presentation flow proof: future-sound margin is {sound_margin}; "
            f"required reserve is {SOUND_RELEASE_RESERVE}"
        )

    profile_label = (
        "high-score test flow" if highscore_test else
        "development helper" if development else "release flow"
    )
    behavior_label = (
        "credit/start isolation, test auxiliary" if highscore_test else
        "global credit/start pre-emption, instruction choreography" if development else
        "global credit/start pre-emption, arcade-route demo"
    )
    print(
        f"presentation flow proof: {profile_label}, "
        "seven title actor surfaces, "
        "authored TMX coordinates, direct selected-screen streaming, bounded loading, "
        f"{behavior_label}, atomic surface copy, "
        f"module {module_bytes}/1280, helper {helper_bytes}/334, cold {cold}/{COLD_HARD_LIMIT} "
        f"(preferred {COLD_PREFERRED_TARGET}), "
        f"combined {combined}/14219, future-sound margin {sound_margin}/{SOUND_RELEASE_RESERVE}"
    )


if __name__ == "__main__":
    main()
