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
CAPSULE = ROOT / "repro" / "bug122-integration-20261014" / "capsule"
BUILD_DEFAULT = CAPSULE / "build"
ROM_SHA = "4b775f8f1b4b2a25a82b7c5d2850ee595e49f402e9ff8060634a0095a7c6dfd5"
RECEIPT_SHA = "5a2601d51a7a526bd228db7f46e0fa872a6e53e2c0197297038078f3694237fc"
REVISION = "3926a4ad73bae3665e619cf9c3154cb8d3d2ed60"
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
FRONT, BACK, PENDING, COMMIT = 0x8F, 0x90, 0x91, 0x92
PLAYER_X, PLAYER_Y, PLAYER_FB, PLAYER_STEP = 0x09, 0x0A, 0x0B, 0x08
JOY_X, JOY_Y, JOY_DIR = 0x01, 0x04, 0x05
PLAYER_DIR, PLAYER_FACE = 0x06, 0x07
PLAYER_WANT, PLAYER_MANUAL = 0x0F, 0x18
STAGE, DOTS_LEFT, STAGE_PENDING = 0x24, 0x25, 0x26
SPECIAL, EXTRA, BONUS_LEFT, INITIAL_ENTRY, RENDER_FLAGS = 0x3C, 0x3D, 0x33, 0xA0, 0x7F
MAZE_STATE, PAR5 = 0xA000, 0xFFA5
ENTITY_COUNT, ENTITY_TABLE = 0x32, 0xA380
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


def artifact_check(build: Path) -> dict[str, Any]:
    build = build.resolve()
    if build != BUILD_DEFAULT.resolve():
        raise ProbeError("build path must be the parent-approved immutable capsule/build")
    capsule = build.parent
    receipt_path = build / "source-build-receipt.json"
    receipt_bytes = receipt_path.read_bytes()
    if sha(receipt_bytes) != RECEIPT_SHA:
        raise ProbeError("frozen source-build receipt hash mismatch")
    receipt = json.loads(receipt_bytes.decode("utf-8"))
    if (receipt.get("state"), receipt.get("profile"), receipt.get("revision")) != (
            "complete", "complete", REVISION):
        raise ProbeError("frozen receipt profile/state/revision mismatch")
    inputs = receipt.get("inputs", {})
    generated = receipt.get("generated_inputs", {})
    artifacts = receipt.get("artifacts", {})
    if len(inputs) != 266 or len(generated) != 4:
        raise ProbeError("receipt must contain exactly 266 authored inputs and four generated inputs")
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
    if file_sha(build / "ladybug.rom") != ROM_SHA:
        raise ProbeError("pinned tested ROM mismatch")
    return {
        "build": str(build), "revision": REVISION, "receipt_sha256": RECEIPT_SHA,
        "rom_sha256": ROM_SHA, "authored_inputs_checked": checked_inputs,
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
        def __init__(self, par0: int = 0x38, corrupt_physical: bool = False):
            self.par0, self.corrupt_physical = par0, corrupt_physical
            self.runtime = (BUILD_DEFAULT / "ladybug-runtime.rom").read_bytes()
            self.enemy = (BUILD_DEFAULT / "ladybug-enemy-runtime.rom").read_bytes()
            self.presentation = (BUILD_DEFAULT / "ladybug-presentation-runtime.bin").read_bytes()
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
    strict_import_check(Path(__file__).resolve())
    return {"result": "pass", "checks": 26, "word_tiles": positive["tiles_checked"],
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
            "unsampled_held_input_is_missing_coverage": True}


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
        self.listings = {
            "main": listing_byte_map(build / "ladybug.lst"),
            "enemy": listing_byte_map(build / "ladybug-enemy-runtime.lst"),
            "presentation": listing_byte_map(build / "ladybug-presentation-runtime.lst"),
        }

    def qualify(self, client: DeadlineClient, address: int, kind: str) -> dict[str, Any]:
        if kind == "main" and 0xC000 <= address < 0xFE00:
            artifact, source_addr, par_indexes = self.main, address - 0xC000, (6, 7)
            expected_pars = (0x3E, 0x3F)
            physical_page = 0x3E if address < 0xE000 else 0x3F
            physical_offset = address - (0xC000 if address < 0xE000 else 0xE000)
        elif kind == "enemy" and ENEMY_ORIGIN <= address < ENEMY_ORIGIN + len(self.enemy):
            artifact, source_addr, par_indexes = self.enemy, address - ENEMY_ORIGIN, (0,)
            expected_pars = (0x38,)
            physical_page, physical_offset = 0x38, address
        elif kind == "presentation" and PRES <= address < PRES + len(self.presentation):
            artifact, source_addr, par_indexes = self.presentation, address - PRES, (0,)
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
            "source_revision": REVISION}


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
                manifest_path = (args.preparation_output or (SCHEDULED_OWNED / "preparation-final.json")).resolve()
                if not inside(manifest_path, SCHEDULED_OWNED) or manifest_path.exists():
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
