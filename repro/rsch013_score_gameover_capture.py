#!/usr/bin/env python3
"""Capture identity-proven high-score and game-over ROM screen publications."""
import hashlib
import json
import sys
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import verify_bug011_runtime as runtime
import verify_bug009_monitor_input as monitor
from build_screen import PALETTE

BUILD = ROOT / "build"
OUT = ROOT / "repro/rsch013-score-gameover.json"


def png(frame, path):
    colours = [((170 if c & 0x20 else 0) + (85 if c & 4 else 0),
                (170 if c & 0x10 else 0) + (85 if c & 2 else 0),
                (170 if c & 8 else 0) + (85 if c & 1 else 0)) for c in PALETTE]
    data = bytearray()
    for b in frame:
        data.extend(colours[b >> 4]); data.extend(colours[b & 15])
    Image.frombytes("RGB", (320, 192), bytes(data)).save(path)


def pens(frame, x, y):
    values = set()
    for row in range(y * 8, y * 8 + 8):
        for b in frame[row * 160 + x * 4:row * 160 + x * 4 + 4]:
            values.update((b >> 4, b & 15))
    values.discard(0)
    return sorted(values)


def main():
    rom = BUILD / "ladybug.rom"
    report = {"rom_sha256": hashlib.sha256(rom.read_bytes()).hexdigest(),
              "phase_deadline_seconds": 40,
              "timeout_meaning": "screen load or front publication marker absent",
              "mode": "synthetic start_screen call after natural demo entry"}
    process, client = runtime.launch_fast(monitor, ROOT / "docs/reference/xroar/src/xroar", rom)
    syms = runtime.symbols(BUILD / "ladybug-presentation-runtime.map")

    def reach(address):
        ids = monitor.setup(client, [address])
        try:
            hit = client.run_to_breakpoint(40)
            if hit.get("pc") != address:
                raise RuntimeError(f"unexpected marker {hit}")
        finally:
            monitor.clear(client, ids)

    try:
        reach(syms["presentation_flow_tick"])
        authored = (BUILD / "ladybug-presentation-runtime.bin").read_bytes()
        report["presentation_identity"] = runtime.read_bytes(client, 0x1900, len(authored)) == authored
        if not report["presentation_identity"]:
            raise RuntimeError("presentation identity mismatch")
        reach(syms["demo_run"])
        auxiliary = (BUILD / "ladybug-demo-runtime.bin").read_bytes()
        report["demo_auxiliary_identity"] = runtime.read_bytes(client, 0x0300, len(auxiliary)) == auxiliary
        if not report["demo_auxiliary_identity"]:
            raise RuntimeError("demo auxiliary identity mismatch")
        for screen, name in ((3, "high-score"), (4, "game-over")):
            regs = client.call("read_registers")
            stack = regs["s"] - 2
            runtime.write_word(client, stack, 0x1900)
            client.call("write_registers", {"pc": syms["start_screen"], "a": screen, "s": stack})
            reach(syms["load_done_publish"])
            if runtime.read_byte(client, 0xA6) != screen:
                raise RuntimeError(f"wrong screen {name}")
            back = runtime.read_byte(client, runtime.FB_BACK)
            staged = runtime.read_owner(client, back)
            staged_hash = hashlib.sha256(staged).hexdigest()
            for _ in range(12):
                reach(syms["presentation_flow_tick"])
                front = runtime.read_byte(client, runtime.FB_FRONT)
                frame = runtime.read_owner(client, front)
                if hashlib.sha256(frame).hexdigest() == staged_hash:
                    break
            else:
                raise RuntimeError(f"{name}: staged frame did not reach front")
            png(frame, ROOT / f"repro/rsch013-{name}.png")
            report[name] = {"front": front, "frame_sha256": staged_hash,
                "cells": {f"{x},{y}": pens(frame, x, y) for y in range(24)
                          for x in range(40) if pens(frame, x, y)}}
            if name == "high-score":
                hashes = [staged_hash]
                for _ in range(19):
                    reach(syms["presentation_flow_tick"])
                    hashes.append(hashlib.sha256(runtime.read_owner(
                        client, runtime.read_byte(client, runtime.FB_FRONT))).hexdigest())
                report[name]["twenty_tick_frame_hashes"] = hashes
        report["success_marker"] = "both forced screens reached visible front"
    except Exception as exc:
        report["failure"] = f"{type(exc).__name__}: {exc}"
    finally:
        client.close(); monitor.stop(process)
        OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print({k: v for k, v in report.items() if k not in ("high-score", "game-over")})


if __name__ == "__main__":
    main()
