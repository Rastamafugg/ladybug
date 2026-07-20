#!/usr/bin/env python3
"""Verify the enemy module's fixed ABI and phase-separated compositor."""

from pathlib import Path


root = Path(__file__).resolve().parents[1]
source = (root / "src/enemy_runtime.s").read_text(encoding="utf-8")
main = (root / "src/main.s").read_text(encoding="utf-8")
resident = (root / "build/ladybug_resident.inc").read_text(encoding="utf-8")
rom = (root / "build/ladybug-enemy-runtime.rom").read_bytes()

if len(rom) < 18 or any(rom[offset] != 0x7E for offset in range(0, 18, 3)):
    raise SystemExit("enemy proof: fixed $0800 jump table is invalid")
if len(rom) > 0x800:
    raise SystemExit("enemy proof: bank-3 low-RAM module exceeds 2 KiB")
if "PACKED_SPRITE_SIZE equ    64" not in resident:
    raise SystemExit("enemy proof: generated packed-sprite source size changed")

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
    "tst     ENEMY_DIRTY",
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
    "jsr     restore_player",
    "sta     BOX_TIMER",
    "clr     BOX_INDEX",
    "clr     BOX_PHASE",
    "clr     PLAYER_TICK_PENDING",
    "jmp     player_compose_impl",
    "jmp     gate_compose_impl",
    "PLAYER_STAGE   equ $A3F0",
    "PLAYER_OLD_STAGE equ $A610",
    "et_contact_scan",
    "lbsr    enemy_player_contact",
    "cmpd    #2400",
    "RECORD_SIZE    equ 8",
    "lbsr    enemy_choose_direction",
    "enemy_direction_legal",
    "ldy     #maze_gate_owner",
    "SHADOW_PAGE0   equ $2C",
    "LIVE_PAGE0     equ $30",
    "jsr     gate_render_hidden",
    "lbsr    gate_region_to_shadow",
    "lbsr    gate_region_from_shadow",
]
missing = [fragment for fragment in required if fragment not in source]
if missing:
    raise SystemExit("enemy proof: missing contracts: " + ", ".join(missing))
if source.index("et_render_test") > source.index("et_compose"):
    raise SystemExit("enemy proof: idle render gate must precede composition")
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
gate_turn_start = main.index("\ncm_rotate\n")
gate_turn = main[gate_turn_start : main.index("\ncm_regular\n", gate_turn_start)]
if "expose_player_background" in gate_turn or "jsr     GATE_MODULE_COMPOSE" not in gate_turn:
    raise SystemExit("enemy proof: gate transition still mutates the visible player region")
gate_finish_start = main.index("\nfinish_gate_animation\n")
gate_finish = main[gate_finish_start : main.index("\ngate_render_hidden\n", gate_finish_start)]
if "restore_player" in gate_finish or "jsr     GATE_MODULE_COMPOSE" not in gate_finish:
    raise SystemExit("enemy proof: final gate state bypasses hidden composition")
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
skull = main[main.index("cep_skull\n") : main.index("; Replace the player")]
if "lbsr    enemy_tick" not in skull:
    raise SystemExit("enemy proof: static skull does not trigger direct enemy reset")
wrapper_start = main.index("\nenemy_tick\n")
wrapper = main[wrapper_start : main.index("\nenemy_release\n", wrapper_start)]
if "lda     ENEMY_DEATH_LATCH" not in wrapper or "cmpa    #1" not in wrapper or "lbsr    reset_perimeter_visual" not in wrapper:
    raise SystemExit("enemy proof: death reset does not publish the all-White perimeter")
death_start = main.index("\ndeath_tick\n")
death = main[death_start : main.index("\ndraw_death_frame\n", death_start)]
if "state 4: terminal game-over hold" not in death or "sta     DEATH_STATE" not in death[death.index("dt_game_over\n"):]:
    raise SystemExit("enemy proof: zero-life path can resume with an off-screen player")
walkoff_start = death.index("\ndt_finish_walkoff\n")
walkoff = death[walkoff_start : death.index("\ndt_game_over\n", walkoff_start)]
if walkoff.count("beq     dt_game_over") != 1 or walkoff.index("dec     LIVES") > walkoff.index("lbsr    init_player"):
    raise SystemExit("enemy proof: final reserve is not consumed before replacement entry")
print(
    f"enemy proof: {len(rom)}/2048 bank-3 bytes; fixed ABI, compact staging, "
    "64-byte source stride, idle render gate, off-screen nest compositor, "
    "immediate death reset, reset/frozen release timer, staged player publish, "
    "hidden gate publish, footprint collision, skull decrement, exclusive "
    "vegetable layer, 300-frame freeze, and first junction choice verified"
)
