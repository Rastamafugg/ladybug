#!/usr/bin/env python3
"""Retain BUG-010's controlled natural-sequence loop-return evidence."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MONITOR_PATH = ROOT / "scripts/verify_bug009_monitor_input.py"
MODULE_MAP = ROOT / "build/ladybug-presentation-runtime.map"
HELPER_MAP = ROOT / "build/ladybug-perimeter-reset-helper.map"
MANIFEST = ROOT / "build/ladybug-presentation.json"
MODULE = ROOT / "build/ladybug-presentation-runtime.bin"
HELPER = ROOT / "build/ladybug-perimeter-reset-helper.bin"
MODULE_ADDRESS = 0x1900
HELPER_ADDRESS = 0x06B2
PAR1 = 0xFFA1
FB_FRONT = 0x008F
PENDING = 0x0091
PRES_MODE = 0x00A5
PRES_SCREEN = 0x00A6
PRES_EVENT = 0x00A9
PRES_TIMER = 0x00B0
PRES_ACTOR_PHASE = 0x00D3
PRES_HOLD_STATE = 0x00D4
DEATH = 0x004D
VISIBLE_BYTES = 30720
MODE_ATTRACT = 2
MODE_NAME = 8
MAP_SEQUENCE = (0, 1, 2, 4, 5, 0)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def symbol(path: Path, name: str) -> int:
    match = re.search(
        rf"^Symbol: {re.escape(name)} .* = ([0-9A-Fa-f]+)$",
        path.read_text(encoding="utf-8"), re.MULTILINE,
    )
    if not match:
        raise SystemExit(f"BUG-010 loop return: missing symbol {name} in {path}")
    return int(match.group(1), 16)


def load_monitor():
    spec = importlib.util.spec_from_file_location("bug009_monitor", MONITOR_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load monitor client")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_bytes(client, address: int, length: int) -> bytes:
    return bytes.fromhex(client.call("read_memory", {
        "addr": address, "length": length,
    })["data"])


def read_byte(client, address: int) -> int:
    return read_bytes(client, address, 1)[0]


def read_word(client, address: int) -> int:
    return int.from_bytes(read_bytes(client, address, 2), "big")


def read_owner(client, owner: int) -> bytes:
    saved = [read_byte(client, PAR1 + index) for index in range(4)]
    base = 0x30 if owner == 0 else 0x2C
    output = bytearray()
    try:
        for index in range(4):
            client.call("write_memory", {
                "addr": PAR1 + index, "data": f"{base + index:02x}",
            })
            count = min(0x2000, VISIBLE_BYTES - len(output))
            output.extend(read_bytes(client, 0x2000 + index * 0x2000, count))
    finally:
        for index, page in enumerate(saved):
            client.call("write_memory", {
                "addr": PAR1 + index, "data": f"{page:02x}",
            })
    return bytes(output)


def register(client, name: str) -> int:
    registers = client.call("read_registers")
    value = registers.get(name.lower(), registers.get(name.upper()))
    if value is None:
        raise SystemExit(f"BUG-010 loop return: missing register {name}: {registers}")
    return int(value)


def state(client) -> dict[str, int]:
    return {
        "mode": read_byte(client, PRES_MODE),
        "screen": read_byte(client, PRES_SCREEN),
        "event": read_byte(client, PRES_EVENT),
        "timer": read_word(client, PRES_TIMER),
        "actor_phase": read_byte(client, PRES_ACTOR_PHASE),
        "hold_state": read_byte(client, PRES_HOLD_STATE),
        "front": read_byte(client, FB_FRONT),
        "pending": read_byte(client, PENDING),
        "death": read_byte(client, DEATH),
    }


def marker(client, timeout: float, expected_pc: int, label: str) -> dict:
    hit = client.run_to_breakpoint(timeout)
    if hit.get("pc") != expected_pc:
        raise SystemExit(
            f"BUG-010 loop return: {label} expected PC {expected_pc:04x}, got {hit}"
        )
    return hit


def step_instructions(client, count: int, expected_pc: int, label: str) -> dict:
    client.call("step_instruction", {"n": count})
    stopped = client.call("wait_for_stop", {"timeout_ms": 2000})
    if stopped.get("reason") != "step" or stopped.get("pc") != expected_pc:
        raise SystemExit(
            f"BUG-010 loop return: {label} expected stepped PC {expected_pc:04x}, "
            f"got {stopped}"
        )
    return stopped


def screen_request(client) -> dict[str, object]:
    snapshot = state(client)
    snapshot.update({
        "requested_map": register(client, "a"),
        "cpu_cycles": client.call("read_cycles")["cpu_cycles"],
    })
    return snapshot


def await_screen_map(client, timeout: float, start_screen: int, label: str,
                     expected_map: int, screen_calls: list[dict[str, object]]) -> dict[str, object]:
    for _ in range(4):
        marker(client, timeout, start_screen, label)
        request = screen_request(client)
        if request["requested_map"] == expected_map:
            request["classification"] = "logical_transition"
            screen_calls.append(request)
            print(
                f"BUG010_LOOP_MARKER {label} map={expected_map} "
                f"timer={request['timer']}", flush=True,
            )
            return request
        if (request["requested_map"] == 0 and request["screen"] == 0 and
                request["mode"] == 1 and request["hold_state"] != 0):
            request["classification"] = "internal_attract_owner_hydration"
            screen_calls.append(request)
            continue
        raise SystemExit(f"BUG-010 loop return: {label} map mismatch: {request}")
    raise SystemExit(f"BUG-010 loop return: {label} hidden by repeated hydration calls")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xroar", type=Path, required=True)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--phase-timeout", type=float, default=60.0)
    args = parser.parse_args()

    start_screen = symbol(MODULE_MAP, "start_screen")
    start_screen_map = symbol(MODULE_MAP, "start_screen_map")
    demo_force_death = symbol(MODULE_MAP, "demo_force_death")
    name_tick = symbol(MODULE_MAP, "name_tick")
    phase_change = symbol(HELPER_MAP, "pao_phase_change")
    manifest = json.loads(MANIFEST.read_text(encoding="ascii"))
    expected_phases = manifest["attract_actor_surfaces"]["phase_frame_sha256"]
    expected_name = manifest["static_frame_sha256"][5]
    monitor = load_monitor()
    process, client = monitor.launch(args.xroar, args.rom, monitor.free_port())
    try:
        start_id = monitor.setup(client, [start_screen])[0]
        marker(client, args.phase_timeout, start_screen, "cold attract request")
        cold_request = screen_request(client)
        cold_request["classification"] = "logical_transition"
        requests = [cold_request]
        screen_calls = [cold_request]
        print("BUG010_LOOP_MARKER cold attract request map=0", flush=True)

        authored_module = MODULE.read_bytes()
        authored_helper = HELPER.read_bytes()
        live_module = read_bytes(client, MODULE_ADDRESS, len(authored_module))
        live_helper = read_bytes(client, HELPER_ADDRESS, len(authored_helper))
        identity = {
            "module": {
                "bytes": len(authored_module),
                "authored_sha256": digest(authored_module),
                "live_sha256": digest(live_module),
                "match": authored_module == live_module,
            },
            "helper": {
                "bytes": len(authored_helper),
                "authored_sha256": digest(authored_helper),
                "live_sha256": digest(live_helper),
                "match": authored_helper == live_helper,
            },
        }
        if not identity["module"]["match"] or not identity["helper"]["match"]:
            raise SystemExit(f"BUG-010 loop return: live code identity failed: {identity}")

        for label, expected_map in (("instructions request", 1), ("level request", 2)):
            request = await_screen_map(
                client, args.phase_timeout, start_screen, label, expected_map, screen_calls
            )
            requests.append(request)

        demo_id = monitor.setup(client, [demo_force_death])[0]
        marker(client, args.phase_timeout, demo_force_death, "natural demo death")
        demo_death = state(client)
        demo_death["cpu_cycles"] = client.call("read_cycles")["cpu_cycles"]
        monitor.clear(client, [demo_id])
        print(
            f"BUG010_LOOP_MARKER natural demo death timer={demo_death['timer']}",
            flush=True,
        )
        if demo_death["timer"] != 180 or demo_death["death"] != 0:
            raise SystemExit(f"BUG-010 loop return: demo death boundary mismatch: {demo_death}")

        for label, expected_map in (("game-over request", 4), ("name request", 5)):
            request = await_screen_map(
                client, args.phase_timeout, start_screen, label, expected_map, screen_calls
            )
            requests.append(request)

        name_id = monitor.setup(client, [name_tick])[0]
        marker(client, args.phase_timeout, name_tick, "published name screen")
        name_before = state(client)
        name_frame = read_owner(client, name_before["front"])
        name_before["frame_sha256"] = digest(name_frame)
        name_before["expected_sha256"] = expected_name
        name_before["match"] = name_before["frame_sha256"] == expected_name
        print(
            f"BUG010_LOOP_MARKER published name screen match={name_before['match']}",
            flush=True,
        )
        if name_before["mode"] != MODE_NAME or not name_before["match"]:
            raise SystemExit(f"BUG-010 loop return: name screen mismatch: {name_before}")

        client.call("inject_key", {"key": 1, "action": "press"})
        marker(client, args.phase_timeout, name_tick, "name-screen Player 1 edge")
        name_edge = state(client)
        print(
            f"BUG010_LOOP_MARKER name-screen Player 1 edge event={name_edge['event']}",
            flush=True,
        )
        if not name_edge["event"] & 1:
            raise SystemExit(f"BUG-010 loop return: Player 1 edge missing: {name_edge}")
        monitor.clear(client, [name_id])
        monitor.clear(client, [start_id])
        step_instructions(client, 5, start_screen, "name edge to start_screen")
        step_instructions(client, 13, start_screen_map, "start_screen to map setup")
        returned_request = state(client)
        returned_request.update({
            "requested_map": returned_request["screen"],
            "cpu_cycles": client.call("read_cycles")["cpu_cycles"],
            "classification": "logical_transition",
            "observation_pc": start_screen_map,
        })
        print(
            f"BUG010_LOOP_MARKER returned attract request "
            f"map={returned_request['requested_map']} timer={returned_request['timer']}",
            flush=True,
        )
        screen_calls.append(returned_request)
        requests.append(returned_request)
        client.call("inject_key", {"key": 1, "action": "release"})
        actual_maps = tuple(int(item["requested_map"]) for item in requests)
        if actual_maps != MAP_SEQUENCE:
            raise SystemExit(
                f"BUG-010 loop return: screen sequence {actual_maps}, expected {MAP_SEQUENCE}"
            )
        if requests[1]["timer"] != 558 or requests[2]["timer"] != 192:
            raise SystemExit(f"BUG-010 loop return: attract/instructions deadlines differ: {requests}")
        if requests[4]["timer"] != 180:
            raise SystemExit(f"BUG-010 loop return: game-over deadline differs: {requests[4]}")
        if (name_edge["mode"] != MODE_NAME or requests[5]["mode"] != 1 or
                requests[5]["screen"] != 0 or not requests[5]["event"] & 1):
            raise SystemExit(
                f"BUG-010 loop return: return was not caused by name edge: "
                f"edge={name_edge} request={requests[5]}"
            )

        phase_id = monitor.setup(client, [phase_change])[0]
        returned_phases: dict[int, dict[str, object]] = {}
        phase_hits = 0
        while set(returned_phases) != set(range(4)):
            marker(client, args.phase_timeout, phase_change, "returned attract phase change")
            phase_hits += 1
            snapshot = state(client)
            old_phase = snapshot["actor_phase"]
            if (snapshot["hold_state"] == 0 and old_phase in range(4) and
                    old_phase not in returned_phases):
                frame = read_owner(client, snapshot["front"])
                frame_hash = digest(frame)
                returned_phases[old_phase] = {
                    "state": snapshot,
                    "frame_sha256": frame_hash,
                    "expected_sha256": expected_phases[old_phase],
                    "match": frame_hash == expected_phases[old_phase],
                    "cpu_cycles": client.call("read_cycles")["cpu_cycles"],
                }
                print(
                    f"BUG010_LOOP_MARKER returned phase={old_phase} "
                    f"match={returned_phases[old_phase]['match']}", flush=True,
                )
            if phase_hits > 16:
                raise SystemExit(
                    f"BUG-010 loop return: four returned phases not observed: {returned_phases}"
                )
        monitor.clear(client, [phase_id])

        result = {
            "schema": "ladybug-bug010-loop-return-v1",
            "revision": args.revision,
            "rom_sha256": digest(args.rom.read_bytes()),
            "phase_deadline_seconds": args.phase_timeout,
            "timeout_meaning": (
                "The named runtime marker was not reached within the probe boundary; "
                "a timeout is not a target-code cycle measurement."
            ),
            "control_writes": [
                {"at": "published name screen", "key": 1, "action": "press"},
                {"at": "returned attract request", "key": 1, "action": "release"},
            ],
            "state_acceleration_writes": [],
            "probe_adjustments": [
                "Internal attract owner hydration calls are classified separately from logical screen transitions.",
                "The monitor intermittently missed fresh breakpoints after the name edge; bounded forward stepping proves name_tick to start_screen to start_screen_map instead.",
                "Revision identity is supplied explicitly because WSL Git cannot resolve this Windows worktree pointer.",
            ],
            "identity": identity,
            "screen_requests": requests,
            "all_start_screen_calls": screen_calls,
            "expected_map_sequence": list(MAP_SEQUENCE),
            "demo_death": demo_death,
            "name_screen": name_before,
            "name_edge": name_edge,
            "returned_phase_hits": phase_hits,
            "returned_phases": {
                str(key): value for key, value in sorted(returned_phases.items())
            },
            "pass": (
                actual_maps == MAP_SEQUENCE and
                identity["module"]["match"] and identity["helper"]["match"] and
                name_before["match"] and name_edge["event"] & 1 and
                set(returned_phases) == set(range(4)) and
                all(item["match"] for item in returned_phases.values())
            ),
        }
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="ascii")
        if not result["pass"]:
            raise SystemExit(f"BUG-010 loop return failed: {result}")
        print(
            "BUG-010 loop return pass: natural maps 0,1,2,4,5,0; built-in demo "
            f"death at tick 180; name-screen Player 1 edge; {phase_hits} returned "
            "phase-change hits; all four physical phase hashes exact"
        )
    finally:
        client.close()
        monitor.stop(process)
        process.wait(timeout=2)


if __name__ == "__main__":
    main()
