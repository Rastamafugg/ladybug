#!/usr/bin/env python3
"""Capture the first natural complete-ROM demo HUD publication."""
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
    output = ROOT / "repro/rsch013-demo-hud.json"
    report = {"rom_sha256": hashlib.sha256(rom.read_bytes()).hexdigest(),
              "phase_deadline_seconds": 40,
              "timeout_meaning": "natural demo marker not reached"}
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

    try:
        reach("presentation_flow_tick")
        authored = (build / "ladybug-presentation-runtime.bin").read_bytes()
        report["presentation_identity"] = (
            runtime.read_bytes(client, 0x1900, len(authored)) == authored)
        if not report["presentation_identity"]:
            raise RuntimeError("presentation identity mismatch")
        reach("demo_run")
        helper = (build / "ladybug-demo-runtime.bin").read_bytes()
        report["demo_identity"] = runtime.read_bytes(client, 0x0300, len(helper)) == helper
        if not report["demo_identity"]:
            raise RuntimeError("demo identity mismatch")
        owner = runtime.read_byte(client, runtime.FB_FRONT)
        frame = runtime.read_owner(client, owner)
        save_png(frame, ROOT / "repro/rsch013-demo-hud.png")
        report["front"] = owner
        report["frame_sha256"] = hashlib.sha256(frame).hexdigest()
        report["credit_region"] = {
            f"{x},{y}": cell_pens(frame, x, y)
            for y in range(7, 12) for x in range(32, 40)}
        report["success_marker"] = "first natural demo_run front"
    except Exception as exc:
        report["failure"] = f"{type(exc).__name__}: {exc}"
    finally:
        client.close()
        monitor.stop(process)
        output.write_text(json.dumps(report, indent=2) + "\n")
    print({k: v for k, v in report.items() if k != "credit_region"})
    if "failure" in report:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
