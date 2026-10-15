#!/usr/bin/env python3
"""Bounded BUG-117/BUG-046 stage-preview observer; import has no side effects."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import socket
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[2]
SCHEDULED_OWNED = ROOT / "repro" / "bug117-scheduled-step-20261015"
STAGE_ENTRY_OWNED = ROOT / "repro" / "bug117-stage-repair-20261015" / "observer"
CAPSULE = ROOT / "repro" / "bug122-integration-20261014" / "capsule"
BUILD_DEFAULT = CAPSULE / "build"
ROM_SHA = "4b775f8f1b4b2a25a82b7c5d2850ee595e49f402e9ff8060634a0095a7c6dfd5"
RECEIPT_SHA = "5a2601d51a7a526bd228db7f46e0fa872a6e53e2c0197297038078f3694237fc"
REVISION = "3926a4ad73bae3665e619cf9c3154cb8d3d2ed60"
STAGE_ENTRY_BUILD = ROOT / "repro" / "bug117-stage-repair-20261015" / "capsule" / "build"
STAGE_ENTRY_ROM_SHA = "8d24086dab88be68178831927af85c7592f5c8c2932c8a6be2cf6551516a8a29"
STAGE_ENTRY_RECEIPT_SHA = "8e40c2fe5221d9194c40014a93264291a3805eacd02d3ed4e7674fcf789e264a"
STAGE_ENTRY_REVISION = "4ca288268620f67ee2c4bf3e706c4fd5ba81ffd3"
STAGE_ENTRY_MAIN_SHA = "88d9ef86a470488f81eeca51255b0ddb752e1d29f18685425ebb28b4868407a4"
STAGE_ENTRY_GUARD = bytes.fromhex("d618da06270a")
HIDDEN_OWNED = ROOT / "repro" / "bug046-hidden-owner-20261015"
HIDDEN_CAPSULE = ROOT / "repro" / "bug046-display-repair-20261015" / "capsule"
HIDDEN_BUILD = HIDDEN_CAPSULE / "build"
HIDDEN_ROM_SHA = "fddedcb5698dbdaa5a5b3b622cfc97bcb4c7d54a3eefdfc2756f1e755fbd0f9d"
HIDDEN_RECEIPT_SHA = "46d58ab7b1e83d2418b82e7e2adeb9cc7c9bbd9be12c553c20f33660236140ee"
HIDDEN_REVISION = "b94af065c4a94a0e1d0b1239831e46e21dd2ac77"
HIDDEN_HELPER_ORIGIN = 0xAC40
HIDDEN_HELPER_PAGE = 0x23
HIDDEN_TAIL_PC = 0xB190
HIDDEN_WORD_PC = 0xC41B
HIDDEN_RETURN_PC = 0x1B21
HIDDEN_SCANOUT_BASE = 0x50000
HIDDEN_HOLD_HELPER_ORIGIN = 0x06B2
HIDDEN_ORACLE_PATH = ROOT / "repro" / "bug122-heart-verification-20261014" / "pixel_oracle.py"
HIDDEN_ORACLE_SHA = "14b765a97f265d2053fe9e0fb67c32190265e14c9c1cf792966b8ebd4c417009"
HIDDEN_PANEL_MAP_SHA = "fdc8db8aecf3fabcd4799b66b680809da48d96d18606fdb9d542c08905c821fc"
HIDDEN_CHARS_SHA = "eba245a632ad24b1b836bc7d480ddf1b4d5393062851969cf811bf16c13bb7a7"
HIDDEN_BLUE_TABLE_SHA = "cb85c439bfb999efd1183f9bc4c98b0069594ff2fed905c94229ca18ba22530a"
HIDDEN_BASELINE_ROM_SHA = "85e2d503756eec66d70eb5c2180fd7e8ddfca7e12004c3a7d432e8132268b300"
HIDDEN_BASELINE_BUILD = ROOT / "repro" / "bug122-parent" / "baseline"
HIDDEN_BASELINE_CAPTURE = ROOT / "repro" / "bug117-scheduled-step-20261015" / "scheduled-neutral.json"
HIDDEN_BASELINE_CAPTURE_SHA = "de874554a3fbf83527c5e481e4e1a9c64d58222ccb7693d6d2acfd68fbb864cd"
PHASE_SECONDS = 45.0
STOP_SECONDS = 10.0
MAX_STOPS = 1000
READ_RESERVE = 0.13
MAX_READ = 2048
FIXTURE = ((0x003C, 0x49), (0x003D, 0x15), (0x0025, 0x01), (0x0033, 0x00))
KEY_COIN, KEY_ENTER = 5, 48
KEY_UP, KEY_DOWN = 0x2B, 0x2C
DIR_NORTH, DIR_SOUTH, DIR_NONE = 0x00, 0x02, 0xFF
PRES = 0x1900
ENEMY_ORIGIN = 0x0800
PRES_MODE, PRES_SCREEN, PRES_CONTEXT = 0xA5, 0xA6, 0xA7
PRES_HOLD_STATE, PRES_HOLD_SAVED_FRONT, PRES_HOLD_SAVED_BACK, PRES_HOLD_OWNER = 0xD4, 0xD6, 0xD7, 0xD9
STAGE_LETTER_VARIANTS = 0xC2
RF_STAGE = 0x40
FRONT, BACK, PENDING, COMMIT = 0x8F, 0x90, 0x91, 0x92
PLAYER_X, PLAYER_Y, PLAYER_FB, PLAYER_STEP = 0x09, 0x0A, 0x0B, 0x08
JOY_X, JOY_Y, JOY_DIR = 0x01, 0x04, 0x05
PLAYER_DIR, PLAYER_FACE = 0x06, 0x07
PLAYER_WANT, PLAYER_MANUAL = 0x0F, 0x18
STAGE, DOTS_LEFT, STAGE_PENDING = 0x24, 0x25, 0x26
SPECIAL, EXTRA, BONUS_LEFT, INITIAL_ENTRY, RENDER_FLAGS = 0x3C, 0x3D, 0x33, 0xA0, 0x7F
MAZE_STATE, PAR5 = 0xA000, 0xFFA5
ENTITY_COUNT, ENTITY_TABLE = 0x32, 0xA380
BOX_TIMER, BOX_INDEX = 0x4A, 0x4B
ENEMY_ACTIVE, ENEMY_RELEASED, ENEMY_ROAMING = 0x58, 0x59, 0x7E
ENEMY_TABLE, ENEMY_RECORD_SIZE, ENEMY_RECORDS = 0xA470, 8, 4
FRAMES, PLAYER_ERASED, PLAYER_BG_VALID = 0x02, 0x69, 0x6A
DEATH_STATE, PICKUP_TIMER, TURN_SNAP = 0x4D, 0x51, 0x56
PLAYER_TICK_PENDING, RENDER_FLAGS2 = 0x6B, 0x80
FB_SIM_SEQ, FB_RENDER_ACTIVE = 0x94, 0x98
ACTIVE_ORIGIN = 0x038F


class ProbeError(RuntimeError):
    pass


class PhaseDeadline(ProbeError):
    pass


class ProductReproduction(Exception):
    pass


class MissingCoverage(Exception):
    pass


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha(path: Path) -> str:
    return sha(path.read_bytes())


def inside(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def canonical_hash(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha(raw)


def pinned_build_identity(build: Path) -> tuple[str, str, str, str]:
    build = build.resolve()
    pins = {
        BUILD_DEFAULT.resolve(): (RECEIPT_SHA, ROM_SHA, REVISION, "known-broken"),
        STAGE_ENTRY_BUILD.resolve(): (STAGE_ENTRY_RECEIPT_SHA, STAGE_ENTRY_ROM_SHA,
                                      STAGE_ENTRY_REVISION, "stage-entry-repair-candidate"),
        HIDDEN_BUILD.resolve(): (HIDDEN_RECEIPT_SHA, HIDDEN_ROM_SHA,
                                 HIDDEN_REVISION, "hidden-owner-candidate"),
    }
    if build not in pins:
        raise ProbeError("build path is not one of the three parent-pinned immutable capsules")
    return pins[build]


def artifact_check(build: Path) -> dict[str, Any]:
    build = build.resolve()
    expected_receipt, expected_rom, expected_revision, identity = pinned_build_identity(build)
    capsule = build.parent
    receipt_path = build / "source-build-receipt.json"
    receipt_bytes = receipt_path.read_bytes()
    if sha(receipt_bytes) != expected_receipt:
        raise ProbeError("frozen source-build receipt hash mismatch")
    receipt = json.loads(receipt_bytes.decode("utf-8"))
    if (receipt.get("state"), receipt.get("profile"), receipt.get("revision")) != (
            "complete", "complete", expected_revision):
        raise ProbeError("frozen receipt profile/state/revision mismatch")
    inputs = receipt.get("inputs", {})
    generated = receipt.get("generated_inputs", {})
    artifacts = receipt.get("artifacts", {})
    if len(inputs) != 266 or len(generated) != 4:
        raise ProbeError("receipt must contain exactly 266 authored inputs and four generated inputs")
    if identity == "stage-entry-repair-candidate" and inputs.get("src/main.s") != STAGE_ENTRY_MAIN_SHA:
        raise ProbeError("stage-entry candidate main.s hash differs from the approved guard capsule")
    checked_inputs = 0
    for rel, expected in inputs.items():
        path = capsule / rel
        if not inside(path, capsule) or not path.is_file() or file_sha(path) != expected:
            raise ProbeError("authored-input receipt mismatch: " + str(rel))
        checked_inputs += 1
    checked_generated = 0
    for rel, expected in generated.items():
        # Receipt paths are relative to capsule root (usually `build/...`),
        # unlike final artifacts, which are relative to capsule/build.
        path = capsule / rel
        if not inside(path, capsule) or not path.is_file() or file_sha(path) != expected:
            raise ProbeError("generated-input receipt mismatch: " + str(rel))
        checked_generated += 1
    checked_artifacts = 0
    for rel, expected in artifacts.items():
        path = build / rel
        if not inside(path, build) or not path.is_file() or file_sha(path) != expected:
            raise ProbeError("artifact receipt mismatch: " + str(rel))
        checked_artifacts += 1
    if file_sha(build / "ladybug.rom") != expected_rom:
        raise ProbeError("pinned tested ROM mismatch")
    return {
        "build": str(build), "identity": identity, "revision": expected_revision,
        "receipt_sha256": expected_receipt, "rom_sha256": expected_rom,
        "authored_inputs_checked": checked_inputs,
        "generated_inputs_checked": checked_generated, "artifacts_checked": checked_artifacts,
        "profile": "complete", "state": "complete",
    }


def offline_source_site_check(build: Path) -> dict[str, Any]:
    qualifier = SiteQualifier(build)
    checks = []
    for filename, names, kind in (
            ("ladybug.map", ("mainloop", "draw_word_progress_hud", "player_tick", "pt_draw"), "main"),
            ("ladybug-enemy-runtime.map", ("fri_stage_background",), "enemy"),
            ("ladybug-presentation-runtime.map",
             ("presentation_flow_tick", "demo_run", "credit_tick", "normal_game", "level_tick"),
             "presentation")):
        symbols = symbols_for(build, filename)
        image = {"main": qualifier.main, "enemy": qualifier.enemy,
                 "presentation": qualifier.presentation}[kind]
        origin = {"main": 0xC000, "enemy": ENEMY_ORIGIN,
                  "presentation": PRES}[kind]
        for name in names:
            address = marker_addr(symbols, name)
            offset = address - origin
            if offset < 0 or offset + 16 > len(image):
                raise ProbeError("offline source marker leaves staged module: " + name)
            listing = qualifier.listings[kind]
            if any(address + i not in listing for i in range(16)):
                raise ProbeError("offline source listing lacks 16 bytes for " + name)
            source = bytes(listing[address + i] for i in range(16))
            staged = image[offset:offset + 16]
            if source != staged:
                raise ProbeError("offline source/staged marker bytes differ for " + name)
            checks.append({"name": name, "kind": kind, "address": hex(address),
                           "length": 16, "source_sha256": sha(source),
                           "staged_sha256": sha(staged)})
    release_pc = stage2_release_pc(build)
    presentation = qualifier.presentation
    offset = release_pc - PRES
    listing = qualifier.listings["presentation"]
    if offset < 0 or offset + 16 > len(presentation) or any(
            release_pc + i not in listing for i in range(16)):
        raise ProbeError("source listing lacks the derived stage-2 release site window")
    source = bytes(listing[release_pc + i] for i in range(16))
    staged = presentation[offset:offset + 16]
    if source != staged:
        raise ProbeError("source/staged release-site bytes differ")
    checks.append({"name": "stage2_release_clr_mode", "kind": "presentation",
                   "address": hex(release_pc), "length": 16,
                   "source_sha256": sha(source), "staged_sha256": sha(staged)})
    return {"checks": checks, "count": len(checks), "result": "pass"}


def stage2_release_pc(build: Path) -> int:
    """Derive the approved context-2 release PC from the pinned listing."""
    symbols = symbols_for(build, "ladybug-presentation-runtime.map")
    level_tick = marker_addr(symbols, "level_tick")
    listing = listing_byte_map(build / "ladybug-presentation-runtime.lst")
    sequence = bytes.fromhex("7f00a70fa54f39")
    candidates = [address for address in listing if level_tick < address <= level_tick + 0x40
                  and all(address + offset in listing for offset in range(len(sequence)))
                  and bytes_at(listing, address, len(sequence), "stage-2 release sequence") == sequence]
    if len(candidates) != 1:
        raise ProbeError("pinned listing does not uniquely derive the level_tick context-2 release")
    return candidates[0] + 3


def bytes_at(image: dict[int, int], address: int, length: int, label: str) -> bytes:
    if any(address + offset not in image for offset in range(length)):
        raise ProbeError("source listing lacks scheduled-step bytes for " + label)
    return bytes(image[address + offset] for offset in range(length))


def offline_scheduled_step_check(build: Path) -> dict[str, Any]:
    """Qualify the release, eligible caller, and first north-step source path."""
    main_map = symbols_for(build, "ladybug.map")
    pres_map = symbols_for(build, "ladybug-presentation-runtime.map")
    active_map = symbols_for(build, "ladybug-adaptive-active.map")
    main_listing = listing_byte_map(build / "ladybug.lst")
    pres_listing = listing_byte_map(build / "ladybug-presentation-runtime.lst")
    active_listing = listing_byte_map(build / "ladybug-adaptive-active.lst")

    release_pc = stage2_release_pc(build)
    release = bytes_at(pres_listing, release_pc, 4, "stage-2 context release")
    if (release != bytes.fromhex("0fa54f39") or
            bytes_at(pres_listing, release_pc - 3, 7, "context-before-mode release") !=
            bytes.fromhex("7f00a70fa54f39")):
        raise ProbeError("stage-2 release is not the pinned clear-context/clear-mode/return sequence")

    call_start, call_end = 0x04D5, 0x04E2
    caller = bytes_at(active_listing, call_start, call_end - call_start,
                      "pending-gated adaptive player caller")
    active_binary = (build / "ladybug-adaptive-active.bin").read_bytes()
    active_staged = active_binary[call_start - ACTIVE_ORIGIN:call_end - ACTIVE_ORIGIN]
    if (marker_addr(active_map, "atb_no_popup") != call_start or
            marker_addr(active_map, "player_tick") != marker_addr(main_map, "player_tick") or
            active_map.get("ADAPTIVE_RENDERING") != 1 or caller != bytes.fromhex("0d4d260c0d6b27080f6bbdcb6b") or
            active_staged != caller):
        raise ProbeError("adaptive source/staged caller does not consume pending before player_tick")

    expected_symbols = {"player_tick": 0xCB6B, "pt_at_center": 0xCC17,
                        "pt_choose_direction": 0xCC30, "pt_check_active": 0xCC4A,
                        "pt_advance": 0xCCA4, "pt_north": 0xCCB6,
                        "pt_store_fb": 0xCCC4, "pt_draw": 0xCCF4, "pt_done": 0xCD02,
                        "PLAYER_CELL_X": 0x09, "PLAYER_CELL_Y": 0x0A,
                        "PLAYER_DIR": 0x06, "PLAYER_FACE": 0x07,
                        "PLAYER_FB": 0x0B, "PLAYER_STEP": 0x08,
                        "PLAYER_MANUAL": 0x18, "PLAYER_WANT": 0x0F,
                        "PLAYER_TICK_PENDING": PLAYER_TICK_PENDING,
                        "FB_SIM_SEQ": FB_SIM_SEQ}
    if any(main_map.get(name) != address for name, address in expected_symbols.items()):
        raise ProbeError("scheduled-step symbols differ from the frozen source contract")
    route = {
        "north_delta_minus_320": bytes_at(main_listing, marker_addr(main_map, "pt_north"), 4,
                                           "north pixel delta").hex(),
        "store_fb_and_increment_step": bytes_at(main_listing, marker_addr(main_map, "pt_store_fb"), 6,
                                                 "store and increment step").hex(),
        "step_one_branches_to_draw": bytes_at(main_listing, marker_addr(main_map, "pt_store_fb") + 6, 3,
                                               "step-one draw branch").hex(),
        "draw_tail_returns_without_position_write": bytes_at(main_listing, marker_addr(main_map, "pt_draw"), 15,
                                                               "draw tail through return").hex(),
    }


def calls_to(listing: dict[int, int], target: int, origin: int, end: int) -> list[int]:
    """Return absolute JSR targets found in one receipt-pinned listing range."""
    return [address for address in range(origin, end - 2)
            if listing.get(address) == 0xBD and
            listing.get(address + 1) == (target >> 8) and
            listing.get(address + 2) == (target & 0xFF)]


def relative_calls_to(listing: dict[int, int], target: int, start: int, end: int) -> list[int]:
    """Return LBSR sites resolving to target inside one candidate listing range."""
    found = []
    for address in range(start, end - 2):
        if listing.get(address) != 0x17 or address + 2 not in listing:
            continue
        displacement = int.from_bytes(bytes((listing[address + 1], listing[address + 2])),
                                      "big", signed=True)
        if (address + 3 + displacement) & 0xFFFF == target:
            found.append(address)
    return found


def offline_stage_enemy_source_check(build: Path) -> dict[str, Any]:
    """Qualify stage reset, enemy record layout, and release cadence offline."""
    main_map = symbols_for(build, "ladybug.map")
    enemy_map = symbols_for(build, "ladybug-enemy-runtime.map")
    main_listing = listing_byte_map(build / "ladybug.lst")
    enemy_listing = listing_byte_map(build / "ladybug-enemy-runtime.lst")
    main_image = (build / "ladybug-runtime.rom").read_bytes()
    enemy_image = (build / "ladybug-enemy-runtime.rom").read_bytes()
    expected = {"ENEMY_TABLE": ENEMY_TABLE, "RECORD_SIZE": ENEMY_RECORD_SIZE,
                "ENEMY_ACTIVE": ENEMY_ACTIVE, "ENEMY_RELEASED": ENEMY_RELEASED,
                "BOX_TIMER": BOX_TIMER, "BOX_INDEX": BOX_INDEX}
    if any(enemy_map.get(name) != value for name, value in expected.items()):
        raise ProbeError("candidate enemy record or spawner symbols differ from the approved source layout")
    next_stage = marker_addr(main_map, "next_stage")
    init_enemy = marker_addr(main_map, "init_enemy")
    reset_enemy = marker_addr(main_map, "reset_enemy_state")
    reset_clear = marker_addr(main_map, "reset_enemy_clear")
    perimeter = marker_addr(main_map, "perimeter_timer_tick")
    ptt_done = marker_addr(main_map, "ptt_done")
    release = marker_addr(main_map, "enemy_release")
    enemy_init = marker_addr(enemy_map, "enemy_init_impl")
    enemy_contact = marker_addr(enemy_map, "enemy_player_contact")
    enemy_release_impl = marker_addr(enemy_map, "enemy_release_impl")
    stage_init_calls = relative_calls_to(main_listing, init_enemy, next_stage, next_stage + 0x80)
    reset_calls = relative_calls_to(enemy_listing, reset_enemy, enemy_init, enemy_init + 0x20)
    timer_release_calls = relative_calls_to(main_listing, release, perimeter, ptt_done)
    if len(stage_init_calls) != 1 or len(reset_calls) != 1 or len(timer_release_calls) != 1:
        raise ProbeError("candidate stage reset or timed-release call path is not unique")
    reset_tail = bytes_at(main_listing, reset_clear - 2, 8, "32-byte enemy table clear loop")
    reset_tail_staged = main_image[reset_clear - 2 - 0xC000:reset_clear + 6 - 0xC000]
    if reset_tail != bytes.fromhex("c6206f805a26fb39") or reset_tail != reset_tail_staged:
        raise ProbeError("candidate enemy reset no longer clears exactly four 8-byte records")
    init_bridge = bytes_at(main_listing, init_enemy, 3, "enemy init dispatch bridge")
    init_bridge_staged = main_image[init_enemy - 0xC000:init_enemy - 0xC000 + 3]
    if init_bridge != bytes.fromhex("7ea469") or init_bridge != init_bridge_staged:
        raise ProbeError("candidate next-stage enemy initializer dispatch changed")
    init_call = reset_calls[0]
    init_call_bytes = bytes_at(enemy_listing, init_call, 3, "enemy init reset call")
    enemy_init_staged = enemy_image[init_call - ENEMY_ORIGIN:init_call - ENEMY_ORIGIN + 3]
    if init_call_bytes != enemy_init_staged:
        raise ProbeError("enemy-init source/staged reset call differs")
    contact_window = bytes_at(enemy_listing, enemy_contact, 16, "enemy/player collision neighborhood")
    contact_staged = enemy_image[enemy_contact - ENEMY_ORIGIN:enemy_contact - ENEMY_ORIGIN + 16]
    release_window = bytes_at(enemy_listing, enemy_release_impl, 16, "enemy release record publication")
    release_staged = enemy_image[enemy_release_impl - ENEMY_ORIGIN:
                                 enemy_release_impl - ENEMY_ORIGIN + 16]
    if contact_window != contact_staged or release_window != release_staged:
        raise ProbeError("candidate enemy collision/release source bytes differ from staged image")
    timer_window = bytes_at(main_listing, perimeter, ptt_done - perimeter,
                            "perimeter timer and enemy-release threshold")
    timer_staged = main_image[perimeter - 0xC000:ptt_done - 0xC000]
    if timer_window != timer_staged:
        raise ProbeError("candidate perimeter timer source/staged bytes differ")
    return {"result": "pass", "record_table": hex(ENEMY_TABLE),
            "record_size": ENEMY_RECORD_SIZE, "record_count": ENEMY_RECORDS,
            "enemy_init_symbol": hex(enemy_init), "enemy_reset_call": hex(init_call),
            "stage_init_call": hex(stage_init_calls[0]),
            "reset_loop_source_staged_hex": reset_tail.hex(),
            "init_dispatch_source_staged_hex": init_bridge.hex(),
            "collision_source_staged_sha256": sha(contact_window),
            "release_source_staged_sha256": sha(release_window),
            "timer_source_staged_sha256": sha(timer_window),
            "timer_release_call": hex(timer_release_calls[0]),
            "source_interpretation": {
                "active_record": "record byte 0 is nonzero; cell x/y are offsets 4/5",
                "collision_neighborhood": "enemy_player_contact compares each cell-axis distance to 1",
                "released_counter": "monotonic per-stage release count at $0059",
                "release_cadence": "92 perimeter cells; stage 2 reloads a six-tick box interval",
                "collectibles_excluded": "ENTITY_TABLE at $A380 is not roaming ENEMY_TABLE at $A470"}}


def stage_guard_contract(manual: int, direction: int, entry_state: int = 0) -> dict[str, Any]:
    """Specification truth table only; this is not a 6809 instruction emulator."""
    suppress = bool(entry_state) or ((manual | direction) == 0)
    return {"manual": manual, "direction": direction, "entry_state": entry_state,
            "suppressed": suppress, "admitted": not suppress}


def validate_stage_guard(barrier: bytes, guard: bytes, request: int, done: int) -> dict[str, Any]:
    if barrier != bytes.fromhex("0da02610") or guard != STAGE_ENTRY_GUARD:
        raise ProbeError("guard bytes are absent, misplaced, or incorrect")
    relative = guard[5] if guard[5] < 0x80 else guard[5] - 0x100
    target = request + 10 + relative
    if target != done:
        raise ProbeError("guard BEQ target does not resolve to rj_done")
    return {"request_pc": hex(request), "guard_pc": hex(request + 4),
            "source_hex": guard.hex(), "branch_target": hex(target),
            "done_pc": hex(done)}


def stage_walk_pose(advance: int) -> dict[str, Any]:
    if not 0 <= advance <= 16:
        raise ProbeError("stage walk ordinal is outside the approved 0..16 path")
    return {"cell": [12, 22 - advance // 4],
            "fb": hex(0x89EC - 320 * advance), "step": advance % 4}


def stage_post_ready_pose(completed_draws: int, direction: int) -> dict[str, Any]:
    if not 0 <= completed_draws <= 3 or direction not in (DIR_NORTH, DIR_SOUTH):
        raise ProbeError("post-ready predecessor is outside the approved 0..3 draw path")
    delta = 320 * completed_draws * (1 if direction == DIR_SOUTH else -1)
    cell_y = 18 + completed_draws // 4 * (1 if direction == DIR_SOUTH else -1)
    return {"cell": [12, cell_y], "fb": hex(0x75EC + delta),
            "step": completed_draws % 4}


def validate_post_ready_predecessor(snapshot: dict[str, Any], completed_draws: int,
                                    direction: int) -> list[str]:
    try:
        expected = stage_post_ready_pose(completed_draws, direction)
    except ProbeError as exc:
        return [str(exc)]
    errors = []
    if snapshot.get("pose") != expected:
        errors.append("post-ready player-tick predecessor differs from the completed draw ordinal")
    input_state = snapshot.get("input", {})
    expected_player_dir = DIR_NONE if completed_draws == 0 else direction
    if (input_state.get("player_manual"), input_state.get("player_dir"),
            input_state.get("player_face"), input_state.get("player_want"),
            input_state.get("joy_dir")) != \
            (1, expected_player_dir, direction, direction, direction):
        errors.append("post-ready predecessor lost the sampled manual direction")
    return errors


def validate_stage_walk_entry(snapshot: dict[str, Any], advance: int, case: str) -> list[str]:
    """Check one observed pre-move record; return discrepancies for fail-closed callers."""
    if case not in ("neutral", "held") or not 0 <= advance < 16:
        return ["invalid approved case or movement ordinal"]
    errors = []
    if snapshot.get("pose") != stage_walk_pose(advance):
        errors.append("position/step does not match the source-derived movement ordinal")
    input_state = snapshot.get("input", {})
    expected_axes = (32, 64) if case == "held" else (32, 32)
    if (input_state.get("joy_x"), input_state.get("joy_y")) != expected_axes:
        errors.append("sampled raw axes do not match neutral/held fixture")
    if (input_state.get("joy_dir"), input_state.get("player_dir"),
            input_state.get("player_face"), input_state.get("player_want"),
            input_state.get("player_manual")) != (DIR_NONE, DIR_NORTH, DIR_NORTH,
                                                    DIR_NONE, 0):
        errors.append("automatic entry input publication invariant changed before center stop")
    return errors


def offline_stage_entry_check(build: Path) -> dict[str, Any]:
    """Qualify the approved candidate guard, adaptive callers, and fixed lane offline."""
    build = build.resolve()
    if build != STAGE_ENTRY_BUILD.resolve():
        raise ProbeError("stage-entry qualification is pinned to the approved combined candidate capsule")
    pins = artifact_check(build)
    broken_pins = artifact_check(BUILD_DEFAULT)
    candidate_map = symbols_for(build, "ladybug.map")
    candidate_listing = listing_byte_map(build / "ladybug.lst")
    candidate_main = (build / "ladybug-runtime.rom").read_bytes()
    broken_map = symbols_for(BUILD_DEFAULT, "ladybug.map")
    broken_listing = listing_byte_map(BUILD_DEFAULT / "ladybug.lst")
    broken_main = (BUILD_DEFAULT / "ladybug-runtime.rom").read_bytes()

    request = marker_addr(candidate_map, "rj_request")
    done = marker_addr(candidate_map, "rj_done")
    barrier = bytes_at(candidate_listing, request, 4, "initial-entry input barrier")
    guard = bytes_at(candidate_listing, request + 4, len(STAGE_ENTRY_GUARD), "six-byte stage guard")
    runtime_guard = candidate_main[request + 4 - 0xC000:request + 10 - 0xC000]
    branch_pc = request + 8
    relative = guard[5] if guard[5] < 0x80 else guard[5] - 0x100
    branch_target = branch_pc + 2 + relative
    guard_proof = validate_stage_guard(barrier, guard, request, done)
    if runtime_guard != guard or branch_target != done:
        raise ProbeError("candidate guard is not the exact post-initial-entry six-byte source/staged branch")
    broken_request = marker_addr(broken_map, "rj_request")
    broken_guard_window = bytes_at(broken_listing, broken_request + 4,
                                   len(STAGE_ENTRY_GUARD), "frozen broken guard window")
    if broken_guard_window == STAGE_ENTRY_GUARD:
        raise ProbeError("frozen broken capsule unexpectedly contains the candidate guard")

    # Bind the candidate listing to its staged image and the defective fixture
    # to its own immutable image. The unrelated BUG-046 difference in the
    # combined candidate is reported rather than attributed to BUG-117.
    candidate_inputs = json.loads((build / "source-build-receipt.json").read_text(encoding="utf-8"))["inputs"]
    broken_inputs = json.loads((BUILD_DEFAULT / "source-build-receipt.json").read_text(encoding="utf-8"))["inputs"]
    input_deltas = [{"path": name, "broken_sha256": broken_inputs.get(name),
                     "candidate_sha256": candidate_inputs.get(name)}
                    for name in sorted(set(candidate_inputs) | set(broken_inputs))
                    if candidate_inputs.get(name) != broken_inputs.get(name)]
    if sorted(item["path"] for item in input_deltas) != ["src/main.s", "src/shared_text_stage.inc"]:
        raise ProbeError("combined candidate authored-input delta changed from the reviewed BUG-046/117 capsules")

    main_symbols = ("player_tick", "pt_at_center", "pt_choose_direction", "pt_advance",
                    "pt_north", "pt_store_fb", "pt_cell_north", "pt_draw", "can_move",
                    "cm_entry_masks")
    main_symbol_addresses = {name: hex(marker_addr(candidate_map, name)) for name in main_symbols}
    center = marker_addr(candidate_map, "pt_at_center")
    center_source = bytes_at(candidate_listing, center, 25, "automatic center-stop branch")
    expected_center = bytes.fromhex("961826159609810c260f960a8112260986ff9706970f1600c4")
    if center_source != expected_center:
        raise ProbeError("candidate player center-stop path no longer clears direction/request without movement")
    entry_masks = bytes_at(candidate_listing, marker_addr(candidate_map, "cm_entry_masks"), 4,
                           "reciprocal movement entry masks")
    if entry_masks != bytes.fromhex("04080102"):
        raise ProbeError("candidate can_move reciprocal entry-mask order changed")
    staged_source_points = {}
    for name in main_symbols:
        address = marker_addr(candidate_map, name)
        count = 4 if name == "cm_entry_masks" else 16
        source = bytes_at(candidate_listing, address, count, "main source/staged marker " + name)
        staged = candidate_main[address - 0xC000:address - 0xC000 + count]
        if source != staged:
            raise ProbeError("candidate source/staged main bytes differ at " + name)
        staged_source_points[name] = {"address": hex(address), "length": count,
                                      "sha256": sha(source)}

    capsule = build.parent
    maze_path = capsule / "assets" / "arcade" / "maze.json"
    maze_doc = json.loads(maze_path.read_text(encoding="utf-8"))
    if tuple(maze_doc.get("dimensions", ())) != (24, 24):
        raise ProbeError("source maze dimensions differ from the approved 24x24 map")
    nav = bytes(value for row in maze_doc["maze_nav"] for value in row)
    gates = bytes(value for row in maze_doc["gate_owner"] for value in row)
    if len(nav) != 576 or len(gates) != 576:
        raise ProbeError("source maze nav/gate tables are not complete 24x24 arrays")
    nav_addr = marker_addr(candidate_map, "maze_nav")
    gate_addr = marker_addr(candidate_map, "maze_gate_owner")
    staged_nav = candidate_main[nav_addr - 0xC000:nav_addr - 0xC000 + 576]
    staged_gates = candidate_main[gate_addr - 0xC000:gate_addr - 0xC000 + 576]
    if staged_nav != nav or staged_gates != gates:
        raise ProbeError("authored maze nav/gate arrays differ from candidate staged tables")
    route_edges = []
    edges = [("automatic-north", (12, y), (12, y - 1), 0, 0x04)
             for y in range(22, 18, -1)]
    edges.extend([("post-ready-up", (12, 18), (12, 17), 0, 0x04),
                  ("held-down", (12, 18), (12, 19), 0x02, 0x01)])
    for label, origin, target, direction_bit, reciprocal_bit in edges:
        ox, oy = origin
        tx, ty = target
        origin_nav, target_nav = nav[oy * 24 + ox], nav[ty * 24 + tx]
        target_gate = gates[ty * 24 + tx]
        if not (origin_nav & (1 << direction_bit)) or not (target_nav & reciprocal_bit) or target_gate != 0:
            raise ProbeError("authored stage lane has an illegal or gated edge: " + label)
        route_edges.append({"label": label, "origin": list(origin), "target": list(target),
                            "origin_nav": origin_nav, "target_nav": target_nav,
                            "target_gate_owner": target_gate, "source_legal": True})

    active_map = symbols_for(build, "ladybug-adaptive-active.map")
    active_listing = listing_byte_map(build / "ladybug-adaptive-active.lst")
    active_staged = (build / "ladybug-adaptive-active.bin").read_bytes()
    read_site = calls_to(active_listing, marker_addr(candidate_map, "read_joystick"),
                         ACTIVE_ORIGIN, ACTIVE_ORIGIN + len(active_staged))
    tick_site = calls_to(active_listing, marker_addr(candidate_map, "player_tick"),
                         ACTIVE_ORIGIN, ACTIVE_ORIGIN + len(active_staged))
    atb = marker_addr(active_map, "atb_no_popup")
    if (len(read_site) != 1 or len(tick_site) != 1 or
            marker_addr(active_map, "player_tick") != marker_addr(candidate_map, "player_tick")):
        raise ProbeError("adaptive active module does not expose unique input and movement callsites")
    read_call, tick_call = read_site[0], tick_site[0]
    read_return, tick_return = read_call + 3, tick_call + 3
    caller_prefix = bytes_at(active_listing, atb, tick_return - atb,
                             "pending-gated adaptive player caller")
    expected_prefix = bytes.fromhex("0d4d260c0d6b27080f6bbdcb71")
    if (caller_prefix != expected_prefix or tick_call != atb + 10 or
            bytes_at(active_listing, read_call, 3, "adaptive input call") !=
            bytes.fromhex("bd" + f"{marker_addr(candidate_map, 'read_joystick'):04x}") or
            bytes_at(active_listing, tick_call, 3, "adaptive player call") !=
            bytes.fromhex("bd" + f"{marker_addr(candidate_map, 'player_tick'):04x}")):
        raise ProbeError("adaptive input/player caller bytes do not match candidate source ordering")
    for address, count, label in ((read_call, 3, "input call"),
                                  (tick_call, len(caller_prefix) - 10, "pending/player caller")):
        source = bytes_at(active_listing, address, count, label)
        staged = active_staged[address - ACTIVE_ORIGIN:address - ACTIVE_ORIGIN + count]
        if source != staged:
            raise ProbeError("active module source/staged caller bytes differ: " + label)

    contracts = [stage_guard_contract(0, DIR_NORTH),
                 stage_guard_contract(0, DIR_NONE),
                 stage_guard_contract(1, DIR_NORTH),
                 stage_guard_contract(0, DIR_NONE, entry_state=1)]
    if [item["admitted"] for item in contracts] != [False, True, True, False]:
        raise ProbeError("stage guard contract truth table failed")
    enemy_setup = offline_stage_enemy_source_check(build)
    return {
        "result": "pass", "pins": pins, "frozen_broken": broken_pins,
        "authored_input_deltas_vs_broken": input_deltas,
        "guard": {"request_pc": hex(request), "initial_entry_barrier_hex": barrier.hex(),
                  "guard_pc": hex(request + 4), "source_hex": guard.hex(),
                  "staged_hex": runtime_guard.hex(), "branch_target": hex(branch_target),
                  "done_pc": hex(done), "frozen_broken_window_hex": broken_guard_window.hex(),
                  "name_manual0_dir_none_admitted": contracts[1]["admitted"],
                  "ordinary_manual_north_admitted": contracts[2]["admitted"],
                  "automatic_manual0_dir_north_suppressed": not contracts[0]["admitted"],
                  "initial_entry_still_suppressed": not contracts[3]["admitted"],
                  "semantics_method": "specification truth table; no CPU interpreter"},
        "movement_source_points": staged_source_points,
        "enemy_reset_and_release_source": enemy_setup,
        "center_stop_source_hex": center_source.hex(),
        "reciprocal_entry_masks_hex": entry_masks.hex(),
        "adaptive_callers": {"input_call": hex(read_call), "input_return": hex(read_return),
                             "player_call": hex(tick_call), "player_return": hex(tick_return),
                             "pending_clear_before_player_tick": True,
                             "input_sample_order": "adaptive input call runs before pending-gated player_tick"},
        "authored_maze_sha256": file_sha(maze_path),
        "candidate_staged_nav_sha256": sha(staged_nav),
        "candidate_staged_gate_sha256": sha(staged_gates),
        "route_edges": route_edges,
        "walk_model": [{"advance": n, "cell": [12, 22 - n // 4],
                        "fb": hex(0x89EC - 320 * n), "step": n % 4}
                       for n in range(17)],
        "runtime_enemy_safety": "dynamic authoritative ENEMY_TABLE and release-state preflight at every observed player_tick; unsafe lane occupancy is missing coverage, no route search",
        "runtime_and_manual_claims": {"live_runtime_observed": False,
                                      "manual_name_replacement": "pending",
                                      "adaptive_input_order": "source/staged only",
                                      "nonadaptive_profile": "not covered by this keyboard/adaptive scenario"},
    }
    if route != {"north_delta_minus_320": "3089fec0",
                 "store_fb_and_increment_step": "9f0b0c089608",
                 "step_one_branches_to_draw": "810425",
                 "draw_tail_returns_without_position_write": "964d260a96512606967f8a01977f39"}:
        raise ProbeError("pinned player source no longer proves the approved first northward step")
    return {
        "result": "pass", "release": {"address": hex(release_pc),
            "source_and_staged_hex": release.hex(),
            "meaning": "context was cleared by the preceding source branch; mode clears here, then RTS"},
        "eligible_caller": {"address": hex(call_start), "length": len(caller),
            "source_hex": caller.hex(), "staged_hex": active_staged.hex(),
            "pending_consumed_before_call": True, "jsr_return_pc": hex(call_end)},
        "position_path": route,
        "expected_neutral_step": {"cell_before_after": [12, 22], "fb_before": "0x89ec",
            "fb_delta": -320, "fb_after": "0x88ac", "step_before": 0, "step_after": 1},
        "clock_comparison": "movement ordinal and source boundary; event_ticks are diagnostic metadata only",
    }


def offline_hidden_owner_check(candidate: Path = HIDDEN_BUILD,
                               broken: Path = BUILD_DEFAULT) -> dict[str, Any]:
    """Qualify the repaired helper tail against the immutable defective capsule."""
    candidate, broken = candidate.resolve(), broken.resolve()
    candidate_pins, broken_pins = artifact_check(candidate), artifact_check(broken)
    candidate_map = symbols_for(candidate, "ladybug-highscore-helper.map")
    broken_map = symbols_for(broken, "ladybug-highscore-helper.map")
    candidate_listing = listing_byte_map(candidate / "ladybug-highscore-helper.lst")
    broken_listing = listing_byte_map(broken / "ladybug-highscore-helper.lst")
    candidate_helper = (candidate / "ladybug-highscore-helper.bin").read_bytes()
    broken_helper = (broken / "ladybug-highscore-helper.bin").read_bytes()
    candidate_tail = bytes_at(candidate_listing, HIDDEN_TAIL_PC, 3, "candidate word-renderer tail")
    candidate_staged = candidate_helper[HIDDEN_TAIL_PC - HIDDEN_HELPER_ORIGIN:
                                         HIDDEN_TAIL_PC - HIDDEN_HELPER_ORIGIN + 3]
    broken_tail = bytes_at(broken_listing, HIDDEN_TAIL_PC, 3, "broken helper loop tail")
    broken_loop_return = bytes_at(broken_listing, HIDDEN_TAIL_PC + 2, 1, "broken helper return")
    if candidate_tail != bytes.fromhex("7ec41b") or candidate_staged != candidate_tail:
        raise ProbeError("candidate helper B190 does not source/staged-match JMP $C41B")
    if broken_tail != bytes.fromhex("26e439") or broken_loop_return != bytes.fromhex("39"):
        raise ProbeError("frozen broken helper does not retain its loop branch and direct RTS at B190")
    if (marker_addr(candidate_map, "stage_panel_finish") != 0xB12C or
            marker_addr(candidate_map, "stage_panel_letter_loop") != 0xB175 or
            marker_addr(candidate_map, "stage_panel_read_letters") != 0xB062 or
            marker_addr(broken_map, "stage_panel_letter_loop") != 0xB176 or
            marker_addr(candidate_map, "draw_word_progress_hud") != HIDDEN_WORD_PC):
        raise ProbeError("candidate/broken helper map symbols differ from pinned BUG-046 sites")

    main_map = symbols_for(candidate, "ladybug.map")
    main_listing = listing_byte_map(candidate / "ladybug.lst")
    main_image = (candidate / "ladybug-runtime.rom").read_bytes()
    word_source = bytes_at(main_listing, HIDDEN_WORD_PC, 16, "resident word-renderer entry")
    word_staged = main_image[HIDDEN_WORD_PC - 0xC000:HIDDEN_WORD_PC - 0xC000 + 16]
    if word_staged != word_source:
        raise ProbeError("candidate resident word-renderer listing and staged ROM differ")
    presentation_map = symbols_for(candidate, "ladybug-presentation-runtime.map")
    presentation_listing = listing_byte_map(candidate / "ladybug-presentation-runtime.lst")
    presentation_image = (candidate / "ladybug-presentation-runtime.bin").read_bytes()
    map_back = marker_addr(presentation_map, "map_back")
    map_back_source = bytes_at(presentation_listing, map_back, 31, "selected BACK map routine")
    map_back_staged = presentation_image[map_back - PRES:map_back - PRES + len(map_back_source)]
    expected_map_back = bytes.fromhex(
        "9690260486302002862cb7ffa14cb7ffa24cb7ffa34cb7ffa4863ab7ffa539"
    )
    if map_back != 0x1C2E or map_back_source != expected_map_back or map_back_staged != map_back_source:
        raise ProbeError("candidate map_back source/staged routine does not map BACK0/1 PAR1-PAR4 and PAR5=$3A")
    load_done = marker_addr(presentation_map, "load_done")
    caller = bytes_at(presentation_listing, load_done, 8, "page-$23 stage-panel caller")
    caller_staged = presentation_image[load_done - PRES:load_done - PRES + len(caller)]
    if (load_done != 0x1B19 or caller != bytes.fromhex("8623b7ffa5bdb080") or
            caller_staged != caller or load_done + len(caller) != HIDDEN_RETURN_PC):
        raise ProbeError("candidate caller does not map PAR5=$23, JSR $B080, and return at $1B21")
    return_site = bytes_at(presentation_listing, HIDDEN_RETURN_PC, 16,
                           "post-render helper return site")
    if presentation_image[HIDDEN_RETURN_PC - PRES:HIDDEN_RETURN_PC - PRES + 16] != return_site:
        raise ProbeError("candidate helper return source/staged bytes differ")
    layout = json.loads((candidate / "ladybug-sparse-layout.json").read_text(encoding="utf-8"))
    helper_layout = layout.get("highscore_helper", {})
    if (helper_layout.get("stage_page"), helper_layout.get("stage_address"),
            helper_layout.get("bytes")) != (HIDDEN_HELPER_PAGE, HIDDEN_HELPER_ORIGIN, len(candidate_helper)):
        raise ProbeError("candidate helper sparse placement is not page $23 at $AC40")

    hold_listing = listing_byte_map(candidate / "ladybug-perimeter-reset-helper.lst")
    if min(hold_listing) != HIDDEN_HOLD_HELPER_ORIGIN or \
            max(hold_listing) - HIDDEN_HOLD_HELPER_ORIGIN + 1 != len(
                (candidate / "ladybug-perimeter-reset-helper.bin").read_bytes()):
        raise ProbeError("compatibility hold helper source range differs from its staged origin")
    hold_stage = bytes_at(hold_listing, 0x0712, 16, "compatibility publication request")
    publish_stage = bytes_at(hold_listing, 0x0723, 24, "compatibility publication restore")
    hold_image = (candidate / "ladybug-perimeter-reset-helper.bin").read_bytes()
    hold_stage_image = hold_image[0x0712 - HIDDEN_HOLD_HELPER_ORIGIN:
                                  0x0712 - HIDDEN_HOLD_HELPER_ORIGIN + len(hold_stage)]
    publish_image = hold_image[0x0723 - HIDDEN_HOLD_HELPER_ORIGIN:
                               0x0723 - HIDDEN_HOLD_HELPER_ORIGIN + len(publish_stage)]
    if hold_stage != hold_stage_image or publish_stage != publish_image:
        raise ProbeError("compatibility hold helper listing and staged bytes differ")
    if bytes_at(hold_listing, 0x0712, 5, "owner2 request") != bytes.fromhex("1a10860297"):
        raise ProbeError("hold request no longer selects owner2 before publication")
    if bytes_at(hold_listing, 0x072D, 16, "hold owner restore") != \
            bytes.fromhex("96d6978f96d797900fd9860397d41cef"):
        raise ProbeError("hold publish no longer restores saved owners before HYDRATE")
    return {
        "result": "pass", "candidate": candidate_pins, "frozen_broken": broken_pins,
        "candidate_hidden_tail": {"pc": hex(HIDDEN_TAIL_PC), "listing_hex": candidate_tail.hex(),
                                   "staged_hex": candidate_staged.hex(),
                                   "meaning": "JMP $C41B enters resident word renderer"},
        "broken_hidden_tail": {"pc": hex(HIDDEN_TAIL_PC), "listing_hex": broken_tail.hex(),
                                "meaning": "BNE loop followed by RTS; no resident word-renderer tail call"},
        "caller": {"load_done": hex(load_done), "source_staged_hex": caller.hex(),
                   "return_pc": hex(HIDDEN_RETURN_PC)},
        "resident_word_site": {"pc": hex(HIDDEN_WORD_PC), "length": 16,
                                "source_sha256": sha(word_source), "staged_sha256": sha(word_staged)},
        "helper_placement": {"page": HIDDEN_HELPER_PAGE, "origin": hex(HIDDEN_HELPER_ORIGIN),
                             "bytes": len(candidate_helper)},
        "selected_back_mapping": {"pc": hex(map_back), "length": len(map_back_source),
                                  "source_staged_sha256": sha(map_back_source),
                                  "meaning": "static mapper selects FB_BACK_ID pages in PAR1-PAR4 and sets its own PAR5 to $3A"},
        "hold_owner2_source_staged": True,
        "runtime_hidden_back_reads_qualified_yet": False,
        "actual_GIME_hidden_scanout_qualified_yet": False,
        "broken_baseline_pixel_capture_observed": False,
        "fixture_class": "source/artifact qualification only; no emulator was launched",
    }


def parse_symbols(path: Path) -> dict[str, int]:
    text = path.read_text(encoding="utf-8")
    return {name: int(value, 16) for name, value in
            re.findall(r"^Symbol: (\w+) .* = ([0-9A-Fa-f]+)$", text, re.MULTILINE)}


def tmx_layer(path: Path, name: str) -> tuple[int, int, list[int]]:
    root = ET.parse(str(path)).getroot()
    width, height = int(root.get("width", "0")), int(root.get("height", "0"))
    layer = next((x for x in root.findall("layer") if x.get("name") == name), None)
    if layer is None:
        raise ProbeError("missing authored TMX layer: " + name)
    data = layer.find("data")
    if data is None or data.get("encoding") != "csv" or not data.text:
        raise ProbeError("unsupported TMX encoding")
    values = [int(x.strip()) for x in data.text.replace("\r", "").split(",") if x.strip()]
    if len(values) != width * height:
        raise ProbeError("TMX layer dimensions do not match cells")
    return width, height, values


def glyph_tile(chars: list[list[list[int]]], gid: int, colour: int) -> bytes:
    if gid <= 0 or gid & 0xE0000000:
        raise ProbeError("empty/flipped tile is not accepted by the word oracle")
    sheet_index = gid - 1
    code = (sheet_index % 16) * 32 + (31 - sheet_index // 16)
    if not 0 <= code < len(chars):
        raise ProbeError("TMX gid is outside pinned raw character sheet")
    raw = chars[code]
    # build_screen.rotate_ccw, then the packed CoCo byte uses left pixel in high nibble.
    rotated = [[raw[x][7 - y] for x in range(8)] for y in range(8)]
    out = bytearray()
    for row in rotated:
        values = [0 if p == 0 else colour for p in row]
        out.extend((values[i] << 4) | values[i + 1] for i in range(0, 8, 2))
    return bytes(out)


def word_oracle(capsule: Path = CAPSULE, masks: tuple[int, int] = (0x49, 0x15)) -> dict[str, Any]:
    path = capsule / "tiled" / "coco-level-start-screen.tmx"
    width, _, gids = tmx_layer(path, "CoCo Side HUD")
    chars = json.loads((capsule / "assets" / "arcade" / "chars.json").read_text(encoding="utf-8"))
    special_gids = [gids[1 * width + x] for x in range(1, 8)]
    extra_gids = [gids[4 * width + x] for x in range(1, 6)]
    if special_gids != [49, 97, 273, 305, 209, 337, 161] or extra_gids != [273, 482, 33, 65, 337]:
        raise ProbeError("pinned TMX word-glyph positions changed")
    rows = []
    for word, row, selected, word_gids, colour in (
        ("SPECIAL", 1, masks[0], special_gids, 1),
        ("EXTRA", 4, masks[1], extra_gids, 2),
    ):
        tiles = []
        for index, gid in enumerate(word_gids):
            lit = bool(selected & (1 << index))
            tile = glyph_tile(chars, gid, colour if lit else 7)
            tiles.append({"cell": [index + 1, row], "gid": gid,
                          "selected": lit, "colour": colour if lit else 7,
                          "expected_sha256": sha(tile), "expected_hex": tile.hex()})
        rows.append({"word": word, "tiles": tiles})
    return {"source": str(path), "source_sha256": file_sha(path),
            "font_sha256": file_sha(capsule / "assets" / "arcade" / "chars.json"),
            "special_mask": "49", "extra_mask": "15", "rows": rows,
            "semantics": "nonzero raw glyph pixels use red=1 or yellow=2 when selected; otherwise gray=7; zero stays black"}


def tile_from_frame(frame: bytes, x: int, y: int) -> bytes:
    start = y * 8 * 160 + x * 4
    return b"".join(frame[start + row * 160:start + row * 160 + 4] for row in range(8))


def check_word_tiles(frame: bytes, oracle: dict[str, Any], require_selected: bool = True) -> dict[str, Any]:
    expected_count = sum(len(group["tiles"]) for group in oracle["rows"])
    if expected_count != 12:
        raise ProbeError("word crop is incomplete: expected twelve authored glyph cells")
    seen = []
    for group in oracle["rows"]:
        for tile in group["tiles"]:
            actual = tile_from_frame(frame, tile["cell"][0], tile["cell"][1])
            expected = bytes.fromhex(tile["expected_hex"])
            if actual != expected:
                raise ProbeError("word pixel mismatch at %s %s actual=%s expected=%s" %
                                 (group["word"], tile["cell"], sha(actual), sha(expected)))
            if require_selected and tile["selected"] and not any(actual):
                raise ProbeError("selected word glyph is empty")
            seen.append({"word": group["word"], "cell": tile["cell"], "sha256": sha(actual)})
    return {"tiles_checked": len(seen), "sha256": canonical_hash(seen), "tiles": seen}


def load_hidden_pixel_oracle() -> Any:
    if not HIDDEN_ORACLE_PATH.is_file() or file_sha(HIDDEN_ORACLE_PATH) != HIDDEN_ORACLE_SHA:
        raise ProbeError("pinned BUG-122 letter/heart pixel oracle is missing or changed")
    spec = importlib.util.spec_from_file_location("bug122_pixel_oracle_for_bug046", HIDDEN_ORACLE_PATH)
    if spec is None or spec.loader is None:
        raise ProbeError("cannot load the pinned letter/heart pixel oracle")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if Path(module.__file__).resolve() != HIDDEN_ORACLE_PATH.resolve() or \
            file_sha(Path(module.__file__)) != HIDDEN_ORACLE_SHA:
        raise ProbeError("pixel oracle import resolved outside the pinned source")
    return module


def receipt_input(build: Path, relative: str) -> tuple[Path, str]:
    """Return one exact capsule-authored input after verifying its receipt identity."""
    receipt_path = build / "source-build-receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    expected = receipt.get("inputs", {}).get(relative)
    if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise ProbeError("pinned candidate receipt lacks authored input " + relative)
    path = build.parent / relative
    if not inside(path, build.parent) or not path.is_file() or file_sha(path) != expected:
        raise ProbeError("receipt-qualified input changed: " + relative)
    return path, expected


def hidden_underlay(build: Path) -> tuple[bytes, dict[str, Any], Any, list[bytes], bytes]:
    """Compile the frozen candidate map with the existing host rasterizer and oracle helpers."""
    build = build.resolve()
    if build != HIDDEN_BUILD.resolve():
        raise ProbeError("absolute panel oracle requires the frozen BUG-046 candidate capsule")
    capsule = build.parent
    map_path = capsule / "tiled" / "coco-level-start-screen.tmx"
    chars_path = capsule / "assets" / "arcade" / "chars.json"
    if file_sha(map_path) != HIDDEN_PANEL_MAP_SHA or file_sha(chars_path) != HIDDEN_CHARS_SHA:
        raise ProbeError("candidate panel-map or raw-character source identity changed")
    oracle = load_hidden_pixel_oracle()
    presentation_script, presentation_script_sha = receipt_input(build, "scripts/build_presentation.py")
    screen_script, screen_script_sha = receipt_input(build, "scripts/build_screen.py")
    scripts = HIDDEN_CAPSULE / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    # The candidate capsule is the import root. Remove same-named modules that
    # may have been loaded from the mutable checkout by an earlier tool call.
    sys.modules.pop("build_presentation", None)
    sys.modules.pop("build_screen", None)
    import build_presentation as bp
    import build_screen as bs
    for module, path, expected_sha in ((bp, presentation_script, presentation_script_sha),
                                       (bs, screen_script, screen_script_sha)):
        if Path(module.__file__).resolve() != path.resolve() or file_sha(path) != expected_sha:
            raise ProbeError("candidate oracle compiler import did not resolve to its receipt-pinned capsule input")

    HIDDEN_OWNED.mkdir(parents=True, exist_ok=True)
    import tempfile
    with tempfile.TemporaryDirectory(prefix="pixel-oracle-", dir=str(HIDDEN_OWNED)) as temporary:
        scratch = Path(temporary)
        candidate = ET.parse(str(map_path)).getroot()
        for tileset in candidate.findall("tileset"):
            relative = tileset.get("source")
            if relative:
                tileset.set("source", str((capsule / "tiled" / relative).resolve()))
        compiled_map = scratch / map_path.name
        ET.ElementTree(candidate).write(compiled_map, encoding="utf-8", xml_declaration=True)
        chars = bs.load_chars(chars_path)
        tiles: list[bytes] = []
        tile_ids: dict[bytes, int] = {}
        tile_map, metadata = bp.compile_map(compiled_map, chars, tiles, tile_ids)
        if len(tile_map) != 40 * 24:
            raise ProbeError("candidate panel map did not compile to the 40x24 approved screen")
        frame = bytearray(30720)
        for cell, tile_id in enumerate(tile_map):
            x, y = cell % 40, cell // 40
            tile = tiles[tile_id]
            for row in range(8):
                offset = (y * 8 + row) * 160 + x * 4
                frame[offset:offset + 4] = tile[row * 4:row * 4 + 4]
        underlay = bytes(frame)

    if (HIDDEN_BASELINE_BUILD / "retention.json").is_file():
        retention_bytes = (HIDDEN_BASELINE_BUILD / "retention.json").read_bytes()
        retention = json.loads(retention_bytes.decode("utf-8"))
        if retention.get("rom_sha256") != HIDDEN_BASELINE_ROM_SHA or \
                retention.get("files", {}).get("ladybug.rom") != HIDDEN_BASELINE_ROM_SHA:
            raise ProbeError("known-good Blue3 palette baseline retention identity changed")
    else:
        raise ProbeError("known-good Blue3 palette baseline retention manifest is missing")
    if file_sha(HIDDEN_BASELINE_BUILD / "ladybug.rom") != HIDDEN_BASELINE_ROM_SHA:
        raise ProbeError("known-good Blue3 palette baseline ROM identity changed")
    masks = oracle.compile_masks()
    candidate_masks = oracle.artifact_data(build, "object_masks", 12 * 64)
    authored_masks = b"".join(masks)
    if len(masks) != 12 or any(len(mask) != 64 for mask in masks) or authored_masks != candidate_masks:
        raise ProbeError("compiled authored masks do not match the candidate resident object masks")
    blue = oracle.expected_blue_pair_map(HIDDEN_BASELINE_BUILD)
    if sha(blue) != HIDDEN_BLUE_TABLE_SHA:
        raise ProbeError("known-good frozen baseline sprite_blue_pairs table changed")
    info = {
        "oracle_path": str(HIDDEN_ORACLE_PATH), "oracle_sha256": HIDDEN_ORACLE_SHA,
        "candidate_compiler_inputs": {
            "build_presentation.py": {"path": str(presentation_script), "sha256": presentation_script_sha},
            "build_screen.py": {"path": str(screen_script), "sha256": screen_script_sha}},
        "candidate_map_sha256": file_sha(map_path), "candidate_chars_sha256": file_sha(chars_path),
        "underlay_sha256": sha(underlay), "underlay_bytes": len(underlay),
        "map_role": metadata.get("role"), "map_atlas_tiles": len(tiles),
        "candidate_object_masks_sha256": sha(candidate_masks),
        "compiled_object_masks_sha256": sha(authored_masks),
        "baseline_rom_sha256": HIDDEN_BASELINE_ROM_SHA,
        "baseline_retention_sha256": sha(retention_bytes),
        "baseline_sprite_blue_pairs_sha256": sha(blue),
        "absolute_letter_and_heart_oracle": "qualified for current candidate inputs",
        "historical_clean_underlay_status": "unusable: old BUG-122 baseline retention.json is absent; this path does not synthesize or bypass it",
    }
    return underlay, info, oracle, masks, blue


def panel_pixel_check(frame: bytes, masks_state: dict[str, int], variants: list[int],
                      build: Path, underlay: bytes, pixel_oracle: Any,
                      masks: list[bytes], blue: bytes) -> dict[str, Any]:
    try:
        word = check_word_tiles(frame, word_oracle(build.parent))
        word_result = {"classification": "pixel_match", "tiles_checked": word["tiles_checked"],
                       "sha256": word["sha256"]}
    except ProbeError as exc:
        word_result = {"classification": "pixel_mismatch", "error": str(exc)}
    word_match = masks_state == {"special": 0x49, "extra": 0x15}
    if len(variants) != 3 or any(not 0 <= value < len(masks) for value in variants):
        raise MissingCoverage("captured random-letter identities are incomplete or out of oracle range")
    letters = pixel_oracle.compare_letter_slots(frame, underlay, variants, masks, blue)
    hearts = pixel_oracle.compare_heart_slots(frame, underlay)
    return {
        "word_pixels": word_result,
        "stored_masks": {"expected": {"special": 0x49, "extra": 0x15},
                         "actual": masks_state, "classification": "match" if word_match else "mismatch"},
        "random_letters": {"selected_variants": variants,
                           "all_slots_match": letters["all_slots_match"],
                           "slots": [{"slot": item["slot"], "variant": item["variant"],
                                      "pass": item["comparison"]["pass"],
                                      "actual_sha256": item["comparison"]["actual_sha256"],
                                      "expected_sha256": item["comparison"]["expected_sha256"]}
                                     for item in letters["slots"]]},
        "hearts": {"all_slots_match": hearts["all_slots_match"],
                   "slots": [{"slot": item["slot"], "pass": item["comparison"]["pass"],
                              "actual_sha256": item["comparison"]["actual_sha256"],
                              "expected_sha256": item["comparison"]["expected_sha256"]}
                             for item in hearts["slots"]]},
    }


def hidden_reference_frame(underlay: bytes, variants: list[int], pixel_oracle: Any,
                           masks: list[bytes], blue: bytes, words: dict[str, Any]) -> bytes:
    """Create a synthetic positive fixture; it is not observed runtime evidence."""
    frame = bytearray(underlay)
    for slot, variant in enumerate(variants):
        crop = pixel_oracle.compose_slot(underlay, slot, masks[variant], blue)
        byte_col = pixel_oracle.SLOT_BYTE_COLS[slot]
        for row in range(16):
            offset = (112 + row) * 160 + byte_col
            frame[offset:offset + 8] = crop[row * 8:row * 8 + 8]
    for group in words["rows"]:
        for tile in group["tiles"]:
            x, y = tile["cell"]
            data = bytes.fromhex(tile["expected_hex"])
            for row in range(8):
                offset = (y * 8 + row) * 160 + x * 4
                frame[offset:offset + 4] = data[row * 4:row * 4 + 4]
    return bytes(frame)


def hidden_owner_identity_check(captures: list[dict[str, Any]], preview_commit: dict[str, int]) -> dict[str, Any]:
    if {item.get("back_owner") for item in captures} != {0, 1} or len(captures) != 2:
        raise MissingCoverage("natural hidden-owner evidence does not contain exactly BACK0 and BACK1")
    expected_bases = {0: 0x60000, 1: 0x58000}
    if any(item.get("selected_back_base") != expected_bases.get(item.get("back_owner"))
           for item in captures):
        raise ProbeError("selected BACK metadata does not map to its receipt-qualified physical pages")
    saved_front, saved_back = captures[0].get("hold_saved_front"), captures[0].get("hold_saved_back")
    if {saved_front, saved_back} != {0, 1}:
        raise MissingCoverage("source-restored saved FRONT/BACK identities do not cover owners0 and1")
    if ([captures[0].get("back_owner"), captures[1].get("back_owner")] !=
            [saved_back, saved_front] or any(
                (item.get("hold_saved_front"), item.get("hold_saved_back")) !=
                (saved_front, saved_back) for item in captures)):
        raise MissingCoverage("natural hidden order does not follow restored saved BACK then saved FRONT")
    identities = [item.get("letter_variants") for item in captures]
    if identities[0] != identities[1]:
        raise MissingCoverage("natural hidden captures changed random-letter identity")
    if any(item.get("gime_scanout", {}).get("base") != HIDDEN_SCANOUT_BASE or
           item.get("gime_scanout", {}).get("owner") != 2 or
           item.get("gime_scanout", {}).get("mode") != 0x80 or
           item.get("gime_scanout", {}).get("vres") != 0x1E for item in captures):
        raise MissingCoverage("actual GIME did not remain on compatibility scanout owner2 during hidden rendering")
    if any(item.get("pending") != 0 or item.get("hold_state") != 3 for item in captures):
        raise MissingCoverage("hidden crop was not captured during stable HYDRATE ownership")
    pixel_gates = []
    for item in captures:
        pixels = item.get("pixel_checks", {})
        pixel_gates.append({
            "back_owner": item["back_owner"],
            "words_pass": pixels.get("word_pixels", {}).get("classification") == "pixel_match",
            "masks_pass": pixels.get("stored_masks", {}).get("classification") == "match",
            "letters_pass": bool(pixels.get("random_letters", {}).get("all_slots_match")),
            "hearts_pass": bool(pixels.get("hearts", {}).get("all_slots_match")),
        })
    pixels_pass = all(all(value for key, value in gate.items() if key != "back_owner")
                      for gate in pixel_gates)
    if preview_commit.get("published") is None or preview_commit.get("before") is None or \
            ((int(preview_commit["published"]) - int(preview_commit["before"])) & 0xFFFF) == 0:
        raise MissingCoverage("preview commit did not advance from the pre-transition publication")
    return {"result": "pass" if pixels_pass else "product_reproduced",
            "hidden_BACK_owners": sorted(item["back_owner"] for item in captures),
            "shared_random_letter_identity": identities[0],
            "actual_GIME_hidden_scanout_owner": 2,
            "absolute_pixel_gates": pixel_gates,
            "preview_commit_advanced": True}


class PhaseBudget:
    """One absolute phase deadline; nested client calls may not renew it."""
    def __init__(self, seconds: float = PHASE_SECONDS, clock: Callable[[], float] = time.monotonic):
        self.clock = clock
        self.started = clock()
        self.deadline = self.started + seconds
        self.stops = 0

    def remaining(self) -> float:
        return self.deadline - self.clock()

    def require(self, label: str, reserve: float = READ_RESERVE) -> float:
        left = self.remaining()
        if left <= reserve:
            raise PhaseDeadline("phase deadline exhausted before " + label)
        return left - reserve

    def stop(self, label: str) -> float:
        self.stops += 1
        if self.stops > MAX_STOPS:
            raise ProbeError("1000-stop phase cap exceeded at " + label)
        return min(STOP_SECONDS, self.require(label))


class DeadlineClient:
    """Per-client clamp around the maintained MonitorClient; restores on exit."""
    def __init__(self, raw: Any, budget: PhaseBudget, writes: dict[int, int], keys: set[int]):
        self.raw, self.budget = raw, budget
        self.writes, self.keys = writes, keys
        self.original = {name: getattr(raw, name) for name in ("_read", "call", "run_to_breakpoint")}
        self.fixture_seen: list[tuple[int, int]] = []
        self.key_down: set[int] = set()
        self.last_qualified_marker: dict[str, Any] | None = None
        self.restored = False
        original_read, original_call, original_run = self.original.values()

        def strict_read(local_deadline: float) -> dict[str, Any]:
            left = self.budget.require("monitor read")
            clipped = min(local_deadline, self.budget.deadline - READ_RESERVE)
            if clipped - time.monotonic() <= 0.10:
                raise PhaseDeadline("monitor read refused below helper's 0.10-second floor")
            message = original_read(clipped)
            if self.budget.remaining() <= 0:
                raise PhaseDeadline("monitor read returned after phase deadline")
            return message

        def strict_call(method: str, params: dict[str, Any] | None = None,
                        timeout: float = 20.0) -> dict[str, Any]:
            left = self.budget.require("RPC " + method)
            if method in ("write_registers", "write_register", "memory.write"):
                raise ProbeError("register/alternate guest write RPC is forbidden")
            if method == "write_memory":
                write = self._guard_write(params or {})
            else:
                write = None
            if method == "inject_key":
                self._guard_key(params or {})
            allowed = {"events.subscribe", "set_breakpoint", "clear_breakpoint", "read_memory",
                       "read_registers", "read_cycles", "read_gime_state", "write_memory", "inject_key", "pause",
                       "wait_for_stop", "run"}
            if method not in allowed:
                raise ProbeError("unreviewed monitor method rejected: " + method)
            args = dict(params) if params is not None else None
            if method == "wait_for_stop" and args is not None:
                args["timeout_ms"] = min(int(args.get("timeout_ms", 0)), int(left * 1000))
            result = original_call(method, args, timeout=min(float(timeout), left))
            if self.budget.remaining() <= 0:
                raise PhaseDeadline("RPC returned after whole-phase deadline: " + method)
            if write is not None:
                self.fixture_seen.append(write)
            return result

        def strict_run(timeout: float = 20.0) -> dict[str, Any]:
            left = self.budget.require("breakpoint wait")
            result = original_run(timeout=min(float(timeout), left))
            if self.budget.remaining() <= 0:
                raise PhaseDeadline("breakpoint wait returned after whole-phase deadline")
            return result

        raw._read, raw.call, raw.run_to_breakpoint = strict_read, strict_call, strict_run

    def _guard_write(self, params: dict[str, Any]) -> tuple[int, int]:
        if set(params) - {"addr", "data", "space"} or params.get("space", "cpu") != "cpu":
            raise ProbeError("non-CPU or extra-parameter guest write rejected")
        address = int(params.get("addr", -1))
        data = bytes.fromhex(str(params.get("data", "")))
        if len(data) != 1 or address not in self.writes or data[0] != self.writes[address]:
            raise ProbeError("guest write rejected outside exact four-byte fixture")
        if any(old == address for old, _ in self.fixture_seen):
            raise ProbeError("duplicate fixture write rejected")
        return address, data[0]

    def _guard_key(self, params: dict[str, Any]) -> None:
        key = int(params.get("key", -1))
        action = params.get("action")
        if key not in self.keys or action not in ("press", "release"):
            raise ProbeError("unapproved keyboard input rejected")
        if action == "press":
            if key in self.key_down:
                raise ProbeError("duplicate key press rejected")
            self.key_down.add(key)
        else:
            if key not in self.key_down:
                raise ProbeError("unmatched key release rejected")
            self.key_down.remove(key)

    def close(self) -> None:
        if self.restored:
            return
        for name, value in self.original.items():
            setattr(self.raw, name, value)
        self.restored = True


def strict_import_check(path: Path) -> None:
    old_socket, old_popen = socket.socket, subprocess.Popen
    def denied(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("import attempted process or socket activity")
    try:
        socket.socket = denied  # type: ignore[assignment]
        subprocess.Popen = denied  # type: ignore[assignment]
        spec = importlib.util.spec_from_file_location("stage_preview_probe_isolated", path)
        if spec is None or spec.loader is None:
            raise ProbeError("cannot construct isolated import")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        socket.socket, subprocess.Popen = old_socket, old_popen


def self_test() -> dict[str, Any]:
    oracle = word_oracle()
    good = bytearray(30720)
    for group in oracle["rows"]:
        for tile in group["tiles"]:
            start = tile["cell"][1] * 8 * 160 + tile["cell"][0] * 4
            data = bytes.fromhex(tile["expected_hex"])
            for row in range(8):
                good[start + row * 160:start + row * 160 + 4] = data[row * 4:row * 4 + 4]
    positive = check_word_tiles(bytes(good), oracle)
    unlit_oracle = word_oracle(masks=(0, 0))
    broken = bytearray(30720)
    for group in unlit_oracle["rows"]:
        for tile in group["tiles"]:
            start = tile["cell"][1] * 8 * 160 + tile["cell"][0] * 4
            data = bytes.fromhex(tile["expected_hex"])
            for row in range(8):
                broken[start + row * 160:start + row * 160 + 4] = data[row * 4:row * 4 + 4]
    try:
        check_word_tiles(bytes(broken), oracle)
        raise AssertionError("same-mask all-unlit preview negative passed")
    except ProbeError:
        pass
    try:
        check_word_tiles(bytes(good), word_oracle(masks=(0x41, 0x15)))
        raise AssertionError("changed-mask oracle negative passed")
    except ProbeError:
        pass
    try:
        check_word_tiles(bytes(good), {**oracle, "rows": []})
        raise AssertionError("missing-crop negative passed")
    except ProbeError:
        pass
    # Nested read/wait RPCs clamp to the same absolute phase; expiry blocks calls.
    clock = [0.0]
    budget = PhaseBudget(1.0, lambda: clock[0])
    assert budget.require("setup") > 0.8
    calls: list[tuple[str, float]] = []
    class FakeClient:
        def _read(self, deadline: float) -> dict[str, Any]:
            calls.append(("read", deadline))
            return {}
        def call(self, method: str, params: dict[str, Any] | None = None,
                 timeout: float = 20.0) -> dict[str, Any]:
            calls.append((method, timeout))
            if method == "wait_for_stop" and params is not None:
                assert params["timeout_ms"] <= int(timeout * 1000)
            clock[0] += 0.2
            return {}
        def run_to_breakpoint(self, timeout: float = 20.0) -> dict[str, Any]:
            calls.append(("legacy_run", timeout))
            return {}
    fake = FakeClient()
    guarded = DeadlineClient(fake, budget, dict(FIXTURE), {KEY_UP})
    guarded.raw.call("read_memory", {"addr": 0, "length": 1}, timeout=20.0)
    assert calls[-1][0] == "read_memory" and 0 < calls[-1][1] < 1.0
    clock[0] = 0.0
    guarded.raw.call("wait_for_stop", {"timeout_ms": 5000}, timeout=5.0)
    assert calls[-1][0] == "wait_for_stop" and 0 < calls[-1][1] < 1.0
    guarded.close()
    assert fake.call.__func__ is FakeClient.call and fake._read.__func__ is FakeClient._read
    calls.clear()
    clock[0] = 0.90
    try:
        guarded = DeadlineClient(fake, budget, dict(FIXTURE), {KEY_UP})
        guarded.raw.call("read_memory", {"addr": 0, "length": 1}, timeout=20.0)
        raise AssertionError("near-budget nested RPC was not rejected")
    except PhaseDeadline:
        pass
    finally:
        guarded.close()
    assert calls == []
    # Source-listing/staged/CPU/physical/PAR qualification uses a fake monitor
    # backed only by the receipt-pinned staged images. No process or socket is
    # created by these tests.
    class ImageMonitor:
        def __init__(self, par0: int = 0x38, corrupt_physical: bool = False,
                     build: Path = BUILD_DEFAULT):
            self.par0, self.corrupt_physical = par0, corrupt_physical
            self.runtime = (build / "ladybug-runtime.rom").read_bytes()
            self.enemy = (build / "ladybug-enemy-runtime.rom").read_bytes()
            self.presentation = (build / "ladybug-presentation-runtime.bin").read_bytes()
            self.active = (build / "ladybug-adaptive-active.bin").read_bytes()
            self.calls: list[str] = []
        def _read(self, deadline: float) -> dict[str, Any]:
            raise AssertionError("site qualification should not use transport reads")
        def run_to_breakpoint(self, timeout: float = 20.0) -> dict[str, Any]:
            raise AssertionError("site qualification should not run the emulator")
        def call(self, method: str, params: dict[str, Any] | None = None,
                 timeout: float = 20.0) -> dict[str, Any]:
            self.calls.append(method)
            args = params or {}
            if method == "read_gime_state":
                task0 = [self.par0, 0, 0, 0, 0, 0x34, 0x3E, 0x3F]
                return {"mmu_task": 0, "pars": {"task0": task0, "task1": [0] * 8},
                        "registers": {"FF98": 0x80}}
            if method != "read_memory":
                raise AssertionError("unexpected fake monitor method: " + method)
            address, length = int(args["addr"]), int(args["length"])
            space = args.get("space", "cpu")
            out = bytearray()
            for pos in range(address, address + length):
                if space == "physical":
                    page, offset = divmod(pos, 0x2000)
                    if page == 0x38 and PRES <= offset < PRES + len(self.presentation):
                        value = self.presentation[offset - PRES]
                    elif page == 0x38 and ENEMY_ORIGIN <= offset < ENEMY_ORIGIN + len(self.enemy):
                        value = self.enemy[offset - ENEMY_ORIGIN]
                    elif page == 0x38 and ACTIVE_ORIGIN <= offset < ACTIVE_ORIGIN + len(self.active):
                        value = self.active[offset - ACTIVE_ORIGIN]
                    elif page == 0x3E:
                        value = self.runtime[offset]
                    elif page == 0x3F and offset < 0x1E00:
                        value = self.runtime[0x2000 + offset]
                    else:
                        raise AssertionError("fake physical read outside qualified sites")
                    if self.corrupt_physical and pos == address:
                        value ^= 0x01
                elif 0xC000 <= pos < 0xFE00:
                    value = self.runtime[pos - 0xC000]
                elif PRES <= pos < PRES + len(self.presentation):
                    value = self.presentation[pos - PRES]
                elif ENEMY_ORIGIN <= pos < ENEMY_ORIGIN + len(self.enemy):
                    value = self.enemy[pos - ENEMY_ORIGIN]
                elif ACTIVE_ORIGIN <= pos < ACTIVE_ORIGIN + len(self.active):
                    value = self.active[pos - ACTIVE_ORIGIN]
                else:
                    raise AssertionError("fake CPU read outside qualified sites")
                out.append(value)
            return {"data": out.hex()}
    qualifier = SiteQualifier(BUILD_DEFAULT)
    fake = ImageMonitor()
    guarded = DeadlineClient(fake, PhaseBudget(30.0), dict(FIXTURE), {KEY_UP})
    proofs = [qualifier.qualify(guarded, addr, kind) for kind, addr in (
        ("main", 0xC41B), ("enemy", 0x0C21), ("presentation", 0x1900))]
    guarded.close()
    assert all(proof["source_sha256"] == proof["staged_sha256"] ==
               proof["cpu_sha256"] == proof["physical_sha256"] for proof in proofs)
    hidden_qualifier = SiteQualifier(HIDDEN_BUILD)
    class HelperImageMonitor:
        def __init__(self, par5: int = HIDDEN_HELPER_PAGE, corrupt_physical: bool = False):
            self.par5, self.corrupt_physical = par5, corrupt_physical
            self.helper = (HIDDEN_BUILD / "ladybug-highscore-helper.bin").read_bytes()
            self.calls: list[str] = []
        def _read(self, deadline: float) -> dict[str, Any]:
            raise AssertionError("banked-helper qualification should not use transport reads")
        def run_to_breakpoint(self, timeout: float = 20.0) -> dict[str, Any]:
            raise AssertionError("banked-helper qualification should not run the emulator")
        def call(self, method: str, params: dict[str, Any] | None = None,
                 timeout: float = 20.0) -> dict[str, Any]:
            self.calls.append(method)
            if method == "read_gime_state":
                task0 = [0x38, 0, 0, 0, 0, self.par5, 0x3E, 0x3F]
                return {"mmu_task": 0, "pars": {"task0": task0, "task1": [0] * 8},
                        "registers": {"FF98": 0x80}}
            if method != "read_memory":
                raise AssertionError("unexpected helper fake-monitor method: " + method)
            args = params or {}
            address, length = int(args["addr"]), int(args["length"])
            space = args.get("space", "cpu")
            output = bytearray()
            for pos in range(address, address + length):
                if space == "physical":
                    page, offset = divmod(pos, 0x2000)
                    cpu = 0xA000 + offset
                    if page != HIDDEN_HELPER_PAGE or not HIDDEN_HELPER_ORIGIN <= cpu < HIDDEN_HELPER_ORIGIN + len(self.helper):
                        raise AssertionError("helper fake physical read leaves page-$23 image")
                    value = self.helper[cpu - HIDDEN_HELPER_ORIGIN]
                    if self.corrupt_physical and pos == address:
                        value ^= 1
                else:
                    if self.par5 != HIDDEN_HELPER_PAGE or not HIDDEN_HELPER_ORIGIN <= pos < HIDDEN_HELPER_ORIGIN + len(self.helper):
                        raise AssertionError("helper fake CPU read leaves mapped page-$23 image")
                    value = self.helper[pos - HIDDEN_HELPER_ORIGIN]
                output.append(value)
            return {"data": output.hex()}
    helper_fake = HelperImageMonitor()
    guarded = DeadlineClient(helper_fake, PhaseBudget(10.0), dict(FIXTURE), {KEY_UP})
    helper_proof = hidden_qualifier.qualify(guarded, HIDDEN_TAIL_PC, "banked_helper")
    guarded.close()
    assert helper_proof["source_sha256"] == helper_proof["staged_sha256"] == \
           helper_proof["cpu_sha256"] == helper_proof["physical_sha256"]
    wrong_helper_map = HelperImageMonitor(par5=0x24)
    guarded = DeadlineClient(wrong_helper_map, PhaseBudget(10.0), dict(FIXTURE), {KEY_UP})
    try:
        hidden_qualifier.qualify(guarded, HIDDEN_TAIL_PC, "banked_helper")
        raise AssertionError("wrong banked-helper PAR5 negative passed")
    except ProbeError:
        pass
    finally:
        guarded.close()
    assert "read_memory" not in wrong_helper_map.calls
    wrong_helper_physical = HelperImageMonitor(corrupt_physical=True)
    guarded = DeadlineClient(wrong_helper_physical, PhaseBudget(10.0), dict(FIXTURE), {KEY_UP})
    try:
        hidden_qualifier.qualify(guarded, HIDDEN_TAIL_PC, "banked_helper")
        raise AssertionError("banked-helper physical-page mismatch negative passed")
    except ProbeError:
        pass
    finally:
        guarded.close()
    bad_map = ImageMonitor(par0=0x39)
    guarded = DeadlineClient(bad_map, PhaseBudget(10.0), dict(FIXTURE), {KEY_UP})
    try:
        qualifier.qualify(guarded, 0x1900, "presentation")
        raise AssertionError("wrong PAR0 site negative passed")
    except ProbeError:
        pass
    finally:
        guarded.close()
    assert "read_memory" not in bad_map.calls
    bad_physical = ImageMonitor(corrupt_physical=True)
    guarded = DeadlineClient(bad_physical, PhaseBudget(10.0), dict(FIXTURE), {KEY_UP})
    try:
        qualifier.qualify(guarded, 0x1900, "presentation")
        raise AssertionError("physical-site byte negative passed")
    except ProbeError:
        pass
    finally:
        guarded.close()
    # Candidate-relative BUG-117 source/site qualification has its own fixture;
    # it proves the active-page mapping without launching XRoar.
    stage_static = offline_stage_entry_check(STAGE_ENTRY_BUILD)
    assert stage_static["result"] == "pass"
    stage_entry_assertions = ["candidate/frozen-broken guard and source/staged bytes",
        "candidate caller and CPU/physical mapping positives plus mapping negatives",
        "sixteen-step ordinal/input fixtures and position/input negatives",
        "post-ready predecessor ordinals 0..3 including initial PLAYER_DIR=DIR_NONE",
        "authoritative enemy-table safe/unsafe/invalid/mismatch fixtures",
        "enemy page mapping good/PAR5/PAR6 negatives",
        "stage enemy-reset/release source and staged-byte proof",
        "R1 state-evidence good, missing/read/mismatch/mapping negatives and product differential",
        "R2 three pinned revision identities and unknown-build rejection"]
    state_pars = [0x38, 0x39, 0x3A, 0x3B, 0x3C, 0x34, 0x3E, 0x3F]
    good_state = {
        "errors": [], "direct_page_cpu_physical_match": True,
        "direct_page_cpu_length": 0xA8, "direct_page_physical_length": 0xA8,
        "direct_page_cpu_sha256": "state-hash", "direct_page_physical_sha256": "state-hash",
        "gime": {"mmu_task": 0, "task0_pars": state_pars, "task1_pars": state_pars},
        "state_mapping_expected": True, "pose": stage_walk_pose(0),
        "input": {"joy_x": 32, "joy_y": 32, "joy_dir": DIR_NONE,
                  "player_dir": DIR_NORTH, "player_face": DIR_NORTH,
                  "player_want": DIR_NONE, "player_manual": 0},
        "flags": {key: 0 for key in ("initial_entry_state", "player_tick_pending", "box_timer",
            "box_index", "enemy_active", "enemy_released", "enemy_roaming", "death_state",
            "pickup_timer", "stage", "presentation_mode", "presentation_screen",
            "presentation_context")},
        "cpu": {"pc": "0x8123", "s": "0x7000", "cc": "0", "dp": "0"},
        "cycles": {"event_ticks": 100, "cpu_cycles": 200}}
    assert stage_state_evidence_check(good_state)["pass"]
    state_negatives = [
        ({**good_state, "pose": None, "input": None}, "missing direct-page values"),
        ({**good_state, "errors": ["direct-page CPU read: controlled failure"]}, "failed state read"),
        ({**good_state, "direct_page_cpu_physical_match": False}, "CPU/physical mismatch"),
        ({**good_state, "gime": {**good_state["gime"],
                                  "task0_pars": [0x39] + state_pars[1:]},
          "state_mapping_expected": False}, "invalid state mapping")]
    for snapshot, label in state_negatives:
        evidence = stage_state_evidence_check(snapshot)
        if evidence["pass"] or not evidence["errors"]:
            raise AssertionError("R1 state evidence negative passed: " + label)
    product_state = {**good_state, "pose": stage_walk_pose(1)}
    if not stage_state_evidence_check(product_state)["pass"] or \
            not validate_stage_walk_entry(product_state, 0, "neutral"):
        raise AssertionError("valid state evidence did not preserve product discrepancy discrimination")
    pinned_identities = ((BUILD_DEFAULT, REVISION, "known-broken"),
                         (STAGE_ENTRY_BUILD, STAGE_ENTRY_REVISION,
                          "stage-entry-repair-candidate"),
                         (HIDDEN_BUILD, HIDDEN_REVISION, "hidden-owner-candidate"))
    for path, revision, identity in pinned_identities:
        if pinned_build_identity(path)[2:] != (revision, identity):
            raise AssertionError("R2 pinned build identity mismatch: " + str(path))
    try:
        artifact_check(ROOT / "repro" / "unapproved-build")
        raise AssertionError("R2 unknown build path was accepted")
    except ProbeError:
        pass
    stage_map = symbols_for(STAGE_ENTRY_BUILD, "ladybug.map")
    stage_qualifier = SiteQualifier(STAGE_ENTRY_BUILD)
    stage_fake = ImageMonitor(build=STAGE_ENTRY_BUILD)
    guarded = DeadlineClient(stage_fake, PhaseBudget(20.0), dict(FIXTURE), {KEY_UP})
    guard_proof = stage_qualifier.qualify(guarded,
        marker_addr(stage_map, "rj_request") + 4, "main")
    active_call = stage_static["adaptive_callers"]["input_call"]
    active_proof = stage_qualifier.qualify(guarded, int(active_call, 16), "active")
    guarded.close()
    assert guard_proof["source_sha256"] == guard_proof["staged_sha256"] == \
           guard_proof["cpu_sha256"] == guard_proof["physical_sha256"]
    assert active_proof["source_sha256"] == active_proof["staged_sha256"] == \
           active_proof["cpu_sha256"] == active_proof["physical_sha256"]
    stage_bad_map = ImageMonitor(par0=0x39, build=STAGE_ENTRY_BUILD)
    guarded = DeadlineClient(stage_bad_map, PhaseBudget(10.0), dict(FIXTURE), {KEY_UP})
    try:
        stage_qualifier.qualify(guarded, int(active_call, 16), "active")
        raise AssertionError("candidate active-page mapping negative passed")
    except ProbeError:
        pass
    finally:
        guarded.close()
    assert "read_memory" not in stage_bad_map.calls
    stage_bad_physical = ImageMonitor(corrupt_physical=True, build=STAGE_ENTRY_BUILD)
    guarded = DeadlineClient(stage_bad_physical, PhaseBudget(10.0), dict(FIXTURE), {KEY_UP})
    try:
        stage_qualifier.qualify(guarded, marker_addr(stage_map, "rj_request") + 4, "main")
        raise AssertionError("candidate physical guard-byte negative passed")
    except ProbeError:
        pass
    finally:
        guarded.close()
    for barrier, guard in ((bytes.fromhex("0da02610"), bytes(6)),
                           (bytes.fromhex("0da02610"), bytes.fromhex("d618da062709")),
                           (bytes.fromhex("0da02611"), STAGE_ENTRY_GUARD)):
        try:
            validate_stage_guard(barrier, guard, 0xCB4A, 0xCB5E)
            raise AssertionError("absent/wrong stage guard fixture passed")
        except ProbeError:
            pass
    stage_entry_negative = False
    try:
        validate_stage_guard(bytes.fromhex("0da02610"), STAGE_ENTRY_GUARD,
                             0xCB4A, 0xCB5F)
    except ProbeError:
        stage_entry_negative = True
    assert stage_entry_negative
    assert validate_stage_guard(bytes.fromhex("0da02610"), STAGE_ENTRY_GUARD,
                                0xCB4A, 0xCB5E)["branch_target"] == "0xcb5e"
    truth = [stage_guard_contract(0, DIR_NORTH)["admitted"],
             stage_guard_contract(0, DIR_NONE)["admitted"],
             stage_guard_contract(1, DIR_NORTH)["admitted"]]
    assert truth == [False, True, True]
    held_entry = {"pose": stage_walk_pose(7), "input": {"joy_x": 32, "joy_y": 64,
        "joy_dir": DIR_NONE, "player_dir": DIR_NORTH, "player_face": DIR_NORTH,
        "player_want": DIR_NONE, "player_manual": 0}}
    assert validate_stage_walk_entry(held_entry, 7, "held") == []
    for snapshot, ordinal, case, label in (
            ({**held_entry, "pose": stage_walk_pose(8)}, 7, "held", "position ordinal"),
            (held_entry, 17, "held", "out-of-range ordinal"),
            ({**held_entry, "input": {**held_entry["input"], "joy_y": 32}}, 7, "held", "input axis")):
        if not validate_stage_walk_entry(snapshot, ordinal, case):
            raise AssertionError("stage position/input negative passed: " + label)
    post_ready_snaps = []
    for ordinal in range(4):
        pose = stage_post_ready_pose(ordinal, DIR_NORTH)
        post_ready_snaps.append({"pose": pose, "input": {"player_manual": 1,
            "player_dir": DIR_NONE if ordinal == 0 else DIR_NORTH,
            "player_face": DIR_NORTH, "player_want": DIR_NORTH, "joy_dir": DIR_NORTH}})
        if validate_post_ready_predecessor(post_ready_snaps[-1], ordinal, DIR_NORTH):
            raise AssertionError("source-derived post-ready predecessor fixture rejected")
    if not validate_post_ready_predecessor(post_ready_snaps[1], 0, DIR_NORTH):
        raise AssertionError("post-ready draw-ordinal predecessor negative passed")
    wrong_initial_dir = {"pose": stage_post_ready_pose(0, DIR_SOUTH),
        "input": {"player_manual": 1, "player_dir": DIR_SOUTH, "player_face": DIR_SOUTH,
                  "player_want": DIR_SOUTH, "joy_dir": DIR_SOUTH}}
    if not validate_post_ready_predecessor(wrong_initial_dir, 0, DIR_SOUTH):
        raise AssertionError("post-ready initial PLAYER_DIR negative passed")
    lane_origin, lane_target = (12, 22), (12, 21)
    empty_lifecycle = {"enemy_active": 0, "enemy_released": 0, "enemy_roaming": 0,
                       "box_index": 2, "box_timer": 5, "death_state": 0, "pickup_timer": 0}
    empty_enemy = bytes(ENEMY_RECORD_SIZE * ENEMY_RECORDS)
    assert stage_enemy_lane_snapshot(empty_enemy, empty_enemy, empty_lifecycle,
                                     lane_origin, lane_target)["pass"]
    far_enemy = bytearray(empty_enemy)
    far_enemy[0:8] = bytes((1, 0x57, 0xEC, 0, 1, 1, 0, 0))
    far_lifecycle = {**empty_lifecycle, "enemy_active": 1, "enemy_released": 1}
    assert stage_enemy_lane_snapshot(bytes(far_enemy), bytes(far_enemy), far_lifecycle,
                                     lane_origin, lane_target)["pass"]
    near_enemy = bytearray(far_enemy)
    near_enemy[4], near_enemy[5] = 12, 21
    if stage_enemy_lane_snapshot(bytes(near_enemy), bytes(near_enemy), far_lifecycle,
                                 lane_origin, lane_target)["pass"]:
        raise AssertionError("active enemy lane hazard negative passed")
    physical_enemy = bytearray(empty_enemy)
    physical_enemy[0] = 1
    if stage_enemy_lane_snapshot(empty_enemy, bytes(physical_enemy), empty_lifecycle,
                                 lane_origin, lane_target)["pass"]:
        raise AssertionError("enemy CPU/physical mapping negative passed")
    if stage_enemy_lane_snapshot(bytes(far_enemy), bytes(far_enemy), empty_lifecycle,
                                 lane_origin, lane_target)["pass"]:
        raise AssertionError("enemy active counter mismatch negative passed")
    invalid_enemy = bytearray(empty_enemy)
    invalid_enemy[0:8] = bytes((1, 0x57, 0xEC, 0, 24, 22, 0, 0))
    invalid_lifecycle = {**empty_lifecycle, "enemy_active": 1}
    if stage_enemy_lane_snapshot(bytes(invalid_enemy), bytes(invalid_enemy), invalid_lifecycle,
                                 lane_origin, lane_target)["pass"]:
        raise AssertionError("invalid active enemy position negative passed")
    bad_enemy_mapping = [0x38, 0, 0, 0, 0, 0x35, 0x3E, 0x3F]
    good_enemy_mapping = [0x38, 0, 0, 0, 0, 0x34, 0x3E, 0x3F]
    assert stage_enemy_mapping_check(0, good_enemy_mapping)["pass"]
    if stage_enemy_mapping_check(0, bad_enemy_mapping)["pass"] or \
            stage_enemy_mapping_check(0, [0x38, 0, 0, 0, 0, 0x34, 0x3D, 0x3F])["pass"]:
        raise AssertionError("enemy page mapping negative passed")
    write_guard = ImageMonitor()
    guarded = DeadlineClient(write_guard, PhaseBudget(10.0), dict(FIXTURE), {KEY_UP})
    for method, params in (("write_memory", {"addr": 0x3C, "data": "49", "space": "physical"}),
                           ("inject_key", {"key": 27, "action": "press"})):
        try:
            guarded.raw.call(method, params)
            raise AssertionError("unauthorized write/input negative passed")
        except ProbeError:
            pass
    assert "write_memory" not in write_guard.calls and "inject_key" not in write_guard.calls
    guarded.close()
    def scheduled(case: str, held_dir: int, face: int, event_ticks: int) -> dict[str, Any]:
        return {"case": case, "scheduled_step": {
            "movement_ordinal": 1, "player_tick_calls": 1, "draw_ordinal": 1, "draw_count": 1,
            "entry": {"event_ticks": event_ticks, "position": {"cell": [12, 22],
                       "fb": "0x89ec", "step": 0},
                       "input": {"joy_dir": held_dir, "player_face": face}},
            "draw": {"event_ticks": event_ticks + 128, "position": {"cell": [12, 22],
                       "fb": "0x88ac", "step": 1}}}}
    neutral = scheduled("neutral", DIR_NONE, DIR_NORTH, 1000)
    held = scheduled("held", DIR_SOUTH, DIR_SOUTH, 1128)
    pair = compare_scheduled_pair(neutral, held)
    assert pair["result"] == "pass" and pair["event_ticks_compared"] is False
    assert pair["facing_compared"] is False and pair["same_position"] is True
    for field, changed in (("cell", [12, 21]), ("fb", "0x89ea"), ("step", 2)):
        negative = scheduled("held", DIR_SOUTH, DIR_SOUTH, 5000)
        negative["scheduled_step"]["draw"]["position"][field] = changed
        assert compare_scheduled_pair(neutral, negative)["result"] == "position_divergence"
    for field, value in (("movement_ordinal", 0), ("player_tick_calls", 2),
                         ("draw_ordinal", 2), ("draw_count", 2)):
        negative = scheduled("held", DIR_SOUTH, DIR_SOUTH, 1128)
        negative["scheduled_step"][field] = value
        try:
            compare_scheduled_pair(neutral, negative)
            raise AssertionError("missing/duplicate ordinal negative passed: " + field)
        except ProbeError:
            pass
    try:
        compare_scheduled_pair(neutral, scheduled("held", DIR_NONE, DIR_SOUTH, 1128))
        raise AssertionError("unsampled held-input negative passed")
    except MissingCoverage:
        pass
    underlay, oracle_info, pixel_oracle, masks, blue = hidden_underlay(HIDDEN_BUILD)
    hidden_variants = [2, 4, 8]
    selected_oracle = word_oracle(HIDDEN_CAPSULE)
    hidden_frame = hidden_reference_frame(underlay, hidden_variants, pixel_oracle,
                                          masks, blue, selected_oracle)
    hidden_panel = panel_pixel_check(hidden_frame, {"special": 0x49, "extra": 0x15},
                                     hidden_variants, HIDDEN_BUILD, underlay,
                                     pixel_oracle, masks, blue)
    assert hidden_panel["word_pixels"]["classification"] == "pixel_match"
    assert hidden_panel["random_letters"]["all_slots_match"] and hidden_panel["hearts"]["all_slots_match"]
    unlit_words = word_oracle(HIDDEN_CAPSULE, masks=(0, 0))
    synthetic_broken = hidden_reference_frame(underlay, hidden_variants, pixel_oracle,
                                              masks, blue, unlit_words)
    synthetic_broken_panel = panel_pixel_check(synthetic_broken,
        {"special": 0x49, "extra": 0x15}, hidden_variants, HIDDEN_BUILD,
        underlay, pixel_oracle, masks, blue)
    assert synthetic_broken_panel["word_pixels"]["classification"] == "pixel_mismatch"
    shifted_word = bytearray(hidden_frame)
    selected_tile = next(tile for group in selected_oracle["rows"] for tile in group["tiles"]
                         if tile["selected"])
    tx, ty = selected_tile["cell"]
    shifted_word[ty * 8 * 160 + tx * 4] ^= 0x11
    assert panel_pixel_check(bytes(shifted_word), {"special": 0x49, "extra": 0x15},
        hidden_variants, HIDDEN_BUILD, underlay, pixel_oracle, masks, blue)[
            "word_pixels"]["classification"] == "pixel_mismatch"
    try:
        check_word_tiles(hidden_frame, word_oracle(HIDDEN_CAPSULE, masks=(0x41, 0x15)))
        raise AssertionError("wrong selected-mask mapping negative passed")
    except ProbeError:
        pass
    shifted_letter = bytearray(hidden_frame)
    shifted_letter[112 * 160 + pixel_oracle.SLOT_BYTE_COLS[0]] ^= 0x01
    letter_negative = panel_pixel_check(bytes(shifted_letter), {"special": 0x49, "extra": 0x15},
        hidden_variants, HIDDEN_BUILD, underlay, pixel_oracle, masks, blue)
    assert not letter_negative["random_letters"]["all_slots_match"]
    shifted_heart = bytearray(hidden_frame)
    shifted_heart[136 * 160 + pixel_oracle.SLOT_BYTE_COLS[0]] ^= 0x01
    heart_negative = panel_pixel_check(bytes(shifted_heart), {"special": 0x49, "extra": 0x15},
        hidden_variants, HIDDEN_BUILD, underlay, pixel_oracle, masks, blue)
    assert not heart_negative["hearts"]["all_slots_match"]
    natural_owner_pair = [
        {"back_owner": 0, "selected_back_base": 0x60000,
         "gime_scanout": {"base": HIDDEN_SCANOUT_BASE, "owner": 2, "mode": 0x80, "vres": 0x1E},
         "pending": 0, "hold_state": 3, "hold_saved_front": 1, "hold_saved_back": 0,
         "letter_variants": hidden_variants,
         "pixel_checks": hidden_panel},
        {"back_owner": 1, "selected_back_base": 0x58000,
         "gime_scanout": {"base": HIDDEN_SCANOUT_BASE, "owner": 2, "mode": 0x80, "vres": 0x1E},
         "pending": 0, "hold_state": 3, "hold_saved_front": 1, "hold_saved_back": 0,
         "letter_variants": hidden_variants,
         "pixel_checks": hidden_panel},
    ]
    assert hidden_owner_identity_check(natural_owner_pair,
        {"before": 17, "published": 18})["result"] == "pass"
    for bad_capture, label, expected_error in (
            ([natural_owner_pair[0]], "missing owner", MissingCoverage),
            ([natural_owner_pair[0], {**natural_owner_pair[1], "letter_variants": [2, 4, 9]}],
             "changed random-letter identity", MissingCoverage),
            ([{**natural_owner_pair[0], "selected_back_base": 0x58000}, natural_owner_pair[1]],
             "wrong selected BACK mapping", ProbeError),
            ([{**natural_owner_pair[0], "gime_scanout": {"base": 0x58000, "owner": 1,
                                                           "mode": 0x80, "vres": 0x1E}},
              natural_owner_pair[1]], "wrong actual GIME owner", MissingCoverage),
            (natural_owner_pair, "stale preview publication", MissingCoverage)):
        commit = {"before": 17, "published": 17} if label == "stale preview publication" else {"before": 17, "published": 18}
        try:
            hidden_owner_identity_check(bad_capture, commit)
            raise AssertionError(label + " negative passed")
        except expected_error:
            pass
    hidden_product_negative = hidden_owner_identity_check(
        [{**natural_owner_pair[0], "pixel_checks": synthetic_broken_panel}, natural_owner_pair[1]],
        {"before": 17, "published": 18})
    assert hidden_product_negative["result"] == "product_reproduced"
    strict_import_check(Path(__file__).resolve())
    return {"result": "pass", "checks": 46,
            "checks_scope": "pre-existing pixel/BUG-046 oracle checks only",
            "stage_entry_checks": {"result": "pass", "count": len(stage_entry_assertions),
                                   "groups": stage_entry_assertions},
             "stage_state_evidence_positive": True,
             "stage_state_evidence_negatives_rejected": [label for _, label in state_negatives],
             "valid_state_product_discrepancy_preserved": True,
             "pinned_build_revision_identities_qualified": {
                 identity: revision for _, revision, identity in pinned_identities},
             "unknown_build_path_rejected": True,
            "word_tiles": positive["tiles_checked"],
            "good_fixture": positive["sha256"], "all_gray_rejected": True,
            "changed_masks_rejected": True,
            "missing_crop_rejected": True, "deadline_floor_rejected": True,
            "same_phase_read_wait_clamp": True, "zero_budget_no_rpc": True,
            "method_restoration": True,
            "import_socket_process_denied": True,
            "source_staged_cpu_physical_site_positive": True,
            "wrong_par_mapping_rejected_before_read": True,
            "physical_site_mismatch_rejected": True,
            "unauthorized_guest_write_input_rejected": True,
            "scheduled_semantic_boundary_clocks_ignored": True,
            "scheduled_facing_only_difference_ignored": True,
            "scheduled_cell_step_framebuffer_negatives_rejected": True,
            "missing_duplicate_ordinal_rejected": True,
            "unsampled_held_input_is_missing_coverage": True,
            "banked_helper_source_staged_cpu_physical_positive": True,
            "banked_helper_wrong_PAR5_rejected_before_read": True,
            "banked_helper_physical_mismatch_rejected": True,
            "synthetic_known_good_words_letters_hearts_match": True,
            "synthetic_broken_all_gray_words_rejected": True,
            "modified_word_glyph_rejected": True,
            "wrong_selected_mask_mapping_rejected": True,
            "shifted_random_letter_rejected": True,
            "shifted_heart_rejected": True,
            "missing_hidden_owner_is_missing_coverage": True,
            "changed_random_letter_identity_is_missing_coverage": True,
            "wrong_selected_BACK_mapping_rejected": True,
            "wrong_actual_GIME_owner_is_missing_coverage": True,
            "hidden_word_pixel_failure_rejected": True,
            "stale_preview_publication_is_missing_coverage": True,
            "hidden_oracle": oracle_info}


def _monitor_module() -> Any:
    path = ROOT / "scripts" / "verify_bug009_monitor_input.py"
    spec = importlib.util.spec_from_file_location("bug009_monitor_for_stage_preview", path)
    if spec is None or spec.loader is None:
        raise ProbeError("cannot load maintained monitor helper")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_bytes(client: DeadlineClient, address: int, length: int, space: str = "cpu") -> bytes:
    output = bytearray()
    pos = 0
    while pos < length:
        count = min(MAX_READ, length - pos)
        result = client.raw.call("read_memory", {"addr": address + pos, "length": count,
                                                  "space": space}, timeout=5.0)
        data = bytes.fromhex(result["data"])
        if len(data) != count:
            raise ProbeError("short monitor memory read")
        output.extend(data)
        pos += count
    return bytes(output)


def read_byte(client: DeadlineClient, address: int) -> int:
    return read_bytes(client, address, 1)[0]


def read_word(client: DeadlineClient, address: int) -> int:
    return int.from_bytes(read_bytes(client, address, 2), "big")


def read_main_physical(client: DeadlineClient, address: int, length: int) -> bytes:
    if address < 0xC000 or address + length > 0xFE00:
        raise ProbeError("main runtime physical read leaves C000-FDFF")
    pieces = []
    cursor, end = address, address + length
    while cursor < end:
        page_start = 0xC000 if cursor < 0xE000 else 0xE000
        page = 0x3E if cursor < 0xE000 else 0x3F
        boundary = 0xE000 if page == 0x3E else 0xFE00
        count = min(end, boundary) - cursor
        pieces.append(read_bytes(client, page * 0x2000 + cursor - page_start, count, "physical"))
        cursor += count
    return b"".join(pieces)


def read_cycles(client: DeadlineClient) -> dict[str, Any]:
    value = client.raw.call("read_cycles", timeout=5.0)
    return {key: value[key] for key in sorted(value) if key in ("event_ticks", "cpu_cycles")}


class Breakpoint:
    def __init__(self, client: DeadlineClient, budget: PhaseBudget, address: int, label: str,
                 qualifier: Callable[[int], dict[str, Any]]):
        self.client, self.budget, self.address, self.label = client, budget, address, label
        self.qualifier = qualifier
        self.ident = client.raw.call("set_breakpoint", {"addr": address, "kind": "exec"}, timeout=3.0)["id"]

    def hit(self) -> dict[str, Any]:
        timeout = self.budget.stop(self.label)
        self.client.raw.call("run", timeout=min(2.0, timeout))
        result = self.client.raw.call("wait_for_stop", {"timeout_ms": int(timeout * 1000)},
                                      timeout=timeout)
        if result.get("reason") == "timeout":
            raise PhaseDeadline("synchronous stop wait expired at " + self.label)
        pc = int(result.get("pc", -1))
        if pc != self.address:
            raise ProbeError("unexpected stop at %04x while waiting for %s" % (pc, self.label))
        # Every hit is source/staged/live/physical qualified before the caller
        # is allowed to interpret any state predicate at this PC.
        result["site_proof"] = self.qualifier(pc)
        self.client.last_qualified_marker = {"label": self.label, "pc": hex(pc),
                                             "proof": result["site_proof"]}
        return result

    def close(self) -> None:
        if self.ident is not None and self.budget.remaining() > READ_RESERVE:
            self.client.raw.call("clear_breakpoint", {"id": self.ident}, timeout=2.0)
        self.ident = None


def symbols_for(build: Path, filename: str) -> dict[str, int]:
    return parse_symbols(build / filename)


def listing_byte_map(path: Path) -> dict[int, int]:
    result: dict[int, int] = {}
    row = re.compile(r"^([0-9A-Fa-f]{4})\s+((?:[0-9A-Fa-f]{2}){1,16})\s+\(")
    for line in path.read_text(encoding="utf-8").splitlines():
        match = row.match(line)
        if match is None:
            continue
        address = int(match.group(1), 16)
        data = bytes.fromhex(match.group(2))
        for offset, value in enumerate(data):
            # Listings can show alternate sections at the same address. Any
            # disagreement is ambiguous and must fail closed.
            old = result.get(address + offset)
            if old is not None and old != value:
                raise ProbeError("source listing has conflicting bytes at %04x" % (address + offset))
            result[address + offset] = value
    return result


class SiteQualifier:
    """Cached listing/artifact identities plus a cheap per-hit live proof."""
    def __init__(self, build: Path):
        self.build = build
        self.main = (build / "ladybug-runtime.rom").read_bytes()
        self.enemy = (build / "ladybug-enemy-runtime.rom").read_bytes()
        self.presentation = (build / "ladybug-presentation-runtime.bin").read_bytes()
        self.active = (build / "ladybug-adaptive-active.bin").read_bytes()
        self.helper = (build / "ladybug-highscore-helper.bin").read_bytes()
        self.hold_helper = (build / "ladybug-perimeter-reset-helper.bin").read_bytes()
        self.listings = {
            "main": listing_byte_map(build / "ladybug.lst"),
            "enemy": listing_byte_map(build / "ladybug-enemy-runtime.lst"),
            "presentation": listing_byte_map(build / "ladybug-presentation-runtime.lst"),
            "active": listing_byte_map(build / "ladybug-adaptive-active.lst"),
            "banked_helper": listing_byte_map(build / "ladybug-highscore-helper.lst"),
            "hold_helper": listing_byte_map(build / "ladybug-perimeter-reset-helper.lst"),
        }
        self.main_origin = min(self.listings["main"])
        self.enemy_origin = min(self.listings["enemy"])
        self.presentation_origin = min(self.listings["presentation"])
        self.active_origin = min(self.listings["active"])
        self.helper_origin = min(self.listings["banked_helper"])
        self.hold_helper_origin = min(self.listings["hold_helper"])
        layout = json.loads((build / "ladybug-sparse-layout.json").read_text(encoding="utf-8"))
        placement = layout.get("highscore_helper", {})
        if (self.main_origin != 0xC000 or self.enemy_origin != ENEMY_ORIGIN or
                self.presentation_origin != PRES or self.active_origin != ACTIVE_ORIGIN or
                self.helper_origin != placement.get("stage_address") or
                placement.get("stage_page") != HIDDEN_HELPER_PAGE or
                placement.get("bytes") != len(self.helper) or
                placement.get("sha256") != sha(self.helper) or
                self.hold_helper_origin != HIDDEN_HOLD_HELPER_ORIGIN or
                max(self.listings["hold_helper"]) - self.hold_helper_origin + 1 != len(self.hold_helper)):
            raise ProbeError("module origins or banked-helper placement differ from the pinned listings/layout")

    def qualify(self, client: DeadlineClient, address: int, kind: str) -> dict[str, Any]:
        if kind == "main" and self.main_origin <= address < 0xFE00:
            artifact, source_addr, par_indexes = self.main, address - self.main_origin, (6, 7)
            expected_pars = (0x3E, 0x3F)
            physical_page = 0x3E if address < 0xE000 else 0x3F
            physical_offset = address - (0xC000 if address < 0xE000 else 0xE000)
        elif kind == "enemy" and self.enemy_origin <= address < self.enemy_origin + len(self.enemy):
            artifact, source_addr, par_indexes = self.enemy, address - self.enemy_origin, (0,)
            expected_pars = (0x38,)
            physical_page, physical_offset = 0x38, address
        elif kind == "presentation" and self.presentation_origin <= address < self.presentation_origin + len(self.presentation):
            artifact, source_addr, par_indexes = self.presentation, address - self.presentation_origin, (0,)
            expected_pars = (0x38,)
            physical_page, physical_offset = 0x38, address
        elif kind == "active" and self.active_origin <= address < self.active_origin + len(self.active):
            artifact, source_addr, par_indexes = self.active, address - self.active_origin, (0,)
            expected_pars = (0x38,)
            physical_page, physical_offset = 0x38, address
        elif kind == "banked_helper" and self.helper_origin <= address < self.helper_origin + len(self.helper):
            artifact, source_addr, par_indexes = self.helper, address - self.helper_origin, (5,)
            expected_pars = (HIDDEN_HELPER_PAGE,)
            physical_page, physical_offset = HIDDEN_HELPER_PAGE, address - 0xA000
        elif kind == "hold_helper" and self.hold_helper_origin <= address < self.hold_helper_origin + len(self.hold_helper):
            artifact, source_addr, par_indexes = self.hold_helper, address - self.hold_helper_origin, (0,)
            expected_pars = (0x38,)
            physical_page, physical_offset = 0x38, address
        else:
            raise ProbeError("live PC is outside its declared source/staged module: %04x %s" % (address, kind))
        count = min(16, len(artifact) - source_addr)
        if count != 16:
            raise ProbeError("source/staged site window is shorter than 16 bytes")
        listing = self.listings[kind]
        if any(address + offset not in listing for offset in range(count)):
            raise ProbeError("source listing lacks complete site bytes at %04x" % address)
        source = bytes(listing[address + offset] for offset in range(count))
        staged = artifact[source_addr:source_addr + count]
        if source != staged:
            raise ProbeError("source listing and staged site bytes differ at %04x" % address)
        before = client.raw.call("read_gime_state", timeout=3.0)
        if len(before["pars"]["task0"]) != 8 or len(before["pars"]["task1"]) != 8:
            raise ProbeError("GIME view did not return complete FFA0-FFA7/task maps")
        task0 = tuple(int(before["pars"]["task0"][index]) for index in par_indexes)
        if (before["mmu_task"] != 0 or int(before["pars"]["task0"][0]) != 0x38 or
                task0 != expected_pars):
            raise ProbeError("live site PAR/MMU mapping mismatch at %04x" % address)
        live = read_bytes(client, address, count)
        physical = read_bytes(client, physical_page * 0x2000 + physical_offset,
                              count, "physical")
        after = client.raw.call("read_gime_state", timeout=3.0)
        if (before["pars"] != after["pars"] or before["registers"] != after["registers"] or
                before["mmu_task"] != after["mmu_task"]):
            raise ProbeError("live site mapping changed during byte proof at %04x" % address)
        if live != staged or physical != staged:
            raise ProbeError("source/staged/CPU/physical site bytes differ at %04x" % address)
        return {"kind": kind, "address": hex(address), "length": count,
                "source_sha256": sha(source), "staged_sha256": sha(staged),
                "cpu_sha256": sha(live), "physical_sha256": sha(physical),
                "physical_page": physical_page, "task0_pars": list(before["pars"]["task0"]),
                "task1_pars": list(before["pars"]["task1"]), "mmu_task": before["mmu_task"]}


def live_image_check(client: DeadlineClient, build: Path) -> dict[str, Any]:
    _, _, source_revision, _ = pinned_build_identity(build)
    runtime = (build / "ladybug-runtime.rom").read_bytes()
    presentation = (build / "ladybug-presentation-runtime.bin").read_bytes()
    if len(runtime) != 0x4000:
        raise ProbeError("runtime ROM is not 16 KiB")
    # The CPU window ends at FDFF. The two physical MMU pages and PAR pair are
    # checked independently; FF00-FFFF is read only through XRoar's GIME view.
    gime = client.raw.call("read_gime_state", timeout=5.0)
    pars = gime["pars"]["task0"]
    if (len(pars) != 8 or len(gime["pars"]["task1"]) != 8 or
            gime["mmu_task"] != 0 or (int(pars[6]), int(pars[7])) != (0x3E, 0x3F)):
        raise ProbeError("runtime C000-FDFF PAR6/7 identity mismatch")
    live_runtime = read_bytes(client, 0xC000, 0x3E00)
    if live_runtime != runtime[:0x3E00]:
        raise ProbeError("live CPU runtime C000-FDFF differs from staged ROM")
    physical_runtime = (read_bytes(client, 0x3E * 0x2000, 0x2000, "physical") +
                        read_bytes(client, 0x3F * 0x2000, 0x1E00, "physical"))
    if physical_runtime != runtime[:0x3E00]:
        raise ProbeError("physical pages3E/3F differ from staged runtime C000-FDFF")
    par0 = int(gime["pars"]["task0"][0])
    live_presentation = read_bytes(client, PRES, len(presentation))
    physical_presentation = read_bytes(client, par0 * 0x2000 + PRES,
                                       len(presentation), "physical")
    if par0 != 0x38 or live_presentation != presentation or physical_presentation != presentation:
        raise ProbeError("live CPU/physical presentation bytes do not match staged module")
    after = client.raw.call("read_gime_state", timeout=5.0)
    if gime["pars"] != after["pars"] or gime["registers"] != after["registers"]:
        raise ProbeError("GIME mapping changed during live module qualification")
    return {"runtime_sha256": sha(live_runtime), "runtime_physical_sha256": sha(physical_runtime),
            "presentation_sha256": sha(live_presentation),
            "runtime_artifact_bytes": len(runtime), "runtime_live_bytes": len(live_runtime),
            "presentation_bytes": len(presentation),
            "presentation_physical_sha256": sha(physical_presentation),
            "presentation_par0": par0, "gime_registers": gime["registers"],
            "task0_pars": gime["pars"]["task0"], "task1_pars": gime["pars"]["task1"],
            "source_revision": source_revision}


def physical_frame(client: DeadlineClient, owner: int) -> tuple[bytes, dict[str, Any]]:
    if owner not in (0, 1):
        raise ProbeError("invalid framebuffer owner")
    gime = client.raw.call("read_gime_state", timeout=5.0)
    if gime["mmu_task"] != 0 or int(gime["pars"]["task0"][0]) != 0x38:
        raise ProbeError("PAR0/MMU is not pinned before FRONT metadata reads")
    front = read_byte(client, FRONT)
    pending = read_byte(client, PENDING)
    seq = read_word(client, COMMIT)
    regs = gime["registers"]
    mode, vres = int(regs["FF98"]), int(regs["FF99"])
    v1, v0 = int(regs["FF9D"]), int(regs["FF9E"])
    phys_base = (0x30 if owner == 0 else 0x2C) * 0x2000
    scan_base = v1 * 0x800 + v0 * 0x200
    if (front, pending, mode, vres, scan_base) != (owner, 0, 0x80, 0x1E, phys_base):
        raise ProbeError("FRONT/GIME scanout identity is not stable and source-qualified")
    frame = read_bytes(client, phys_base, 30720, "physical")
    after_gime = client.raw.call("read_gime_state", timeout=5.0)
    after_regs = after_gime["registers"]
    after = (read_byte(client, FRONT), read_byte(client, PENDING), read_word(client, COMMIT),
             int(after_regs["FF98"]), int(after_regs["FF99"]),
             int(after_regs["FF9D"]), int(after_regs["FF9E"]))
    if (after != (front, pending, seq, mode, vres, v1, v0) or
            gime["pars"] != after_gime["pars"] or gime["mmu_task"] != after_gime["mmu_task"]):
        raise ProbeError("framebuffer publication changed during physical read")
    return frame, {"owner": owner, "front": front, "pending": pending, "commit_seq": seq,
                   "gime_mode": mode, "gime_vres": vres, "voff": [v1, v0],
                   "task0_pars": gime["pars"]["task0"], "task1_pars": gime["pars"]["task1"],
                   "physical_base": phys_base,
                   "frame_sha256": sha(frame)}


def gime_scanout_identity(gime: dict[str, Any]) -> dict[str, int]:
    regs = gime["registers"]
    mode, vres = int(regs["FF98"]), int(regs["FF99"])
    high, low = int(regs["FF9D"]), int(regs["FF9E"])
    base = high * 0x800 + low * 0x200
    return {"mode": mode, "vres": vres, "base": base,
            "owner": {0x60000: 0, 0x58000: 1, 0x50000: 2}.get(base, -1)}


def capture_hidden_back(client: DeadlineClient, site_proofs: list[dict[str, Any]]) -> tuple[bytes, dict[str, Any]]:
    """Capture the selected hidden BACK while proving the independent GIME scanout owner."""
    before_gime = client.raw.call("read_gime_state", timeout=4.0)
    if before_gime["mmu_task"] != 0 or int(before_gime["pars"]["task0"][0]) != 0x38:
        raise ProbeError("PAR0/MMU does not map the direct-page state at helper return")
    if int(before_gime["pars"]["task0"][5]) != 0x23:
        raise ProbeError("helper-return PAR5 does not match receipt-qualified caller mapping $23")
    low_cpu = read_bytes(client, 0, 0x100)
    low_physical = read_bytes(client, 0x38 * 0x2000, 0x100, "physical")
    if low_cpu != low_physical:
        raise ProbeError("helper-return direct-page CPU/physical metadata bytes differ")
    state = {"front": low_cpu[FRONT], "back_owner": low_cpu[BACK],
             "pending": low_cpu[PENDING], "commit_seq": int.from_bytes(low_cpu[COMMIT:COMMIT + 2], "big"),
             "hold_state": low_cpu[PRES_HOLD_STATE],
             "hold_saved_front": low_cpu[PRES_HOLD_SAVED_FRONT],
             "hold_saved_back": low_cpu[PRES_HOLD_SAVED_BACK],
             "hold_owner": low_cpu[PRES_HOLD_OWNER],
             "stage": low_cpu[STAGE], "screen": low_cpu[PRES_SCREEN],
             "context": low_cpu[PRES_CONTEXT], "masks": {"special": low_cpu[SPECIAL],
                                                           "extra": low_cpu[EXTRA]},
             "letter_variants": list(low_cpu[STAGE_LETTER_VARIANTS:STAGE_LETTER_VARIANTS + 3]),
             "gime_scanout": gime_scanout_identity(before_gime),
             "task0_pars": list(before_gime["pars"]["task0"]),
             "task1_pars": list(before_gime["pars"]["task1"]),
             "site_proofs": site_proofs}
    owner = state["back_owner"]
    expected_base = {0: 0x60000, 1: 0x58000}.get(owner)
    if expected_base is None or owner == state["front"]:
        raise MissingCoverage("helper return did not select a hidden BACK0/BACK1 destination")
    expected_pars = {0: (0x30, 0x31, 0x32, 0x33),
                     1: (0x2C, 0x2D, 0x2E, 0x2F)}[owner]
    observed_pars = tuple(int(value) for value in before_gime["pars"]["task0"][1:5])
    if observed_pars != expected_pars:
        raise ProbeError("receipt-qualified map_back did not map selected BACK%d through PAR1-PAR4" % owner)
    if state["pending"] != 0 or state["hold_state"] != 3:
        raise MissingCoverage("helper return was not a stable HYDRATE crop with no pending publication")
    if state["gime_scanout"] != {"mode": 0x80, "vres": 0x1E, "base": HIDDEN_SCANOUT_BASE, "owner": 2}:
        raise MissingCoverage("actual GIME scanout did not remain on compatibility owner2")
    if len(state["letter_variants"]) != 3 or any(value >= 12 for value in state["letter_variants"]):
        raise MissingCoverage("captured random-letter variant identities are invalid")
    frame = read_bytes(client, expected_base, 30720, "physical")
    after_gime = client.raw.call("read_gime_state", timeout=4.0)
    low_after = read_bytes(client, 0, 0x100)
    low_after_physical = read_bytes(client, 0x38 * 0x2000, 0x100, "physical")
    if (low_after != low_after_physical or low_after != low_cpu or
            before_gime["pars"] != after_gime["pars"] or
            before_gime["registers"] != after_gime["registers"] or
            before_gime["mmu_task"] != after_gime["mmu_task"]):
        raise ProbeError("hidden crop or independent scanout changed during physical reads")
    state.update({"selected_back_base": expected_base,
                  "selected_back_frame_sha256": sha(frame),
                  "scanout_owner": 2, "scanout_base": HIDDEN_SCANOUT_BASE,
                  "direct_page_source_physical_match": True})
    return frame, state


def hidden_offline_qualification() -> dict[str, Any]:
    candidate = artifact_check(HIDDEN_BUILD)
    broken = artifact_check(BUILD_DEFAULT)
    static = offline_hidden_owner_check(HIDDEN_BUILD, BUILD_DEFAULT)
    underlay, oracle_info, pixel_oracle, masks, blue = hidden_underlay(HIDDEN_BUILD)
    variants = [2, 4, 8]
    good_words = word_oracle(HIDDEN_CAPSULE)
    good_frame = hidden_reference_frame(underlay, variants, pixel_oracle, masks, blue, good_words)
    good_pixels = panel_pixel_check(good_frame, {"special": 0x49, "extra": 0x15},
                                    variants, HIDDEN_BUILD, underlay, pixel_oracle, masks, blue)
    broken_words = word_oracle(HIDDEN_CAPSULE, masks=(0, 0))
    broken_frame = hidden_reference_frame(underlay, variants, pixel_oracle, masks, blue, broken_words)
    broken_pixels = panel_pixel_check(broken_frame, {"special": 0x49, "extra": 0x15},
                                      variants, HIDDEN_BUILD, underlay, pixel_oracle, masks, blue)
    broken_unlit_tile = next(tile for group in broken_words["rows"] for tile in group["tiles"]
                             if group["word"] == "SPECIAL" and tile["cell"] == [1, 1])
    capture_bytes = HIDDEN_BASELINE_CAPTURE.read_bytes()
    if sha(capture_bytes) != HIDDEN_BASELINE_CAPTURE_SHA:
        raise ProbeError("pinned historical broken visible preview evidence changed")
    historical = json.loads(capture_bytes.decode("utf-8"))
    publication = historical.get("preview_publication", {})
    findings = historical.get("known_bug046_findings", [])
    word_error = next((item.get("detail", {}).get("error", "") for item in findings
                       if item.get("kind") == "word-pixel-mismatch"), "")
    match = re.search(r"actual=([0-9a-f]{64}) expected=([0-9a-f]{64})", word_error)
    if (historical.get("pins", {}).get("rom_sha256") != ROM_SHA or
            publication.get("owner") != 1 or publication.get("physical_base") != 0x58000 or
            publication.get("stored_masks", {}).get("actual") != {"special": 0x49, "extra": 0x15} or
            match is None or match.group(1) != broken_unlit_tile["expected_sha256"] or
            match.group(2) != good_words["rows"][0]["tiles"][0]["expected_sha256"] or
            publication.get("frame_bytes") is not None):
        raise ProbeError("historical visible broken crop does not bind to the pinned unlit/selected word fixtures")
    if (good_pixels["word_pixels"]["classification"] != "pixel_match" or
            not good_pixels["random_letters"]["all_slots_match"] or
            not good_pixels["hearts"]["all_slots_match"] or
            broken_pixels["word_pixels"]["classification"] != "pixel_mismatch" or
            not broken_pixels["random_letters"]["all_slots_match"] or
            not broken_pixels["hearts"]["all_slots_match"]):
        raise ProbeError("synthetic known-good/known-broken oracle qualification failed")
    return {
        "candidate": candidate, "frozen_broken": broken,
        "source_site_check": static,
        "oracle_inputs": oracle_info,
        "synthetic_good_fixture": {"classification": "pass", "selected_letter_variants": variants,
                                   "word_tiles": good_pixels["word_pixels"],
                                   "letters_pass": good_pixels["random_letters"]["all_slots_match"],
                                   "hearts_pass": good_pixels["hearts"]["all_slots_match"]},
        "synthetic_broken_fixture": {"classification": "word_pixel_mismatch",
                                     "SPECIAL_1_1_unlit_sha256": broken_unlit_tile["expected_sha256"],
                                     "letters_pass": broken_pixels["random_letters"]["all_slots_match"],
                                     "hearts_pass": broken_pixels["hearts"]["all_slots_match"]},
        "historical_broken_visible_evidence": {
            "path": str(HIDDEN_BASELINE_CAPTURE), "sha256": HIDDEN_BASELINE_CAPTURE_SHA,
            "rom_sha256": ROM_SHA, "visible_owner": publication["owner"],
            "visible_physical_base": publication["physical_base"],
            "visible_frame_sha256": publication.get("frame_sha256"),
            "SPECIAL_1_1_actual_sha256": match.group(1),
            "SPECIAL_1_1_expected_selected_sha256": match.group(2),
            "actual_hash_matches_synthetic_unlit": True,
            "crop_bytes_retained": False,
            "proves_hidden_BACK0_baseline": False},
        "runtime_source_CPU_physical_mapping_qualified": False,
        "actual_GIME_hidden_scanout_qualified": False,
        "current_candidate_hidden_crops_observed": False,
        "classification": "offline-only; synthetic good/broken and historical visible owner1 evidence are distinct"}


def state_snapshot(client: DeadlineClient) -> dict[str, Any]:
    gime_before = client.raw.call("read_gime_state", timeout=5.0)
    if (len(gime_before["pars"]["task0"]) != 8 or
            len(gime_before["pars"]["task1"]) != 8 or
            int(gime_before["pars"]["task0"][0]) != 0x38):
        raise ProbeError("PAR0 is not the pinned low-state page before direct-page snapshot")
    low = read_bytes(client, 0, 0x100)
    gime = client.raw.call("read_gime_state", timeout=5.0)
    if int(gime["pars"]["task0"][5]) != 0x34:
        raise ProbeError("PAR5 is not the pinned maze/state page before A000 snapshot")
    state = read_bytes(client, MAZE_STATE, 0x2000)
    state_physical = read_bytes(client, 0x34 * 0x2000, 0x2000, "physical")
    if state != state_physical:
        raise ProbeError("A000-BFFF state CPU/physical pages differ")
    owner_frames = {}
    for owner in (0, 1):
        base = (0x30 if owner == 0 else 0x2C) * 0x2000
        owner_frames[str(owner)] = sha(read_bytes(client, base, 30720, "physical"))
    regs = client.raw.call("read_registers", timeout=5.0)
    cycles = read_cycles(client)
    gime = client.raw.call("read_gime_state", timeout=5.0)
    if gime_before["pars"] != gime["pars"] or gime_before["registers"] != gime["registers"]:
        raise ProbeError("GIME map changed during predecessor snapshot")
    return {"low_ram_sha256": sha(low), "state_window_a000_bfff_sha256": sha(state),
            "owner_frames_sha256": owner_frames, "cycles": cycles,
            "cpu_regs": {k: regs.get(k) for k in ("pc", "dp", "s", "cc")},
            "gime_registers": gime["registers"], "task0_pars": gime["pars"]["task0"],
            "task1_pars": gime["pars"]["task1"],
            "task0_par_span": ["FFA0", "FFA7"], "task1_par_span": ["FFA8", "FFAF"],
            "scripted_keys_down": sorted(client.key_down), "ram_init": "clear",
            "state_cpu_physical_match": True,
            "front_back_pending_commit": read_bytes(client, FRONT, 5).hex()}


def run_to_condition(client: DeadlineClient, budget: PhaseBudget, address: int,
                     label: str, predicate: Callable[[], bool],
                     qualifier: Callable[[int], dict[str, Any]],
                     observe: Callable[[], None] | None = None) -> dict[str, Any]:
    bp = Breakpoint(client, budget, address, label, qualifier)
    last: dict[str, Any] = {}
    try:
        while True:
            last = bp.hit()
            if observe is not None:
                observe()
            if predicate():
                return last
    finally:
        bp.close()


def launch_owned(binary: Path, rom: Path, budget: PhaseBudget, monitor: Any) -> tuple[Any, Any]:
    if not binary.is_file():
        raise ProbeError("repository XRoar binary not found: " + str(binary))
    port_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        port_sock.bind(("127.0.0.1", 0))
        port = int(port_sock.getsockname()[1])
    finally:
        port_sock.close()
    argv = [str(binary), "-ui", "null", "-ao", "null", "-machine", "coco3", "-ram", "512",
            "-cart-type", "gmc", "-cart-rom", str(rom), "-cart-autorun", "-no-ratelimit",
            "-ram-init", "clear", "-monitor", "127.0.0.1:%d" % port, "-monitor-halt-on-start"]
    process = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               start_new_session=(os.name != "nt"))
    deadline = budget.deadline - READ_RESERVE
    last_error: Exception | None = None
    sock = None
    client = None
    try:
        while time.monotonic() < deadline:
            left = budget.require("monitor connect")
            try:
                sock = socket.create_connection(("127.0.0.1", port), timeout=min(0.25, left))
                sock.settimeout(min(0.25, budget.require("monitor hello")))
                client = monitor.MonitorClient(sock)
                hello = json.loads(client.file.readline())
                if hello.get("method") != "hello":
                    raise ProbeError("unexpected monitor greeting")
                result = DeadlineClient(client, budget, dict(FIXTURE),
                                        {KEY_COIN, KEY_ENTER, KEY_UP, KEY_DOWN})
                result.raw.call("events.subscribe", {"kinds": ["bp"]}, timeout=3.0)
                return process, result
            except (OSError, ValueError, ProbeError) as exc:
                last_error = exc
                if sock is not None:
                    try:
                        sock.close()
                    except OSError:
                        pass
                    sock = None
                client = None
                time.sleep(min(0.025, max(0.0, budget.require("monitor retry")) / 4))
        raise ProbeError("monitor connection missing within whole-phase bound: %r" % last_error)
    except BaseException:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass
        elif sock is not None:
            try:
                sock.close()
            except OSError:
                pass
        if process.poll() is None:
            process.kill()
        try:
            process.wait(timeout=2)
        except Exception:
            pass
        raise


def marker_addr(symbols: dict[str, int], name: str) -> int:
    if name not in symbols:
        raise ProbeError("required frozen map symbol missing: " + name)
    return symbols[name]


def source_neighbor_gate(client: DeadlineClient, symbols: dict[str, int], build: Path,
                         origin: tuple[int, int], target: tuple[int, int],
                         require_flower: bool) -> dict[str, Any]:
    if target != (origin[0], origin[1] - 1) or not (0 <= origin[0] < 24 and 1 <= origin[1] < 24):
        raise ProbeError("only the approved one-cell north edge is permitted")
    gime = client.raw.call("read_gime_state", timeout=3.0)
    if (gime["mmu_task"] != 0 or int(gime["pars"]["task0"][0]) != 0x38 or
            int(gime["pars"]["task0"][5]) != 0x34 or
            (int(gime["pars"]["task0"][6]), int(gime["pars"]["task0"][7])) != (0x3E, 0x3F)):
        raise ProbeError("PAR5 or main runtime PAR6/7 is not pinned before state/nav decode")
    x, y = read_byte(client, PLAYER_X), read_byte(client, PLAYER_Y)
    if (x, y) != origin:
        raise ProbeError("stage-1 player is not at the approved source cell %r" % (origin,))
    maze = read_bytes(client, MAZE_STATE, 24 * 24)
    maze_physical = read_bytes(client, 0x34 * 0x2000, 24 * 24, "physical")
    if maze != maze_physical:
        raise ProbeError("A000 maze state CPU/physical bytes differ")
    offset = target[1] * 24 + target[0]
    entity_count = read_byte(client, ENTITY_COUNT)
    if not 0 <= entity_count <= 12:
        raise ProbeError("live entity count is outside the source table capacity")
    entities = read_bytes(client, ENTITY_TABLE, entity_count * 4)
    entities_physical = read_bytes(client, 0x34 * 0x2000 + (ENTITY_TABLE - 0xA000),
                                   entity_count * 4, "physical")
    if entities != entities_physical:
        raise ProbeError("entity table CPU/physical bytes differ")
    occupied = [i for i in range(entity_count)
                if entities[4 * i + 2] != 0 and
                (entities[4 * i], entities[4 * i + 1]) == target]
    if occupied:
        raise ProbeError("approved edge target is occupied by active entity records")
    nav_addr = symbols["maze_nav"]
    gate_addr = symbols["maze_gate_owner"]
    if not (0xC000 <= nav_addr < 0xFE00 and 0xC000 <= gate_addr < 0xFE00):
        raise ProbeError("maze nav/gate symbols are outside the pinned runtime window")
    runtime = (build / "ladybug-runtime.rom").read_bytes()
    nav_live = read_bytes(client, nav_addr, 576)
    gates_live = read_bytes(client, gate_addr, 576)
    nav_physical = read_main_physical(client, nav_addr, 576)
    gates_physical = read_main_physical(client, gate_addr, 576)
    nav_expected = runtime[nav_addr - 0xC000:nav_addr - 0xC000 + 576]
    gates_expected = runtime[gate_addr - 0xC000:gate_addr - 0xC000 + 576]
    if (nav_live != nav_expected or gates_live != gates_expected or
            nav_physical != nav_expected or gates_physical != gates_expected):
        raise ProbeError("stage-1 nav/gate tables differ from pinned staged runtime")
    after_gime = client.raw.call("read_gime_state", timeout=3.0)
    if gime["pars"] != after_gime["pars"] or gime["registers"] != after_gime["registers"]:
        raise ProbeError("GIME mapping changed during stage-1 state/nav qualification")
    origin_nav = nav_live[y * 24 + x]
    target_nav = nav_live[offset]
    target_cell = maze[offset]
    # can_move tests the origin direction bit and reciprocal target bit;
    # a zero gate-owner byte selects the source regular-cell branch.
    if not (origin_nav & 0x01) or not (target_nav & 0x04) or gates_live[offset] != 0:
        raise ProbeError("approved north edge is not source-admitted for this live state")
    target_is_dot = bool(target_cell & 0x80)
    if require_flower and not target_is_dot:
        raise ProbeError("approved final flower at %r is absent or already collected" % (target,))
    return {"player_cell": [x, y], "target_cell": list(target), "target_byte": target_cell,
            "origin_nav": origin_nav, "target_nav": target_nav, "target_gate_owner": gates_live[offset],
            "entity_count": entity_count, "target_active_entity_indexes": occupied,
            "target_is_dot": target_is_dot, "target_is_unoccupied": True,
            "required_uncollected_flower": require_flower,
            "legal_edge": "north; current and reciprocal target nav bits pass, no target gate owner"}


def apply_fixture(client: DeadlineClient) -> dict[str, Any]:
    gime = client.raw.call("read_gime_state", timeout=3.0)
    if int(gime["pars"]["task0"][0]) != 0x38:
        raise ProbeError("PAR0 is not the pinned runtime page before fixture writes")
    before = {hex(a): read_byte(client, a) for a, _ in FIXTURE}
    before_physical = {hex(a): read_bytes(client, 0x38 * 0x2000 + a, 1, "physical")[0]
                       for a, _ in FIXTURE}
    if before != before_physical:
        raise ProbeError("fixture direct-page CPU/physical bytes differ before writes")
    for address, value in FIXTURE:
        client.raw.call("write_memory", {"addr": address, "data": "%02x" % value}, timeout=2.0)
    if sorted(client.fixture_seen) != sorted(FIXTURE):
        raise ProbeError("fixture write trace does not exactly match four authorized bytes")
    after = {hex(a): read_byte(client, a) for a, _ in FIXTURE}
    after_physical = {hex(a): read_bytes(client, 0x38 * 0x2000 + a, 1, "physical")[0]
                      for a, _ in FIXTURE}
    expected = {hex(a): v for a, v in FIXTURE}
    if after != expected or after_physical != expected:
        raise ProbeError("four-byte fixture readback mismatch")
    after_gime = client.raw.call("read_gime_state", timeout=3.0)
    if gime["pars"] != after_gime["pars"] or gime["registers"] != after_gime["registers"]:
        raise ProbeError("PAR0 mapping changed during four-byte fixture writes")
    return {"before": before, "before_physical": before_physical,
            "after": after, "after_physical": after_physical,
            "writes": [[hex(a), v] for a, v in client.fixture_seen]}


def stage_preview_oracle(client: DeadlineClient, owner: int, build: Path) -> dict[str, Any]:
    state = (read_byte(client, STAGE), read_byte(client, PRES_MODE), read_byte(client, PRES_SCREEN),
             read_byte(client, PRES_CONTEXT))
    if state != (2, 6, 2, 2):
        raise ProbeError("stage-2 level-start preview state mismatch")
    frame, publication = physical_frame(client, owner)
    oracle = word_oracle(build.parent)
    try:
        check = check_word_tiles(frame, oracle)
        product = {"classification": "pixel_match", "check": check}
    except ProbeError as exc:
        product = {"classification": "pixel_mismatch", "error": str(exc)}
    masks = {"special": read_byte(client, SPECIAL), "extra": read_byte(client, EXTRA)}
    publication.update({"screen_role": "level-start", "word_oracle": product,
                        "stored_masks": {"expected": {"special": 0x49, "extra": 0x15},
                                         "actual": masks,
                                         "classification": "match" if masks == {"special": 0x49, "extra": 0x15}
                                         else "mismatch"}})
    return publication


def pose(client: DeadlineClient) -> dict[str, Any]:
    return {"cell": [read_byte(client, PLAYER_X), read_byte(client, PLAYER_Y)],
            "step": read_byte(client, PLAYER_STEP), "fb": hex(read_word(client, PLAYER_FB)),
            "entry_state": read_byte(client, INITIAL_ENTRY)}


def position_sample(client: DeadlineClient) -> dict[str, Any]:
    current = pose(client)
    cycles = read_cycles(client)
    if "event_ticks" not in cycles:
        raise ProbeError("monitor cycle view lacks the approved simulation-tick key")
    tick_value = cycles["event_ticks"]
    event_ticks = int(tick_value, 0) if isinstance(tick_value, str) else int(tick_value)
    return {"event_ticks": event_ticks,
            "position": {"cell": current["cell"], "fb": current["fb"],
                         "step": current["step"]}}


def scheduled_position(record: dict[str, Any], label: str) -> dict[str, Any]:
    if (record.get("movement_ordinal") != 1 or record.get("player_tick_calls") != 1 or
            record.get("draw_ordinal") != 1 or record.get("draw_count") != 1):
        raise ProbeError(label + " does not contain exactly the first player_tick and pt_draw")
    entry, draw = record.get("entry"), record.get("draw")
    if not isinstance(entry, dict) or not isinstance(draw, dict):
        raise ProbeError(label + " is missing its entry/draw snapshots")
    return {"entry": entry["position"], "draw": draw["position"]}


def compare_scheduled_pair(neutral: dict[str, Any], held: dict[str, Any]) -> dict[str, Any]:
    if neutral.get("case") != "neutral" or held.get("case") != "held":
        raise ProbeError("scheduled-step pair must be neutral then held")
    neutral_step, held_step = neutral.get("scheduled_step", {}), held.get("scheduled_step", {})
    n = scheduled_position(neutral_step, "neutral run")
    h = scheduled_position(held_step, "held run")
    held_entry = held_step.get("entry", {})
    if held_entry.get("input", {}).get("joy_dir") != DIR_SOUTH:
        raise MissingCoverage("held Down was not visible in sampled JOY_DIR at first player_tick entry")
    if n["entry"] != h["entry"]:
        raise ProbeError("paired first player_tick entries do not share the approved start position")
    if n["entry"] != {"cell": [12, 22], "fb": "0x89ec", "step": 0}:
        raise ProbeError("first scheduled entry differs from the approved stage-2 start pose")
    neutral_target = {"cell": [12, 22], "fb": "0x88ac", "step": 1}
    if n["draw"] != neutral_target:
        return {"result": "neutral_target_miss", "neutral": n, "held": h,
                "event_ticks_compared": False, "facing_compared": False,
                "same_position": h["draw"] == n["draw"]}
    return {"result": "pass" if h["draw"] == n["draw"] else "position_divergence",
            "neutral": n, "held": h,
            "event_ticks_compared": False,
            "facing_compared": False,
            "same_position": h["draw"] == n["draw"]}


def live_active_caller_check(client: DeadlineClient, build: Path) -> dict[str, Any]:
    start, end = 0x04D5, 0x04E2
    expected = bytes.fromhex("0d4d260c0d6b27080f6bbdcb6b")
    source = listing_byte_map(build / "ladybug-adaptive-active.lst")
    staged = (build / "ladybug-adaptive-active.bin").read_bytes()
    offset = start - ACTIVE_ORIGIN
    if (marker_addr(symbols_for(build, "ladybug-adaptive-active.map"), "atb_no_popup") != start or
            any(start + i not in source for i in range(len(expected)))):
        raise ProbeError("active pending-gate source callsite is not pinned at its approved symbol")
    source_bytes = bytes(source[start + i] for i in range(len(expected)))
    staged_bytes = staged[offset:offset + len(expected)]
    gime = client.raw.call("read_gime_state", timeout=3.0)
    if gime["mmu_task"] != 0 or int(gime["pars"]["task0"][0]) != 0x38:
        raise ProbeError("PAR0/MMU does not map the active player caller")
    cpu = read_bytes(client, start, len(expected))
    physical = read_bytes(client, 0x38 * 0x2000 + start, len(expected), "physical")
    after = client.raw.call("read_gime_state", timeout=3.0)
    if (gime["pars"] != after["pars"] or gime["registers"] != after["registers"] or
            gime["mmu_task"] != after["mmu_task"]):
        raise ProbeError("PAR0/MMU changed during active caller byte qualification")
    if any(data != expected for data in (source_bytes, staged_bytes, cpu, physical)):
        raise ProbeError("active source/staged/CPU/physical caller bytes differ")
    registers = client.raw.call("read_registers", timeout=3.0)
    stack_raw = registers["s"]
    stack = int(stack_raw, 0) if isinstance(stack_raw, str) else int(stack_raw)
    return_pc = read_word(client, stack)
    pending = read_byte(client, PLAYER_TICK_PENDING)
    if return_pc != end:
        raise ProbeError("player_tick entry stack return PC does not prove the scheduled caller JSR")
    if pending != 0:
        raise ProbeError("active scheduled caller did not clear pending before player_tick entry")
    return {"address": hex(start), "length": len(expected), "source_sha256": sha(source_bytes),
            "staged_sha256": sha(staged_bytes), "cpu_sha256": sha(cpu),
            "physical_sha256": sha(physical), "par0": 0x38,
            "return_pc": hex(return_pc), "pending_consumed_before_call": True,
            "entry_pending_expected": 0, "entry_pending_observed": pending}


def scheduled_state(client: DeadlineClient) -> dict[str, Any]:
    fields = (JOY_X, JOY_Y, JOY_DIR, PLAYER_DIR, PLAYER_FACE, PLAYER_WANT,
              PLAYER_MANUAL, PLAYER_TICK_PENDING, PLAYER_X, PLAYER_Y,
              PLAYER_STEP, PLAYER_FB, FRAMES, FB_SIM_SEQ, RENDER_FLAGS,
              RENDER_FLAGS2, FB_RENDER_ACTIVE, INITIAL_ENTRY, DEATH_STATE,
              PICKUP_TIMER, TURN_SNAP, PLAYER_ERASED, PLAYER_BG_VALID,
              FRONT, BACK, PENDING)
    values = {hex(address): read_byte(client, address) for address in fields}
    commit_seq = read_word(client, COMMIT)
    fb = read_word(client, PLAYER_FB)
    fb_offset = fb - 0x8000
    if fb_offset < 0 or fb_offset + 7 * 160 + 4 > 30720:
        raise ProbeError("player framebuffer pointer is outside the pinned 160x192 owner buffer")
    owner_tiles = {}
    for owner, page in ((0, 0x30), (1, 0x2C)):
        base = page * 0x2000
        tile = b"".join(read_bytes(client, base + fb_offset + row * 160, 4, "physical")
                         for row in range(8))
        owner_tiles[str(owner)] = {"page": page, "sha256": sha(tile), "bytes_hex": tile.hex()}
    gime = client.raw.call("read_gime_state", timeout=3.0)
    cycles = read_cycles(client)
    return {"position": {"cell": [values[hex(PLAYER_X)], values[hex(PLAYER_Y)]],
                          "fb": hex(fb), "step": values[hex(PLAYER_STEP)]},
            "input": {"joy_x": values[hex(JOY_X)], "joy_y": values[hex(JOY_Y)],
                      "joy_dir": values[hex(JOY_DIR)], "player_want": values[hex(PLAYER_WANT)],
                      "player_dir": values[hex(PLAYER_DIR)], "player_face": values[hex(PLAYER_FACE)],
                      "player_manual": values[hex(PLAYER_MANUAL)]},
            "flags": {hex(address): values[hex(address)] for address in fields
                      if address not in (JOY_X, JOY_Y, JOY_DIR, PLAYER_DIR, PLAYER_FACE,
                                         PLAYER_WANT, PLAYER_MANUAL, PLAYER_X, PLAYER_Y,
                                         PLAYER_STEP, PLAYER_FB)},
            "frames": read_word(client, FRAMES), "fb_sim_seq": read_word(client, FB_SIM_SEQ),
            "front_back_pending_commit": [values[hex(FRONT)], values[hex(BACK)],
                                          values[hex(PENDING)], commit_seq],
            "framebuffer_player_tile_by_owner": owner_tiles,
            "event_ticks": cycles.get("event_ticks"),
            "gime_registers": gime["registers"], "task0_pars": gime["pars"]["task0"],
            "task1_pars": gime["pars"]["task1"], "mmu_task": gime["mmu_task"]}


def run_hidden_case(args: argparse.Namespace) -> dict[str, Any]:
    if not args.run_live:
        raise ProbeError("hidden-owner runtime requires --run-live and a separate parent runtime lease")
    output = Path(args.output).resolve()
    build = Path(args.build).resolve()
    if build != HIDDEN_BUILD.resolve():
        raise ProbeError("hidden-owner runtime is pinned to the recovered BUG-046 candidate capsule")
    if not inside(output, HIDDEN_OWNED) or output.exists():
        raise ProbeError("hidden-owner output must be a fresh path inside its owned evidence directory")
    cases: dict[str, Any] = {
        "scenario": "hidden-owner", "phases": [], "product_findings": [],
        "scope": "one natural candidate run: hidden BACK0/BACK1 while GIME owner2, then actual preview and first maze scanout",
        "fixture_contract": [[hex(address), value] for address, value in FIXTURE],
        "phase_contract": {"whole_phase_seconds_max": PHASE_SECONDS, "stop_seconds_max": STOP_SECONDS,
                           "stops_per_phase_max": MAX_STOPS, "phases_per_run": 3,
                           "max_runs": 2, "retries": 0},
    }
    process = None
    client = None
    phase: PhaseBudget | None = None
    try:
        cases["pins"] = artifact_check(build)
        cases["source_site_check"] = offline_hidden_owner_check(HIDDEN_BUILD, BUILD_DEFAULT)
        underlay, oracle_info, pixel_oracle, masks, blue = hidden_underlay(build)
        cases["pixel_oracle_inputs"] = oracle_info
        monitor = _monitor_module()
        pres_syms = symbols_for(build, "ladybug-presentation-runtime.map")
        main_syms = symbols_for(build, "ladybug.map")
        site_images = SiteQualifier(build)
        xroar = Path(args.xroar) if args.xroar else ROOT / "docs" / "reference" / "xroar" / "src" / "xroar"

        # Phase 1: the same cold legal predecessor used by the approved natural route.
        phase = PhaseBudget()
        process, client = launch_owned(xroar, build / "ladybug.rom", phase, monitor)
        cases["xroar_binary"] = str(xroar.resolve())
        reach = lambda symbols, name, label: run_to_condition(
            client, phase, marker_addr(symbols, name), label, lambda: True,
            lambda pc: site_images.qualify(client, pc, "presentation"))
        reach(pres_syms, "presentation_flow_tick", "initial PFT")
        cases["live_images"] = live_image_check(client, build)
        reach(pres_syms, "demo_run", "attract exit")
        client.raw.call("inject_key", {"key": KEY_COIN, "action": "press"}, timeout=2.0)
        reach(pres_syms, "credit_tick", "credit")
        client.raw.call("inject_key", {"key": KEY_COIN, "action": "release"}, timeout=2.0)
        client.raw.call("inject_key", {"key": KEY_ENTER, "action": "press"}, timeout=2.0)
        reach(pres_syms, "normal_game", "credited game start")
        client.raw.call("inject_key", {"key": KEY_ENTER, "action": "release"}, timeout=2.0)
        mainloop = marker_addr(main_syms, "mainloop")
        run_to_condition(client, phase, mainloop, "first-life ready",
                         lambda: read_byte(client, INITIAL_ENTRY) == 0 and
                         read_word(client, PLAYER_FB) == 0x75EC,
                         lambda pc: site_images.qualify(client, pc, "main"))
        start_cell = [read_byte(client, PLAYER_X), read_byte(client, PLAYER_Y)]
        if start_cell != [12, 18]:
            raise ProbeError("first-life automatic entry reached an unexpected source cell: %r" % start_cell)
        entry_edge = source_neighbor_gate(client, main_syms, build, (12, 18), (12, 17),
                                          require_flower=False)
        client.raw.call("inject_key", {"key": KEY_UP, "action": "press"}, timeout=2.0)
        run_to_condition(client, phase, mainloop, "one-cell legal approach", lambda:
                         (read_byte(client, PLAYER_X), read_byte(client, PLAYER_Y)) == (12, 17),
                         lambda pc: site_images.qualify(client, pc, "main"))
        client.raw.call("inject_key", {"key": KEY_UP, "action": "release"}, timeout=2.0)
        adjacency = source_neighbor_gate(client, main_syms, build, (12, 17), (12, 16),
                                         require_flower=True)
        predecessor = state_snapshot(client)
        cases["paired_predecessor"] = {"state": predecessor, "sha256": canonical_hash(predecessor),
                                       "entry_edge": entry_edge, "flower_edge": adjacency}
        cases["phases"].append({"name": "cold-legal-predecessor",
                                "elapsed_seconds": round(45 - phase.remaining(), 3),
                                "stops": phase.stops})

        # Phase 2: exactly four fixture writes, then observe each natural helper
        # return before the dispatcher republishes the preview.
        phase = PhaseBudget()
        client.budget = phase
        cases["fixture"] = apply_fixture(client)
        cases["fixture_write_trace"] = [[hex(address), value] for address, value in client.fixture_seen]
        client.raw.call("inject_key", {"key": KEY_UP, "action": "press"}, timeout=2.0)
        hidden_captures = []
        for ordinal in (1, 2):
            tail = run_to_condition(client, phase, HIDDEN_TAIL_PC,
                                    "hidden pass %d banked-helper tail" % ordinal, lambda: True,
                                    lambda pc: site_images.qualify(client, pc, "banked_helper"))
            word = run_to_condition(client, phase, HIDDEN_WORD_PC,
                                    "hidden pass %d resident word renderer" % ordinal, lambda: True,
                                    lambda pc: site_images.qualify(client, pc, "main"))
            returned = run_to_condition(client, phase, HIDDEN_RETURN_PC,
                                        "hidden pass %d caller return" % ordinal, lambda: True,
                                        lambda pc: site_images.qualify(client, pc, "presentation"))
            hold_request = site_images.qualify(client, 0x0712, "hold_helper")
            hold_restore = site_images.qualify(client, 0x072D, "hold_helper")
            back_map = site_images.qualify(
                client, marker_addr(pres_syms, "map_back"), "presentation")
            frame, evidence = capture_hidden_back(client, [tail["site_proof"], word["site_proof"],
                                                           returned["site_proof"], hold_request,
                                                           hold_restore, back_map])
            saved_pair = {evidence["hold_saved_front"], evidence["hold_saved_back"]}
            if saved_pair != {0, 1}:
                raise MissingCoverage("helper-return history does not identify saved FRONT/BACK owners0 and1")
            expected_owner = (evidence["hold_saved_back"] if ordinal == 1
                              else evidence["hold_saved_front"])
            if ordinal == 2 and (evidence["hold_saved_front"], evidence["hold_saved_back"]) != (
                    hidden_captures[0]["hold_saved_front"], hidden_captures[0]["hold_saved_back"]):
                raise MissingCoverage("saved FRONT/BACK source history changed between hidden passes")
            if evidence["back_owner"] != expected_owner:
                raise MissingCoverage("natural hidden pass %d selected BACK%d, expected restored identity BACK%d" %
                                      (ordinal, evidence["back_owner"], expected_owner))
            evidence["pixel_checks"] = panel_pixel_check(
                frame, evidence["masks"], evidence["letter_variants"], build,
                underlay, pixel_oracle, masks, blue)
            if hidden_captures and evidence["letter_variants"] != hidden_captures[0]["letter_variants"]:
                raise MissingCoverage("natural hidden passes do not share random-letter identities")
            if (evidence["pixel_checks"]["word_pixels"]["classification"] != "pixel_match" or
                    evidence["pixel_checks"]["stored_masks"]["classification"] != "match" or
                    not evidence["pixel_checks"]["random_letters"]["all_slots_match"] or
                    not evidence["pixel_checks"]["hearts"]["all_slots_match"]):
                cases["product_findings"].append({"phase": "hidden-BACK%d" % expected_owner,
                    "kind": "hidden-pixel-gate-failure", "detail": evidence["pixel_checks"]})
            hidden_captures.append(evidence)
        preview_pc = marker_addr(pres_syms, "level_tick")
        run_to_condition(client, phase, preview_pc, "first actual stage-2 preview", lambda:
                         read_byte(client, STAGE) == 2 and read_byte(client, PRES_MODE) == 6 and
                         read_byte(client, PRES_SCREEN) == 2 and read_byte(client, PRES_CONTEXT) == 2,
                         lambda pc: site_images.qualify(client, pc, "presentation"))
        client.raw.call("inject_key", {"key": KEY_UP, "action": "release"}, timeout=2.0)
        visible_owner = read_byte(client, FRONT)
        preview_frame, preview_publication = physical_frame(client, visible_owner)
        preview_variants = read_bytes(client, STAGE_LETTER_VARIANTS, 3)
        preview_masks = {"special": read_byte(client, SPECIAL), "extra": read_byte(client, EXTRA)}
        preview_publication.update({"screen_role": "level-start", "masks": preview_masks,
                                    "letter_variants": list(preview_variants)})
        preview_publication["pixel_checks"] = panel_pixel_check(
            preview_frame, preview_masks, list(preview_variants), build,
            underlay, pixel_oracle, masks, blue)
        if list(preview_variants) != hidden_captures[0]["letter_variants"]:
            raise MissingCoverage("published stage-2 preview changed the hidden random-letter identity")
        hidden_contract = hidden_owner_identity_check(hidden_captures,
            {"before": hidden_captures[-1]["commit_seq"],
             "published": preview_publication["commit_seq"]})
        cases["hidden_captures"] = hidden_captures
        cases["hidden_owner_contract"] = hidden_contract
        cases["preview_publication"] = preview_publication
        preview_pixels = preview_publication["pixel_checks"]
        if (preview_pixels["word_pixels"]["classification"] != "pixel_match" or
                preview_pixels["stored_masks"]["classification"] != "match" or
                not preview_pixels["random_letters"]["all_slots_match"] or
                not preview_pixels["hearts"]["all_slots_match"]):
            cases["product_findings"].append({"phase": "stage2-preview",
                "kind": "preview-pixel-gate-failure", "detail": preview_pixels})
        if hidden_contract["result"] == "product_reproduced":
            cases["product_findings"].append({"phase": "hidden-owners",
                "kind": "hidden-pixel-gate-failure", "detail": hidden_contract["absolute_pixel_gates"]})
        cases["phases"].append({"name": "hidden-BACK0-BACK1-and-first-stage2-preview",
                                "elapsed_seconds": round(45 - phase.remaining(), 3),
                                "stops": phase.stops})

        # Phase 3: source-qualified release, followed by the first aligned maze scanout.
        phase = PhaseBudget()
        client.budget = phase
        release_pc = stage2_release_pc(build)
        run_to_condition(client, phase, release_pc, "stage-2 context-2 release branch",
                         lambda: read_byte(client, STAGE) == 2 and
                         read_byte(client, PRES_MODE) == 6 and
                         read_byte(client, PRES_SCREEN) == 2 and
                         read_byte(client, PRES_CONTEXT) == 0 and
                         (read_byte(client, PLAYER_X), read_byte(client, PLAYER_Y)) == (12, 22) and
                         read_word(client, PLAYER_FB) == 0x89EC and
                         read_byte(client, PLAYER_STEP) == 0,
                         lambda pc: site_images.qualify(client, pc, "presentation"))
        cases["stage2_release"] = {"pc": hex(release_pc), "stage": read_byte(client, STAGE),
                                   "mode": read_byte(client, PRES_MODE),
                                   "screen": read_byte(client, PRES_SCREEN),
                                   "context": read_byte(client, PRES_CONTEXT),
                                   "cell": [read_byte(client, PLAYER_X), read_byte(client, PLAYER_Y)],
                                   "fb": hex(read_word(client, PLAYER_FB)),
                                   "step": read_byte(client, PLAYER_STEP)}
        enemy_syms = symbols_for(build, "ladybug-enemy-runtime.map")
        stage_render_pc = marker_addr(enemy_syms, "fri_stage_background")
        stage_render_entry = run_to_condition(
            client, phase, stage_render_pc, "source-qualified RF_STAGE background render",
            lambda: (read_byte(client, STAGE) == 2 and read_byte(client, PRES_CONTEXT) == 0 and
                     read_byte(client, PRES_MODE) != 6 and (read_byte(client, RENDER_FLAGS) & RF_STAGE) != 0),
            lambda pc: site_images.qualify(client, pc, "enemy"))
        cases["maze_stage_render_entry"] = {
            "pc": hex(stage_render_pc), "site_proof": stage_render_entry["site_proof"],
            "render_flags": read_byte(client, RENDER_FLAGS), "RF_STAGE": RF_STAGE}
        preview_commit = int(preview_publication["commit_seq"])
        def maze_ready() -> bool:
            if (read_byte(client, STAGE) != 2 or read_byte(client, PRES_SCREEN) != 2 or
                    read_byte(client, PRES_CONTEXT) != 0 or read_byte(client, PRES_MODE) == 6 or
                    read_byte(client, PENDING) != 0 or
                    (read_byte(client, RENDER_FLAGS) & RF_STAGE) != 0 or
                    ((read_word(client, COMMIT) - preview_commit) & 0xFFFF) == 0):
                return False
            front = read_byte(client, FRONT)
            if front not in (0, 1):
                return False
            gime = client.raw.call("read_gime_state", timeout=3.0)
            return gime_scanout_identity(gime) == {
                "mode": 0x80, "vres": 0x1E,
                "base": {0: 0x60000, 1: 0x58000}[front], "owner": front}
        run_to_condition(client, phase, mainloop, "first actual maze scanout", maze_ready,
                         lambda pc: site_images.qualify(client, pc, "main"))
        maze_owner = read_byte(client, FRONT)
        maze_frame, maze_publication = physical_frame(client, maze_owner)
        maze_masks = {"special": read_byte(client, SPECIAL), "extra": read_byte(client, EXTRA)}
        try:
            maze_word = check_word_tiles(maze_frame, word_oracle(HIDDEN_CAPSULE))
            maze_word_result = {"classification": "pixel_match", "tiles_checked": maze_word["tiles_checked"],
                                "sha256": maze_word["sha256"]}
        except ProbeError as exc:
            maze_word_result = {"classification": "pixel_mismatch", "error": str(exc)}
        maze_masks_match = maze_masks == {"special": 0x49, "extra": 0x15}
        if maze_word_result["classification"] != "pixel_match" or not maze_masks_match:
            cases["product_findings"].append({"phase": "first-maze",
                "kind": "maze-word-or-mask-mismatch",
                "detail": {"word_pixels": maze_word_result, "masks": maze_masks,
                           "expected_masks": {"special": 0x49, "extra": 0x15}}})
        preview_word = preview_publication["pixel_checks"]["word_pixels"]
        maze_word_identity = (maze_word_result.get("sha256") == preview_word.get("sha256") and
                              maze_word_result["classification"] == "pixel_match" and
                              preview_word["classification"] == "pixel_match")
        if not maze_word_identity:
            cases["product_findings"].append({"phase": "first-maze",
                "kind": "maze-preview-word-crop-identity-mismatch",
                "detail": {"preview": preview_word, "maze": maze_word_result}})
        cases["maze_publication"] = {"screen_role": "first-maze-after-stage2-release",
                                     "commit_seq": maze_publication["commit_seq"],
                                     "owner": maze_publication["owner"],
                                     "physical_base": maze_publication["physical_base"],
                                     "frame_sha256": sha(maze_frame),
                                     "gime_mode": maze_publication["gime_mode"],
                                     "gime_vres": maze_publication["gime_vres"],
                                     "pending": maze_publication["pending"],
                                     "render_flags": read_byte(client, RENDER_FLAGS),
                                     "RF_STAGE_cleared": (read_byte(client, RENDER_FLAGS) & RF_STAGE) == 0,
                                     "commit_advanced_from_preview":
                                         ((maze_publication["commit_seq"] - preview_commit) & 0xFFFF) != 0,
                                     "masks": maze_masks, "word_pixels": maze_word_result,
                                     "word_crop_matches_preview": maze_word_identity,
                                     "word_crop_identity": maze_word_result.get("sha256")}
        cases["phases"].append({"name": "stage2-release-through-first-maze-scanout",
                                "elapsed_seconds": round(45 - phase.remaining(), 3),
                                "stops": phase.stops, "release_pc": hex(release_pc)})
        cases["result"] = "product_reproduced" if cases["product_findings"] else "candidate_hidden_owner_pass"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(cases, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return cases
    except ProductReproduction as exc:
        cases["result"] = "product_reproduced"
        cases["failure"] = {"type": "product_reproduction", "message": str(exc)}
        if client is not None:
            cases["last_qualified_marker"] = client.last_qualified_marker
            cases["fixture_write_trace"] = [[hex(address), value] for address, value in client.fixture_seen]
        if phase is not None:
            cases["last_phase"] = {"elapsed_seconds": round(phase.clock() - phase.started, 3),
                                   "remaining_seconds": round(phase.remaining(), 3), "stops": phase.stops}
        if not output.exists():
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(cases, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return cases
    except MissingCoverage as exc:
        cases["result"] = "missing_coverage"
        cases["failure"] = {"type": "missing_coverage", "message": str(exc)}
        if client is not None:
            cases["last_qualified_marker"] = client.last_qualified_marker
            cases["fixture_write_trace"] = [[hex(address), value] for address, value in client.fixture_seen]
        if phase is not None:
            cases["last_phase"] = {"elapsed_seconds": round(phase.clock() - phase.started, 3),
                                   "remaining_seconds": round(phase.remaining(), 3), "stops": phase.stops}
        if not output.exists():
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(cases, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return cases
    except Exception as exc:
        cases["result"] = "setup_or_observer_failure"
        cases["failure"] = {"type": type(exc).__name__, "message": str(exc)}
        if client is not None:
            cases["last_qualified_marker"] = client.last_qualified_marker
            cases["fixture_write_trace"] = [[hex(address), value] for address, value in client.fixture_seen]
        if phase is not None:
            cases["last_phase"] = {"elapsed_seconds": round(phase.clock() - phase.started, 3),
                                   "remaining_seconds": round(phase.remaining(), 3), "stops": phase.stops}
        if not output.exists():
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(cases, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        raise
    finally:
        if client is not None:
            try:
                if not client.restored:
                    client.close()
                client.raw.close()
            except Exception:
                pass
        if process is not None:
            if process.poll() is None:
                process.kill()
            try:
                process.wait(timeout=2)
            except Exception:
                pass


def source_module_bytes(client: DeadlineClient, build: Path, address: int,
                        length: int) -> dict[str, Any]:
    staged = (build / "ladybug-enemy-runtime.rom").read_bytes()
    gime = client.raw.call("read_gime_state", timeout=5.0)
    par0 = int(gime["pars"]["task0"][0])
    source_offset = address - ENEMY_ORIGIN
    if par0 != 0x38 or source_offset < 0 or source_offset + length > len(staged):
        raise ProbeError("stage-background page/address is outside the pinned active module")
    expected = staged[source_offset:source_offset + length]
    cpu = read_bytes(client, address, length)
    physical = read_bytes(client, par0 * 0x2000 + address, length, "physical")
    if cpu != expected or physical != expected:
        raise ProbeError("stage-background source/staged/live/physical bytes differ")
    after = client.raw.call("read_gime_state", timeout=5.0)
    if gime["pars"] != after["pars"] or gime["registers"] != after["registers"]:
        raise ProbeError("GIME mapping changed during stage-background byte qualification")
    return {"address": hex(address), "length": length, "sha256": sha(cpu),
            "par0": par0, "physical_sha256": sha(physical)}


def _number(value: Any) -> int:
    return int(value, 0) if isinstance(value, str) else int(value)


def stage_state_evidence_check(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Fail closed on incomplete or unqualified state before interpreting stage behavior."""
    errors = []
    if not isinstance(snapshot, dict):
        return {"pass": False, "errors": ["state snapshot is not an object"]}
    if snapshot.get("errors"):
        errors.append("state snapshot contains failed reads")
    if snapshot.get("direct_page_cpu_physical_match") is not True:
        errors.append("direct-page CPU/physical bytes are not qualified equal")
    for key in ("direct_page_cpu_sha256", "direct_page_physical_sha256"):
        if not isinstance(snapshot.get(key), str) or not snapshot[key]:
            errors.append("missing direct-page evidence: " + key)
    if snapshot.get("direct_page_cpu_length") != 0xA8 or \
            snapshot.get("direct_page_physical_length") != 0xA8:
        errors.append("direct-page evidence is incomplete")
    if snapshot.get("direct_page_cpu_sha256") != snapshot.get("direct_page_physical_sha256"):
        errors.append("direct-page CPU/physical hashes differ")
    gime = snapshot.get("gime")
    if not isinstance(gime, dict):
        errors.append("missing GIME state evidence")
    else:
        task0, task1 = gime.get("task0_pars"), gime.get("task1_pars")
        try:
            p0 = [_number(value) for value in task0]
            p1 = [_number(value) for value in task1]
            valid_pars = (len(p0) == 8 and len(p1) == 8 and
                          all(0 <= value <= 0x3F for value in p0 + p1))
            valid_state_map = (gime.get("mmu_task") == 0 and valid_pars and
                               (p0[0], p0[6], p0[7]) == (0x38, 0x3E, 0x3F))
        except (TypeError, ValueError):
            valid_state_map = False
        if not valid_state_map or snapshot.get("state_mapping_expected") is not True:
            errors.append("state CPU/PAR mapping is missing or invalid")
    pose = snapshot.get("pose")
    if (not isinstance(pose, dict) or not isinstance(pose.get("cell"), list) or
            len(pose["cell"]) != 2 or pose.get("fb") is None or pose.get("step") is None):
        errors.append("direct-page pose evidence is incomplete")
    input_state = snapshot.get("input")
    input_keys = ("joy_x", "joy_y", "joy_dir", "player_dir", "player_face",
                  "player_want", "player_manual")
    if not isinstance(input_state, dict) or any(input_state.get(key) is None for key in input_keys):
        errors.append("direct-page input evidence is incomplete")
    flag_keys = ("initial_entry_state", "player_tick_pending", "box_timer", "box_index",
                 "enemy_active", "enemy_released", "enemy_roaming", "death_state",
                 "pickup_timer", "stage", "presentation_mode", "presentation_screen",
                 "presentation_context")
    flags = snapshot.get("flags")
    if not isinstance(flags, dict) or any(flags.get(key) is None for key in flag_keys):
        errors.append("direct-page control-state evidence is incomplete")
    cpu = snapshot.get("cpu")
    if not isinstance(cpu, dict) or any(cpu.get(key) is None for key in ("pc", "s", "cc", "dp")):
        errors.append("CPU register evidence is incomplete")
    cycles = snapshot.get("cycles")
    if not isinstance(cycles, dict) or any(cycles.get(key) is None for key in ("event_ticks", "cpu_cycles")):
        errors.append("cycle evidence is incomplete")
    return {"pass": not errors, "errors": errors}


def stage_brief_snapshot(client: DeadlineClient, pc: int, event: str) -> dict[str, Any]:
    """Best-effort short state record, retained before stage observer assertions."""
    result: dict[str, Any] = {"event": event, "pc": hex(pc), "errors": []}
    try:
        gime = client.raw.call("read_gime_state", timeout=3.0)
        pars = gime.get("pars") if isinstance(gime, dict) else None
        result["gime"] = {"mmu_task": gime.get("mmu_task") if isinstance(gime, dict) else None,
                          "task0_pars": pars.get("task0") if isinstance(pars, dict) else None,
                          "task1_pars": pars.get("task1") if isinstance(pars, dict) else None}
        if not isinstance(pars, dict):
            result["errors"].append("GIME snapshot returned an incomplete PAR mapping")
    except Exception as exc:
        gime = None
        result["errors"].append("GIME snapshot: %s: %s" % (type(exc).__name__, exc))
    direct = None
    physical = None
    try:
        direct = read_bytes(client, 0, 0xA8)
        result["direct_page_cpu_length"] = len(direct)
        result["direct_page_cpu_sha256"] = sha(direct)
    except Exception as exc:
        result["errors"].append("direct-page CPU read: %s: %s" % (type(exc).__name__, exc))
    try:
        physical = read_bytes(client, 0x38 * 0x2000, 0xA8, "physical")
        result["direct_page_physical_length"] = len(physical)
        result["direct_page_physical_sha256"] = sha(physical)
    except Exception as exc:
        result["errors"].append("direct-page physical read: %s: %s" % (type(exc).__name__, exc))
    if direct is not None and physical is not None:
        result["direct_page_cpu_physical_match"] = direct == physical
    if direct is not None:
        try:
            result["pose"] = {"cell": [direct[PLAYER_X], direct[PLAYER_Y]],
                              "fb": hex((direct[PLAYER_FB] << 8) | direct[PLAYER_FB + 1]),
                              "step": direct[PLAYER_STEP]}
            result["input"] = {"joy_x": direct[JOY_X], "joy_y": direct[JOY_Y],
                               "joy_dir": direct[JOY_DIR], "player_dir": direct[PLAYER_DIR],
                               "player_face": direct[PLAYER_FACE], "player_want": direct[PLAYER_WANT],
                               "player_manual": direct[PLAYER_MANUAL]}
            result["flags"] = {"initial_entry_state": direct[INITIAL_ENTRY],
                               "player_tick_pending": direct[PLAYER_TICK_PENDING],
                               "box_timer": direct[BOX_TIMER], "box_index": direct[BOX_INDEX],
                               "enemy_active": direct[ENEMY_ACTIVE],
                               "enemy_released": direct[ENEMY_RELEASED],
                               "enemy_roaming": direct[ENEMY_ROAMING],
                               "death_state": direct[DEATH_STATE],
                               "pickup_timer": direct[PICKUP_TIMER],
                               "stage": direct[STAGE], "presentation_mode": direct[PRES_MODE],
                               "presentation_screen": direct[PRES_SCREEN],
                               "presentation_context": direct[PRES_CONTEXT]}
        except Exception as exc:
            result["errors"].append("direct-page decode: %s: %s" % (type(exc).__name__, exc))
    try:
        registers = client.raw.call("read_registers", timeout=3.0)
        result["cpu"] = {key: registers.get(key) for key in ("pc", "s", "cc", "dp")}
    except Exception as exc:
        result["errors"].append("CPU snapshot: %s: %s" % (type(exc).__name__, exc))
    try:
        result["cycles"] = read_cycles(client)
    except Exception as exc:
        result["errors"].append("cycle snapshot: %s: %s" % (type(exc).__name__, exc))
    result["scripted_keys_down"] = sorted(client.key_down)
    if gime is not None and isinstance(gime, dict):
        try:
            pars = gime.get("pars", {}).get("task0", [])
            result["state_mapping_expected"] = (gime.get("mmu_task") == 0 and len(pars) == 8 and
                                                 _number(pars[0]) == 0x38 and
                                                 (_number(pars[6]), _number(pars[7])) == (0x3E, 0x3F))
            result["par5_observed_without_release_site_assumption"] = pars[5] if len(pars) == 8 else None
        except Exception as exc:
            result["state_mapping_expected"] = False
            result["errors"].append("GIME mapping decode: %s: %s" % (type(exc).__name__, exc))
    return result


def _brief_site(proof: dict[str, Any]) -> dict[str, Any]:
    return {key: proof.get(key) for key in ("kind", "address", "length", "source_sha256",
                                             "staged_sha256", "cpu_sha256", "physical_sha256",
                                             "physical_page", "mmu_task")}


def stage_enemy_lane_snapshot(cpu_records: bytes, physical_records: bytes,
                              lifecycle: dict[str, int], origin: tuple[int, int],
                              target: tuple[int, int]) -> dict[str, Any]:
    """Validate the four source-defined enemy records against one legal lane edge."""
    errors: list[str] = []
    if len(cpu_records) != ENEMY_RECORD_SIZE * ENEMY_RECORDS or \
            len(physical_records) != ENEMY_RECORD_SIZE * ENEMY_RECORDS:
        return {"pass": False, "errors": ["enemy table must contain exactly four 8-byte records"]}
    active_records = []
    invalid_positions = []
    nearby = []
    for index in range(ENEMY_RECORDS):
        record = cpu_records[index * ENEMY_RECORD_SIZE:(index + 1) * ENEMY_RECORD_SIZE]
        if record[0] == 0:
            continue
        cell = [record[4], record[5]]
        item = {"index": index, "state": record[0],
                "framebuffer": hex(int.from_bytes(record[1:3], "big")),
                "pixel_step": record[3], "cell": cell,
                "background_valid": record[6], "direction": record[7]}
        active_records.append(item)
        x, y = cell
        if not (0 <= x < 24 and 0 <= y < 24):
            invalid_positions.append(index)
        elif any(max(abs(x - hx), abs(y - hy)) <= 1 for hx, hy in (origin, target)):
            nearby.append(index)
    if cpu_records != physical_records:
        errors.append("enemy CPU/physical records differ")
    if len(active_records) != lifecycle.get("enemy_active"):
        errors.append("active enemy records differ from ENEMY_ACTIVE")
    if nearby:
        errors.append("active enemy is within the source collision neighborhood of the approved edge")
    if invalid_positions:
        errors.append("active enemy record has out-of-map cell coordinates")
    if not 0 <= lifecycle.get("enemy_active", -1) <= ENEMY_RECORDS:
        errors.append("ENEMY_ACTIVE exceeds the four authoritative record slots")
    if not 0 <= lifecycle.get("enemy_released", -1) <= ENEMY_RECORDS:
        errors.append("ENEMY_RELEASED exceeds the stage release limit")
    if not 0 <= lifecycle.get("box_index", -1) < 92 or not 1 <= lifecycle.get("box_timer", -1) <= 6:
        errors.append("box timer/index is outside the stage-2 release cycle")
    if lifecycle.get("death_state") != 0 or lifecycle.get("pickup_timer") != 0:
        errors.append("death or pickup transient interrupts the approved movement edge")
    return {"pass": not errors, "errors": errors,
            "enemy_records_cpu_sha256": sha(cpu_records),
            "enemy_records_physical_sha256": sha(physical_records),
            "enemy_records_match": cpu_records == physical_records,
            "active_enemy_records": active_records,
            "active_enemy_count_matches": len(active_records) == lifecycle.get("enemy_active"),
            "collision_neighborhood_cells": [list(origin), list(target)],
            "nearby_active_enemy_indexes": nearby,
            "invalid_active_enemy_indexes": invalid_positions}


def stage_enemy_mapping_check(mmu_task: Any, task0: list[Any]) -> dict[str, Any]:
    pars = [_number(value) for value in task0] if len(task0) == 8 else []
    valid = (mmu_task == 0 and len(pars) == 8 and
             (pars[0], pars[5], pars[6], pars[7]) == (0x38, 0x34, 0x3E, 0x3F))
    return {"pass": valid, "mmu_task": mmu_task, "task0_pars": task0,
            "enemy_page_selected": bool(pars and pars[5] == 0x34),
            "state_page_selected": bool(pars and pars[0] == 0x38),
            "errors": [] if valid else ["enemy-state CPU/PAR mapping mismatch"]}


def stage_live_table_preflight(client: DeadlineClient, build: Path,
                               symbols: dict[str, int]) -> dict[str, Any]:
    """Prove live route tables equal the receipt-pinned candidate and physical pages."""
    result: dict[str, Any] = {"errors": []}
    try:
        before = client.raw.call("read_gime_state", timeout=3.0)
        task0 = before["pars"]["task0"]
        if (before["mmu_task"] != 0 or len(task0) != 8 or
                (_number(task0[0]), _number(task0[6]), _number(task0[7])) !=
                (0x38, 0x3E, 0x3F)):
            result["errors"].append("PAR0/PAR6/PAR7 or MMU mapping mismatch")
        runtime = (build / "ladybug-runtime.rom").read_bytes()
        table_hashes = {}
        for name, length in (("maze_nav", 576), ("maze_gate_owner", 576)):
            address = marker_addr(symbols, name)
            expected = runtime[address - 0xC000:address - 0xC000 + length]
            cpu = read_bytes(client, address, length)
            physical = read_main_physical(client, address, length)
            table_hashes[name] = {"address": hex(address), "expected_sha256": sha(expected),
                                  "cpu_sha256": sha(cpu), "physical_sha256": sha(physical),
                                  "matches": expected == cpu == physical}
            if expected != cpu or expected != physical:
                result["errors"].append(name + " differs from candidate staged bytes")
        after = client.raw.call("read_gime_state", timeout=3.0)
        if (before["pars"] != after["pars"] or before["registers"] != after["registers"] or
                before["mmu_task"] != after["mmu_task"]):
            result["errors"].append("GIME mapping changed during route-table reads")
        result.update({"task0_pars": task0, "par5_observed_unconstrained": task0[5],
                       "tables": table_hashes,
                       "mapping_stable": not any("GIME mapping" in e for e in result["errors"])})
    except Exception as exc:
        result["errors"].append("route-table read: %s: %s" % (type(exc).__name__, exc))
    result["pass"] = not result["errors"]
    return result


def stage_enemy_preflight(client: DeadlineClient, origin: tuple[int, int],
                          target: tuple[int, int], direction_bit: int,
                          reciprocal_bit: int, nav: bytes, gates: bytes) -> dict[str, Any]:
    """Recheck one edge against authoritative roaming-enemy and spawner state."""
    result: dict[str, Any] = {"origin": list(origin), "target": list(target), "errors": [],
        "safety_source": "ENEMY_TABLE at $A470; ENTITY_TABLE at $A380 is collectible state"}
    try:
        before = client.raw.call("read_gime_state", timeout=3.0)
        task0 = before["pars"]["task0"]
        mapping = stage_enemy_mapping_check(before.get("mmu_task"), task0)
        result["mapping_before_guard"] = mapping
        result["errors"].extend(mapping["errors"])
        direct = read_bytes(client, 0, 0xA8)
        lifecycle = {"enemy_active": direct[ENEMY_ACTIVE],
                     "enemy_released": direct[ENEMY_RELEASED],
                     "enemy_roaming": direct[ENEMY_ROAMING],
                     "box_index": direct[BOX_INDEX], "box_timer": direct[BOX_TIMER],
                     "death_state": direct[DEATH_STATE],
                     "pickup_timer": direct[PICKUP_TIMER]}
        cpu_records = read_bytes(client, ENEMY_TABLE, ENEMY_RECORD_SIZE * ENEMY_RECORDS)
        physical_records = read_bytes(client,
            0x34 * 0x2000 + (ENEMY_TABLE - 0xA000),
            ENEMY_RECORD_SIZE * ENEMY_RECORDS, "physical")
        tx, ty = target
        ox, oy = origin
        offset = ty * 24 + tx
        origin_nav, target_nav, gate = nav[oy * 24 + ox], nav[offset], gates[offset]
        after = client.raw.call("read_gime_state", timeout=3.0)
        if (before["pars"] != after["pars"] or before["registers"] != after["registers"] or
                before["mmu_task"] != after["mmu_task"]):
            result["errors"].append("GIME mapping changed during enemy preflight")
        enemy_check = stage_enemy_lane_snapshot(cpu_records, physical_records, lifecycle,
                                                origin, target)
        result.update({"lifecycle_before_guard": lifecycle,
                       "enemy_lane_check": enemy_check,
                       "origin_nav": origin_nav, "target_nav": target_nav,
                       "target_gate_owner": gate,
                       "source_legal": bool(origin_nav & (1 << direction_bit)) and
                                       bool(target_nav & reciprocal_bit) and gate == 0,
                       "lane_enemy_safe": enemy_check["pass"],
                       "task0_pars_after": after["pars"]["task0"]})
        result["errors"].extend(enemy_check["errors"])
        if not result["source_legal"]:
            result["errors"].append("runtime nav/gate no longer admits the approved edge")
    except Exception as exc:
        result["errors"].append("enemy preflight read: %s: %s" % (type(exc).__name__, exc))
    result["pass"] = not result["errors"]
    return result


def stage_stack_return(client: DeadlineClient, site_images: SiteQualifier,
                       call_site: int, expected_return: int, label: str) -> dict[str, Any]:
    """Return source/caller/mapping evidence without asserting before it is recorded."""
    proof = site_images.qualify(client, call_site, "active")
    registers = client.raw.call("read_registers", timeout=3.0)
    stack_value = registers.get("s")
    stack = _number(stack_value)
    observed_return = read_word(client, stack)
    return {"label": label, "call_site": hex(call_site),
            "expected_return": hex(expected_return), "observed_return": hex(observed_return),
            "matches": observed_return == expected_return, "active_site": _brief_site(proof)}


def stage_stream_event(client: DeadlineClient, phase: PhaseBudget,
                       sites: dict[int, tuple[str, str]],
                       site_images: SiteQualifier) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """Wait for one of the approved BUG-117 full-walk source boundaries."""
    timeout = phase.stop("stage-entry source event")
    client.raw.call("run", timeout=min(2.0, timeout))
    result = client.raw.call("wait_for_stop", {"timeout_ms": int(timeout * 1000)}, timeout=timeout)
    if result.get("reason") == "timeout":
        raise PhaseDeadline("stage-entry source event stop expired")
    pc = _number(result.get("pc", -1))
    if pc not in sites:
        raise ProbeError("unexpected stage-entry stop at %04x" % pc)
    event, kind = sites[pc]
    observation = stage_brief_snapshot(client, pc, event)
    observation["state_evidence"] = stage_state_evidence_check(observation)
    if not observation["state_evidence"]["pass"]:
        observation["state_evidence_error"] = "; ".join(observation["state_evidence"]["errors"])
        return event, result, observation
    try:
        proof = site_images.qualify(client, pc, kind)
        observation["site_proof"] = _brief_site(proof)
    except Exception as exc:
        observation["site_proof_error"] = "%s: %s" % (type(exc).__name__, exc)
        return event, result, observation
    client.last_qualified_marker = {"label": event, "pc": hex(pc),
                                    "proof": observation["site_proof"]}
    return event, result, observation


def run_stage_entry_case(args: argparse.Namespace) -> dict[str, Any]:
    """Run the approved natural full-walk observer; caller requires parent runtime lease."""
    if not args.run_live:
        raise ProbeError("stage-entry runtime requires --run-live and a separate parent runtime lease")
    output = Path(args.output).resolve()
    if not inside(output, STAGE_ENTRY_OWNED) or output.exists():
        raise ProbeError("stage-entry output must be a fresh path inside the owned observer directory")
    build = Path(args.build).resolve()
    if build != STAGE_ENTRY_BUILD.resolve():
        raise ProbeError("stage-entry runtime is pinned to the approved combined candidate capsule")
    if args.case == "held" and args.paired_neutral is None:
        raise ProbeError("held stage-entry case requires its completed neutral predecessor evidence")
    if args.case == "neutral" and args.paired_neutral is not None:
        raise ProbeError("neutral stage-entry case must not name another predecessor")
    cases: dict[str, Any] = {
        "scenario": "stage-entry", "case": args.case, "phases": [],
        "observations": [], "input_samples": [], "product_findings": [],
        "known_bug046_findings": [], "fixture_contract": [[hex(a), v] for a, v in FIXTURE],
        "scope": "one natural stage-2 full-walk run; no hydration; no random route search",
        "runtime_authorized_by_this_artifact": False,
        "phase_contract": {"whole_phase_seconds_max": PHASE_SECONDS,
                           "stop_seconds_max": STOP_SECONDS,
                           "stops_per_phase_max": MAX_STOPS,
                           "phases_per_run": 3, "max_runs": 2,
                           "total_seconds_per_run_max": 135,
                           "combined_runs_max_seconds": 270, "retries": 0},
    }
    process = None
    client = None
    phase: PhaseBudget | None = None
    try:
        cases["pins"] = artifact_check(build)
        cases["offline_qualification"] = offline_stage_entry_check(build)
        monitor = _monitor_module()
        pres_syms = symbols_for(build, "ladybug-presentation-runtime.map")
        main_syms = symbols_for(build, "ladybug.map")
        active_syms = symbols_for(build, "ladybug-adaptive-active.map")
        site_images = SiteQualifier(build)
        xroar = Path(args.xroar) if args.xroar else ROOT / "docs" / "reference" / "xroar" / "src" / "xroar"

        def boundary(label: str, pc: int, kind: str) -> None:
            if client is None:
                return
            snap = stage_brief_snapshot(client, pc, label)
            cases.setdefault("boundary_snapshots", {})[label] = snap
            snap["state_evidence"] = stage_state_evidence_check(snap)
            if not snap["state_evidence"]["pass"]:
                snap["state_evidence_error"] = "; ".join(snap["state_evidence"]["errors"])
                raise ProbeError("stage boundary state evidence failed at " + label + ": " +
                                 snap["state_evidence_error"])
            try:
                proof = site_images.qualify(client, pc, kind)
                snap["site_proof"] = _brief_site(proof)
            except Exception as exc:
                snap["site_proof_error"] = "%s: %s" % (type(exc).__name__, exc)

        def qualify_boundary(pc: int, label: str, kind: str) -> dict[str, Any]:
            try:
                return site_images.qualify(client, pc, kind)
            except Exception:
                # run_to_condition invokes its site qualifier before its observer;
                # capture the failed boundary before propagating a setup failure.
                boundary(label, pc, kind)
                raise

        def reach(symbols: dict[str, int], name: str, tag: str) -> dict[str, Any]:
            address = marker_addr(symbols, name)
            kind = "presentation" if symbols is pres_syms else "main"
            return run_to_condition(client, phase, address, tag, lambda: True,
                                    lambda pc: qualify_boundary(pc, tag, kind),
                                    lambda: boundary(tag, address, kind))

        # Phase 1: cold natural first-life route to the authored final flower.
        phase = PhaseBudget()
        process, client = launch_owned(xroar, build / "ladybug.rom", phase, monitor)
        cases["xroar_binary"] = str(xroar.resolve())
        reach(pres_syms, "presentation_flow_tick", "initial published preview path")
        cases["live_images"] = live_image_check(client, build)
        reach(pres_syms, "demo_run", "attract exit")
        client.raw.call("inject_key", {"key": KEY_COIN, "action": "press"}, timeout=2.0)
        reach(pres_syms, "credit_tick", "credit")
        client.raw.call("inject_key", {"key": KEY_COIN, "action": "release"}, timeout=2.0)
        client.raw.call("inject_key", {"key": KEY_ENTER, "action": "press"}, timeout=2.0)
        reach(pres_syms, "normal_game", "credited game start")
        client.raw.call("inject_key", {"key": KEY_ENTER, "action": "release"}, timeout=2.0)
        mainloop = marker_addr(main_syms, "mainloop")
        ready_stop = run_to_condition(client, phase, mainloop, "first-life ready",
            lambda: read_byte(client, INITIAL_ENTRY) == 0 and read_word(client, PLAYER_FB) == 0x75EC,
            lambda pc: site_images.qualify(client, pc, "main"),
            lambda: boundary("first-life ready probe", mainloop, "main"))
        start_snap = cases["boundary_snapshots"]["first-life ready probe"]
        start_cell = start_snap.get("pose", {}).get("cell")
        if start_cell != [12, 18]:
            raise MissingCoverage("first-life automatic entry did not reach authored cell (12,18)")
        boundary("first-life route predecessor", mainloop, "main")
        entry_edge = source_neighbor_gate(client, main_syms, build, (12, 18), (12, 17),
                                          require_flower=False)
        client.raw.call("inject_key", {"key": KEY_UP, "action": "press"}, timeout=2.0)
        target_snap: dict[str, Any] = {}
        def reached_first_flower() -> bool:
            snap = stage_brief_snapshot(client, mainloop, "first-life one-cell approach")
            target_snap.clear()
            target_snap.update(snap)
            cases.setdefault("boundary_snapshots", {})["first-life one-cell approach"] = snap
            snap["state_evidence"] = stage_state_evidence_check(snap)
            if not snap["state_evidence"]["pass"]:
                snap["state_evidence_error"] = "; ".join(snap["state_evidence"]["errors"])
                raise ProbeError("first-life predecessor state evidence failed: " +
                                 snap["state_evidence_error"])
            return snap.get("pose", {}).get("cell") == [12, 17]
        approach_stop = run_to_condition(client, phase, mainloop, "one-cell legal approach",
            reached_first_flower,
            lambda pc: qualify_boundary(pc, "first-life one-cell approach", "main"))
        client.raw.call("inject_key", {"key": KEY_UP, "action": "release"}, timeout=2.0)
        flower_edge = source_neighbor_gate(client, main_syms, build, (12, 17), (12, 16),
                                           require_flower=True)
        predecessor = state_snapshot(client)
        cases["paired_predecessor"] = {"state": predecessor,
                                       "sha256": canonical_hash(predecessor),
                                       "entry_edge": entry_edge, "flower_edge": flower_edge,
                                       "source_qualified_ready": start_snap,
                                       "source_qualified_approach": target_snap,
                                       "approach_stop": approach_stop.get("site_proof")}
        cases["phases"].append({"name": "cold-legal-predecessor",
                                "elapsed_seconds": round(PHASE_SECONDS - phase.remaining(), 3),
                                "stops": phase.stops})
        prior = None
        if args.case == "held":
            neutral_path = Path(args.paired_neutral).resolve()
            if not inside(neutral_path, STAGE_ENTRY_OWNED) or not neutral_path.is_file():
                raise ProbeError("paired neutral evidence must be an existing observer-owned file")
            prior = json.loads(neutral_path.read_text(encoding="utf-8"))
            if (prior.get("scenario") != "stage-entry" or prior.get("case") != "neutral" or
                    prior.get("paired_predecessor", {}).get("sha256") != cases["paired_predecessor"]["sha256"]):
                raise ProbeError("neutral/held cold predecessor identity mismatch; no retry permitted")

        # Phase 2: exactly four fixture writes, final flower, normal published preview.
        phase = PhaseBudget()
        client.budget = phase
        fixture = apply_fixture(client)
        client.raw.call("inject_key", {"key": KEY_UP, "action": "press"}, timeout=2.0)
        level_tick = marker_addr(pres_syms, "level_tick")
        preview_stop = run_to_condition(client, phase, level_tick, "final flower to stage-2 preview",
            lambda: read_byte(client, STAGE) == 2 and read_byte(client, PRES_MODE) == 6 and
                    read_byte(client, PRES_SCREEN) == 2 and read_byte(client, PRES_CONTEXT) == 2,
            lambda pc: qualify_boundary(pc, "published stage-2 preview probe", "presentation"),
            lambda: boundary("published stage-2 preview probe", level_tick, "presentation"))
        client.raw.call("inject_key", {"key": KEY_UP, "action": "release"}, timeout=2.0)
        owner = read_byte(client, FRONT)
        preview = stage_preview_oracle(client, owner, build)
        cases["fixture"] = fixture
        cases["preview_publication"] = preview
        if preview["stored_masks"]["classification"] != "match":
            cases["known_bug046_findings"].append({"phase": "stage2-preview",
                "kind": "stored-mask-mismatch", "detail": preview["stored_masks"]})
        if preview["word_oracle"]["classification"] != "pixel_match":
            cases["known_bug046_findings"].append({"phase": "stage2-preview",
                "kind": "word-pixel-mismatch", "detail": preview["word_oracle"]})
        cases["phases"].append({"name": "final-flower-to-first-stage2-preview",
                                "elapsed_seconds": round(PHASE_SECONDS - phase.remaining(), 3),
                                "stops": phase.stops,
                                "preview_release_marker": preview_stop.get("site_proof")})

        # Phase 3: fresh natural release, all 16 north advances, existing center stop,
        # then the actual held Down sample or a post-stop neutral-run Up control.
        phase = PhaseBudget()
        client.budget = phase
        if args.case == "held":
            client.raw.call("inject_key", {"key": KEY_DOWN, "action": "press"}, timeout=2.0)
            cases["held_input_setup"] = {"key": KEY_DOWN,
                                         "queued_while": "published stage-2 preview",
                                         "additional_guest_writes": 0}
        release_pc = stage2_release_pc(build)
        release_stop = run_to_condition(client, phase, release_pc, "stage-2 context-2 release",
            lambda: read_byte(client, STAGE) == 2 and read_byte(client, PRES_MODE) == 6 and
                    read_byte(client, PRES_SCREEN) == 2 and read_byte(client, PRES_CONTEXT) == 0 and
                    (read_byte(client, PLAYER_X), read_byte(client, PLAYER_Y)) == (12, 22) and
                    read_word(client, PLAYER_FB) == 0x89EC and read_byte(client, PLAYER_STEP) == 0,
            lambda pc: qualify_boundary(pc, "stage-2 release predecessor", "presentation"),
            lambda: boundary("stage-2 release predecessor", release_pc, "presentation"))
        release_snapshot = cases["boundary_snapshots"]["stage-2 release predecessor"]
        release_pose = release_snapshot.get("pose")
        release_input = release_snapshot.get("input", {})
        release_good = (release_pose == stage_walk_pose(0) and
                        release_snapshot.get("flags", {}).get("stage") == 2 and
                        release_snapshot.get("flags", {}).get("presentation_context") == 0 and
                        release_input.get("player_dir") == DIR_NORTH and
                        release_input.get("player_manual") == 0 and
                        release_input.get("player_want") == DIR_NONE and
                        release_input.get("joy_dir") == DIR_NONE)
        if not release_good:
            raise MissingCoverage("stage-2 release snapshot does not match the approved north/manual0 predecessor")
        cases["stage2_release"] = {"pose": release_pose, "input": release_input,
                                   "site_proof": release_snapshot.get("site_proof"),
                                   "stop": release_stop}
        tables = stage_live_table_preflight(client, build, main_syms)
        cases["stage_map_preflight"] = tables
        if not tables["pass"]:
            raise MissingCoverage("candidate route tables or live MMU mapping failed preflight")
        nav = (build / "ladybug-runtime.rom").read_bytes()[
            marker_addr(main_syms, "maze_nav") - 0xC000:
            marker_addr(main_syms, "maze_nav") - 0xC000 + 576]
        gates = (build / "ladybug-runtime.rom").read_bytes()[
            marker_addr(main_syms, "maze_gate_owner") - 0xC000:
            marker_addr(main_syms, "maze_gate_owner") - 0xC000 + 576]
        release_obs = stage_brief_snapshot(client, release_pc, "stage-2 release qualified")
        release_obs["site_proof"] = release_snapshot.get("site_proof")
        release_obs["state_evidence"] = stage_state_evidence_check(release_obs)
        cases["observations"].append(release_obs)
        if not release_obs["state_evidence"]["pass"]:
            release_obs["state_evidence_error"] = "; ".join(release_obs["state_evidence"]["errors"])
            raise ProbeError("stage-2 release state evidence failed: " +
                             release_obs["state_evidence_error"])

        read_call = next(iter(calls_to(listing_byte_map(build / "ladybug-adaptive-active.lst"),
                                       marker_addr(main_syms, "read_joystick"), ACTIVE_ORIGIN,
                                       ACTIVE_ORIGIN + len((build / "ladybug-adaptive-active.bin").read_bytes()))))
        tick_call = next(iter(calls_to(listing_byte_map(build / "ladybug-adaptive-active.lst"),
                                       marker_addr(main_syms, "player_tick"), ACTIVE_ORIGIN,
                                       ACTIVE_ORIGIN + len((build / "ladybug-adaptive-active.bin").read_bytes()))))
        read_done = marker_addr(main_syms, "rj_done")
        tick_pc = marker_addr(main_syms, "player_tick")
        center_pc = marker_addr(main_syms, "pt_at_center")
        draw_pc = marker_addr(main_syms, "pt_draw")
        watch = {read_done: ("input-return", "main"), tick_pc: ("player-tick-entry", "main"),
                 center_pc: ("center-stop-branch", "main"), draw_pc: ("player-draw", "main")}
        breakpoint_ids = []
        for address in watch:
            ident = client.raw.call("set_breakpoint", {"addr": address, "kind": "exec"},
                                    timeout=3.0)["id"]
            breakpoint_ids.append(ident)
        advance = 0
        center_stop_seen = False
        center_candidate_seen = False
        post_ready_input = False
        final_draws = 0
        tick_pending: dict[str, Any] | None = None
        stop_record = None
        input_direction = DIR_SOUTH if args.case == "held" else DIR_NORTH
        direction_bit = 2 if args.case == "held" else 0
        reciprocal_bit = 0x01 if args.case == "held" else 0x04
        edge_target_y = 19 if args.case == "held" else 17
        try:
            while not (center_stop_seen and post_ready_input and final_draws == 4):
                event, stop, record = stage_stream_event(client, phase, watch, site_images)
                cases["last_observation"] = record
                if event != "input-return":
                    cases["observations"].append(record)
                if record.get("state_evidence_error"):
                    raise ProbeError("stage state evidence failed at " + event + ": " +
                                     record["state_evidence_error"])
                if record.get("site_proof_error"):
                    raise ProbeError("candidate source/live site qualification failed at " + event)
                snap_input = record.get("input", {})
                snap_pose = record.get("pose")
                if event == "input-return":
                    caller: dict[str, Any]
                    caller_error = None
                    try:
                        caller = stage_stack_return(client, site_images, read_call, read_call + 3,
                                                    "read_joystick return")
                    except Exception as exc:
                        caller = {"matches": False, "error": "%s: %s" % (type(exc).__name__, exc)}
                        caller_error = exc
                    record["active_caller_proof"] = caller
                    if caller_error is not None or not caller.get("matches"):
                        raise ProbeError("read_joystick did not return through the candidate adaptive caller")
                    if not center_stop_seen:
                        expected_axes = (32, 64) if args.case == "held" else (32, 32)
                        if (snap_input.get("joy_x"), snap_input.get("joy_y")) != expected_axes:
                            raise MissingCoverage("automatic-entry sample lacks approved raw axis observation")
                        if (snap_input.get("player_manual"), snap_input.get("player_dir"),
                                snap_input.get("joy_dir"), snap_input.get("player_want")) != \
                                (0, DIR_NORTH, DIR_NONE, DIR_NONE):
                            raise ProductReproduction("input state published manual direction before center stop")
                        if advance == 0:
                            cases["input_samples"].append(record)
                    else:
                        if not post_ready_input:
                            if args.case == "neutral":
                                latched = (snap_input.get("joy_dir") == DIR_NORTH and
                                           snap_input.get("player_manual") == 1 and
                                           snap_input.get("player_want") == DIR_NORTH and
                                           snap_input.get("player_face") == DIR_NORTH)
                                if not latched:
                                    raise MissingCoverage("post-stop Up positive-control input was not sampled")
                            else:
                                if (snap_input.get("joy_x"), snap_input.get("joy_y")) != (32, 64):
                                    raise MissingCoverage("held Down raw axes were not present at first post-stop sample")
                                if (snap_input.get("joy_dir"), snap_input.get("player_manual"),
                                        snap_input.get("player_want"), snap_input.get("player_face")) != \
                                        (DIR_SOUTH, 1, DIR_SOUTH, DIR_SOUTH):
                                    raise ProductReproduction("held Down was not admitted at the first sample after center stop")
                            post_ready_input = True
                            cases["input_samples"].append(record)
                elif event == "player-tick-entry":
                    caller = {}
                    caller_error = None
                    try:
                        caller = stage_stack_return(client, site_images, tick_call, tick_call + 3,
                                                    "adaptive player_tick call")
                    except Exception as exc:
                        caller = {"matches": False, "error": "%s: %s" % (type(exc).__name__, exc)}
                        caller_error = exc
                    record["active_caller_proof"] = caller
                    if caller_error is not None or not caller.get("matches"):
                        raise ProbeError("player_tick entry did not return to its candidate adaptive caller")
                    if tick_pending is not None:
                        raise ProbeError("a prior player_tick did not reach its draw before another call")
                    if not center_stop_seen:
                        if advance < 16:
                            discrepancies = validate_stage_walk_entry(record, advance, args.case)
                            preflight = stage_enemy_preflight(client,
                                (12, 22 - advance // 4), (12, 21 - advance // 4),
                                0, 0x04, nav, gates)
                            record["enemy_safe_preflight"] = preflight
                            if discrepancies:
                                raise ProductReproduction("automatic entry invariant failed at ordinal %d: %s" %
                                                          (advance, "; ".join(discrepancies)))
                            if not preflight["pass"]:
                                raise MissingCoverage("automatic north lane failed live enemy preflight")
                            if record.get("flags", {}).get("player_tick_pending") != 0:
                                raise ProbeError("adaptive pending tick was not consumed before player_tick")
                            tick_pending = {"kind": "automatic", "advance": advance,
                                            "pre_pose": snap_pose, "pre_input": snap_input,
                                            "preflight": preflight}
                        else:
                            expected = stage_walk_pose(16)
                            center_candidate_seen = (snap_pose == expected and
                                snap_input.get("player_manual") == 0 and
                                snap_input.get("player_dir") == DIR_NORTH)
                            record["center_candidate"] = center_candidate_seen
                            if (not center_candidate_seen or snap_input.get("player_want") != DIR_NONE):
                                raise MissingCoverage("automatic route did not reach the approved center-stop predecessor")
                            tick_pending = {"kind": "center-stop", "advance": 16,
                                            "pre_pose": snap_pose, "pre_input": snap_input}
                    else:
                        edge = stage_enemy_preflight(client, (12, 18), (12, edge_target_y),
                                                     direction_bit, reciprocal_bit, nav, gates)
                        record["enemy_safe_preflight"] = edge
                        if not edge["pass"]:
                            raise MissingCoverage("post-ready direction lane failed live enemy preflight")
                        if not post_ready_input:
                            raise MissingCoverage("player movement began before the post-stop input sample was recorded")
                        discrepancies = validate_post_ready_predecessor(record, final_draws,
                                                                        input_direction)
                        if discrepancies:
                            raise ProductReproduction("post-ready player-tick predecessor failed at draw ordinal %d: %s" %
                                                      (final_draws, "; ".join(discrepancies)))
                        tick_pending = {"kind": "post-ready", "draw_ordinal": final_draws + 1,
                                        "pre_pose": snap_pose, "pre_input": snap_input,
                                        "preflight": edge}
                elif event == "center-stop-branch":
                    if center_stop_seen:
                        record["post_ready_center_choice"] = (final_draws == 0 and
                            snap_pose == stage_post_ready_pose(0, input_direction) and
                            snap_input.get("player_manual") == 1 and
                            snap_input.get("player_dir") == DIR_NONE and
                            snap_input.get("player_want") == input_direction)
                        if not record["post_ready_center_choice"]:
                            raise ProductReproduction("post-ready input did not reach the source center direction choice")
                    elif advance == 16:
                        record["center_candidate"] = (snap_pose == stage_walk_pose(16) and
                            snap_input.get("player_manual") == 0 and
                            snap_input.get("player_dir") == DIR_NORTH and
                            snap_input.get("player_want") == DIR_NONE)
                        if not record["center_candidate"]:
                            raise MissingCoverage("pt_at_center was not reached in the automatic stop state")
                        center_candidate_seen = True
                    elif snap_pose != stage_walk_pose(advance):
                        raise ProbeError("intermediate center branch pose differs from the captured walk ordinal")
                elif event == "player-draw":
                    if tick_pending is None:
                        raise ProbeError("player draw was observed without a qualified candidate player_tick entry")
                    kind = tick_pending["kind"]
                    if kind == "automatic":
                        expected = stage_walk_pose(tick_pending["advance"] + 1)
                        record["movement_ordinal_after_draw"] = tick_pending["advance"] + 1
                        if snap_pose != expected:
                            cases["product_findings"].append({"kind": "automatic-north-position-miss",
                                "expected": expected, "actual": snap_pose,
                                "preflight": tick_pending["preflight"]})
                            raise ProductReproduction("source-legal automatic north pixel did not advance as expected")
                        advance += 1
                    elif kind == "center-stop":
                        stopped = (snap_pose == stage_walk_pose(16) and
                                   (snap_input.get("player_dir"), snap_input.get("player_want"),
                                    snap_input.get("player_manual"), snap_input.get("joy_dir")) ==
                                   (DIR_NONE, DIR_NONE, 0, DIR_NONE))
                        record["center_stop_no_move"] = stopped
                        if not center_candidate_seen or not stopped:
                            raise ProductReproduction("automatic center stop moved or failed to clear direction/request")
                        center_stop_seen = True
                        cases["center_stop"] = {"pre_pose": tick_pending["pre_pose"],
                                                 "post_pose": snap_pose,
                                                 "pre_input": tick_pending["pre_input"],
                                                 "post_input": snap_input,
                                                 "no_movement": True,
                                                 "center_source_pc": hex(center_pc),
                                                 "site_proof": record.get("site_proof")}
                        if args.case == "neutral":
                            client.raw.call("inject_key", {"key": KEY_UP, "action": "press"}, timeout=2.0)
                            cases["post_stop_control_setup"] = {"key": KEY_UP,
                                                               "queued_after_center_stop": True,
                                                               "additional_guest_writes": 0}
                    else:
                        final_draws += 1
                        expected_fb = 0x75EC + ((320 if args.case == "held" else -320) * final_draws)
                        expected_cell_y = (19 if args.case == "held" else 17) if final_draws == 4 else 18
                        expected = {"cell": [12, expected_cell_y], "fb": hex(expected_fb),
                                    "step": final_draws % 4}
                        record["post_ready_draw_ordinal"] = final_draws
                        if snap_pose != expected:
                            cases["product_findings"].append({"kind": "post-ready-position-miss",
                                "expected": expected, "actual": snap_pose,
                                "preflight": tick_pending.get("preflight")})
                            raise ProductReproduction("admitted post-ready direction failed the approved one-cell movement")
                        if (snap_input.get("joy_dir"), snap_input.get("player_dir"),
                                snap_input.get("player_face"), snap_input.get("player_want"),
                                snap_input.get("player_manual")) != \
                                (input_direction, input_direction, input_direction, input_direction, 1):
                            raise ProductReproduction("post-ready held direction was lost before one-cell movement completed")
                    tick_pending = None
                if event == "input-return" and record not in cases["input_samples"]:
                    cases["last_input_sample"] = record
                # The exact PC whitelist is the stop discriminator. Monitor reason
                # labels have changed across XRoar revisions and are not evidence.
        finally:
            for ident in breakpoint_ids:
                if phase.remaining() > READ_RESERVE:
                    try:
                        client.raw.call("clear_breakpoint", {"id": ident}, timeout=2.0)
                    except Exception:
                        pass
        if tick_pending is not None:
            raise MissingCoverage("stage-entry run ended before the observed player tick reached draw")
        cases["full_walk"] = {"advances": advance, "expected_advances": 16,
                              "center_stop_seen": center_stop_seen,
                              "post_ready_input_sampled": post_ready_input,
                              "post_ready_draws": final_draws,
                              "required_post_ready_draws": 4,
                              "movement_path": [stage_walk_pose(n) for n in range(17)]}
        if advance != 16 or not center_stop_seen or not post_ready_input or final_draws != 4:
            raise MissingCoverage("full approved stage-entry sequence did not complete")
        cases["phases"].append({"name": "stage2-release-through-full-walk-and-next-move",
                                "elapsed_seconds": round(PHASE_SECONDS - phase.remaining(), 3),
                                "stops": phase.stops, "release_marker": release_stop.get("site_proof")})
        cases["result"] = "stage_entry_full_walk_pass"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(cases, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return cases
    except ProductReproduction as exc:
        cases["result"] = "product_reproduced"
        cases["failure"] = {"type": "product_reproduction", "message": str(exc)}
        if client is not None:
            cases["last_qualified_marker"] = client.last_qualified_marker
            cases["fixture_write_trace"] = [[hex(a), value] for a, value in client.fixture_seen]
        if phase is not None:
            cases["last_phase"] = {"elapsed_seconds": round(phase.clock() - phase.started, 3),
                                   "remaining_seconds": round(phase.remaining(), 3),
                                   "stops": phase.stops}
        if not output.exists():
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(cases, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return cases
    except MissingCoverage as exc:
        cases["result"] = "missing_coverage"
        cases["failure"] = {"type": "missing_coverage", "message": str(exc)}
        if client is not None:
            cases["last_qualified_marker"] = client.last_qualified_marker
            cases["fixture_write_trace"] = [[hex(a), value] for a, value in client.fixture_seen]
        if phase is not None:
            cases["last_phase"] = {"elapsed_seconds": round(phase.clock() - phase.started, 3),
                                   "remaining_seconds": round(phase.remaining(), 3),
                                   "stops": phase.stops}
        if not output.exists():
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(cases, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return cases
    except Exception as exc:
        cases["result"] = "setup_or_observer_failure"
        cases["failure"] = {"type": type(exc).__name__, "message": str(exc)}
        if client is not None:
            cases["last_qualified_marker"] = client.last_qualified_marker
            cases["fixture_write_trace"] = [[hex(a), value] for a, value in client.fixture_seen]
        if phase is not None:
            cases["last_phase"] = {"elapsed_seconds": round(phase.clock() - phase.started, 3),
                                   "remaining_seconds": round(phase.remaining(), 3),
                                   "stops": phase.stops}
        if not output.exists():
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(cases, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        raise
    finally:
        if client is not None:
            try:
                if not client.restored:
                    client.close()
                client.raw.close()
            except Exception:
                pass
        if process is not None:
            if process.poll() is None:
                process.kill()
            try:
                process.wait(timeout=2)
            except Exception:
                pass


def run_case(args: argparse.Namespace) -> dict[str, Any]:
    if not args.run_live:
        raise ProbeError("live adapter requires explicit --run-live; this invocation is not authorized by offline checks")
    output = Path(args.output).resolve()
    if not inside(output, SCHEDULED_OWNED) or output.exists():
        raise ProbeError("output must be a fresh, nonexisting path inside the owned scratch directory")
    build = Path(args.build).resolve()
    cases = {"case": args.case, "phases": [], "classifications": {}, "product_findings": [],
             "known_bug046_findings": [],
             "scope": "approved two-run first-scheduled-step diagnosis; preview retained as BUG-046 context"}
    process = None
    client = None
    phase = None
    try:
        cases["pins"] = artifact_check(build)
        monitor = _monitor_module()
        pres_syms = symbols_for(build, "ladybug-presentation-runtime.map")
        main_syms = symbols_for(build, "ladybug.map")
        site_images = SiteQualifier(build)
        xroar = Path(args.xroar) if args.xroar else ROOT / "docs" / "reference" / "xroar" / "src" / "xroar"
        # Phase 1: ordinary start, first-life completion, fixed one-cell approach to adjacent flower.
        phase = PhaseBudget()
        process, client = launch_owned(xroar, build / "ladybug.rom", phase, monitor)
        cases["xroar_binary"] = str(xroar.resolve())
        def reach(sym: dict[str, int], name: str, tag: str) -> dict[str, Any]:
            return run_to_condition(client, phase, marker_addr(sym, name), tag, lambda: True,
                                    lambda pc: site_images.qualify(client, pc, "presentation"))
        reach(pres_syms, "presentation_flow_tick", "initial PFT")
        image = live_image_check(client, build)
        reach(pres_syms, "demo_run", "attract exit")
        client.raw.call("inject_key", {"key": KEY_COIN, "action": "press"}, timeout=2.0)
        reach(pres_syms, "credit_tick", "credit")
        client.raw.call("inject_key", {"key": KEY_COIN, "action": "release"}, timeout=2.0)
        client.raw.call("inject_key", {"key": KEY_ENTER, "action": "press"}, timeout=2.0)
        reach(pres_syms, "normal_game", "credited game start")
        client.raw.call("inject_key", {"key": KEY_ENTER, "action": "release"}, timeout=2.0)
        mainloop = marker_addr(main_syms, "mainloop")
        run_to_condition(client, phase, mainloop, "first-life ready", lambda:
                         read_byte(client, INITIAL_ENTRY) == 0 and
                         read_word(client, PLAYER_FB) == 0x75EC,
                         lambda pc: site_images.qualify(client, pc, "main"))
        start_cell = [read_byte(client, PLAYER_X), read_byte(client, PLAYER_Y)]
        if start_cell != [12, 18]:
            raise ProbeError("first-life automatic entry reached an unexpected source cell: %r" % start_cell)
        entry_edge = source_neighbor_gate(client, main_syms, build, (12, 18), (12, 17),
                                          require_flower=False)
        client.raw.call("inject_key", {"key": KEY_UP, "action": "press"}, timeout=2.0)
        run_to_condition(client, phase, mainloop, "one-cell legal approach", lambda:
                         (read_byte(client, PLAYER_X), read_byte(client, PLAYER_Y)) == (12, 17),
                         lambda pc: site_images.qualify(client, pc, "main"))
        client.raw.call("inject_key", {"key": KEY_UP, "action": "release"}, timeout=2.0)
        adjacency = source_neighbor_gate(client, main_syms, build, (12, 17), (12, 16),
                                         require_flower=True)
        pre = state_snapshot(client)
        cases["paired_predecessor"] = {"state": pre, "sha256": canonical_hash(pre),
                                         "entry_edge": entry_edge, "flower_edge": adjacency}
        cases["phases"].append({"name": "cold-legal-predecessor", "elapsed_seconds": round(45-phase.remaining(), 3),
                                 "stops": phase.stops, "live_images": image})
        if args.case == "held":
            if not args.paired_neutral:
                raise ProbeError("held case requires the completed neutral evidence path")
            neutral_path = Path(args.paired_neutral).resolve()
            if not inside(neutral_path, SCHEDULED_OWNED) or not neutral_path.is_file():
                raise ProbeError("paired neutral evidence must be an existing file in the owned directory")
            prior = json.loads(neutral_path.read_text(encoding="utf-8"))
            if prior.get("case") != "neutral" or prior.get("paired_predecessor", {}).get("sha256") != cases["paired_predecessor"]["sha256"]:
                raise ProbeError("neutral/held cold predecessor identity mismatch; no retry permitted")
        # Phase 2: exact fixture, one ordinary northward flower pickup, stage-2 preview.
        phase = PhaseBudget()
        client.budget = phase
        fixture = apply_fixture(client)
        client.raw.call("inject_key", {"key": KEY_UP, "action": "press"}, timeout=2.0)
        pres_level = marker_addr(pres_syms, "level_tick")
        run_to_condition(client, phase, pres_level, "final flower to stage-2 preview", lambda:
                         read_byte(client, STAGE) == 2 and read_byte(client, PRES_MODE) == 6 and
                         read_byte(client, PRES_SCREEN) == 2 and read_byte(client, PRES_CONTEXT) == 2,
                         lambda pc: site_images.qualify(client, pc, "presentation"))
        client.raw.call("inject_key", {"key": KEY_UP, "action": "release"}, timeout=2.0)
        owner = read_byte(client, FRONT)
        preview = stage_preview_oracle(client, owner, build)
        cases["fixture"] = fixture
        cases["preview_publication"] = preview
        if preview["stored_masks"]["classification"] != "match":
            cases["known_bug046_findings"].append({"phase": "stage2-preview",
                "kind": "stored-mask-mismatch", "detail": preview["stored_masks"]})
        if preview["word_oracle"]["classification"] != "pixel_match":
            cases["known_bug046_findings"].append({"phase": "stage2-preview",
                "kind": "word-pixel-mismatch", "detail": preview["word_oracle"]})
        cases["phases"].append({"name": "final-flower-to-first-stage2-preview",
                                 "elapsed_seconds": round(45-phase.remaining(), 3), "stops": phase.stops})
        preview_seq = int(preview["commit_seq"])
        # Phase 3: qualify the stage-2 semantic release and capture exactly one scheduled move.
        phase = PhaseBudget()
        client.budget = phase
        if args.case == "held":
            # The preview remains foreground-owned until the proven context-2 release;
            # this gives the ordinary decoder time to sample Down before any gameplay call.
            client.raw.call("inject_key", {"key": KEY_DOWN, "action": "press"}, timeout=2.0)
            cases["held_input_setup"] = {"key": KEY_DOWN, "queued_while": "stage-2 preview owns foreground",
                                          "writes_added": 0}
        release_pc = stage2_release_pc(build)
        run_to_condition(client, phase, release_pc, "stage-2 context-2 release branch",
                         lambda: read_byte(client, STAGE) == 2 and
                         read_byte(client, PRES_MODE) == 6 and
                         read_byte(client, PRES_SCREEN) == 2 and
                         read_byte(client, PRES_CONTEXT) == 0 and
                         (read_byte(client, PLAYER_X), read_byte(client, PLAYER_Y)) == (12, 22) and
                         read_word(client, PLAYER_FB) == 0x89EC and
                         read_byte(client, PLAYER_STEP) == 0,
                         lambda pc: site_images.qualify(client, pc, "presentation"))
        release_pose = {"stage": read_byte(client, STAGE), "mode": read_byte(client, PRES_MODE),
                        "screen": read_byte(client, PRES_SCREEN),
                        "context": read_byte(client, PRES_CONTEXT),
                        "cell": [read_byte(client, PLAYER_X), read_byte(client, PLAYER_Y)],
                        "fb": hex(read_word(client, PLAYER_FB)),
                        "step": read_byte(client, PLAYER_STEP),
                        "release_pc": hex(release_pc)}
        cases["stage2_release"] = release_pose
        if release_pose["stage"] != 2 or release_pose["mode"] != 6 or \
                release_pose["screen"] != 2 or release_pose["context"] != 0 or \
                release_pose["cell"] != [12, 22] or release_pose["fb"] != "0x89ec" or \
                release_pose["step"] != 0:
            raise MissingCoverage("source-qualified stage-2 release did not retain the approved start pose")
        north_edge = source_neighbor_gate(client, main_syms, build, (12, 22), (12, 21),
                                          require_flower=False)
        entry_pc = marker_addr(main_syms, "player_tick")
        draw_pc = marker_addr(main_syms, "pt_draw")
        entry_bp = Breakpoint(client, phase, entry_pc, "first scheduled player_tick",
                              lambda pc: site_images.qualify(client, pc, "main"))
        draw_bp = Breakpoint(client, phase, draw_pc, "first pt_draw of first scheduled call",
                             lambda pc: site_images.qualify(client, pc, "main"))
        try:
            entry_stop = entry_bp.hit()
            entry = scheduled_state(client)
            cases["scheduled_step"] = {"movement_ordinal": 1, "player_tick_calls": 1,
                "draw_ordinal": 0, "draw_count": 0, "entry": entry, "draw": None,
                "entry_stop": entry_stop, "caller_proof": None,
                "source_legal_north_edge": north_edge, "release_pose": release_pose}
            caller_proof = live_active_caller_check(client, build)
            cases["scheduled_step"]["caller_proof"] = caller_proof
            entry_pending = entry["flags"].get(hex(PLAYER_TICK_PENDING))
            if entry_pending != 0 or caller_proof["entry_pending_expected"] != 0:
                raise ProbeError("eligible pending tick was not consumed before player_tick entry")
            if entry["position"] != {"cell": [12, 22], "fb": "0x89ec", "step": 0}:
                raise MissingCoverage("first scheduled call entry does not match the approved stage-2 pose")
            if args.case == "held" and entry["input"]["joy_dir"] != DIR_SOUTH:
                raise MissingCoverage("held Down was not visible in sampled JOY_DIR at first player_tick entry")
            if args.case == "neutral" and entry["input"]["joy_dir"] != DIR_NONE:
                raise MissingCoverage("neutral input was not visible in sampled JOY_DIR at first player_tick entry")
            draw_stop = draw_bp.hit()
            draw = scheduled_state(client)
            cases["scheduled_step"].update({"draw_ordinal": 1, "draw_count": 1,
                                             "draw": draw, "draw_stop": draw_stop})
        finally:
            draw_bp.close()
            entry_bp.close()
        cases["scheduled_step"] = {"movement_ordinal": 1, "player_tick_calls": 1,
            "draw_ordinal": 1, "draw_count": 1, "entry": entry, "draw": draw,
            "entry_stop": entry_stop, "draw_stop": draw_stop,
            "caller_proof": caller_proof, "source_legal_north_edge": north_edge,
            "release_pose": release_pose}
        cases["phases"].append({"name": "stage2-release-through-first-scheduled-draw",
                                 "elapsed_seconds": round(45-phase.remaining(), 3),
                                 "stops": phase.stops, "release_pc": hex(release_pc)})
        if args.case == "held":
            comparison = compare_scheduled_pair(prior, cases)
            cases["scheduled_comparison"] = comparison
            if comparison["result"] != "pass":
                cases["product_findings"].append({"phase": "first-scheduled-step",
                    "kind": comparison["result"], "detail": comparison})
        elif draw["position"] != {"cell": [12, 22], "fb": "0x88ac", "step": 1}:
            cases["product_findings"].append({"phase": "first-scheduled-step",
                "kind": "neutral-target-miss", "expected": {"cell": [12, 22],
                "fb": "0x88ac", "step": 1}, "actual": draw["position"]})
        cases["classifications"] = {
            "preview_masks": preview["stored_masks"]["classification"],
            "preview_pixels": preview["word_oracle"]["classification"],
            "preview_findings_are_known_bug046": True,
            "scheduled_step": cases.get("scheduled_comparison", {}).get("result", "awaiting paired run")}
        if cases["product_findings"]:
            cases["result"] = "product_reproduced"
        elif args.case == "neutral":
            cases["result"] = "scheduled_step_captured_pair_pending"
        else:
            cases["result"] = "scheduled_pair_position_match"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(cases, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return cases
    except ProductReproduction as exc:
        cases["result"] = "product_reproduced"
        cases["failure"] = {"type": "product_reproduction", "message": str(exc)}
        if client is not None:
            cases["last_qualified_marker"] = client.last_qualified_marker
            cases["fixture_write_trace"] = [[hex(a), value] for a, value in client.fixture_seen]
        if phase is not None:
            cases["last_phase"] = {"elapsed_seconds": round(phase.clock() - phase.started, 3),
                                   "remaining_seconds": round(phase.remaining(), 3),
                                   "stops": phase.stops}
        if not output.exists():
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(cases, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return cases
    except MissingCoverage as exc:
        cases["result"] = "missing_coverage"
        cases["failure"] = {"type": "missing_coverage", "message": str(exc)}
        if client is not None:
            cases["last_qualified_marker"] = client.last_qualified_marker
            cases["fixture_write_trace"] = [[hex(a), value] for a, value in client.fixture_seen]
        if phase is not None:
            cases["last_phase"] = {"elapsed_seconds": round(phase.clock() - phase.started, 3),
                                   "remaining_seconds": round(phase.remaining(), 3),
                                   "stops": phase.stops}
        if not output.exists():
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(cases, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return cases
    except Exception as exc:
        cases["result"] = "setup_or_observer_failure"
        cases["failure"] = {"type": type(exc).__name__, "message": str(exc)}
        if client is not None:
            cases["last_qualified_marker"] = client.last_qualified_marker
            cases["fixture_write_trace"] = [[hex(a), value] for a, value in client.fixture_seen]
        if phase is not None:
            cases["last_phase"] = {"elapsed_seconds": round(phase.clock() - phase.started, 3),
                                   "remaining_seconds": round(phase.remaining(), 3),
                                   "stops": phase.stops}
        if not output.exists():
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(cases, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        raise
    finally:
        if client is not None:
            try:
                if not client.restored:
                    client.close()
                client.raw.close()
            except Exception:
                pass
        if process is not None:
            if process.poll() is None:
                process.kill()
            try:
                process.wait(timeout=2)
            except Exception:
                pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path, default=BUILD_DEFAULT)
    parser.add_argument("--scenario", choices=("scheduled-step", "hidden-owner", "stage-entry"),
                        default="scheduled-step",
                        help="select the legacy scheduled-step, BUG-046 hidden-owner, or BUG-117 full-walk path")
    parser.add_argument("--case", choices=("neutral", "held"))
    parser.add_argument("--paired-neutral", type=Path)
    parser.add_argument("--xroar", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--artifact-check", action="store_true")
    parser.add_argument("--write-preparation", action="store_true")
    parser.add_argument("--preparation-output", type=Path,
                        help="fresh manifest path inside the owned directory; never overwrites")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--run-live", action="store_true",
                        help="explicit execution switch; separate parent runtime authorization is still required")
    args = parser.parse_args(argv)
    try:
        if args.self_test:
            print(json.dumps(self_test(), indent=2, sort_keys=True))
            return 0
        if args.artifact_check:
            if args.scenario == "stage-entry":
                pins = artifact_check(args.build)
                qualification = offline_stage_entry_check(args.build)
                result = {"scenario": "stage-entry", "pins": pins,
                          "offline_qualification": qualification,
                          "source_site_check": offline_source_site_check(args.build),
                          "offline_self_test": self_test(),
                          "probe_sha256": file_sha(Path(__file__)),
                          "helper_sha256": {"monitor": file_sha(ROOT / "scripts" / "verify_bug009_monitor_input.py"),
                                            "runtime": file_sha(ROOT / "scripts" / "verify_bug011_runtime.py")},
                          "runtime_authorized": False, "capsule_only": True,
                          "phase_contract": {"phase_seconds_max": PHASE_SECONDS,
                                             "stop_seconds_max": STOP_SECONDS,
                                             "stops_per_phase_max": MAX_STOPS,
                                             "phases_per_run": 3, "runs_max": 2,
                                             "max_seconds_per_run": 135,
                                             "max_seconds_total": 270,
                                             "retry_policy": "none"},
                          "proposed_runtime_commands": [
                              "python -B repro/stage-preview-diagnosis-20261014/probe.py --scenario stage-entry --case neutral --run-live --build repro/bug117-stage-repair-20261015/capsule/build --output repro/bug117-stage-repair-20261015/observer/stage-entry-neutral.json",
                              "python -B repro/stage-preview-diagnosis-20261014/probe.py --scenario stage-entry --case held --run-live --build repro/bug117-stage-repair-20261015/capsule/build --paired-neutral repro/bug117-stage-repair-20261015/observer/stage-entry-neutral.json --output repro/bug117-stage-repair-20261015/observer/stage-entry-held.json"],
                          "commands_are_proposals_only": True,
                          "runtime_readiness": "offline preparation only; parent source review and exclusive runtime lease required"}
            elif args.scenario == "hidden-owner":
                pins = artifact_check(args.build)
                result = {"scenario": "hidden-owner", "pins": pins,
                          "offline_qualification": hidden_offline_qualification(),
                          "rejected_observer_assumptions": [
                              {"assumption": "compatibility helper origin was $0600",
                               "result": "rejected; pinned source listing and staged image begin at $06B2"},
                              {"assumption": "hold request selected owner1 from a guessed opcode sequence",
                               "result": "rejected; listing/staged bytes at $0712 begin 1A10 8602 9790 8601 9791"},
                              {"assumption": "the selected-BACK mapper's short expected byte sequence was complete",
                               "result": "rejected; exact 31-byte listing/staged window at $1C2E now includes PAR1-PAR4 stores, PAR5=$3A store, and RTS"},
                              {"assumption": "hidden capture order must be BACK0 then BACK1",
                               "result": "rejected; runtime order derives from saved BACK then saved FRONT and requires the exact set {0,1}"},
                              {"assumption": "map_back's $3A PAR5 is still active at helper return $1B21",
                               "result": "rejected; caller maps PAR5=$23 before JSR $B080, so return qualification requires $23"},
                              {"assumption": "historical visible owner1 evidence proves hidden BACK0 pixels",
                               "result": "rejected; its pixel hash matches synthetic unlit output but no crop bytes or hidden BACK0 capture were retained"},
                              {"assumption": "historical clean_underlay can be reused without its BUG-122 retention.json",
                               "result": "rejected; that path remains unusable and no retention file was synthesized"},
                          ],
                          "scheduled_step_source_check": offline_scheduled_step_check(args.build),
                          "source_site_check": offline_source_site_check(args.build),
                          "offline_self_test": self_test(),
                          "probe_sha256": file_sha(Path(__file__)),
                          "helper_sha256": {"monitor": file_sha(ROOT / "scripts" / "verify_bug009_monitor_input.py"),
                                            "runtime": file_sha(ROOT / "scripts" / "verify_bug011_runtime.py")},
                          "runtime_authorized": False, "capsule_only": True,
                          "phase_contract": {"phase_seconds_max": PHASE_SECONDS,
                                             "stop_seconds_max": STOP_SECONDS,
                                             "stops_per_phase_max": MAX_STOPS,
                                             "planned_runs": 1, "runs_max": 2,
                                             "phases_per_run": 3,
                                             "planned_total_seconds_max": 135,
                                             "contract_total_seconds_max": 270,
                                             "retry_policy": "none"},
                          "proposed_runtime_commands": [
                              "python3 -B repro/stage-preview-diagnosis-20261014/probe.py --scenario hidden-owner --build repro/bug046-display-repair-20261015/capsule/build --run-live --output repro/bug046-hidden-owner-20261015/hidden-owner.json"],
                          "commands_are_proposals_only": True,
                          "runtime_readiness": "offline preparation only; parent lease and review required"}
            else:
                pins = artifact_check(args.build)
                result = {"pins": pins, "source_site_check": offline_source_site_check(args.build),
                          "scheduled_step_source_check": offline_scheduled_step_check(args.build),
                          "offline_self_test": self_test(), "word_oracle": word_oracle(),
                          "probe_sha256": file_sha(Path(__file__)),
                          "helper_sha256": {"monitor": file_sha(ROOT / "scripts" / "verify_bug009_monitor_input.py"),
                                            "runtime": file_sha(ROOT / "scripts" / "verify_bug011_runtime.py")},
                          "runtime_authorized": False, "capsule_only": True,
                          "phase_contract": {"phase_seconds_max": PHASE_SECONDS,
                                             "stop_seconds_max": STOP_SECONDS,
                                             "stops_per_phase_max": MAX_STOPS,
                                             "runs": 2, "phases_per_run": 3,
                                             "total_seconds_max": 270,
                                             "retry_policy": "none"},
                          "proposed_runtime_commands": [
                              "python repro/stage-preview-diagnosis-20261014/probe.py --case neutral --run-live --output repro/bug117-scheduled-step-20261015/scheduled-neutral.json",
                              "python repro/stage-preview-diagnosis-20261014/probe.py --case held --run-live --paired-neutral repro/bug117-scheduled-step-20261015/scheduled-neutral.json --output repro/bug117-scheduled-step-20261015/scheduled-held.json"],
                          "commands_are_proposals_only": True}
            if args.write_preparation:
                preparation_root = (STAGE_ENTRY_OWNED if args.scenario == "stage-entry" else
                                    HIDDEN_OWNED if args.scenario == "hidden-owner" else SCHEDULED_OWNED)
                default_name = ("preparation.json" if args.scenario == "stage-entry" else
                                "offline-preparation.json" if args.scenario == "hidden-owner" else
                                "preparation-final.json")
                manifest_path = (args.preparation_output or (preparation_root / default_name)).resolve()
                if not inside(manifest_path, preparation_root) or manifest_path.exists():
                    raise ProbeError("preparation manifest path already exists or leaves owned directory")
                manifest_path.parent.mkdir(parents=True, exist_ok=True)
                result["preparation_path"] = str(manifest_path)
                manifest_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                                          encoding="utf-8")
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        if args.write_preparation:
            parser.error("--write-preparation requires --artifact-check")
        if args.preparation_output is not None:
            parser.error("--preparation-output requires --artifact-check --write-preparation")
        if args.scenario == "stage-entry":
            if args.case is None or args.output is None:
                parser.error("stage-entry runtime requires --case neutral|held and a fresh --output path")
            if not args.run_live:
                parser.error("stage-entry runtime requires --run-live and separate parent runtime authorization")
            result = run_stage_entry_case(args)
            print(json.dumps({"result": result.get("result"), "output": str(args.output),
                              "sha256": file_sha(Path(args.output)) if Path(args.output).is_file() else None},
                             indent=2, sort_keys=True))
            return 0
        if args.scenario == "hidden-owner":
            if args.case is not None or args.paired_neutral is not None:
                parser.error("hidden-owner scenario has no --case or --paired-neutral mode")
            if args.output is None:
                parser.error("hidden-owner runtime requires --output inside repro/bug046-hidden-owner-20261015/")
            result = run_hidden_case(args)
            print(json.dumps({"result": result.get("result"), "output": str(args.output),
                              "sha256": file_sha(Path(args.output)) if Path(args.output).is_file() else None},
                             indent=2, sort_keys=True))
            return 0
        if args.case is None or args.output is None:
            parser.error("runtime adapter requires --case, --run-live, and a fresh --output path")
        if not args.run_live:
            parser.error("live adapter requires --run-live and separate parent runtime authorization")
        if args.case == "held" and args.paired_neutral is None:
            parser.error("held case requires --paired-neutral neutral evidence")
        result = run_case(args)
        print(json.dumps({"result": result.get("result"), "output": str(args.output),
                          "sha256": file_sha(Path(args.output))}, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"result": "setup_or_observer_failure", "error": "%s: %s" % (type(exc).__name__, exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
