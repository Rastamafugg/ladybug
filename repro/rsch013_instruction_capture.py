#!/usr/bin/env python3
"""Capture development-profile instruction pixels and actor travel."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import verify_bug011_runtime as runtime
from rsch013_colour_animation_capture import cell_pens, save_png


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    build = workspace / "build"
    rom = build / "ladybug.rom"
    output = ROOT / "repro/rsch013-instruction.json"
    result = {"profile": "development",
              "rom_sha256": hashlib.sha256(rom.read_bytes()).hexdigest(),
              "phase_deadline_seconds": 40,
              "timeout_meaning": "named entry or tick marker not reached"}
    monitor = runtime.load_monitor()
    process, client = runtime.launch_fast(
        monitor, ROOT / "docs/reference/xroar/src/xroar", rom)
    symbols = runtime.symbols(build / "ladybug-presentation-runtime.map")

    def reach(name):
        address = symbols[name]
        ids = monitor.setup(client, [address])
        try:
            hit = client.run_to_breakpoint(40)
            if hit.get("pc") != address:
                raise RuntimeError(f"{name}: unexpected {hit}")
        finally:
            monitor.clear(client, ids)

    try:
        reach("presentation_flow_tick")
        authored = (build / "ladybug-presentation-runtime.bin").read_bytes()
        result["presentation_identity"] = (
            runtime.read_bytes(client, 0x1900, len(authored)) == authored)
        if not result["presentation_identity"]:
            raise RuntimeError("presentation identity mismatch")
        reach("instructions_tick")
        helper = (build / "ladybug-instruction-runtime.bin").read_bytes()
        result["instruction_identity"] = (
            runtime.read_bytes(client, 0x0300, len(helper)) == helper)
        if not result["instruction_identity"]:
            raise RuntimeError("instruction identity mismatch")
        owner = runtime.read_byte(client, runtime.FB_FRONT)
        frame = runtime.read_owner(client, owner)
        save_png(frame, ROOT / "repro/rsch013-instruction.png")
        result["initial"] = {
            "owner": owner,
            "frame_sha256": hashlib.sha256(frame).hexdigest(),
            "targets": {f"{x},{y}": cell_pens(frame, x, y)
                        for x, y in [(33, 2), (33, 6), (18, 14),
                                     (28, 13), (29, 13), (25, 20)]}}
        ticks = []
        for index in range(160):
            if 116 <= index <= 140 or index in (0, 80, 159):
                ticks.append({"tick": index,
                              "timer": runtime.read_word(client, 0x00B0),
                              "out": runtime.read_word(client, 0x00B7),
                              "event_phase": runtime.read_byte(client, 0x00CA),
                              "sprite_phase": runtime.read_byte(client, 0x00CE)})
            if index == 130:
                moving_owner = runtime.read_byte(client, runtime.FB_FRONT)
                moving_frame = runtime.read_owner(client, moving_owner)
                save_png(moving_frame, ROOT / "repro/rsch013-instruction-moving.png")
                result["moving_frame_sha256"] = hashlib.sha256(moving_frame).hexdigest()
            reach("instructions_tick")
        result["actor_tick_samples"] = ticks
        result["success_marker"] = "160 instruction dispatch ticks"
    except Exception as exc:
        result["failure"] = f"{type(exc).__name__}: {exc}"
    finally:
        client.close()
        runtime.stop(process)
        output.write_text(json.dumps(result, indent=2) + "\n")
    print({k: (len(v) if isinstance(v, list) else v)
           for k, v in result.items() if k != "initial"})
    if "failure" in result:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
