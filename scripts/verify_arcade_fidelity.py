#!/usr/bin/env python3
"""Verify versioned MAME timing, turning, popup, and gate evidence."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

from build_screen import (BLACK, GREEN, PINK, PURPLE, compile_screen,
                          load_chars, pack_tile, recolor, rotate_ccw)


ROOT = Path(__file__).resolve().parents[1]


def load(name: str) -> dict[str, object]:
    return json.loads((ROOT / "assets/arcade" / name).read_text(encoding="utf-8"))


def one_player(document: dict[str, object], frame: int) -> dict[str, int]:
    matches = document["player"].get(str(frame), [])  # type: ignore[index,union-attr]
    assert len(matches) == 1, f"frame {frame}: expected one recognized Lady Bug"
    return matches[0]


def verify_speed() -> None:
    capture = load("gameplay_reference.json")
    for frame in range(600, 687):
        current = one_player(capture, frame)
        assert current["x"] == 89
        assert current["y"] == 807 - frame
        assert current["direction"] == 3
    assert one_player(capture, 687)["y"] == 121
    assert one_player(capture, 688)["y"] == 121


def verify_early_turn() -> None:
    capture = load("turn_reference.json")
    assert any(action == {"frame": 620, "control": "right", "pressed": True,
                          "field": "P1 Right"}
               for action in capture["inputs"])  # type: ignore[union-attr]
    assert one_player(capture, 654)["direction"] == 3
    assert one_player(capture, 655) == {
        "x": 89, "y": 153, "code": 0, "direction": 0
    }
    assert one_player(capture, 656)["x"] == 90


def verify_gate_capture() -> None:
    capture = load("gate_reference.json")
    changes = capture["background_changes"]  # type: ignore[assignment]
    assert "729" in changes and "730" in changes
    assert one_player(capture, 712)["y"] == 185
    assert one_player(capture, 745)["y"] == 153
    for frame in range(712, 746):
        one_player(capture, frame)


def verify_movement_snap() -> None:
    reference = load("movement_snap_reference.json")
    observations = reference["observations"]  # type: ignore[assignment]
    corner = observations["ordinary_corner"]
    assert corner["accepted_offset_pixels"] == 6
    assert corner["rejected_offset_pixels"] == 7
    assert corner["diagonal_correction_frames"] == [746, 747, 748, 749, 750, 751]
    gate = observations["gate_17"]
    assert gate["offset_pixels"] == 3
    assert gate["diagonal_correction_frames"] == [713, 714, 715]
    popup = observations["score_popup"]
    assert popup["hold_frames"] == 30
    assert popup["popup_last_frame"] - popup["popup_first_frame"] + 1 == 30


def verify_animation_captures() -> None:
    bonus = load("bonus_popup_reference.json")["observations"]  # type: ignore[index]
    intervals = bonus["popup_intervals"]
    assert len(intervals) == 4
    assert all(record["last_frame"] - record["first_frame"] + 1 == 30
               for record in intervals)
    multiplied = [record for record in intervals if record["multiplier"]]
    assert len(multiplied) == 2
    for record in multiplied:
        multiplier = record["multiplier"]
        assert [multiplier["xy"][axis] - record["score_xy"][axis]
                for axis in range(2)] == [7, 10]
    assert bonus["multiplier_composition"]["colour"] == "white"

    death = load("death_animation_reference.json")["observations"]  # type: ignore[index]
    sequence = death["shrink_and_wing_frames"]
    assert [record["sprite_code"] for record in sequence] == (
        list(range(57, 64)) + list(range(82, 88))
    )
    assert sequence[0]["last_frame"] - sequence[0]["first_frame"] + 1 == 29
    assert all(record["last_frame"] - record["first_frame"] + 1 == 5
               for record in sequence[1:])
    assert death["angel"]["stationary_frames"] == 30
    assert death["angel"]["moving_frames"] == 114
    assert death["blank_hold"]["duration_frames"] == 37
    assert death["durations"] == {
        "visible_death_art_frames": 233,
        "death_to_replacement_appearance_frames": 270,
        "death_to_replacement_start_position_frames": 407,
    }

    source = (ROOT / "src/main.s").read_text(encoding="utf-8")
    assert "leax    -800,x          ; score pixels occupy rows 0-5" in source
    assert "leax    803,x            ; right-centre multiplier" in source
    assert "cmpa    #89             ; first frame 29" in source
    assert "cmpa    #144            ; 30 stationary + 114 moving frames" in source
    assert "lda     #37" in source
    pickup_snapshot = source.index("sta     PICKUP_MULTIPLIER")
    pickup_score = source.index("lbsr    add_bonus_score")
    pickup_advance = source.index("sta     MULTIPLIER", pickup_score)
    assert pickup_snapshot < pickup_score < pickup_advance
    assert "draw_popup_multiplier\n        lda     PICKUP_MULTIPLIER" in source
    assert "andb    #$03            ; repeat the captured four-quarter motion cycle" in source
    assert "cmpx    #FB_VIRT+160" in source
    assert "sta     DEATH_FRAME\n        bra     dt_swing_hidden" in source
    compiler = (ROOT / "scripts/build_screen.py").read_text(encoding="utf-8")
    assert "(BLACK, WHITE, WHITE, WHITE)" in compiler


def verify_neutral_stop_contract() -> None:
    source = (ROOT / "src/main.s").read_text(encoding="utf-8")
    start = source.index("\nplayer_tick\n")
    end = source.index("pt_snap_advance\n", start)
    control = source[start:end]
    assert control.index("lda     JOY_DIR") < control.index("lda     TURN_SNAP")
    assert "cmpa    #DIR_NONE" in control
    assert "lbeq    pt_draw          ; neutral stops immediately" in control
    assert "sta     PLAYER_WANT" not in control[:control.index("pt_input_active\n")]


def verify_stage_timer_contract() -> None:
    source = (ROOT / "src/main.s").read_text(encoding="utf-8")
    timer = source[source.index("\nreload_box_timer\n"):
                   source.index("\n; Publish the reset timer state", source.index("\nreload_box_timer\n"))]
    assert "cmpa    #2" in timer
    assert "cmpa    #5" in timer
    assert "ldb     #9" in timer
    assert timer.count("subb    #3") == 2
    assert source.count("lbsr    reload_box_timer") == 3


def verify_hud_rows() -> None:
    source = (ROOT / "src/main.s").read_text(encoding="utf-8")
    hud = source[source.index("\ndraw_hud\n"):
                 source.index("\ndhu_mod10\n", source.index("\ndraw_hud\n"))]
    assert "lda     #6\n        sta     HUD_Y" in hud
    assert "lda     #11\n        sta     HUD_Y" in hud
    vegetable = source[source.index("\ndraw_vegetable_hud\n"):
                       source.index("\nvegetable_values\n")]
    assert "ldx     #$5C80" in vegetable
    assert "lda     #13\n        sta     HUD_Y" in vegetable

    document = ET.parse(ROOT / "tiled/coco-screen.tmx").getroot()
    layer = next(item for item in document.findall("layer")
                 if item.get("name") == "HUD Placeholders")
    gids = [int(value) for value in (layer.findtext("data") or "").split(",")
            if value.strip()]
    assert gids[9 * 40 + 33] == 0
    assert gids[10 * 40 + 33] == 497


def verify_player_restore_contract() -> None:
    source = (ROOT / "src/main.s").read_text(encoding="utf-8")
    tick_start = source.index("\nplayer_tick\n")
    tick_end = source.index("\n;==============================================================================\n; player_cell_offset", tick_start)
    tick = source[tick_start:tick_end]
    prologue = tick[:tick.index("pt_alive\n")]
    draw = tick[tick.index("\npt_draw\n"):tick.index("\npt_done\n")]
    expose = tick[tick.index("\nexpose_player_background\n"):]
    assert "restore_player" not in prologue
    assert "ora     #RF_PLAYER" in draw
    assert "restore_player" not in draw
    assert "inc     PLAYER_ERASED" in expose
    assert "restore_player" not in expose
    assert "PLAYER_MODULE_COMPOSE equ $080C" in source
    assert "pt_arrived\n        lbsr    expose_player_background" not in tick
    entity = source[source.index("check_entity_pickup\n"):source.index("; Replace the player")]
    assert "lbsr    expose_player_background" in entity


def verify_gate_tables() -> None:
    maze = load("maze.json")
    owner = maze["gate_owner"]
    dots = {tuple(dot) for dot in maze["dots"]}
    for gate in maze["gates"]:
        gate_id = gate["id"]
        cells = {tuple(cell) for cell in gate["rotation_cells"]}
        assert len(cells) == 5
        assert not cells & dots
        assert all(owner[y][x] == gate_id + 1 for x, y in cells)
    counts = [sum(cell == gate_id + 1 for row in owner for cell in row)
              for gate_id in range(20)]
    assert counts == [5] * 20


def blend(base: bytes, overlay: bytes) -> bytes:
    result = bytearray()
    for background, foreground in zip(base, overlay):
        bh, bl = background >> 4, background & 0x0F
        fh, fl = foreground >> 4, foreground & 0x0F
        result.append(((fh or bh) << 4) | (fl or bl))
    return bytes(result)


def verify_gate_graphics() -> None:
    screen, tiles, states, diagonals, backgrounds, neighbors, dot_tile = compile_screen(
        ROOT / "tiled/coco-screen.tmx",
        ROOT / "assets/arcade/maze.json",
        ROOT / "assets/arcade/chars.json",
        ROOT / "assets/arcade/sprites.json",
    )
    offsets = ((0, -2), (0, -1), (-2, 0), (-1, 0),
               (0, 0), (1, 0), (0, 1))
    rendered = {offset: tiles[tile_id]
                for offset, tile_id in zip(offsets, backgrounds[17])}
    for dx, dy, tile_id in states[1]:
        rendered[(dx, dy)] = blend(rendered[(dx, dy)], tiles[tile_id])

    characters = [rotate_ccw(tile) for tile in load_chars(
        ROOT / "assets/arcade/chars.json"
    )]
    # Final MAME frame-730 codes across gate 17's seven-cell visual union.
    for offset, code in zip(offsets, (59, 61, 50, 64, 62, 255, 63)):
        expected = pack_tile(recolor(characters[code],
                                     (BLACK, PINK, PURPLE, GREEN)))
        assert rendered[offset] == expected

    # MAME frame 729: gate 17's one-frame backslash intermediate.
    pivot_x, pivot_y = 15, 19
    intermediate = {
        (dx, dy): tiles[screen[(pivot_y + dy) * 40 + pivot_x + dx + 8]]
        for dx in range(-2, 2) for dy in range(-2, 2)
    }
    for offset, tile_id in zip(offsets, backgrounds[17]):
        intermediate[offset] = tiles[tile_id]
    for dx, dy, tile_id in diagonals[1]:
        intermediate[(dx, dy)] = tiles[tile_id]
    expected_codes = {
        (-2, 0): 50,
        (-1, -1): 65, (0, -1): 57, (1, -1): 229,
        (-1, 0): 64, (0, 0): 66, (1, 0): 67,
        (-1, 1): 229, (0, 1): 68, (1, 1): 69,
    }
    for offset, code in expected_codes.items():
        expected = (tiles[dot_tile] if code == 229 else
                    pack_tile(recolor(characters[code],
                                      (BLACK, PINK, PURPLE, GREEN))))
        assert intermediate[offset] == expected

    overlaps = {(gate_id, neighbor - 1)
                for gate_id, neighbor in enumerate(neighbors)
                if neighbor and gate_id < neighbor - 1}
    assert overlaps == {(2, 4), (5, 9), (10, 12), (11, 14)}
    assert [len(records) for records in diagonals] == [7, 7]
    assert 0 <= dot_tile < len(tiles)


def main() -> None:
    verify_speed()
    verify_early_turn()
    verify_gate_capture()
    verify_movement_snap()
    verify_animation_captures()
    verify_neutral_stop_contract()
    verify_stage_timer_contract()
    verify_hud_rows()
    verify_player_restore_contract()
    verify_gate_tables()
    verify_gate_graphics()
    print("arcade fidelity: movement, gates, 30-frame stacked popups, and 270-frame death transition verified")


if __name__ == "__main__":
    main()
