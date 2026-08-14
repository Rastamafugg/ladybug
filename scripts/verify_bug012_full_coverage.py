#!/usr/bin/env python3
"""Prove BUG-012 full coverage in the live copied game and demo runtimes."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MONITOR_INPUT = ROOT / "scripts/verify_bug009_monitor_input.py"
MODULE_MAP = ROOT / "build/ladybug-presentation-runtime.map"
AUXILIARY_MAP = ROOT / "build/ladybug-instruction-runtime.map"
MAIN_MAP = ROOT / "build/ladybug.map"
MODULE = ROOT / "build/ladybug-presentation-runtime.bin"
AUXILIARY = ROOT / "build/ladybug-instruction-runtime.bin"
PRESENTATION = ROOT / "build/ladybug-presentation.json"
COLD = ROOT / "build/ladybug-presentation-cold.bin"
OFFLINE_PROOF = ROOT / "build/bug012-demo-walk.json"
PRES_SCREEN = 0x00A6
PRES_MODE = 0x00A5
PRES_ROUTE = 0x00DA
PRES_DEMO_DIR = 0x00DD
PLAYER_DIR = 0x0006
PLAYER_STEP = 0x0008
PLAYER_CELL_X = 0x0009
PLAYER_CELL_Y = 0x000A
PLAYER_WANT = 0x000F
PLAYER_MANUAL = 0x0018
DEATH = 0x004D
PAR5 = 0xFFA5
PAR5_GAMEPLAY = 0x34
PAR5_WINDOW = 0xA000
PAGE_BYTES = 0x2000


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


def write_bytes(client, address: int, data: bytes) -> None:
    client.call("write_memory", {"addr": address, "data": data.hex()})


def read_cold(client, base_page: int, offset: int, length: int) -> bytes:
    result = bytearray()
    try:
        while length:
            page = base_page + offset // PAGE_BYTES
            within = offset % PAGE_BYTES
            count = min(length, PAGE_BYTES - within)
            write_bytes(client, PAR5, bytes((page,)))
            result.extend(read_bytes(client, PAR5_WINDOW + within, count))
            offset += count
            length -= count
    finally:
        write_bytes(client, PAR5, bytes((PAR5_GAMEPLAY,)))
    return bytes(result)


def remaining(deadline: float) -> float:
    value = deadline - time.monotonic()
    if value <= 0:
        raise TimeoutError("BUG-012 full coverage: 60-second runtime phase expired")
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xroar", type=Path, required=True)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()

    module_syms = symbols(MODULE_MAP)
    auxiliary_syms = symbols(AUXILIARY_MAP)
    main_syms = symbols(MAIN_MAP)
    manifest = json.loads(PRESENTATION.read_text(encoding="ascii"))
    offline = json.loads(OFFLINE_PROOF.read_text(encoding="ascii"))
    route_manifest = manifest["demo_route"]
    authored_cold = COLD.read_bytes()
    stored_walk = authored_cold[
        route_manifest["cold_offset"]:
        route_manifest["cold_offset"] + route_manifest["bytes"]
    ]

    monitor = load_monitor()
    process, client = monitor.launch(args.xroar, args.rom, monitor.free_port())
    screen_requests: list[dict[str, int]] = []
    try:
        start_screen = module_syms["start_screen"]
        demo_run = module_syms["demo_run"]
        start_id, demo_id = monitor.setup(client, [start_screen, demo_run])
        for _ in range(12):
            hit = client.run_to_breakpoint(args.timeout)
            if hit.get("pc") == demo_run:
                break
            if hit.get("pc") != start_screen:
                raise SystemExit(f"BUG-012 full coverage: unexpected entry breakpoint {hit}")
            screen_requests.append({
                "map": register(client, "a"),
                "mode": read_byte(client, PRES_MODE),
                "screen": read_byte(client, PRES_SCREEN),
            })
        else:
            raise SystemExit("BUG-012 full coverage: demo entry missing")
        monitor.clear(client, [start_id, demo_id])

        authored_module = MODULE.read_bytes()
        authored_auxiliary = AUXILIARY.read_bytes()
        identities = {
            "module": read_bytes(client, 0x1900, len(authored_module)) == authored_module,
            "auxiliary": read_bytes(client, 0x0300, len(authored_auxiliary)) == authored_auxiliary,
            "cold_walk": read_cold(
                client, 0x3A, route_manifest["cold_offset"], len(stored_walk)
            ) == stored_walk,
        }
        if not all(identities.values()):
            raise SystemExit(f"BUG-012 full coverage: live artifact identity mismatch {identities}")

        entity_table = main_syms["ENTITY_TABLE"]
        entity_count = read_byte(client, main_syms["ENTITY_COUNT"])
        entities = bytearray(read_bytes(client, entity_table, entity_count * 4))
        replaced_skulls = []
        for index in range(entity_count):
            offset = index * 4
            if entities[offset + 2] == main_syms["ENTITY_SKULL"]:
                replaced_skulls.append([entities[offset], entities[offset + 1]])
                entities[offset + 2] = 0
        write_bytes(client, entity_table, entities)
        bonus_left = main_syms["BONUS_LEFT"]
        bonus_baseline = read_byte(client, bonus_left)
        write_bytes(client, bonus_left, bytes((bonus_baseline + 1,)))
        write_bytes(client, main_syms["ENEMY_ACTIVE"], b"\x00\x00")
        enemy_table = main_syms["ENEMY_TABLE"]
        enemy_records = bytearray(read_bytes(client, enemy_table, 32))
        for offset in range(0, 32, 8):
            enemy_records[offset] = 0
        write_bytes(client, enemy_table, enemy_records)
        write_bytes(client, main_syms["BOX_TIMER"], b"\xff")

        deadline = time.monotonic() + args.timeout
        route_id = monitor.setup(client, [auxiliary_syms["demo_route_advance"]])[0]
        nodes = []
        for action in range(147):
            try:
                hit = client.run_to_breakpoint(remaining(deadline))
            except Exception as exc:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps({
                    "schema": "ladybug-bug012-full-coverage-v1",
                    "result": "fail",
                    "failure": "route-advance-timeout",
                    "next_action": action,
                    "observed_actions": len(nodes),
                    "last_node": nodes[-1] if nodes else None,
                    "phase_deadline_seconds": args.timeout,
                }, indent=2) + "\n", encoding="ascii")
                raise SystemExit(
                    "BUG-012 full coverage: route-advance deadline expired at "
                    f"action {action}; evidence={args.output}"
                ) from exc
            if hit.get("pc") != auxiliary_syms["demo_route_advance"]:
                raise SystemExit(f"BUG-012 full coverage: unexpected route breakpoint {hit}")
            direct_page = read_bytes(client, 0, 0x00DE)
            route_index = direct_page[PRES_ROUTE]
            cell = [direct_page[PLAYER_CELL_X], direct_page[PLAYER_CELL_Y]]
            gate_states = list(read_bytes(client, main_syms["GATE_STATE"], 20))
            expected = offline["action_records"][action]
            if route_index != action or cell != expected["start"]:
                raise SystemExit(
                    "BUG-012 full coverage: route sequence differs at "
                    f"action {action}: index={route_index}, cell={cell}"
                )
            if gate_states != expected["gate_states_before"]:
                raise SystemExit(
                    "BUG-012 full coverage: live gate states differ at "
                    f"action {action}: {gate_states} != {expected['gate_states_before']}"
                )
            if action % 8 == 0:
                write_bytes(client, main_syms["BOX_TIMER"], b"\xff")
            nodes.append({
                "action": action,
                "route_index_before_advance": route_index,
                "cell": cell,
                "gate_states": gate_states,
            })
        monitor.clear(client, [route_id])

        collect_id = monitor.setup(client, [main_syms["enemy_collect"]])[0]
        terminal = None
        for _ in range(12):
            hit = client.run_to_breakpoint(remaining(deadline))
            if hit.get("pc") != main_syms["enemy_collect"]:
                raise SystemExit(f"BUG-012 full coverage: unexpected completion breakpoint {hit}")
            write_bytes(client, main_syms["BOX_TIMER"], b"\xff")
            cell = [read_byte(client, PLAYER_CELL_X), read_byte(client, PLAYER_CELL_Y)]
            if cell != [6, 2] or read_byte(client, PLAYER_STEP) != 0:
                continue
            maze_state = read_bytes(client, main_syms["MAZE_STATE"], 576)
            final_entities = read_bytes(client, entity_table, entity_count * 4)
            diagnostic_bonus = read_byte(client, bonus_left)
            if diagnostic_bonus != 1:
                raise SystemExit(
                    "BUG-012 full coverage: stage-clear sentinel differs at "
                    f"terminal cell: {diagnostic_bonus}"
                )
            write_bytes(client, bonus_left, b"\x00")
            write_bytes(client, main_syms["STAGE_PENDING"], b"\x00")
            terminal = {
                "cell": cell,
                "route_index": read_byte(client, PRES_ROUTE),
                "death": read_byte(client, DEATH),
                "dots_left": read_byte(client, main_syms["DOTS_LEFT"]),
                "bonus_left": read_byte(client, bonus_left),
                "maze_dots_remaining": sum(bool(value & 0x80) for value in maze_state),
                "entities_remaining": sum(
                    final_entities[offset + 2] != 0
                    for offset in range(0, len(final_entities), 4)
                ),
                "gate_states": list(read_bytes(client, main_syms["GATE_STATE"], 20)),
            }
            break
        monitor.clear(client, [collect_id])
        if terminal is None:
            raise SystemExit("BUG-012 full coverage: terminal cell was not observed")
        if any((
            terminal["route_index"] != 147,
            terminal["death"] != 0,
            terminal["dots_left"] != 0,
            terminal["bonus_left"] != 0,
            terminal["maze_dots_remaining"] != 0,
            terminal["entities_remaining"] != 0,
        )):
            raise SystemExit(f"BUG-012 full coverage: terminal state differs {terminal}")

        # Suppress the already-proven stage-clear transition only long enough to
        # observe the route terminator's specified DIR_NONE hold.
        held_id = monitor.setup(client, [auxiliary_syms["demo_route_held"]])[0]
        held_hit = client.run_to_breakpoint(remaining(deadline))
        if held_hit.get("pc") != auxiliary_syms["demo_route_held"]:
            raise SystemExit("BUG-012 full coverage: terminal hold missing")
        hold = {
            "route_index": read_byte(client, PRES_ROUTE),
            "demo_direction": read_byte(client, PRES_DEMO_DIR),
            "player_direction": read_byte(client, PLAYER_DIR),
            "player_want": read_byte(client, PLAYER_WANT),
            "player_manual": read_byte(client, PLAYER_MANUAL),
        }
        monitor.clear(client, [held_id])
        if (hold["route_index"] != 147 or hold["demo_direction"] != 0xFF or
                hold["player_want"] != 0xFF):
            raise SystemExit(f"BUG-012 full coverage: terminal hold differs {hold}")

        front_faults = read_byte(client, main_syms["FB_WRITE_FRONT_FAULT"])
        if front_faults:
            raise SystemExit(f"BUG-012 full coverage: FRONT writes detected {front_faults}")
        elapsed = args.timeout - remaining(deadline)
        evidence = {
            "schema": "ladybug-bug012-full-coverage-v1",
            "result": "pass",
            "rom_sha256": hashlib.sha256(args.rom.read_bytes()).hexdigest(),
            "artifact_identity": identities,
            "screen_requests": screen_requests,
            "diagnostic_mutations": {
                "enemy_activation_disabled": True,
                "skull_records_removed_after_placement": replaced_skulls,
                "stage_clear_bonus_sentinel": 1,
                "stage_clear_sentinel_removed_at_zero_remaining": True,
            },
            "walk_sha256": route_manifest["walk_sha256"],
            "cold_walk_sha256": hashlib.sha256(stored_walk).hexdigest(),
            "route_nodes": nodes,
            "terminal": terminal,
            "hold": hold,
            "front_write_faults": front_faults,
            "phase_deadline_seconds": args.timeout,
            "phase_elapsed_seconds": elapsed,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="ascii")
        print(
            "BUG-012 full coverage pass: live 147/147 actions, 117/117 "
            f"collectibles, zero remaining, DIR_NONE hold; evidence={args.output}"
        )
    finally:
        client.close()
        monitor.stop(process)
        process.wait(timeout=2)


if __name__ == "__main__":
    main()
