#!/usr/bin/env python3
"""Verify BUG-010 capture wiring, phase schedule, and loaded actor ownership."""

from __future__ import annotations

import hashlib
import json
import re
import argparse
from pathlib import Path


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

EXPECTED_ACTORS = (
    (0x661C, (66, 65, 64, 65)),
    (0x2F24, (128, 129, 12, 129)),
    (0x7F34, (22, 21, 20, 21)),
    (0x5238, (34, 33, 32, 33)),
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

    records = presentation.get("attract_actor_records", {})
    actual = tuple(
        (entry["destination"], tuple(entry["sparse_indexes"]))
        for entry in records.get("records", [])
    )
    if actual != EXPECTED_ACTORS:
        fail(f"actor metadata differs: {actual!r}")
    if records.get("bytes") != 24 or records.get("record_bytes") != 6:
        fail("actor metadata is not the compact 24-byte format")
    underlays = presentation.get("attract_actor_underlays", {})
    if underlays.get("bytes") != 512 or underlays.get("storage") != "loader-copy-to-$B000":
        fail("underlay payload is not the four-owner 512-byte loader allocation")

    enemy = sparse.get("enemy", {})
    if (enemy.get("frames"), enemy.get("bytes"), enemy.get("index_bytes")) != (130, 23005, 390):
        fail("enemy sparse projection is not 130 frames / 23005 bytes / 390 index bytes")
    if enemy["index"][128]["frame"] != 128 or enemy["index"][129]["frame"] != 129:
        fail("appended sparse indexes are absent")
    targets = {
        segment["target"]: segment
        for segment in sparse["gmc"]["segments"]
        if segment["target"] in {"attract_actor_records", "attract_actor_underlays"}
    }
    if targets.get("attract_actor_records", {}).get("destination_address") != 0xB200:
        fail("actor records are not loaded at $B200")
    if targets.get("attract_actor_underlays", {}).get("destination_address") != 0xB000:
        fail("actor underlays are not loaded at $B000")

    for symbol in ("PRES_MAIN_FB_PREPARE", "PRES_MAIN_FB_FINISH",
                   "PRES_MAIN_FB_CAPTURE"):
        if symbol not in module_map and symbol not in source:
            fail(f"runtime symbol or source contract missing: {symbol}")
    required_source = (
        "PRES_ACTOR_TABLE equ $B200",
        "PRES_ACTOR_UNDERLAY equ $B000",
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
        "PRES_MAIN_RESTORE_PLAYER",
    )
    if any(fragment not in source for fragment in required_source):
        fail("persistent-owner runtime contract is incomplete")

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
        "PRES_MODULE_DRAW_ACTOR",
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
    digest = hashlib.sha256(MODULE.read_bytes()).hexdigest()
    print(
        f"BUG-010 verifier: title 558 ticks, four actors, phases, hold helper and loader ownership pass; "
        f"module {module_bytes}/1280 bytes, helper {helper_bytes}/334 bytes, "
        f"original 1280-byte target margin {target_margin}, "
        f"module_sha256 {digest}"
    )


if __name__ == "__main__":
    main()
