#!/usr/bin/env python3
"""Read-only BUG-100 static/deferred-frame discriminator for the complete C3 build."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


EXPECTED_REVISION = "436478586482afb0457357b4fddbbf05a7b9c52a"
EXPECTED_ROM = "e3a6cb1c9b9c3d959bc911433aea2b681b22a06608eeee40c8b9c14fae2f7982"
FRAME_BYTES = 0x7800
ROW_BYTES = 160


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_receipt(source_root: Path, build_dir: Path) -> dict[str, object]:
    receipt = json.loads((build_dir / "source-build-receipt.json").read_text())
    assert receipt["revision"] == EXPECTED_REVISION
    assert receipt["state"] == receipt["profile"] == "complete"
    assert sha256(build_dir / "ladybug.rom") == EXPECTED_ROM
    assert receipt["artifacts"]["ladybug.rom"] == EXPECTED_ROM
    mismatches = []
    for relative, expected in receipt["inputs"].items():
        path = source_root / relative
        if not path.is_file() or sha256(path) != expected:
            mismatches.append(f"input:{relative}")
    for relative, expected in receipt["artifacts"].items():
        path = build_dir / relative
        if not path.is_file() or sha256(path) != expected:
            mismatches.append(f"artifact:{relative}")
    # These three generated assembly sources are rooted at the checkout, unlike artifacts.
    for relative, expected in receipt["generated_inputs"].items():
        path = source_root / relative
        if not path.is_file() or sha256(path) != expected:
            mismatches.append(f"generated:{relative}")
    assert not mismatches, mismatches[:8]
    return {
        "revision": receipt["revision"],
        "rom_sha256": EXPECTED_ROM,
        "input_hashes_verified": len(receipt["inputs"]),
        "artifact_hashes_verified": len(receipt["artifacts"]),
        "generated_input_hashes_verified": len(receipt["generated_inputs"]),
        "mismatches": mismatches,
    }


def include_bytes(text: str, label: str, end: str) -> bytes:
    section = text.split("\n" + label + "\n", 1)[1].split("\n" + end + "\n", 1)[0]
    values = []
    for line in section.splitlines():
        if "fcb" not in line:
            continue
        payload = line.split("fcb", 1)[1].split(";", 1)[0]
        for token in payload.split(","):
            token = token.strip()
            if token:
                values.append(int(token[1:], 16) if token.startswith("$") else int(token))
    return bytes(values)


def decode_static_frame(cold: bytes, manifest: dict[str, object], font: bytes,
                        screen_index: int) -> bytearray:
    shared = manifest["shared_text"]
    ptr = manifest["map_stream_offsets"][screen_index]
    frame = bytearray(FRAME_BYTES)
    cell = 0
    while cell < 40 * 24:
        count, ident = cold[ptr], cold[ptr + 1]
        ptr += 2
        if ident == 255:
            colour = cold[ptr]
            ptr += 1
            tile = None
            assert manifest["maps"][screen_index]["name"] == "game-over" and colour == 0
        elif ident >= 174:
            colour = cold[ptr]
            ptr += 1
            glyph = ident - 174
            assert glyph < shared["font_count"] and colour < 16
            mask = font[glyph * 8:glyph * 8 + 8]
            tile = bytes(
                ((colour if mask[row] & (128 >> (column * 2)) else 0) << 4)
                | (colour if mask[row] & (64 >> (column * 2)) else 0)
                for row in range(8) for column in range(4)
            )
        else:
            assert ident < shared["static_graphics"]
            tile = cold[ident * 32:ident * 32 + 32]
            assert len(tile) == 32
        assert count and cell + count <= 40 * 24
        for _ in range(count):
            x, y = cell % 40, cell // 40
            offset = y * 8 * ROW_BYTES + x * 4
            if tile is not None:
                for row in range(8):
                    frame[offset + row * ROW_BYTES:offset + row * ROW_BYTES + 4] = tile[row * 4:row * 4 + 4]
            cell += 1
    return frame


def region_bytes(frame: bytes | bytearray, x: int, y: int) -> bytes:
    result = bytearray()
    for row in range(16):
        offset = (y * 8 + row) * ROW_BYTES + x * 4
        result.extend(frame[offset:offset + 4])
    return bytes(result)


def region_pixels(frame: bytes | bytearray, x: int, y: int) -> list[list[int]]:
    pixels = []
    for row in range(16):
        offset = (y * 8 + row) * ROW_BYTES + x * 4
        expanded = []
        for value in frame[offset:offset + 4]:
            expanded.extend((value >> 4, value & 0x0F))
        pixels.append(expanded)
    return pixels


def foreground_report(frame: bytes | bytearray, x: int, y: int,
                      red_pen: int) -> dict[str, object]:
    pixels = region_pixels(frame, x, y)
    ink = [(column, value) for row in pixels for column, value in enumerate(row) if value]
    return {
        "foreground_pixels": len(ink),
        "foreground_colours": sorted({value for _, value in ink}),
        "left_half_foreground": sum(column < 4 for column, _ in ink),
        "right_half_foreground": sum(column >= 4 for column, _ in ink),
        "red_pen": red_pen,
        "all_foreground_red": bool(ink) and all(value == red_pen for _, value in ink),
        "white_foreground_pixels": sum(value == 7 for _, value in ink),
    }


def overlay_tile(frame: bytearray, destination: int, tile: bytes) -> None:
    offset = destination - 0x2000
    for row in range(8):
        frame[offset + row * ROW_BYTES:offset + row * ROW_BYTES + 4] = tile[row * 4:row * 4 + 4]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--build-dir", type=Path, required=True)
    args = parser.parse_args()
    root, build = args.source_root.resolve(), args.build_dir.resolve()
    receipt = verify_receipt(root, build)
    sys.path.insert(0, str(root / "scripts"))
    import build_presentation as p
    import build_screen as s

    manifest = json.loads((build / "ladybug-presentation.json").read_text())
    cold = (build / "ladybug-presentation-cold.bin").read_bytes()
    assert hashlib.sha256(cold).hexdigest() == manifest["cold_payload"]["sha256"]
    include = (build / "ladybug_shared_text.inc").read_text()
    font = include_bytes(include, "font", "colour_lut")
    screen_names = [record["name"] for record in manifest["maps"]]
    screen_index = screen_names.index("high-score")

    high_path = root / "tiled" / p.MAP_FILES["high-score"]
    high_root, flat, _ = p.flatten_map(high_path)
    mark_cells = []
    for x, y in ((31, 13), (31, 14)):
        gid = flat[y * 40 + x] & p.GID_MASK
        mark_cells.append({"x": x, "y": y, "gid": gid,
                           "raw_character_code": p.raw_char_code(high_root, high_path, gid)})
    assert [(r["gid"], r["raw_character_code"]) for r in mark_cells] == [(388, 103), (484, 97)]

    native_tiles: list[bytes] = []
    native_map, _ = p.compile_map(high_path, s.load_chars(root / "assets/arcade/chars.json"),
                                  native_tiles, {}, False, False)
    native_frame = p.title_framebuffer(native_map, native_tiles)
    static_frame = decode_static_frame(cold, manifest, font, screen_index)
    static_hash = hashlib.sha256(static_frame).hexdigest()
    assert static_hash == manifest["shared_static_frame_sha256"][screen_index]
    native_region = region_bytes(native_frame, 31, 13)
    static_region = region_bytes(static_frame, 31, 13)
    assert native_region == static_region

    attract_path = root / "tiled" / p.MAP_FILES["attract"]
    attract_tiles: list[bytes] = []
    attract_map, _ = p.compile_map(attract_path, s.load_chars(root / "assets/arcade/chars.json"),
                                   attract_tiles, {}, False, False)
    attract_base = p.title_framebuffer(attract_map, attract_tiles)
    logo_roots, source_frames = p.compile_logo_frames(attract_base)
    expected_records = []
    for y in range(24):
        for x in range(40):
            offset = y * 1280 + x * 4
            pair = [b"".join(frame[offset + row * ROW_BYTES:offset + row * ROW_BYTES + 4]
                             for row in range(8)) for frame in source_frames]
            if pair[0] != pair[1]:
                expected_records.append((p.framebuffer_destination((x, y + 6)), pair[0], pair[1]))

    stored_records = manifest["highscore_logo"]["records"]
    assert len(logo_roots) == 12 and len(expected_records) == manifest["highscore_logo"]["cells"] == 12
    assert len(stored_records) == len(expected_records)
    destinations = []
    for stored, (expected_destination, phase0, phase1) in zip(stored_records, expected_records):
        destination, phase0_ptr, phase1_ptr = stored
        assert destination == expected_destination
        assert cold[phase0_ptr:phase0_ptr + 32] == phase0
        assert cold[phase1_ptr:phase1_ptr + 32] == phase1
        byte_offset = destination - 0x2000
        cell = (byte_offset % 1280 // 4, byte_offset // 1280)
        destinations.append({"x": cell[0], "y": cell[1]})

    frame_reports = []
    for phase in (0, 1):
        composed = bytearray(static_frame)
        for destination, phase0_ptr, phase1_ptr in stored_records:
            tile_ptr = (phase0_ptr, phase1_ptr)[phase]
            overlay_tile(composed, destination, cold[tile_ptr:tile_ptr + 32])
        assert region_bytes(composed, 31, 13) == static_region
        report = foreground_report(composed, 31, 13, p.RED)
        assert report["all_foreground_red"]
        frame_reports.append(report)

    r_pixels_static = foreground_report(static_frame, 31, 13, p.RED)
    assert r_pixels_static["all_foreground_red"]
    assert r_pixels_static["foreground_pixels"] == 25
    assert r_pixels_static["left_half_foreground"] == 22
    assert r_pixels_static["right_half_foreground"] == 3
    assert not any((record["x"], record["y"]) in ((31, 13), (31, 14)) for record in destinations)

    result = {
        "status": "pass",
        "receipt": receipt,
        "screen": "high-score",
        "screen_index": screen_index,
        "full_shared_static_frame_sha256": static_hash,
        "trademark_cells": mark_cells,
        "static_native_matches_full_shared_conversion": native_region == static_region,
        "static_r_region_sha256": hashlib.sha256(static_region).hexdigest(),
        "static_r": r_pixels_static,
        "deferred_logo": {
            "source_layers": ["Logo Frame 1", "Logo Frame 2"],
            "source_roots": len(logo_roots),
            "generated_record_count": len(stored_records),
            "record_destinations": destinations,
            "frame0_r": frame_reports[0],
            "frame1_r": frame_reports[1],
            "r_region_unchanged_in_both_phases": True,
        },
        "limitation": "Source/generated composition is proven for this exact ROM receipt; no live XRoar/GDB frame or framebuffer-owner observation was made.",
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
