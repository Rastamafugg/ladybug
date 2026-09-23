#!/usr/bin/env python3
"""Bounded current-ROM SPECIAL/EXTRA stage-handoff capture."""
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import verify_bug011_runtime as runtime
import verify_bug009_monitor_input as monitor

BUILD = ROOT / "build"
OUT = ROOT / "repro/rsch013-current-rom-word.json"


def main():
    rom = BUILD / "ladybug.rom"
    evidence = {"rom_sha256": hashlib.sha256(rom.read_bytes()).hexdigest(),
                "deadline_seconds_per_phase": 40,
                "timeout_meaning": "named phase marker not reached", "phases": []}
    process, client = runtime.launch_fast(monitor, ROOT / "docs/reference/xroar/src/xroar", rom)
    syms = runtime.symbols(BUILD / "ladybug-presentation-runtime.map")
    main_syms = runtime.symbols(BUILD / "ladybug.map")

    def reach(name, table=syms):
        address = table[name]
        ids = monitor.setup(client, [address])
        print(f"phase={name} marker={address:04x} deadline=40s; timeout=marker-not-reached", flush=True)
        try:
            hit = client.run_to_breakpoint(40)
            if hit["pc"] != address:
                raise RuntimeError(f"unexpected {hit}")
        finally:
            monitor.clear(client, ids)
        evidence["phases"].append(name)

    def sample(label):
        masks = runtime.read_bytes(client, 0x3C, 2)
        front = runtime.read_byte(client, runtime.FB_FRONT)
        frame = runtime.read_owner(client, front)
        cells = {}
        for row, count in ((1, 7), (4, 5)):
            for col in range(1, count + 1):
                x, y = col * 8, row * 8
                tile = b"".join(frame[(y + dy) * 160 + x // 2:(y + dy) * 160 + x // 2 + 4] for dy in range(8))
                cells[f"{col},{row}"] = hashlib.sha256(tile).hexdigest()[:16]
        evidence[label] = {"stage": runtime.read_byte(client, 0x24),
            "masks": masks.hex(), "front": front, "frame_sha256": hashlib.sha256(frame).hexdigest(), "hud_tile_sha256_prefix": cells}

    try:
        reach("presentation_flow_tick")
        presentation = (BUILD / "ladybug-presentation-runtime.bin").read_bytes()
        evidence["identity"] = {"presentation": runtime.read_bytes(client, 0x1900, len(presentation)) == presentation}
        if not evidence["identity"]["presentation"]:
            raise RuntimeError("presentation identity mismatch")
        reach("demo_run")
        client.call("inject_key", {"key": 5, "action": "press"})
        reach("credit_tick")
        client.call("inject_key", {"key": 5, "action": "release"})
        client.call("inject_key", {"key": 1, "action": "press"})
        reach("normal_game")
        client.call("inject_key", {"key": 1, "action": "release"})
        runtime_rom = (BUILD / "ladybug-runtime.rom").read_bytes()
        word_addr = main_syms["draw_word_progress_hud"]
        evidence["identity"]["word_code"] = runtime.read_bytes(client, word_addr, 32) == runtime_rom[word_addr - 0xC000:word_addr - 0xC000 + 32]
        if not evidence["identity"]["word_code"]:
            raise RuntimeError("word routine identity mismatch")
        for _ in range(64):
            if runtime.read_byte(client, 0xA0) == 0:
                break
            reach("normal_game")
        else:
            raise RuntimeError("entry animation did not finish")
        runtime.write_byte(client, 0x3C, 0x49)
        runtime.write_byte(client, 0x3D, 0x11)
        sample("part1_seeded")
        runtime.write_byte(client, 0x25, 1)
        runtime.write_byte(client, 0x33, 0)
        client.call("inject_key", {"key": 0x2B, "action": "press"})
        for _ in range(64):
            reach("normal_stage")
            if runtime.read_byte(client, 0x26):
                break
        else:
            raise RuntimeError("final-dot stage request missing")
        client.call("inject_key", {"key": 0x2B, "action": "release"})
        sample("part2_request")
        reach("level_tick")
        if runtime.read_byte(client, 0x91):
            reach("level_tick")
        sample("part2_visible")
        evidence["success_marker"] = "first committed Part 2 image"
        reach("normal_game")
        sample("part2_gameplay_entry")
        for _ in range(3):
            reach("normal_game")
        sample("part2_gameplay_published")
    except Exception as exc:
        evidence["failure"] = f"{type(exc).__name__}: {exc}"
    finally:
        client.close()
        monitor.stop(process)
        OUT.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in evidence.items() if k not in ("part1_seeded", "part2_visible", "part2_request")}, indent=2))


if __name__ == "__main__":
    main()
