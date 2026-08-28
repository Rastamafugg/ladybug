#!/usr/bin/env python3
"""Exercise the isolated FEAT-003 high-score test profile in XRoar."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import sys
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import verify_bug011_runtime as runtime  # noqa: E402
from build_screen import PALETTE, gime_rgb  # noqa: E402


ROM = ROOT / "build/ladybug.rom"
XROAR = ROOT / "docs/reference/xroar/src/xroar"
MANIFEST = ROOT / "build/ladybug-presentation.json"
MODULE_MAP = ROOT / "build/ladybug-presentation-runtime.map"
MODULE_RUNTIME = ROOT / "build/ladybug-presentation-runtime.bin"
DEMO_MAP = ROOT / "build/ladybug-demo-runtime.map"
DEMO_RUNTIME = ROOT / "build/ladybug-demo-runtime.bin"
INCLUDE = ROOT / "build/ladybug_presentation.inc"
COLD = ROOT / "build/ladybug-presentation-cold.bin"
RUNTIME_ROM = ROOT / "build/ladybug-runtime.rom"
PRES_MODE = 0x00A5
PRES_SCREEN = 0x00A6
PRES_NAME_ROW = 0x00DF
PRES_NAME_COL = 0x00E0
PRES_NAME_REPEAT = 0x00E1
PRES_NAME_LAST_DIR = 0x00E2
PRES_NAME_LEN = 0x00CB
PRES_INSERT = 0x00C9
PRES_SCORE = 0x00BF
PRES_TABLE = 0xAF84
PRES_NAME = 0xAFDE
JOY_DIR = 0x0005
PAR5 = 0xFFA5
PRES_TIMER = 0x00B0
PRES_NAME_TIMER_PHASE = 0x00E8
PRES_NAME_TIMER_BOX = 0x00E9
MAP_HIGH_SCORE = 3
MAP_ENTER_HIGH_SCORE = 5
MODE_NAME = 8


def symbols(path: Path) -> dict[str, int]:
    return {
        name: int(value, 16)
        for name, value in re.findall(
            r"^Symbol: (\w+) .* = ([0-9A-Fa-f]+)$",
            path.read_text(encoding="utf-8"), re.MULTILINE,
        )
    }


def constants(path: Path) -> dict[str, int]:
    return {
        name: int(value[1:], 16) if value.startswith("$") else int(value)
        for name, value in re.findall(
            r"^(PRESENTATION_GLYPH_\d+) equ (\$[0-9A-Fa-f]+|\d+)$",
            path.read_text(encoding="ascii"), re.MULTILINE,
        )
    }


def bcd_digits(score: bytes) -> list[int]:
    return [digit for value in score for digit in (value >> 4, value & 15)]


def lzss_expand(stream: bytes, expected_bytes: int) -> bytes:
    output = bytearray()
    cursor = 0
    while len(output) < expected_bytes:
        flags = stream[cursor]
        cursor += 1
        for bit in range(8):
            if len(output) >= expected_bytes:
                break
            if flags & (1 << bit):
                output.append(stream[cursor])
                cursor += 1
                continue
            token = int.from_bytes(stream[cursor:cursor + 2], "big")
            cursor += 2
            distance = token >> 4
            length = (token & 0x0F) + 3
            if distance == 0 or distance > len(output):
                raise ValueError("invalid presentation atlas match distance")
            for _ in range(length):
                output.append(output[-distance])
                if len(output) > expected_bytes:
                    raise ValueError("presentation atlas exceeds its output bound")
    return bytes(output)


def expected_tile(manifest: dict[str, object], tile_id: int) -> bytes:
    cold = COLD.read_bytes()
    base = int(manifest["gameplay_tile_base"])
    if tile_id < base:
        atlas = lzss_expand(
            cold[:int(manifest["tile_atlas_compressed_bytes"])],
            int(manifest["tile_atlas_expanded_bytes"]),
        )
        return atlas[tile_id * 32:(tile_id + 1) * 32]
    lookup = int(manifest["gameplay_lookup_offset"]) + tile_id - base
    gameplay_id = cold[lookup]
    offset = 0xE3D0 - 0xC000 + gameplay_id * 32
    return RUNTIME_ROM.read_bytes()[offset:offset + 32]


def read_state(client, address: int, length: int) -> bytes:
    saved = runtime.read_byte(client, PAR5)
    try:
        runtime.write_byte(client, PAR5, 0x34)
        return runtime.read_bytes(client, address, length)
    finally:
        runtime.write_byte(client, PAR5, saved)


def write_state(client, address: int, data: bytes) -> None:
    saved = runtime.read_byte(client, PAR5)
    try:
        runtime.write_byte(client, PAR5, 0x34)
        client.call("write_memory", {"addr": address, "data": data.hex()})
    finally:
        runtime.write_byte(client, PAR5, saved)


def score_visible(frame: bytes, destination: int, score: bytes,
                  glyphs: dict[int, int], manifest: dict[str, object]) -> bool:
    for index, digit in enumerate(bcd_digits(score)):
        actual = runtime.frame_tile(frame, destination + index * 4)
        expected = expected_tile(manifest, glyphs[digit])
        if actual != expected:
            return False
    return True


def name_visible(frame: bytes, destination: int, name: bytes, black: int,
                 manifest: dict[str, object]) -> bool:
    tiles = [tile or black for tile in name] + [black, black]
    return all(
        runtime.frame_tile(frame, destination + index * 4) ==
        expected_tile(manifest, tile)
        for index, tile in enumerate(tiles)
    )


def tile_uses_only(frame: bytes, destination: int, colours: set[int]) -> bool:
    return all(
        nibble in colours
        for value in runtime.frame_tile(frame, destination)
        for nibble in (value >> 4, value & 0x0F)
    )


def tile_matches(frame: bytes, destination: int, expected: bytes) -> bool:
    return runtime.frame_tile(frame, destination) == expected


def png_chunk(kind: bytes, data: bytes) -> bytes:
    return (struct.pack(">I", len(data)) + kind + data +
            struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF))


def write_frame_png(path: Path, framebuffer: bytes) -> None:
    palette = [gime_rgb(value) for value in PALETTE]
    rows = bytearray()
    for y in range(192):
        rows.append(0)
        for value in framebuffer[y * 160:(y + 1) * 160]:
            rows.extend(palette[value >> 4])
            rows.extend(palette[value & 0x0F])
    payload = (
        b"\x89PNG\r\n\x1a\n" +
        png_chunk(b"IHDR", struct.pack(">IIBBBBB", 320, 192, 8, 2, 0, 0, 0)) +
        png_chunk(b"IDAT", zlib.compress(bytes(rows), 9)) +
        png_chunk(b"IEND", b"")
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def fail(marker: str, detail: str) -> None:
    raise SystemExit(f"FEAT-003 highscore-test: marker={marker} failure={detail}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xroar", type=Path, default=XROAR)
    parser.add_argument("--rom", type=Path, default=ROM)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / "build/feat003-highscore-test.json",
    )
    parser.add_argument("--initial-png", type=Path)
    parser.add_argument("--updated-png", type=Path)
    args = parser.parse_args()

    manifest = json.loads(MANIFEST.read_text(encoding="ascii"))
    if manifest.get("highscore_test_profile") is not True:
        fail("artifact-profile", "manifest is not highscore-test")
    module = symbols(MODULE_MAP)
    demo = symbols(DEMO_MAP)
    main_symbols = symbols(ROOT / "build/ladybug.map")
    required_module = ("presentation_flow_tick", "load_done_publish")
    required_demo = ("name_joy_ready",)
    if any(name not in module for name in required_module):
        fail("module-symbols", "required presentation symbol missing")
    if any(name not in demo for name in required_demo):
        fail("demo-symbols", "required auxiliary symbol missing")
    glyph_constants = constants(INCLUDE)
    glyphs = {digit: glyph_constants[f"PRESENTATION_GLYPH_{digit}"]
              for digit in range(10)}
    name_contract = manifest["high_score_name_entry"]
    node_tiles = name_contract["node_tile_ids"]
    black = manifest["black_tile"]
    timer_cells = [tuple(cell) for cell in name_contract["timer_cells"]]
    if (len(timer_cells) != 92 or len(set(timer_cells)) != 92 or
            len(name_contract["timer_base_tile_ids"]) != 92 or
            len(name_contract["timer_green_tile_ids"]) != 92 or
            len(name_contract["edge_masks"]) != 45):
        fail(
            "generated-contract",
            f"timer cells={len(timer_cells)} unique={len(set(timer_cells))} "
            f"base={len(name_contract['timer_base_tile_ids'])} "
            f"green={len(name_contract['timer_green_tile_ids'])} "
            f"edges={len(name_contract['edge_masks'])}",
        )
    fixture = b"".join(
        bytes((rank, 0, 0)) + bytes((glyphs[rank],)) * 7
        for rank in range(9, 0, -1)
    )
    expected_score = bytes((0x09, 0x50, 0x00))

    monitor = runtime.load_monitor()
    process, client = runtime.launch_fast(monitor, args.xroar, args.rom)
    evidence: dict[str, object] = {
        "schema": "ladybug-feat003-highscore-test-v1",
        "rom_sha256": hashlib.sha256(args.rom.read_bytes()).hexdigest(),
        "events": [],
    }
    ids: list[int] = []
    try:
        ids = monitor.setup(client, [module["load_done_publish"]])
        hit = client.run_to_breakpoint(args.timeout)
        if hit.get("pc") != module["load_done_publish"]:
            fail("entry-publication", str(hit))
        if runtime.read_byte(client, PRES_SCREEN) != MAP_ENTER_HIGH_SCORE:
            fail("entry-screen", "cold boot did not request map 5")
        if runtime.read_byte(client, PRES_MODE) not in (1, MODE_NAME):
            fail("entry-mode", "name mode was not loading or active")
        if runtime.read_bytes(client, 0x0300, DEMO_RUNTIME.stat().st_size) != DEMO_RUNTIME.read_bytes():
            fail("auxiliary-dispatch", "$0300 runtime differs from highscore auxiliary")
        saved_par5 = runtime.read_byte(client, 0xFFA5)
        runtime.write_byte(client, 0xFFA5, 0x3B)
        live_atlas = runtime.read_bytes(
            client, 0xA000, manifest["tile_atlas_expanded_bytes"]
        )
        runtime.write_byte(client, 0xFFA5, saved_par5)
        cold = COLD.read_bytes()
        expected_atlas = lzss_expand(
            cold[:manifest["tile_atlas_compressed_bytes"]],
            manifest["tile_atlas_expanded_bytes"],
        )
        if live_atlas != expected_atlas:
            fail("expanded-atlas", "boot destination differs from generated source")
        if read_state(client, PRES_TABLE, 90) != fixture:
            fail("dummy-table", "nine descending dummy records differ")
        if runtime.read_bytes(client, PRES_SCORE, 3) != expected_score:
            fail("pending-score", "pending player score is not 095000")
        if runtime.read_byte(client, PRES_INSERT) != 0:
            fail("pending-rank", "player is not pending at rank 1")
        if read_state(client, PRES_NAME, 7) != bytes((black,)) * 7:
            fail("pending-name", "name is not blank")
        if (runtime.read_byte(client, PRES_NAME_ROW),
                runtime.read_byte(client, PRES_NAME_COL)) != (9, 2):
            fail("sprite-start", "runtime cursor differs from authored marker")
        owners = [runtime.read_owner(client, owner) for owner in (0, 1)]
        cursor_destination = name_contract["cursor_destination"]
        if any(not any(runtime.frame_tile(frame, cursor_destination,
                                           width=8, rows=16))
               for frame in owners):
            fail("cursor-render", "starting Lady Bug is absent on an owner")
        inner_wall_destination = 0x2000 + 3 * 1280 + 11 * 4
        border_destination = 0x2000 + 0 * 1280 + 9 * 4
        if any(
                not tile_uses_only(frame, inner_wall_destination, {0, 4}) or
                not tile_uses_only(frame, border_destination, {0, 4, 6})
                for frame in owners):
            fail("wall-palette", "inner or border wall is not wall-coloured")
        score_dst = name_contract["score_destinations"][0]
        top_dst = name_contract["top_destinations"][0]
        top_right_dst = name_contract["top_right_destinations"][0]
        hud_checks = [
            (
                score_visible(frame, score_dst, expected_score, glyphs, manifest),
                score_visible(frame, top_dst, expected_score, glyphs, manifest),
                score_visible(frame, top_right_dst, expected_score, glyphs, manifest),
            )
            for frame in owners
        ]
        if not all(all(checks) for checks in hud_checks):
            expected_zero = hashlib.sha256(expected_tile(
                manifest, glyphs[0]
            )).hexdigest()[:12]
            actual = [
                hashlib.sha256(runtime.frame_tile(frame, score_dst)).hexdigest()[:12]
                for frame in owners
            ]
            digit_checks = [
                [
                    runtime.frame_tile(frame, score_dst + index * 4) ==
                    expected_tile(manifest, glyphs[digit])
                    for index, digit in enumerate(bcd_digits(expected_score))
                ]
                for frame in owners
            ]
            actual_five = runtime.frame_tile(owners[0], score_dst + 8)
            actual_five_id = next(
                (digit for digit in range(10)
                 if actual_five == expected_tile(manifest, glyphs[digit])),
                None,
            )
            fail(
                "entry-HUD",
                f"pending and TOP score checks={hud_checks} digits={digit_checks} "
                f"five-as={actual_five_id} first={actual} expected0={expected_zero}",
            )
        if args.initial_png:
            write_frame_png(args.initial_png, owners[0])
        monitor.clear(client, ids)

        ids = monitor.setup(client, [demo["name_joy_ready"]])
        hit = client.run_to_breakpoint(args.timeout)
        if hit.get("pc") != demo["name_joy_ready"]:
            fail("seven-character-bound", f"unexpected breakpoint {hit}")
        full_name = bytes((node_tiles[0],)) * 7
        write_state(client, PRES_NAME, full_name)
        runtime.write_byte(client, PRES_NAME_LEN, 7)
        runtime.write_byte(client, JOY_DIR, 0)
        hit = client.run_to_breakpoint(args.timeout)
        if (hit.get("pc") != demo["name_joy_ready"] or
                runtime.read_byte(client, PRES_NAME_LEN) != 7 or
                read_state(client, PRES_NAME, 7) != full_name):
            fail("seven-character-bound", "eighth character changed the pending name")
        write_state(client, PRES_NAME, bytes((black,)) * 7)
        runtime.write_byte(client, PRES_NAME_LEN, 0)
        runtime.write_byte(client, PRES_NAME_ROW, 9)
        runtime.write_byte(client, PRES_NAME_COL, 2)
        runtime.write_byte(client, PRES_NAME_REPEAT, 0)
        runtime.write_byte(client, PRES_NAME_LAST_DIR, 0xFF)
        directions = [0, 3, 0, 3, 0, 1, 0, 1, 0, 1, 0, 1, 3, 0, 3, 0, 3, 0, 3, 2, 1, 0, 1, 0, 1, 0, 1]
        edge_masks = name_contract["edge_masks"]
        expected_lengths = []
        expected_positions = []
        simulated_name = []
        simulated_position = [9, 2]
        simulated_end = False
        for direction in directions:
            expected_lengths.append(len(simulated_name))
            expected_positions.append(tuple(simulated_position))
            row, column = simulated_position
            if row == 9:
                if direction != 0:
                    continue
            elif not edge_masks[row * 5 + column] & (1 << direction):
                continue
            if direction == 0:
                simulated_position[0] -= 1
            elif direction == 1:
                simulated_position[1] += 1
            elif direction == 2:
                simulated_position[0] += 1
            else:
                simulated_position[1] -= 1
            tile = node_tiles[simulated_position[0] * 5 + simulated_position[1]]
            if tile == 0xFD:
                simulated_end = True
                break
            if tile == 0xFE:
                if simulated_name:
                    simulated_name.pop()
            elif tile < 0xFD and len(simulated_name) < 7:
                simulated_name.append(tile)
        if not simulated_end:
            fail("test-route", "generated legal route did not reach END")
        for direction, expected_length, expected_position in zip(
                directions, expected_lengths, expected_positions):
            for _ in range(12):
                hit = client.run_to_breakpoint(args.timeout)
                if hit.get("pc") == demo["name_joy_ready"]:
                    break
                if (hit.get("pc") != module["load_done_publish"] or
                        runtime.read_byte(client, PRES_SCREEN) != MAP_ENTER_HIGH_SCORE):
                    break
            if hit.get("pc") != demo["name_joy_ready"]:
                fail(
                    "name-input",
                    f"unexpected breakpoint {hit} screen={runtime.read_byte(client, PRES_SCREEN)} "
                    f"mode={runtime.read_byte(client, PRES_MODE)} "
                    f"hold={runtime.read_byte(client, 0x00D4):02x} "
                    f"owner={runtime.read_byte(client, 0x00D9)}",
                )
            if runtime.read_byte(client, PRES_NAME_LEN) != expected_length:
                fail(
                    "cell-entry",
                    f"name length={runtime.read_byte(client, PRES_NAME_LEN)} "
                    f"expected={expected_length} before direction={direction} "
                    f"row={runtime.read_byte(client, PRES_NAME_ROW)} "
                    f"col={runtime.read_byte(client, PRES_NAME_COL)} "
                    f"pending={read_state(client, PRES_NAME, 7).hex()} "
                    f"node={node_tiles[runtime.read_byte(client, PRES_NAME_ROW) * 5 + runtime.read_byte(client, PRES_NAME_COL)]:02x}",
                )
            actual_position = (
                runtime.read_byte(client, PRES_NAME_ROW),
                runtime.read_byte(client, PRES_NAME_COL),
            )
            if actual_position != expected_position:
                fail("cursor-path", f"position={actual_position} expected={expected_position}")
            runtime.write_byte(client, JOY_DIR, direction)

        monitor.clear(client, ids)
        ids = monitor.setup(client, [module["presentation_flow_tick"]])
        try:
            hit = client.run_to_breakpoint(args.timeout)
        except Exception as exc:
            fail("END-transition-timeout", f"presentation boundary error={exc}")
        if hit.get("pc") != module["presentation_flow_tick"]:
            fail(
                "END-transition",
                f"unexpected breakpoint {hit} "
                f"row={runtime.read_byte(client, PRES_NAME_ROW)} "
                f"col={runtime.read_byte(client, PRES_NAME_COL)}",
            )
        if runtime.read_byte(client, PRES_SCREEN) != MAP_HIGH_SCORE:
            fail("END-transition", "END did not request high-score map")
        monitor.clear(client, ids)
        ids = monitor.setup(client, [module["load_done_publish"]])
        hit = client.run_to_breakpoint(args.timeout)
        if hit.get("pc") != module["load_done_publish"]:
            fail("END-publication", f"unexpected breakpoint {hit}")
        pending_name = bytes(simulated_name)
        expected_table = (
            expected_score + pending_name +
            bytes((black,)) * (7 - len(pending_name)) + fixture[:80]
        )
        actual_table = read_state(client, PRES_TABLE, 90)
        if actual_table != expected_table:
            fail(
                "commit-once",
                f"ranked table differs after END expected={expected_table[:10].hex()} "
                f"actual={actual_table[:10].hex()} pending={pending_name.hex()} "
                f"sim={simulated_position}",
            )
        owners = [runtime.read_owner(client, owner) for owner in (0, 1)]
        score_destinations = manifest["high_score_table"]["score_destinations"]
        name_destinations = manifest["high_score_table"]["name_destinations"]
        records = [expected_table[index:index + 10] for index in range(0, 90, 10)]
        row_counts = [
            sum(
                score_visible(frame, score_destination, record[:3], glyphs, manifest) and
                name_visible(frame, name_destination, record[3:], black, manifest)
                for score_destination, name_destination, record in zip(
                    score_destinations, name_destinations, records
                )
            )
            for frame in owners
        ]
        if row_counts != [9, 9]:
            fail("all-nine-rendering", f"visible score/name rows={row_counts}")
        if args.updated_png:
            write_frame_png(args.updated_png, owners[0])
        monitor.clear(client, ids)

        ids = monitor.setup(client, [module["presentation_flow_tick"]])
        for key in (5, 6):
            client.call("inject_key", {"key": key, "action": "press"})
            for _ in range(4):
                hit = client.run_to_breakpoint(args.timeout)
                if hit.get("pc") != module["presentation_flow_tick"]:
                    fail("hold", f"unexpected breakpoint {hit}")
                if runtime.read_byte(client, PRES_SCREEN) != MAP_HIGH_SCORE:
                    fail("credit-start-isolation", f"key {key} preempted high scores")
            client.call("inject_key", {"key": key, "action": "release"})
        if read_state(client, PRES_TABLE, 90) != expected_table:
            fail("commit-once", "held screen changed the ranked table")

        monitor.clear(client, ids)
        ids = []
        client.call("reset", {"kind": "soft"})
        ids = monitor.setup(client, [module["load_done_publish"]])
        hit = client.run_to_breakpoint(args.timeout)
        if (hit.get("pc") != module["load_done_publish"] or
                runtime.read_byte(client, PRES_SCREEN) != MAP_ENTER_HIGH_SCORE or
                read_state(client, PRES_TABLE, 90) != fixture or
                read_state(client, PRES_NAME, 7) != bytes((black,)) * 7):
            fail("reset-reseed", "soft reset did not restore the direct-entry fixture")
        monitor.clear(client, ids)
        ids = monitor.setup(client, [demo["name_joy_ready"]])
        hit = client.run_to_breakpoint(args.timeout)
        if hit.get("pc") != demo["name_joy_ready"]:
            fail("empty-name-END", f"unexpected breakpoint {hit}")
        if (runtime.read_bytes(client, PRES_SCORE, 3) != expected_score or
                runtime.read_byte(client, PRES_INSERT) != 0 or
                read_state(client, PRES_TABLE, 90) != fixture or
                client.call("read_registers").get("dp") != 0):
            fail(
                "reset-name-state",
                f"score={runtime.read_bytes(client, PRES_SCORE, 3).hex()} "
                f"insert={runtime.read_byte(client, PRES_INSERT)} "
                f"dp={client.call('read_registers').get('dp')} "
                f"first={read_state(client, PRES_TABLE, 10).hex()}",
            )
        live_module = runtime.read_bytes(client, 0x1900, MODULE_RUNTIME.stat().st_size)
        if live_module != MODULE_RUNTIME.read_bytes():
            fail(
                "reset-module-identity",
                f"live={hashlib.sha256(live_module).hexdigest()} "
                f"built={hashlib.sha256(MODULE_RUNTIME.read_bytes()).hexdigest()}",
            )
        live_demo = runtime.read_bytes(client, 0x0300, DEMO_RUNTIME.stat().st_size)
        if live_demo != DEMO_RUNTIME.read_bytes():
            fail("reset-auxiliary-identity", "reset changed the $0300 test runtime")
        ready_before_empty = runtime.read_byte(client, 0x00E7)
        runtime.write_byte(client, PRES_NAME_ROW, 8)
        runtime.write_byte(client, PRES_NAME_COL, 3)
        runtime.write_byte(client, PRES_NAME_LEN, 0)
        runtime.write_byte(client, PRES_NAME_LAST_DIR, 0xFF)
        runtime.write_byte(client, JOY_DIR, 1)
        monitor.clear(client, ids)
        ids = monitor.setup(client, [module["presentation_flow_tick"]])
        hit = client.run_to_breakpoint(args.timeout)
        expected_empty = expected_score + bytes((black,)) * 7 + fixture[:80]
        if (hit.get("pc") != module["presentation_flow_tick"] or
                runtime.read_byte(client, PRES_SCREEN) != MAP_HIGH_SCORE or
                read_state(client, PRES_TABLE, 90) != expected_empty):
            actual_empty = read_state(client, PRES_TABLE, 90)
            fail(
                "empty-name-END",
                f"hit={hit} screen={runtime.read_byte(client, PRES_SCREEN)} "
                f"dp={client.call('read_registers').get('dp')} "
                f"ready={ready_before_empty}->{runtime.read_byte(client, 0x00E7)} "
                f"dp2score={runtime.read_bytes(client, 0x02BF, 3).hex()} "
                f"first={actual_empty[:10].hex()} expected={expected_empty[:10].hex()}",
            )

        monitor.clear(client, ids)
        ids = []
        client.call("reset", {"kind": "soft"})
        ids = monitor.setup(client, [module["load_done_publish"]])
        hit = client.run_to_breakpoint(args.timeout)
        if (hit.get("pc") != module["load_done_publish"] or
                runtime.read_byte(client, PRES_SCREEN) != MAP_ENTER_HIGH_SCORE or
                read_state(client, PRES_TABLE, 90) != fixture):
            fail("second-reset-reseed", "reset after empty END retained ranking state")
        monitor.clear(client, ids)
        ids = monitor.setup(client, [demo["name_joy_ready"]])
        hit = client.run_to_breakpoint(args.timeout)
        if hit.get("pc") != demo["name_joy_ready"]:
            fail("timer-entry", f"unexpected breakpoint {hit}")
        runtime.write_byte(client, JOY_DIR, 0xFF)
        write_state(client, PRES_NAME, bytes((node_tiles[35],)) + bytes((black,)) * 6)
        runtime.write_byte(client, PRES_NAME_LEN, 1)
        runtime.write_byte(client, PRES_TIMER, 0)
        runtime.write_byte(client, PRES_TIMER + 1, 59)
        runtime.write_byte(client, PRES_NAME_TIMER_PHASE, 59)
        runtime.write_byte(client, PRES_NAME_TIMER_BOX, 0)
        monitor.clear(client, ids)
        ids = monitor.setup(client, [demo["name_joy_ready"]])
        hit = client.run_to_breakpoint(args.timeout)
        if (hit.get("pc") != demo["name_joy_ready"] or
                runtime.read_byte(client, PRES_SCREEN) != MAP_ENTER_HIGH_SCORE or
                runtime.read_bytes(client, PRES_TIMER, 2) != bytes((0, 60)) or
                runtime.read_byte(client, PRES_NAME_TIMER_BOX) != 1):
            fail(
                "timer-first-box",
                f"timer state after first box={hit} screen={runtime.read_byte(client, PRES_SCREEN)} "
                f"timer={runtime.read_bytes(client, PRES_TIMER, 2).hex()} "
                f"phase={runtime.read_byte(client, PRES_NAME_TIMER_PHASE)} "
                f"box={runtime.read_byte(client, PRES_NAME_TIMER_BOX)}",
            )
        monitor.clear(client, ids)
        ids = monitor.setup(client, [main_symbols["irq_handler"]])
        for _ in range(2):
            hit = client.run_to_breakpoint(args.timeout)
            if hit.get("pc") != main_symbols["irq_handler"]:
                fail("timer-publication", f"unexpected IRQ breakpoint {hit}")
        timer_cell = name_contract["timer_cells"][0]
        timer_destination = 0x2000 + timer_cell[1] * 1280 + timer_cell[0] * 4
        front = runtime.read_byte(client, 0x008F)
        if not tile_matches(
                runtime.read_owner(client, front), timer_destination,
                expected_tile(manifest, name_contract["timer_green_tile_ids"][0])):
            actual_timer = runtime.frame_tile(runtime.read_owner(client, front), timer_destination)
            expected_timer = expected_tile(manifest, name_contract["timer_green_tile_ids"][0])
            owner_tiles = {
                owner: runtime.frame_tile(runtime.read_owner(client, owner), timer_destination).hex()
                for owner in (0, 1)
            }
            fail(
                "timer-render",
                f"first border box did not turn green on FRONT owner={front} "
                f"cell={timer_cell} actual={actual_timer.hex()} expected={expected_timer.hex()} "
                f"owners={owner_tiles}",
            )
        runtime.write_byte(client, PRES_TIMER, 0)
        runtime.write_byte(client, PRES_TIMER + 1, 59)
        runtime.write_byte(client, PRES_NAME_TIMER_PHASE, 59)
        runtime.write_byte(client, PRES_NAME_TIMER_BOX, 1)
        monitor.clear(client, ids)
        ids = monitor.setup(client, [demo["name_joy_ready"]])
        hit = client.run_to_breakpoint(args.timeout)
        if (hit.get("pc") != demo["name_joy_ready"] or
                runtime.read_bytes(client, PRES_TIMER, 2) != bytes((0, 60)) or
                runtime.read_byte(client, PRES_NAME_TIMER_BOX) != 2):
            fail(
                "timer-second-box",
                f"timer state after second box={hit} screen={runtime.read_byte(client, PRES_SCREEN)} "
                f"timer={runtime.read_bytes(client, PRES_TIMER, 2).hex()} "
                f"phase={runtime.read_byte(client, PRES_NAME_TIMER_PHASE)} "
                f"box={runtime.read_byte(client, PRES_NAME_TIMER_BOX)}",
            )
        monitor.clear(client, ids)
        ids = monitor.setup(client, [main_symbols["irq_handler"]])
        for _ in range(2):
            hit = client.run_to_breakpoint(args.timeout)
            if hit.get("pc") != main_symbols["irq_handler"]:
                fail("timer-publication", f"unexpected IRQ breakpoint={hit}")
        front = runtime.read_byte(client, 0x008F)
        for index, cell in enumerate(name_contract["timer_cells"][:2]):
            destination = 0x2000 + cell[1] * 1280 + cell[0] * 4
            if not tile_matches(
                    runtime.read_owner(client, front), destination,
                    expected_tile(manifest, name_contract["timer_green_tile_ids"][index])):
                fail(
                    "timer-sequence",
                    f"box {index} is not green on cumulative FRONT owner={front} cell={cell}",
                )
        runtime.write_byte(client, PRES_TIMER, 0x15)
        runtime.write_byte(client, PRES_TIMER + 1, 0x8F)
        runtime.write_byte(client, PRES_NAME_TIMER_PHASE, 59)
        runtime.write_byte(client, PRES_NAME_TIMER_BOX, 91)
        monitor.clear(client, ids)
        ids = monitor.setup(client, [module["name_timeout"]])
        hit = client.run_to_breakpoint(args.timeout)
        if hit.get("pc") != module["name_timeout"]:
            fail("timer-timeout", f"timeout marker was not reached: {hit}")
        monitor.clear(client, ids)
        ids = monitor.setup(client, [module["presentation_flow_tick"]])
        hit = client.run_to_breakpoint(args.timeout)
        timeout_table = expected_score + bytes((node_tiles[35],)) + bytes((black,)) * 6 + fixture[:80]
        if (hit.get("pc") != module["presentation_flow_tick"] or
                runtime.read_byte(client, PRES_SCREEN) != MAP_HIGH_SCORE or
                read_state(client, PRES_TABLE, 90) != timeout_table):
            fail(
                "timer-timeout",
                f"timeout did not accept partial name hit={hit} "
                f"screen={runtime.read_byte(client, PRES_SCREEN)} "
                f"first={read_state(client, PRES_TABLE, 10).hex()}",
            )
        evidence["events"] = [
            "direct-enter-high-score", "dummy-nine-rows", "character-entry",
            "CL-delete", "seven-character-bound", "END-commit",
            "empty-name-END", "all-nine-render", "hold-through-credit-start",
            "reset-reseed", "cursor-render", "wall-palette",
            "wall-edge-block", "timer-first-box", "timer-timeout",
        ]
    finally:
        try:
            monitor.clear(client, ids)
        except (OSError, ValueError):
            pass
        try:
            client.close()
        except OSError:
            pass
        monitor.stop(process)

    if args.initial_png:
        evidence["initial_png_sha256"] = hashlib.sha256(
            args.initial_png.read_bytes()
        ).hexdigest()
    if args.updated_png:
        evidence["updated_png_sha256"] = hashlib.sha256(
            args.updated_png.read_bytes()
        ).hexdigest()
    args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="ascii")
    print("FEAT-003 highscore-test: entry, edit, END, nine rows, and reset-only hold passed")
    print(f"evidence={args.output}")


if __name__ == "__main__":
    main()
