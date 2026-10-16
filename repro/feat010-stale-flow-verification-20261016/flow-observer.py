#!/usr/bin/env python3
"""Verify FEAT-002 dynamic presentation structure and capacity guards."""

from __future__ import annotations

import json
import hashlib
import re
from pathlib import Path


ROOT = Path('/mnt/e/projects/ladybug/repro/feat010-source-documentation-repair-20261016/capsule')
SOURCE = ROOT / "src/presentation_runtime.s"
DEMO_SOURCE = ROOT / "src/demo_runtime.s"
HELPER_SOURCE = ROOT / "src/perimeter_reset_helper.s"
BOOT_SOURCE = ROOT / "src/gmc_bootstrap.s"
PAGE23_SOURCE = ROOT / "src/shared_text_stage.inc"
KEYBINDING_SOURCE = ROOT / "src/keybinding_runtime.s"
MAIN_SOURCE = ROOT / "src/main.s"
BUILD_SCRIPT = ROOT / "scripts/build.sh"
SOURCE_REFERENCE = ROOT / "scripts/source_reference.json"
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


def verify_helper_attract_dispatch(page23_source: str) -> None:
    """Check the FEAT-010 attract path stays in its approved helper regions."""

    lines = page23_source.splitlines()

    def label_index(label: str) -> int:
        label_pattern = re.compile(r"^\s*" + re.escape(label) + r"\s*:?\s*$")
        matches = [
            index for index, line in enumerate(lines)
            if label_pattern.fullmatch(line.split(";", 1)[0])
        ]
        if len(matches) != 1:
            raise SystemExit(
                "presentation flow proof: FEAT-010 helper dispatch requires one "
                + label
                + " label"
            )
        return matches[0]

    def code_lines(start: int, end: int) -> list[str]:
        result = []
        for line in lines[start + 1:end]:
            code = " ".join(line.split(";", 1)[0].split())
            if code:
                result.append(code)
        return result

    phase_tick = label_index("highscore_phase_tick")
    non_attract = label_index("highscore_phase_not_attract")
    if phase_tick >= non_attract:
        raise SystemExit(
            "presentation flow proof: FEAT-010 helper dispatch phase labels are reversed"
        )
    expected_prefix = [
        "lda PRES_SCREEN",
        "cmpa #PRESENTATION_MAP_ATTRACT",
        "lbeq highscore_attract_tick",
    ]
    if code_lines(phase_tick, non_attract) != expected_prefix:
        raise SystemExit(
            "presentation flow proof: FEAT-010 attract prefix is not the exact three-instruction dispatch"
        )

    record_includes = [
        index for index, line in enumerate(lines)
        if re.fullmatch(
            r'\s*include\s+"ladybug_menu_records\.inc"\s*',
            line.split(";", 1)[0],
        )
    ]
    if len(record_includes) != 1:
        raise SystemExit(
            "presentation flow proof: FEAT-010 helper dispatch requires one menu-record include"
        )
    wrapper = label_index("highscore_attract_tick")
    helper_end = label_index("highscore_phase_helper_end")
    if not record_includes[0] < wrapper < helper_end:
        raise SystemExit(
            "presentation flow proof: FEAT-010 attract wrapper is outside the post-record helper tail"
        )
    next_code = next(
        (index for index in range(record_includes[0] + 1, len(lines))
         if lines[index].split(";", 1)[0].strip()),
        None,
    )
    if next_code != wrapper:
        raise SystemExit(
            "presentation flow proof: FEAT-010 attract wrapper does not immediately follow menu records"
        )
    expected_wrapper = [
        "lbsr highscore_logo_tick",
        "lda PRES_MODE",
        "cmpa #MODE_ATTRACT",
        "lbne highscore_phase_hold",
        "lbra menu_tick",
    ]
    if code_lines(wrapper, helper_end) != expected_wrapper:
        raise SystemExit(
            "presentation flow proof: FEAT-010 attract wrapper is not the exact five-instruction tail"
        )


def main() -> None:
    source = SOURCE.read_text(encoding="ascii")
    demo_source = DEMO_SOURCE.read_text(encoding="ascii")
    helper_source = HELPER_SOURCE.read_text(encoding="ascii")
    boot_source = BOOT_SOURCE.read_text(encoding="ascii")
    page23_source = PAGE23_SOURCE.read_text(encoding="ascii")
    keybinding_source = KEYBINDING_SOURCE.read_text(encoding="ascii")
    main_source = MAIN_SOURCE.read_text(encoding="utf-8")
    build_script = BUILD_SCRIPT.read_text(encoding="ascii")
    source_reference = json.loads(SOURCE_REFERENCE.read_text(encoding="utf-8"))
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
        if (instruction_runtime.get("destination_address") != 0x0300 or
                instruction_runtime.get("destination_end", 0) > 0x06AA):
            raise SystemExit("presentation flow proof: title instruction owner exceeds $0300-$06A9")
        if not highscore_helper.get("bytes"):
            raise SystemExit("presentation flow proof: page-$23 high-score helper is absent")
        if aux.get("staged_bytes", 0) < sum(
                item.get("bytes", 0) for item in
                (instruction_runtime, demo_runtime, highscore_runtime, highscore_helper)):
            raise SystemExit("presentation flow proof: auxiliary staged coverage is incomplete")

        # FEAT-010 cold title paint must establish Start on hidden BACK before
        # the loader can publish either hydrated owner as FRONT.
        load_before_publish = source[
            source.index("\nload_done\n"):
            source.index("\nload_done_publish\n")
        ]
        for fragment in (
            "jsr     $B080", "PRESENTATION_ATTRACT_OVERLAY",
            "PRES_MAIN_FB_CAPTURE", "PRES_MAIN_FB_PUBLISH",
        ):
            if fragment not in load_before_publish:
                raise SystemExit("presentation flow proof: hidden title paint path omits " + fragment)
        if not (load_before_publish.index("jsr     $B080") <
                load_before_publish.index("PRESENTATION_ATTRACT_OVERLAY") <
                load_before_publish.index("PRES_MAIN_FB_CAPTURE") <
                load_before_publish.index("PRES_MAIN_FB_PUBLISH")):
            raise SystemExit("presentation flow proof: title paint/animation/capture/publication order changed")
        publish_block = source[
            source.index("\nload_done_publish\n"):
            source.index("\nload_done_normal\n")
        ]
        if "sta     PENDING" not in publish_block:
            raise SystemExit("presentation flow proof: cold title never marks the published surface pending")
        cold_start = source[
            source.index("\npft_helper_ready\n"):
            source.index("\npft_ready\n")
        ]
        for fragment in ("lbsr    start_screen", "clr     $D0", "clr     $E0", "clr     $E1"):
            if fragment not in cold_start:
                raise SystemExit("presentation flow proof: cold Start selection seed omits " + fragment)

        # Fixed inputs 5/6 are both coin edges.  The complete profile may
        # count them only after the live normal-game owner is established;
        # SPECIAL completion remains the independent stage-pending path.
        fixed_coin_scan = keybinding_source[
            keybinding_source.index("\nks_next\n"):
            keybinding_source.index("\nks_edges\n")
        ]
        fixed_coin_events = keybinding_source[
            keybinding_source.index("\nks_global\n"):
            keybinding_source.index("\nks_menu\n")
        ]
        for fragment in (
            "KB_FIXED_COIN_5 equ 44", "KB_FIXED_COIN_6 equ 52",
            "#KB_FIXED_COIN_5", "#KB_FIXED_COIN_6",
        ):
            if fragment not in keybinding_source and fragment not in fixed_coin_scan:
                raise SystemExit("presentation flow proof: fixed coin input omits " + fragment)
        for fragment in ("ora #32", "ora #64"):
            if fragment not in fixed_coin_scan:
                raise SystemExit("presentation flow proof: fixed coin held state omits " + fragment)
        for fragment in (
            "bitb #32", "ora #2", "bitb #64", "ora #4", "sta $A9",
        ):
            if fragment not in fixed_coin_events:
                raise SystemExit("presentation flow proof: coin event mapping omits " + fragment)
        coin_ready = source[
            source.index("\npft_ready\n"):
            source.index("\npft_no_credit\n")
        ]
        coin_guard_end = coin_ready.index("        cmpa    #$06")
        coin_guard = coin_ready[:coin_guard_end]
        for fragment in (
            "anda    #$06", "pshs    a", "lda     <PRES_MODE",
            "cmpa    #MODE_NORMAL", "lda     <PRES_SCREEN",
            "cmpa    #PRESENTATION_MAP_LEVEL_START",
            "lda     <PRES_CONTEXT", "cmpa    #PRES_CONTEXT_NEXT_STAGE",
            "pft_coin_suppress", "puls    a",
        ):
            if fragment not in coin_guard:
                raise SystemExit("presentation flow proof: complete live-credit guard omits " + fragment)
        context_guard = coin_guard[coin_guard.index("lda     <PRES_CONTEXT"):]
        if "tst     <PRES_CONTEXT" in context_guard:
            raise SystemExit("presentation flow proof: live credit rejects context 0 after stage preview")
        if coin_ready.index("        puls    a") > coin_ready.index("        bsr     add_credit"):
            raise SystemExit("presentation flow proof: complete credit count precedes its owner guard")
        coin_suppression = source[
            source.index("\npft_coin_suppress\n"):
            source.index("\nadd_credit\n")
        ]
        for fragment in ("leas    1,s", "lbra    pft_loop_wake"):
            if fragment not in coin_suppression:
                raise SystemExit("presentation flow proof: suppressed coin edge bypasses " + fragment)
        special_award = main_source[
            main_source.index("\nalp_special\n"):
            main_source.index("\nalp_special_draw\n")
        ]
        for fragment in ("cmpb    #$7F", "bsr    add_special_score", "inc     STAGE_PENDING"):
            if fragment not in special_award:
                raise SystemExit("presentation flow proof: SPECIAL award omits " + fragment)
        stage_handoff = source[
            source.index("\nnormal_stage\n"):
            source.index("\nnormal_start\n")
        ]
        for fragment in (
            "PRES_MAIN_NEXT_STAGE", "PRES_CONTEXT_NEXT_STAGE",
            "PRESENTATION_MAP_LEVEL_START",
        ):
            if fragment not in stage_handoff:
                raise SystemExit("presentation flow proof: SPECIAL stage handoff omits " + fragment)
        stage_preview = source[
            source.index("\nlevel_tick\n"):
            source.index("\nlive_begin\n")
        ]
        for fragment in (
            "cmpa    #PRES_CONTEXT_NEXT_STAGE", "clr     PRES_CONTEXT",
            "clr     <PRES_MODE",
        ):
            if fragment not in stage_preview:
                raise SystemExit("presentation flow proof: stage preview does not restore live context " + fragment)

        # Keep menu repaints on the resident framebuffer return path while
        # the copied $0300 owner is the larger instruction runtime.
        menu_source = page23_source[
            page23_source.index("\nmenu_tick\n"):
            page23_source.index("\nmenu_load_finish\n")
        ]
        for forbidden in ("PRES_HIGHSCORE_FB_PREPARE", "PRES_HIGHSCORE_FB_FINISH"):
            if forbidden in menu_source:
                raise SystemExit("presentation flow proof: menu callback depends on copied high-score owner")
        for fragment in (
            "PRES_MAIN_FB_PREPARE", "PRES_MAIN_FB_FINISH",
            "PRES_GAME_PAGE_RETURN", "PRES_MAIN_PAGE23_RESUME",
        ):
            if fragment not in menu_source:
                raise SystemExit("presentation flow proof: resident menu return omits " + fragment)
        menu_painter = page23_source[
            page23_source.index("\nmenu_load_finish\n"):
            page23_source.index("\nmenu_paint_options\n")
        ]
        for fragment in (
            "menu_paint_attract", "menu_attract_rows", "cmpb    MENU_SELECT",
            "lda     #10", "lda     #7",
        ):
            if fragment not in menu_painter:
                raise SystemExit("presentation flow proof: cold title painter omits " + fragment)
        verify_helper_attract_dispatch(page23_source)

        key_scan = keybinding_source[
            keybinding_source.index("\nkey_scan\n"):
            keybinding_source.index("\nkey_bits\n")
        ]
        for fragment in (
            "lda ,x", "coma", "anda ,s", "sta ,x+",
            "ifne INPUT_JOYSTICK", "jsr PRES_MAIN_JOY_AXIS",
            "#MODE_LEVEL", "#MODE_CREDIT", "#PRESENTATION_MAP_HIGH_SCORE",
            "sta PIA2_DA", "sta $FF01", "sta $FF03", "sta PIA2_CRB",
        ):
            if fragment not in key_scan:
                raise SystemExit("presentation flow proof: fresh-input sampler omits " + fragment)
        if key_scan.count("jsr PRES_MAIN_JOY_AXIS") != 2:
            raise SystemExit("presentation flow proof: joystick sampler must read exactly two axes")
        if any(token in key_scan for token in ("JOY_DIR", "PLAYER_WANT", "PLAYER_FACE", "PLAYER_MANUAL")):
            raise SystemExit("presentation flow proof: frontend sampler writes gameplay input state")
        if "if int(input_joystick):\n    wanted['joy_read_axis'] = 'PRES_MAIN_JOY_AXIS'" not in build_script:
            raise SystemExit("presentation flow proof: joystick callback is not conditionally exported")
        key_module = next(item for item in source_reference["modules"]
                          if item["id"] == "keybinding-runtime")
        if ("PRES_MAIN_JOY_AXIS" not in key_module.get("conditional_external_symbols", []) or "PRES_MAIN_JOY_AXIS" in key_module.get("external_symbols", [])):
            raise SystemExit("presentation flow proof: conditional joystick dependency is undocumented")
        key_init = keybinding_source[
            keybinding_source.index("\nkey_init\n"):
            keybinding_source.index("\nkey_defaults\n")
        ]
        if "lda #$FF" not in key_init or "sta ,x+" not in key_init:
            raise SystemExit("presentation flow proof: raw history is not seeded before first scan")
        if not re.search(r"ifne\s+INPUT_JOYSTICK\s+lda\s+#\$FF\s+sta\s+key_joy_last", key_init):
            raise SystemExit("presentation flow proof: joystick first sample can manufacture an edge")

        # Name entry may keep the private direction baseline current, but only
        # automatic-loop owners may publish a direction edge.
        name_joy_start = key_scan.index("cmpa #MODE_NAME")
        name_joy_branch = key_scan[
            name_joy_start:
            key_scan.index("ks_joy_credit_screen", name_joy_start)
        ]
        if "bra ks_joy_silent" not in name_joy_branch or "sta key_joy_last" in name_joy_branch:
            raise SystemExit("presentation flow proof: name entry does not silently sample its private baseline")
        if not re.search(r"ks_joy_silent\s+clra\s+ks_joy_begin\s+pshs a", key_scan):
            raise SystemExit("presentation flow proof: silent presentation sample can emit a wake")

        joy_sample = key_scan[
            key_scan.index("\nks_joy_begin\n"):
            key_scan.index("\nks_joy_done\n")
        ]
        joy_sample_code = "\n".join(line.split(";", 1)[0] for line in joy_sample.splitlines())
        joy_sample_flat = " ".join(joy_sample_code.split())
        if ("lda #$34 sta PIA2_CRB sta $FF01 sta $FF03 "
                "jsr PRES_MAIN_JOY_AXIS pshs b lda #$3C sta $FF01 "
                "jsr PRES_MAIN_JOY_AXIS pshs b lda ,s suba #32 "
                "bpl ks_joy_y_abs nega ks_joy_y_abs sta KB_WORK "
                "lda 1,s suba #32 bpl ks_joy_x_abs nega ks_joy_x_abs "
                "sta KB_CAND" not in joy_sample_flat):
            raise SystemExit("presentation flow proof: axis callback order no longer maps X and Y stack samples correctly")
        if ("lda KB_CAND cmpa KB_WORK bhs ks_joy_horizontal "
                "lda KB_WORK cmpa #8 bls ks_joy_center lda ,s cmpa #32 "
                "blo ks_joy_north lda #DIR_S" not in joy_sample_flat):
            raise SystemExit("presentation flow proof: vertical fallthrough does not reload Y magnitude before its deadzone")
        if ("ks_joy_horizontal lda KB_CAND cmpa #8 bls ks_joy_center "
                "lda 1,s cmpa #32 blo ks_joy_west lda #DIR_E" not in joy_sample_flat):
            raise SystemExit("presentation flow proof: horizontal path does not retain X magnitude for its deadzone")
        if not all(example in joy_sample for example in (
                "X=32/Y=0 -> N", "X=0/Y=32 -> W", "X=48/Y=48 -> E")):
            raise SystemExit("presentation flow proof: asymmetric and tied-axis examples are missing")
        axis_examples = ((32, 0, "N"), (0, 32, "W"), (48, 48, "E"))
        for x_axis, y_axis, expected in axis_examples:
            x_delta, y_delta = abs(x_axis - 32), abs(y_axis - 32)
            if x_delta >= y_delta:
                actual = "none" if x_delta <= 8 else ("E" if x_axis >= 32 else "W")
            else:
                actual = "none" if y_delta <= 8 else ("S" if y_axis >= 32 else "N")
            if actual != expected:
                raise SystemExit("presentation flow proof: joystick axis example has the wrong cardinal result")
        if not all(fragment in joy_sample_flat for fragment in (
                "cmpa #DIR_NONE beq ks_joy_store", "tst ,s beq ks_joy_store",
                "cmpa #$FF beq ks_joy_store", "sta key_joy_last")):
            raise SystemExit("presentation flow proof: cold seed, neutral release, or eligible-edge guard changed")
        if (len(re.findall(r"^\s*pshs\s+(?:a|b)\s*$", joy_sample_code, re.MULTILINE)) != 3 or
                len(re.findall(r"^\s*leas\s+2,s\s*$", joy_sample_code, re.MULTILINE)) != 1 or
                len(re.findall(r"^\s*leas\s+1,s\s*$", joy_sample_code, re.MULTILINE)) != 1):
            raise SystemExit("presentation flow proof: raw joystick sample stack is unbalanced")
        if not re.search(
                r"lda #\$80 sta PIA2_DA lda #\$34 sta \$FF01 "
                r"lda #\$3C sta \$FF03 sta PIA2_CRB", joy_sample_flat):
            raise SystemExit("presentation flow proof: raw sample does not restore established GMC selectors")
        if any(token in joy_sample_code for token in (
                "PRES_MAIN_READ_JOY", "JOY_X", "JOY_Y", "JOY_DIR",
                "PLAYER_WANT", "PLAYER_FACE", "PLAYER_MANUAL", "PRES_NAME_")):
            raise SystemExit("presentation flow proof: private direction sample writes name or gameplay input state")

        joy_axis_start = main_source.index("\njoy_read_axis\n")
        joy_axis_end = main_source.index("\n        else\n", joy_axis_start)
        joy_axis_source = main_source[joy_axis_start:joy_axis_end]
        joy_axis_code = "\n".join(line.split(";", 1)[0] for line in joy_axis_source.splitlines())
        joy_axis_flat = " ".join(joy_axis_code.split())
        if "stb PIA2_DA" not in joy_axis_flat or "lda PIA1_DA" not in joy_axis_flat:
            raise SystemExit("presentation flow proof: existing raw axis callback lost its DAC/PA7 sampling path")
        if any(token in joy_axis_code for token in (
                "sta PIA1", "JOY_", "PLAYER_", "PRES_NAME_")):
            raise SystemExit("presentation flow proof: raw axis callback writes selector or owned game/name state")
        pft_scan = source[
            source.index("\npresentation_flow_tick\n"):
            source.index("\npft_ready\n")
        ]
        if ("scan_keys" not in pft_scan or
                "jsr PRES_MAIN_READ_JOY" not in " ".join(page23_source.split())):
            raise SystemExit("presentation flow proof: name baseline scan order or name-owned joystick path changed")
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

    normalized_source = " ".join(source.lower().split())
    auxiliary_copy_contracts = (
        "install_aux_runtime_copy sta par5 ldy #$0300 "
        "install_aux_runtime_byte lda ,x+ sta ,y+ leau -1,u "
        "cmpu #0 bne install_aux_runtime_byte",
        "install_aux_runtime_copy sta par5 exg u,y ldu #$0300 "
        "install_aux_runtime_byte lda ,x+ sta ,u+ leay -1,y "
        "bne install_aux_runtime_byte",
    )
    if not any(contract in normalized_source for contract in auxiliary_copy_contracts):
        raise SystemExit(
            "presentation flow proof: auxiliary copy loop is neither the baseline "
            "nor the register-swapped bounded implementation"
        )

    actor_surfaces = presentation_layout.get("attract_actor_surfaces", {})
    if (actor_surfaces.get("bytes") != 7680 or
            len(actor_surfaces.get("actors", [])) != 8):
        raise SystemExit("presentation flow proof: eight authored actor surfaces are not wired")
    attract_source = helper_source
    if "jsr     PRES_MAIN_FB_PREPARE" not in attract_source or "PRES_MAIN_FB_FINISH" not in attract_source:
        raise SystemExit("presentation flow proof: attract owner publication is incomplete")
    for fragment in ("lda     #$3C", "ldx     #$BE28", "ldx     #$BE00",
                     "lda     #8", "lda     #16", "leay    152,y"):
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
    hold_contract = (
        "cmpa    #PRESENTATION_MAP_LEVEL_START",
        "beq     start_screen_done",
    ) if complete else (
        "cmpa    #PRESENTATION_MAP_INSTRUCTIONS",
        "bls     start_screen_hold",
        "cmpa    #PRESENTATION_MAP_ENTER_HIGH_SCORE",
        "bne     start_screen_done",
    )
    for fragment in hold_contract:
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
        "bita    #1", "tst     <PRES_CREDITS", "dec     <PRES_CREDITS",
        "PRESENTATION_MAP_LEVEL_START",
    ):
        if fragment not in preemption:
            raise SystemExit(
                "presentation flow proof: global start pre-emption is incomplete"
            )
    if source.index("clr     <PRES_ACTOR_FRAME") > source.index("\npft_ready\n"):
        raise SystemExit("presentation flow proof: actor frame is not initialized")
        loop_wake = source[
            source.index("\npft_loop_wake\n"):
            source.index("\npft_mode\n")
        ]
        for fragment in (
            "#MODE_DEMO", "#MODE_LEVEL", "#PRESENTATION_MAP_INSTRUCTIONS",
            "#PRESENTATION_MAP_LEVEL_START", "#MODE_LOAD",
            "#PRESENTATION_MAP_HIGH_SCORE", "#MODE_CREDIT", "bita    #$80",
            "clr     <PRES_EVENT>", "clr     $D0", "clr     <PENDING>",
            "#PRESENTATION_MAP_ATTRACT", "clr     <PRES_TIMER>",
        ):
            if fragment not in loop_wake:
                raise SystemExit("presentation flow proof: fresh automatic-loop wake omits " + fragment)
    if "sta     PRES_ACTOR_PHASE" not in attract_source:
        raise SystemExit("presentation flow proof: attract phase selection is absent")
    cold_manifest = presentation_layout.get("native_intermediate", presentation_layout)
    if cold_manifest.get("gameplay_tile_base") != cold_manifest.get(
        "cold_only_tile_count"
    ):
        raise SystemExit("presentation flow proof: gameplay tile partition is ambiguous")
    if cold_manifest.get("gameplay_lookup_bytes", 0) <= 0:
        raise SystemExit("presentation flow proof: gameplay tile lookup is absent")
    expected_cells = [[11, 3], [20, 4], [35, 4], [27, 5], [3, 9],
                      [10, 15], [33, 19], [5, 20]]
    if [actor["cell"] for actor in actor_surfaces["actors"]] != expected_cells:
        raise SystemExit("presentation flow proof: authored TMX actor cells differ")

    helper_bytes = len((ROOT / "build/ladybug-perimeter-reset-helper.bin").read_bytes())
    if module_bytes > 1280:
        raise SystemExit(f"presentation flow proof: module is {module_bytes}/1280 bytes")
    if helper_bytes > 334:
        raise SystemExit(f"presentation flow proof: helper is {helper_bytes}/334 bytes")
    cold_limit = 16384 if complete else COLD_HARD_LIMIT
    combined_limit = 17664 if complete else 14219
    if cold > cold_limit:
        raise SystemExit(f"presentation flow proof: cold payload is {cold}/{cold_limit} bytes")
    if combined > combined_limit:
        raise SystemExit(f"presentation flow proof: module+cold is {combined}/{combined_limit} bytes")
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
        "eight title actor surfaces, "
        "authored TMX coordinates, direct selected-screen streaming, bounded loading, "
        f"{behavior_label}, atomic surface copy, "
        f"module {module_bytes}/1280, helper {helper_bytes}/334, cold {cold}/{cold_limit} "
        f"(preferred {COLD_PREFERRED_TARGET}), "
        f"combined {combined}/{combined_limit}, {sound_label} {sound_margin}/{SOUND_RELEASE_RESERVE}"
    )


if __name__ == "__main__":
    main()
