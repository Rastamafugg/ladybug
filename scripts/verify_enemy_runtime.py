#!/usr/bin/env python3
"""Verify the enemy module's fixed ABI and phase-separated compositor."""

from __future__ import annotations

from pathlib import Path
import re

from build_screen import compile_enemy_sprites


root = Path(__file__).resolve().parents[1]
source = (root / "src/enemy_runtime.s").read_text(encoding="utf-8")
main = (root / "src/main.s").read_text(encoding="utf-8")
bootstrap = (root / "src/gmc_bootstrap.s").read_text(encoding="utf-8")
build_script = (root / "scripts/build.sh").read_text(encoding="utf-8")
resident = (root / "build/ladybug_resident.inc").read_text(encoding="utf-8")
rom = (root / "build/ladybug-enemy-runtime.rom").read_bytes()
sprites = (root / "build/ladybug-enemy-sprites.bin").read_bytes()

if len(rom) < 27 or any(rom[offset] != 0x7E for offset in range(0, 27, 3)):
    raise SystemExit("enemy proof: fixed $0800 jump table is invalid")
if len(rom) > 0x1000:
    raise SystemExit("enemy proof: bank-3 low-RAM module exceeds 4 KiB")
if "PACKED_SPRITE_SIZE equ    64" not in resident:
    raise SystemExit("enemy proof: generated packed-sprite source size changed")
expected_sprites = b"".join(compile_enemy_sprites(root / "assets/arcade/sprites.json"))
if len(sprites) != 8 * 4 * 4 * 64 or sprites != expected_sprites:
    raise SystemExit("enemy proof: directional enemy atlas is not the generated 8192-byte payload")

labels = ["cez_copy_bg", "cez_active_loop", "draw_enemy_stage", "cez_commit"]
positions = [source.index(label) for label in labels]
if positions != sorted(positions):
    raise SystemExit("enemy proof: off-screen compositor phase order changed")

required = [
    "PLAYER_CELL_X  equ $0009",
    "DEATH_STATE    equ $004D",
    "ENEMY_ZONE_BG  equ $A490",
    "ENEMY_ZONE_STAGE equ $A590",
    "ENEMY_ZONE_FB  equ $4DEC",
    "SPRITE_SOURCE_SIZE equ 64",
    "tst     ENEMY_NEST_DIRTY",
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
    "stb     BOX_TIMER",
    "clr     BOX_INDEX",
    "clr     BOX_PHASE",
    "clr     PLAYER_TICK_PENDING",
    "jmp     player_compose_impl",
    "jmp     gate_compose_impl",
    "jmp     enemy_render_impl",
    "jmp     frame_render_impl",
    "PLAYER_STAGE   equ $A3F0",
    "PLAYER_OLD_STAGE equ $A610",
    "et_contact_scan",
    "lbsr    enemy_player_contact",
    "cmpa    #1",
    "RECORD_SIZE    equ 8",
    "lbsr    enemy_choose_direction",
    "enemy_direction_legal",
    "ldy     #maze_gate_owner",
    "leay    maze_nav-maze_gate_owner,y",
    "do not re-enter the den from cell (12,10)",
    "SHADOW_PAGE0   equ $2C",
    "LIVE_PAGE0     equ $30",
    "jsr     gate_render_hidden",
    "lbsr    gate_region_to_shadow",
    "lbsr    gate_region_from_shadow",
    "ENEMY_BG_BASE  equ $A690",
    "ENEMY_OLD_FB   equ $A890",
    "ENEMY_SPRITE_CACHE equ $1800",
    "ENEMY_CACHE_KEYS equ $1A80",
    "ENEMY_CACHE_FRAME_SIZE equ 128",
    "PLAYER_SPRITE_CACHE equ $1A85",
    "PLAYER_CACHE_KEY equ $1B05",
    "lbsr    enemy_sprite_cache",
    "lbsr    roam_prepare_shadow",
    "lbsr    roam_finish_shadow",
    "rsn_actor",
    "rfs_save_actor",
    "roam_copy_bg_to_fb",
    "roam_copy_fb_to_bg",
    "lbsr    blit_enemy_fb",
    "lbsr    blit_enemy_stage",
]
missing = [fragment for fragment in required if fragment not in source]
if missing:
    raise SystemExit("enemy proof: missing contracts: " + ", ".join(missing))
cache_symbols = {
    name: int(value[1:], 16) if value.startswith("$") else int(value)
    for name, value in re.findall(
        r"^(ENEMY_SPRITE_CACHE|ENEMY_CACHE_KEYS|ENEMY_CACHE_FRAME_SIZE) "
        r"equ +(\$[0-9A-F]+|[0-9]+)",
        source,
        re.MULTILINE,
    )
}
if cache_symbols["ENEMY_CACHE_KEYS"] != (
    cache_symbols["ENEMY_SPRITE_CACHE"] + 5 * cache_symbols["ENEMY_CACHE_FRAME_SIZE"]
):
    raise SystemExit("enemy proof: native cache slots overlap their keys")
if "PLAYER_CACHE_KEY equ $1B05" not in source or 0x1FFE - 0x1B06 + 1 < 1024:
    raise SystemExit("enemy proof: native caches leave less than 1 KiB for stack growth")
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
if render.index("tst     ENEMY_MOVE") < render.index("tst     ENEMY_NEST_DIRTY"):
    raise SystemExit("enemy proof: nest dirtiness must gate before movement-only rendering")
compose_tail = render[render.index("\net_compose\n"):]
if not compose_tail.index("tst     ENEMY_NEST_DIRTY") < compose_tail.index("lbsr    compose_enemy_zone"):
    raise SystemExit("enemy proof: movement-only frames do not bypass nest composition")
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
if "PLAYER_MODULE_CACHE equ $0812" not in main:
    raise SystemExit("enemy proof: player native-cache ABI entry is missing")
reset_start = source.index("\nreset_enemy_state\n")
reset = source[reset_start : source.index("\nreload_enemy_box_timer\n", reset_start)]
if "sta     PLAYER_CACHE_KEY" not in reset:
    raise SystemExit("enemy proof: player cache key is not invalidated before first draw")
if "cmpx    #$D800" not in bootstrap:
    raise SystemExit("enemy proof: bootstrap does not copy the approved 4 KiB bank-3 window")
if "cmpx    #$E800" not in bootstrap or "ldy     #$A000" not in bootstrap:
    raise SystemExit("enemy proof: bootstrap does not copy the bank-2 enemy sprite sets")
sprite_select = source[source.index("\nenemy_sprite_cache\n"):
                       source.index("\ndraw_vegetable_stage\n")]
for fragment in ("cmpa    #9", "anda    #7", "cmpa    #5",
                 "suba    ENEMY_WORK", "sta     GIME_PAR5",
                 "ENEMY_CACHE_KEYS", "esc_expand",
                 "ldb     #ENEMY_CACHE_FRAME_SIZE"):
    if fragment not in sprite_select:
        raise SystemExit("enemy proof: directional enemy cache selection changed")
expand = sprite_select[sprite_select.index("\nesc_expand\n"):
                       sprite_select.index("\nesc_cached\n")]
if expand.count("lda     a,u") != 2 or expand.count("sta     ,x+") != 2:
    raise SystemExit("enemy proof: cache miss does not expand two native bytes per packed byte")
if "jsr     blit_packed_sprite" in source[source.index("\ndraw_enemy_fb\n"):
                                         source.index("\ncompose_enemy_zone\n")]:
    raise SystemExit("enemy proof: framebuffer enemy still uses packed blitter")
native_stage = source[source.index("\ndraw_enemy_stage\n"):
                      source.index("\nenemy_sprite_cache\n")]
if "lbsr    blit_enemy_stage" not in native_stage or "blit_stage_sprite" in native_stage:
    raise SystemExit("enemy proof: nest enemy still uses packed stage blitter")
player_compose = source[source.index("\nplayer_compose_impl\n"):
                        source.index("\npci_done\n")]
if ("lbsr    player_frame_cache_impl" not in player_compose or
        "lbsr    blit_enemy_stage" not in player_compose or
        "blit_stage_sprite" in player_compose):
    raise SystemExit("enemy proof: hot player compositor still expands packed frames")
draw_player = main[main.index("\ndraw_player\n"):main.index("\nplayer_animation_tick\n")]
if ("jsr     PLAYER_MODULE_CACHE" not in draw_player or
        "lbsr    blit_native_sprite" not in draw_player or
        "blit_packed_sprite" in draw_player):
    raise SystemExit("enemy proof: resident player redraw still expands packed frames")
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
for fragment in ("clr     2,u", "clr     ,x", "sta     ENEMY_NEST_DIRTY",
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
        ("enemy_init_impl", "reset_enemy_state"),
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
    "lbsr    render_exposed_player",
    "jsr     erase_entity_footprints",
    "jsr     draw_maze_state_cell",
    "lbsr    enemy_render_impl",
    "lbsr    player_compose_impl",
    "lbsr    gate_compose_impl",
]
if [frame_renderer.index(fragment) for fragment in render_order] != sorted(
    frame_renderer.index(fragment) for fragment in render_order
):
    raise SystemExit("enemy proof: background, enemy, player, and gate layer order changed")
print(
    f"enemy proof: {len(rom)}/4096 bank-3 bytes; fixed ABI, state/render ownership, compact staging, "
    "64-byte source stride, idle render gate, off-screen nest compositor, "
    "immediate death reset, reset/frozen release timer, staged player publish, "
    "hidden gate publish, footprint collision, skull decrement, exclusive "
    "vegetable layer, 300-frame freeze, native enemy/player caches, nest-dirty separation, roaming phase separation, dynamic "
    "gate passage, den exit, roaming ownership, hidden skull cleanup, continuous "
    "colour cycling, randomized stage-one seed, nest-dot synchronization, and "
    "junction choice verified"
)
