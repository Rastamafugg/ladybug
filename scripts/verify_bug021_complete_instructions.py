#!/usr/bin/env python3
"""Verify the complete-profile instructions install and natural transition."""

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


XROAR_DEFAULT = ROOT / "docs/reference/xroar/src/xroar"
ROM = ROOT / "build/ladybug.rom"
PRESENTATION_MAP = ROOT / "build/ladybug-presentation-runtime.map"
PRESENTATION_MANIFEST = ROOT / "build/ladybug-presentation.json"
LAYOUT = ROOT / "build/ladybug-sparse-layout.json"
INSTRUCTION_RUNTIME = ROOT / "build/ladybug-instruction-runtime.bin"
ACTOR_UNDERLAYS = ROOT / "build/ladybug-attract-actor-underlays.bin"
ACTOR_RECORDS = ROOT / "build/ladybug-attract-actor-records.bin"
DEMO_RUNTIME = ROOT / "build/ladybug-demo-runtime.bin"
PRES_IN = 0x00B5


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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xroar", type=Path, default=XROAR_DEFAULT)
    parser.add_argument("--rom", type=Path, default=ROM)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "build/bug021-complete-instructions.json")
    parser.add_argument("--timeout", type=float, default=40.0)
    args = parser.parse_args()

    manifest = json.loads(PRESENTATION_MANIFEST.read_text(encoding="ascii"))
    layout = json.loads(LAYOUT.read_text(encoding="ascii"))
    if manifest.get("complete_profile") is not True:
        fail("artifact", "complete_profile", "manifest is not complete profile")
    syms = symbols(PRESENTATION_MAP)
    expected_instruction = INSTRUCTION_RUNTIME.read_bytes()
    expected_stage = expected_instruction + DEMO_RUNTIME.read_bytes()
    if len(expected_instruction) != layout["instruction_runtime"]["bytes"]:
        fail("artifact", "instruction-runtime", "file/layout length mismatch")

    monitor = monitor_probe.load_monitor()
    process, client = monitor_probe.launch_fast(monitor, args.xroar, args.rom)
    evidence: dict[str, object] = {
        "schema": "ladybug-bug021-complete-instructions-v1",
        "rom_sha256": digest(args.rom.read_bytes()),
        "timeout_seconds": args.timeout,
    }
    try:
        ids = monitor.setup(client, [syms["presentation_flow_tick"]])
        try:
            hit = client.run_to_breakpoint(args.timeout)
        except Exception as exc:
            fail("boot", "presentation_flow_tick", f"timeout: {exc}")
        if hit.get("pc") != syms["presentation_flow_tick"]:
            fail("boot", "presentation_flow_tick", repr(hit))
        saved_par5 = monitor_probe.read_byte(client, monitor_probe.PAR5)
        monitor_probe.write_byte(client, monitor_probe.PAR5, 0x23)
        staged = monitor_probe.read_bytes(client, 0xA422, len(expected_stage))
        monitor_probe.write_byte(client, monitor_probe.PAR5, saved_par5)
        monitor.clear(client, ids)
        evidence["staged_sha256"] = digest(staged)
        if staged != expected_stage:
            fail("staging", "page23-bundle", "authored/staged bytes differ")

        ids = monitor.setup(client, [syms["attract_next"]])
        try:
            hit = client.run_to_breakpoint(args.timeout)
        except Exception as exc:
            fail("natural screen request", "attract_next", f"timeout: {exc}")
        if hit.get("pc") != syms["attract_next"]:
            fail("natural screen request", "attract_next", repr(hit))
        monitor.clear(client, ids)
        ids = monitor.setup(client, [syms["start_screen"]])
        try:
            hit = client.run_to_breakpoint(args.timeout)
        except Exception as exc:
            fail("natural screen request", "start_screen", f"timeout: {exc}")
        if hit.get("pc") != syms["start_screen"]:
            fail("natural screen request", "start_screen", repr(hit))
        registers = client.call("read_registers")
        requested = registers.get("a", registers.get("A"))
        if requested != 1:
            fail("natural screen request", "instructions-map-id-1",
                 f"A={requested!r}")
        monitor.clear(client, ids)

        ids = monitor.setup(client, [syms["instructions_tick"]])
        try:
            hit = client.run_to_breakpoint(args.timeout)
        except Exception as exc:
            fail("natural instructions transition", "instructions_tick",
                 f"timeout: {exc}")
        if hit.get("pc") != syms["instructions_tick"]:
            fail("natural instructions transition", "instructions_tick", repr(hit))
        installed = monitor_probe.read_bytes(
            client, 0x0300, len(expected_instruction)
        )
        evidence["installed_sha256"] = digest(installed)
        if installed != expected_instruction:
            fail("post-install", "instruction-runtime-destination",
                 "authored/destination bytes differ")
        screen = monitor_probe.read_byte(client, monitor_probe.PRES_SCREEN)
        mode = monitor_probe.read_byte(client, monitor_probe.PRES_MODE)
        stream_end = manifest["map_stream_offsets"][1] + manifest["map_stream_bytes"][1]
        pres_in = monitor_probe.read_word(client, PRES_IN)
        if (screen, mode, pres_in) != (1, 3, stream_end):
            fail("natural instructions transition", "instructions-state",
                 f"screen={screen} mode={mode} pres_in={pres_in:04x} "
                 f"expected_end={stream_end:04x}")
        expected_hash = manifest["static_frame_sha256"][1]
        hashes = {
            str(owner): digest(monitor_probe.read_owner(client, owner))
            for owner in (0, 1)
        }
        evidence.update({
            "screen": screen,
            "mode": mode,
            "stream_end": stream_end,
            "visible_owner_sha256": hashes,
        })
        if any(value != expected_hash for value in hashes.values()):
            fail("visible instructions", "both-owner-hashes",
                 f"live={hashes} expected={expected_hash}")
    finally:
        try:
            client.close()
        finally:
            monitor_probe.stop(process)
    args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="ascii")
    print("BUG-021 complete instructions: staged, installed, natural transition, "
          "and both-owner visible hash passed")


if __name__ == "__main__":
    main()
