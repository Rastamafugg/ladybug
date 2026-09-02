#!/usr/bin/env python3
"""Verify FEAT-002 dynamic presentation structure and capacity guards."""

from __future__ import annotations

import json
import hashlib
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/presentation_runtime.s"
DEMO_SOURCE = ROOT / "src/demo_runtime.s"
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
    demo_source = DEMO_SOURCE.read_text(encoding="ascii")
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
    audio_integrated = bool(layout.get("audio_runtime"))
    development = bool(presentation_layout.get("development_profile"))
    complete = bool(presentation_layout.get("complete_profile"))
    highscore_test = bool(presentation_layout.get("highscore_test_profile"))
    if complete:
        aux = layout.get("aux_runtime", {})
        instruction_runtime = layout.get("instruction_runtime", {})
        demo_runtime = layout.get("demo_runtime", {})
        highscore_runtime = layout.get("highscore_runtime", {})
        highscore_helper = layout.get("highscore_helper", {})
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
        if highscore_runtime.get("destination_address") != 0x0300 or highscore_runtime.get("destination_end", 0) > 0x0698:
            raise SystemExit("presentation flow proof: high-score owner exceeds $0300-$0697")
        if not highscore_helper.get("bytes"):
            raise SystemExit("presentation flow proof: page-$23 high-score helper is absent")
        if aux.get("staged_bytes", 0) < sum(
                item.get("bytes", 0) for item in
                (instruction_runtime, demo_runtime, highscore_runtime, highscore_helper)):
            raise SystemExit("presentation flow proof: auxiliary staged coverage is incomplete")
        for fragment in (
            "lbmi    highscore_timer_owner",
            "lda     #$80",
            "sta     PRES_TICK_PHASE",
            "tst     FB_PENDING",
            "inc     PRES_TICK_PHASE",
            "lbra    highscore_timer_prepare",
            "cmpa    #PRES_HOLD_FINAL",
            "clr     PRES_HOLD_STATE",
        ):
            if fragment not in demo_source:
                raise SystemExit(
                    "presentation flow proof: complete name timer omits " + fragment
                )
        if not re.search(
                r"puls\s+a\s+tsta\s+bne\s+demo_runtime_done",
                demo_source,
                re.MULTILINE):
            raise SystemExit(
                "presentation flow proof: restored helper result is not tested before branch"
            )
        timer_callback = demo_source[
            demo_source.index("\nhighscore_after_tile\n"):
            demo_source.index("\nhighscore_tick_second\n")
        ]
        if "dec     PRES_TMP_H" in timer_callback or "highscore_timer_draw" in timer_callback:
            raise SystemExit(
                "presentation flow proof: complete name timer retains cumulative redraw"
            )
        prepare_block = demo_source[
            demo_source.index("\nhighscore_prepare_name\n"):
            demo_source.index("\nhighscore_commit_name\n")
        ]
        commit_block = demo_source[
            demo_source.index("\nhighscore_commit_name\n"):
            demo_source.index("\nhighscore_timer_records\n")
        ]
        for fragment in (
            "PRES_HIGHSCORE_ALIAS equ $8F84",
            "PRES_PENDING_NAME_ALIAS equ $8FDE",
            "ldu     #PRES_HIGHSCORE_ALIAS",
            "ldx     #PRES_PENDING_NAME_ALIAS",
            "ldx     #PRES_HIGHSCORE_ALIAS+70",
            "ldu     #PRES_HIGHSCORE_ALIAS+80",
            "lda     #7",
            "bmi     highscore_commit_write",
        ):
            if fragment not in demo_source:
                raise SystemExit(
                    "presentation flow proof: mapped high-score state omits " + fragment
                )
        for label, block in (("prepare", prepare_block), ("commit", commit_block)):
            if block.count("lda     PAR4") != 1 or block.count("sta     PAR4") != 2:
                raise SystemExit(
                    f"presentation flow proof: {label} does not save/map/restore PAR4 exactly"
                )
            for fragment in ("pshs    cc", "orcc    #$10", "puls    cc"):
                if fragment not in block:
                    raise SystemExit(
                        f"presentation flow proof: {label} mapping omits {fragment}"
                    )
        for pattern in (
            r"#PRES_HIGHSCORE_BASE(?:\+|\s)",
            r"#PRES_PENDING_NAME\s",
        ):
            if re.search(pattern, prepare_block) or re.search(pattern, commit_block):
                raise SystemExit(
                    "presentation flow proof: page-$23 helper retains direct page-$34 access " + pattern
                )

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
    hold_select = source[
        source.index("\nstart_screen_map\n"):source.index("\nstart_screen_hold\n")
    ]
    for fragment in (
        "cmpa    #PRESENTATION_MAP_INSTRUCTIONS",
        "bls     start_screen_hold",
        "cmpa    #PRESENTATION_MAP_ENTER_HIGH_SCORE",
        "bne     start_screen_done",
    ):
        if fragment not in hold_select:
            raise SystemExit(
                "presentation flow proof: held-screen selector omits " + fragment
            )
    if "HIGHSCORE_TEST_PROFILE" in hold_select:
        raise SystemExit(
            "presentation flow proof: enter-high-score hydration is profile-conditional"
        )
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
    if cold > COLD_HARD_LIMIT and not complete:
        raise SystemExit(f"presentation flow proof: cold payload is {cold}/{COLD_HARD_LIMIT} bytes")
    if combined > 14219 and not complete:
        raise SystemExit(f"presentation flow proof: module+cold is {combined}/14219 bytes")
    if audio_integrated:
        # FEAT-006 now owns the approved audio payload.  The old 1,536-byte
        # future-sound reservation is no longer a valid release calculation;
        # retain only the post-integration source-pool spare guard here.
        sound_margin = source_spare
        sound_label = "post-audio source spare"
    else:
        sound_margin = source_spare - SOUND_SOURCE_BUDGET
        sound_label = "future-sound margin"
    if not development and sound_margin < SOUND_RELEASE_RESERVE:
        raise SystemExit(
            f"presentation flow proof: {sound_label} is {sound_margin}; "
            f"required reserve is {SOUND_RELEASE_RESERVE}"
        )

    profile_label = (
        "high-score test flow" if highscore_test else
        "complete flow" if complete else
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
        f"combined {combined}/14219, {sound_label} {sound_margin}/{SOUND_RELEASE_RESERVE}"
    )


if __name__ == "__main__":
    main()
