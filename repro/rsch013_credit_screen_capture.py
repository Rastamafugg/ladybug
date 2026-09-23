#!/usr/bin/env python3
"""Capture natural first and second credit high-score screens."""
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import verify_bug011_runtime as runtime
import verify_bug009_monitor_input as monitor
from rsch013_colour_animation_capture import cell_pens, save_png


def main():
    build = ROOT / "build"
    rom = build / "ladybug.rom"
    output = ROOT / "repro/rsch013-credit-screen.json"
    report = {"rom_sha256": hashlib.sha256(rom.read_bytes()).hexdigest(),
              "phase_deadline_seconds": 40,
              "timeout_meaning": "natural credit screen marker not reached"}
    process, client = runtime.launch_fast(
        monitor, ROOT / "docs/reference/xroar/src/xroar", rom)
    syms = runtime.symbols(build / "ladybug-presentation-runtime.map")

    def reach(name):
        address = syms[name]
        ids = monitor.setup(client, [address])
        try:
            hit = client.run_to_breakpoint(40)
            if hit.get("pc") != address:
                raise RuntimeError(f"{name}: unexpected {hit}")
        finally:
            monitor.clear(client, ids)

    def capture(count):
        owner = runtime.read_byte(client, runtime.FB_FRONT)
        frame = runtime.read_owner(client, owner)
        save_png(frame, ROOT / f"repro/rsch013-credit-{count}.png")
        pens = Counter()
        for byte in frame:
            pens[byte >> 4] += 1
            pens[byte & 15] += 1
        return {"credits": runtime.read_byte(client, 0x00A8),
                "screen": runtime.read_byte(client, 0x00A6),
                "owner": owner, "frame_sha256": hashlib.sha256(frame).hexdigest(),
                "nonblack_pens": {str(pen): n for pen, n in sorted(pens.items()) if pen},
                "prompt_cells": {f"{x},{y}": cell_pens(frame, x, y)
                                 for y in range(17, 24) for x in range(8, 32)
                                 if cell_pens(frame, x, y)}}

    try:
        reach("presentation_flow_tick")
        authored = (build / "ladybug-presentation-runtime.bin").read_bytes()
        report["presentation_identity"] = (
            runtime.read_bytes(client, 0x1900, len(authored)) == authored)
        if not report["presentation_identity"]:
            raise RuntimeError("presentation identity mismatch")
        reach("demo_run")
        client.call("inject_key", {"key": 5, "action": "press"})
        reach("credit_tick")
        report["first"] = capture(1)
        client.call("inject_key", {"key": 5, "action": "release"})
        reach("credit_tick")
        client.call("inject_key", {"key": 6, "action": "press"})
        reach("credit_tick")
        report["second"] = capture(2)
        report["success_marker"] = "natural first and second credit screens"
    except Exception as exc:
        report["failure"] = f"{type(exc).__name__}: {exc}"
    finally:
        client.close()
        monitor.stop(process)
        output.write_text(json.dumps(report, indent=2) + "\n")
    print({k: v for k, v in report.items() if k not in ("first", "second")})
    if "failure" in report:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
