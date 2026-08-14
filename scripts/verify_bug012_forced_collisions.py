#!/usr/bin/env python3
"""Force BUG-012 skull and enemy collision paths through normal services."""

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
ENEMY_MAP = ROOT / "build/ladybug-enemy-runtime.map"
PRES_MODE = 0x00A5
DEATH_STATE = 0x004D
DEATH_TIMER = 0x003A
LIVES = 0x0023
SCORE = 0x001D
PLAYER_CELL_X = 0x0009
PLAYER_CELL_Y = 0x000A
ENTITY_COUNT = 0x0032
ENTITY_TABLE = 0xA380
ENEMY_ACTIVE = 0x0058
ENEMY_TABLE = 0xA470
PAR5 = 0xFFA5


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
    result = client.call("read_memory", {"addr": address, "length": length})
    return bytes.fromhex(result["data"])


def read_byte(client, address: int) -> int:
    return read_bytes(client, address, 1)[0]


def write_bytes(client, address: int, data: bytes) -> None:
    client.call("write_memory", {"addr": address, "data": data.hex()})


def boot_to_demo(monitor, client, start_screen: int, demo_run: int,
                 timeout: float) -> tuple[int, int]:
    start_id, demo_id = monitor.setup(client, [start_screen, demo_run])
    for _ in range(12):
        hit = client.run_to_breakpoint(timeout)
        if hit.get("pc") == demo_run:
            return start_id, demo_id
        if hit.get("pc") != start_screen:
            raise RuntimeError(f"unexpected pre-demo marker {hit}")
    raise RuntimeError("demo entry missing")


def run_case(monitor, binary: Path, rom: Path, timeout: float,
             cause: str, module_syms: dict[str, int],
             main_syms: dict[str, int], enemy_syms: dict[str, int]) -> dict[str, object]:
    process, client = monitor.launch(binary, rom, monitor.free_port())
    ids: list[int] = []
    try:
        start_id, demo_id = boot_to_demo(
            monitor, client, module_syms["start_screen"], module_syms["demo_run"], timeout
        )
        ids.extend((start_id, demo_id))
        monitor.clear(client, [demo_id])
        ids.remove(demo_id)
        lives_before = read_byte(client, LIVES)
        score_before = read_bytes(client, SCORE, 3).hex()
        player = (read_byte(client, PLAYER_CELL_X), read_byte(client, PLAYER_CELL_Y))
        write_bytes(client, PAR5, b"\x34")

        if cause == "enemy":
            collision_id = monitor.setup(client, [main_syms["main_after_player"]])[0]
            ids.append(collision_id)
            record = bytes((1, 0x57, 0xEC, 0, player[0], player[1], 0, 0xFF))
            write_bytes(client, ENEMY_TABLE, record)
            write_bytes(client, ENEMY_ACTIVE, b"\x01")
            injected = read_bytes(client, ENEMY_TABLE, 8)
            if injected != record:
                raise RuntimeError(f"enemy injection differs: record={injected.hex()}")
            hit = client.run_to_breakpoint(timeout)
            expected_pc = main_syms["main_after_player"]
            live_player = (read_byte(client, PLAYER_CELL_X), read_byte(client, PLAYER_CELL_Y))
            if hit.get("pc") != expected_pc or live_player != player:
                raise RuntimeError(
                    f"enemy post-tick boundary differs: hit={hit} player={live_player}"
                )
            if read_byte(client, DEATH_STATE) != 1:
                raise RuntimeError("enemy tick did not enter ordinary death state")
        else:
            collision_id = monitor.setup(client, [main_syms["cep_skull"]])[0]
            ids.append(collision_id)
            x, y = player
            adjacent = ((x, y - 1), (x + 1, y), (x, y + 1), (x - 1, y))
            records = b"".join(
                bytes((cell_x & 0xFF, cell_y & 0xFF, 1, 0))
                for cell_x, cell_y in adjacent
            )
            write_bytes(client, ENTITY_TABLE, records)
            write_bytes(client, ENTITY_COUNT, b"\x04")
            hit = client.run_to_breakpoint(timeout)
            expected_pc = main_syms["cep_skull"]

        if hit.get("pc") != expected_pc:
            raise RuntimeError(f"{cause} collision boundary missing {hit}")
        monitor.clear(client, [collision_id])
        ids.remove(collision_id)
        hit = client.run_to_breakpoint(timeout)
        if hit.get("pc") != module_syms["start_screen"]:
            raise RuntimeError(f"{cause} death did not return to attract {hit}")
        return_map = int(client.call("read_registers")["a"])
        result = {
            "cause": cause,
            "collision_pc": expected_pc,
            "collision_service_pc": (
                enemy_syms["et_player_death"] if cause == "enemy" else expected_pc
            ),
            "player_cell": list(player),
            "death_state": read_byte(client, DEATH_STATE),
            "death_timer": read_byte(client, DEATH_TIMER),
            "lives_before": lives_before,
            "lives_after": read_byte(client, LIVES),
            "score_before": score_before,
            "score_after": read_bytes(client, SCORE, 3).hex(),
            "return_map": return_map,
            "presentation_mode_before_request": read_byte(client, PRES_MODE),
        }
        if result["death_state"] != 3 or result["death_timer"] != 0:
            raise RuntimeError(f"{cause} death completion state mismatch {result}")
        if result["lives_after"] != lives_before or result["score_after"] != score_before:
            raise RuntimeError(f"{cause} mutated demo lives or score {result}")
        if return_map != 0 or result["presentation_mode_before_request"] != 4:
            raise RuntimeError(f"{cause} returned through wrong flow {result}")
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
    parser.add_argument("--cause", choices=("skull", "enemy", "both"), default="both")
    args = parser.parse_args()
    monitor = load_monitor()
    module_syms = symbols(MODULE_MAP)
    main_syms = symbols(MAIN_MAP)
    enemy_syms = symbols(ENEMY_MAP)
    causes = ("skull", "enemy") if args.cause == "both" else (args.cause,)
    cases = []
    for cause in causes:
        cases.append(run_case(
            monitor, args.xroar, args.rom, args.timeout, cause,
            module_syms, main_syms, enemy_syms,
        ))
        print(f"BUG-012 forced collision pass: {cause}")
    evidence = {
        "schema": "ladybug-bug012-forced-collisions-v1",
        "rom_sha256": hashlib.sha256(args.rom.read_bytes()).hexdigest(),
        "phase_deadline_seconds": args.timeout,
        "cases": cases,
    }
    args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="ascii")
    print(f"BUG-012 forced collisions pass: {', '.join(causes)} return to attract")


if __name__ == "__main__":
    main()
