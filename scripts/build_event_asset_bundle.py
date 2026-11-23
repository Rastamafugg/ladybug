#!/usr/bin/env python3
"""Compile SPECIAL/EXTRA EVD1 event pages ($25/$26) and dinosaur sparse frames."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_screen import (
    GID_MASK,
    compile_sprite_codes,
    nearest_palette_index,
    pack_tile,
    parse_csv,
    tileset_ranges,
)
from build_sparse_sprites import LEGACY_ENEMY_PEN_MAP, encode_sparse_frame

EVENT_TILE_COUNT = 320
EVENT_COLUMNS = 16
EVENT_TILE_SIZE = 8
EVENT_PAGE_BYTES = 8192
EVENT_ATLAS_PAGE = 0x25
EVENT_DATA_PAGE = 0x26
EVENT_WINDOW_BASE = 0xA000
EVENT_SCENE_X0 = 8
EVENT_SCENE_Y0 = 0
EVENT_SCENE_W = 24
EVENT_SCENE_H = 24
PART_VEGETABLE_GID = 633
DIR_N = 0
DIR_E = 1
DIR_S = 2
DIR_W = 3
DINOSAUR_CODES = tuple(range(89, 126))


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_file(path: Path) -> str:
    return sha256(path.read_bytes())


def event_tileset_info(map_path: Path, tileset_path: Path) -> tuple[ET.Element, int]:
    root = ET.parse(map_path).getroot()
    references = [
        node
        for node in root.findall("tileset")
        if node.get("source")
        and (map_path.parent / node.get("source", "")).resolve() == tileset_path.resolve()
    ]
    if len(references) != 1:
        raise ValueError(f"{map_path}: expected exactly one reference to {tileset_path.name}")
    tsx = ET.parse(tileset_path).getroot()
    expected = {
        "tilewidth": EVENT_TILE_SIZE,
        "tileheight": EVENT_TILE_SIZE,
        "tilecount": EVENT_TILE_COUNT,
        "columns": EVENT_COLUMNS,
    }
    actual = {key: int(tsx.get(key, "-1")) for key in expected}
    if actual != expected:
        raise ValueError(f"{tileset_path}: tileset contract differs: {actual}")
    firstgid = int(references[0].get("firstgid", "0"))
    ranges = tileset_ranges(root, map_path)
    event_range = next((item for item in ranges if int(item["firstgid"]) == firstgid), None)
    if (
        event_range is None
        or event_range["name"] != tsx.get("name")
        or event_range["lastgid"] - firstgid + 1 != EVENT_TILE_COUNT
    ):
        raise ValueError(f"{map_path}: event tileset GID range differs from TSX")
    return tsx, firstgid


def extract_part_vegetable_destination(map_path: Path) -> dict[str, int]:
    """Validate single raw GID-633 marker in Sprite Locations and derive $2000-based root."""
    root = ET.parse(map_path).getroot()
    layers = [layer for layer in root.findall("layer") if layer.get("name") == "Sprite Locations"]
    if len(layers) != 1:
        raise ValueError(f"{map_path}: expected exactly one 'Sprite Locations' layer")
    layer = layers[0]
    width = int(layer.get("width", "0"))
    height = int(layer.get("height", "0"))
    if (width, height) != (40, 24):
        raise ValueError(f"{map_path}: Sprite Locations must be 40x24, found {width}x{height}")
    data = layer.find("data")
    if data is None:
        raise ValueError(f"{map_path}: Sprite Locations missing <data>")
    cells = parse_csv(data, "Sprite Locations")
    if len(cells) != 960:
        raise ValueError(f"{map_path}: Sprite Locations expected 960 cells, found {len(cells)}")

    markers: list[tuple[int, int]] = []
    for index, raw_gid in enumerate(cells):
        if raw_gid == 0:
            continue
        if raw_gid & ~GID_MASK:
            raise ValueError(
                f"{map_path}: transformed GID 0x{raw_gid:08X} in Sprite Locations is forbidden"
            )
        if raw_gid != PART_VEGETABLE_GID:
            raise ValueError(
                f"{map_path}: unexpected GID {raw_gid} in Sprite Locations "
                f"(expected only raw GID {PART_VEGETABLE_GID})"
            )
        markers.append((index % width, index // width))

    if len(markers) != 1:
        raise ValueError(
            f"{map_path}: expected exactly one raw GID {PART_VEGETABLE_GID} in Sprite Locations, "
            f"found {len(markers)}"
        )
    mx, my = markers[0]
    root_x, root_y = mx, my - 1
    if not (0 <= root_x <= 38 and 0 <= root_y <= 22):
        raise ValueError(f"{map_path}: derived Part Vegetable root ({root_x},{root_y}) out of bounds")
    fb_dst = 0x2000 + root_y * 8 * 160 + root_x * 4
    return {
        "marker_x": mx,
        "marker_y": my,
        "root_x": root_x,
        "root_y": root_y,
        "fb_dst": fb_dst,
    }


def _parse_polyline_vertices(obj: ET.Element, map_path: Path, label: str) -> list[tuple[int, int]]:
    pl = obj.find("polyline")
    if pl is None or not pl.get("points"):
        raise ValueError(f"{map_path}: {label} missing <polyline points>")
    ox = int(round(float(obj.get("x", "0"))))
    oy = int(round(float(obj.get("y", "0"))))
    vertices: list[tuple[int, int]] = []
    for pair in pl.get("points", "").split():
        xs, ys = pair.split(",")
        vx = ox + int(round(float(xs)))
        vy = oy + int(round(float(ys)))
        vertices.append((vx, vy))
    if len(vertices) < 2:
        raise ValueError(f"{map_path}: {label} needs at least 2 vertices")
    return vertices


def _encode_segments(vertices: list[tuple[int, int]], map_path: Path, label: str) -> bytes:
    encoded = bytearray()
    for (x0, y0), (x1, y1) in zip(vertices, vertices[1:]):
        dx = x1 - x0
        dy = y1 - y0
        if (dx == 0) == (dy == 0):
            raise ValueError(f"{map_path}: {label} has non-orthogonal leg ({x0},{y0})->({x1},{y1})")
        if dx != 0:
            if abs(dx) % 2 != 0:
                raise ValueError(f"{map_path}: {label} leg dx={dx} must be even")
            direction = DIR_E if dx > 0 else DIR_W
            steps = abs(dx) // 2
        else:
            if abs(dy) % 2 != 0:
                raise ValueError(f"{map_path}: {label} leg dy={dy} must be even")
            direction = DIR_S if dy > 0 else DIR_N
            steps = abs(dy) // 2
        while steps > 254:
            encoded.extend((direction, 254))
            steps -= 254
        encoded.extend((direction, steps))
    encoded.append(0xFF)
    return bytes(encoded)


def compile_routes(special_map: Path, extra_map: Path) -> tuple[bytes, bytes, bytes, dict[str, object]]:
    """Compile SPECIAL route, EXTRA shared route, and 12 EXTRA slot connectors."""
    sp_root = ET.parse(special_map).getroot()
    sp_groups = [g for g in sp_root.findall("objectgroup") if g.get("name") == "Ladybug Path"]
    if len(sp_groups) != 1 or len(sp_groups[0].findall("object")) != 1:
        raise ValueError(f"{special_map}: expected single Ladybug Path polyline")
    sp_verts = _parse_polyline_vertices(sp_groups[0].findall("object")[0], special_map, "SPECIAL Ladybug Path")
    sp_start_tl = (sp_verts[0][0] - 8, sp_verts[0][1] - 8)
    sp_route = struct.pack(">hh", sp_start_tl[0], sp_start_tl[1]) + _encode_segments(
        sp_verts, special_map, "SPECIAL Ladybug Path"
    )

    ex_root = ET.parse(extra_map).getroot()
    ex_groups = [g for g in ex_root.findall("objectgroup") if g.get("name") == "Ladybug Path"]
    if len(ex_groups) != 1 or len(ex_groups[0].findall("object")) != 1:
        raise ValueError(f"{extra_map}: expected single EXTRA Ladybug Path polyline")
    ex_verts = _parse_polyline_vertices(ex_groups[0].findall("object")[0], extra_map, "EXTRA Shared Route")
    ex_start_tl = (ex_verts[0][0] - 8, ex_verts[0][1] - 8)
    ex_shared = struct.pack(">hh", ex_start_tl[0], ex_start_tl[1]) + _encode_segments(
        ex_verts, extra_map, "EXTRA Shared Route"
    )

    conn_groups = [g for g in ex_root.findall("objectgroup") if g.get("name") == "EXTRA Life Connectors"]
    if len(conn_groups) != 1:
        raise ValueError(f"{extra_map}: expected single 'EXTRA Life Connectors' group")
    objs = conn_groups[0].findall("object")
    if len(objs) != 12:
        raise ValueError(f"{extra_map}: expected 12 EXTRA connectors, found {len(objs)}")
    ex_connectors = bytearray()
    shared_end = ex_verts[-1]
    connector_meta = []
    for slot, obj in enumerate(objs):
        expected_name = f"slot-{slot:02d}"
        if obj.get("name") != expected_name:
            raise ValueError(f"{extra_map}: connector {slot} named {obj.get('name')!r}, expected {expected_name!r}")
        verts = _parse_polyline_vertices(obj, extra_map, expected_name)
        if verts[0] != shared_end:
            raise ValueError(f"{extra_map}: {expected_name} starts at {verts[0]}, expected {shared_end}")
        seg = _encode_segments(verts, extra_map, expected_name)
        if len(seg) != 5:
            raise ValueError(f"{extra_map}: {expected_name} expected 2 legs (5 encoded bytes), got {len(seg)}")
        ex_connectors.extend(seg)
        connector_meta.append({"name": expected_name, "vertices": [list(v) for v in verts], "bytes": len(seg)})

    route_meta = {
        "special": {"vertices": [list(v) for v in sp_verts], "start_top_left": list(sp_start_tl), "bytes": len(sp_route)},
        "extra_shared": {"vertices": [list(v) for v in ex_verts], "start_top_left": list(ex_start_tl), "bytes": len(ex_shared)},
        "extra_connectors": connector_meta,
        "extra_connector_stride": 5,
    }
    return sp_route, ex_shared, bytes(ex_connectors), route_meta


def _apply_tiled_flips(pixels: list[list[int]], flags: int) -> list[list[int]]:
    """Apply Tiled flip flags (bit 29 diagonal, bit 31 horiz, bit 30 vert) to an 8x8 tile."""
    out = [row[:] for row in pixels]
    if flags & 0x20000000:  # anti-diagonal (transpose x,y)
        out = [[out[x][y] for x in range(EVENT_TILE_SIZE)] for y in range(EVENT_TILE_SIZE)]
    if flags & 0x80000000:  # horizontal flip
        out = [row[::-1] for row in out]
    if flags & 0x40000000:  # vertical flip
        out = out[::-1]
    return out


def extract_event_scene_grid(map_path: Path, tileset_path: Path) -> tuple[int, list[tuple[int, int]]]:
    """Extract the 24x24 CoCo Event Scene entries as (source_tile_id, flip_flags)."""
    root = ET.parse(map_path).getroot()
    _, firstgid = event_tileset_info(map_path, tileset_path)
    layers = [layer for layer in root.findall("layer") if layer.get("name") == "CoCo Event Scene"]
    if len(layers) != 1:
        raise ValueError(f"{map_path}: expected exactly one 'CoCo Event Scene' layer")
    data = layers[0].find("data")
    if data is None:
        raise ValueError(f"{map_path}: CoCo Event Scene missing <data>")
    cells = parse_csv(data, "CoCo Event Scene")
    if len(cells) != 960:
        raise ValueError(f"{map_path}: CoCo Event Scene expected 960 cells, found {len(cells)}")

    grid: list[tuple[int, int]] = []
    for y in range(EVENT_SCENE_Y0, EVENT_SCENE_Y0 + EVENT_SCENE_H):
        for x in range(EVENT_SCENE_X0, EVENT_SCENE_X0 + EVENT_SCENE_W):
            raw = cells[y * 40 + x]
            gid = raw & GID_MASK
            flags = raw & ~GID_MASK
            if not (firstgid <= gid < firstgid + EVENT_TILE_COUNT):
                raise ValueError(
                    f"{map_path}: CoCo Event Scene cell ({x},{y}) GID {gid} outside event tileset"
                )
            grid.append((gid - firstgid, flags))
    # Also verify no stray event tiles outside x=[8..31]
    for idx, raw in enumerate(cells):
        x, y = idx % 40, idx // 40
        if not (EVENT_SCENE_X0 <= x < EVENT_SCENE_X0 + EVENT_SCENE_W):
            if raw != 0:
                raise ValueError(f"{map_path}: unexpected CoCo Event Scene tile at ({x},{y})")
    return firstgid, grid


def compile_event_asset(
    special_map: Path,
    extra_map: Path,
    tileset_path: Path,
    image_path: Path,
) -> tuple[bytes, dict[str, object]]:
    """Compile EVD1 page-$25 atlas and page-$26 maps/routes/metadata."""
    sp_veg = extract_part_vegetable_destination(special_map)
    ex_veg = extract_part_vegetable_destination(extra_map)
    sp_firstgid, sp_src_grid = extract_event_scene_grid(special_map, tileset_path)
    ex_firstgid, ex_src_grid = extract_event_scene_grid(extra_map, tileset_path)
    if sp_firstgid != ex_firstgid:
        raise ValueError("SPECIAL and EXTRA maps use different event firstgid values")

    tsx = ET.parse(tileset_path).getroot()
    image_node = tsx.find("image")
    if image_node is None or not image_node.get("source"):
        raise ValueError(f"{tileset_path}: no embedded tilesheet image source")
    declared_image = (tileset_path.parent / image_node.get("source", "")).resolve()
    if declared_image != image_path.resolve():
        raise ValueError(f"{tileset_path}: tilesheet path does not match {image_path}")

    with Image.open(image_path) as source:
        image = source.convert("RGBA")
    expected_size = (
        EVENT_COLUMNS * EVENT_TILE_SIZE,
        (EVENT_TILE_COUNT + EVENT_COLUMNS - 1) // EVENT_COLUMNS * EVENT_TILE_SIZE,
    )
    if image.size != expected_size:
        raise ValueError(f"{image_path}: expected {expected_size}, found {image.size}")

    atlas: list[bytes] = []
    atlas_ids: dict[bytes, int] = {}
    key_to_atlas: dict[tuple[int, int], int] = {}

    used_special = sorted({tid for tid, _ in sp_src_grid})
    used_extra = sorted({tid for tid, _ in ex_src_grid})
    for key in sorted(set(sp_src_grid) | set(ex_src_grid)):
        tile_id, flags = key
        col = tile_id % EVENT_COLUMNS
        row = tile_id // EVENT_COLUMNS
        crop = image.crop(
            (
                col * EVENT_TILE_SIZE,
                row * EVENT_TILE_SIZE,
                (col + 1) * EVENT_TILE_SIZE,
                (row + 1) * EVENT_TILE_SIZE,
            )
        )
        pixels: list[list[int]] = []
        for y in range(EVENT_TILE_SIZE):
            line = []
            for x in range(EVENT_TILE_SIZE):
                red, green, blue, alpha = crop.getpixel((x, y))
                line.append(0 if alpha == 0 else nearest_palette_index([red, green, blue]))
            pixels.append(line)
        if flags:
            pixels = _apply_tiled_flips(pixels, flags)
        packed = pack_tile(pixels)
        atlas_id = atlas_ids.get(packed)
        if atlas_id is None:
            atlas_id = len(atlas)
            if atlas_id >= 0xFF:
                raise ValueError("EVD1 shared event atlas exceeds 255 one-byte tile IDs")
            atlas_ids[packed] = atlas_id
            atlas.append(packed)
        key_to_atlas[key] = atlas_id

    page25_raw = b"".join(atlas)
    if len(page25_raw) > EVENT_PAGE_BYTES:
        raise ValueError(f"EVD1 page $25 atlas ({len(page25_raw)} B) exceeds 8,192 B")

    sp_map_bytes = bytes(key_to_atlas[key] for key in sp_src_grid)
    ex_map_bytes = bytes(key_to_atlas[key] for key in ex_src_grid)
    sp_route, ex_shared, ex_connectors, route_meta = compile_routes(special_map, extra_map)

    header_len = 16
    sp_map_offset = header_len
    ex_map_offset = sp_map_offset + len(sp_map_bytes)
    sp_route_offset = ex_map_offset + len(ex_map_bytes)
    ex_shared_offset = sp_route_offset + len(sp_route)
    ex_conn_offset = ex_shared_offset + len(ex_shared)

    sp_route_addr = EVENT_WINDOW_BASE + sp_route_offset
    ex_shared_addr = EVENT_WINDOW_BASE + ex_shared_offset
    ex_conn_addr = EVENT_WINDOW_BASE + ex_conn_offset

    header = (
        b"EVD1"
        + bytes((1, len(atlas)))
        + struct.pack(
            ">HHHHH",
            sp_veg["fb_dst"],
            ex_veg["fb_dst"],
            sp_route_addr,
            ex_shared_addr,
            ex_conn_addr,
        )
    )
    assert len(header) == header_len
    page26_raw = header + sp_map_bytes + ex_map_bytes + sp_route + ex_shared + ex_connectors
    if len(page26_raw) > EVENT_PAGE_BYTES:
        raise ValueError(f"EVD1 page $26 data ({len(page26_raw)} B) exceeds 8,192 B")
    if len(page25_raw) + len(page26_raw) > 2 * EVENT_PAGE_BYTES:
        raise ValueError("EVD1 expanded payload exceeds 16,384 B ceiling")

    raw = page25_raw + page26_raw
    metadata: dict[str, object] = {
        "format": "EVD1",
        "version": 1,
        "header_bytes": header_len,
        "atlas_page": EVENT_ATLAS_PAGE,
        "data_page": EVENT_DATA_PAGE,
        "atlas_tile_bytes": 32,
        "atlas_tiles": len(atlas),
        "atlas_bytes": len(page25_raw),
        "page25_bytes": len(page25_raw),
        "page25_sha256": sha256(page25_raw),
        "page26_bytes": len(page26_raw),
        "page26_sha256": sha256(page26_raw),
        "firstgid": sp_firstgid,
        "special_map_addr": EVENT_WINDOW_BASE + sp_map_offset,
        "extra_map_addr": EVENT_WINDOW_BASE + ex_map_offset,
        "special_route_addr": sp_route_addr,
        "extra_shared_route_addr": ex_shared_addr,
        "extra_connectors_addr": ex_conn_addr,
        "extra_connector_stride": 5,
        "special_vegetable": sp_veg,
        "extra_vegetable": ex_veg,
        "routes": route_meta,
        "maps": {
            "special": {
                "tmx": str(special_map.relative_to(ROOT)),
                "tmx_sha256": hash_file(special_map),
                "used_source_tile_ids": used_special,
                "scene_cells": len(sp_map_bytes),
            },
            "extra": {
                "tmx": str(extra_map.relative_to(ROOT)),
                "tmx_sha256": hash_file(extra_map),
                "used_source_tile_ids": used_extra,
                "scene_cells": len(ex_map_bytes),
            },
        },
        "inputs": {
            "tileset_tsx": str(tileset_path.relative_to(ROOT)),
            "tileset_tsx_sha256": hash_file(tileset_path),
            "tilesheet_png": str(image_path.relative_to(ROOT)),
            "tilesheet_png_sha256": hash_file(image_path),
        },
        "raw_bytes": len(raw),
        "raw_sha256": sha256(raw),
    }
    return raw, metadata


def write_event_include(path: Path, meta: dict[str, object]) -> None:
    sp_veg = meta["special_vegetable"]
    ex_veg = meta["extra_vegetable"]
    assert isinstance(sp_veg, dict) and isinstance(ex_veg, dict)
    lines = [
        "; Generated by scripts/build_event_asset_bundle.py; do not edit.",
        f"EVENT_ATLAS_PAGE equ ${EVENT_ATLAS_PAGE:02X}",
        f"EVENT_DATA_PAGE equ ${EVENT_DATA_PAGE:02X}",
        f"EVENT_ATLAS_ADDR equ ${EVENT_WINDOW_BASE:04X}",
        f"EVENT_HEADER_ADDR equ ${EVENT_WINDOW_BASE:04X}",
        f"EVENT_SPECIAL_MAP_ADDR equ ${int(meta['special_map_addr']):04X}",
        f"EVENT_EXTRA_MAP_ADDR equ ${int(meta['extra_map_addr']):04X}",
        f"EVENT_SPECIAL_ROUTE_ADDR equ ${int(meta['special_route_addr']):04X}",
        f"EVENT_EXTRA_SHARED_ROUTE_ADDR equ ${int(meta['extra_shared_route_addr']):04X}",
        f"EVENT_EXTRA_CONNECTORS_ADDR equ ${int(meta['extra_connectors_addr']):04X}",
        f"EVENT_EXTRA_CONNECTOR_STRIDE equ {int(meta['extra_connector_stride'])}",
        f"FEAT011_SPECIAL_VEGETABLE_DST equ ${int(sp_veg['fb_dst']):04X}",
        f"FEAT011_EXTRA_VEGETABLE_DST equ ${int(ex_veg['fb_dst']):04X}",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="ascii")


def compile_dinosaur_asset(sprites_path: Path) -> tuple[bytes, dict[str, object]]:
    frames = compile_sprite_codes(sprites_path, DINOSAUR_CODES)
    streams = [encode_sparse_frame(frame, LEGACY_ENEMY_PEN_MAP) for frame in frames]
    header_bytes = 6
    index_bytes = 5 * len(streams)
    stream_offset = 0
    index = bytearray()
    frame_details = []
    for code, stream in zip(DINOSAUR_CODES, streams):
        index.extend(
            (
                code,
                stream_offset & 0xFF,
                (stream_offset >> 8) & 0xFF,
                len(stream) & 0xFF,
                (len(stream) >> 8) & 0xFF,
            )
        )
        frame_details.append(
            {
                "source_sprite_code": code,
                "offset_from_stream_data": stream_offset,
                "bytes": len(stream),
                "sha256": sha256(stream),
            }
        )
        stream_offset += len(stream)
    header = b"DIN1" + bytes((DINOSAUR_CODES[0], len(DINOSAUR_CODES)))
    raw = header + bytes(index) + b"".join(streams)
    metadata = {
        "format": "DIN1",
        "header_bytes": header_bytes,
        "index_entry_bytes": 5,
        "index_bytes": index_bytes,
        "stream_data_offset": header_bytes + index_bytes,
        "frame_count": len(streams),
        "source_sprite_codes": list(DINOSAUR_CODES),
        "sparse_pen_map": list(LEGACY_ENEMY_PEN_MAP),
        "frames": frame_details,
        "input": str(sprites_path.relative_to(ROOT)),
        "input_sha256": hash_file(sprites_path),
        "raw_bytes": len(raw),
        "raw_sha256": sha256(raw),
    }
    return raw, metadata


def run_marker_negative_controls(sample_map: Path) -> None:
    """F11-01 negative controls: reject missing, duplicate, transformed, and wrong-GID markers."""
    base_text = sample_map.read_text(encoding="utf-8")
    assert ",633," in base_text, "expected raw GID 633 in sample map"

    cases = (
        ("missing_marker", base_text.replace(",633,", ",0,", 1)),
        ("duplicate_marker", base_text.replace(",633,0,", ",633,633,", 1)),
        ("transformed_marker", base_text.replace(",633,", f",{633 | 0x80000000},", 1)),
        ("wrong_gid_marker", base_text.replace(",633,", ",634,", 1)),
    )
    with tempfile.TemporaryDirectory() as td:
        for name, text in cases:
            p = Path(td) / f"{name}.tmx"
            p.write_text(text, encoding="utf-8")
            try:
                extract_part_vegetable_destination(p)
            except ValueError:
                continue
            raise SystemExit(f"event marker negative control {name} unexpectedly passed")
    print("event marker negative controls: 4/4 rejected (missing, duplicate, transformed, wrong-GID)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--special-map", type=Path, default=ROOT / "tiled/coco-special-screen.tmx")
    parser.add_argument("--extra-map", type=Path, default=ROOT / "tiled/coco-extra-screen.tmx")
    parser.add_argument("--tileset", type=Path, default=ROOT / "tiled/arcade-event-tiles.tsx")
    parser.add_argument("--tilesheet", type=Path, default=ROOT / "tiled/arcade-event-tiles.png")
    parser.add_argument("--sprites", type=Path, default=ROOT / "assets/arcade/sprites.json")
    parser.add_argument("--event-output", type=Path, default=ROOT / "build/ladybug-event-art.raw")
    parser.add_argument("--event-page25-output", type=Path, default=ROOT / "build/ladybug-event-page25.raw")
    parser.add_argument("--event-page26-output", type=Path, default=ROOT / "build/ladybug-event-page26.raw")
    parser.add_argument("--include-output", type=Path, default=ROOT / "build/ladybug_event_assets.inc")
    parser.add_argument("--dinosaur-output", type=Path, default=ROOT / "build/ladybug-dinosaur-art.raw")
    parser.add_argument("--manifest-output", type=Path, default=ROOT / "build/ladybug-event-assets.json")
    parser.add_argument("--self-test", action="store_true", help="run Part Vegetable marker negative controls")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.self_test:
        run_marker_negative_controls(args.special_map)
        return
    event, event_metadata = compile_event_asset(
        args.special_map, args.extra_map, args.tileset, args.tilesheet
    )
    p25_len = int(event_metadata["page25_bytes"])
    page25 = event[:p25_len]
    page26 = event[p25_len:]
    dinosaur, dinosaur_metadata = compile_dinosaur_asset(args.sprites)
    outputs = (
        (args.event_output, event),
        (args.event_page25_output, page25),
        (args.event_page26_output, page26),
        (args.dinosaur_output, dinosaur),
    )
    for path, data in outputs:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    write_event_include(args.include_output, event_metadata)
    manifest = {
        "generator": "scripts/build_event_asset_bundle.py",
        "assets": {
            "special_extra_event_art": event_metadata,
            "dinosaur": dinosaur_metadata,
        },
    }
    args.manifest_output.parent.mkdir(parents=True, exist_ok=True)
    args.manifest_output.write_text(json.dumps(manifest, indent=2) + "\n", encoding="ascii")
    print(
        f"event assets (EVD1): {event_metadata['atlas_tiles']} shared tiles "
        f"(page $25: {len(page25)}/8192 B, page $26: {len(page26)}/8192 B, "
        f"total {len(event)}/16384 B); "
        f"veg dsts SPECIAL=${int(event_metadata['special_vegetable']['fb_dst']):04X} "
        f"EXTRA=${int(event_metadata['extra_vegetable']['fb_dst']):04X}; "
        f"{len(dinosaur)} dinosaur bytes"
    )


if __name__ == "__main__":
    main()
