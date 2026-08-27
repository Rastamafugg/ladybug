#!/usr/bin/env python3
"""Capture the natural cold complete-profile presentation sequence."""

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
INSTRUCTION_RUNTIME = ROOT / "build/ladybug-instruction-runtime.bin"
DEMO_RUNTIME = ROOT / "build/ladybug-demo-runtime.bin"
PRES_MODE = 0x00A5
PRES_SCREEN = 0x00A6
PRES_TIMER = 0x00B0
PRES_DEMO_DIR = 0x00DD
STAGE = 0x0024
PRESENTATION_MODE_INSTRUCTIONS = 3
PRESENTATION_MODE_LEVEL = 6
PRESENTATION_MODE_DEMO = 4


def symbols(path: Path) -> dict[str, int]:
    return {
        name: int(value, 16)
        for name, value in re.findall(
            r"^Symbol: (\w+) .* = ([0-9A-Fa-f]+)$",
            path.read_text(encoding="ascii"), re.MULTILINE,
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
                        default=ROOT / "build/feat004-complete-natural.json")
    parser.add_argument("--timeout", type=float, default=40.0,
                        help="deadline for each natural marker phase")
    args = parser.parse_args()

    manifest = json.loads(PRESENTATION_MANIFEST.read_text(encoding="ascii"))
    if manifest.get("complete_profile") is not True:
        fail("artifact", "complete-profile", "presentation manifest is not complete")
    module_syms = symbols(PRESENTATION_MAP)
    required_symbols = (
        "start_screen_no_instruction_install",
        "load_done_publish",
        "level_tick",
        "demo_tick",
    )
    missing = [name for name in required_symbols if name not in module_syms]
    if missing:
        fail("artifact", "symbols", ", ".join(missing))

    expected_rom_hash = digest(args.rom.read_bytes())
    expected_instruction = INSTRUCTION_RUNTIME.read_bytes()
    expected_demo = DEMO_RUNTIME.read_bytes()
    expected_frames = manifest["static_frame_sha256"]
    monitor = monitor_probe.load_monitor()
    process, client = monitor_probe.launch_fast(monitor, args.xroar, args.rom)
    evidence: dict[str, object] = {
        "schema": "ladybug-feat004-complete-natural-v1",
        "rom_sha256": expected_rom_hash,
        "deadline_seconds": args.timeout,
        "events": [],
    }
    breakpoints = [module_syms[name] for name in required_symbols]
    ids: list[int] = []
    try:
        ids = monitor.setup(client, breakpoints)
        seen_publications: set[int] = set()
        sequence: list[str] = []
        instructions_seen = False
        level_seen = False
        demo_seen = False
        for _ in range(512):
            try:
                hit = client.run_to_breakpoint(args.timeout)
            except Exception as exc:
                fail("natural sequence", "next-marker", f"timeout: {exc}")
            pc = hit.get("pc")
            if pc == module_syms["start_screen_no_instruction_install"]:
                screen = monitor_probe.read_byte(client, PRES_SCREEN)
                event = {"marker": "start_screen", "screen": screen}
                cast_events = evidence["events"]
                assert isinstance(cast_events, list)
                cast_events.append(event)
                if not sequence or sequence[-1] != f"request-{screen}":
                    sequence.append(f"request-{screen}")
                if screen == 1 and not instructions_seen:
                    instructions_seen = True
                    sequence.append("instructions")
                    destination = monitor_probe.read_bytes(
                        client, 0x0300, len(expected_instruction)
                    )
                    evidence["instructions"] = {
                        "screen": screen,
                        "mode_before_publication": monitor_probe.read_byte(
                            client, PRES_MODE
                        ),
                        "runtime_destination_sha256": digest(destination),
                    }
                    if destination != expected_instruction:
                        fail("instructions", "runtime-destination", "hash mismatch")
            elif pc == module_syms["load_done_publish"]:
                screen = monitor_probe.read_byte(client, PRES_SCREEN)
                if screen in seen_publications:
                    continue
                seen_publications.add(screen)
                owners = {
                    str(owner): digest(monitor_probe.read_owner(client, owner))
                    for owner in (0, 1)
                }
                expected = expected_frames[screen] if screen in (1, 2) else None
                if expected is not None and not any(value == expected for value in owners.values()):
                    fail("visible screen", f"map-{screen}",
                         f"owners={owners} expected={expected} absent")
                event = {
                    "marker": "load_done_publish",
                    "screen": screen,
                    "owner_sha256": owners,
                    "static_hash_checked": expected is not None,
                }
                cast_events = evidence["events"]
                assert isinstance(cast_events, list)
                cast_events.append(event)
                sequence.append(f"visible-{screen}")
            elif pc == module_syms["level_tick"]:
                screen = monitor_probe.read_byte(client, PRES_SCREEN)
                mode = monitor_probe.read_byte(client, PRES_MODE)
                if (screen, mode) != (2, PRESENTATION_MODE_LEVEL):
                    continue
                timer = monitor_probe.read_word(client, PRES_TIMER)
                if not level_seen and timer >= 179:
                    level_seen = True
                    sequence.append("level-start")
                    evidence["level_start"] = {
                        "screen": screen,
                        "mode": mode,
                        "stage_before_gameplay_init": monitor_probe.read_byte(client, STAGE),
                        "timer": timer,
                    }
            elif pc == module_syms["demo_tick"]:
                mode = monitor_probe.read_byte(client, PRES_MODE)
                if mode != PRESENTATION_MODE_DEMO:
                    continue
                if not demo_seen:
                    demo_seen = True
                    sequence.append("demo")
                    destination = monitor_probe.read_bytes(
                        client, 0x0300, len(expected_demo)
                    )
                    evidence["demo"] = {
                        "mode": mode,
                        "direction": monitor_probe.read_byte(client, PRES_DEMO_DIR),
                        "runtime_destination_sha256": digest(destination),
                    }
                    if destination != expected_demo:
                        fail("demo", "runtime-destination", "hash mismatch")
                    break

        if not (instructions_seen and level_seen and demo_seen):
            fail("natural sequence", "attract-instructions-level-demo",
                 f"sequence={sequence}")
        required_visible = {"visible-0", "visible-1", "visible-2"}
        if not required_visible.issubset(sequence):
            fail("visible sequence", "attract-instructions-level",
                 f"sequence={sequence}")
        evidence["sequence"] = sequence
    finally:
        try:
            monitor.clear(client, ids)
        except (OSError, ValueError):
            pass
        try:
            client.close()
        except OSError:
            pass
        monitor_probe.stop(process)

    args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="ascii")
    print("FEAT-004 complete natural: attract, instructions, level-start, and demo passed")
    print(f"evidence={args.output}")


if __name__ == "__main__":
    main()
