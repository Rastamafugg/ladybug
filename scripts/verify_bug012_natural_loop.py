#!/usr/bin/env python3
"""Capture the natural BUG-012 release loop through the XRoar monitor."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MONITOR_INPUT = ROOT / "scripts/verify_bug009_monitor_input.py"
MODULE_MAP = ROOT / "build/ladybug-presentation-runtime.map"
MAIN_MAP = ROOT / "build/ladybug.map"
MODULE = ROOT / "build/ladybug-presentation-runtime.bin"
AUXILIARY = ROOT / "build/ladybug-instruction-runtime.bin"
LAYOUT = ROOT / "build/ladybug-sparse-layout.json"
PRESENTATION = ROOT / "build/ladybug-presentation.json"
PRES_SCREEN = 0x00A6
PRES_MODE = 0x00A5
PRES_ROUTE = 0x00DA
PRES_DEMO_DIR = 0x00DD
PRES_TIMER = 0x00B0
DEATH = 0x004D
PLAYER_STEP = 0x0008
PLAYER_DIR = 0x0006
PLAYER_CELL_X = 0x0009
PLAYER_CELL_Y = 0x000A
PLAYER_WANT = 0x000F
PLAYER_MANUAL = 0x0018
JOY_DIR = 0x0005
FB_START = 0x2000
FB_BYTES = 0x7800


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


def register(client, name: str) -> int:
    registers = client.call("read_registers")
    value = registers.get(name.lower(), registers.get(name.upper()))
    if value is None:
        raise RuntimeError(f"missing register {name}: {registers}")
    return int(value)


def read_bytes(client, address: int, length: int) -> bytes:
    return bytes.fromhex(client.call(
        "read_memory", {"addr": address, "length": length}
    )["data"])


def read_byte(client, address: int) -> int:
    return read_bytes(client, address, 1)[0]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xroar", type=Path, required=True)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--demo-call-limit", type=int, default=1000)
    args = parser.parse_args()

    syms = symbols(MODULE_MAP)
    main_syms = symbols(MAIN_MAP)
    start_screen = syms["start_screen"]
    load_done_publish = syms["load_done_publish"]
    demo_tick = syms["demo_run"]
    manifest = json.loads(PRESENTATION.read_text(encoding="ascii"))
    layout = json.loads(LAYOUT.read_text(encoding="ascii"))
    monitor = load_monitor()
    process, client = monitor.launch(args.xroar, args.rom, monitor.free_port())
    requests: list[dict[str, int]] = []
    try:
        start_id, demo_id = monitor.setup(client, [start_screen, demo_tick])
        entered_demo = False
        for _ in range(12):
            hit = client.run_to_breakpoint(args.timeout)
            if hit.get("pc") == demo_tick:
                entered_demo = True
                monitor.clear(client, [demo_id])
                break
            if hit.get("pc") != start_screen:
                raise SystemExit(f"BUG-012 natural: unexpected breakpoint {hit}")
            requests.append({
                "map": register(client, "a"),
                "mode": read_byte(client, PRES_MODE),
                "screen": read_byte(client, PRES_SCREEN),
            })
        if not entered_demo:
            raise SystemExit(f"BUG-012 natural: demo entry missing; requests={requests}")

        authored_module = MODULE.read_bytes()
        authored_auxiliary = AUXILIARY.read_bytes()
        identities = {
            "module": hashlib.sha256(read_bytes(client, 0x1900, len(authored_module))).hexdigest()
            == hashlib.sha256(authored_module).hexdigest(),
            "auxiliary": hashlib.sha256(read_bytes(client, 0x0300, len(authored_auxiliary))).hexdigest()
            == hashlib.sha256(authored_auxiliary).hexdigest(),
        }
        if not all(identities.values()):
            raise SystemExit(f"BUG-012 natural: live artifact identity mismatch {identities}")

        return_hit = None
        demo_calls = 0
        last_demo_state: dict[str, object] = {}
        demo_samples: list[dict[str, object]] = []
        if args.demo_call_limit == 0:
            return_hit = client.run_to_breakpoint(args.timeout)
        else:
            trace_address = main_syms["player_tick"]
            aux_id = monitor.setup(client, [trace_address])[0]
        for demo_calls in range(1, args.demo_call_limit + 1):
            hit = client.run_to_breakpoint(args.timeout)
            if hit.get("pc") == start_screen:
                return_hit = hit
                break
            if hit.get("pc") != trace_address:
                raise SystemExit(f"BUG-012 natural: unexpected demo breakpoint {hit}")
            direct_page = read_bytes(client, 0, PRES_DEMO_DIR + 1)
            last_demo_state = {
                "death": direct_page[DEATH],
                "route_index": direct_page[PRES_ROUTE],
                "timer": int.from_bytes(direct_page[PRES_TIMER:PRES_TIMER + 2], "big"),
                "player_cell": [direct_page[PLAYER_CELL_X], direct_page[PLAYER_CELL_Y]],
                "player_step": direct_page[PLAYER_STEP],
                "player_dir": direct_page[PLAYER_DIR],
                "player_want": direct_page[PLAYER_WANT],
                "player_manual": direct_page[PLAYER_MANUAL],
                "joy_dir": direct_page[JOY_DIR],
            }
            if len(demo_samples) < 32:
                demo_samples.append({"call": demo_calls, **last_demo_state})
        if args.demo_call_limit:
            monitor.clear(client, [aux_id])
        if return_hit is None:
            raise SystemExit(
                f"BUG-012 natural: no post-demo screen request within {args.demo_call_limit} route ticks; "
                f"samples={demo_samples}"
            )
        if return_hit.get("pc") != start_screen:
            raise SystemExit(f"BUG-012 natural: post-demo screen request missing {return_hit}")
        return_map = register(client, "a")
        death = read_byte(client, DEATH)
        route_index = read_byte(client, PRES_ROUTE)
        if return_map != 0 or death != 4:
            raise SystemExit(
                "BUG-012 natural: demo did not return through natural completed death; "
                f"map={return_map} death={death} route={route_index} last={last_demo_state}"
            )

        monitor.clear(client, [start_id])
        load_id = monitor.setup(client, [load_done_publish])[0]
        publish_hit = client.run_to_breakpoint(args.timeout)
        if publish_hit.get("pc") != load_done_publish or read_byte(client, PRES_SCREEN) != 0:
            raise SystemExit("BUG-012 natural: returned attract publication missing")
        returned_hash = hashlib.sha256(read_bytes(client, FB_START, FB_BYTES)).hexdigest()
        monitor.clear(client, [load_id])

        logical_maps = []
        for item in requests:
            if not logical_maps or logical_maps[-1] != item["map"]:
                logical_maps.append(item["map"])
        if logical_maps[:2] != [0, 2]:
            raise SystemExit(f"BUG-012 natural: unexpected pre-demo maps {logical_maps}")
        evidence = {
            "schema": "ladybug-bug012-natural-loop-v1",
            "rom_sha256": hashlib.sha256(args.rom.read_bytes()).hexdigest(),
            "module_identity": identities,
            "screen_requests": requests,
            "logical_pre_demo_maps": logical_maps,
            "demo_entry": True,
            "natural_death_state": death,
            "route_index_at_return": route_index,
            "demo_runtime_calls": demo_calls,
            "last_demo_state": last_demo_state,
            "return_map": return_map,
            "returned_attract_framebuffer_sha256": returned_hash,
            "route_source_sha256": manifest["demo_route"]["source_sha256"],
            "gmc_spare_bytes": layout["gmc"]["spare_bytes"],
            "phase_deadline_seconds": args.timeout,
        }
        args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="ascii")
        print(
            "BUG-012 natural loop pass: logical maps 0,2,demo,0; "
            f"natural death=4 route_index={route_index}; evidence={args.output}"
        )
    finally:
        client.close()
        monitor.stop(process)
        process.wait(timeout=2)


if __name__ == "__main__":
    main()
