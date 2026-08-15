#!/usr/bin/env python3
"""Verify BUG-017 geometry, live payload identity, and forced skull reset."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
from pathlib import Path

from build_screen import compile_screen
from verify_perimeter_reset import stores


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
MONITOR_INPUT = ROOT / "scripts/verify_bug009_monitor_input.py"
FB_BYTES = 0x7800
FB_FRONT = 0x008F
FB_BACK = 0x0090
FB_WRITE_FRONT_FAULT = 0x0099
ENTITY_COUNT = 0x0032
ENTITY_TABLE = 0xA380
PLAYER_CELL_X = 0x0009
PLAYER_CELL_Y = 0x000A
PAR1 = 0xFFA1
PAR5 = 0xFFA5


def load_monitor():
    spec = importlib.util.spec_from_file_location("bug009_monitor", MONITOR_INPUT)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load monitor client")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def symbols(path: Path) -> dict[str, int]:
    return {
        name: int(value, 16)
        for name, value in re.findall(
            r"^Symbol: (\w+) .* = ([0-9A-Fa-f]+)$",
            path.read_text(encoding="ascii"), re.MULTILINE,
        )
    }


def read_bytes(client, address: int, length: int) -> bytes:
    return bytes.fromhex(client.call(
        "read_memory", {"addr": address, "length": length}
    )["data"])


def read_byte(client, address: int) -> int:
    return read_bytes(client, address, 1)[0]


def write_bytes(client, address: int, data: bytes) -> None:
    client.call("write_memory", {"addr": address, "data": data.hex()})


def coordinates(box: int) -> tuple[int, int]:
    if not 0 <= box < 92:
        raise ValueError(box)
    if box < 12:
        return box + 12, 0
    if box < 35:
        return 23, box - 11
    if box < 58:
        return 22 - (box - 35), 23
    if box < 80:
        return 0, 22 - (box - 58)
    return box - 80, 0


def expected_reset(stride: int = 8) -> dict[int, int]:
    screen_map, tiles, *_ = compile_screen(
        ROOT / "tiled/coco-screen.tmx",
        ROOT / "assets/arcade/maze.json",
        ROOT / "assets/arcade/chars.json",
        ROOT / "assets/arcade/sprites.json",
    )
    expected: dict[int, int] = {}
    for box in range(92):
        x, y = coordinates(box)
        tile = tiles[screen_map[y * 40 + x + 8]]
        for row in range(8):
            base = 0x2000 + (y * stride + row) * 160 + (x + 8) * 4
            for column, value in enumerate(tile[row * 4:(row + 1) * 4]):
                if value >> 4 == 6 or value & 0x0F == 6:
                    expected[base + column] = value
    return expected


def static_contract(payload: bytes) -> tuple[dict[int, int], dict[str, object]]:
    expected = expected_reset()
    actual = stores(payload)
    if actual != expected:
        raise RuntimeError("decoded payload differs from independent 8-pixel oracle")
    if len({coordinates(box) for box in range(92)}) != 92:
        raise RuntimeError("perimeter coordinates contain a duplicate")
    mutation = expected_reset(5)
    first_non_top = min(
        address for address in set(expected) ^ set(mutation)
        if address >= 0x2000
    )
    if mutation == expected:
        raise RuntimeError("five-stride mutation was accepted")
    bottom_scanline = max(coordinates(box)[1] * 8 + 7 for box in range(92))
    if bottom_scanline != 191 or max(
        (address - 0x2000) // 160 for address in expected
    ) > bottom_scanline:
        raise RuntimeError("corrected perimeter footprint exceeds scanline 191")
    source = (ROOT / "src/main.s").read_text(encoding="utf-8")
    begin = source.index("\ndraw_perimeter_box\n")
    end = source.index("\ndpb_row\n", begin)
    incremental = source[begin:end]
    for fragment in ("ldb     #5", "mul", "tfr     b,a", "clrb"):
        if fragment not in incremental:
            raise RuntimeError("incremental eight-pixel identity changed")
    bootstrap = (ROOT / "src/gmc_bootstrap.s").read_text(encoding="utf-8")
    if "LDD #value16 / STD address" not in bootstrap or "lda     #8" not in bootstrap:
        raise RuntimeError("boot paired-store/eight-row contract missing")
    pair_count = 0
    cursor = 0
    while cursor < len(payload) - 1:
        if payload[cursor] == 0xCC:
            pair_count += 1
            cursor += 6
        elif payload[cursor] == 0x86:
            cursor += 5
        else:
            raise RuntimeError(f"unexpected payload opcode ${payload[cursor]:02X}")
    return expected, {
        "coordinates": 92,
        "tile_height_pixels": 8,
        "scanline_stride_bytes": 160,
        "bottom_scanline": bottom_scanline,
        "changed_bytes": len(expected),
        "payload_bytes": len(payload),
        "payload_page_margin_bytes": 8192 - len(payload),
        "paired_store_opcodes": pair_count,
        "five_stride_mutation_rejected": True,
        "first_mutated_address": first_non_top,
        "incremental_renderer_unchanged": True,
    }


def live_frame(client, page0: int) -> bytes:
    saved = read_bytes(client, PAR1, 4)
    try:
        write_bytes(client, PAR1, bytes(range(page0, page0 + 4)))
        return read_bytes(client, 0x2000, FB_BYTES)
    finally:
        write_bytes(client, PAR1, saved)


def verify_live_identity(client, payload: bytes) -> dict[str, bool]:
    resident = (BUILD / "ladybug-runtime.rom").read_bytes()[:0x3E00]
    enemy = (BUILD / "ladybug-enemy-runtime.rom").read_bytes()
    resident_ok = read_bytes(client, 0xC000, len(resident)) == resident
    enemy_ok = read_bytes(client, 0x0800, len(enemy)) == enemy
    saved_par5 = read_byte(client, PAR5)
    try:
        write_bytes(client, PAR5, b"\x20")
        payload_ok = read_bytes(client, 0xA000, len(payload)) == payload
    finally:
        write_bytes(client, PAR5, bytes((saved_par5,)))
    identity = {
        "resident_authored_live_match": resident_ok,
        "enemy_authored_live_match": enemy_ok,
        "reset_generated_live_match": payload_ok,
    }
    if not all(identity.values()):
        raise RuntimeError(f"live artifact identity mismatch: {identity}")
    return identity


def skull_case(monitor, binary: Path, rom: Path, timeout: float,
               initial_owner: int, expected: dict[int, int],
               payload: bytes) -> dict[str, object]:
    presentation = symbols(BUILD / "ladybug-presentation-runtime.map")
    main = symbols(BUILD / "ladybug.map")
    enemy = symbols(BUILD / "ladybug-enemy-runtime.map")
    process, client = monitor.launch(binary, rom, monitor.free_port())
    ids: list[int] = []
    try:
        start_id, pickup_id = monitor.setup(
            client, [presentation["start_screen"], main["check_entity_pickup"]]
        )
        ids.extend((start_id, pickup_id))
        owner_set = False
        while True:
            hit = client.run_to_breakpoint(timeout)
            if hit.get("pc") == presentation["start_screen"]:
                if not owner_set:
                    write_bytes(client, FB_FRONT, bytes((initial_owner, 1 - initial_owner)))
                    owner_set = True
                continue
            if hit.get("pc") == main["check_entity_pickup"]:
                break
            raise RuntimeError(f"skull phase entry: unexpected marker {hit}")
        monitor.clear(client, ids)
        ids.clear()
        identity = verify_live_identity(client, payload)
        x = read_byte(client, PLAYER_CELL_X)
        y = read_byte(client, PLAYER_CELL_Y)
        write_bytes(client, ENTITY_COUNT, b"\x01")
        write_bytes(client, ENTITY_TABLE, bytes((x, y, 1, 0)))
        reset_id = monitor.setup(client, [enemy["perimeter_reset_published"]])[0]
        ids.append(reset_id)
        targets: list[int] = []
        for publication in range(2):
            hit = client.run_to_breakpoint(timeout)
            if hit.get("pc") != enemy["perimeter_reset_published"]:
                raise RuntimeError(f"skull reset publication {publication + 1} missing: {hit}")
            targets.append(read_byte(client, FB_BACK))
        frame_a = live_frame(client, 0x30)
        frame_b = live_frame(client, 0x2C)
        for label, frame in (("A", frame_a), ("B", frame_b)):
            wrong = [
                address for address, value in expected.items()
                if frame[address - 0x2000] != value
            ]
            if wrong:
                raise RuntimeError(
                    f"skull reset {label}: {len(wrong)} perimeter bytes differ; "
                    f"first=${wrong[0]:04X}"
                )
        faults = read_byte(client, FB_WRITE_FRONT_FAULT)
        if faults:
            raise RuntimeError(f"skull reset FRONT-write faults: {faults}")
        return {
            "initial_owner": initial_owner,
            "player_cell": [x, y],
            "skull_record_forced": True,
            "reset_publications": 2,
            "publication_back_owners": targets,
            "owner_a_perimeter_exact": True,
            "owner_b_perimeter_exact": True,
            "owner_a_frame_sha256": hashlib.sha256(frame_a).hexdigest(),
            "owner_b_frame_sha256": hashlib.sha256(frame_b).hexdigest(),
            "front_write_faults": faults,
            "live_identity": identity,
        }
    finally:
        if ids:
            try:
                monitor.clear(client, ids)
            except Exception:
                pass
        client.close()
        monitor.stop(process)
        process.wait(timeout=2)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xroar", type=Path, required=True)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()
    payload = (BUILD / "ladybug-perimeter-reset.bin").read_bytes()
    expected, static = static_contract(payload)
    monitor = load_monitor()
    skulls = [
        skull_case(monitor, args.xroar, args.rom, args.timeout, 0, expected, payload),
        skull_case(monitor, args.xroar, args.rom, args.timeout, 1, expected, payload),
    ]
    evidence = {
        "schema": "ladybug-bug017-perimeter-vertical-stride-v1",
        "rom_sha256": hashlib.sha256(args.rom.read_bytes()).hexdigest(),
        "phase_deadline_seconds": args.timeout,
        "static_contract": static,
        "forced_skull_cases": skulls,
        "verdict": "PASS",
    }
    args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="ascii")
    print("BUG-017 perimeter stride pass: independent geometry and both-owner skull reset")


if __name__ == "__main__":
    main()
