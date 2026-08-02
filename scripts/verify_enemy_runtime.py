#!/usr/bin/env python3
"""Verify the enemy module's fixed ABI and phase-separated compositor."""

from __future__ import annotations

from pathlib import Path
import re

root = Path(__file__).resolve().parents[1]
source = (root / "src/enemy_runtime.s").read_text(encoding="utf-8")
main = (root / "src/main.s").read_text(encoding="utf-8")
bootstrap = (root / "src/gmc_bootstrap.s").read_text(encoding="utf-8")
build_script = (root / "scripts/build.sh").read_text(encoding="utf-8")
resident = (root / "build/ladybug_resident.inc").read_text(encoding="utf-8")
enemy_map = (root / "build/ladybug-enemy-runtime.map").read_text(encoding="utf-8")
rom = (root / "build/ladybug-enemy-runtime.rom").read_bytes()

if len(rom) < 36 or any(rom[offset] != 0x7E for offset in range(0, 36, 3)):
    raise SystemExit("enemy proof: fixed $0800 jump table is invalid")
if len(rom) > 0x1000:
    raise SystemExit("enemy proof: bank-3 low-RAM module exceeds 4 KiB")
if "PACKED_SPRITE_SIZE equ    64" not in resident:
    raise SystemExit("enemy proof: retained death/vegetable packed-source size changed")
if "player_sprites" in resident:
    raise SystemExit("enemy proof: packed player frames remain in the resident image")

labels = ["cez_copy_bg", "cez_active_loop", "draw_enemy_stage", "cez_commit"]
positions = [source.index(label) for label in labels]
if positions != sorted(positions):
    raise SystemExit("enemy proof: off-screen compositor phase order changed")

required = [
    "PERSISTENT_FB  equ 1",
    "PLAYER_CELL_X  equ $0009",
    "DEATH_STATE    equ $004D",
    "ENEMY_ZONE_BG  equ $A490",
    "ENEMY_ZONE_STAGE equ ACTOR_STAGE",
    "ENEMY_ZONE_FB  equ $4DEC",
    "SPRITE_SOURCE_SIZE equ 64",
    "anda    #ERF_NEST|ERF_NEST_ANIM",
    "lbsr    compose_enemy_zone",
    "tst     ENEMY_DEATH_LATCH",
    "lbsr    reset_enemy_state",
    "tst     DEATH_STATE",
    "lbra    et_begin_death",
    "clr     2,u",
    "dec     ENEMY_ACTIVE",
    "clr     VEG_STATE",
    "ldd     #300",
    "cmpa    #4",
    "sta     VEG_STATE",
    "clr     BOX_INDEX",
    "jmp     player_compose_impl",
    "jmp     gate_compose_impl",
    "jmp     player_draw_impl",
    "jmp     enemy_render_impl",
    "jmp     frame_render_impl",
    "jmp     framebuffer_init_impl",
    "jmp     framebuffer_irq_impl",
    "ACTOR_STAGE    equ $1800",
    "PLAYER_STAGE   equ ACTOR_STAGE",
    "PLAYER_OLD_STAGE equ ACTOR_STAGE+128",
    "et_contact_scan",
    "lbsr    enemy_player_contact",
    "cmpa    #1",
    "RECORD_SIZE    equ 8",
    "lbsr    enemy_choose_direction",
    "enemy_direction_legal",
    "ldy     #maze_gate_owner",
    "leay    maze_nav-maze_gate_owner,y",
    "do not re-enter the den from cell (12,10)",
    "FB_SCRATCH_PAGE0 equ $28",
    "FB_B_PAGE0     equ $2C",
    "LIVE_PAGE0     equ $30",
    "jsr     gate_render_hidden",
    "lbsr    gate_region_to_shadow",
    "lbsr    gate_region_from_shadow",
    "ENEMY_BG_BASE  equ $A690",
    "ENEMY_OLD_FB   equ $A890",
    "ENEMY_BG_RING  equ $A898",
    "FBM_ENEMY_RINGS equ 44",
    "SPARSE_ENEMY_INDEX_ADDR equ $0500",
    "SPARSE_PLAYER_INDEX_ADDR equ $0680",
    "lbsr    sparse_enemy_stream",
    "lbsr    sparse_player_stream",
    "lbsr    sparse_blit_fb",
    "lbsr    sparse_blit_stage",
    "lbsr    roam_prepare_shadow",
    "lbsr    roam_finish_shadow",
    "rsn_actor",
    "rfs_save_actor",
    "roam_copy_bg_to_fb",
    "roam_copy_fb_to_bg",
    "roam_update_background",
    "roam_capture_ring_row",
    "jsr     draw_all_gates",
    "jsr     draw_word_progress_hud",
]
missing = [fragment for fragment in required if fragment not in source]
if missing:
    raise SystemExit("enemy proof: missing contracts: " + ", ".join(missing))
for fragment in ("stb     BOX_TIMER", "clr     BOX_PHASE", "clr     PLAYER_TICK_PENDING"):
    if fragment not in source and fragment not in main:
        raise SystemExit("enemy proof: missing relocated contract: " + fragment)
for legacy in (
    "ENEMY_SPRITE_CACHE", "ENEMY_CACHE_KEYS", "PLAYER_SPRITE_CACHE",
    "PLAYER_CACHE_KEY", "enemy_sprite_cache", "player_frame_cache_impl",
    "blit_enemy_fb", "blit_enemy_stage",
):
    if legacy in source:
        raise SystemExit("enemy proof: obsolete native-cache path remains: " + legacy)
if 0x1FFE - 0x1900 + 1 < 1024:
    raise SystemExit("enemy proof: low-RAM actor stage leaves less than 1 KiB for stack growth")
if source.index("et_render_test") > source.index("et_compose"):
    raise SystemExit("enemy proof: idle render gate must precede composition")
tick_head = source[source.index("\nenemy_tick_impl\n"):
                   source.index("\net_snapshot_ready\n")]
if not (
    tick_head.index("bita    #ERF_DIRTY")
    < tick_head.index("bne     et_snapshot_ready")
    < tick_head.index("lbsr    roam_snapshot_old")
):
    raise SystemExit("enemy proof: repeated same-Vbord enemy logic can overwrite its old snapshot")
render_start = source.index("\net_render_test\n")
render = source[render_start : source.index("\nenemy_collect_impl\n", render_start)]
move_scan = source[source.index("\net_move_scan\n"):render_start]
if "sta     ENEMY_NEST_DIRTY" in move_scan:
    raise SystemExit("enemy proof: roaming movement still dirties the nest")
enemy_render = source[source.index("\nenemy_render_impl\n"):
                      source.index("\nframe_render_impl\n")]
for fragment in (
    "bita    #ERF_NEST_ANIM",
    "bita    #ERF_NEST",
    "lbsr    compose_enemy_zone",
):
    if fragment not in enemy_render:
        raise SystemExit("enemy proof: normalized nest intent missing: " + fragment)
nest_anim_test = enemy_render.index("bita    #ERF_NEST_ANIM")
nest_test = enemy_render.index("bita    #ERF_NEST", nest_anim_test + 1)
if not nest_anim_test < nest_test < enemy_render.index("lbsr    compose_enemy_zone"):
    raise SystemExit("enemy proof: movement-only frames do not bypass nest composition")
queue = source[source.index("\nframebuffer_queue_damage\n"):
               source.index("\nroam_mark_underlay\n")]
for fragment in (
    "lda     ENEMY_RENDER_FLAGS",
    "anda    #ERF_NEST|ERF_NEST_ANIM",
    "sta     8,u",
):
    if fragment not in queue:
        raise SystemExit("enemy proof: queued nest intent is not normalized: " + fragment)
if source.index("pci_commit_row") > source.index("pci_horizontal_strip"):
    raise SystemExit("enemy proof: final player rows must publish before old strips")
strip_start = source.index("\npci_horizontal_strip\n")
strip = source[strip_start : source.index("\npci_done\n", strip_start)]
if not strip.index("ldb     #16") < strip.index("tsta") < strip.index("bmi     pci_restore_right"):
    raise SystemExit("enemy proof: horizontal cleanup loses the signed player delta")
if main.index("lbsr    enemy_release") < main.index("perimeter_timer_tick"):
    raise SystemExit("enemy proof: release is not driven by the perimeter timer")
if "setdp   $00" not in main or "clra                    ; DP = $00" not in main:
    raise SystemExit("enemy proof: resident runtime direct page is not explicitly page zero")
if "GATE_MODULE_COMPOSE equ $080F" not in main:
    raise SystemExit("enemy proof: gate compositor ABI entry is missing")
if "PLAYER_MODULE_DRAW  equ $0812" not in main:
    raise SystemExit("enemy proof: player sparse-draw ABI entry is missing")
if "FB_MODULE_INIT      equ $081B" not in main:
    raise SystemExit("enemy proof: framebuffer ownership-init ABI entry is missing")
if "FB_MODULE_IRQ       equ $081E" not in main:
    raise SystemExit("enemy proof: framebuffer Vbord-commit ABI entry is missing")
reset_start = main.index("\nreset_enemy_state\n")
reset = main[reset_start : main.index("\nreload_enemy_box_timer\n", reset_start)]
for fragment in ("clr     ENEMY_OLD_VALID", "ldx     #ENEMY_OLD_FB", "std     6,x"):
    if fragment not in reset:
        raise SystemExit("enemy proof: cold enemy ownership is not initialized: " + fragment)
if "cmpx    #$D800" not in bootstrap:
    raise SystemExit("enemy proof: bootstrap does not copy the approved 4 KiB bank-3 window")
for fragment in (
    'include "ladybug-sparse-loader.inc"',
    "lda     #SPARSE_COPY_SEGMENT_COUNT",
    "copy_sparse_segment",
    "copy_sparse_bytes",
    "copy_enemy_sparse_index",
    "copy_player_sparse_index",
    "#SPARSE_ENEMY_INDEX_ADDR",
    "#SPARSE_PLAYER_INDEX_ADDR",
):
    if fragment not in bootstrap:
        raise SystemExit("enemy proof: sparse loader is incomplete: " + fragment)
if "copy_enemy_sprites" in bootstrap:
    raise SystemExit("enemy proof: bootstrap still copies the packed enemy atlas")
stage_clear = main[main.index("\ncheck_stage_clear\n"):
                   main.index("\ndraw_hud\n")]
for fragment in ("lda     DOTS_LEFT", "lda     BONUS_LEFT"):
    if fragment not in stage_clear:
        raise SystemExit("enemy proof: stage clear omits collectible: " + fragment)
if "VEG_STATE" in stage_clear:
    raise SystemExit("enemy proof: vegetable incorrectly gates stage clear")
respawn = main[main.index("\ndt_finish_blank\n"):
               main.index("\ndt_game_over\n")]
for fragment in ("clr     PLAYER_BG_VALID",
                 "clr     FB_META_A+FBM_PLAYER_VALID",
                 "clr     FB_META_B+FBM_PLAYER_VALID"):
    if fragment not in respawn:
        raise SystemExit("enemy proof: respawn retains player history: " + fragment)
nest = source[source.index("\ncompose_enemy_zone\n"):
              source.index("\nplayer_compose_impl\n")]
for fragment in ("cmpa    #2", "lda     ENEMY_ACTIVE",
                 "cmpa    #4", "beq     cez_commit"):
    if fragment not in nest:
        raise SystemExit("enemy proof: collected vegetable nest rule missing: " + fragment)
for fragment in (
    "ERF_NEST_ANIM  equ $10",
    "ENEMY_NEST_CACHE equ $AD80",
    "lbsr    compose_enemy_animation",
    "lbsr    build_enemy_nest_cache",
    "lbra    cez_commit_row",
    "ldu     #ENEMY_ZONE_STAGE",
    "lbsr    sparse_blit_stage",
):
    if fragment not in source:
        raise SystemExit("enemy proof: bounded nest animation path missing: " + fragment)
if not source.index("tst     ENEMY_NEST_DIRTY", source.index("et_animation_timer")) < source.index("ora     #ERF_NEST_ANIM"):
    raise SystemExit("enemy proof: structural nest dirtiness does not dominate animation")
for fragment in ("reset_enemy_state", "reload_enemy_box_timer"):
    if fragment not in main:
        raise SystemExit("enemy proof: cold reset helper was not moved to resident code: " + fragment)
sprite_select = source[source.index("\nenemy_frame_number\n"):
                       source.index("\nplayer_draw_impl\n")]
for fragment in ("cmpa    #9", "anda    #7", "cmpa    #5",
                 "suba    ENEMY_WORK", "ora     ENEMY_ANIM"):
    if fragment not in sprite_select:
        raise SystemExit("enemy proof: directional sparse-frame selection changed")
enemy_draw = source[source.index("\ndraw_enemy_fb\n"):
                    source.index("\ncompose_enemy_zone\n")]
for fragment in ("lbsr    enemy_frame_number", "lbsr    sparse_enemy_stream",
                 "lbsr    sparse_blit_fb"):
    if fragment not in enemy_draw:
        raise SystemExit("enemy proof: framebuffer enemy sparse path is incomplete")
stage_draw = source[source.index("\ndraw_enemy_stage\n"):
                    source.index("\nenemy_frame_number\n")]
if "lbsr    sparse_blit_stage" not in stage_draw:
    raise SystemExit("enemy proof: nest enemy does not use the sparse stage decoder")
player_compose = source[source.index("\nplayer_compose_impl\n"):
                        source.index("\npci_done\n")]
for fragment in ("lbsr    sparse_player_stream", "lbsr    sparse_blit_stage"):
    if fragment not in player_compose:
        raise SystemExit("enemy proof: staged player sparse path is incomplete")
draw_player = main[main.index("\ndraw_player\n"):main.index("\nplayer_animation_tick\n")]
if "jsr     PLAYER_MODULE_DRAW" not in draw_player or "blit_native_sprite" in main:
    raise SystemExit("enemy proof: resident player sparse draw ABI is incomplete")
sparse_resolve = source[source.index("\nsparse_enemy_stream\n"):
                        source.index("\nsparse_blit_fb\n")]
for fragment in (
    "SPARSE_ENEMY_INDEX_ADDR",
    "SPARSE_PLAYER_INDEX_ADDR",
    "ldb     #3",
    "ldu     1,u",
    "sta     GIME_PAR5",
):
    if fragment not in sparse_resolve:
        raise SystemExit("enemy proof: sparse index resolution is incomplete: " + fragment)
sparse_fb = source[source.index("\nsparse_blit_fb\n"):
                   source.index("\nsparse_blit_stage\n")]
for fragment in (
    "cmpb    #$FF",
    "sbf_extended",
    "leax    d,x",
    "leau    1,u",
    "bmi     sbf_partial",
    "cmpb    #5",
    "blo     sbf_opaque_small",
    "sbf_opaque_small",
    "sbf_opaque3",
    "sbf_opaque2",
    "sbf_opaque1",
    "sbf_opaque5",
    "sbf_opaque6",
    "sbf_opaque4",
    "ldd     ,u++",
    "std     ,x++",
    "sta     ,x+",
    "anda    ,x",
    "ora     ,u+",
    "decb",
):
    if fragment not in sparse_fb:
        raise SystemExit("enemy proof: framebuffer sparse decoder is incomplete: " + fragment)
if "stb     SPARSE_COUNT" in sparse_fb or "dec     SPARSE_COUNT" in sparse_fb:
    raise SystemExit("enemy proof: framebuffer sparse decoder still spills command counts")
small_dispatch = """sbf_opaque_small
        cmpb    #2
        beq     sbf_opaque2
        blo     sbf_opaque1
        bra     sbf_opaque3"""
if small_dispatch not in sparse_fb:
    raise SystemExit("enemy proof: short opaque dispatch no longer covers 1/2/3")
partial_start = sparse_fb.index("\nsbf_partial\n")
delta_start = sparse_fb.index("\nsbf_delta\n")
if partial_start > delta_start:
    raise SystemExit("enemy proof: partial decoder no longer falls through to delta parser")
partial_fallthrough = sparse_fb[partial_start:delta_start]
if "bra     sbf_delta" in partial_fallthrough:
    raise SystemExit("enemy proof: partial decoder restored its per-command parser branch")
specialized_opaque = {
    1: ("byte",),
    2: ("word",),
    3: ("word", "byte"),
    4: ("word", "word"),
    5: ("word", "word", "byte"),
    6: ("word", "word", "word"),
}
specialized_blocks = {
    5: """sbf_opaque5
        pulu    d,y
        std     ,x++
        sty     ,x++
sbf_opaque1
        lda     ,u+
        sta     ,x+
        bra     sbf_delta""",
    6: """sbf_opaque6
        pulu    d,y
        std     ,x++
        sty     ,x++
        ldd     ,u++
        std     ,x++
        bra     sbf_delta""",
    4: """sbf_opaque4
        pulu    d,y
        std     ,x++
        sty     ,x++
        bra     sbf_delta""",
}
for length, operations in specialized_opaque.items():
    copied = []
    cursor = 0
    for operation in operations:
        if operation == "word":
            copied.extend((cursor, cursor + 1))
            cursor += 2
        else:
            copied.append(cursor)
            cursor += 1
    if copied != list(range(length)):
        raise SystemExit(
            f"enemy proof: opaque-{length} word-copy model changed byte order"
        )
for length, block in specialized_blocks.items():
    if block not in sparse_fb:
        raise SystemExit(
            f"enemy proof: opaque-{length} shared-tail instruction order changed"
        )
sparse_stage = source[source.index("\nsparse_blit_stage\n"):
                      source.index("\ndraw_vegetable_stage\n")]
for fragment in (
    "cmpb    #$FF", "bitb    #$80", "subb    #152", "sbs_extended",
    "bmi     sbs_partial", "anda    ,x", "ora     ,u+", "decb",
    "ldb     ,u+", "abx"
):
    if fragment not in sparse_stage:
        raise SystemExit("enemy proof: stage sparse decoder is incomplete: " + fragment)
if "stb     SPARSE_COUNT" in sparse_stage or "dec     SPARSE_COUNT" in sparse_stage:
    raise SystemExit("enemy proof: stage sparse decoder still spills command counts")
decode_done = source[source.index("\nsparse_decode_done\n"):
                     source.index("\nsparse_blit_stage\n")]
if "lda     #$34" not in decode_done or "sta     GIME_PAR5" not in decode_done:
    raise SystemExit("enemy proof: sparse decoder does not restore game-state PAR5")
if "sparse_restore_page" in source:
    raise SystemExit("enemy proof: sparse wrappers retain a separate PAR5 restore call")
for obsolete in ("ladybug-enemy-sprites.bin", "ENEMY_SPRITES"):
    if obsolete in build_script:
        raise SystemExit("enemy proof: build still depends on the packed enemy atlas")
for fragment in ("SPARSE_BANK2", "SPARSE_BANK3", "sparse bank-3 runtime payload"):
    if fragment not in build_script:
        raise SystemExit("enemy proof: delivered GMC image does not use sparse banks")
direction_start = source.index("\nenemy_direction_legal\n")
direction = source[direction_start : source.index("\nenemy_entry_masks\n", direction_start)]
if "lda     ENTITY_Y\n        ldb     #24" not in direction:
    raise SystemExit("enemy proof: navigation offset does not use the target row")
if "leay    d,y\n        lda     ,y" not in direction:
    raise SystemExit("enemy proof: gate-owner lookup does not preserve the navigation offset")
dot_start = main.index("\nrefresh_enemy_zone_dot\n")
dot_sync = main[dot_start : main.index("\nred_done\n", dot_start)]
if "cmpa    #12" not in dot_sync or "cmpa    #10" not in dot_sync:
    raise SystemExit("enemy proof: nest background is not synchronized for dot (12,10)")
roam_order = ["rps_restore_loop", "rfs_save_loop", "rfs_draw_loop", "rfs_publish_loop"]
if [source.index(label) for label in roam_order] != sorted(source.index(label) for label in roam_order):
    raise SystemExit("enemy proof: roaming restore/save/draw/publish phase order changed")
prepare_start = source.index("\nroam_prepare_shadow\n")
prepare = source[prepare_start : source.index("\nroam_finish_shadow\n", prepare_start)]
if prepare.count("lbsr    roam_copy_bg_to_fb") != 1:
    raise SystemExit("enemy proof: old roaming backgrounds must be restored exactly once")
for start_label, end_label in (
    ("gate_region_to_shadow", "gate_region_from_shadow"),
    ("gate_region_from_shadow", "draw_enemy_stage"),
):
    start = source.index(f"\n{start_label}\n")
    region_copy = source[start : source.index(f"\n{end_label}\n", start)]
    if region_copy.count("lbsr    gate_map_shadow_window") != 1:
        raise SystemExit(
            f"enemy proof: {start_label} must map once before its page-segment loop"
        )
    row = region_copy.index(f"\n{'grts_row' if start_label.endswith('to_shadow') else 'grfs_row'}\n")
    if region_copy.index("lbsr    gate_map_shadow_window") > row:
        raise SystemExit(
            f"enemy proof: {start_label} remaps the shadow window per row"
        )
    for fragment in ("leau    d,u", "leau    -$2000,u", "sta     GIME_PAR5"):
        if fragment not in region_copy:
            raise SystemExit(
                f"enemy proof: {start_label} lacks page-segment step {fragment!r}"
            )
gate_turn_start = main.index("\ncm_rotate\n")
gate_turn = main[gate_turn_start : main.index("\ncm_regular\n", gate_turn_start)]
if "expose_player_background" in gate_turn or "lbsr    queue_gate_render" not in gate_turn:
    raise SystemExit("enemy proof: gate transition does not publish a render intent")
gate_finish_start = main.index("\nfinish_gate_animation\n")
gate_finish = main[gate_finish_start : main.index("\ngate_render_hidden\n", gate_finish_start)]
if "restore_player" in gate_finish or "lbsr    queue_gate_render" not in gate_finish:
    raise SystemExit("enemy proof: final gate state bypasses the render queue")
mainloop = main[main.index("mainloop\n") : main.index(";==============================================================================\n; Phase 5")]
player_order = [
    "lbsr    finish_gate_animation",
    "lbsr    enemy_tick",
    "tst     PLAYER_TICK_PENDING",
    "lbsr    player_tick",
    "lbsr    read_joystick",
    "lbsr    perimeter_timer_tick",
]
positions = [mainloop.index(fragment) for fragment in player_order]
if positions != sorted(positions):
    raise SystemExit("enemy proof: player update is not front-loaded at Vbord")
phase_tick = main[main.index("phase4_before_tick") : main.index(";==============================================================================\n; Phase 5")]
if "sta     PLAYER_TICK_PENDING" not in phase_tick or "lbsr    player_tick" in phase_tick:
    raise SystemExit("enemy proof: 30 Hz player update is not deferred to Vbord")
player_head = main[main.index("\nplayer_tick\n"):main.index("\npt_alive\n")]
player_snapshot_order = [
    "tst     PLAYER_ERASED",
    "bne     pt_snapshot_ready",
    "ldd     PLAYER_FB",
    "std     PLAYER_OLD_FB",
]
if [player_head.index(fragment) for fragment in player_snapshot_order] != sorted(
    player_head.index(fragment) for fragment in player_snapshot_order
):
    raise SystemExit("enemy proof: an earlier same-Vbord player exposure can be overwritten")
skull = main[main.index("cep_skull\n") : main.index("; Replace the player")]
if "lbsr    enemy_tick" not in skull:
    raise SystemExit("enemy proof: static skull does not trigger direct enemy reset")
enemy_skull_start = source.index("\nenemy_skull_test\n")
enemy_skull = source[enemy_skull_start : source.index("\nest_next\n", enemy_skull_start)]
for fragment in ("clr     2,u", "clr     ,x", "inc     ENEMY_NEST_DIRTY",
                 "sta     ENEMY_RENDER_FLAGS"):
    if fragment not in enemy_skull:
        raise SystemExit("enemy proof: skull cleanup does not publish state/render intents")
for fragment in ("restore_entity_footprint", "gate_region_to_shadow"):
    if fragment in enemy_skull:
        raise SystemExit("enemy proof: skull gameplay path still writes framebuffer state")
nest_start = source.index("\ncez_active_loop\n")
nest_actor = source[nest_start : source.index("\ncez_active_next\n", nest_start)]
if "tst     6,u" not in nest_actor or "cmpa    #10" in nest_actor:
    raise SystemExit("enemy proof: nest compositor does not use actor ownership state")
bonus_start = main.index("\nbonus_color_tick\n")
bonus_tick = main[bonus_start : main.index("\nbct_done\n", bonus_start)]
if "LIVES" in bonus_tick:
    raise SystemExit("enemy proof: collectible colour cycle still depends on reserve lives")
entry_seed = main[main.index("lbsr    init_joystick") : main.index("lbsr    init_entities")]
if "RNG_ENTROPY" not in entry_seed or "cmpd    #0" not in entry_seed:
    raise SystemExit("enemy proof: cold-start entity seed lacks nonzero RAM entropy")
if "-ram-init random" not in build_script:
    raise SystemExit("enemy proof: canonical XRoar run does not provide startup RAM entropy")
wrapper_start = main.index("\nenemy_tick\n")
wrapper = main[wrapper_start : main.index("\nenemy_release\n", wrapper_start)]
if "lda     ENEMY_DEATH_LATCH" not in wrapper or "cmpa    #1" not in wrapper or "lbsr    reset_perimeter_visual" not in wrapper:
    raise SystemExit("enemy proof: death reset does not publish the all-White perimeter")
death_start = main.index("\ndeath_tick\n")
death = main[death_start : main.index("\ndraw_death_frame\n", death_start)]
if "state 4: terminal game-over hold" not in death or "sta     DEATH_STATE" not in death[death.index("dt_game_over\n"):]:
    raise SystemExit("enemy proof: zero-life path can resume with an off-screen player")
death_snapshot = death[:death.index("\ndt_mark_render\n")]
if not (
    death_snapshot.index("tst     PLAYER_ERASED")
    < death_snapshot.index("bne     dt_mark_render")
    < death_snapshot.index("std     PLAYER_OLD_FB")
):
    raise SystemExit("enemy proof: death can overwrite an earlier same-Vbord player exposure")
respawn_start = death.index("\ndt_finish_blank\n")
respawn = death[respawn_start : death.index("\ndt_game_over\n", respawn_start)]
respawn_order = [
    "lda     LIVES",
    "beq     dt_game_over",
    "deca",
    "sta     LIVES",
    "lbsr    init_player",
    "ora     #RF_LIVES|RF_PLAYER",
]
if [respawn.index(fragment) for fragment in respawn_order] != sorted(
    respawn.index(fragment) for fragment in respawn_order
):
    raise SystemExit("enemy proof: final reserve is not consumed before replacement entry")

# Phase 2 ownership proof: gameplay/state routines may call other mutation
# routines, but they must not directly invoke any framebuffer-writing path.
framebuffer_call = re.compile(
    r"\b(?:lbsr|jsr)\s+("
    r"draw_\w+|restore_\w+|save_player|blit_\w+|"
    r"PLAYER_MODULE_COMPOSE|GATE_MODULE_COMPOSE|ENEMY_MODULE_RENDER"
    r")"
)


def assert_state_only(text: str, ranges: list[tuple[str, str]], owner: str) -> None:
    for start_label, end_label in ranges:
        start = text.index(f"\n{start_label}\n")
        end = text.index(f"\n{end_label}\n", start)
        match = framebuffer_call.search(text[start:end])
        if match:
            raise SystemExit(
                f"enemy proof: {owner} state routine {start_label} directly "
                f"calls framebuffer path {match.group(1)}"
            )


assert_state_only(
    main,
    [
        ("next_stage", "add_dot_score"),
        ("add_dot_score", "add_bonus_score"),
        ("add_bonus_score", "apply_letter_pickup"),
        ("apply_letter_pickup", "add_special_score"),
        ("add_special_score", "draw_multiplier_hud"),
        ("bonus_color_tick", "perimeter_timer_tick"),
        ("perimeter_timer_tick", "reload_box_timer"),
        ("reset_perimeter_visual", "perimeter_box_coordinates"),
        ("player_tick", "player_cell_offset"),
        ("cm_rotate", "cm_regular"),
        ("finish_gate_animation", "gate_render_hidden"),
        ("check_entity_pickup", "draw_score_popup"),
        ("death_tick", "draw_death_frame"),
        ("eat_dot", "refresh_enemy_zone_dot"),
    ],
    "resident",
)
assert_state_only(
    source,
    [
        ("enemy_init_impl", "enemy_release_impl"),
        ("enemy_release_impl", "enemy_tick_impl"),
        ("enemy_tick_impl", "enemy_render_impl"),
        ("enemy_collect_impl", "enemy_choose_direction"),
        ("enemy_skull_test", "est_next"),
    ],
    "bank-3",
)
mainloop = main[main.index("\nmainloop\n") : main.index("\ninit_game_state\n")]
if mainloop.count("lbsr    render_frame") != 1:
    raise SystemExit("enemy proof: mainloop must enter the framebuffer owner exactly once")
frame_renderer = source[source.index("\nframe_render_impl\n"):
                        source.index("\nenemy_collect_impl\n")]
for fragment in (
    "lbsr    enemy_render_impl",
    "lbsr    player_compose_impl",
    "lbsr    gate_compose_impl",
    "jsr     draw_hud",
    "jsr     draw_player",
):
    if fragment not in frame_renderer:
        raise SystemExit("enemy proof: central frame renderer is incomplete: " + fragment)
render_order = [
    "lbsr    frame_render_background",
    "lbsr    actor_closure_draw",
]
if [frame_renderer.index(fragment) for fragment in render_order] != sorted(
    frame_renderer.index(fragment) for fragment in render_order
):
    raise SystemExit("enemy proof: background must precede actor closure drawing")

frame_owner = source[source.index("\nframe_render_impl\n"):
                     source.index("\nframebuffer_project_damage\n")]
owner_order = [
    "lbsr    framebuffer_prepare_back",
    "lbsr    actor_closure_restore",
    "lbsr    framebuffer_queue_damage",
    "lbsr    framebuffer_project_damage",
    "lbsr    roam_mark_underlay",
    "bcs     fri_actor_closure",
    "lbsr    frame_render_background",
    "\nfri_actor_closure\n",
    "lbsr    actor_closure_draw",
    "lbsr    framebuffer_finish_back",
]
if [frame_owner.index(fragment) for fragment in owner_order] != sorted(
    frame_owner.index(fragment) for fragment in owner_order
):
    raise SystemExit("enemy proof: persistent closure does not bracket background projection")

if "frame_render_pass" in source:
    raise SystemExit("enemy proof: obsolete frame pass must not hide fast gate projection")

if "fbpd_generic\n        andcc   #$FE" not in source:
    raise SystemExit("enemy proof: generic damage projection must clear fast-path carry")

underlay = source[source.index("\nroam_mark_underlay\n"):
                  source.index("\nframe_render_background\n")]
if "pshs    cc" not in underlay or "puls    cc" not in underlay:
    raise SystemExit("enemy proof: underlay marking must preserve fast-path carry")

projection = source[source.index("\nframebuffer_project_damage\n"):
                    source.index("\nframebuffer_queue_damage\n")]
if "lbsr    frame_render_background" not in projection or "actor_closure_draw" in projection:
    raise SystemExit("enemy proof: damage replay is not background-only")

closure_restore = source[source.index("\nactor_closure_restore\n"):
                         source.index("\nactor_closure_draw\n")]
restore_order = [
    "jsr     restore_player",
    "sta     PLAYER_ERASED",
    "acr_enemy_loop",
    "lbsr    roam_copy_bg_to_fb",
]
if [closure_restore.index(fragment) for fragment in restore_order] != sorted(
    closure_restore.index(fragment) for fragment in restore_order
):
    raise SystemExit("enemy proof: player must be restored before all old enemies")

closure_draw = source[source.index("\nactor_closure_draw\n"):
                      source.index("\nframebuffer_init_impl\n")]
draw_order = [
    "acd_save_loop",
    "lbsr    roam_update_background",
    "acd_draw_loop",
    "lbsr    draw_enemy_fb",
    "tst     PICKUP_TIMER",
    "jsr     draw_score_popup",
    "tst     PLAYER_ERASED",
    "jsr     draw_player",
]
if [closure_draw.index(fragment) for fragment in draw_order] != sorted(
    closure_draw.index(fragment) for fragment in draw_order
):
    raise SystemExit("enemy proof: actor save/draw painter order changed")

ring_update = source[source.index("\nroam_update_background\n"):
                     source.index("\nroam_set_prepare_union\n")]
for fragment in (
    "cmpd    #1",
    "cmpd    #-1",
    "cmpd    #320",
    "cmpd    #-320",
    "rub_horizontal",
    "rub_column_first",
    "rub_column_second",
    "leau    -128,u",
    "rub_vertical",
    "roam_capture_ring_row",
    "clr     ,u",
):
    if fragment not in ring_update:
        raise SystemExit("enemy proof: circular save-under path is incomplete: " + fragment)
for legacy in ("roam_prepare_shadow", "roam_finish_shadow", "gate_region_to_shadow"):
    if re.search(rf"^Symbol: {legacy} ", enemy_map, re.MULTILINE):
        raise SystemExit("enemy proof: persistent image still contains legacy shadow code: " + legacy)

ring_restore = source[source.index("\nroam_copy_bg_to_fb\n"):
                      source.index("\nroam_copy_fb_to_bg\n")]
for fragment in (
    "bita    #$F0",
    "lbne    rcbtf_ring_setup",
    "ldy     #rcbtf_fast_table",
    "ldy     a,y",
    "jmp     ,y",
    "rcbtf_phase0",
    "rcbtf_phase1",
    "rcbtf_phase2",
    "rcbtf_phase3",
    "rcbtf_phase4",
    "rcbtf_phase5",
    "rcbtf_phase6",
    "rcbtf_phase7",
    "rcbtf_ring_setup",
):
    if fragment not in ring_restore:
        raise SystemExit("enemy proof: circular restore fast path is incomplete: " + fragment)

# Prove the packed row/column phase equations across wraps and direction turns.
world = [[row * 100 + col for col in range(80)] for row in range(80)]
backing = [[world[20 + row][20 + col] for col in range(8)] for row in range(16)]
row_phase = col_phase = 0


def segmented_column_capture(
        storage: list[list[int]], phase: int, slot: int, pixels: list[int]
) -> None:
    """Model the two contiguous physical segments used by rub_horizontal_fb."""
    first_count = 16 - phase
    for index, pixel in enumerate(pixels[:first_count]):
        storage[phase + index][slot] = pixel
    for index, pixel in enumerate(pixels[first_count:]):
        storage[index][slot] = pixel


for phase in range(16):
    for slot in range(8):
        model = [[-1] * 8 for _ in range(16)]
        pixels = [phase * 1000 + slot * 100 + row for row in range(16)]
        segmented_column_capture(model, phase, slot, pixels)
        for row, pixel in enumerate(pixels):
            if model[(phase + row) & 15][slot] != pixel:
                raise SystemExit(
                    "enemy proof: segmented horizontal capture diverged "
                    f"at row phase {phase}, slot {slot}"
                )
x_pos = y_pos = 20

def restore_ring() -> list[list[int]]:
    return [
        [
            backing[(row + row_phase) & 15][(col + col_phase) & 7]
            for col in range(8)
        ]
        for row in range(16)
    ]

def restore_horizontal_fast(phase: int) -> list[list[int]]:
    return [
        [backing[row][(col + phase) & 7] for col in range(8)]
        for row in range(16)
    ]

fast_phase_pairs = {
    0: ((0, 1), (2, 3), (4, 5), (6, 7)),
    1: ((1, 2), (3, 4), (5, 6), (7, 0)),
    2: ((2, 3), (4, 5), (6, 7), (0, 1)),
    3: ((3, 4), (5, 6), (7, 0), (1, 2)),
    4: ((4, 5), (6, 7), (0, 1), (2, 3)),
    5: ((5, 6), (7, 0), (1, 2), (3, 4)),
    6: ((6, 7), (0, 1), (2, 3), (4, 5)),
    7: ((7, 0), (1, 2), (3, 4), (5, 6)),
}
for phase in range(8):
    copied_columns = [
        column for pair in fast_phase_pairs[phase] for column in pair
    ]
    if copied_columns != [(phase + column) & 7 for column in range(8)]:
        raise SystemExit(
            f"enemy proof: circular restore word order diverged at column phase {phase}"
        )
    row_phase, col_phase = 0, phase
    if restore_horizontal_fast(phase) != restore_ring():
        raise SystemExit(
            f"enemy proof: circular restore fast path diverged at column phase {phase}"
        )
row_phase = col_phase = 0

def move_ring(dx: int, dy: int) -> None:
    global row_phase, col_phase, x_pos, y_pos
    old_row, old_col = row_phase, col_phase
    x_pos += dx
    y_pos += dy
    if dx == 1:
        col_phase = (old_col + 1) & 7
        for row in range(16):
            backing[(row + old_row) & 15][old_col] = world[y_pos + row][x_pos + 7]
    elif dx == -1:
        col_phase = (old_col - 1) & 7
        for row in range(16):
            backing[(row + old_row) & 15][col_phase] = world[y_pos + row][x_pos]
    elif dy == 2:
        row_phase = (old_row + 2) & 15
        for row in range(14, 16):
            physical_row = (old_row + row - 14) & 15
            for col in range(8):
                backing[physical_row][(col + old_col) & 7] = world[y_pos + row][x_pos + col]
    elif dy == -2:
        row_phase = (old_row - 2) & 15
        for row in range(2):
            physical_row = (row_phase + row) & 15
            for col in range(8):
                backing[physical_row][(col + old_col) & 7] = world[y_pos + row][x_pos + col]
    else:
        raise AssertionError("unsupported ring test delta")

for delta in (
    [(1, 0)] * 9
    + [(0, 2)] * 9
    + [(-1, 0)] * 11
    + [(0, -2)] * 10
    + [(1, 0), (0, 2), (-1, 0), (0, -2)] * 3
):
    move_ring(*delta)
    expected = [row[x_pos:x_pos + 8] for row in world[y_pos:y_pos + 16]]
    if restore_ring() != expected:
        raise SystemExit(f"enemy proof: circular save-under diverged after delta {delta}")

background = source[source.index("\nframe_render_background\n"):
                    source.index("\nrender_exposed_player\n")]
background_order = [
    "jsr     erase_entity_footprints",
    "jsr     draw_maze_state_cell",
    "lbsr    enemy_render_impl",
    "lbsr    gate_compose_impl",
]
if [background.index(fragment) for fragment in background_order] != sorted(
    background.index(fragment) for fragment in background_order
):
    raise SystemExit("enemy proof: persistent background layer order changed")

gate_compositor = source[source.index("\ngate_compose_impl\n"):
                         source.index("\ngate_compute_region\n")]
for fragment in ("jsr     restore_gate_diagonal_dots",
                 "jsr     draw_gate_transition"):
    if fragment not in gate_compositor:
        raise SystemExit("enemy proof: persistent gate path is not background-only: " + fragment)
for legacy in ("jsr     draw_gate_diagonal\n", "jsr     draw_gate\n",
               "jsr     draw_gate_entities\n", "jsr     draw_entities\n"):
    if legacy in gate_compositor:
        raise SystemExit("enemy proof: persistent gate path retains legacy composition: " + legacy)

gate_transition = main[
    main.index("\ndraw_gate_transition\n"):
    main.index("\nfinish_gate_animation\n")
]
for fragment in (
    "ldu     #GATE_TRANSITION_PAYLOAD",
    "lda     #GATE_TRANSITION_PAGE",
    "sta     PAR_EXEC+5",
    "leax    d,x",
    "abx",
    "sta     ,x+",
    "lda     #$34",
    "lbsr    draw_gate_entities",
):
    if fragment not in gate_transition:
        raise SystemExit("enemy proof: gate transition decoder is incomplete: " + fragment)
if gate_transition.index("sta     PAR_EXEC+5") > gate_transition.index(
    "ldu     #GATE_TRANSITION_PAYLOAD"
):
    raise SystemExit("enemy proof: gate stream index is read before page mapping")

damage_projection = source[source.index("\nframebuffer_project_damage\n"):
                           source.index("\nframebuffer_queue_damage\n")]
for fragment in (
    "cmpa    FBM_PENDING_INTENTS+9,u",
    "clr     FBM_PENDING_INTENTS+9,u",
    "cmpa    FBM_PENDING_INTENTS+11,u",
    "clr     FBM_PENDING_INTENTS+11,u",
):
    if fragment not in damage_projection:
        raise SystemExit("enemy proof: same-gate final replay coalescing is missing")

gate_entity_builder = main[
    main.index("\nbuild_gate_entity_lists\n"):
    main.index("\ndraw_gate_entities\n")
]
gate_entity_filter = main[
    main.index("\ndraw_gate_entities\n"):
    main.index("\ngate_cross_offsets\n")
]
for fragment in (
    "cmpa    GATE_START_X",
    "cmpa    GATE_END_X",
    "cmpa    GATE_START_Y",
    "cmpa    GATE_END_Y",
):
    if fragment not in gate_entity_builder:
        raise SystemExit("enemy proof: gate entity-footprint filter is incomplete")
for fragment in (
    "GATE_ENTITY_RECORD_SIZE",
    "ldx     ,y++",
    "lda     2,x",
    "ldu     ,y++",
    "lbsr    replay_gate_entity_overlay",
):
    if fragment not in gate_entity_filter:
        raise SystemExit("enemy proof: gate cached replay records are incomplete")

ownership_init = source[source.index("\nframebuffer_init_impl\n"):
                        source.index("\nframebuffer_prepare_back\n")]
for fragment in (
    "lda     #FB_B_PAGE0",
    "sta     GIME_PAR5",
    "ldy     #4096",
    "cmpx    #$A000",
    "lda     #$34",
    "ldx     #PLAYER_BG",
    "ldu     #PLAYER_BG_B",
    "ldx     #ENEMY_BG_BASE",
    "ldu     #ENEMY_BG_B",
    "ldx     #FB_META_A",
    "ldu     #FB_META_B",
    "sta     FB_INIT_STATE",
):
    if fragment not in ownership_init:
        raise SystemExit("enemy proof: A/B cold initialization is incomplete: " + fragment)
metadata_symbols = {
    name: int(value, 16)
    for name, value in re.findall(
        r"^(FB_META_A|FB_META_B|PLAYER_BG_B|ENEMY_BG_B) +equ \$([0-9A-F]+)",
        source,
        re.MULTILINE,
    )
}
if metadata_symbols != {
    "FB_META_A": 0xA900,
    "FB_META_B": 0xAA00,
    "PLAYER_BG_B": 0xAB00,
    "ENEMY_BG_B": 0xAB80,
}:
    raise SystemExit("enemy proof: phase-3 ownership/restoration allocation changed")
pointer_symbols = {
    "enemy": re.search(r"^PLAYER_BG_PTR +equ \$([0-9A-F]+)", source, re.MULTILINE),
    "resident": re.search(r"^PLAYER_BG_PTR +equ \$([0-9A-F]+)", main, re.MULTILINE),
}
if any(match is None or int(match.group(1), 16) != 0x00A2
       for match in pointer_symbols.values()):
    raise SystemExit("enemy proof: resident/bank-3 player save-under pointer ABI changed")
if not (
    frame_renderer.index("lbsr    framebuffer_prepare_back")
    < frame_renderer.index("lbcs    fri_abort")
    < frame_renderer.index("lbsr    framebuffer_finish_back")
):
    raise SystemExit("enemy proof: back-buffer ownership does not bracket rendering")
for fragment in (
    "framebuffer_begin_fallback",
    "framebuffer_finish_fallback",
    "ifeq    PERSISTENT_FB",
):
    if fragment not in source:
        raise SystemExit("enemy proof: build-time compatibility fallback is missing")
prepare = source[source.index("\nframebuffer_prepare_back\n"):
                 source.index("\nframebuffer_finish_back\n")]
for fragment in (
    "cmpa    FB_FRONT_ID",
    "inc     FB_WRITE_FRONT_FAULT",
    "orcc    #$01",
    "lbsr    gate_map_live",
    "FBM_PLAYER_FB,u",
    "ldx     #PLAYER_BG",
    "ldx     #PLAYER_BG_B",
    "stx     PLAYER_BG_PTR",
    "FBM_ENEMIES,u",
    "sta     ENEMY_OLD_VALID",
    "std     ENEMY_BG_RING",
    "std     ENEMY_BG_RING+2",
):
    if fragment not in prepare:
        raise SystemExit("enemy proof: back-buffer hydration is incomplete: " + fragment)
pointer_order = [
    "ldx     #PLAYER_BG",
    "tst     FB_BACK_ID",
    "ldx     #PLAYER_BG_B",
    "stx     PLAYER_BG_PTR",
]
if [prepare.index(fragment) for fragment in pointer_order] != sorted(
    prepare.index(fragment) for fragment in pointer_order
):
    raise SystemExit("enemy proof: back owner does not select its player save-under")
enemies = prepare.index("leau    FBM_ENEMIES,u")
if prepare.index("stx     PLAYER_BG_PTR") > enemies:
    raise SystemExit("enemy proof: player save-under selection follows enemy hydration")
finish = source[source.index("\nframebuffer_finish_back\n"):
                source.index("\nframebuffer_back_meta\n")]
for fragment in (
    "lbsr    framebuffer_capture_back",
    "orcc    #$10",
    "sta     FB_RENDER_PENDING",
    "clr     FB_RENDER_ACTIVE",
    "andcc   #$EF",
):
    if fragment not in finish:
        raise SystemExit("enemy proof: atomic ready publication is incomplete: " + fragment)
if "framebuffer_swap_player_bg" in source or "fbsp_loop" in source:
    raise SystemExit("enemy proof: physical player save-under swapping was restored")
player_compose = source[source.index("\nplayer_compose_impl\n"):
                        source.index("\ncopy_two_fb_rows\n")]
if player_compose.count("PLAYER_BG_PTR") != 2 or "#PLAYER_BG" in player_compose:
    raise SystemExit("enemy proof: player compositor bypasses the selected save-under")
save_player = main[main.index("\nsave_player\n"):main.index("\nrestore_player\n")]
restore_player = main[main.index("\nrestore_player\n"):main.index("\n;==============================================================================\n; draw_screen")]
if "ldu     PLAYER_BG_PTR" not in save_player or "#PLAYER_BG" in save_player:
    raise SystemExit("enemy proof: resident player save bypasses the selected save-under")
if "ldu     PLAYER_BG_PTR" not in restore_player or "#PLAYER_BG" in restore_player:
    raise SystemExit("enemy proof: resident player restore bypasses the selected save-under")
boot = main[main.index("entry_seed_ready\n"):main.index("; --- Un-blank")]
boot_order = ["std     PLAYER_BG_PTR", "lbsr    render_frame", "jsr     FB_MODULE_INIT"]
if [boot.index(fragment) for fragment in boot_order] != sorted(
    boot.index(fragment) for fragment in boot_order
):
    raise SystemExit("enemy proof: A/B convergence does not occur after the blanked full render")
game_init = main[main.index("\ninit_game_state\n"):main.index("\nnext_stage\n")]
if "clr     FB_INIT_STATE" not in game_init:
    raise SystemExit("enemy proof: cold render can observe random ownership-init state")
after_ownership_init = boot[boot.index("jsr     FB_MODULE_INIT"):]
if "clr     FB_INIT_STATE" in after_ownership_init:
    raise SystemExit("enemy proof: post-boot setup discards initialized A/B ownership")
irq = main[main.index("\nirq_handler\n"):main.index("\npar_table\n")]
if "jsr     FB_MODULE_IRQ" not in irq:
    raise SystemExit("enemy proof: resident IRQ does not delegate the Vbord commit")
irq_impl = source[source.index("\nframebuffer_irq_impl\n"):]
irq_order = [
    "lda     GIME_IRQEN",
    "tst     FB_RENDER_PENDING",
    "sta     GIME_VOFF1",
    "stb     FB_FRONT_ID",
    "sta     FB_BACK_ID",
    "clr     FB_RENDER_PENDING",
    "inc     FB_COMMIT_SEQ+1",
    "inc     FB_SIM_SEQ+1",
]
if [irq_impl.index(fragment) for fragment in irq_order] != sorted(
    irq_impl.index(fragment) for fragment in irq_order
):
    raise SystemExit("enemy proof: Vbord ownership commit order changed")
mapping = source[source.index("\ngate_map_shadow\n"):
                 source.index("\ngate_map_shadow_window\n")]
if "lda     #FB_SCRATCH_PAGE0" not in mapping:
    raise SystemExit("enemy proof: region compositor still aliases framebuffer B")
if "tst     FB_BACK_ID" not in mapping or "lda     #FB_B_PAGE0" not in mapping:
    raise SystemExit("enemy proof: PAR1-PAR4 do not select the current back owner")
damage = source[source.index("\nframebuffer_project_damage\n"):
                source.index("\nroam_mark_underlay\n")]
damage_order = [
    "lbsr    framebuffer_queue_damage",
    "lbsr    framebuffer_project_damage",
]
frame_head = source[source.index("\nframe_render_impl\n"):
                    source.index("\nframebuffer_project_damage\n")]
if [frame_head.index(fragment) for fragment in damage_order] != sorted(
    frame_head.index(fragment) for fragment in damage_order
):
    raise SystemExit("enemy proof: damage is not queued before back-buffer projection")
for fragment in (
    "FBM_PENDING_INTENTS equ 160",
    "tst     FBM_DAMAGE,u",
    "clr     PLAYER_ERASED",
    "ldd     PLAYER_CELL_X",
    "std     PLAYER_CELL_X",
    "sta     PLAYER_ERASED",
    "clr     FBM_DAMAGE,u",
    "bcs     fri_actor_closure",
    "ora     9,u",
    "ora     11,u",
    "inc     FBM_DAMAGE-FBM_PENDING_INTENTS,u",
):
    if fragment not in source:
        raise SystemExit("enemy proof: persistent damage ledger is incomplete: " + fragment)
queue = source[source.index("\nframebuffer_queue_damage\n"):
               source.index("\nroam_mark_underlay\n")]
for fragment in (
    "anda    #RF_HUD|RF_LIVES|RF_ENTITIES|RF_BOX|RF_DOT|RF_STAGE",
    "anda    #RF2_MULTIPLIER|RF2_LETTER|RF2_PERIM_RESET",
    "lda     ENEMY_RENDER_FLAGS",
    "anda    #ERF_NEST|ERF_NEST_ANIM",
    "sta     8,u",
    "ora     8,u",
):
    if fragment not in queue:
        raise SystemExit("enemy proof: transient actor state leaked into damage ledger")
print(
    f"enemy proof: {len(rom)}/4096 bank-3 bytes; fixed ABI, state/render ownership, A/B cold convergence, back-buffer hydration, persistent damage projection, Vbord commit handshake, compact staging, "
    "indexed sparse enemy/player streams, segmented loader, idle render gate, off-screen nest compositor, "
    "immediate death reset, reset/frozen release timer, staged player publish, "
    "hidden gate publish, footprint collision, skull decrement, exclusive "
    "vegetable layer, 300-frame freeze, nest-dirty separation, circular save-under, dynamic "
    "gate passage, den exit, roaming ownership, hidden skull cleanup, continuous "
    "colour cycling, randomized stage-one seed, nest-dot synchronization, and "
    "junction choice verified"
)
