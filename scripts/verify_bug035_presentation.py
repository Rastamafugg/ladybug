#!/usr/bin/env python3
"""BUG-035 pixel oracle and bounded runtime checks using the existing harness."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import sys
import xml.etree.ElementTree as ET

import build_presentation as p
import build_screen as screen
import verify_bug011_runtime as runtime
from gmc_lzss import decompress

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
OUT = BUILD / "bug035"
BUG060_EVIDENCE = (
    ROOT / "wiki/internal/tickets/evidence/rsch014-ready-060/parent-integration.json"
)
MENU_PROBE = (
    ROOT / "wiki/internal/tickets/evidence/rsch014-ready-menu/gdb_menu_probe.py"
)
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


def digest(data):
    return hashlib.sha256(data).hexdigest()


def verify_attract_fixture_hashes():
    partition = json.loads(BUG060_EVIDENCE.read_text(encoding="ascii"))
    expected = dict(partition["saved_user_tmx_input_sha256"])
    expected.update({
        filename: item["candidate_sha256"]
        for filename, item in partition["maps"].items()
    })
    actual = {}
    for filename, expected_hash in expected.items():
        value = digest((ROOT / "tiled" / filename).read_bytes())
        if value != expected_hash:
            raise AssertionError(f"read-only TMX fixture changed: {filename}: {value}")
        actual[filename] = value
    if len(actual) != 11:
        raise AssertionError(f"expected 11 read-only TMX fixtures, found {len(actual)}")
    return actual


def verify_attract_palette_contract(check_fixture_hashes=False):
    """Compare the retained palette with the current exact attract candidate."""
    map_path = ROOT / "tiled" / p.MAP_FILES["attract"]
    fixture_hashes = verify_attract_fixture_hashes() if check_fixture_hashes else None
    chars_path = ROOT / "assets/arcade/chars.json"
    chars = p.load_chars(chars_path)
    root, flattened, sources = p.flatten_map(map_path)
    row = []
    for x in range(13, 28):
        index = 15 * p.SCREEN_WIDTH + x
        gid = flattened[index] & p.GID_MASK
        code = p.raw_char_code(root, map_path, gid) if gid else -1
        if 0 <= code <= 35:
            row.append({
                "x": x, "code": code,
                "char": str(code) if code < 10 else chr(code + 55),
                "source_layer": sources[index],
                "current_pens": list(p.presentation_pen_map(
                    "attract", x, 15, sources[index], code,
                )),
            })
    by_x = {item["x"]: item for item in row}
    visible_text = "".join(by_x[x]["char"] if x in by_x else " " for x in range(13, 28))
    expected_cells = [13, 14, 15, 16, 17, 19, 21, 22, 24, 26, 27]
    if visible_text != "PRESS 5 OR 6 TO":
        raise AssertionError(f"attract row 15 text changed: {visible_text!r}")
    if [item["x"] for item in row] != expected_cells:
        raise AssertionError(f"attract row 15 glyph cells changed: {[item['x'] for item in row]}")
    if any(item["source_layer"] != "Attract Title and Prompts" for item in row):
        raise AssertionError("attract prompt glyph escaped its authored source layer")

    production_map = p.presentation_pen_map
    for label, arguments, expected in (
        ("wrong source layer", ("attract", 13, 15, "Background", 25), (0, 1, 2, 3)),
        ("space/non-alphanumeric", ("attract", 13, 15, "Attract Title and Prompts", 36), (0, 1, 2, 3)),
        ("other row", ("attract", 13, 14, "Attract Title and Prompts", 25), (0, 1, 2, 3)),
    ):
        if production_map(*arguments) != expected:
            raise AssertionError(f"BUG-063 palette ownership leaked to {label}")

    def prior_palette(role, x, y, source_layer="", raw_code=-1,
                      highscore_test_profile=False):
        if role == "attract" and y == 15:
            if 15 <= x <= 25:
                return (p.BLACK, p.PURPLE, p.PURPLE, p.PURPLE)
            return (0, 1, 2, 3)
        return production_map(
            role, x, y, source_layer, raw_code, highscore_test_profile,
        )

    def compile_static(palette):
        tiles = []
        previous = p.presentation_pen_map
        p.presentation_pen_map = palette
        try:
            mapping, _ = p.compile_map(map_path, chars, tiles, {})
        finally:
            p.presentation_pen_map = previous
        return bytes(p.title_framebuffer(mapping, tiles))

    before = compile_static(prior_palette)
    after = compile_static(production_map)
    if len(before) != 30720 or len(after) != 30720:
        raise AssertionError("attract static frame must be exactly 30,720 bytes")
    changed = [index for index, (old, new) in enumerate(zip(before, after)) if old != new]
    edge_cells = [13, 14, 26, 27]
    allowed = {
        y * 160 + x * 4 + byte
        for y in range(15 * 8, 16 * 8)
        for x in edge_cells
        for byte in range(4)
    }
    changed_cells = sorted({(index % 160) // 4 for index in changed})
    if len(changed) != 56 or not set(changed) <= allowed or changed_cells != edge_cells:
        raise AssertionError(
            f"palette delta must be 56 bytes in edge cells {edge_cells}; "
            f"got {len(changed)} bytes in cells {changed_cells}"
        )
    for item in row:
        glyph = p.rotate_ccw(chars[item["code"]])
        mapped_pens = {
            production_map(
                "attract", item["x"], 15, item["source_layer"], item["code"],
            )[int(pixel)]
            for line in glyph for pixel in line if pixel
        }
        if mapped_pens != {p.PURPLE}:
            raise AssertionError(
                f"attract glyph at x={item['x']} does not use only pen 9: {mapped_pens}"
            )
    proof = {
        "ticket": "BUG-063",
        "current_worktree": str(ROOT),
        "map_sha256": digest(map_path.read_bytes()),
        "character_asset_sha256": digest(chars_path.read_bytes()),
        "producer_sha256": digest((ROOT / "scripts/build_presentation.py").read_bytes()),
        "row15_visible_text": visible_text,
        "row15_text_cells": row,
        "candidate_rule": (
            "Attract Title and Prompts layer, row 15, actual alphanumeric glyphs; "
            "map all glyph pens to pen 9 (PURPLE)."
        ),
        "changed_cell_x": edge_cells,
        "changed_packed_frame_bytes": len(changed),
        "changed_bytes_confined_to_four_edge_glyph_cells": True,
        "baseline_frame_sha256": digest(before),
        "candidate_static_frame_sha256": digest(after),
        "runtime_or_full_build_claimed": False,
    }
    if fixture_hashes is not None:
        proof["readonly_tmx_fixture_sha256"] = fixture_hashes
        proof["verifier_sha256"] = digest(Path(__file__).read_bytes())
        proof["checked_commands"] = [
            "python -m py_compile scripts/build_presentation.py scripts/verify_bug035_presentation.py",
            "python scripts/verify_bug016_presentation_layers.py --tiled-dir tiled",
        ]
    return proof


def run_attract_only(output: Path):
    proof = verify_attract_palette_contract()
    rom_path = BUILD / "ladybug.rom"
    if not rom_path.is_file():
        raise SystemExit(
            f"current worktree ROM is missing: {rom_path}; run the assigned complete build first"
        )
    output_path = output if output.is_absolute() else ROOT / output
    rom_sha256 = digest(rom_path.read_bytes())
    command = [
        sys.executable, str(MENU_PROBE),
        "--worktree", str(ROOT),
        "--rom-sha256", rom_sha256,
        "--output", str(output_path),
        "--prompt-only",
    ]
    print(
        f"BUG-063 static: 56 bytes in cells 13,14,26,27; "
        f"current ROM sha256={rom_sha256}; GDB deadline=40s, "
        "timeout=prompt publication not observed",
        flush=True,
    )
    subprocess.run(command, cwd=ROOT, check=True, timeout=45)
    return proof


def legacy_main():
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
        presentation = (BUILD / "ladybug-presentation-runtime.bin").read_bytes()
        compare(runtime.read_bytes(client, 0x1900, len(presentation)), presentation, "module-identity")
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
        # BUG-039's entrant owns gameplay until its complete walkout/re-entry
        # sequence finishes. Seed the final pickup only after that handoff.
        for _ in range(64):
            if runtime.read_byte(client, 0x00A0) == 0:
                break
            reach("normal_game")
        else:
            raise AssertionError("initial entry did not complete within 64 gameplay dispatches")
        # The authored dot two cells north of the maze entrance is the
        # controlled final pickup; normal movement/eat_dot/check_stage_clear
        # must produce the request before normal_stage increments the part.
        assert (runtime.read_byte(client, 0x09), runtime.read_byte(client, 0x0A)) == (12, 18)
        runtime.write_byte(client, 0x25, 1)
        runtime.write_byte(client, 0x33, 0)
        client.call("inject_key", {"key": 0x2B, "action": "press"})
        for _ in range(64):
            reach("normal_stage")
            if runtime.read_byte(client, 0x26):
                break
        else:
            raise AssertionError("final authored dot did not request Part 2 within 64 stage dispatches")
        assert runtime.read_byte(client, 0x24) == 1
        assert runtime.read_byte(client, 0xA18C) & 0x80 == 0
        client.call("inject_key", {"key": 0x2B, "action": "release"})
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


def run_current_parts(output, adapter):
    output = output.resolve()
    if output.exists():
        raise SystemExit("output exists; retain each run under a fresh path")
    adapter = adapter.resolve()
    if not adapter.is_file():
        raise SystemExit("shared GDB adapter missing")
    output.mkdir(parents=True)
    rom_hash = digest((BUILD / "ladybug.rom").read_bytes())
    scenarios = [("hud", "--hud-parts", None)]
    scenarios += [("level-" + str(n), "--level-part", n) for n in (1,9,10,99,100,199,200,255)]
    scenarios += [("next-" + str(n), "--next-part", n) for n in (99,199,255)]
    receipt = {"status":"RUNNING", "rom_sha256":rom_hash,
               "adapter_sha256":digest(adapter.read_bytes()), "scenarios":[],
               "qualification":"Prototype preparation. HUD covers both persistent owners; level-start covers published FRONT. Each phase40seconds; timeout means missing boundary, not slow target."}
    try:
        for name, flag, value in scenarios:
            target = output / (name + ".json")
            command = [sys.executable,str(adapter),"--worktree",str(ROOT),
                       "--rom-sha256",rom_hash,"--output",str(target),flag]
            if value is not None:
                command.append(str(value))
            print("BUG-061 " + name, flush=True)
            subprocess.run(command,cwd=ROOT,check=True,timeout=150)
            proof = json.loads(target.read_text())
            if proof.get("status") != "PASS":
                raise AssertionError("scenario did not pass: " + name)
            receipt["scenarios"].append({"name":name,"status":"PASS",
                "receipt_sha256":digest(target.read_bytes()),
                "phases":len(proof["phases"])})
        receipt["status"] = "PASS"
    finally:
        (output / "summary.json").write_text(json.dumps(receipt,indent=2)+"\n")


def main():
    arguments = sys.argv[1:]
    if "--current-parts" in arguments:
        parser = argparse.ArgumentParser(description="Current BUG-061 credited GDB checks")
        parser.add_argument("--current-parts",action="store_true")
        parser.add_argument("--adapter",type=Path,required=True)
        parser.add_argument("--output",type=Path,required=True)
        args = parser.parse_args(arguments)
        run_current_parts(args.output,args.adapter)
        return
    if "--attract-only" not in arguments:
        if "--output" in arguments:
            raise SystemExit("--output requires --attract-only")
        legacy_main()
        return
    parser = argparse.ArgumentParser(description="Run the current BUG-063 attract prompt probe.")
    parser.add_argument("--attract-only", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(arguments)
    proof = run_attract_only(args.output)
    print(json.dumps({
        "status": "static-pass; natural-gdb-pass",
        "changed_packed_frame_bytes": proof["changed_packed_frame_bytes"],
        "candidate_static_frame_sha256": proof["candidate_static_frame_sha256"],
    }, indent=2))


if __name__ == "__main__":
    main()
