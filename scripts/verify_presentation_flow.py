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


def verify_attract_menu_schedule(module: bytes, symbols: dict[str, int]) -> None:
    """Exercise emitted Attract scheduling; callbacks model existing contracts.

    This does not emulate the painter, MMU, IRQ timing or pixels. Independent
    cases require idle repaint replay, clock progress and safe draw ordering.
    Unexpected instructions fail closed rather than silently skipping work.
    """
    origin = symbols["presentation_flow_tick"]
    timer_address = symbols["PRES_TIMER"]
    idle_address = symbols["PRES_IDLE_ORIGIN"]
    limit = symbols["PRESENTATION_ROTATION_TICKS"]

    def require(condition, detail):
        if not condition:
            raise SystemExit("presentation flow proof: Attract schedule " + detail)

    def tick(state):
        memory, calls = bytearray(65536), []
        event, dirty, back, pending, selection = 0xD0, 0xE1, 0x90, 0x91, 0xE0
        for address, key in ((event, "event"), (dirty, "dirty"), (back, "back"),
                             (pending, "pending"), (selection, "selection")):
            memory[address] = state.get(key, 0)
        value = state.get("timer", 37)
        memory[timer_address:timer_address+2] = value.to_bytes(2, "big")
        memory[idle_address:idle_address+2] = (6).to_bytes(2, "big")
        pc, d, zero, carry = symbols["attract_tick_prepare"], 0, False, False

        def word(address):
            return int.from_bytes(memory[address:address+2], "big")

        def callback(target):
            nonlocal d
            if target == symbols["timer"]:
                calls.append("clock")
                d = (word(timer_address) + 1) & 0xFFFF
                memory[timer_address:timer_address+2] = d.to_bytes(2, "big")
            elif target == symbols["menu_runtime_dispatch"]:
                calls.append("menu")
                if memory[event] == 2:  # One normal Down at START.
                    memory[selection] += 1
                    memory[dirty] = 3
                bit = 1 << memory[back]
                if not memory[pending] and memory[dirty] & bit:
                    memory[dirty] &= ~bit
                    memory[pending] = 1
                    calls.append("paint")
            elif target == symbols["PRES_MAIN_PAGE23_RESUME"]:
                calls.append("logo")
            elif target == symbols["PRESENTATION_ATTRACT_OVERLAY"]:
                calls.append("actor")
            else:
                require(False, "unmodelled callback at $%04X" % target)

        for _ in range(64):
            if pc in (symbols["hold"], symbols["attract_next"]):
                if pc == symbols["attract_next"]:
                    calls.append("expire")
                break
            offset = pc - origin
            require(0 <= offset < len(module), "left the bound module")
            opcode = module[offset]
            if opcode == 0x0D:  # TST direct.
                zero = memory[module[offset+1]] == 0
                pc += 2
            elif opcode in (0x20, 0x24, 0x26, 0x27):  # BRA/BHS/BNE/BEQ.
                take = {0x20: True, 0x24: not carry, 0x26: not zero, 0x27: zero}[opcode]
                delta = int.from_bytes(module[offset+1:offset+2], "big", signed=True)
                pc += 2 + (delta if take else 0)
            elif opcode in (0x16, 0x17, 0x8D, 0xBD):  # LBRA/LBSR/BSR/JSR.
                width = 2 if opcode == 0x8D else 3
                operand = module[offset+1:offset+width]
                target = int.from_bytes(operand, "big", signed=opcode != 0xBD)
                if opcode != 0xBD:
                    target += pc + width
                if opcode == 0x16 and target != symbols["menu_runtime_dispatch"]:
                    pc = target
                    continue
                callback(target)
                if opcode == 0x16:  # Existing input path tail-returns.
                    break
                pc += width
            elif opcode == 0x93:  # SUBD direct, idle-origin calculation.
                amount = word(module[offset+1])
                carry, d = d < amount, (d - amount) & 0xFFFF
                zero, pc = d == 0, pc + 2
            elif module[offset:offset+2] == bytes((0x10, 0x83)):  # CMPD immediate.
                amount = int.from_bytes(module[offset+2:offset+4], "big")
                zero, carry, pc = d == amount, d < amount, pc + 4
            elif opcode == 0xCC:  # LDD immediate, resident continuation pointer.
                d = int.from_bytes(module[offset+1:offset+3], "big")
                zero, pc = d == 0, pc + 3
            elif opcode in (0xDD, 0xFD):  # STD direct or extended.
                width = 2 if opcode == 0xDD else 3
                address = int.from_bytes(module[offset+1:offset+width], "big")
                memory[address:address+2] = d.to_bytes(2, "big")
                pc += width
            elif opcode == 0x86:  # LDA immediate.
                d = (module[offset+1] << 8) | (d & 255)
                zero, pc = (d >> 8) == 0, pc + 2
            elif opcode == 0xB7:  # STA extended, restore PAR5.
                memory[int.from_bytes(module[offset+1:offset+3], "big")] = d >> 8
                pc += 3
            else:
                require(False, "unsupported opcode $%02X at $%04X" % (opcode, pc))
        else:
            require(False, "did not finish within 64 scheduling instructions")
        result = {key: memory[address] for address, key in
                  ((event, "event"), (dirty, "dirty"), (back, "back"),
                   (pending, "pending"), (selection, "selection"))}
        result["timer"] = word(timer_address)
        return result, calls

    # Start with either owner: one press, publication, idle replay, publication.
    for back in (0, 1):
        state, calls = tick(dict(event=2, back=back))
        require(state["selection"] == 1 and state["dirty"] == 1 << (1-back)
                and state["pending"] == 1, "fresh Down did not update one owner")
        state.update(event=0, back=1-back, pending=0)  # Completed publication.
        before = state["timer"]
        state, calls = tick(state)
        require(state["dirty"] == 0 and state["pending"] == 1
                and state["timer"] == before+1, "idle replay/clock incomplete")
        require(calls == ["clock", "menu", "paint"], "queued repaint did not yield")
        state.update(back=back, pending=0)
        state, calls = tick(state)
        require(calls == ["clock", "logo", "actor"], "clean tick lost animation")
    state, calls = tick(dict(dirty=2, back=1, pending=1))
    require(state["dirty"] == 2 and state["timer"] == 38
            and calls == ["clock", "menu"], "queued frame overwritten or clock stalled")
    state, calls = tick(dict(dirty=2, back=0))  # Dirty B is still FRONT.
    require(state["dirty"] == 2 and not state["pending"]
            and calls == ["clock", "menu", "logo", "actor"],
            "visible dirty owner blocked normal animation")
    state, calls = tick(dict(dirty=2, back=1, timer=limit+5))
    require(calls == ["clock", "expire"], "expired Attract painted outgoing screen")


def main() -> None:
    source = SOURCE.read_text(encoding="ascii")
    keybinding_source = (ROOT / "src/keybinding_runtime.s").read_text(encoding="ascii")
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
    if complete and any(fragment not in load_source for fragment in (
        "cmpa    #PRESENTATION_MAP_HIGH_SCORE",
        "beq     menu_load_discard_event",
        "menu_load_discard_event\n        clr     <$D0",
    )):
        raise SystemExit(
            "presentation flow proof: High Score loading does not consume early input"
        )
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
    start_flow = source[source.index("\nnormal_start\n"):source.index("\nnormal_hold\n")]
    for fragment in (
        "bita    #1", "sta     <PRES_CONTEXT", "PRESENTATION_MAP_LEVEL_START",
    ):
        if fragment not in start_flow:
            raise SystemExit(
                "presentation flow proof: free-start path is incomplete"
            )
    if "PRES_CREDITS" in source or "add_credit" in source:
        raise SystemExit(
            "presentation flow proof: obsolete cabinet-credit state remains"
        )
    attract_menu = source[source.index("\nattract_tick\n"):source.index("\nattract_tick_ready\n")]
    if "<$D0" not in attract_menu or "menu_runtime_dispatch" not in attract_menu:
        raise SystemExit(
            "presentation flow proof: live Attract menu dispatch is absent"
        )
    if complete:
        verify_attract_menu_schedule(MODULE.read_bytes(), symbols)
    menu_source = (ROOT / "src/shared_text_stage.inc").read_text(encoding="ascii")
    if "menu_attract_rows" not in menu_source or "menu_start_free" not in menu_source:
        raise SystemExit(
            "presentation flow proof: authored Attract menu is not wired"
        )
    key_local = keybinding_source[
        keybinding_source.index("\nks_local\n"):keybinding_source.index("\nks_done\n")
    ]
    screen_filter = re.search(
        r"\nks_menu\n[ \t]+lda[ \t]+\$A6\n"
        r"[ \t]+cmpa[ \t]+#PRESENTATION_MAP_ATTRACT\n[ \t]+l?beq[ \t]+ks_local\b\n"
        r"[ \t]+cmpa[ \t]+#PRESENTATION_MAP_HIGH_SCORE\n[ \t]+l?beq[ \t]+ks_local\b\n"
        r"[ \t]+cmpa[ \t]+#PRESENTATION_MAP_OPTIONS\n[ \t]+l?blo[ \t]+ks_done\b",
        keybinding_source,
    )
    if (
        'include "ladybug_presentation.inc"' not in keybinding_source or
        screen_filter is None or
        "sta $D0" not in key_local
    ):
        raise SystemExit(
            "presentation flow proof: menu screen allowlist or local event publication changed"
        )
    runtime_source = source[source.index("\npresentation_flow_tick\n"):]
    demo_branches = runtime_source.split("\ndemo_death_done\n")[1:]
    if len(demo_branches) < 2 or any(
        branch.split("\ndemo_return\n", 1)[0].count(
            "lda     #PRESENTATION_MAP_HIGH_SCORE\n        lbsr    start_screen"
        ) != 2
        for branch in demo_branches[:2]
    ):
        raise SystemExit(
            "presentation flow proof: demo completion does not enter high-score"
        )
    complete_demo_routes = demo_branches[0].split("\ndemo_return\n", 1)[0]
    if complete and len(re.findall(
        r"lbsr\s+install_highscore_runtime\s+"
        r"lda\s+#PRESENTATION_MAP_HIGH_SCORE\s+"
        r"lbsr\s+start_screen",
        complete_demo_routes,
    )) != 2:
        raise SystemExit(
            "presentation flow proof: Attract High Score routes do not install the shared painter"
        )
    normal_routes = source[
        source.index("\nnormal_tick\n"):source.index("\nnormal_stage\n")
    ]
    if complete and re.search(
        r"l?bsr\s+install_highscore_runtime\s+"
        r"lda\s+#PRESENTATION_MAP_GAME_OVER",
        normal_routes,
    ) is None:
        raise SystemExit(
            "presentation flow proof: post-game path does not retain the shared High Score painter"
        )
    painter = demo_source[
        demo_source.index("\nrender_high_score\n"):
        demo_source.index("\ndraw_high_score_screen\n")
    ]
    ranking_rows = demo_source[
        demo_source.index("\ndraw_high_score_screen\n"):
        demo_source.index("\ndraw_high_score_entry\n")
    ]
    if complete and (
        "bsr     draw_high_score_screen" not in painter or
        "init_scores" in painter or
        "PRES_HS_READY" not in ranking_rows or
        "highscore_default_record_data" not in ranking_rows
    ):
        raise SystemExit(
            "presentation flow proof: shared ranking painter writes or omits uninitialized Attract records"
        )
    runtime_attract = runtime_source[
        runtime_source.index("\nattract_tick\n"):
        runtime_source.index("\nattract_next\n")
    ]
    highscore_rotation = menu_source[
        menu_source.index("\nmenu_tick_not_keybinding\n"):
        menu_source.index("\nmenu_tick_not_high_score\n")
    ]
    ui_tick = source[
        source.index("\npresentation_ui_tick\n"):
        source.index("\nlevel_tick\n")
    ]
    if (
        "PRESENTATION_ROTATION_TICKS equ 558" not in source or
        "cmpd    #PRESENTATION_ROTATION_TICKS" not in runtime_attract or
        "lbsr    logo_tick" not in highscore_rotation or
        "cmpd    #PRESENTATION_ROTATION_TICKS" not in highscore_rotation or
        "lda     #PRESENTATION_MAP_ATTRACT" not in highscore_rotation or
        "lbra    menu_change" not in highscore_rotation
    ):
        raise SystemExit(
            "presentation flow proof: Attract/high-score rotation timing differs"
        )
    if complete and any(fragment not in ui_tick for fragment in (
        "lda     <PRES_SCREEN",
        "cmpa    #PRESENTATION_MAP_HIGH_SCORE",
        "lbeq    menu_runtime_dispatch",
    )):
        raise SystemExit(
            "presentation flow proof: visible High Score ticks bypass the shared timer owner"
        )
    if complete and any(fragment not in highscore_rotation for fragment in (
        "ldd     PRES_TIMER\n        bne     menu_tick_high_score_visible",
        "tst     FB_PENDING\n        bne     menu_tick_high_score_initial_pending",
        "bita    #16",
        "clr     MENU_EVENT",
        "lbsr    logo_tick",
        "cmpd    #PRESENTATION_ROTATION_TICKS",
        "tst     FB_PENDING\n        lbne    menu_hold",
    )):
        raise SystemExit(
            "presentation flow proof: shared High Score timer, input, or publication gate changed"
        )
    if source.index("clr     <PRES_ACTOR_FRAME") > source.index("\npft_ready\n"):
        raise SystemExit("presentation flow proof: actor frame is not initialized")
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
        "free-start flow, test auxiliary" if highscore_test else
        "Attract free-start menu, instruction choreography" if development else
        "Attract free-start menu, arcade-route demo"
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
