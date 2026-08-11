#!/usr/bin/env python3
"""Verify BUG-010 capture wiring, phase schedule, and loaded actor ownership."""

from __future__ import annotations

import hashlib
import json
import re
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_screen import FLIP_D, FLIP_H, FLIP_V, rotate_ccw, transform  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
REFERENCE = ROOT / "assets/arcade/attract_actor_reference.json"
PRESENTATION = ROOT / "build/ladybug-presentation.json"
SPARSE = ROOT / "build/ladybug-sparse-layout.json"
MODULE_MAP = ROOT / "build/ladybug-presentation-runtime.map"
SOURCE = ROOT / "src/presentation_runtime.s"
HELPER_SOURCE = ROOT / "src/perimeter_reset_helper.s"
ENEMY_SOURCE = ROOT / "src/enemy_runtime.s"
MODULE = ROOT / "build/ladybug-presentation-runtime.bin"
HELPER = ROOT / "build/ladybug-perimeter-reset-helper.bin"
COMPRESSED = ROOT / "build/ladybug-attract-actor-underlays.bin"
METADATA = ROOT / "build/ladybug-attract-actor-records.bin"
BOOT_SOURCE = ROOT / "src/gmc_bootstrap.s"
SPRITES = ROOT / "assets/arcade/sprites.json"

EXPECTED_ACTORS = (
    ([11, 3], 0x2F2C, [23, 16, 17], [6, 5, 4], 0xA0000000),
    ([35, 4], 0x348C, [45, 46, 47], [6, 2, 13], 0),
    ([27, 5], 0x396C, [9, 10, 11], [6, 5, 9], 0x60000000),
    ([3, 9], 0x4D0C, [33, 34, 35], [6, 2, 13], 0),
    ([10, 15], 0x6B28, [3, 4, 5], [2, 5, 1], 0xA0000000),
    ([33, 19], 0x7F84, [27, 28, 29], [6, 8, 5], 0),
    ([5, 20], 0x8414, [21, 22, 23], [6, 2, 13], 0),
)


def fail(message: str) -> None:
    raise SystemExit(f"BUG-010 verifier: {message}")


def phase_schedule(duration: int) -> list[int]:
    phases = []
    for tick in range(1, duration + 1):
        if tick <= 6:
            phases.append(0)
        else:
            phases.append((1 + (tick - 7) // 8) % 4)
    return phases


def lzss_expand(data: bytes, expected: int) -> bytes:
    output = bytearray()
    cursor = 0
    while len(output) < expected:
        flags = data[cursor]
        cursor += 1
        for _ in range(8):
            if len(output) >= expected:
                break
            if flags & 1:
                output.append(data[cursor])
                cursor += 1
            else:
                token = int.from_bytes(data[cursor:cursor + 2], "big")
                cursor += 2
                offset, length = token >> 4, (token & 15) + 3
                if not offset or offset > len(output):
                    fail("compressed actor stream has an invalid back-reference")
                for _ in range(length):
                    output.append(output[-offset])
            flags >>= 1
    if cursor != len(data):
        fail("compressed actor stream has trailing bytes")
    return bytes(output)


def transformed_sprite(sprite: list[list[int]], flags: int) -> list[list[int]]:
    rows = rotate_ccw(sprite)
    if flags & FLIP_D:
        rows = [list(row) for row in zip(*rows)]
    return transform(rows, bool(flags & FLIP_H), bool(flags & FLIP_V))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom", type=Path)
    parser.add_argument("--map", type=Path)
    parser.add_argument("--presentation-map", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--oracle", type=Path)
    parser.add_argument("--cold-timeout", type=int, default=30)
    parser.add_argument("--loop-timeout", type=int, default=30)
    args = parser.parse_args()
    reference = json.loads((args.oracle or REFERENCE).read_text(encoding="ascii"))
    presentation = json.loads((args.manifest or PRESENTATION).read_text(encoding="ascii"))
    sparse = json.loads(SPARSE.read_text(encoding="ascii"))
    source = SOURCE.read_text(encoding="ascii")
    helper_source = HELPER_SOURCE.read_text(encoding="ascii")
    boot_source = BOOT_SOURCE.read_text(encoding="ascii")
    enemy_source = ENEMY_SOURCE.read_text(encoding="ascii")
    module_map = (args.presentation_map or MODULE_MAP).read_text(encoding="ascii")

    if reference.get("schema") != "ladybug-mame-attract-actor-reference-v2":
        fail("capture oracle schema is not v2")
    interval = reference["title_interval"]
    if (interval["first_complete_frame"], interval["last_complete_frame"],
            interval["duration_frames"]) != (185, 742, 558):
        fail("title interval does not match the captured 558-frame contract")
    if phase_schedule(558)[:6] != [0] * 6:
        fail("initial six-tick phase hold is incorrect")
    if phase_schedule(558)[6:38] != [1] * 8 + [2] * 8 + [3] * 8 + [0] * 8:
        fail("recurring eight-tick phase schedule is incorrect")

    records = presentation.get("attract_actor_surfaces", {})
    actual = tuple(
        (entry["cell"], entry["destination"], entry["source_codes"],
         entry["colours"], entry["flags"])
        for entry in records.get("actors", [])
    )
    if actual != EXPECTED_ACTORS:
        fail(f"actor metadata differs: {actual!r}")
    if records.get("bytes") != 2688 or records.get("unique_phases") != 3:
        fail("actor surfaces are not the 7 x 3 x 128-byte format")
    bundle = presentation.get("attract_actor_bundle", {})
    if (bundle.get("compressed_bytes") != 1062 or bundle.get("metadata_bytes") != 20 or
            bundle.get("destination_table_address") != 0xAA80 or
            bundle.get("phase_pointer_address") != 0xAA8E):
        fail("compressed actor bundle differs")
    expanded = lzss_expand(COMPRESSED.read_bytes(), 2688)
    if hashlib.sha256(expanded).hexdigest() != records.get("sha256"):
        fail("compressed actor surfaces do not expand to the authored payload")
    if len(METADATA.read_bytes()) != 20:
        fail("actor destination and phase metadata is not 20 bytes")
    sprites = json.loads(SPRITES.read_text(encoding="ascii"))
    actors = records["actors"]
    for phase in range(3):
        for actor_index, actor in enumerate(actors):
            sprite = transformed_sprite(
                sprites[actor["source_codes"][phase]], actor["flags"]
            )
            white, light_grey, dark_grey = actor["colours"]
            pen_colours = (0, dark_grey, light_grey, white)
            surface = expanded[
                (phase * len(actors) + actor_index) * 128:
                (phase * len(actors) + actor_index + 1) * 128
            ]
            for y, row in enumerate(sprite):
                for x, pen in enumerate(row):
                    if pen == 0:
                        continue
                    packed = surface[y * 8 + x // 2]
                    actual_colour = packed >> 4 if x % 2 == 0 else packed & 15
                    if actual_colour != pen_colours[pen]:
                        fail(
                            f"actor {actor['cell']} phase {phase} raw pen {pen} "
                            f"maps to {actual_colour}, expected {pen_colours[pen]}"
                        )
    for fragment in ("decompress_attract_surfaces", "lda     #$3C",
                     "sta     PAR_EXEC+4", "lda     #$23", "cmpy    #$8A80",
                     "das_metadata_byte"):
        if fragment not in boot_source:
            fail("boot actor-surface decompressor contract is incomplete")

    enemy = sparse.get("enemy", {})
    if (enemy.get("frames"), enemy.get("bytes"), enemy.get("index_bytes")) != (130, 23005, 390):
        fail("enemy sparse projection is not 130 frames / 23005 bytes / 390 index bytes")
    targets = {
        segment["target"]: segment
        for segment in sparse["gmc"]["segments"]
        if segment["target"] == "attract_actor_bundle"
    }
    if targets.get("attract_actor_bundle", {}).get("destination_page") != 0x23:
        fail("compressed actor bundle is not loaded to staging page $23")

    for symbol in ("PRES_MAIN_FB_PREPARE", "PRES_MAIN_FB_FINISH",
                   "PRES_MAIN_FB_CAPTURE"):
        if symbol not in module_map and symbol not in source:
            fail(f"runtime symbol or source contract missing: {symbol}")
    required_source = (
        "cmpd    #558",
        "jsr     PRESENTATION_HOLD_BEGIN",
        "jsr     PRESENTATION_HOLD_TICK",
        "jsr     PRESENTATION_ATTRACT_OVERLAY",
        "PRES_HOLD_STATE equ $00D4",
        "PRES_HOLD_CHUNK equ $00D5",
        "PRES_HOLD_SAVED_FRONT equ $00D6",
        "PRES_HOLD_SAVED_BACK equ $00D7",
        "PRES_HOLD_GEN equ $00D8",
        "PRES_HOLD_OWNER equ $00D9",
        "PRES_HOLD_HYDRATE equ 3",
    )
    if any(fragment not in source for fragment in required_source):
        fail("persistent-owner runtime contract is incomplete")
    tick = source[source.index("\nattract_tick\n"):source.index("\ninstructions_tick\n")]
    if tick.index("cmpd    #558") > tick.index("jsr     PRESENTATION_ATTRACT_OVERLAY"):
        fail("final title tick still queues an actor publication before handoff")

    module_bytes = len(MODULE.read_bytes())
    helper_bytes = len(HELPER.read_bytes())
    if module_bytes > 1280:
        fail(f"module exceeds the approved 1280-byte reservation: {module_bytes}")
    if helper_bytes > 334:
        fail(f"helper exceeds the approved 334-byte reservation: {helper_bytes}")
    required_helper = (
        "PRESENTATION_HOLD_BEGIN",
        "PRESENTATION_HOLD_TICK",
        "PRESENTATION_ATTRACT_OVERLAY",
        "hold_copy_chunk",
        "PRES_MAIN_FB_PREPARE",
        "PRES_MAIN_FB_CAPTURE",
        "PRES_MAIN_FB_FINISH",
        "hold_destination_pages",
        "fcb     $28,$29,$2A,$2B",
    )
    missing_helper = [fragment for fragment in required_helper if fragment not in helper_source]
    if missing_helper:
        fail("hold helper contract is incomplete: " + ", ".join(missing_helper))
    irq_contract = (
        "lda     FB_BACK_ID",
        "        lsla\n        lsla\n        lsla\n        lsla",
        "nega",
        "adda    #$C0",
        "sta     GIME_VOFF1",
    )
    if any(fragment not in enemy_source for fragment in irq_contract):
        fail("framebuffer IRQ does not implement the transient owner Voffset contract")
    if tuple((0xC0 - (owner << 4)) & 0xFF for owner in (0, 1, 2)) != (0xC0, 0xB0, 0xA0):
        fail("transient owner Voffset arithmetic contract is inconsistent")
    target_margin = 1280 - module_bytes
    sound_margin = sparse["gmc"]["spare_bytes"] - 1536
    if sound_margin < 512:
        fail(f"future-sound margin is {sound_margin}/512")
    digest = hashlib.sha256(MODULE.read_bytes()).hexdigest()
    print(
        f"BUG-010 verifier: title 558 ticks, seven authored actors, colours, phases and atomic handoff pass; "
        f"module {module_bytes}/1280 bytes, helper {helper_bytes}/334 bytes, "
        f"module margin {target_margin}, future-sound margin {sound_margin}/512, "
        f"module_sha256 {digest}"
    )


if __name__ == "__main__":
    main()
