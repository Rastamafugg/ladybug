#!/usr/bin/env python3
"""Run the complete BUG-011 sequence in XRoar through the private monitor."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import signal
import socket
import subprocess
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MONITOR_PATH = ROOT / "scripts/verify_bug009_monitor_input.py"
PRESENTATION_MAP = ROOT / "build/ladybug-presentation-runtime.map"
MAIN_MAP = ROOT / "build/ladybug.map"
MANIFEST = ROOT / "build/ladybug-presentation.json"
LAYOUT = ROOT / "build/ladybug-sparse-layout.json"
HELPER = ROOT / "build/ladybug-instruction-runtime.bin"
COLD = ROOT / "build/ladybug-presentation-cold.bin"
RUNTIME_ROM = ROOT / "build/ladybug-runtime.rom"
PAR5 = 0xFFA5
PAR1 = 0xFFA1
FB_FRONT = 0x008F
FB_BACK = 0x0090
PRES_MODE = 0x00A5
PRES_SCREEN = 0x00A6
PRES_TIMER = 0x00B0
PRES_PHASE = 0x00CA
PRES_HIGHLIGHT = 0x00CF
PRES_ACTOR_FRAME = 0x00CE
PRES_WORK = 0x00D1
VISIBLE_START = 0x2000
VISIBLE_BYTES = 30720
TRACE_MAGIC = 0x06AA
TRACE_COLOURS = 0x06AB
TRACE_CONSUMES = 0x06AC
TRACE_DEATHS = 0x06AD
TRACE_OWNERS = 0x06AE


def load_monitor():
    spec = importlib.util.spec_from_file_location("bug009_monitor", MONITOR_PATH)
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
            path.read_text(encoding="utf-8"), re.MULTILINE,
        )
    }


def launch_fast(monitor, binary: Path, rom: Path):
    port = monitor.free_port()
    process = subprocess.Popen([
        str(binary), "-ui", "null", "-ao", "null", "-machine", "coco3",
        "-ram", "512", "-cart-type", "gmc", "-cart-rom", str(rom),
        "-cart-autorun", "-no-ratelimit", "-monitor", f"127.0.0.1:{port}",
        "-monitor-halt-on-start",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=(os.name != "nt"))
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            sock = socket.create_connection(("127.0.0.1", port), timeout=0.5)
            client = monitor.MonitorClient(sock)
            hello = json.loads(client.file.readline())
            if hello.get("method") != "hello":
                raise monitor.MonitorError(f"unexpected hello: {hello}")
            client.call("events.subscribe", {"kinds": ["bp"]})
            return process, client
        except (OSError, monitor.MonitorError):
            time.sleep(0.05)
    monitor.stop(process)
    raise monitor.MonitorError("monitor listener did not accept a client")


def read_bytes(client, address: int, length: int) -> bytes:
    return bytes.fromhex(client.call("read_memory", {
        "addr": address, "length": length,
    })["data"])


def read_byte(client, address: int) -> int:
    return read_bytes(client, address, 1)[0]


def read_word(client, address: int) -> int:
    return int.from_bytes(read_bytes(client, address, 2), "big")


def write_word(client, address: int, value: int) -> None:
    client.call("write_memory", {
        "addr": address, "data": value.to_bytes(2, "big").hex(),
    })


def write_byte(client, address: int, value: int) -> None:
    client.call("write_memory", {"addr": address, "data": f"{value:02x}"})


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_tile(client, destination: int, width: int = 4, rows: int = 8) -> bytes:
    return b"".join(
        read_bytes(client, destination + row * 160, width)
        for row in range(rows)
    )


def read_owner(client, owner: int) -> bytes:
    saved = [read_byte(client, PAR1 + index) for index in range(4)]
    base = 0x30 if owner == 0 else 0x2C
    output = bytearray()
    try:
        for index in range(4):
            write_byte(client, PAR1 + index, base + index)
            count = min(0x2000, VISIBLE_BYTES - len(output))
            output.extend(read_bytes(client, 0x2000 + index * 0x2000, count))
    finally:
        for index, page in enumerate(saved):
            write_byte(client, PAR1 + index, page)
    return bytes(output)


def frame_tile(frame: bytes, destination: int, width: int = 4,
               rows: int = 8) -> bytes:
    offset = destination - VISIBLE_START
    return b"".join(
        frame[offset + row * 160:offset + row * 160 + width]
        for row in range(rows)
    )


def expected_tile(manifest: dict[str, object], tile_id: int) -> bytes:
    cold = COLD.read_bytes()
    base = int(manifest["gameplay_tile_base"])
    if tile_id < base:
        offset = int(manifest["tile_atlas_offset"]) + tile_id * 32
        return cold[offset:offset + 32]
    lookup_offset = int(manifest["gameplay_lookup_offset"]) + tile_id - base
    gameplay_id = cold[lookup_offset]
    runtime = RUNTIME_ROM.read_bytes()
    offset = 0xE3D0 - 0xC000 + gameplay_id * 32
    return runtime[offset:offset + 32]


def stop(process: subprocess.Popen[object]) -> None:
    if process.poll() is not None:
        return
    if os.name != "nt":
        try:
            os.killpg(process.pid, signal.SIGKILL)
            return
        except ProcessLookupError:
            return
    process.kill()


def run_scenario(monitor, binary: Path, rom: Path, timeout: float,
                 owner_order: tuple[int, int]) -> dict[str, object]:
    presentation_symbols = symbols(PRESENTATION_MAP)
    manifest = json.loads(MANIFEST.read_text(encoding="ascii"))
    choreography = manifest["instruction_choreography"]
    sparse_layout = json.loads(LAYOUT.read_text(encoding="ascii"))
    runtime_layout = sparse_layout["instruction_runtime"]
    helper = HELPER.read_bytes()
    staged = helper.ljust(runtime_layout["staged_bytes"], b"\x00")
    process, client = launch_fast(monitor, binary, rom)
    try:
        entry = presentation_symbols["presentation_flow_tick"]
        ids = monitor.setup(client, [entry])
        hit = client.run_to_breakpoint(timeout)
        if hit.get("pc") != entry:
            raise SystemExit(f"BUG-011 runtime: presentation entry timeout {hit}")
        saved_par5 = read_byte(client, PAR5)
        write_byte(client, PAR5, 0x23)
        staged_live = read_bytes(client, 0xA422, len(staged))
        write_byte(client, PAR5, saved_par5)
        if staged_live != staged:
            differences = [index for index, pair in enumerate(zip(staged_live, staged))
                           if pair[0] != pair[1]]
            matches = []
            for page in range(0x20, 0x40):
                write_byte(client, PAR5, page)
                if read_bytes(client, 0xA422, len(staged)) == staged:
                    matches.append(page)
            write_byte(client, PAR5, 0x3A)
            cold_prefix = read_bytes(client, 0xA000, 16).hex()
            write_byte(client, PAR5, saved_par5)
            raise SystemExit(
                "BUG-011 runtime: staged page-$23 helper differs; "
                f"live={digest(staged_live)} expected={digest(staged)} "
                f"first={differences[:8]} live16={staged_live[:16].hex()} "
                f"expected16={staged[:16].hex()} matches={matches} "
                f"boot={read_bytes(client, 0x02F0, 4).hex()} "
                f"magic={read_byte(client, PRES_MODE):02x} cold16={cold_prefix}"
            )
        monitor.clear(client, ids)

        instructions_tick = presentation_symbols["instructions_tick"]
        ids = monitor.setup(client, [instructions_tick])
        hit = client.run_to_breakpoint(timeout)
        if hit.get("pc") != instructions_tick:
            raise SystemExit(f"BUG-011 runtime: instructions entry timeout {hit}")
        if read_bytes(client, 0x0300, len(helper)) != helper:
            raise SystemExit("BUG-011 runtime: installed $0300 helper differs")
        saved_par5 = read_byte(client, PAR5)
        cold_live = bytearray()
        for page in range(0x3A, 0x3E):
            write_byte(client, PAR5, page)
            cold_live.extend(read_bytes(client, 0xA000, 0x2000))
        write_byte(client, PAR5, saved_par5)
        cold_expected = COLD.read_bytes()
        if bytes(cold_live[:len(cold_expected)]) != cold_expected:
            raise SystemExit("BUG-011 runtime: live cold payload differs")
        static_owner = read_byte(client, FB_FRONT)
        static_frames = {owner: read_owner(client, owner) for owner in (0, 1)}
        expected_static = manifest["static_frame_sha256"][1]
        static_hashes = {
            owner: digest(frame) for owner, frame in static_frames.items()
        }
        if any(value != expected_static for value in static_hashes.values()):
            raise SystemExit(
                "BUG-011 runtime: both initial instruction owners are not hydrated; "
                f"live={static_hashes} expected={expected_static}"
            )
        static_frame = static_frames[static_owner]
        write_byte(client, FB_FRONT, owner_order[0])
        write_byte(client, FB_BACK, owner_order[1])
        write_byte(client, 0xFF9D, 0xC0 if owner_order[0] == 0 else 0xB0)
        monitor.clear(client, ids)
        return_pc = presentation_symbols["instructions_runtime_return"]
        init_ids = monitor.setup(client, [return_pc])
        init_hit = client.run_to_breakpoint(timeout)
        monitor.clear(client, init_ids)
        if init_hit.get("pc") != return_pc:
            raise SystemExit(f"BUG-011 runtime: first initialization timeout {init_hit}")
        first_initialised_hashes = sorted(
            digest(read_owner(client, owner)) for owner in (0, 1)
        )
        load_tick = presentation_symbols["load_tick"]
        ids = monitor.setup(client, [load_tick])
        hit = client.run_to_breakpoint(timeout)
        if hit.get("pc") != load_tick:
            raise SystemExit(f"BUG-011 runtime: level-start handoff timeout {hit}")
        if read_byte(client, PRES_SCREEN) != 2 or read_byte(client, PRES_MODE) != 1:
            raise SystemExit(
                "BUG-011 runtime: next screen is not level-start load; "
                f"screen={read_byte(client, PRES_SCREEN)} "
                f"mode={read_byte(client, PRES_MODE)} "
                f"timer={read_word(client, PRES_TIMER)} "
                f"phase={read_byte(client, PRES_PHASE)} "
                f"trace={read_bytes(client, TRACE_MAGIC, 6).hex()}"
            )
        if read_byte(client, TRACE_MAGIC) != 0xA5:
            raise SystemExit("BUG-011 runtime: helper trace was not initialized")
        saved_par5 = read_byte(client, PAR5)
        cold_after = bytearray()
        for page in range(0x3A, 0x3E):
            write_byte(client, PAR5, page)
            cold_after.extend(read_bytes(client, 0xA000, 0x2000))
        write_byte(client, PAR5, saved_par5)
        if bytes(cold_after[:len(cold_expected)]) != cold_expected:
            differences = [
                index for index, pair in enumerate(zip(cold_after, cold_expected))
                if pair[0] != pair[1]
            ]
            raise SystemExit(
                "BUG-011 runtime: choreography corrupted cold payload; "
                f"first={differences[:8]} count={len(differences)}"
            )

        trace = {
            "colour_transitions": read_byte(client, TRACE_COLOURS),
            "consume_count": read_byte(client, TRACE_CONSUMES),
            "death_surface_count": read_byte(client, TRACE_DEATHS),
            "owner_mask": read_byte(client, TRACE_OWNERS),
        }
        if trace["colour_transitions"] != 48:
            raise SystemExit(
                "BUG-011 runtime: colour trace differs: "
                f"{trace} phase={read_byte(client, PRES_PHASE)} "
                f"timer={read_word(client, PRES_TIMER)}"
            )
        if trace["consume_count"] != 16:
            raise SystemExit(f"BUG-011 runtime: consume trace differs: {trace}")
        if trace["death_surface_count"] != 15:
            raise SystemExit(f"BUG-011 runtime: death trace differs: {trace}")
        if trace["owner_mask"] != 3:
            raise SystemExit(f"BUG-011 runtime: owner alternation missing: {trace}")
        if read_word(client, PRES_TIMER) != choreography["next_screen_tick"]:
            raise SystemExit("BUG-011 runtime: terminal pause boundary differs")
        if read_byte(client, PRES_PHASE) != 16:
            raise SystemExit("BUG-011 runtime: terminal event index differs")

        front_owner = read_byte(client, FB_FRONT)
        frame = read_owner(client, front_owner)
        targets = [[
            frame_tile(frame, event["target_destination"] + offset)
            for offset in (0, 4, 1280, 1284)
        ] for event in choreography["events"]]
        hud = []
        expected_hud = []
        for event in choreography["events"]:
            if not event["hud_destination"]:
                continue
            hud.append(frame_tile(frame, event["hud_destination"]))
            expected_hud.append(expected_tile(manifest, event["hud_tile_id"]))
            if event["hud_tile_2_id"]:
                hud.append(frame_tile(frame, event["hud_destination"] + 4))
                expected_hud.append(expected_tile(
                    manifest, event["hud_tile_2_id"]
                ))
        target_residue = targets[:15] + [targets[15][:2]]
        if any(any(any(tile) for tile in surface) for surface in target_residue):
            visible = [
                (index, choreography["events"][index]["target_destination"],
                 sum(value != 0 for tile in surface for value in tile),
                 [tile.hex() for tile in surface])
                for index, surface in enumerate(target_residue)
                if any(any(tile) for tile in surface)
            ]
            raise SystemExit(
                "BUG-011 runtime: consumed targets remain visible: "
                f"{visible} owner_state={read_bytes(client, 0x00D2, 6).hex()} "
                f"front={read_byte(client, FB_FRONT)} back={read_byte(client, FB_BACK)}"
            )
        if any(not any(tile) for tile in hud):
            dark = [index for index, tile in enumerate(hud) if not any(tile)]
            raise SystemExit(
                f"BUG-011 runtime: consumed HUD targets are not lit: {dark}"
            )
        if hud != expected_hud:
            differences = [
                (index, hud[index].hex(), expected_hud[index].hex())
                for index in range(len(hud)) if hud[index] != expected_hud[index]
            ]
            raise SystemExit(
                f"BUG-011 runtime: final HUD colours/pixels differ: {differences}"
            )

        for reward_name in ("life", "coin"):
            destination = choreography["reward_destinations"][reward_name]
            destinations = (destination, destination + 4,
                            destination + 1280, destination + 1284)
            expected = [
                expected_tile(manifest, tile_id)
                for tile_id in choreography["reward_tile_ids"][reward_name]
            ]
            actual = [frame_tile(frame, item) for item in destinations]
            if actual != expected:
                raise SystemExit(f"BUG-011 runtime: {reward_name} reward differs")

        multiplier_expected = [
            expected_tile(manifest, tile_id)
            for tile_id in choreography["multiplier_tile_ids"]["5"]
        ]
        for destination in choreography["multiplier_destinations"]:
            actual = [frame_tile(frame, destination),
                      frame_tile(frame, destination + 4)]
            if actual != multiplier_expected:
                raise SystemExit("BUG-011 runtime: final X5 multiplier differs")

        value_expected = [
            expected_tile(manifest, tile_id)
            for tile_id in choreography["value_tile_ids"]["red"]
        ]
        value_destination = choreography["value_destination"]
        value_actual = [
            frame_tile(frame, value_destination + index * 4)
            for index in range(3)
        ]
        if value_actual != value_expected:
            raise SystemExit("BUG-011 runtime: final 800 value differs")
        angel_destination = read_word(client, 0x00B7)
        if angel_destination != choreography["angel_destination"]:
            raise SystemExit(
                "BUG-011 runtime: held angel is not at authored destination; "
                f"actual=${angel_destination:04X} "
                f"expected=${choreography['angel_destination']:04X}"
            )
        angel = frame_tile(frame, angel_destination, width=8, rows=16)
        if not any(angel):
            raise SystemExit("BUG-011 runtime: held angel surface is empty")
        monitor.clear(client, ids)

        reset_entry = symbols(MAIN_MAP)["entry"]
        post_terminal = []
        expected_stack = None
        for phase, marker_name, screen_index in (
            ("level-start active", "level_tick", 2),
            ("attract loop resumed", "attract_tick", 0),
        ):
            marker = presentation_symbols[marker_name]
            phase_ids = monitor.setup(client, [marker, reset_entry])
            phase_hit = client.run_to_breakpoint(timeout)
            monitor.clear(client, phase_ids)
            if phase_hit.get("pc") == reset_entry:
                raise SystemExit(
                    f"BUG-011 runtime: reset entered after terminal during {phase}"
                )
            if phase_hit.get("pc") != marker:
                raise SystemExit(
                    f"BUG-011 runtime: {phase} timeout: {phase_hit}"
                )
            registers = client.call("read_registers")
            stack = registers.get("s", registers.get("S"))
            if expected_stack is None:
                expected_stack = stack
            elif stack != expected_stack:
                raise SystemExit(
                    "BUG-011 runtime: stack changed after terminal: "
                    f"${expected_stack:04X} -> ${stack:04X}"
                )
            visible_owner = read_byte(client, FB_FRONT)
            visible_frame = read_owner(client, visible_owner)
            expected_visible = manifest["static_frame_sha256"][screen_index]
            visible_hash = digest(visible_frame)
            if visible_hash != expected_visible:
                raise SystemExit(
                    f"BUG-011 runtime: {phase} visible frame differs; "
                    f"live={visible_hash} expected={expected_visible}"
                )
            post_terminal.append({
                "phase": phase,
                "marker": marker,
                "reset_marker": reset_entry,
                "stack": stack,
                "screen": read_byte(client, PRES_SCREEN),
                "mode": read_byte(client, PRES_MODE),
                "visible_owner": visible_owner,
                "visible_sha256": visible_hash,
            })
        write_word(client, PRES_TIMER, 557)
        repeat_ids = monitor.setup(client, [instructions_tick])
        repeat_hit = client.run_to_breakpoint(timeout)
        monitor.clear(client, repeat_ids)
        if repeat_hit.get("pc") != instructions_tick:
            raise SystemExit(f"BUG-011 runtime: repeat instruction entry timeout {repeat_hit}")
        repeat_static_hashes = {
            owner: digest(read_owner(client, owner)) for owner in (0, 1)
        }
        if any(value != expected_static for value in repeat_static_hashes.values()):
            raise SystemExit(
                "BUG-011 runtime: repeat instruction owners differ; "
                f"live={repeat_static_hashes} expected={expected_static}"
            )
        repeat_init_ids = monitor.setup(client, [return_pc])
        repeat_init_hit = client.run_to_breakpoint(timeout)
        monitor.clear(client, repeat_init_ids)
        if repeat_init_hit.get("pc") != return_pc:
            raise SystemExit(
                f"BUG-011 runtime: repeat initialization timeout {repeat_init_hit}"
            )
        repeat_initialised_hashes = sorted(
            digest(read_owner(client, owner)) for owner in (0, 1)
        )
        if repeat_initialised_hashes != first_initialised_hashes:
            raise SystemExit(
                "BUG-011 runtime: repeat initialization pixels differ; "
                f"first={first_initialised_hashes} repeat={repeat_initialised_hashes}"
            )
        return {
            "owner_order": owner_order,
            "staged_sha256": digest(staged_live),
            "installed_sha256": digest(helper),
            "cold_payload_sha256": digest(cold_expected),
            "trace": trace,
            "front_owner": front_owner,
            "initial_static_sha256": digest(static_frame),
            "initial_owner_sha256": static_hashes,
            "final_frame_sha256": digest(frame),
            "angel_sha256": digest(angel),
            "terminal_timer": choreography["next_screen_tick"],
            "next_screen": 2,
            "post_terminal": post_terminal,
            "repeat_static_sha256": repeat_static_hashes,
            "repeat_initialised_sha256": repeat_initialised_hashes,
        }
    finally:
        try:
            client.close()
        finally:
            stop(process)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--xroar", type=Path,
        default=Path(os.environ.get(
            "XROAR", "/mnt/d/retro/ladybug/docs/reference/xroar/src/xroar",
        )),
    )
    parser.add_argument("--rom", type=Path, default=ROOT / "build/ladybug.rom")
    parser.add_argument("--output", type=Path,
                        default=ROOT / "build/bug011-runtime.json")
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()
    monitor = load_monitor()
    results = [
        run_scenario(monitor, args.xroar, args.rom, args.timeout, order)
        for order in ((0, 1), (1, 0))
    ]
    args.output.write_text(json.dumps({
        "schema": "ladybug-bug011-runtime-v1",
        "rom_sha256": digest(args.rom.read_bytes()),
        "instruction_runtime": json.loads(
            LAYOUT.read_text(encoding="ascii")
        )["instruction_runtime"],
        "scenarios": results,
    }, indent=2) + "\n", encoding="ascii")
    print(
        "BUG-011 runtime: both starting-owner orders passed 48 colour transitions, "
        "16 consumes, 15 death/angel surfaces, exact helper identity, "
        "level-start handoff, and reset-free return to attract"
    )


if __name__ == "__main__":
    main()
