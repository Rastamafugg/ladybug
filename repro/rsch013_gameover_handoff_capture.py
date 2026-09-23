#!/usr/bin/env python3
"""Capture the complete-ROM terminal-death to game-over screen handoff."""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import verify_bug011_runtime as runtime
import verify_bug009_monitor_input as monitor
from rsch013_colour_animation_capture import cell_pens, save_png


def main():
    build = ROOT / "build"
    rom = build / "ladybug.rom"
    output = ROOT / "repro/rsch013-gameover-handoff.json"
    result = {"rom_sha256": hashlib.sha256(rom.read_bytes()).hexdigest(),
              "phase_deadline_seconds": 40,
              "timeout_meaning": "named game/death/screen marker not reached",
              "setup": "natural credited game entry; seed zero remaining lives and death state 1"}
    process, client = runtime.launch_fast(
        monitor, ROOT / "docs/reference/xroar/src/xroar", rom)
    presentation = runtime.symbols(build / "ladybug-presentation-runtime.map")
    game = runtime.symbols(build / "ladybug.map")

    def reach(name, table):
        address = table[name]
        ids = monitor.setup(client, [address])
        try:
            hit = client.run_to_breakpoint(40)
            if hit.get("pc") != address:
                raise RuntimeError(f"{name}: unexpected {hit}")
        finally:
            monitor.clear(client, ids)

    def front():
        owner = runtime.read_byte(client, runtime.FB_FRONT)
        frame = runtime.read_owner(client, owner)
        return owner, frame

    try:
        reach("presentation_flow_tick", presentation)
        authored = (build / "ladybug-presentation-runtime.bin").read_bytes()
        result["presentation_identity"] = (
            runtime.read_bytes(client, 0x1900, len(authored)) == authored)
        if not result["presentation_identity"]:
            raise RuntimeError("presentation identity mismatch")
        reach("demo_run", presentation)
        client.call("inject_key", {"key": 5, "action": "press"})
        reach("credit_tick", presentation)
        client.call("inject_key", {"key": 5, "action": "release"})
        client.call("inject_key", {"key": 1, "action": "press"})
        reach("normal_game", presentation)
        client.call("inject_key", {"key": 1, "action": "release"})
        game_rom = (build / "ladybug-runtime.rom").read_bytes()
        addr = game["death_tick"]
        result["death_code_identity"] = (
            runtime.read_bytes(client, addr, 24) ==
            game_rom[addr - 0xC000:addr - 0xC000 + 24])
        if not result["death_code_identity"]:
            raise RuntimeError("death code identity mismatch")
        for _ in range(64):
            if runtime.read_byte(client, 0x00A0) == 0:
                break
            reach("normal_game", presentation)
        else:
            raise RuntimeError("initial entry incomplete")
        runtime.write_byte(client, 0x0023, 0)
        runtime.write_byte(client, 0x003A, 0)
        runtime.write_byte(client, 0x004D, 1)
        reach("dt_game_over", game)
        owner, frame = front()
        save_png(frame, ROOT / "repro/rsch013-gameover-last-game.png")
        result["last_game"] = {
            "owner": owner, "frame_sha256": hashlib.sha256(frame).hexdigest(),
            "death_state": runtime.read_byte(client, 0x004D),
            "lives": runtime.read_byte(client, 0x0023),
            "cells": {f"{x},{y}": cell_pens(frame, x, y)
                      for x, y in [(8, 0), (8, 1), (8, 20), (31, 20),
                                   (33, 2), (33, 6), (33, 8), (33, 9),
                                   (33, 10), (33, 11)]}}
        reach("start_screen", presentation)
        result["requested_map"] = int(client.call("read_registers")["a"])
        reach("load_done_publish", presentation)
        staged_owner = runtime.read_byte(client, runtime.FB_BACK)
        staged = runtime.read_owner(client, staged_owner)
        staged_hash = hashlib.sha256(staged).hexdigest()
        for _ in range(12):
            reach("presentation_flow_tick", presentation)
            owner, frame = front()
            if hashlib.sha256(frame).hexdigest() == staged_hash:
                break
        else:
            raise RuntimeError("game-over staged frame not visible")
        save_png(frame, ROOT / "repro/rsch013-gameover-natural.png")
        result["first_gameover"] = {
            "owner": owner, "frame_sha256": staged_hash,
            "cells": {f"{x},{y}": cell_pens(frame, x, y)
                      for x, y in [(8, 0), (8, 1), (8, 20), (31, 20),
                                   (33, 2), (33, 6), (33, 8), (33, 9),
                                   (33, 10), (33, 11)]}}
        result["success_marker"] = "terminal dispatch and first visible game-over frame"
    except Exception as exc:
        result["failure"] = f"{type(exc).__name__}: {exc}"
    finally:
        client.close()
        monitor.stop(process)
        output.write_text(json.dumps(result, indent=2) + "\n")
    print({k: v for k, v in result.items() if k not in ("last_game", "first_gameover")})
    if "failure" in result:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
