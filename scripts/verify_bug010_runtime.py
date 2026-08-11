#!/usr/bin/env python3
"""Retain BUG-010 hold-surface and owner-hydration evidence through XRoar monitor."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MONITOR_INPUT = ROOT / "scripts/verify_bug009_monitor_input.py"
ROM = ROOT / "build/ladybug.rom"
PRESENTATION_MAP = ROOT / "build/ladybug-presentation-runtime.map"
EVIDENCE = ROOT / "build/bug010-runtime-evidence.json"
HELPER = ROOT / "build/ladybug-perimeter-reset-helper.bin"
LAYOUT = ROOT / "build/ladybug-sparse-layout.json"

HOLD_BEGIN = 0x06C5
HOLD_COPY_CALL = 0x06FB
HOLD_COPY_CHUNK = 0x074B
HOLD_COPY_RETURN = 0x06FE
PUBLISH = 0x0DD5
LOAD_DONE = 0x1A5E
FB_FRONT = 0x008F
FB_BACK = 0x0090
FB_PENDING = 0x0091
HOLD_STATE = 0x00D4
HOLD_CHUNK = 0x00D5
HOLD_SAVED_FRONT = 0x00D6
HOLD_SAVED_BACK = 0x00D7
HOLD_GENERATION = 0x00D8
HOLD_OWNER = 0x00D9
PRES_SCREEN = 0x00A6
PRES_MODE = 0x00A5
PAR1 = 0xFFA1
PAR5 = 0xFFA5
HOLD_PHYSICAL = 0x28 * 0x2000
FRAMEBUFFER_BYTES = 0x7800


def load_monitor_module():
    spec = importlib.util.spec_from_file_location("bug009_monitor", MONITOR_INPUT)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load monitor client")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_map_symbol(path: Path, name: str) -> int:
    match = re.search(
        rf"^Symbol: {re.escape(name)} .* = ([0-9A-Fa-f]+)$",
        path.read_text(encoding="ascii"),
        re.MULTILINE,
    )
    if not match:
        raise RuntimeError(f"missing map symbol {name}")
    return int(match.group(1), 16)


def read_byte(monitor, client, address: int) -> int:
    return bytes.fromhex(
        client.call("read_memory", {"addr": address, "length": 1})["data"]
    )[0]


def read_bytes(monitor, client, address: int, length: int, space: str = "cpu") -> bytes:
    return bytes.fromhex(
        client.call(
            "read_memory",
            {"addr": address, "length": length, "space": space},
        )["data"]
    )


def state(monitor, client) -> dict[str, int]:
    return {
        "front": read_byte(monitor, client, FB_FRONT),
        "back": read_byte(monitor, client, FB_BACK),
        "pending": read_byte(monitor, client, FB_PENDING),
        "hold_state": read_byte(monitor, client, HOLD_STATE),
        "chunk": read_byte(monitor, client, HOLD_CHUNK),
        "saved_front": read_byte(monitor, client, HOLD_SAVED_FRONT),
        "saved_back": read_byte(monitor, client, HOLD_SAVED_BACK),
        "generation": read_byte(monitor, client, HOLD_GENERATION),
        "owner": read_byte(monitor, client, HOLD_OWNER),
        "screen": read_byte(monitor, client, PRES_SCREEN),
        "mode": read_byte(monitor, client, PRES_MODE),
        "par1": read_byte(monitor, client, PAR1),
        "par5": read_byte(monitor, client, PAR5),
    }


def cycles(client) -> dict[str, int]:
    return client.call("read_cycles")


def hold_hashes(monitor, client, front: int) -> tuple[str, str]:
    hold = read_bytes(monitor, client, HOLD_PHYSICAL, FRAMEBUFFER_BYTES, "physical")
    source_page = 0x30 if front == 0 else 0x2C
    source = read_bytes(
        monitor,
        client,
        source_page * 0x2000,
        FRAMEBUFFER_BYTES,
        "physical",
    )
    hold_hash = hashlib.sha256(hold).hexdigest()
    source_hash = hashlib.sha256(source).hexdigest()
    if hold_hash != source_hash:
        raise RuntimeError(
            f"hold hash mismatch for front {front}: {hold_hash} != {source_hash}"
        )
    return hold_hash, source_hash


def run_order(monitor, rom: Path, order: tuple[int, int]) -> dict:
    process, client = monitor.launch(
        monitor_binary,
        rom,
        monitor.free_port(),
    )
    try:
        begin_id = monitor.setup(client, [HOLD_BEGIN])[0]
        begin_hit = client.run_to_breakpoint(20)
        if begin_hit.get("pc") != HOLD_BEGIN:
            raise RuntimeError(f"hold begin PC mismatch: {begin_hit}")
        initial = state(monitor, client)
        if order != (0, 1):
            client.call("write_memory", {"addr": FB_FRONT, "data": f"{order[0]:02x}"})
            client.call("write_memory", {"addr": FB_BACK, "data": f"{order[1]:02x}"})
        configured = state(monitor, client)
        monitor.clear(client, [begin_id])
        live_helper_sha256 = hashlib.sha256(
            read_bytes(monitor, client, 0x06B2, len(HELPER.read_bytes()))
        ).hexdigest()
        breakpoint_ids = monitor.setup(client, [HOLD_COPY_CHUNK, PUBLISH, LOAD_DONE])

        chunks: list[dict] = []
        first_publish: dict | None = None
        loads: list[dict] = []
        final_publish: dict | None = None
        while len(chunks) < 30 or len(loads) < 2 or final_publish is None:
            hit = client.run_to_breakpoint(30)
            pc = hit.get("pc")
            current = state(monitor, client)
            if pc == HOLD_COPY_CHUNK:
                chunks.append(current)
                expected_generation = len(chunks) - 1
                if current["hold_state"] != 0x80:
                    raise RuntimeError(f"copy chunk left COPY state: {current}")
                if current["generation"] != expected_generation:
                    raise RuntimeError(f"copy generation mismatch: {current}")
            elif pc == PUBLISH:
                if first_publish is None:
                    first_publish = current
                    if current["back"] != 2 or current["pending"] != 1:
                        raise RuntimeError(f"transient owner contract failed: {current}")
                    hold_hash, source_hash = hold_hashes(
                        monitor, client, current["front"]
                    )
                else:
                    final_publish = current
            elif pc == LOAD_DONE:
                loads.append(current)
                if len(loads) == 1 and current["owner"] != 0:
                    raise RuntimeError(f"first hydration owner mismatch: {current}")
                if len(loads) == 2 and current["owner"] != 1:
                    raise RuntimeError(f"second hydration owner mismatch: {current}")
            else:
                raise RuntimeError(f"unexpected monitor breakpoint {hit}")
        if first_publish is None or final_publish is None or len(loads) != 2:
            raise RuntimeError("hold sequence did not reach both publications and owners")
        if final_publish["hold_state"] != 0x81 or final_publish["pending"] != 1:
            raise RuntimeError(f"final publication contract failed: {final_publish}")
        return {
            "order": list(order),
            "live_helper_sha256": live_helper_sha256,
            "initial": initial,
            "configured": configured,
            "chunks": chunks,
            "first_publish": first_publish,
            "loads": loads,
            "final_publish": final_publish,
            "hold_sha256": hold_hash,
            "source_sha256": source_hash,
        }
    finally:
        client.close()
        monitor.stop(process)
        process.wait(timeout=2)


def run_cycle_order(monitor, rom: Path, order: tuple[int, int]) -> dict:
    process, client = monitor.launch(monitor_binary, rom, monitor.free_port())
    try:
        begin_id = monitor.setup(client, [HOLD_BEGIN])[0]
        begin_hit = client.run_to_breakpoint(20)
        if begin_hit.get("pc") != HOLD_BEGIN:
            raise RuntimeError(f"cycle hold begin PC mismatch: {begin_hit}")
        if order != (0, 1):
            client.call("write_memory", {"addr": FB_FRONT, "data": f"{order[0]:02x}"})
            client.call("write_memory", {"addr": FB_BACK, "data": f"{order[1]:02x}"})
        monitor.clear(client, [begin_id])
        breakpoint_ids = monitor.setup(client, [HOLD_COPY_CALL, HOLD_COPY_RETURN])
        worklists: list[dict] = []
        entry_cycles: list[int] = []
        copy_start: dict | None = None
        while len(worklists) < 30:
            hit = client.run_to_breakpoint(30)
            pc = hit.get("pc")
            if pc == HOLD_COPY_CALL:
                if copy_start is not None:
                    raise RuntimeError("hold copy call observed before prior return")
                current = state(monitor, client)
                start = cycles(client)
                entry_cycles.append(start["cpu_cycles"])
                copy_start = {"state": current, "cycles": start}
            elif pc == HOLD_COPY_RETURN:
                if copy_start is None:
                    raise RuntimeError("hold copy return observed without call marker")
                end = cycles(client)
                start = copy_start["cycles"]
                worklists.append({
                    "generation": copy_start["state"]["generation"],
                    "copy_page_index": copy_start["state"]["owner"],
                    "chunk": copy_start["state"]["chunk"],
                    "start_cpu_cycles": start["cpu_cycles"],
                    "end_cpu_cycles": end["cpu_cycles"],
                    "cpu_cycles": end["cpu_cycles"] - start["cpu_cycles"],
                    "event_ticks": end["event_ticks"] - start["event_ticks"],
                })
                copy_start = None
            else:
                raise RuntimeError(f"unexpected cycle breakpoint {hit}")
        monitor.clear(client, breakpoint_ids)
        return {
            "order": list(order),
            "worklists": worklists,
            "entry_intervals": [
                entry_cycles[index] - entry_cycles[index - 1]
                for index in range(1, len(entry_cycles))
            ],
        }
    finally:
        client.close()
        monitor.stop(process)
        process.wait(timeout=2)


def run_input_preemption(monitor, rom: Path) -> dict:
    process, client = monitor.launch(monitor_binary, rom, monitor.free_port())
    try:
        breakpoint_ids = monitor.setup(client, [HOLD_COPY_CHUNK, PUBLISH, LOAD_DONE])
        copy_count = 0
        injected: dict | None = None
        transient: dict | None = None
        replacement_load: dict | None = None
        while replacement_load is None:
            hit = client.run_to_breakpoint(30)
            pc = hit.get("pc")
            current = state(monitor, client)
            if pc == HOLD_COPY_CHUNK:
                copy_count += 1
                if copy_count == 5:
                    client.call("inject_key", {"key": 5, "action": "press"})
                if copy_count == 6:
                    injected = current
                    client.call("inject_key", {"key": 5, "action": "release"})
                    if current["screen"] != 3 or current["hold_state"] != 0x80:
                        raise RuntimeError(f"input did not replace screen during hold: {current}")
            elif pc == PUBLISH and transient is None:
                transient = current
            elif pc == LOAD_DONE and current["screen"] == 3:
                replacement_load = current
        if injected is None or transient is None or replacement_load is None:
            raise RuntimeError("input pre-emption evidence is incomplete")
        return {
            "copy_count_at_injection": 5,
            "copy_count_at_observation": 6,
            "injected": injected,
            "transient_publish": transient,
            "replacement_load": replacement_load,
        }
    finally:
        client.close()
        monitor.stop(process)
        process.wait(timeout=2)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--xroar", type=Path, required=True)
    parser.add_argument("--rom", type=Path, default=ROM)
    parser.add_argument("--output", type=Path, default=EVIDENCE)
    args = parser.parse_args()
    global monitor_binary
    monitor_binary = args.xroar
    monitor = load_monitor_module()
    orders = [run_order(monitor, args.rom, (0, 1)), run_order(monitor, args.rom, (1, 0))]
    cycle_orders = [
        run_cycle_order(monitor, args.rom, (0, 1)),
        run_cycle_order(monitor, args.rom, (1, 0)),
    ]
    helper_sha256 = hashlib.sha256(HELPER.read_bytes()).hexdigest()
    staged_helper_sha256 = json.loads(
        LAYOUT.read_text(encoding="ascii")
    )["perimeter_reset"]["helper_sha256"]
    live_helper_hashes = {
        order["live_helper_sha256"] for order in orders
    }
    if live_helper_hashes != {helper_sha256} or staged_helper_sha256 != helper_sha256:
        raise RuntimeError(
            "hold helper identity mismatch: "
            f"authored={helper_sha256}, staged={staged_helper_sha256}, "
            f"live={sorted(live_helper_hashes)}"
        )
    worklist_cycles = [
        worklist["cpu_cycles"]
        for order in cycle_orders
        for worklist in order["worklists"]
    ]
    entry_intervals = [
        interval
        for order in cycle_orders
        for interval in order["entry_intervals"]
    ]
    results = {
        "schema": "ladybug-bug010-runtime-evidence-v2",
        "rom_sha256": hashlib.sha256(args.rom.read_bytes()).hexdigest(),
        "xroar_sha256": hashlib.sha256(args.xroar.read_bytes()).hexdigest(),
        "helper_identity": {
            "bytes": len(HELPER.read_bytes()),
            "authored_sha256": helper_sha256,
            "staged_sha256": staged_helper_sha256,
            "live_sha256": next(iter(live_helper_hashes)),
            "match": True,
        },
        "load_done": read_map_symbol(PRESENTATION_MAP, "load_done"),
        "publish": read_map_symbol(ROOT / "build/ladybug-enemy-runtime.map", "fbiq_publish"),
        "cycle_measurement": {
            "status": "measured",
            "definition": "CPU cycles from the hold-copy call site at $06FB through return at $06FE",
            "marker_deadline_seconds": 30,
            "sample_count": len(worklist_cycles),
            "minimum_cycles": min(worklist_cycles),
            "maximum_cycles": max(worklist_cycles),
            "entry_interval_sample_count": len(entry_intervals),
            "entry_interval_minimum_cycles": min(entry_intervals),
            "entry_interval_maximum_cycles": max(entry_intervals),
            "target_cycles": 27000,
            "hard_max_cycles": 29666,
            "engineering_target_pass": max(worklist_cycles) <= 27000,
            "hardware_maximum_pass": max(worklist_cycles) <= 29666,
        },
        "orders": orders,
        "cycle_orders": cycle_orders,
        "input_preemption": run_input_preemption(monitor, args.rom),
    }
    args.output.write_text(json.dumps(results, indent=2) + "\n", encoding="ascii")
    print(
        "BUG-010 runtime evidence: 60 measured hold chunks, transient ID-2 hash, "
        "two owner hydrations, A/B and B/A orders, and input pre-emption pass; "
        f"hold worklist range {min(worklist_cycles)}-{max(worklist_cycles)} cycles; "
        f"evidence={args.output}"
    )


if __name__ == "__main__":
    main()
