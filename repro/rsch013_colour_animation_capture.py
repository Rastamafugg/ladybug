#!/usr/bin/env python3
"""Bounded current-ROM attract/level palette and gameplay animation capture."""
import hashlib
import json
import sys
import argparse
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import verify_bug011_runtime as runtime
import verify_bug009_monitor_input as monitor
from build_screen import PALETTE
from PIL import Image

BUILD = ROOT / "build"
OUT = ROOT / "repro/rsch013-colour-animation.json"


def save_png(frame, path):
    rgb = []
    for code in PALETTE:
        rgb.append(((170 if code & 0x20 else 0) + (85 if code & 0x04 else 0),
                    (170 if code & 0x10 else 0) + (85 if code & 0x02 else 0),
                    (170 if code & 0x08 else 0) + (85 if code & 0x01 else 0)))
    pixels = bytearray()
    for packed in frame:
        pixels.extend(rgb[packed >> 4])
        pixels.extend(rgb[packed & 15])
    Image.frombytes("RGB", (320, 192), bytes(pixels)).save(path)


def cell_pens(frame, x, y):
    values = Counter()
    for row in range(y * 8, y * 8 + 8):
        for byte in frame[row * 160 + x * 4:row * 160 + x * 4 + 4]:
            values[byte >> 4] += 1
            values[byte & 15] += 1
    return {str(k): v for k, v in sorted(values.items()) if k}


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--colour-only", action="store_true")
    mode.add_argument("--animation-only", action="store_true")
    args = parser.parse_args()
    output = ROOT / "repro/rsch013-animation.json" if args.animation_only else OUT
    rom = BUILD / "ladybug.rom"
    result = {"rom_sha256": hashlib.sha256(rom.read_bytes()).hexdigest(),
              "phase_deadline_seconds": 40,
              "timeout_meaning": "named screen or tick marker not reached"}
    process, client = runtime.launch_fast(monitor, ROOT / "docs/reference/xroar/src/xroar", rom)
    syms = runtime.symbols(BUILD / "ladybug-presentation-runtime.map")
    main_syms = runtime.symbols(BUILD / "ladybug.map")

    def reach(name, table=syms):
        address = table[name]
        ids = monitor.setup(client, [address])
        try:
            hit = client.run_to_breakpoint(40)
            if hit.get("pc") != address:
                raise RuntimeError(f"{name}: unexpected {hit}")
        finally:
            monitor.clear(client, ids)

    def frame():
        owner = runtime.read_byte(client, runtime.FB_FRONT)
        return owner, runtime.read_owner(client, owner)

    try:
        reach("presentation_flow_tick")
        authored = (BUILD / "ladybug-presentation-runtime.bin").read_bytes()
        result["presentation_identity"] = runtime.read_bytes(client, 0x1900, len(authored)) == authored
        if not result["presentation_identity"]:
            raise RuntimeError("presentation identity mismatch")
        if not args.animation_only:
            reach("attract_tick")
            attract = []
            for tick in range(24):
                owner, pixels = frame()
                if tick in (0, 16):
                    save_png(pixels, ROOT / f"repro/rsch013-attract-{tick}.png")
                logo_yellow = [[x, y] for y in range(7, 13) for x in range(9, 31)
                               if "2" in cell_pens(pixels, x, y)]
                attract.append({"tick": tick, "owner": owner,
                                "frame_sha256": hashlib.sha256(pixels).hexdigest(),
                                "logo_yellow_cells": logo_yellow})
                reach("attract_tick")
            result["attract"] = attract
        reach("level_tick")
        if runtime.read_byte(client, 0x91):
            reach("level_tick")
        if not args.animation_only:
            owner, pixels = frame()
            save_png(pixels, ROOT / "repro/rsch013-level-start.png")
            result["level_start"] = {"owner": owner,
                "frame_sha256": hashlib.sha256(pixels).hexdigest(),
                "cells": {f"{x},{y}": cell_pens(pixels, x, y)
                          for y in range(0, 24) for x in range(0, 40)
                          if (17 <= x <= 22 and 11 <= y <= 18)
                          or (x >= 32 and y in (7, 8, 9, 10, 11))}}
        if args.colour_only:
            result["success_marker"] = "identity-proven attract and level-start colour frames"
            return
        reach("demo_run")
        client.call("inject_key", {"key": 5, "action": "press"})
        reach("credit_tick")
        client.call("inject_key", {"key": 5, "action": "release"})
        client.call("inject_key", {"key": 1, "action": "press"})
        reach("normal_game")
        client.call("inject_key", {"key": 1, "action": "release"})
        runtime_rom = (BUILD / "ladybug-runtime.rom").read_bytes()
        address = main_syms["player_animation_tick"]
        result["player_tick_identity"] = runtime.read_bytes(client, address, 24) == runtime_rom[address - 0xC000:address - 0xC000 + 24]
        if not result["player_tick_identity"]:
            raise RuntimeError("player tick identity mismatch")
        for _ in range(64):
            if runtime.read_byte(client, 0xA0) == 0:
                break
            reach("normal_game")
        else:
            raise RuntimeError("initial entry incomplete")
        animation = []
        for index in range(32):
            reach("normal_game")
            page = runtime.read_bytes(client, 0, 0x56)
            animation.append({"call": index, "vbord": int.from_bytes(page[2:4], "big"),
                "player_phase": page[0x4F], "player_timer": page[0x50],
                "enemy_phase": page[0x54], "enemy_timer": page[0x55],
                "death_state": page[0x4D]})
        result["gameplay_animation"] = animation
        result["success_marker"] = "32 identity-proven gameplay animation ticks"
    except Exception as exc:
        result["failure"] = f"{type(exc).__name__}: {exc}"
    finally:
        client.close()
        monitor.stop(process)
        output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print({k: (len(v) if isinstance(v, list) else v) for k, v in result.items()
           if k != "level_start"})
    if "failure" in result:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
