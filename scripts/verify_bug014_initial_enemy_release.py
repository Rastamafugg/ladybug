#!/usr/bin/env python3
"""Verify BUG-014 dormant startup and timer-owned first enemy release."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import random
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MONITOR_INPUT = ROOT / "scripts/verify_bug009_monitor_input.py"
PRESENTATION_MAP = ROOT / "build/ladybug-presentation-runtime.map"
MAIN_MAP = ROOT / "build/ladybug.map"
ENEMY_MAP = ROOT / "build/ladybug-enemy-runtime.map"
PRESENTATION_SOURCE = ROOT / "src/presentation_runtime.s"
MAIN_SOURCE = ROOT / "src/main.s"

BOX_TIMER = 0x004A
BOX_INDEX = 0x004B
BOX_PHASE = 0x004C
ENEMY_ACTIVE = 0x0058
ENEMY_RELEASED = 0x0059
ENEMY_NEST_DIRTY = 0x0060
RENDER_FLAGS = 0x007F
ENEMY_RENDER_FLAGS = 0x0087
FB_FRONT = 0x008F
FB_BACK = 0x0090
FB_WRITE_FRONT_FAULT = 0x0099
PRES_CREDITS = 0x00A8
FIRST_BOX_ADVANCES = 92
PART_ONE_TICKS_PER_ADVANCE = 9


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


def write_byte(client, address: int, value: int) -> None:
    client.call("write_memory", {"addr": address, "data": f"{value & 0xFF:02x}"})


def register(client, name: str) -> int:
    values = client.call("read_registers")
    value = values.get(name.lower(), values.get(name.upper()))
    if value is None:
        raise RuntimeError(f"missing register {name}: {values}")
    return int(value)


def state(client) -> dict[str, int]:
    return {
        "box_timer": read_byte(client, BOX_TIMER),
        "box_index": read_byte(client, BOX_INDEX),
        "box_phase": read_byte(client, BOX_PHASE),
        "enemy_active": read_byte(client, ENEMY_ACTIVE),
        "enemy_released": read_byte(client, ENEMY_RELEASED),
        "nest_dirty": read_byte(client, ENEMY_NEST_DIRTY),
        "render_flags": read_byte(client, RENDER_FLAGS),
        "enemy_render_flags": read_byte(client, ENEMY_RENDER_FLAGS),
        "fb_front": read_byte(client, FB_FRONT),
        "fb_back": read_byte(client, FB_BACK),
        "front_write_faults": read_byte(client, FB_WRITE_FRONT_FAULT),
    }


def assert_dormant(sample: dict[str, int], label: str) -> None:
    if sample["enemy_active"] != 0 or sample["enemy_released"] != 0:
        raise RuntimeError(f"{label}: enemy activated before timer expiry: {sample}")


def set_breakpoint(client, address: int) -> int:
    return client.call("set_breakpoint", {"addr": address, "kind": "exec"})["id"]


def step_to(client, count: int, expected_pc: int, timeout: float, label: str) -> None:
    client.call("step_instruction", {"n": count})
    stopped = client.call("wait_for_stop", {"timeout_ms": int(timeout * 1000)})
    if stopped.get("reason") != "step" or stopped.get("pc") != expected_pc:
        raise RuntimeError(
            f"{label}: expected stepped PC {expected_pc:04x}, got {stopped}"
        )


def static_contract() -> dict[str, object]:
    source = PRESENTATION_SOURCE.read_text(encoding="utf-8")
    begin = source.index("\ninit_gameplay\n")
    end = source.index("\n        ifeq", begin)
    body = source[begin:end]
    services = [
        "PRES_MAIN_INIT", "PRES_MAIN_MAZE", "PRES_MAIN_GATES",
        "PRES_MAIN_ENTITIES", "PRES_MAIN_PLAYER", "PRES_MAIN_ENEMY",
    ]
    offsets = [body.find(f"jsr     {service}") for service in services]
    if any(offset < 0 for offset in offsets) or offsets != sorted(offsets):
        raise RuntimeError(f"initializer service order mismatch: {list(zip(services, offsets))}")
    reentry = body.find("lbsr    gameplay_reentry")
    if reentry < 0 or reentry > offsets[0]:
        raise RuntimeError("owner-preserving gameplay re-entry does not precede initialization")
    if "jsr     $081B" in body:
        raise RuntimeError("visible initialization restored the cold fixed-owner ABI")
    if "jsr     $0806" in body:
        raise RuntimeError("initializer still owns direct enemy release")
    main = MAIN_SOURCE.read_text(encoding="utf-8")
    timer_begin = main.index("\nperimeter_timer_tick\n")
    timer_end = main.index("\n; The arcade program selects", timer_begin)
    timer_body = main[timer_begin:timer_end]
    if "cmpa    #92" not in timer_body or "lbsr    enemy_release" not in timer_body:
        raise RuntimeError("perimeter timer no longer owns the 92-box release")
    return {
        "initializer_services_in_order": services,
        "owner_preserving_reentry_before_services": True,
        "cold_fixed_owner_abi_absent": True,
        "initializer_has_direct_release": False,
        "timer_release_owner": "perimeter_timer_tick",
        "part_one_ticks_per_advance": PART_ONE_TICKS_PER_ADVANCE,
        "first_release_box_advances": FIRST_BOX_ADVANCES,
        "projected_first_release_ticks": FIRST_BOX_ADVANCES * PART_ONE_TICKS_PER_ADVANCE,
    }


def initialize_navigation(monitor, client, module: dict[str, int], timeout: float,
                          mode: str, initial_owner: int) -> dict[str, object]:
    start_id = set_breakpoint(client, module["start_screen"])
    hit = client.run_to_breakpoint(timeout)
    if hit.get("pc") != module["start_screen"] or register(client, "a") != 0:
        raise RuntimeError(f"{mode}: cold attract request missing: {hit}")
    monitor.clear(client, [start_id])
    write_byte(client, FB_FRONT, initial_owner)
    write_byte(client, FB_BACK, 1 - initial_owner)
    rng = random.Random(0xB014)
    contamination: dict[str, int] = {}
    for name, address in (
        ("box_timer", BOX_TIMER), ("box_index", BOX_INDEX),
        ("box_phase", BOX_PHASE), ("enemy_active", ENEMY_ACTIVE),
        ("enemy_released", ENEMY_RELEASED), ("nest_dirty", ENEMY_NEST_DIRTY),
        ("render_flags", RENDER_FLAGS), ("enemy_render_flags", ENEMY_RENDER_FLAGS),
    ):
        value = rng.randrange(1, 256)
        write_byte(client, address, value)
        contamination[name] = value

    requests = [0]
    if mode == "live":
        attract_id = set_breakpoint(client, module["attract_tick"])
        hit = client.run_to_breakpoint(timeout)
        if hit.get("pc") != module["attract_tick"]:
            raise RuntimeError(f"live: attract input marker missing: {hit}")
        monitor.clear(client, [attract_id])
        client.call("inject_key", {"key": 5, "action": "press"})
        start_id = set_breakpoint(client, module["start_screen"])
        hit = client.run_to_breakpoint(timeout)
        client.call("inject_key", {"key": 5, "action": "release"})
        if hit.get("pc") != module["start_screen"] or register(client, "a") != 3:
            raise RuntimeError(f"live: credit did not request high-score screen: {hit}")
        requests.append(3)
        monitor.clear(client, [start_id])
        credit_id = set_breakpoint(client, module["credit_tick"])
        hit = client.run_to_breakpoint(timeout)
        if hit.get("pc") != module["credit_tick"] or read_byte(client, PRES_CREDITS) != 1:
            raise RuntimeError(f"live: credited screen state missing: {hit}")
        monitor.clear(client, [credit_id])
        client.call("inject_key", {"key": 1, "action": "press"})
        start_id = set_breakpoint(client, module["start_screen"])
        hit = client.run_to_breakpoint(timeout)
        client.call("inject_key", {"key": 1, "action": "release"})
        if hit.get("pc") != module["start_screen"] or register(client, "a") != 2:
            raise RuntimeError(f"live: Player 1 did not request level start: {hit}")
        requests.append(2)
        monitor.clear(client, [start_id])
    return {"screen_requests": requests, "randomized_contamination": contamination}


def startup_case(monitor, binary: Path, rom: Path, timeout: float,
                 mode: str, initial_owner: int) -> dict[str, object]:
    module = symbols(PRESENTATION_MAP)
    main = symbols(MAIN_MAP)
    process, client = monitor.launch(binary, rom, monitor.free_port())
    timer_id = None
    try:
        navigation = initialize_navigation(monitor, client, module, timeout, mode, initial_owner)
        timer_id = set_breakpoint(client, main["perimeter_timer_tick"])
        hit = client.run_to_breakpoint(timeout)
        if hit.get("pc") != main["perimeter_timer_tick"]:
            raise RuntimeError(f"{mode}: first gameplay tick missing: {hit}")
        first = state(client)
        assert_dormant(first, f"{mode} first gameplay tick")
        if (first["box_timer"], first["box_index"], first["box_phase"]) != (9, 0, 0):
            raise RuntimeError(f"{mode}: first timer state mismatch: {first}")
        if not first["render_flags"] & 0x40:
            raise RuntimeError(f"{mode}: full-stage render intent missing: {first}")
        return {"mode": mode, "initial_owner": initial_owner, **navigation,
                "first_gameplay_tick": first}
    finally:
        if timer_id is not None:
            try:
                monitor.clear(client, [timer_id])
            except Exception:
                pass
        client.close()
        monitor.stop(process)
        process.wait(timeout=2)


def release_case(monitor, binary: Path, rom: Path, timeout: float,
                 initial_owner: int) -> dict[str, object]:
    module = symbols(PRESENTATION_MAP)
    main = symbols(MAIN_MAP)
    enemy = symbols(ENEMY_MAP)
    process, client = monitor.launch(binary, rom, monitor.free_port())
    ids: list[int] = []
    try:
        navigation = initialize_navigation(monitor, client, module, timeout, "live", initial_owner)
        draw_id = set_breakpoint(client, main["ptt_draw"])
        ids.append(draw_id)
        advances = 0
        before_expiry = None
        while advances < FIRST_BOX_ADVANCES:
            hit = client.run_to_breakpoint(timeout)
            if hit.get("pc") == main["ptt_draw"]:
                advances += 1
                sample = state(client)
                assert_dormant(sample, f"box advance {advances}")
                if sample["box_index"] != advances - 1 or sample["box_timer"] != 9:
                    raise RuntimeError(f"box advance {advances} timer/index mismatch: {sample}")
                if advances == FIRST_BOX_ADVANCES:
                    before_expiry = sample
                continue
            raise RuntimeError(f"release trace: unexpected marker {hit}")
        monitor.clear(client, [draw_id])
        ids.remove(draw_id)
        step_to(client, 15, main["enemy_release"], timeout, "timer release caller")
        step_to(client, 1, 0x0806, timeout, "enemy release ABI")
        step_to(client, 1, enemy["enemy_release_impl"], timeout, "enemy release implementation")
        step_to(client, 29, enemy["er_done"], timeout, "completed first release")
        after_release = state(client)
        if advances != FIRST_BOX_ADVANCES or before_expiry is None:
            raise RuntimeError(f"release occurred after {advances} box advances")
        if after_release["enemy_active"] != 1 or after_release["enemy_released"] != 1:
            raise RuntimeError(f"first release did not activate exactly one enemy: {after_release}")
        if (after_release["box_timer"], after_release["box_index"],
                after_release["box_phase"]) != (9, 0, 1):
            raise RuntimeError(f"release boundary timer state mismatch: {after_release}")
        if after_release["front_write_faults"] != 0:
            raise RuntimeError(f"FRONT-write fault during release trace: {after_release}")
        return {
            "initial_owner": initial_owner,
            **navigation,
            "box_advances_before_release": advances,
            "immediately_before_expiry": before_expiry,
            "after_first_release": after_release,
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
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / "build/bug014-initial-enemy-release.json",
    )
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()

    monitor = load_monitor()
    startup = [
        startup_case(monitor, args.xroar, args.rom, args.timeout, "demo", 0),
        startup_case(monitor, args.xroar, args.rom, args.timeout, "demo", 1),
        startup_case(monitor, args.xroar, args.rom, args.timeout, "live", 0),
    ]
    releases = [
        release_case(monitor, args.xroar, args.rom, args.timeout, 0),
        release_case(monitor, args.xroar, args.rom, args.timeout, 1),
    ]
    evidence = {
        "schema": "ladybug-bug014-initial-enemy-release-v1",
        "rom_sha256": hashlib.sha256(args.rom.read_bytes()).hexdigest(),
        "phase_deadline_seconds": args.timeout,
        "static_contract": static_contract(),
        "startup_cases": startup,
        "release_cases": releases,
        "runtime_service_trace": "not retained: monitor resume semantics made the probe intrusive",
    }
    args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="ascii")
    print(
        "BUG-014 initial enemy release pass: live/demo dormant startup and "
        "both-owner 92-box timer release"
    )


if __name__ == "__main__":
    main()
