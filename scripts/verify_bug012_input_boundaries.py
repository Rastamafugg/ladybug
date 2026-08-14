#!/usr/bin/env python3
"""Verify BUG-012 credit/start pre-emption and demo input ownership."""

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
AUXILIARY_MAP = ROOT / "build/ladybug-instruction-runtime.map"
PRES_MODE = 0x00A5
PRES_CONTEXT = 0x00A7
PRES_CREDITS = 0x00A8
PRES_DEMO_DIR = 0x00DD
DEATH_STATE = 0x004D
FB_PENDING = 0x0091
JOY_DIR = 0x0005
PLAYER_WANT = 0x000F


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


def read_byte(client, address: int) -> int:
    result = client.call("read_memory", {"addr": address, "length": 1})
    return bytes.fromhex(result["data"])[0]


def write_byte(client, address: int, value: int) -> None:
    client.call("write_memory", {"addr": address, "data": f"{value:02x}"})


def reach(client, address: int, timeout: float) -> int:
    ident = client.call("set_breakpoint", {"addr": address, "kind": "exec"})["id"]
    hit = client.run_to_breakpoint(timeout)
    if hit.get("pc") != address:
        raise RuntimeError(f"target marker {address:04x} missing: {hit}")
    return ident


def input_case(monitor, binary: Path, rom: Path, timeout: float,
               module_syms: dict[str, int], boundary: str, key: int,
               expected_map: int, pending: bool = False) -> dict[str, object]:
    process, client = monitor.launch(binary, rom, monitor.free_port())
    ids: list[int] = []
    try:
        if boundary == "death":
            demo_id = reach(client, module_syms["demo_run"], timeout)
            ids.append(demo_id)
            write_byte(client, DEATH_STATE, 1)
            monitor.clear(client, [demo_id])
            ids.remove(demo_id)
            target = module_syms["demo_death_tick"]
        else:
            target = module_syms[{"attract": "attract_tick", "level": "level_tick"}.get(
                boundary, "demo_run"
            )]
        target_id = reach(client, target, timeout)
        ids.append(target_id)
        mode_at_injection = read_byte(client, PRES_MODE)
        if key == 1:
            write_byte(client, PRES_CREDITS, 1)
        if pending:
            write_byte(client, FB_PENDING, 1)
        client.call("inject_key", {"key": key, "action": "press"})
        monitor.clear(client, [target_id])
        ids.remove(target_id)
        start_id = client.call("set_breakpoint", {
            "addr": module_syms["start_screen"], "kind": "exec",
        })["id"]
        ids.append(start_id)
        hit = client.run_to_breakpoint(timeout)
        client.call("inject_key", {"key": key, "action": "release"})
        if hit.get("pc") != module_syms["start_screen"]:
            raise RuntimeError(f"{boundary} key {key} did not reach start_screen: {hit}")
        requested = int(client.call("read_registers")["a"])
        result = {
            "boundary": boundary,
            "key": key,
            "pending_at_injection": pending,
            "mode_at_injection": mode_at_injection,
            "requested_map": requested,
            "context_after_request": read_byte(client, PRES_CONTEXT),
        }
        if requested != expected_map:
            raise RuntimeError(f"input boundary mismatch {result}, expected map {expected_map}")
        return result
    finally:
        if ids:
            try:
                monitor.clear(client, ids)
            except Exception:
                pass
        client.close()
        monitor.stop(process)
        process.wait(timeout=2)


def demo_ownership_case(monitor, binary: Path, rom: Path, timeout: float,
                        module_syms: dict[str, int], auxiliary_syms: dict[str, int]) -> dict[str, int]:
    process, client = monitor.launch(binary, rom, monitor.free_port())
    ids: list[int] = []
    try:
        demo_id = reach(client, module_syms["demo_run"], timeout)
        ids.append(demo_id)
        for _ in range(64):
            route_direction = read_byte(client, PRES_DEMO_DIR)
            if route_direction != 0xFF:
                break
            hit = client.run_to_breakpoint(timeout)
            if hit.get("pc") != module_syms["demo_run"]:
                raise RuntimeError(f"demo direction marker mismatch {hit}")
        else:
            raise RuntimeError("demo route direction did not become active")
        injected = (route_direction + 1) & 3
        write_byte(client, JOY_DIR, injected)
        write_byte(client, PLAYER_WANT, injected)
        monitor.clear(client, [demo_id])
        ids.remove(demo_id)
        player_id = client.call("set_breakpoint", {
            "addr": auxiliary_syms["demo_route_advance"], "kind": "exec",
        })["id"]
        ids.append(player_id)
        hit = client.run_to_breakpoint(timeout)
        if hit.get("pc") != auxiliary_syms["demo_route_advance"]:
            raise RuntimeError(f"post-demo-runtime input marker missing {hit}")
        result = {
            "route_direction": route_direction,
            "injected_live_direction": injected,
            "joy_before_route_advance": read_byte(client, JOY_DIR),
            "want_before_route_advance": read_byte(client, PLAYER_WANT),
        }
        if result["joy_before_route_advance"] != route_direction:
            raise RuntimeError(f"live input retained JOY_DIR ownership {result}")
        if result["want_before_route_advance"] != route_direction:
            raise RuntimeError(f"live input retained PLAYER_WANT ownership {result}")
        return result
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
    parser.add_argument(
        "--scenario", choices=("all", "preemption", "ownership"), default="all"
    )
    args = parser.parse_args()
    monitor = load_monitor()
    module_syms = symbols(MODULE_MAP)
    auxiliary_syms = symbols(AUXILIARY_MAP)
    cases = []
    if args.scenario in ("all", "preemption"):
        for boundary in ("attract", "level", "demo", "death"):
            cases.append(input_case(
                monitor, args.xroar, args.rom, args.timeout, module_syms,
                boundary, 5, 3,
            ))
        cases.append(input_case(
            monitor, args.xroar, args.rom, args.timeout, module_syms,
            "demo", 5, 3, pending=True,
        ))
        for boundary in ("attract", "demo", "death"):
            cases.append(input_case(
                monitor, args.xroar, args.rom, args.timeout, module_syms,
                boundary, 1, 2,
            ))
    ownership = (
        demo_ownership_case(
            monitor, args.xroar, args.rom, args.timeout, module_syms, auxiliary_syms
        )
        if args.scenario in ("all", "ownership") else None
    )
    evidence = {
        "schema": "ladybug-bug012-input-boundaries-v1",
        "rom_sha256": hashlib.sha256(args.rom.read_bytes()).hexdigest(),
        "phase_deadline_seconds": args.timeout,
        "preemption_cases": cases,
        "demo_input_ownership": ownership,
    }
    args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="ascii")
    print(f"BUG-012 input boundaries pass: scenario={args.scenario}")


if __name__ == "__main__":
    main()
