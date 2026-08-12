#!/usr/bin/env python3
"""Complete BUG-011 warm, forced, input, and cycle evidence in XRoar."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import verify_bug011_runtime as runtime


PRES_CONTEXT = 0x00A7
PRES_CREDITS = 0x00A8
PRES_EVENT = 0x00A9
PRES_OUT = 0x00B7
PRES_COLOUR_TIMER = 0x00D0
OWNER_CACHE = (0x00D2, 0x00D3, 0x00D6, 0x00D7)
PLAYER_BG_VALID = 0x006A
HARDWARE_CEILING = 29666
ENGINEERING_TARGET = 27000


def write_word(client, address: int, value: int) -> None:
    client.call("write_memory", {
        "addr": address, "data": value.to_bytes(2, "big").hex(),
    })


def set_breakpoint(client, address: int) -> int:
    return client.call("set_breakpoint", {"addr": address, "kind": "exec"})["id"]


def clear_breakpoint(client, ident: int) -> None:
    client.call("clear_breakpoint", {"id": ident})


def run_to(client, address: int, timeout: float) -> dict[str, object]:
    ident = set_breakpoint(client, address)
    try:
        hit = client.run_to_breakpoint(timeout)
    finally:
        clear_breakpoint(client, ident)
    if hit.get("pc") != address:
        raise SystemExit(f"BUG-011 evidence: expected ${address:04X}, got {hit}")
    return hit


def boot_to_instructions(monitor, binary: Path, rom: Path, timeout: float):
    process, client = runtime.launch_fast(monitor, binary, rom)
    syms = runtime.symbols(runtime.PRESENTATION_MAP)
    run_to(client, syms["instructions_tick"], timeout)
    helper = runtime.HELPER.read_bytes()
    if runtime.read_bytes(client, 0x0300, len(helper)) != helper:
        raise SystemExit("BUG-011 evidence: live helper identity differs")
    return process, client, syms


def execute_instruction(client, return_address: int, timeout: float) -> int:
    start = client.call("read_cycles")["cpu_cycles"]
    run_to(client, return_address, timeout)
    return client.call("read_cycles")["cpu_cycles"] - start


def close(monitor, process, client) -> None:
    try:
        client.close()
    finally:
        runtime.stop(process)
        process.wait(timeout=2)


def trigger_colour(index: int) -> int:
    if index < 5:
        return 2
    if index < 12:
        return 1
    return 3


def initialise_once(client, syms: dict[str, int], timeout: float) -> int:
    cycles = execute_instruction(client, syms["instructions_runtime_return"], timeout)
    run_to(client, syms["instructions_tick"], timeout)
    return cycles


def force_worklist(client, syms: dict[str, int], timeout: float,
                   phase: int, timer_before: int, colour: int,
                   out: int | None = None, colour_timer: int = 2) -> int:
    write_byte = runtime.write_byte
    write_byte(client, runtime.PRES_PHASE, phase)
    write_word(client, runtime.PRES_TIMER, timer_before)
    write_byte(client, runtime.PRES_HIGHLIGHT, colour)
    write_byte(client, PRES_COLOUR_TIMER, colour_timer)
    write_byte(client, PLAYER_BG_VALID, 0)
    for address in OWNER_CACHE:
        write_byte(client, address, 0xFF)
    if out is not None:
        write_word(client, PRES_OUT, out)
    return execute_instruction(client, syms["instructions_runtime_return"], timeout)


def verify_reward(frame: bytes, manifest: dict[str, object], name: str) -> bool:
    choreography = manifest["instruction_choreography"]
    destination = choreography["reward_destinations"][name]
    destinations = (destination, destination + 4, destination + 1280, destination + 1284)
    expected = [runtime.expected_tile(manifest, tile_id)
                for tile_id in choreography["reward_tile_ids"][name]]
    return [runtime.frame_tile(frame, item) for item in destinations] == expected


def forced_capture(monitor, binary: Path, rom: Path, timeout: float,
                   manifest: dict[str, object], index: int) -> dict[str, object]:
    process, client, syms = boot_to_instructions(monitor, binary, rom, timeout)
    try:
        initialise_once(client, syms, timeout)
        event = manifest["instruction_choreography"]["events"][index]
        cycles = force_worklist(
            client, syms, timeout, index, event["consume_tick"] - 1,
            trigger_colour(index),
        )
        if runtime.read_byte(client, runtime.PRES_PHASE) != index + 1:
            raise SystemExit(f"BUG-011 evidence: forced target {index} did not advance")
        owner = runtime.read_byte(client, runtime.FB_BACK)
        frame = runtime.read_owner(client, owner)
        events = manifest["instruction_choreography"]["events"]
        for target_index, target in enumerate(events):
            tile = runtime.frame_tile(frame, target["target_destination"])
            if target_index <= index and any(tile):
                raise SystemExit(
                    f"BUG-011 evidence: forced target {index} left target {target_index} visible"
                )
            if target_index > index and not any(tile):
                raise SystemExit(
                    f"BUG-011 evidence: forced target {index} erased future target {target_index}"
                )
        for hud_index, hud_event in enumerate(events[:index + 1]):
            if not hud_event["hud_destination"]:
                continue
            actual = runtime.frame_tile(frame, hud_event["hud_destination"])
            expected = runtime.expected_tile(manifest, hud_event["hud_tile_id"])
            if actual != expected:
                raise SystemExit(
                    f"BUG-011 evidence: forced target {index} HUD {hud_index} differs"
                )
        if index >= 4 and not verify_reward(frame, manifest, "life"):
            raise SystemExit(f"BUG-011 evidence: target {index} lacks life reward")
        if index >= 11 and not verify_reward(frame, manifest, "coin"):
            raise SystemExit(f"BUG-011 evidence: target {index} lacks coin reward")
        return {
            "event_index": index,
            "name": event["name"],
            "row_boundary": index in (4, 11, 15),
            "timer": runtime.read_word(client, runtime.PRES_TIMER),
            "phase": runtime.read_byte(client, runtime.PRES_PHASE),
            "back_owner": owner,
            "frame_sha256": runtime.digest(frame),
            "target_sha256": runtime.digest(runtime.frame_tile(
                frame, event["target_destination"])),
            "cycles": cycles,
        }
    finally:
        close(monitor, process, client)


def warm_reset(monitor, binary: Path, rom: Path, timeout: float,
               manifest: dict[str, object]) -> dict[str, object]:
    process, client, syms = boot_to_instructions(monitor, binary, rom, timeout)
    try:
        initialise_once(client, syms, timeout)
        event = manifest["instruction_choreography"]["events"][7]
        force_worklist(client, syms, timeout, 7, event["consume_tick"] - 1, 1)
        stale = {
            "timer": runtime.read_word(client, runtime.PRES_TIMER),
            "phase": runtime.read_byte(client, runtime.PRES_PHASE),
            "consumes": runtime.read_byte(client, runtime.TRACE_CONSUMES),
        }
        client.call("reset", {"kind": "soft"})
        run_to(client, syms["instructions_tick"], timeout)
        helper = runtime.HELPER.read_bytes()
        live_helper = runtime.read_bytes(client, 0x0300, len(helper))
        owner = runtime.read_byte(client, runtime.FB_FRONT)
        frame = runtime.read_owner(client, owner)
        expected_hash = manifest["static_frame_sha256"][1]
        if runtime.digest(frame) != expected_hash:
            raise SystemExit("BUG-011 evidence: warm reset static frame differs")
        if runtime.read_word(client, runtime.PRES_TIMER) != 0:
            raise SystemExit("BUG-011 evidence: warm reset timer is not zero")
        if runtime.read_byte(client, runtime.PRES_PHASE) != 0xFF:
            raise SystemExit("BUG-011 evidence: warm reset phase is not cold")
        execute_instruction(client, syms["instructions_runtime_return"], timeout)
        reset_trace = {
            "colours": runtime.read_byte(client, runtime.TRACE_COLOURS),
            "consumes": runtime.read_byte(client, runtime.TRACE_CONSUMES),
            "deaths": runtime.read_byte(client, runtime.TRACE_DEATHS),
        }
        if reset_trace != {"colours": 0, "consumes": 0, "deaths": 0}:
            raise SystemExit(f"BUG-011 evidence: warm reset retained trace {reset_trace}")
        return {
            "kind": "soft",
            "stale_state": stale,
            "reset_timer": 0,
            "reset_phase": 0xFF,
            "static_sha256": runtime.digest(frame),
            "helper_authored_sha256": runtime.digest(helper),
            "helper_live_sha256": runtime.digest(live_helper),
            "helper_match": helper == live_helper,
            "post_initialise_trace": reset_trace,
        }
    finally:
        close(monitor, process, client)


def prepare_boundary(client, syms: dict[str, int], timeout: float,
                     choreography: dict[str, object], boundary: str) -> int:
    initialise_once(client, syms, timeout)
    events = choreography["events"]
    if boundary == "row":
        event = events[4]
        return force_worklist(client, syms, timeout, 4,
                              event["consume_tick"] - 1, 2)
    if boundary == "movement":
        event = events[1]
        return force_worklist(client, syms, timeout, 1,
                              event["motion_tick"] - 1, 2,
                              choreography["anchors"][0])
    if boundary == "death":
        return force_worklist(client, syms, timeout, 16,
                              choreography["death_collision_tick"], 3)
    if boundary == "pause":
        return force_worklist(client, syms, timeout, 16,
                              choreography["angel_tick"] - 1, 3)
    raise ValueError(boundary)


def preemption(monitor, binary: Path, rom: Path, timeout: float,
               manifest: dict[str, object], boundary: str,
               action: str) -> dict[str, object]:
    process, client, syms = boot_to_instructions(monitor, binary, rom, timeout)
    try:
        cycles = prepare_boundary(
            client, syms, timeout, manifest["instruction_choreography"], boundary,
        )
        run_to(client, syms["pft_ready"], timeout)
        before_trace = runtime.read_bytes(client, runtime.TRACE_MAGIC, 6)
        before_timer = runtime.read_word(client, runtime.PRES_TIMER)
        before_phase = runtime.read_byte(client, runtime.PRES_PHASE)
        if action == "credit":
            runtime.write_byte(client, PRES_EVENT, 2)
            expected_screen = 3
            expected_credits = runtime.read_byte(client, PRES_CREDITS) + 1
        else:
            runtime.write_byte(client, PRES_CREDITS, 1)
            runtime.write_byte(client, PRES_EVENT, 1)
            expected_screen = 2
            expected_credits = 0
        run_to(client, syms["presentation_flow_tick"], timeout)
        actual = {
            "screen": runtime.read_byte(client, runtime.PRES_SCREEN),
            "mode": runtime.read_byte(client, runtime.PRES_MODE),
            "credits": runtime.read_byte(client, PRES_CREDITS),
            "timer": runtime.read_word(client, runtime.PRES_TIMER),
            "phase": runtime.read_byte(client, runtime.PRES_PHASE),
            "trace_sha256": runtime.digest(runtime.read_bytes(
                client, runtime.TRACE_MAGIC, 6)),
        }
        if actual["screen"] != expected_screen or actual["mode"] != 1:
            raise SystemExit(
                f"BUG-011 evidence: {boundary} {action} did not pre-empt: {actual}"
            )
        if actual["credits"] != expected_credits:
            raise SystemExit(
                f"BUG-011 evidence: {boundary} {action} credits differ: {actual}"
            )
        if actual["timer"] != before_timer or actual["phase"] != before_phase:
            raise SystemExit(
                f"BUG-011 evidence: {boundary} {action} mutated choreography: {actual}"
            )
        if runtime.read_bytes(client, runtime.TRACE_MAGIC, 6) != before_trace:
            raise SystemExit(
                f"BUG-011 evidence: {boundary} {action} advanced helper trace"
            )
        return {
            "boundary": boundary,
            "action": action,
            "forced_worklist_cycles": cycles,
            "before_timer": before_timer,
            "before_phase": before_phase,
            **actual,
        }
    finally:
        close(monitor, process, client)


def measure_cycle_case(monitor, binary: Path, rom: Path, timeout: float,
                       name: str, phase: int | None = None,
                       timer_before: int = 0, colour: int = 1,
                       out: int | None = None,
                       colour_timer: int = 2) -> dict[str, object]:
    process, client, syms = boot_to_instructions(monitor, binary, rom, timeout)
    try:
        if phase is None:
            cycles = execute_instruction(
                client, syms["instructions_runtime_return"], timeout,
            )
        else:
            initialise_once(client, syms, timeout)
            cycles = force_worklist(
                client, syms, timeout, phase, timer_before, colour, out,
                colour_timer,
            )
        return {
            "name": name,
            "phase": runtime.read_byte(client, runtime.PRES_PHASE),
            "timer": runtime.read_word(client, runtime.PRES_TIMER),
            "cycles": cycles,
        }
    finally:
        close(monitor, process, client)


def worklist_cycle_maximum(monitor, binary: Path, rom: Path,
                           timeout: float, choreography: dict[str, object],
                           forced: list[dict[str, object]],
                           inputs: list[dict[str, object]]) -> dict[str, object]:
    thresholds = (0, 4, 5, 11, 12, 15, 16)
    cases = [
        {"name": f"consume-{item['event_index']}", "phase": item["phase"],
         "timer": item["timer"], "cycles": item["cycles"]}
        for item in forced
    ]
    cases.extend({
        "name": f"preemption-boundary-{item['boundary']}-{item['action']}",
        "phase": item["before_phase"], "timer": item["before_timer"],
        "cycles": item["forced_worklist_cycles"],
    } for item in inputs)
    cases.append(measure_cycle_case(
        monitor, binary, rom, timeout, "initialise",
    ))
    for phase in thresholds:
        cases.append(measure_cycle_case(
            monitor, binary, rom, timeout, f"idle-phase-{phase}",
            phase, 1, trigger_colour(min(phase, 15)), colour_timer=2,
        ))
        cases.append(measure_cycle_case(
            monitor, binary, rom, timeout, f"colour-phase-{phase}",
            phase, 1, trigger_colour(min(phase, 15)), colour_timer=1,
        ))
    largest_death = max(
        range(len(choreography["death_stream_bytes"])),
        key=lambda index: choreography["death_stream_bytes"][index],
    )
    death_timer = (choreography["angel_tick"] if largest_death == 14 else
                   choreography["death_collision_tick"] + 30 +
                   (largest_death - 1) * 5)
    cases.append(measure_cycle_case(
        monitor, binary, rom, timeout,
        f"largest-death-stream-{largest_death}", 16, death_timer - 1, 3,
    ))
    maximum = max(cases, key=lambda item: int(item["cycles"]))
    minimum = min(int(item["cycles"]) for item in cases)
    return {
        "measurement": "branch-complete forced instructions_tick through helper return",
        "coverage": (
            "all 16 consumes; row/movement/death/pause boundary worklists; largest "
            "death stream; persistent-state thresholds; initialise; colour/value; idle"
        ),
        "measurement_count": len(cases),
        "cycle_min": minimum,
        "cycle_max": maximum,
        "measurements": cases,
        "terminal_complete_source_bound_cycles": 62,
        "terminal_complete_bound_basis": (
            "static 6809 instruction sum from instructions_tick through the taken "
            "irt_complete return; below the measured maximum"
        ),
        "hardware_ceiling_cycles": HARDWARE_CEILING,
        "engineering_target_cycles": ENGINEERING_TARGET,
        "hardware_margin_cycles": HARDWARE_CEILING - int(maximum["cycles"]),
        "engineering_margin_cycles": ENGINEERING_TARGET - int(maximum["cycles"]),
        "gating": "non-gating PERF-005 input",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xroar", type=Path, required=True)
    parser.add_argument("--rom", type=Path, default=runtime.ROOT / "build/ladybug.rom")
    parser.add_argument("--output", type=Path,
                        default=runtime.ROOT / "build/bug011-evidence.json")
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()
    monitor = runtime.load_monitor()
    manifest = json.loads(runtime.MANIFEST.read_text(encoding="ascii"))
    forced = [
        forced_capture(monitor, args.xroar, args.rom, args.timeout, manifest, index)
        for index in range(16)
    ]
    inputs = [
        preemption(monitor, args.xroar, args.rom, args.timeout,
                   manifest, boundary, action)
        for boundary in ("row", "movement", "death", "pause")
        for action in ("credit", "start")
    ]
    result = {
        "schema": "ladybug-bug011-evidence-v1",
        "deadline_seconds": args.timeout,
        "rom_sha256": runtime.digest(args.rom.read_bytes()),
        "warm_reset": warm_reset(
            monitor, args.xroar, args.rom, args.timeout, manifest,
        ),
        "forced_target_captures": forced,
        "input_preemption": inputs,
        "worklist_cycles": worklist_cycle_maximum(
            monitor, args.xroar, args.rom, args.timeout,
            manifest["instruction_choreography"], forced, inputs,
        ),
        "pass": True,
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="ascii")
    print(
        "BUG-011 evidence pass: warm reset, 16 independent target captures, "
        "8 boundary input scenarios, and a branch-complete worklist maximum"
    )


if __name__ == "__main__":
    main()
