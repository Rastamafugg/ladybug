#!/usr/bin/env python3
"""Verify complete-profile key-5/key-6 high-score runtime dispatch."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import verify_bug011_runtime as monitor_probe  # noqa: E402


PRESENTATION_MAP = ROOT / "build/ladybug-presentation-runtime.map"
MANIFEST = ROOT / "build/ladybug-presentation.json"
DEMO_RUNTIME = ROOT / "build/ladybug-demo-runtime.bin"
PRES_MODE = 0x00A5
PRES_SCREEN = 0x00A6
PRES_CREDITS = 0x00A8
PRES_EVENT = 0x00A9


def symbols(path: Path) -> dict[str, int]:
    return {
        name: int(value, 16)
        for name, value in re.findall(
            r"^Symbol: (\w+) .* = ([0-9A-Fa-f]+)$",
            path.read_text(encoding="utf-8"), re.MULTILINE,
        )
    }


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fail(phase: str, marker: str, detail: str) -> None:
    raise SystemExit(f"phase={phase} marker={marker} failure={detail}")


def run_key(monitor, binary: Path, rom: Path, syms: dict[str, int],
            demo: bytes, key: int, timeout: float) -> dict[str, object]:
    process, client = monitor_probe.launch_fast(monitor, binary, rom)
    try:
        ids = monitor.setup(client, [syms["presentation_flow_tick"]])
        try:
            hit = client.run_to_breakpoint(timeout)
        except Exception as exc:
            fail("cold entry", "presentation_flow_tick", f"timeout: {exc}")
        if hit.get("pc") != syms["presentation_flow_tick"]:
            fail("cold entry", "presentation_flow_tick", repr(hit))
        monitor.clear(client, ids)

        ids = monitor.setup(client, [syms["load_done"]])
        try:
            hit = client.run_to_breakpoint(timeout)
        except Exception as exc:
            fail("cold load", "load_done", f"timeout: {exc}")
        if hit.get("pc") != syms["load_done"]:
            fail("cold load", "load_done", repr(hit))
        monitor.clear(client, ids)

        ids = monitor.setup(client, [syms["load_done_publish"]])
        try:
            hit = client.run_to_breakpoint(timeout)
        except Exception as exc:
            fail("cold publish", "load_done_publish", f"timeout: {exc}")
        if hit.get("pc") != syms["load_done_publish"]:
            fail("cold publish", "load_done_publish", repr(hit))
        monitor.clear(client, ids)

        client.call("inject_key", {"key": key, "action": "press"})
        ids = monitor.setup(client, [syms["pft_ready"]])
        try:
            hit = client.run_to_breakpoint(timeout)
        except Exception as exc:
            fail("credit edge", f"key-{key}-pft-ready", f"timeout: {exc}")
        event = monitor_probe.read_byte(client, PRES_EVENT)
        if hit.get("pc") != syms["pft_ready"] or not (event & 0x06):
            fail("credit edge", f"key-{key}-pft-ready",
                 f"hit={hit} event={event:02x}")
        monitor.clear(client, ids)

        ids = monitor.setup(client, [syms["load_done_dynamic_high"],
                                     syms["install_demo_runtime"]])
        try:
            hit = client.run_to_breakpoint(timeout)
        except Exception as exc:
            fail("high-score load", f"key-{key}-dynamic", f"timeout: {exc}")
        mode = monitor_probe.read_byte(client, PRES_MODE)
        screen = monitor_probe.read_byte(client, PRES_SCREEN)
        credits = monitor_probe.read_byte(client, PRES_CREDITS)
        if (hit.get("pc") not in (syms["load_done_dynamic_high"],
                                   syms["install_demo_runtime"])
                or mode != 1
                or screen != 3 or credits != 1):
            fail("high-score load", f"key-{key}-dynamic",
                 f"hit={hit} mode={mode:02x} screen={screen:02x}")
        high_id, install_id = ids
        if hit.get("pc") == syms["load_done_dynamic_high"]:
            monitor.clear(client, [high_id])
            try:
                hit = client.run_to_breakpoint(timeout)
            except Exception as exc:
                fail("auxiliary dispatch", f"key-{key}-install-entry", f"timeout: {exc}")
            if hit.get("pc") != syms["install_demo_runtime"]:
                fail("auxiliary dispatch", f"key-{key}-install-entry", repr(hit))
        monitor.clear(client, [high_id, install_id])

        ids = monitor.setup(client, [syms["install_aux_runtime_byte"],
                                     syms["load_done_dynamic_ready"]])
        try:
            hit = client.run_to_breakpoint(timeout)
        except Exception as exc:
            fail("auxiliary dispatch", f"key-{key}-return", f"timeout: {exc}")
        if hit.get("pc") == syms["install_aux_runtime_byte"]:
            monitor.clear(client, ids[:1])
            try:
                hit = client.run_to_breakpoint(timeout)
            except Exception as exc:
                fail("auxiliary dispatch", f"key-{key}-return", f"timeout: {exc}")
        if hit.get("pc") != syms["load_done_dynamic_ready"]:
            fail("auxiliary dispatch", f"key-{key}-return", repr(hit))

        client.call("inject_key", {"key": key, "action": "release"})
        monitor.clear(client, ids)
        return {
            "key": key,
            "credits": credits,
            "screen": screen,
            "mode": mode,
            "runtime_pc": 0x0300,
            "return_pc": syms["load_done_dynamic_ready"],
            "demo_runtime_sha256": digest(demo),
        }
    finally:
        client.close()
        monitor_probe.stop(process)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xroar", type=Path,
                        default=ROOT / "docs/reference/xroar/src/xroar")
    parser.add_argument("--rom", type=Path, default=ROOT / "build/ladybug.rom")
    parser.add_argument("--output", type=Path,
                        default=ROOT / "build/feat003-complete-credit-dispatch.json")
    parser.add_argument("--timeout", type=float, default=40.0)
    args = parser.parse_args()

    manifest = json.loads(MANIFEST.read_text(encoding="ascii"))
    if manifest.get("complete_profile") is not True:
        fail("artifact", "complete-profile", "manifest is not complete")
    syms = symbols(PRESENTATION_MAP)
    demo = DEMO_RUNTIME.read_bytes()
    monitor = monitor_probe.load_monitor()
    results = [run_key(monitor, args.xroar, args.rom, syms, demo, key, args.timeout)
               for key in (5, 6)]
    evidence = {
        "schema": "ladybug-feat003-complete-credit-dispatch-v1",
        "rom_sha256": digest(args.rom.read_bytes()),
        "timeout_seconds": args.timeout,
        "results": results,
    }
    args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="ascii")
    print("FEAT-003 complete credit dispatch: keys 5 and 6 reached high-score "
          "load and executed the installed demo runtime")


if __name__ == "__main__":
    main()
