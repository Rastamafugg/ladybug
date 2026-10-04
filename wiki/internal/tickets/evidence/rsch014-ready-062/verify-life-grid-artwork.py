#!/usr/bin/env python3
"""Verify the independent authored-quartet oracle for the BUG-062 grid."""
import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
import re


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def section_values(text, start, end):
    section = text.split("\n" + start + "\n", 1)[1].split("\n" + end + "\n", 1)[0]
    output = []
    for line in section.splitlines():
        if "fcb" not in line:
            continue
        values = line.split("fcb", 1)[1].split(";", 1)[0]
        for value in values.split(","):
            token = value.strip()
            if token:
                output.append(int(token[1:], 16) if token.startswith("$") else int(token))
    return bytes(output)


def pen_counts(tile):
    return Counter((byte >> shift) & 3 for byte in tile for shift in (6, 4, 2, 0))


def symbol_values(path):
    return {name: int(value, 16) for name, value in re.findall(
        r"^Symbol: (\w+) .* = ([0-9A-Fa-f]+)$", path.read_text(encoding="utf-8"), re.M)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--input", choices=("keyboard", "joystick"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root, build = args.source_root.resolve(), args.build_dir.resolve()
    source = root / "src/main.s"
    shared_source = root / "src/shared_text_runtime.inc"
    gameplay_map = root / "tiled/coco-screen.tmx"
    include = build / "ladybug_screen.inc"
    rom = build / "ladybug.rom"
    runtime = build / "ladybug-runtime.rom"
    source_text = source.read_text(encoding="utf-8")
    marker = source_text.split("\ndraw_life_marker\n", 1)[1].split(
        "\ndraw_authored_hud_tile\n", 1)[0]
    addresses = (21 * 40 + 33, 21 * 40 + 34, 22 * 40 + 33, 22 * 40 + 34)
    for address in addresses:
        assert f"ldb     screen_map+{address}" in marker, address
    assert marker.count("bsr     draw_hud_tile") == 4
    assert "        else\n" in marker and "bsr     draw_authored_hud_tile" in marker.split(
        "        else\n", 1)[1]

    image = include.read_text(encoding="utf-8")
    mapping = section_values(image, "screen_map", "screen_tiles")
    tiles = section_values(image, "screen_tiles", "gate_state_tiles")
    assert len(mapping) == 960 and len(tiles) % 32 == 0
    tile_count = len(tiles) // 32
    template_ids = [mapping[address] for address in addresses]
    assert all(0 <= tile_id < tile_count for tile_id in template_ids)
    template = [tiles[tile_id * 32:(tile_id + 1) * 32] for tile_id in template_ids]
    assert len(set(template)) == 4, template_ids
    pens = [pen_counts(tile) for tile in template]
    assert all(sum(counts[p] for p in (1, 2, 3)) > 0 for counts in pens), pens

    roots = [(33 + 2 * (slot % 3), 21 - 2 * (slot // 3)) for slot in range(12)]
    destination_baseline = []
    for slot, (x, y) in enumerate(roots):
        dest = [mapping[(y + dy) * 40 + x + dx] for dy, dx in ((0, 0), (0, 1), (1, 0), (1, 1))]
        destination_baseline.append(dest)
        if slot >= 3:
            assert all(not any(tiles[tile_id * 32:(tile_id + 1) * 32]) for tile_id in dest), (slot, dest)
    for count in range(13):
        rendered = {}
        for slot, (x, y) in enumerate(roots):
            for quarter, (dy, dx) in enumerate(((0, 0), (0, 1), (1, 0), (1, 1))):
                rendered[(x + dx, y + dy)] = template[quarter] if slot < count else bytes(32)
        assert len(rendered) == 48
        assert sum(any(tile) for tile in rendered.values()) == 4 * count
        for slot in range(12):
            x, y = roots[slot]
            for quarter, (dy, dx) in enumerate(((0, 0), (0, 1), (1, 0), (1, 1))):
                expected = template[quarter] if slot < count else bytes(32)
                assert rendered[(x + dx, y + dy)] == expected

    symbols = symbol_values(build / "ladybug.map")
    required = {"resident_end", "asset_start", "asset_end", "INPUT_JOYSTICK",
                "draw_life_marker", "draw_authored_hud_tile", "screen_map"}
    assert required <= symbols.keys(), required - symbols.keys()
    assert symbols["INPUT_JOYSTICK"] == (1 if args.input == "joystick" else 0), symbols["INPUT_JOYSTICK"]
    resident_used = symbols["resident_end"] - 0xC000
    asset_used = symbols["asset_end"] - symbols["asset_start"]
    assert resident_used <= 8192 and asset_used <= 7680
    runtime_bytes = runtime.read_bytes()
    marker_start = symbols["draw_life_marker"] - 0xC000
    marker_end = symbols["draw_authored_hud_tile"] - 0xC000
    marker_bytes = runtime_bytes[marker_start:marker_end]
    assert len(marker_bytes) == 29, len(marker_bytes)
    result = {
        "schema": "bug062-authored-quartet-grid-static-v1",
        "status": "PASS",
        "profile": "complete",
        "input": args.input,
        "current_map_sha256": sha(gameplay_map),
        "main_source_sha256": sha(source),
        "shared_text_source_sha256": sha(shared_source),
        "screen_include_sha256": sha(include),
        "runtime_sha256": sha(runtime),
        "rom_sha256": sha(rom),
        "template_map_indices": list(addresses),
        "template_tile_ids": template_ids,
        "template_quadrant_sha256": [hashlib.sha256(tile).hexdigest() for tile in template],
        "template_quadrant_pens": [dict(sorted(counts.items())) for counts in pens],
        "template_foreground_pixels_per_quadrant": [sum(counts[p] for p in (1, 2, 3)) for counts in pens],
        "upper_destination_source_is_blank": True,
        "input_joystick_flag": symbols["INPUT_JOYSTICK"],
        "marker_renderer": {
            "start_address": symbols["draw_life_marker"],
            "end_address": symbols["draw_authored_hud_tile"],
            "bytes": len(marker_bytes),
            "sha256": hashlib.sha256(marker_bytes).hexdigest(),
            "source_addresses": [symbols["screen_map"] + address for address in addresses],
        },
        "modeled_counts": list(range(13)),
        "modeled_slot_roots": roots,
        "resident": {"used": resident_used, "limit": 8192, "free": 8192 - resident_used},
        "assets": {"used": asset_used, "limit": 7680, "free": 7680 - asset_used},
        "qualification": "Static emitted-artifact oracle: repeats the independent bottom-left source quartet at all twelve roots. No runtime or BUG-039/BUG-084 accounting claim.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "template_tile_ids": template_ids,
                      "resident": result["resident"], "assets": result["assets"],
                      "rom_sha256": result["rom_sha256"], "output": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()
