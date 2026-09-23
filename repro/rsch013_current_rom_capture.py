#!/usr/bin/env python3
"""Bounded read-only current-ROM capture for BUG-045 demo routing."""
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import verify_bug011_runtime as runtime
import verify_bug009_monitor_input as monitor

BUILD = ROOT / "build"
OUT = ROOT / "repro/rsch013-current-rom-demo.json"
DEADLINE = 60.0


def main():
    rom = BUILD / "ladybug.rom"
    process, client = runtime.launch_fast(monitor, ROOT / "docs/reference/xroar/src/xroar", rom)
    evidence = {"rom_sha256": hashlib.sha256(rom.read_bytes()).hexdigest(),
                "phase": "natural demo action 9–15", "deadline_seconds": DEADLINE,
                "timeout_meaning": "target action not observed within bounded probe", "actions": []}
    started = time.monotonic()
    try:
        syms = runtime.symbols(BUILD / "ladybug-presentation-runtime.map")
        start = syms["start_screen"]
        demo = syms["demo_run"]
        ids = monitor.setup(client, [start, demo])
        while time.monotonic() - started < DEADLINE:
            hit = client.run_to_breakpoint(min(15, max(1, DEADLINE - (time.monotonic() - started))))
            if hit["pc"] == demo:
                break
        else:
            raise RuntimeError("demo entry deadline")
        monitor.clear(client, ids)
        authored = (BUILD / "ladybug-presentation-runtime.bin").read_bytes()
        auxiliary = (BUILD / "ladybug-demo-runtime.bin").read_bytes()
        live_auxiliary = runtime.read_bytes(client, 0x0300, len(auxiliary))
        evidence["identity"] = {
            "presentation": runtime.read_bytes(client, 0x1900, len(authored)) == authored,
            "auxiliary": live_auxiliary == auxiliary,
            "auxiliary_live_prefix": live_auxiliary[:16].hex(),
            "auxiliary_expected_prefix": auxiliary[:16].hex(),
        }
        if not evidence["identity"]["presentation"] or not evidence["identity"]["auxiliary"]:
            raise RuntimeError("live artifact identity mismatch")
        main_syms = runtime.symbols(BUILD / "ladybug.map")
        tick_address = main_syms["player_tick"]
        tick_id = monitor.setup(client, [tick_address])[0]
        last = -1
        calls = 0
        while time.monotonic() - started < DEADLINE and calls < 2500:
            client.run_to_breakpoint(min(10, max(1, DEADLINE - (time.monotonic() - started))))
            calls += 1
            data = runtime.read_bytes(client, 0, 0xDE)
            route = data[0xDA]
            if route != last and route >= 8:
                evidence["actions"].append({"route_index": route, "cell": [data[9], data[10]],
                    "step": data[8], "direction": data[0xDD], "front": data[0x8F],
                    "frame_sha256": hashlib.sha256(runtime.read_owner(client, data[0x8F])).hexdigest()})
            last = route
            if route >= 16:
                evidence["success_marker"] = "action 15 selected"
                break
        monitor.clear(client, [tick_id])
        evidence["calls"] = calls
        evidence["elapsed_seconds"] = round(time.monotonic() - started, 3)
        evidence.setdefault("success_marker", "not reached")
    except Exception as exc:
        evidence["failure"] = f"{type(exc).__name__}: {exc}"
    finally:
        client.close()
        monitor.stop(process)
        OUT.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
