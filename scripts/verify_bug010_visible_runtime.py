#!/usr/bin/env python3
"""Verify BUG-010 visible title phases and the natural instructions handoff."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_presentation import (  # noqa: E402
    MAP_FILES, MAP_NAMES, coin_tile, compile_attract_surfaces,
    compile_map, compile_screen, compose_attract_frames, load_chars,
    parse_attract_actors, title_framebuffer,
)


ROOT = Path(__file__).resolve().parents[1]
MONITOR_PATH = ROOT / "scripts/verify_bug009_monitor_input.py"
MANIFEST = ROOT / "build/ladybug-presentation.json"
MODULE = ROOT / "build/ladybug-presentation-runtime.bin"
HELPER = ROOT / "build/ladybug-perimeter-reset-helper.bin"
PRESENTATION_ENTRY = 0x1900
PAR1 = 0xFFA1
PAR5 = 0xFFA5
FB_FRONT = 0x008F
PENDING = 0x0091
COMMIT_SEQ = 0x0092
PRES_MODE = 0x00A5
PRES_SCREEN = 0x00A6
PRES_CELL = 0x00AA
PRES_TIMER = 0x00B0
PRES_ACTOR_PHASE = 0x00D3
VISIBLE_BYTES = 30720


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def module_symbol(name: str) -> int:
    text = (ROOT / "build/ladybug-presentation-runtime.map").read_text(encoding="utf-8")
    match = re.search(rf"^Symbol: {re.escape(name)} .* = ([0-9A-Fa-f]+)$", text,
                      re.MULTILINE)
    if not match:
        raise SystemExit(f"BUG-010 visible runtime: missing module symbol {name}")
    return int(match.group(1), 16)


def load_monitor():
    spec = importlib.util.spec_from_file_location("bug009_monitor", MONITOR_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load monitor client")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_bytes(client, address: int, length: int) -> bytes:
    return bytes.fromhex(client.call("read_memory", {
        "addr": address, "length": length,
    })["data"])


def read_byte(client, address: int) -> int:
    return read_bytes(client, address, 1)[0]


def read_owner(client, owner: int) -> bytes:
    saved = [read_byte(client, PAR1 + index) for index in range(4)]
    base = 0x30 if owner == 0 else 0x2C
    output = bytearray()
    try:
        for index in range(4):
            client.call("write_memory", {
                "addr": PAR1 + index, "data": f"{base + index:02x}",
            })
            count = min(0x2000, VISIBLE_BYTES - len(output))
            output.extend(read_bytes(client, 0x2000 + index * 0x2000, count))
    finally:
        for index, page in enumerate(saved):
            client.call("write_memory", {
                "addr": PAR1 + index, "data": f"{page:02x}",
            })
    return bytes(output)


def state(client) -> dict[str, int]:
    return {
        "mode": read_byte(client, PRES_MODE),
        "screen": read_byte(client, PRES_SCREEN),
        "cell": int.from_bytes(read_bytes(client, PRES_CELL, 2), "big"),
        "timer": int.from_bytes(read_bytes(client, PRES_TIMER, 2), "big"),
        "actor_phase": read_byte(client, PRES_ACTOR_PHASE),
        "front": read_byte(client, FB_FRONT),
        "pending": read_byte(client, PENDING),
        "commit_seq": int.from_bytes(read_bytes(client, COMMIT_SEQ, 2), "big"),
    }


def expected_frames() -> tuple[list[bytes], list[bytes]]:
    tiled = ROOT / "tiled"
    chars_path = ROOT / "assets/arcade/chars.json"
    sprites_path = ROOT / "assets/arcade/sprites.json"
    chars = load_chars(chars_path)
    _, gameplay_tiles, *_ = compile_screen(
        tiled / "coco-screen.tmx", ROOT / "assets/arcade/maze.json",
        chars_path, sprites_path,
    )
    tiles: list[bytes] = []
    tile_ids: dict[bytes, int] = {}
    maps = [compile_map(tiled / MAP_FILES[name], chars, tiles, tile_ids)[0]
            for name in MAP_NAMES]
    coin = coin_tile()
    if coin not in tiles:
        tiles.append(coin)
    gameplay_ids = {tile: index for index, tile in enumerate(gameplay_tiles)}
    order = ([index for index, tile in enumerate(tiles) if tile not in gameplay_ids] +
             [index for index, tile in enumerate(tiles) if tile in gameplay_ids])
    remap = {old: new for new, old in enumerate(order)}
    maps = [bytes(remap[value] for value in data) for data in maps]
    tiles = [tiles[index] for index in order]
    actors = parse_attract_actors(tiled / MAP_FILES["attract"])
    sprites = json.loads(sprites_path.read_text(encoding="utf-8"))
    surfaces = compile_attract_surfaces(maps[0], tiles, sprites, actors)
    return compose_attract_frames(maps[0], tiles, surfaces, actors), [
        bytes(title_framebuffer(data, tiles)) for data in maps
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xroar", type=Path, required=True)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=30.0)
    args = parser.parse_args()
    manifest = json.loads(MANIFEST.read_text(encoding="ascii"))
    expected_phases = manifest["attract_actor_surfaces"]["phase_frame_sha256"]
    expected_instructions = manifest["static_frame_sha256"][1]
    expected_surfaces = manifest["attract_actor_surfaces"]["sha256"]
    expected_title_frames, expected_static_frames = expected_frames()
    attract_next = module_symbol("attract_next")
    instructions_tick = module_symbol("instructions_tick")
    load_done = module_symbol("load_done")

    monitor = load_monitor()
    process, client = monitor.launch(args.xroar, args.rom, monitor.free_port())
    try:
        boot_id = monitor.setup(client, [PRESENTATION_ENTRY])
        boot_hit = client.run_to_breakpoint(args.timeout)
        if boot_hit.get("pc") != PRESENTATION_ENTRY:
            raise SystemExit(f"BUG-010 visible runtime: expected presentation entry, got {boot_hit}")
        authored_cold = (ROOT / "build/ladybug-presentation-cold.bin").read_bytes()
        saved_par5 = read_byte(client, PAR5)
        cold = bytearray()
        for page, count in ((0x3A, min(0x2000, len(authored_cold))),
                            (0x3B, max(0, len(authored_cold) - 0x2000))):
            if count == 0:
                continue
            client.call("write_memory", {"addr": PAR5, "data": f"{page:02x}"})
            cold.extend(read_bytes(client, 0xA000, count))
        client.call("write_memory", {"addr": PAR5, "data": f"{saved_par5:02x}"})
        monitor.clear(client, boot_id)
        boot_cold = {
            "live_sha256": digest(cold),
            "authored_sha256": digest(authored_cold),
            "diff_count": sum(actual != expected for actual, expected
                              in zip(cold, authored_cold)),
        }
        breakpoint_ids = monitor.setup(client, [attract_next, instructions_tick, load_done])
        load_snapshots = []
        first = client.run_to_breakpoint(args.timeout)
        while first.get("pc") == load_done:
            snapshot_state = state(client)
            mapped_pages = [read_byte(client, PAR1 + index) for index in range(4)]
            mapped_frame = read_bytes(client, 0x2000, VISIBLE_BYTES)
            back = read_owner(client, read_byte(client, 0x0090))
            load_snapshots.append({
                "state": snapshot_state,
                "back": read_byte(client, 0x0090),
                "frame_sha256": digest(back),
                "mapped_pages": mapped_pages,
                "mapped_frame_sha256": digest(mapped_frame),
                "static_diff_count": sum(actual != expected for actual, expected
                                         in zip(back, expected_static_frames[0])),
                "nonzero": sum(value != 0 for value in back),
                "cold_tile_68": read_bytes(client, 0xA000 + 68 * 32, 32).hex(),
            })
            first = client.run_to_breakpoint(args.timeout)
        client.call("clear_breakpoint", {"id": breakpoint_ids.pop()})
        if first.get("pc") != attract_next:
            raise SystemExit(f"BUG-010 visible runtime: expected attract handoff, got {first}")
        title_state = state(client)
        title = read_owner(client, title_state["front"])
        title_hash = digest(title)
        expected_title = expected_phases[title_state["actor_phase"]]
        expected_title_bytes = expected_title_frames[title_state["actor_phase"]]
        crop_hashes = []
        for actor in manifest["attract_actor_surfaces"]["actors"]:
            offset = actor["destination"] - 0x2000
            crop = b"".join(title[offset + row * 160:offset + row * 160 + 8]
                            for row in range(16))
            crop_hashes.append(digest(crop))
        expected_crop_phase = title_state["actor_phase"]
        if expected_crop_phase == 3:
            expected_crop_phase = 1
        expected_crops = manifest["attract_actor_surfaces"]["phase_crop_sha256"][expected_crop_phase]
        if title_state["timer"] != 558 or title_state["pending"] != 0:
            raise SystemExit(f"BUG-010 visible runtime: invalid final title state {title_state}")
        if title_hash != expected_title:
            # Rebuild expected bytes from the resident phase surfaces is already
            # proven statically; report the visible mismatch boundary here.
            differing = [index for index, (actual, other) in enumerate(zip(title, expected_title_bytes))
                         if actual != other]
            samples = [(index, title[index], expected_title_bytes[index])
                       for index in differing[:8]]
            missing = [index for index in differing
                       if title[index] == 0 and expected_title_bytes[index] != 0]
            unexpected = [index for index in differing
                          if title[index] != 0 and expected_title_bytes[index] == 0]
            changed = [index for index in differing
                       if title[index] != 0 and expected_title_bytes[index] != 0]
            rows = [index // 160 for index in differing]
            columns = [index % 160 for index in differing]
            static_diffs = [sum(actual != expected for actual, expected in zip(title, frame))
                            for frame in expected_static_frames]
            raise SystemExit(
                "BUG-010 visible runtime: final visible title pixels differ "
                f"state={title_state} actual={title_hash} expected={expected_title} "
                f"expected_diff_count={len(differing)} samples={samples} "
                f"actor_crops_match={crop_hashes == expected_crops} "
                f"nonzero_actual={sum(value != 0 for value in title)} "
                f"nonzero_expected={sum(value != 0 for value in expected_title_bytes)} "
                f"missing={len(missing)} unexpected={len(unexpected)} changed={len(changed)} "
                f"bounds=({min(columns)},{min(rows)})-({max(columns)},{max(rows)}) "
                f"static_screen_diff_counts={static_diffs} load_snapshots={load_snapshots}"
            )

        saved_par5 = read_byte(client, PAR5)
        client.call("write_memory", {"addr": PAR5, "data": "3c"})
        live_surfaces = read_bytes(client, 0xA000, 2688)
        live_metadata = read_bytes(client, 0xAA80, 20)
        client.call("write_memory", {"addr": PAR5, "data": f"{saved_par5:02x}"})
        if digest(live_surfaces) != expected_surfaces:
            raise SystemExit("BUG-010 visible runtime: live expanded surface hash differs")

        instruction_samples = []
        for _ in range(3):
            hit = client.run_to_breakpoint(args.timeout)
            if hit.get("pc") != instructions_tick:
                raise SystemExit(f"BUG-010 visible runtime: expected instructions tick, got {hit}")
            sample_state = state(client)
            frame = read_owner(client, sample_state["front"])
            static_differing = [index for index, (actual, expected) in
                                enumerate(zip(frame, expected_static_frames[1]))
                                if actual != expected]
            instruction_samples.append({
                "state": sample_state,
                "frame_sha256": digest(frame),
                "static_diff_count": len(static_differing),
                "static_diff_samples": [(index, frame[index], expected_static_frames[1][index])
                                        for index in static_differing[:16]],
            })
        monitor.clear(client, breakpoint_ids)
        if instruction_samples[0]["state"]["mode"] != 3:
            raise SystemExit("BUG-010 visible runtime: instructions mode was not published")
        if instruction_samples[0]["frame_sha256"] != expected_instructions:
            raise SystemExit(
                "BUG-010 visible runtime: first instructions frame is not static target "
                f"expected={expected_instructions} boot_cold={boot_cold} "
                f"load_snapshots={load_snapshots} samples={instruction_samples}"
            )
        if any(sample["frame_sha256"] == title_hash for sample in instruction_samples):
            raise SystemExit("BUG-010 visible runtime: stale title republished during instructions")
        if len({sample["frame_sha256"] for sample in instruction_samples}) < 2:
            raise SystemExit("BUG-010 visible runtime: instructions actor did not update")

        module = MODULE.read_bytes()
        helper = HELPER.read_bytes()
        result = {
            "schema": "ladybug-bug010-visible-runtime-v1",
            "deadline_seconds": args.timeout,
            "rom_sha256": digest(args.rom.read_bytes()),
            "title": {"state": title_state, "frame_sha256": title_hash},
            "load_snapshots": load_snapshots,
            "boot_cold": boot_cold,
            "expected_phase_frame_sha256": expected_phases,
            "instructions": instruction_samples,
            "expanded_surfaces": {
                "bytes": len(live_surfaces), "sha256": digest(live_surfaces),
            },
            "metadata_sha256": digest(live_metadata),
            "module": {"bytes": len(module), "sha256": digest(module)},
            "helper": {"bytes": len(helper), "sha256": digest(helper)},
            "pass": True,
        }
        args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="ascii")
        print(
            "BUG-010 visible runtime pass: exact final title, timer 558, no pending "
            "publication, exact first instructions frame, and subsequent actor update"
        )
    finally:
        client.close()
        monitor.stop(process)
        process.wait(timeout=2)


if __name__ == "__main__":
    main()
