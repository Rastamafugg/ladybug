#!/usr/bin/env python3
"""BUG-035 pixel oracle and bounded runtime checks using the existing harness."""
from pathlib import Path
import hashlib
import json
import sys
import xml.etree.ElementTree as ET

import build_presentation as p
import build_screen as screen
import verify_bug011_runtime as runtime
from gmc_lzss import decompress

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
OUT = BUILD / "bug035"
NAMES = ("CUCUMBER", "EGGPLANT", "CARROT", "RADISH", "PARSLEY", "TOMATO",
         "PUMPKIN", "BAMBOO SHOOT", "JAPANESE RADISH", "MUSHROOM", "POTATO",
         "ONION", "CHINESE CABBAGE", "TURNIP", "RED PEPPER", "CELERY",
         "SWEET POTATO", "HORSERADISH")


def stamp(frame, x, y, rows, colours):
    for dy, row in enumerate(rows):
        for dx, pen in enumerate(row):
            offset = (y + dy) * 160 + (x + dx) // 2
            value = colours[pen]
            frame[offset] = ((frame[offset] & 15) | value << 4) if (x + dx) % 2 == 0 else ((frame[offset] & 240) | value)


def text(frame, col, row, value, colour, chars):
    for i, char in enumerate(value):
        code = 255 if char == " " else int(char) if char.isdigit() else ord(char) - 55
        stamp(frame, (col + i) * 8, row * 8, p.rotate_ccw(chars[code]), (0, colour, colour, colour))


def stage_expected(base, stage, chars, sprites):
    frame = bytearray(base)
    text(frame, 22, 4, str(stage), 3, chars)
    text(frame, 33, 9, str(stage), 3, chars)
    index = min(max(stage, 1), 18) - 1
    text(frame, 12, 9, NAMES[index].center(16), 2, chars)
    text(frame, 19, 7, str(1000 + index * 500), 5, chars)
    text(frame, 35, 13, str(1000 + index * 500), 5, chars)
    text(frame, 16, 20, "GOOD LUCK", 1, chars)
    # Independent oracle: gameplay attr0 pairs encode source pens 0/C/5/2.
    rows = p.rotate_ccw(sprites[screen.VEGETABLE_CODES[index]])
    for col, row in ((16, 6), (32, 12)):
        stamp(frame, col * 8, row * 8, rows, (0, 12, 5, 2))
    return bytes(frame)


def compare(actual, expected, label):
    if actual != expected:
        differences = [i for i, (a, b) in enumerate(zip(actual, expected)) if a != b]
        OUT.mkdir(exist_ok=True)
        (OUT / (label + "-actual.bin")).write_bytes(actual)
        (OUT / (label + "-expected.bin")).write_bytes(expected)
        raise AssertionError(f"{label}: {len(differences)} byte differences; first {differences[:12]}")


def main():
    OUT.mkdir(exist_ok=True)
    manifest = json.loads((BUILD / "ladybug-presentation.json").read_text())
    chars = p.load_chars(ROOT / "assets/arcade/chars.json")
    sprites = json.loads((ROOT / "assets/arcade/sprites.json").read_text())
    base_frames = []
    for name in p.MAP_NAMES:
        tiles, ids = [], {}
        cells, _ = p.compile_map(ROOT / "tiled" / p.MAP_FILES[name], chars, tiles, ids, False, True)
        base_frames.append(bytes(p.title_framebuffer(cells, tiles)))
    expected_title = bytearray(base_frames[0])
    for col, row, value, colour in ((15, 15, "INSERT COIN", 9), (13, 18, "1", 2),
                                   (21, 18, "1", 2), (15, 18, "COIN", 6), (23, 18, "PLAY", 6)):
        text(expected_title, col, row, value, colour, chars)
    compare(base_frames[0], expected_title, "static-title-text")
    expected_instruction = bytearray(base_frames[1])
    for col, row, value in ((15, 5, "INSTRUCTION"), (17, 17, "10"),
                             (20, 17, "POINTS"), (16, 20, "100"), (20, 20, "POINTS")):
        text(expected_instruction, col, row, value, 6, chars)
    compare(base_frames[1], expected_instruction, "static-instruction-text")
    # Shell source pen differs for the two top-row collectibles.
    stage_path = ROOT / "tiled" / p.MAP_FILES["level-start"]
    stage_root = ET.parse(stage_path).getroot()
    for layer in stage_root.findall("layer"):
        for (x, y), gid in p.layer_records(layer).items():
            if 17 <= x <= 22 and 11 <= y <= 18:
                rows = p.rotate_ccw(chars[p.raw_char_code(stage_root, stage_path, gid)])
                for dy, row in enumerate(rows):
                    for dx, pen in enumerate(row):
                        if pen == (2 if y <= 12 else 1):
                            byte = base_frames[2][(y * 8 + dy) * 160 + x * 4 + dx // 2]
                            assert (byte >> 4 if dx % 2 == 0 else byte & 15) == 11
    surfaces = decompress((BUILD / "ladybug-attract-actor-underlays.bin").read_bytes(), 7296)
    title_path = ROOT / "tiled/coco-attract-screen.tmx"
    title_root = ET.parse(title_path).getroot()
    logo_roots = manifest["attract_actor_surfaces"]["logo_roots"]
    for phase in range(3):
        expected = bytearray(base_frames[0])
        layer = next(l for l in title_root.findall("layer")
                     if l.get("name") == f"Logo Frame {1 + (phase & 1)}")
        for (x, y), gid in p.layer_records(layer).items():
            code = p.raw_char_code(title_root, title_path, gid)
            rows = p.transform(p.rotate_ccw(chars[code]), bool(gid & p.FLIP_H), bool(gid & p.FLIP_V))
            stamp(expected, x * 8, y * 8, rows, (0, 6, 11, 11))
        for i, (x, y) in enumerate(logo_roots):
            actual = surfaces[(phase * 19 + 7 + i) * 128:(phase * 19 + 8 + i) * 128]
            compare(actual, runtime.frame_tile(expected, p.framebuffer_destination((x, y)), 8, 16), f"logo-{phase}-{i}")
    monitor = runtime.load_monitor()
    process, client = runtime.launch_fast(monitor, ROOT / "docs/reference/xroar/src/xroar", BUILD / "ladybug.rom")
    syms = runtime.symbols(BUILD / "ladybug-presentation-runtime.map")
    evidence = {"rom_sha256": runtime.digest((BUILD / "ladybug.rom").read_bytes()), "phases": []}
    last_marker = None

    def reach(name, table=syms):
        nonlocal last_marker
        address = table[name]
        ids = monitor.setup(client, [address])
        if last_marker != name:
            print(f"phase={name} marker={address:04x} deadline=40s; timeout=marker-not-reached", flush=True)
        last_marker = name
        try:
            hit = client.run_to_breakpoint(40)
            assert hit["pc"] == address, hit
        finally:
            monitor.clear(client, ids)

    def owner_frame():
        return runtime.read_owner(client, runtime.read_byte(client, runtime.FB_FRONT))

    def level_frame():
        reach("level_tick")
        if runtime.read_byte(client, 0x91):
            reach("level_tick")
        return owner_frame()

    try:
        reach("presentation_flow_tick")
        compare(runtime.read_bytes(client, 0x1900, 1280), (BUILD / "ladybug-presentation-runtime.bin").read_bytes(), "module-identity")
        saved = runtime.read_byte(client, runtime.PAR5)
        runtime.write_byte(client, runtime.PAR5, 0x23)
        helper = (BUILD / "ladybug-highscore-helper.bin").read_bytes()
        compare(runtime.read_bytes(client, 0xAC40, len(helper)), helper, "helper-identity")
        runtime.write_byte(client, runtime.PAR5, 0x3C)
        surfaces = decompress((BUILD / "ladybug-attract-actor-underlays.bin").read_bytes(), 7296)
        compare(runtime.read_bytes(client, 0xA000, 7296), surfaces, "logo-delivery")
        compare(runtime.read_bytes(client, 0xBC80, 44), (BUILD / "ladybug-attract-actor-records.bin").read_bytes(), "logo-metadata")
        runtime.write_byte(client, runtime.PAR5, saved)
        reach("attract_tick")
        title_hashes = manifest["attract_actor_surfaces"]["phase_frame_sha256"]
        seen = set()
        for tick in range(45):
            frame = owner_frame()
            value = runtime.digest(frame)
            assert value in title_hashes, f"title tick {tick}: {value}"
            seen.add(value)
            if tick in (0, 16):
                (OUT / f"title-{tick}.bin").write_bytes(frame)
            reach("attract_tick")
        assert len(seen) >= 3
        evidence["phases"].append("natural title: all actor phases and both logo frames")
        reach("instructions_tick")
        for owner in (0, 1):
            assert runtime.digest(runtime.read_owner(client, owner)) == manifest["static_frame_sha256"][1]
        instruction_colours = set()
        point_surfaces = {}
        for value in (100, 300, 800):
            expected = bytearray(30720)
            text(expected, 16, 20, str(value), 6, chars)
            point_surfaces[runtime.frame_tile(expected, 0x8440, 12, 8)] = value
        seen_points = set()
        for tick in range(100):
            reach("instructions_runtime_return")
            frame = owner_frame()
            crop = runtime.frame_tile(frame, 0x7F34, 8, 16)
            colours = {v for byte in crop for v in (byte >> 4, byte & 15)} - {0}
            if colours and tick >= 3:
                instruction_colours.update(colours)
            points = runtime.frame_tile(frame, 0x8440, 12, 8)
            assert points in point_surfaces, "instruction value is not white 100/300/800"
            seen_points.add(point_surfaces[points])
            if tick == 80:
                (OUT / "instructions.bin").write_bytes(frame)
        assert instruction_colours == {1, 2, 3}, instruction_colours
        assert seen_points == {100, 300, 800}, seen_points
        evidence["phases"].append("natural instructions: both hydration owners and X red/yellow/blue")
        compare(level_frame(), stage_expected(base_frames[2], 1, chars, sprites), "natural-demo-part1")
        (OUT / "part-1.bin").write_bytes(owner_frame())
        # Entire instruction sequence ran naturally to the level screen.
        assert runtime.read_byte(client, 0x06AC) == 16  # all consumed targets
        assert runtime.read_byte(client, 0x06AE) == 3   # both persistent owners
        client.call("inject_key", {"key": 5, "action": "press"})
        reach("credit_tick")
        client.call("inject_key", {"key": 5, "action": "release"})
        client.call("inject_key", {"key": 1, "action": "press"})
        compare(level_frame(), stage_expected(base_frames[2], 1, chars, sprites), "live-part1")
        client.call("inject_key", {"key": 1, "action": "release"})
        reach("normal_game")
        # Seed only remaining counts; normal movement/eat_dot/check_stage_clear
        # must produce the stage request and normal_stage must increment it.
        runtime.write_byte(client, 0x25, 1)
        runtime.write_byte(client, 0x33, 0)
        compare(level_frame(), stage_expected(base_frames[2], 2, chars, sprites), "live-part2")
        assert runtime.read_byte(client, 0x24) == 2
        evidence["phases"].append("natural credit/start; seeded final-dot pickup through normal Part 1-to-2 transition")
        # Rare variant coverage follows the completed natural presentation path.
        # Call the identity-proven existing start_screen through a synthetic return.
        owners = set()
        for stage in (1,) + tuple(range(1, 20)) + (99, 100, 255):
            runtime.write_byte(client, 0x24, stage)
            runtime.write_byte(client, 0xA7, 2)
            regs = client.call("read_registers")
            stack = regs["s"] - 2
            runtime.write_word(client, stack, 0x1900)
            client.call("write_registers", {"pc": syms["start_screen"], "a": 2, "s": stack})
            compare(level_frame(), stage_expected(base_frames[2], stage, chars, sprites), f"part-{stage}")
            owners.add(runtime.read_byte(client, runtime.FB_FRONT))
            if stage in (2, 9, 13, 18, 100, 255):
                (OUT / f"part-{stage}.bin").write_bytes(owner_frame())
        evidence["phases"].append("forced panels: vegetables 1..18, clamp 19, parts 99/100/255")
        assert owners == {0, 1}, owners
        evidence["panel_owners"] = sorted(owners)
    finally:
        client.close()
        runtime.stop(process)
        (OUT / "summary.json").write_text(json.dumps(evidence, indent=2) + "\n")
    print("BUG-035 pixel/runtime checks passed")


if __name__ == "__main__":
    main()
