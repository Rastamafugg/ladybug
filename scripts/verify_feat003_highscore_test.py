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
from build_screen import LIGHT_BLUE, PALETTE, PINK, gime_rgb  # noqa: E402


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
PRES_NAME_STEPS = 0x00DE
PRES_NAME_LEN = 0x00CB
PRES_INSERT = 0x00C9
PRES_SCORE = 0x00BF
PRES_TABLE = 0xAF84
PRES_NAME = 0xAFDE
PRES_CURSOR_SAVE_A = 0xA590
JOY_DIR = 0x0005
PLAYER_WANT = 0x000F
PLAYER_FB = 0x000B
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


def expected_map_frame(manifest: dict[str, object], map_index: int) -> bytes:
    """Decode one generated map into the native presentation framebuffer."""
    cold = COLD.read_bytes()
    start = int(manifest["map_stream_offsets"][map_index])
    length = int(manifest["map_stream_bytes"][map_index])
    encoded = cold[start:start + length]
    cells = bytearray()
    for index in range(0, len(encoded), 2):
        cells.extend(bytes((encoded[index + 1],)) * encoded[index])
    if len(cells) != 40 * 24:
        raise ValueError(f"generated map {map_index} has {len(cells)} cells")
    frame = bytearray(0x7800)
    for cell_index, tile_id in enumerate(cells):
        row, column = divmod(cell_index, 40)
        destination = row * 1280 + column * 4
        tile = expected_tile(manifest, tile_id)
        for tile_row in range(8):
            start = destination + tile_row * 160
            frame[start:start + 4] = tile[tile_row * 4:tile_row * 4 + 4]
    return bytes(frame)


def frame_diff(actual: bytes, expected: bytes, start: int) -> tuple[int, str | None]:
    end = min(len(actual), start + 16 * 1280)
    differences = [index for index in range(start, end)
                   if actual[index] != expected[index]]
    return len(differences), (f"{differences[0]:04x}" if differences else None)


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
    tiles = [tile or black for tile in name]
    return all(
        runtime.frame_tile(frame, destination + index * 4) ==
        expected_tile(manifest, tile)
        for index, tile in enumerate(tiles)
    )


def entry_name_visible(frame: bytes, destinations: list[int], name: bytes,
                       black: int, manifest: dict[str, object]) -> bool:
    tiles = list(name) + [black] * (7 - len(name))
    return all(
        runtime.frame_tile(frame, destination) ==
        expected_tile(manifest, tile)
        for destination, tile in zip(destinations, tiles)
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


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


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
    parser.add_argument(
        "--boundary-only", action="store_true",
        help="skip the exhaustive input matrix and capture the END transition",
    )
    args = parser.parse_args()

    manifest = json.loads(MANIFEST.read_text(encoding="ascii"))
    if manifest.get("highscore_test_profile") is not True:
        fail("artifact-profile", "manifest is not highscore-test")
    module = symbols(MODULE_MAP)
    demo = symbols(DEMO_MAP)
    main_symbols = symbols(ROOT / "build/ladybug.map")
    required_module = (
        "presentation_flow_tick", "load_done_dynamic_high", "load_done_publish",
    )
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
            len(name_contract["edge_masks"]) != 45 or
            len(name_contract["full_edge_masks"]) != 576 or
            len(name_contract["action_table"]) != 126):
        fail(
            "generated-contract",
            f"timer cells={len(timer_cells)} unique={len(set(timer_cells))} "
            f"base={len(name_contract['timer_base_tile_ids'])} "
            f"green={len(name_contract['timer_green_tile_ids'])} "
            f"edges={len(name_contract['edge_masks'])} "
            f"full-edges={len(name_contract['full_edge_masks'])} "
            f"actions={len(name_contract['action_table'])}",
        )
    default_name = bytes(name_contract["default_name_tile_ids"])
    top_name_tiles = bytes(name_contract["top_name_tile_ids"])
    demo_source = (ROOT / "src/demo_runtime.s").read_text(encoding="ascii")
    high_score_start = demo_source.index("\nrender_high_score\n")
    high_score_source = demo_source[high_score_start:].split(
        "\ndraw_high_score_screen\n", 1
    )[0]
    if "draw_entry_scores" in high_score_source:
        fail("high-score-overlay", "render_high_score still draws the entry-screen HUD")
    name_start = demo_source.index("\nname_cell_arrival\n")
    name_source = demo_source[name_start:].split("\n        ifne    0\n", 1)[0]
    if "suba    #8" not in name_source:
        fail("action-coordinate-origin", "runtime action lookup does not normalize screen X")
    if (len(default_name) != 7 or top_name_tiles != default_name or
            list(name_contract["authored_name_codes"]) != [21, 10, 13, 34, 11, 30, 16]):
        fail("dummy-fixture", f"generated LADYBUG fixture has {len(default_name)} tiles")
    fixture = b"".join(
        bytes((rank, 0, 0)) + default_name
        for rank in range(9, 0, -1)
    )
    expected_score = bytes((0x09, 0x50, 0x00))

    monitor = runtime.load_monitor()
    process, client = runtime.launch_fast(monitor, args.xroar, args.rom)
    boundary_evidence: dict[str, object] = {}
    evidence: dict[str, object] = {
        "schema": "ladybug-feat003-highscore-test-v1",
        "rom_sha256": hashlib.sha256(args.rom.read_bytes()).hexdigest(),
        "events": [],
        "high_score_transition_boundaries": boundary_evidence,
    }
    expected_high_score = expected_map_frame(manifest, MAP_HIGH_SCORE)
    if not tile_uses_only(expected_high_score,
                          0x2000 + 12 * 4,
                          {0, LIGHT_BLUE}):
        fail("high-score-colour", "table/title tile is not light blue")
    if not tile_uses_only(expected_high_score,
                          0x2000 + 15 * 1280 + 9 * 4,
                          {0, PINK}):
        fail("high-score-colour", "Lady Bug logo tile is not pink")
    write_frame_png(ROOT / "build/feat003-boundary-expected.png", expected_high_score)
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
        saved_par5 = runtime.read_byte(client, PAR5)
        try:
            runtime.write_byte(client, PAR5, 0x3A)
            live_cold = runtime.read_bytes(
                client, 0xA000, int(manifest["cold_payload_limit"])
            )
        finally:
            runtime.write_byte(client, PAR5, saved_par5)
        expected_cold = COLD.read_bytes()
        cold_first_diff = next(
            (index for index, pair in enumerate(zip(live_cold, expected_cold))
             if pair[0] != pair[1]),
            None,
        )
        if cold_first_diff is not None:
            fail(
                "cold-payload-identity",
                f"first divergence at +${cold_first_diff:04x} "
                f"live={live_cold[cold_first_diff]:02x} "
                f"expected={expected_cold[cold_first_diff]:02x}",
            )
        if read_state(client, PRES_TABLE, 90) != fixture:
            fail(
                "dummy-table",
                f"nine descending dummy records differ actual={read_state(client, PRES_TABLE, 90).hex()} "
                f"expected={fixture.hex()}",
            )
        if runtime.read_bytes(client, PRES_SCORE, 3) != expected_score:
            fail("pending-score", "pending player score is not 095000")
        if runtime.read_byte(client, PRES_INSERT) != 0:
            fail("pending-rank", "player is not pending at rank 1")
        if read_state(client, PRES_NAME, 7) != bytes((black,)) * 7:
            fail("pending-name", "name is not blank")
        if (runtime.read_byte(client, PRES_NAME_ROW),
                runtime.read_byte(client, PRES_NAME_COL)) != (22, 19):
            fail("sprite-start", "runtime cursor differs from authored marker")
        owners = [runtime.read_owner(client, owner) for owner in (0, 1)]
        cursor_destination = name_contract["cursor_destination"]
        front_owner = runtime.read_byte(client, runtime.FB_FRONT)
        if not any(runtime.frame_tile(owners[front_owner], cursor_destination,
                                       width=8, rows=16)):
            fail("cursor-render", "starting Lady Bug is absent on FRONT")
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
        name_destinations = name_contract["name_destinations"]
        top_name_destinations = name_contract["top_name_destinations"]
        expected_name_destinations = [0x2000 + 19 * 1280 + (1 + index) * 4 for index in range(7)]
        expected_top_name_destinations = [0x2000 + 5 * 1280 + (33 + index) * 4 for index in range(7)]
        if name_destinations != expected_name_destinations:
            fail(
                "entry-name-destination",
                f"generated destinations={name_destinations} "
                f"expected={expected_name_destinations}",
            )
        if top_name_destinations != expected_top_name_destinations:
            fail(
                "entry-top-name-destination",
                f"generated destinations={top_name_destinations} "
                f"expected={expected_top_name_destinations}",
            )
        front_frame = owners[front_owner]
        hud_checks = (
            score_visible(front_frame, score_dst, expected_score, glyphs, manifest),
            score_visible(front_frame, top_dst, expected_score, glyphs, manifest),
            score_visible(front_frame, top_right_dst, expected_score, glyphs, manifest),
            entry_name_visible(front_frame, name_destinations, b"", black, manifest),
            entry_name_visible(front_frame, top_name_destinations, b"", black, manifest),
        )
        if not all(hud_checks):
            if args.initial_png:
                write_frame_png(args.initial_png, front_frame)
            expected_zero = hashlib.sha256(expected_tile(
                manifest, glyphs[0]
            )).hexdigest()[:12]
            name_tiles = [
                runtime.frame_tile(front_frame, destination).hex()
                for destination in name_destinations
            ]
            actual = [
                hashlib.sha256(runtime.frame_tile(frame, score_dst)).hexdigest()[:12]
                for frame in (front_frame,)
            ]
            digit_checks = [
                [
                    runtime.frame_tile(frame, score_dst + index * 4) ==
                    expected_tile(manifest, glyphs[digit])
                    for index, digit in enumerate(bcd_digits(expected_score))
                ]
                for frame in owners
            ]
            actual_five = runtime.frame_tile(front_frame, score_dst + 8)
            actual_five_id = next(
                (digit for digit in range(10)
                 if actual_five == expected_tile(manifest, glyphs[digit])),
                None,
            )
            fail(
                "entry-HUD",
                f"pending and TOP score checks={hud_checks} digits={digit_checks} "
                f"five-as={actual_five_id} first={actual} expected0={expected_zero} "
                f"name-dst={[hex(value) for value in name_destinations]} "
                f"name-tiles={name_tiles}",
            )
        if args.initial_png:
            write_frame_png(args.initial_png, front_frame)
        monitor.clear(client, ids)

        ids = monitor.setup(client, [demo["name_joy_ready"]])
        hit = client.run_to_breakpoint(args.timeout)
        if hit.get("pc") != demo["name_joy_ready"]:
            fail("seven-character-bound", f"unexpected breakpoint {hit}")
        full_name = bytes((default_name[0],)) * 7
        write_state(client, PRES_NAME, full_name)
        runtime.write_byte(client, PRES_NAME_LEN, 7)
        runtime.write_byte(client, JOY_DIR, 0xFF)
        hit = client.run_to_breakpoint(args.timeout)
        if (hit.get("pc") != demo["name_joy_ready"] or
                runtime.read_byte(client, PRES_NAME_LEN) != 7 or
                read_state(client, PRES_NAME, 7) != full_name):
            fail("seven-character-bound", "eighth character changed the pending name")
        monitor.clear(client, ids)
        ids = []
        client.call("reset", {"kind": "soft"})
        ids = monitor.setup(client, [module["load_done_publish"]])
        hit = client.run_to_breakpoint(args.timeout)
        if (hit.get("pc") != module["load_done_publish"] or
                runtime.read_byte(client, PRES_SCREEN) != MAP_ENTER_HIGH_SCORE):
            fail("route-reset", f"unexpected clean route entry {hit}")
        monitor.clear(client, ids)
        ids = monitor.setup(client, [demo["name_joy_ready"]])
        hit = client.run_to_breakpoint(args.timeout)
        if hit.get("pc") != demo["name_joy_ready"]:
            fail("route-reset", f"unexpected clean input entry {hit}")
        write_state(client, PRES_NAME, bytes((black,)) * 7)
        runtime.write_byte(client, PRES_NAME_LEN, 0)
        runtime.write_byte(client, PRES_NAME_ROW, 22)
        runtime.write_byte(client, PRES_NAME_COL, 19)
        runtime.write_byte(client, 0x0009, 19)
        runtime.write_byte(client, 0x000A, 22)
        runtime.write_byte(client, PRES_NAME_REPEAT, 0)
        runtime.write_byte(client, PRES_NAME_LAST_DIR, 0xFF)
        full_edges = name_contract["full_edge_masks"]
        if any(full_edges[x] & 0x01 for x in range(24)):
            fail("generated-boundary", "top perimeter admits north entry")
        if any(full_edges[23 * 24 + x] & 0x04 for x in range(24)):
            fail("generated-boundary", "bottom perimeter admits south entry")
        if any(full_edges[y * 24 + 1] & 0x08 for y in range(24)):
            fail("generated-boundary", "left perimeter admits west entry")
        if any(full_edges[y * 24 + 22] & 0x02 for y in range(24)):
            fail("generated-boundary", "right perimeter admits east entry")
        if any(full_edges[y * 24 + x] for y in range(24)
               for x in range(24) if x in (0, 23) or y in (0, 23)):
            fail("generated-boundary", "perimeter cell remains passable")
        if (any(full_edges[24 + x] for x in range(24)) or
                any(full_edges[y * 24 + 22] for y in range(24))):
            fail(
                "generated-footprint-boundary",
                "top or right sprite-anchor exclusion remains passable",
            )
        action_map = {
            (int(x), int(y)): int(tile)
            for x, y, tile in name_contract["action_records"]
        }
        start_position = (19, 22)
        char_cells = [cell for cell, tile in action_map.items()
                      if tile not in (0xFD, 0xFE)]
        cl_cells = [cell for cell, tile in action_map.items() if tile == 0xFE]
        end_cell = next(cell for cell, tile in action_map.items() if tile == 0xFD)
        cursor_destination = name_contract["cursor_destination"]

        # The authored records use screen-space X while the collision table
        # and packed action table use maze-local X.  Every selectable cell and
        # control must remain reachable from the authored cursor start through
        # the generated full-maze edges.
        reachable = {start_position}
        pending = [start_position]
        while pending:
            sx, sy = pending.pop()
            local_x = sx - 8
            mask = full_edges[sy * 24 + local_x]
            for bit, dx, dy in ((1, 0, -1), (2, 1, 0),
                                (4, 0, 1), (8, -1, 0)):
                if not mask & bit:
                    continue
                next_position = (sx + dx, sy + dy)
                if (8 <= next_position[0] < 32 and
                        0 <= next_position[1] < 24 and
                        next_position not in reachable):
                    reachable.add(next_position)
                    pending.append(next_position)
        unreachable = sorted(set(action_map) - reachable)
        if unreachable:
            fail("generated-reachability", f"unreachable action cells={unreachable}")

        def set_probe_position(position: tuple[int, int]) -> None:
            x, y = position
            pointer = (cursor_destination +
                       (x - start_position[0]) * 4 +
                       (y - start_position[1]) * 1280) & 0xFFFF
            runtime.write_byte(client, PRES_NAME_COL, x)
            runtime.write_byte(client, PRES_NAME_ROW, y)
            runtime.write_byte(client, 0x0009, x)
            runtime.write_byte(client, 0x000A, y)
            runtime.write_word(client, PLAYER_FB, pointer)
            runtime.write_word(client, 0x00DA, pointer)
            runtime.write_word(client, 0x00DC, pointer)
            runtime.write_byte(client, PRES_NAME_STEPS, 0)
            runtime.write_byte(client, JOY_DIR, 0xFF)
            runtime.write_byte(client, PLAYER_WANT, 0xFF)
            runtime.write_byte(client, 0x0006, 0xFF)

        set_probe_position(start_position)
        hit = client.run_to_breakpoint(args.timeout)
        if hit.get("pc") != demo["name_joy_ready"]:
            fail("release-stop", f"initial movement probe stopped at {hit}")
        for _ in range(2):
            runtime.write_byte(client, JOY_DIR, 1)
            runtime.write_byte(client, PLAYER_WANT, 1)
            hit = client.run_to_breakpoint(args.timeout)
            if hit.get("pc") != demo["name_joy_ready"]:
                fail("release-stop", f"movement tick stopped at {hit}")
            if runtime.read_byte(client, PRES_NAME_STEPS):
                break
        partial_pointer = runtime.read_word(client, PLAYER_FB)
        partial_steps = runtime.read_byte(client, PRES_NAME_STEPS)
        if partial_pointer == name_contract["cursor_destination"] or partial_steps != 3:
            fail(
                "release-stop",
                f"movement did not enter partial pixel step pointer={partial_pointer:04x} "
                f"steps={partial_steps}",
            )
        for _ in range(2):
            runtime.write_byte(client, JOY_DIR, 0xFF)
            hit = client.run_to_breakpoint(args.timeout)
            if hit.get("pc") != demo["name_joy_ready"]:
                fail("release-stop", f"neutral input probe stopped at {hit}")
        if (runtime.read_word(client, PLAYER_FB) != partial_pointer or
                runtime.read_byte(client, PRES_NAME_STEPS) != partial_steps):
            fail(
                "release-stop",
                "neutral joystick advanced or discarded the partial pixel step",
            )
        monitor.clear(client, ids)
        ids = []
        client.call("reset", {"kind": "soft"})
        ids = monitor.setup(client, [demo["name_joy_ready"]])
        hit = client.run_to_breakpoint(args.timeout)
        if hit.get("pc") != demo["name_joy_ready"]:
            fail("release-stop", f"clean-state reset stopped at {hit}")

        boundary_cases = (
            ((9, 2), 3), ((9, 2), 0),
            ((29, 22), 1), ((29, 22), 2),
        )
        for position, direction in boundary_cases:
            set_probe_position(position)
            expected_pointer = runtime.read_word(client, PLAYER_FB)
            for _ in range(2):
                hit = client.run_to_breakpoint(args.timeout)
                if hit.get("pc") != demo["name_joy_ready"]:
                    fail("runtime-boundary", f"unexpected breakpoint: {hit}")
                runtime.write_byte(client, JOY_DIR, direction)
                runtime.write_byte(client, PLAYER_WANT, direction)
            if (runtime.read_word(client, PLAYER_FB) != expected_pointer or
                    runtime.read_byte(client, PRES_NAME_STEPS) != 0 or
                    (runtime.read_byte(client, 0x0009),
                     runtime.read_byte(client, 0x000A)) != position):
                fail(
                    "runtime-boundary",
                    f"blocked entry moved from {position} direction={direction} "
                    f"to={(runtime.read_byte(client, 0x0009), runtime.read_byte(client, 0x000A))} "
                    f"pointer={runtime.read_word(client, PLAYER_FB):04x} steps={runtime.read_byte(client, PRES_NAME_STEPS)}",
                )
        wall_cells = [] if args.boundary_only else [
            (x + 8, y) for y in range(1, 23) for x in range(1, 23)
            if full_edges[y * 24 + x] == 0
        ]
        directions = ((0, -1, 0), (1, 0, 1), (0, 1, 2), (-1, 0, 3))
        for wall_x, wall_y in wall_cells:
            for dx, dy, direction in directions:
                position = (wall_x - dx, wall_y - dy)
                if not (8 < position[0] < 31 and 0 < position[1] < 23):
                    continue
                set_probe_position(position)
                expected_pointer = runtime.read_word(client, PLAYER_FB)
                for _ in range(2):
                    hit = client.run_to_breakpoint(args.timeout)
                    if hit.get("pc") != demo["name_joy_ready"]:
                        fail("inner-wall-block", f"unexpected breakpoint: {hit}")
                    runtime.write_byte(client, JOY_DIR, direction)
                    runtime.write_byte(client, PLAYER_WANT, direction)
                if (runtime.read_word(client, PLAYER_FB) != expected_pointer or
                        runtime.read_byte(client, PRES_NAME_STEPS) != 0 or
                        (runtime.read_byte(client, 0x0009),
                         runtime.read_byte(client, 0x000A)) != position):
                    fail(
                        "inner-wall-block",
                        f"entered wall {(wall_x, wall_y)} from {position} "
                        f"direction={direction} pointer={runtime.read_word(client, PLAYER_FB):04x}",
                    )
        set_probe_position(start_position)
        runtime.write_byte(client, JOY_DIR, 0xFF)
        runtime.write_byte(client, PLAYER_WANT, 0xFF)

        def route_between(start: tuple[int, int], target: tuple[int, int]) -> list[int]:
            from collections import deque
            directions = ((0, -1, 1), (1, 0, 2), (0, 1, 4), (-1, 0, 8))
            queue = deque([start])
            previous = {start: None}
            previous_direction = {}
            while queue:
                x, y = queue.popleft()
                if (x, y) == target:
                    break
                for direction, (dx, dy, bit) in enumerate(directions):
                    next_cell = (x + dx, y + dy)
                    if (8 <= next_cell[0] <= 31 and 0 <= next_cell[1] < 24 and
                            full_edges[y * 24 + (x - 8)] & bit and
                            next_cell not in previous):
                        previous[next_cell] = (x, y)
                        previous_direction[next_cell] = direction
                        queue.append(next_cell)
            if target not in previous:
                fail("test-route", f"target {target} is unreachable from {start}")
            result = []
            cursor = target
            while cursor != start:
                result.append(previous_direction[cursor])
                cursor = previous[cursor]
            return result[::-1]

        waypoints = (
            char_cells[0], cl_cells[0],
            char_cells[1], cl_cells[1],
            char_cells[2], cl_cells[2],
            end_cell,
        )
        directions = []
        simulated_position = start_position
        for target in waypoints:
            segment = route_between(simulated_position, target)
            directions.extend(segment)
            x, y = simulated_position
            for direction in segment:
                if direction == 0:
                    y -= 1
                elif direction == 1:
                    x += 1
                elif direction == 2:
                    y += 1
                else:
                    x -= 1
            simulated_position = (x, y)
        simulated_name = []
        simulated_position = list(start_position)
        runtime.write_byte(client, PLAYER_WANT, 0xFF)
        runtime.write_byte(client, JOY_DIR, 0xFF)
        clean_start_tile = read_state(client, PRES_CURSOR_SAVE_A, 128)
        route_ids = monitor.setup(
            client,
            [module["load_done_dynamic_high"], module["load_done_publish"]],
        )
        ids.extend(route_ids)
        transition_hit = None

        def capture_high_score_boundary(label: str) -> None:
            owners_at_boundary = {
                owner: runtime.read_owner(client, owner) for owner in (0, 1)
            }
            map_offset = int(manifest["map_stream_offsets"][MAP_HIGH_SCORE])
            map_bytes = int(manifest["map_stream_bytes"][MAP_HIGH_SCORE])
            expected_map_stream = COLD.read_bytes()[
                map_offset:map_offset + map_bytes
            ]
            saved_par5 = runtime.read_byte(client, PAR5)
            live_pages = {}
            try:
                for page in range(0x20, 0x40):
                    runtime.write_byte(client, PAR5, page)
                    page_stream = runtime.read_bytes(
                        client, 0xA000 + map_offset, map_bytes
                    )
                    live_pages[f"{page:02x}"] = {
                        "sha256": digest(page_stream),
                        "matches": page_stream == expected_map_stream,
                        "first16": page_stream[:16].hex(),
                    }
                runtime.write_byte(client, PAR5, 0x3A)
                live_map_stream = runtime.read_bytes(
                    client, 0xA000 + map_offset, map_bytes
                )
            finally:
                runtime.write_byte(client, PAR5, saved_par5)
            map_first_diff = next(
                (index for index, pair in enumerate(zip(live_map_stream, expected_map_stream))
                 if pair[0] != pair[1]),
                None,
            )
            if map_first_diff is not None:
                fail(
                    "high-score-cold-preservation",
                    f"map stream diverged before dynamic render at +${map_first_diff:04x}",
                )
            lower_diffs = {}
            for owner, frame in owners_at_boundary.items():
                count, first = frame_diff(
                    frame, expected_high_score, 0x2000 + 16 * 1280
                )
                lower_diffs[str(owner)] = {
                    "sha256": digest(frame),
                    "lower_diff_bytes": count,
                    "lower_first_offset": first,
                }
            boundary_evidence[label] = {
                "front_owner": runtime.read_byte(client, runtime.FB_FRONT),
                "back_owner": runtime.read_byte(client, runtime.FB_BACK),
                "screen": runtime.read_byte(client, PRES_SCREEN),
                "pres_in": runtime.read_word(client, 0x00B5),
                "pres_cell": runtime.read_word(client, 0x00AA),
                "pres_dst": runtime.read_word(client, 0x00AE),
                "pres_run": runtime.read_byte(client, 0x00EA),
                "pres_value": runtime.read_byte(client, 0x00EB),
                "live_map_stream_matches": live_map_stream == expected_map_stream,
                "live_map_stream_sha256": digest(live_map_stream),
                "live_map_stream_first16": live_map_stream[:16].hex(),
                "live_map_stream_first_diff": map_first_diff,
                "live_map_stream_window": (
                    live_map_stream[max(0, (map_first_diff or 0) - 8):
                                    (map_first_diff or 0) + 24].hex()
                    if map_first_diff is not None else ""
                ),
                "expected_map_stream_window": (
                    expected_map_stream[max(0, (map_first_diff or 0) - 8):
                                       (map_first_diff or 0) + 24].hex()
                    if map_first_diff is not None else ""
                ),
                "cold_page_scan": live_pages,
                "owners": lower_diffs,
            }
            if label == "before-dynamic-render":
                write_frame_png(
                    ROOT / "build/feat003-boundary-before-dynamic-owner0.png",
                    owners_at_boundary[0],
                )
                write_frame_png(
                    ROOT / "build/feat003-boundary-before-dynamic-owner1.png",
                    owners_at_boundary[1],
                )

        for direction in directions:
            start_pointer = runtime.read_word(client, PLAYER_FB)
            before_position = (
                runtime.read_byte(client, PRES_NAME_COL),
                runtime.read_byte(client, PRES_NAME_ROW),
            )
            step_delta = -320 if direction == 0 else 320 if direction == 2 else 1 if direction == 1 else -1
            expected_pointer = start_pointer
            actual_pointer = start_pointer
            for step in range(4):
                runtime.write_byte(client, JOY_DIR, direction)
                runtime.write_byte(client, PLAYER_WANT, direction)
                calls = 0
                while True:
                    try:
                        hit = client.run_to_breakpoint(args.timeout)
                    except Exception as exc:
                        fail(
                            "pixel-step-timeout",
                            f"direction={direction} step={step + 1}/4 error={exc}",
                        )
                    if hit.get("pc") == module["load_done_dynamic_high"]:
                        if step != 3 or direction != directions[-1]:
                            fail("END-transition", f"unexpected early dynamic boundary {hit}")
                        capture_high_score_boundary("before-dynamic-render")
                        hit = client.run_to_breakpoint(args.timeout)
                        if hit.get("pc") != module["load_done_publish"]:
                            fail("END-transition", f"dynamic render did not reach publish {hit}")
                        capture_high_score_boundary("before-publication")
                        transition_hit = hit
                        break
                    if hit.get("pc") == module["load_done_publish"]:
                        if step != 3 or direction != directions[-1]:
                            fail("END-transition", f"unexpected early transition {hit}")
                        capture_high_score_boundary("before-publication")
                        transition_hit = hit
                        break
                    if hit.get("pc") != demo["name_joy_ready"]:
                        fail("name-input", f"unexpected step breakpoint {hit}")
                    runtime.write_byte(client, JOY_DIR, direction)
                    runtime.write_byte(client, PLAYER_WANT, direction)
                    calls += 1
                    actual_pointer = runtime.read_word(client, PLAYER_FB)
                    if actual_pointer != expected_pointer:
                        expected_pointer = (expected_pointer + step_delta) & 0xFFFF
                        if actual_pointer != expected_pointer:
                            fail(
                                "pixel-step-motion",
                                f"direction={direction} step={step + 1} "
                                f"pointer={actual_pointer:04x}/{expected_pointer:04x}",
                            )
                        runtime.write_byte(client, JOY_DIR, 0xFF)
                        break
                    # The breakpoint is before the injected sample executes.
                    # Starting on an ineligible parity therefore needs three
                    # observed boundaries to cover two executed Vbords.
                    if calls >= 3:
                        fail(
                            "gameplay-cadence",
                            f"direction={direction} step={step + 1} had no movement "
                            f"within two executed Vbords joy={runtime.read_byte(client, JOY_DIR)} "
                            f"want={runtime.read_byte(client, PLAYER_WANT)} "
                            f"dir={runtime.read_byte(client, 0x0006)} "
                            f"cell={(runtime.read_byte(client, 0x0009), runtime.read_byte(client, 0x000A))} "
                            f"frames={runtime.read_word(client, 0x0002):04x} "
                            f"steps={runtime.read_byte(client, PRES_NAME_STEPS)}",
                        )
                if transition_hit is not None:
                    break
                position = (
                    runtime.read_byte(client, PRES_NAME_COL),
                    runtime.read_byte(client, PRES_NAME_ROW),
                )
                if step < 3 and position != before_position:
                    fail("pixel-step-motion", f"logical position changed mid-edge: {position}")
                expected_steps = 3 - step
                if runtime.read_byte(client, PRES_NAME_STEPS) != expected_steps:
                    fail(
                        "pixel-step-motion",
                        f"direction={direction} step={step + 1} steps="
                        f"{runtime.read_byte(client, PRES_NAME_STEPS)}/{expected_steps}",
                    )
                visible_owner = runtime.read_byte(client, 0x00E3)
                visible_frame = runtime.read_owner(client, visible_owner)
                if not any(runtime.frame_tile(visible_frame, actual_pointer,
                                              width=8, rows=16)):
                    fail(
                        "pixel-step-motion",
                        f"cursor absent on rendered owner at intermediate {actual_pointer:04x} "
                        f"owner={visible_owner} steps={runtime.read_byte(client, PRES_NAME_STEPS)}",
                    )
            if transition_hit is not None:
                break
            if runtime.read_byte(client, PRES_NAME_STEPS) != 0:
                fail(
                    "cell-entry",
                    f"direction={direction} steps={runtime.read_byte(client, PRES_NAME_STEPS)}",
                )
            if direction == 0:
                simulated_position[1] -= 1
            elif direction == 1:
                simulated_position[0] += 1
            elif direction == 2:
                simulated_position[1] += 1
            else:
                simulated_position[0] -= 1
            cell = tuple(simulated_position)
            tile = action_map.get(cell)
            if tile == 0xFD:
                transition_hit = hit
                break
            if tile == 0xFE:
                if simulated_name:
                    simulated_name.pop()
            elif tile is not None and len(simulated_name) < 7:
                simulated_name.append(tile)
            if runtime.read_byte(client, PRES_NAME_LEN) != len(simulated_name):
                fail("cell-entry", f"name length did not apply action at {cell}")
            simulated_position[0] = cell[0]
            simulated_position[1] = cell[1]
            visible_owner = runtime.read_byte(client, 0x00E3)
            visible_frame = runtime.read_owner(client, visible_owner)
            if not any(runtime.frame_tile(visible_frame, actual_pointer,
                                          width=8, rows=16)):
                fail("pixel-step-motion", f"regular player absent at {actual_pointer:04x}")
            if clean_start_tile is None:
                clean_start_tile = runtime.frame_tile(
                    visible_frame, name_contract["cursor_destination"], width=8, rows=16
                )
            elif (
                abs(simulated_position[0] - start_position[0]) >= 2 or
                abs(simulated_position[1] - start_position[1]) >= 2
            ) and runtime.frame_tile(
                    visible_frame, name_contract["cursor_destination"], width=8, rows=16
            ) != clean_start_tile:
                actual_start_tile = runtime.frame_tile(
                    visible_frame, name_contract["cursor_destination"], width=8, rows=16
                )
                fail(
                    "owner-local-cursor-restore",
                    f"starting cursor footprint differs after owner swap owner={visible_owner} "
                    f"position={simulated_position} player={runtime.read_word(client, PLAYER_FB):04x} "
                    f"ptr-a={runtime.read_word(client, 0x00DA):04x} "
                    f"ptr-b={runtime.read_word(client, 0x00DC):04x} "
                    f"clean={clean_start_tile.hex()} actual={actual_start_tile.hex()}",
                )

        monitor.clear(client, ids)
        ids = []
        if transition_hit is None:
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
            monitor.clear(client, ids)
        elif runtime.read_byte(client, PRES_SCREEN) != MAP_HIGH_SCORE:
            fail("END-publication", f"END load completed on wrong screen: {transition_hit}")
        ids = monitor.setup(client, [module["presentation_flow_tick"]])
        hit = client.run_to_breakpoint(args.timeout)
        if hit.get("pc") != module["presentation_flow_tick"]:
            fail("END-publication", f"publish body did not return to dispatcher: {hit}")
        if runtime.read_byte(client, 0x0091) != 0:
            hit = client.run_to_breakpoint(args.timeout)
            if hit.get("pc") != module["presentation_flow_tick"]:
                fail("END-publication", f"unexpected second dispatcher boundary: {hit}")
        if runtime.read_byte(client, 0x0091) != 0:
            fail("END-publication", "post-END framebuffer publication remains pending")
        capture_high_score_boundary("after-publication")
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
        high_score_name_destinations = manifest["high_score_table"]["name_destinations"]
        records = [expected_table[index:index + 10] for index in range(0, 90, 10)]
        front_owner = runtime.read_byte(client, runtime.FB_FRONT)
        front_frame = owners[front_owner]
        row_count = sum(
            score_visible(front_frame, score_destination, record[:3], glyphs, manifest) and
            name_visible(front_frame, name_destination, record[3:], black, manifest)
            for score_destination, name_destination, record in zip(
                score_destinations, high_score_name_destinations, records
            )
        )
        if row_count != 9:
            fail("all-nine-rendering", f"visible score/name rows={row_count}")
        if args.updated_png:
            write_frame_png(args.updated_png, front_frame)
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
        # Start one traversable cell before END so the bounded probe measures
        # the empty-name transition rather than an unrelated long walk.
        end_start_position = (26, 20)
        end_start_pointer = (
            cursor_destination +
            (end_start_position[0] - 19) * 4 +
            (end_start_position[1] - 22) * 1280
        ) & 0xFFFF
        runtime.write_byte(client, PRES_NAME_ROW, end_start_position[1])
        runtime.write_byte(client, PRES_NAME_COL, end_start_position[0])
        runtime.write_byte(client, 0x0009, end_start_position[0])
        runtime.write_byte(client, 0x000A, end_start_position[1])
        runtime.write_word(client, PLAYER_FB, end_start_pointer)
        runtime.write_word(client, 0x00DA, end_start_pointer)
        runtime.write_word(client, 0x00DC, end_start_pointer)
        runtime.write_byte(client, PRES_NAME_STEPS, 0)
        runtime.write_byte(client, PRES_NAME_LEN, 0)
        runtime.write_byte(client, PRES_NAME_LAST_DIR, 0xFF)
        runtime.write_byte(client, JOY_DIR, 0xFF)
        runtime.write_byte(client, PLAYER_WANT, 1)
        monitor.clear(client, ids)
        ids = monitor.setup(client, [demo["name_joy_ready"], module["load_done_publish"]])
        empty_end_transition = False
        for step in range(12):
            hit = client.run_to_breakpoint(args.timeout)
            if hit.get("pc") == module["load_done_publish"]:
                empty_end_transition = True
                break
            if hit.get("pc") != demo["name_joy_ready"]:
                fail("empty-name-END", f"unexpected pixel step breakpoint: {hit}")
            runtime.write_byte(client, JOY_DIR, 1)
            runtime.write_byte(client, PLAYER_WANT, 1)
        if not empty_end_transition:
            fail(
                "empty-name-END",
                f"END did not complete map transition within twelve intervals "
                f"cell={(runtime.read_byte(client, 9), runtime.read_byte(client, 10))} "
                f"pointer={runtime.read_word(client, PLAYER_FB):04x} "
                f"steps={runtime.read_byte(client, PRES_NAME_STEPS)} "
                f"joy={runtime.read_byte(client, JOY_DIR)} "
                f"want={runtime.read_byte(client, PLAYER_WANT)}",
            )
        expected_empty = expected_score + bytes((black,)) * 7 + fixture[:80]
        if (runtime.read_byte(client, PRES_SCREEN) != MAP_HIGH_SCORE or
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
        timer_cursor_start = runtime.read_word(client, PLAYER_FB)
        for _ in range(2):
            runtime.write_byte(client, JOY_DIR, 1)
            runtime.write_byte(client, PLAYER_WANT, 1)
            hit = client.run_to_breakpoint(args.timeout)
            if hit.get("pc") != demo["name_joy_ready"]:
                fail("timer-cursor-setup", f"unexpected breakpoint {hit}")
            if runtime.read_word(client, PLAYER_FB) != timer_cursor_start:
                break
        if runtime.read_word(client, PLAYER_FB) == timer_cursor_start:
            fail("timer-cursor-setup", "cursor did not create an owner-local lag")
        runtime.write_byte(client, JOY_DIR, 0xFF)
        write_state(client, PRES_NAME, bytes((default_name[0],)) + bytes((black,)) * 6)
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
        front_pointer = runtime.read_word(
            client, 0x00DA if front == 0 else 0x00DC
        )
        if front_pointer != runtime.read_word(client, PLAYER_FB):
            fail(
                "timer-cursor-convergence",
                f"timer published stale cursor owner={front} "
                f"owner-pointer={front_pointer:04x} "
                f"current={runtime.read_word(client, PLAYER_FB):04x}",
            )
        if not entry_name_visible(
                runtime.read_owner(client, front), name_destinations,
                bytes((default_name[0],)), black, manifest):
            owner_name_tiles = {
                owner: [runtime.frame_tile(runtime.read_owner(client, owner), destination).hex()
                        for destination in name_destinations]
                for owner in (0, 1)
            }
            fail(
                "timer-name-convergence",
                f"timer published a stale pending name front={front} "
                f"state={read_state(client, PRES_NAME, 7).hex()} "
                f"owners={owner_name_tiles}",
            )
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
        timeout_table = expected_score + bytes((default_name[0],)) + bytes((black,)) * 6 + fixture[:80]
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
            "wall-edge-block", "pixel-step-motion",
            "owner-local-cursor-restore", "timer-first-box", "timer-timeout",
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
    print("FEAT-003 highscore-test: entry, pixel steering, owner restore, END, nine rows, and reset-only hold passed")
    print(f"evidence={args.output}")


if __name__ == "__main__":
    main()
