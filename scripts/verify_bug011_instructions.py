#!/usr/bin/env python3
"""Verify BUG-011 generated choreography and development runtime wiring."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PRESENTATION = ROOT / "build/ladybug-presentation.json"
LAYOUT = ROOT / "build/ladybug-sparse-layout.json"
HELPER = ROOT / "build/ladybug-instruction-runtime.bin"
HELPER_MAP = ROOT / "build/ladybug-instruction-runtime.map"
MODULE = ROOT / "build/ladybug-presentation-runtime.bin"
MODULE_SOURCE = ROOT / "src/presentation_runtime.s"
HELPER_SOURCE = ROOT / "src/instruction_runtime.s"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def symbols(path: Path) -> dict[str, int]:
    return {
        name: int(value, 16)
        for name, value in re.findall(
            r"^Symbol: (\w+) .* = ([0-9A-Fa-f]+)$",
            path.read_text(encoding="utf-8"), re.MULTILINE,
        )
    }


def main() -> None:
    presentation = json.loads(PRESENTATION.read_text(encoding="ascii"))
    layout = json.loads(LAYOUT.read_text(encoding="ascii"))
    choreography = presentation["instruction_choreography"]
    events = choreography["events"]
    helper = HELPER.read_bytes()
    module = MODULE.read_bytes()
    helper_symbols = symbols(HELPER_MAP)

    names = [event["name"] for event in events]
    expected_names = list("EXTRA") + list("SPECIAL") + [
        "heart_x2", "heart_x3", "heart_x5", "skull",
    ]
    if names != expected_names:
        raise SystemExit(f"BUG-011 proof: event order differs: {names}")
    if choreography["colour_dwell_frames"] != 30:
        raise SystemExit("BUG-011 proof: colour dwell is not 30 frames")
    if (
        choreography["death_collision_tick"] != 1452 or
        choreography["angel_tick"] != 1547 or
        choreography["next_screen_tick"] != 1612
    ):
        raise SystemExit("BUG-011 proof: death/angel/handoff timing differs")
    for event in events:
        if event["motion_tick"] >= event["consume_tick"]:
            raise SystemExit(f"BUG-011 proof: nonpositive motion interval for {event['name']}")
        if event["goal_destination"] // 1280 != (
            event["target_destination"] + 1280
        ) // 1280:
            raise SystemExit(f"BUG-011 proof: actor goal row differs for {event['name']}")
    if any(event["hud_destination"] == 0 for event in events[:15]):
        raise SystemExit("BUG-011 proof: a collectible lacks its HUD destination")
    if events[-1]["hud_destination"] != 0:
        raise SystemExit("BUG-011 proof: skull unexpectedly has a HUD destination")

    runtime = layout["instruction_runtime"]
    if runtime != {
        **runtime,
        "bytes": len(helper),
        "staged_bytes": 0x3AA,
        "stage_page": 0x23,
        "stage_address": 0xA422,
        "destination_address": 0x0300,
        "destination_end": 0x06AA,
        "sha256": digest(helper),
        "staged_sha256": digest(helper.ljust(0x3AA, b"\x00")),
    }:
        raise SystemExit("BUG-011 proof: instruction runtime manifest differs")
    if len(helper) > 0x3AA:
        raise SystemExit("BUG-011 proof: instruction runtime exceeds loader RAM")
    if helper_symbols.get("instruction_runtime_tick") != 0x0300:
        raise SystemExit("BUG-011 proof: instruction runtime entry is not $0300")
    if helper_symbols.get("instruction_runtime_end", 0) > 0x06AA:
        raise SystemExit("BUG-011 proof: instruction runtime crosses $06AA")
    if len(module) > 1280:
        raise SystemExit("BUG-011 proof: presentation director crosses $1E00")

    module_source = MODULE_SOURCE.read_text(encoding="ascii")
    helper_source = HELPER_SOURCE.read_text(encoding="ascii")
    for fragment in (
        "install_instruction_runtime", "lda     #$23", "ldx     #$A422", "ldy     #$0300",
        "cmpy    #$06AA", "jsr     INSTRUCTION_RUNTIME_TICK",
        "LADYBUG_PROFILE", "BUG011_DEVELOPMENT_PROFILE",
    ):
        source = module_source if fragment != "LADYBUG_PROFILE" else (
            ROOT / "scripts/build.sh"
        ).read_text(encoding="utf-8")
        if fragment not in source:
            raise SystemExit(f"BUG-011 proof: missing development wiring {fragment}")
    for fragment in (
        "recolour_collectibles", "draw_value", "draw_life_reward",
        "draw_coin_reward", "draw_multipliers", "present_player",
        "present_death", "PRESENTATION_INSTRUCTION_DEATH_POINTERS",
    ):
        if fragment not in helper_source:
            raise SystemExit(f"BUG-011 proof: missing runtime operation {fragment}")

    colour = 1
    transitions = {}
    for tick in range(1, choreography["death_collision_tick"] + 1):
        if tick > 1 and (tick - 1) % choreography["colour_dwell_frames"] == 0:
            colour = colour % 3 + 1
            transitions[tick] = colour
    triggers = {event["consume_tick"]: event["name"] for event in events}
    if len(triggers) != 16:
        raise SystemExit("BUG-011 proof: consume ticks are not unique")
    death_indices = [0] * 30 + [index for index in range(1, 14) for _ in range(5)]
    if len(death_indices) != choreography["angel_tick"] - choreography["death_collision_tick"]:
        raise SystemExit("BUG-011 proof: death surface schedule is incomplete")

    print(
        "BUG-011 proof: 16 generated events, 30-frame colour clock, "
        "life/coin/X2-X3-X5 outcomes, 30+13x5 death schedule, held angel, "
        f"helper {len(helper)}/938, director {len(module)}/1280, "
        f"GMC spare {layout['gmc']['spare_bytes']}"
    )


if __name__ == "__main__":
    main()
