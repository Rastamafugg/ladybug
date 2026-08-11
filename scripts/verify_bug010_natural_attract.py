#!/usr/bin/env python3
"""Capture the natural BUG-010 558-tick attract phase through XRoar monitor."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MONITOR_INPUT = ROOT / "scripts/verify_bug009_monitor_input.py"
ROM = ROOT / "build/ladybug.rom"
EVIDENCE = ROOT / "build/bug010-natural-attract-evidence.json"
MODULE = ROOT / "build/ladybug-presentation-runtime.bin"
LAYOUT = ROOT / "build/ladybug-sparse-layout.json"

PUBLISH = 0x0DD5
ATTRACT_TICK = 0x1BA4
ATTRACT_NEXT = 0x1BC3
FB_FRONT = 0x008F
FB_BACK = 0x0090
FB_PENDING = 0x0091
PRES_MODE = 0x00A5
PRES_TIMER = 0x00B0
PRES_PHASE = 0x00CA
PRES_ACTOR_PHASE = 0x00D3
PRES_HOLD_STATE = 0x00D4
PRES_HOLD_OWNER = 0x00D9
TARGET_TICKS = 558
HARD_MAX_CYCLES = 29666
ENGINEERING_TARGET = 27000


def load_monitor_module():
    spec = importlib.util.spec_from_file_location("bug009_monitor", MONITOR_INPUT)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load monitor client")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_bytes(client, address: int, length: int) -> bytes:
    return bytes.fromhex(
        client.call("read_memory", {"addr": address, "length": length})["data"]
    )


def read_byte(client, address: int) -> int:
    return read_bytes(client, address, 1)[0]


def read_state(client) -> dict[str, int]:
    timer = read_bytes(client, PRES_TIMER, 2)
    return {
        "timer": int.from_bytes(timer, "big"),
        "phase": read_byte(client, PRES_PHASE),
        "actor_phase": read_byte(client, PRES_ACTOR_PHASE),
        "hold_state": read_byte(client, PRES_HOLD_STATE),
        "hold_owner": read_byte(client, PRES_HOLD_OWNER),
        "mode": read_byte(client, PRES_MODE),
        "front": read_byte(client, FB_FRONT),
        "back": read_byte(client, FB_BACK),
        "pending": read_byte(client, FB_PENDING),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--xroar", type=Path, required=True)
    parser.add_argument("--rom", type=Path, default=ROM)
    parser.add_argument("--output", type=Path, default=EVIDENCE)
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()

    monitor = load_monitor_module()
    process, client = monitor.launch(args.xroar, args.rom, monitor.free_port())
    try:
        publish_id = monitor.setup(client, [PUBLISH])[0]
        initial_hit = client.run_to_breakpoint(args.timeout)
        initial_cycles = client.call("read_cycles")
        monitor.clear(client, [publish_id])

        attract_id, handoff_id = monitor.setup(client, [ATTRACT_TICK, ATTRACT_NEXT])
        ticks: list[dict] = []
        failure = None
        handoff = None
        for index in range(TARGET_TICKS + 2):
            try:
                hit = client.run_to_breakpoint(args.timeout)
            except Exception as exc:
                failure = {
                    "tick_index": index,
                    "error": type(exc).__name__,
                    "deadline_seconds": args.timeout,
                }
                break
            if hit.get("pc") == ATTRACT_NEXT:
                handoff = hit
                break
            if hit.get("pc") != ATTRACT_TICK:
                failure = {
                    "tick_index": index,
                    "error": "unexpected_natural_breakpoint",
                    "observed_pc": hit.get("pc"),
                    "deadline_seconds": args.timeout,
                }
                break
            cycles = client.call("read_cycles")
            ticks.append({
                "index": index,
                "pc": hit.get("pc"),
                "cpu_cycles": cycles["cpu_cycles"],
                "event_ticks": cycles["event_ticks"],
                "state": read_state(client),
            })

        module = MODULE.read_bytes()
        module_sha256 = hashlib.sha256(module).hexdigest()
        staged_module_sha256 = json.loads(
            LAYOUT.read_text(encoding="ascii")
        )["presentation_module"]["sha256"]
        live_module_sha256 = hashlib.sha256(
            read_bytes(client, 0x1900, len(module))
        ).hexdigest()
        if len({module_sha256, staged_module_sha256, live_module_sha256}) != 1:
            failure = failure or {
                "error": "presentation_module_identity_mismatch",
                "deadline_seconds": args.timeout,
            }

        deltas = [
            ticks[index]["cpu_cycles"] - ticks[index - 1]["cpu_cycles"]
            for index in range(1, len(ticks))
        ]
        phase_change_worklists = [
            {
                "tick_index": index,
                "timer": ticks[index]["state"]["timer"],
                "from_phase": ticks[index - 1]["state"]["actor_phase"],
                "to_phase": ticks[index]["state"]["actor_phase"],
                "cycles": ticks[index]["cpu_cycles"] - ticks[index - 1]["cpu_cycles"],
            }
            for index in range(1, len(ticks))
            if ticks[index]["state"]["actor_phase"] !=
            ticks[index - 1]["state"]["actor_phase"]
        ]
        if failure is None and handoff is None:
            handoff = client.run_to_breakpoint(args.timeout)
        monitor.clear(client, [attract_id, handoff_id])
        if failure is None and handoff.get("pc") != ATTRACT_NEXT:
            failure = {
                "error": "final_branch_did_not_reach_attract_next",
                "observed_pc": handoff.get("pc"),
                "deadline_seconds": args.timeout,
            }

        result = {
            "schema": "ladybug-bug010-natural-attract-evidence-v3",
            "rom_sha256": hashlib.sha256(args.rom.read_bytes()).hexdigest(),
            "xroar_sha256": hashlib.sha256(args.xroar.read_bytes()).hexdigest(),
            "presentation_module_identity": {
                "bytes": len(module),
                "authored_sha256": module_sha256,
                "staged_sha256": staged_module_sha256,
                "live_sha256": live_module_sha256,
                "match": len({module_sha256, staged_module_sha256, live_module_sha256}) == 1,
            },
            "deadline_seconds": args.timeout,
            "target_ticks": TARGET_TICKS,
            "initial_publication": {
                "pc": initial_hit.get("pc"),
                "cpu_cycles": initial_cycles["cpu_cycles"],
                "event_ticks": initial_cycles["event_ticks"],
            },
            "ticks": ticks,
            "handoff": handoff,
            "failure": failure,
            "cycle_deltas": deltas,
            "cycle_max": max(deltas) if deltas else None,
            "cycle_min": min(deltas) if deltas else None,
            "phase_change_worklists": phase_change_worklists,
            "phase_change_cycle_max": max(
                (entry["cycles"] for entry in phase_change_worklists), default=None
            ),
            "hardware_frame_max_cycles": HARD_MAX_CYCLES,
            "engineering_target_cycles": ENGINEERING_TARGET,
            "natural_558_tick_completion": failure is None and len(ticks) == TARGET_TICKS and handoff is not None,
            "cycle_hardware_target_pass": bool(deltas) and max(deltas) <= HARD_MAX_CYCLES,
            "cycle_engineering_target_pass": bool(deltas) and max(deltas) <= ENGINEERING_TARGET,
            "phase_change_hardware_target_pass": bool(phase_change_worklists) and max(
                entry["cycles"] for entry in phase_change_worklists
            ) <= HARD_MAX_CYCLES,
            "phase_change_engineering_target_pass": bool(phase_change_worklists) and max(
                entry["cycles"] for entry in phase_change_worklists
            ) <= ENGINEERING_TARGET,
        }
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="ascii")
        if not result["natural_558_tick_completion"]:
            raise SystemExit(f"BUG-010 natural attract failed: {failure or 'handoff missing'}")
        print(
            f"BUG-010 natural attract pass: {TARGET_TICKS} ticks, handoff PC {handoff.get('pc')}, "
            f"cycle range {min(deltas)}-{max(deltas)}, "
            f"phase-change max {result['phase_change_cycle_max']}, evidence={args.output}"
        )
    finally:
        client.close()
        monitor.stop(process)
        process.wait(timeout=2)


if __name__ == "__main__":
    main()
