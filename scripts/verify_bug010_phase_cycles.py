#!/usr/bin/env python3
"""Measure natural BUG-010 phase-changing actor worklists."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MONITOR_PATH = ROOT / "scripts/verify_bug009_monitor_input.py"
HELPER = ROOT / "build/ladybug-perimeter-reset-helper.bin"
HELPER_MAP = ROOT / "build/ladybug-perimeter-reset-helper.map"
MODULE_MAP = ROOT / "build/ladybug-presentation-runtime.map"
MANIFEST = ROOT / "build/ladybug-presentation.json"
FB_FRONT = 0x008F
PAR1 = 0xFFA1
PRES_TIMER = 0x00B0
PRES_ACTOR_PHASE = 0x00D3
PRES_HOLD_STATE = 0x00D4
HARDWARE_CEILING = 29666
ENGINEERING_TARGET = 27000


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def symbol(path: Path, name: str) -> int:
    match = re.search(
        rf"^Symbol: {re.escape(name)} .* = ([0-9A-Fa-f]+)$",
        path.read_text(encoding="utf-8"), re.MULTILINE,
    )
    if not match:
        raise SystemExit(f"BUG-010 phase cycles: missing symbol {name} in {path}")
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


def read_owner(client, owner: int) -> bytes:
    saved = [read_bytes(client, PAR1 + index, 1)[0] for index in range(4)]
    base = 0x30 if owner == 0 else 0x2C
    output = bytearray()
    try:
        for index in range(4):
            client.call("write_memory", {
                "addr": PAR1 + index, "data": f"{base + index:02x}",
            })
            count = min(0x2000, 30720 - len(output))
            output.extend(read_bytes(client, 0x2000 + index * 0x2000, count))
    finally:
        for index, page in enumerate(saved):
            client.call("write_memory", {
                "addr": PAR1 + index, "data": f"{page:02x}",
            })
    return bytes(output)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xroar", type=Path, required=True)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()

    phase_change = symbol(HELPER_MAP, "pao_phase_change")
    attract_next = symbol(MODULE_MAP, "attract_next")
    monitor = load_monitor()
    expected_phases = json.loads(MANIFEST.read_text(encoding="ascii"))[
        "attract_actor_surfaces"
    ]["phase_frame_sha256"]
    process, client = monitor.launch(args.xroar, args.rom, monitor.free_port())
    try:
        phase_id, handoff_id = monitor.setup(client, [phase_change, attract_next])
        measurements = []
        visible_phases: dict[int, dict[str, object]] = {}
        handoff = None
        while True:
            hit = client.run_to_breakpoint(args.timeout)
            if hit.get("pc") == attract_next:
                handoff = hit
                break
            if hit.get("pc") != phase_change:
                raise SystemExit(f"BUG-010 phase cycles: unexpected breakpoint {hit}")
            start = client.call("read_cycles")["cpu_cycles"]
            before = read_bytes(client, PRES_TIMER, 2)
            old_phase = read_bytes(client, PRES_ACTOR_PHASE, 1)[0]
            hold_state = read_bytes(client, PRES_HOLD_STATE, 1)[0]
            if hold_state == 0 and old_phase in range(4) and old_phase not in visible_phases:
                front = read_bytes(client, FB_FRONT, 1)[0]
                frame_hash = digest(read_owner(client, front))
                visible_phases[old_phase] = {
                    "timer": int.from_bytes(before, "big"),
                    "front": front,
                    "frame_sha256": frame_hash,
                    "expected_sha256": expected_phases[old_phase],
                    "match": frame_hash == expected_phases[old_phase],
                }
            registers = client.call("read_registers")
            stack = registers.get("s", registers.get("S"))
            if stack is None:
                raise SystemExit(f"BUG-010 phase cycles: missing S register {registers}")
            return_address = int.from_bytes(read_bytes(client, int(stack), 2), "big")
            monitor.clear(client, [phase_id])
            done_id = monitor.setup(client, [return_address])[0]
            done = client.run_to_breakpoint(args.timeout)
            end = client.call("read_cycles")["cpu_cycles"]
            monitor.clear(client, [done_id])
            if done.get("pc") != return_address:
                raise SystemExit(f"BUG-010 phase cycles: phase did not return {done}")
            phase_id = monitor.setup(client, [phase_change])[0]
            new_phase = read_bytes(client, PRES_ACTOR_PHASE, 1)[0]
            measurements.append({
                "timer": int.from_bytes(before, "big"),
                "hold_state": hold_state,
                "old_phase": old_phase,
                "new_phase": new_phase,
                "return_address": return_address,
                "cycles": end - start,
            })
        monitor.clear(client, [phase_id, handoff_id])

        helper = HELPER.read_bytes()
        live_helper = read_bytes(client, 0x06B2, len(helper))
        maximum = max(item["cycles"] for item in measurements)
        result = {
            "schema": "ladybug-bug010-phase-cycles-v1",
            "deadline_seconds": args.timeout,
            "rom_sha256": digest(args.rom.read_bytes()),
            "helper": {
                "bytes": len(helper),
                "authored_sha256": digest(helper),
                "live_sha256": digest(live_helper),
                "match": helper == live_helper,
            },
            "handoff": handoff,
            "measurements": measurements,
            "visible_phases": {str(key): value for key, value in sorted(visible_phases.items())},
            "measurement_count": len(measurements),
            "cycle_min": min(item["cycles"] for item in measurements),
            "cycle_max": maximum,
            "hardware_ceiling_cycles": HARDWARE_CEILING,
            "engineering_target_cycles": ENGINEERING_TARGET,
            "hardware_pass": maximum <= HARDWARE_CEILING,
            "engineering_pass": maximum <= ENGINEERING_TARGET,
            "pass": (helper == live_helper and maximum <= ENGINEERING_TARGET and
                     set(visible_phases) == set(range(4)) and
                     all(item["match"] for item in visible_phases.values())),
        }
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="ascii")
        if not result["pass"]:
            raise SystemExit(
                f"BUG-010 phase cycles failed: max={maximum}, helper_match={helper == live_helper}"
            )
        print(
            f"BUG-010 phase cycles pass: {len(measurements)} natural worklists, "
            f"range {result['cycle_min']}-{maximum}, ceiling {HARDWARE_CEILING}"
        )
    finally:
        client.close()
        monitor.stop(process)
        process.wait(timeout=2)


if __name__ == "__main__":
    main()
