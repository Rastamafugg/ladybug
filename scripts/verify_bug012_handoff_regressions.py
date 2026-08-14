#!/usr/bin/env python3
"""Verify BUG-012 full-stage handoff and first-death demo return in XRoar."""

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
PRESENTATION = ROOT / "build/ladybug-presentation.json"
PRES_MODE = 0x00A5
PRES_SCREEN = 0x00A6
DEATH_STATE = 0x004D
DEATH_TIMER = 0x003A
RENDER_FLAGS = 0x007F
RF_STAGE = 0x40
FB_FRONT = 0x008F
FB_BACK = 0x0090
FB_BYTES = 0x7800
PAGE_BYTES = 0x2000
FB_A_PAGE = 0x30
FB_B_PAGE = 0x2C


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


def live_identity(client, address: int, artifact: Path) -> bool:
    expected = artifact.read_bytes()
    result = client.call("read_memory", {"addr": address, "length": len(expected)})
    actual = bytes.fromhex(result["data"])
    return hashlib.sha256(actual).digest() == hashlib.sha256(expected).digest()


def read_physical(client, address: int, length: int) -> bytes:
    result = client.call("read_memory", {
        "space": "physical", "addr": address, "length": length,
    })
    return bytes.fromhex(result["data"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xroar", type=Path, required=True)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--initial-owner", type=int, choices=(0, 1))
    parser.add_argument("--expected-first-maze-sha256")
    args = parser.parse_args()

    module_syms = symbols(MODULE_MAP)
    main_syms = symbols(MAIN_MAP)
    presentation = json.loads(PRESENTATION.read_text(encoding="ascii"))
    start_screen = module_syms["start_screen"]
    demo_run = module_syms["demo_run"]
    render_frame = main_syms["render_frame"]
    monitor = load_monitor()
    process, client = monitor.launch(args.xroar, args.rom, monitor.free_port())
    breakpoint_ids: list[int] = []
    try:
        start_id, demo_id, render_id = monitor.setup(
            client, [start_screen, demo_run, render_frame]
        )
        breakpoint_ids.extend((start_id, demo_id, render_id))
        screen_requests: list[int] = []
        first_render_flags = None
        for _ in range(12):
            hit = client.run_to_breakpoint(args.timeout)
            if hit.get("pc") == demo_run:
                break
            if hit.get("pc") == render_frame:
                first_render_flags = read_byte(client, RENDER_FLAGS)
                if not first_render_flags & RF_STAGE:
                    raise SystemExit(
                        "BUG-012 handoff: transition render lacks RF_STAGE: "
                        f"{first_render_flags:#04x}"
                    )
                monitor.clear(client, [render_id])
                breakpoint_ids.remove(render_id)
                continue
            if hit.get("pc") != start_screen:
                raise SystemExit(f"BUG-012 handoff: unexpected entry marker {hit}")
            if not screen_requests and args.initial_owner is not None:
                client.call("write_memory", {
                    "addr": FB_FRONT, "data": f"{args.initial_owner:02x}",
                })
                client.call("write_memory", {
                    "addr": FB_BACK, "data": f"{1 - args.initial_owner:02x}",
                })
            screen_requests.append(int(client.call("read_registers")["a"]))
        else:
            raise SystemExit("BUG-012 handoff: demo entry missing")

        identities = {
            "module": live_identity(client, 0x1900, MODULE),
            "auxiliary": live_identity(client, 0x0300, AUXILIARY),
        }
        if not all(identities.values()):
            raise SystemExit(f"BUG-012 handoff: live artifact mismatch {identities}")

        if first_render_flags is None:
            raise SystemExit("BUG-012 handoff: transition render marker missing")
        frame_a = read_physical(client, FB_A_PAGE * PAGE_BYTES, FB_BYTES)
        frame_b = read_physical(client, FB_B_PAGE * PAGE_BYTES, FB_BYTES)
        frame_hashes = {
            "a": hashlib.sha256(frame_a).hexdigest(),
            "b": hashlib.sha256(frame_b).hexdigest(),
        }
        level_start_hash = next(
            item["authored_frame_sha256"] for item in presentation["maps"]
            if item["name"] == "level-start"
        )
        front_owner = read_byte(client, FB_FRONT)
        front_hash = frame_hashes["a" if front_owner == 0 else "b"]
        if front_hash == level_start_hash:
            raise SystemExit("BUG-012 handoff: first maze frame remains level-start pixels")
        if (args.expected_first_maze_sha256 is not None and
                front_hash != args.expected_first_maze_sha256):
            raise SystemExit(
                "BUG-012 handoff: first visible maze frame differs from crossover "
                f"oracle {front_hash} != {args.expected_first_maze_sha256}"
            )
        monitor.clear(client, [demo_id])
        breakpoint_ids.remove(demo_id)
        client.call("write_memory", {"addr": DEATH_STATE, "data": "03"})
        client.call("write_memory", {"addr": DEATH_TIMER, "data": "00"})
        hit = client.run_to_breakpoint(args.timeout)
        if hit.get("pc") != start_screen:
            raise SystemExit(f"BUG-012 handoff: completed death did not request attract {hit}")
        registers = client.call("read_registers")
        return_map = int(registers["a"])
        if return_map != 0 or read_byte(client, PRES_MODE) != 4:
            raise SystemExit(
                f"BUG-012 handoff: wrong completed-death request map={return_map} "
                f"mode={read_byte(client, PRES_MODE)} screen={read_byte(client, PRES_SCREEN)}"
            )

        evidence = {
            "schema": "ladybug-bug012-handoff-regressions-v1",
            "rom_sha256": hashlib.sha256(args.rom.read_bytes()).hexdigest(),
            "live_identity": identities,
            "screen_requests_before_demo": screen_requests,
            "first_demo_render_flags": first_render_flags,
            "first_demo_render_has_full_stage": True,
            "first_maze_frame": {
                "initial_owner": args.initial_owner,
                "front_owner": front_owner,
                "front_sha256": front_hash,
                "owner_a_sha256": frame_hashes["a"],
                "owner_b_sha256": frame_hashes["b"],
                "owners_converged_at_transition": frame_a == frame_b,
                "owner_difference_bytes": sum(a != b for a, b in zip(frame_a, frame_b)),
                "level_start_sha256": level_start_hash,
                "differs_from_level_start": True,
                "matches_crossover_oracle": (
                    args.expected_first_maze_sha256 is None or
                    front_hash == args.expected_first_maze_sha256
                ),
            },
            "forced_completed_death": {"state": 3, "timer": 0},
            "return_map": return_map,
            "phase_deadline_seconds": args.timeout,
        }
        args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="ascii")
        print(
            "BUG-012 handoff regressions pass: first visible maze frame differs from "
            "level start and matches any crossover oracle; completed first death requests attract"
        )
    finally:
        if breakpoint_ids:
            try:
                monitor.clear(client, breakpoint_ids)
            except Exception:
                pass
        client.close()
        monitor.stop(process)
        process.wait(timeout=2)


if __name__ == "__main__":
    main()
