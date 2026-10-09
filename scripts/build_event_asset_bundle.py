#!/usr/bin/env python3
"""Compile SPECIAL/EXTRA event tiles and dinosaur sparse frames for ROM storage."""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_screen import GID_MASK, compile_sprite_codes, nearest_palette_index, pack_tile, parse_csv, tileset_ranges
from build_sparse_sprites import LEGACY_ENEMY_PEN_MAP, encode_sparse_frame

EVENT_TILE_COUNT = 320
EVENT_COLUMNS = 16
EVENT_TILE_SIZE = 8
DINOSAUR_CODES = tuple(range(89, 126))


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_file(path: Path) -> str:
    return sha256(path.read_bytes())


def event_tileset_info(map_path: Path, tileset_path: Path) -> tuple[ET.Element, int]:
    root = ET.parse(map_path).getroot()
    references = [node for node in root.findall("tileset")
                  if node.get("source") and
                  (map_path.parent / node.get("source", "")).resolve() == tileset_path.resolve()]
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
    event_range = next((item for item in ranges
                        if int(item["firstgid"]) == firstgid), None)
    if (event_range is None or event_range["name"] != tsx.get("name") or
            event_range["lastgid"] - firstgid + 1 != EVENT_TILE_COUNT):
        raise ValueError(f"{map_path}: event tileset GID range differs from TSX")
    return tsx, firstgid


def collect_event_tile_ids(map_path: Path, tileset_path: Path) -> tuple[int, list[int]]:
    root = ET.parse(map_path).getroot()
    _, firstgid = event_tileset_info(map_path, tileset_path)
    used: set[int] = set()
    for layer in root.findall("layer"):
        data = layer.find("data")
        if data is None:
            continue
        for gid_with_flags in parse_csv(data, layer.get("name", "")):
            gid = gid_with_flags & GID_MASK
            if firstgid <= gid < firstgid + EVENT_TILE_COUNT:
                used.add(gid - firstgid)
    if not used:
        raise ValueError(f"{map_path}: no event tileset references found")
    return firstgid, sorted(used)


def compile_event_asset(
        special_map: Path, extra_map: Path, tileset_path: Path,
        image_path: Path,
) -> tuple[bytes, dict[str, object]]:
    map_paths = {"special": special_map, "extra": extra_map}
    firstgids: dict[str, int] = {}
    used_by_map: dict[str, list[int]] = {}
    for name, path in map_paths.items():
        firstgid, tile_ids = collect_event_tile_ids(path, tileset_path)
        firstgids[name] = firstgid
        used_by_map[name] = tile_ids
    if firstgids["special"] != firstgids["extra"]:
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
    expected_size = (EVENT_COLUMNS * EVENT_TILE_SIZE,
                     (EVENT_TILE_COUNT + EVENT_COLUMNS - 1) // EVENT_COLUMNS * EVENT_TILE_SIZE)
    if image.size != expected_size:
        raise ValueError(f"{image_path}: expected {expected_size}, found {image.size}")

    atlas: list[bytes] = []
    atlas_ids: dict[bytes, int] = {}
    lookups: dict[str, bytearray] = {}
    for name in ("special", "extra"):
        lookup = [0xFFFF] * EVENT_TILE_COUNT
        for tile_id in used_by_map[name]:
            col = tile_id % EVENT_COLUMNS
            row = tile_id // EVENT_COLUMNS
            crop = image.crop((col * EVENT_TILE_SIZE, row * EVENT_TILE_SIZE,
                               (col + 1) * EVENT_TILE_SIZE,
                               (row + 1) * EVENT_TILE_SIZE))
            pixels: list[list[int]] = []
            for y in range(EVENT_TILE_SIZE):
                line = []
                for x in range(EVENT_TILE_SIZE):
                    red, green, blue, alpha = crop.getpixel((x, y))
                    line.append(0 if alpha == 0 else nearest_palette_index([red, green, blue]))
                pixels.append(line)
            packed = pack_tile(pixels)
            atlas_id = atlas_ids.get(packed)
            if atlas_id is None:
                atlas_id = len(atlas)
                if atlas_id > 0xFFFE:
                    raise ValueError("event art atlas exceeds 16-bit lookup capacity")
                atlas_ids[packed] = atlas_id
                atlas.append(packed)
            lookup[tile_id] = atlas_id
        lookups[name] = bytearray()
        for atlas_id in lookup:
            lookups[name].extend(struct.pack("<H", atlas_id))

    header = b"EVT1" + bytes((1,)) + struct.pack(
        "<HHH", len(atlas), EVENT_TILE_COUNT, firstgids["special"]
    )
    raw = header + b"".join(atlas) + bytes(lookups["special"]) + bytes(lookups["extra"])
    metadata = {
        "format": "EVT1",
        "version": 1,
        "header_bytes": len(header),
        "atlas_tile_bytes": EVENT_TILE_SIZE * EVENT_TILE_SIZE // 2,
        "atlas_tiles": len(atlas),
        "atlas_bytes": sum(map(len, atlas)),
        "source_tile_count": EVENT_TILE_COUNT,
        "atlas_index_bytes": 2,
        "unused_lookup_value": 65535,
        "map_lookup_entries_each": EVENT_TILE_COUNT,
        "map_lookup_bytes_each": EVENT_TILE_COUNT * 2,
        "firstgid": firstgids["special"],
        "deduplication": "native 4bpp tile bytes shared across SPECIAL and EXTRA",
        "maps": {
            name: {
                "tmx": str(path.relative_to(ROOT)),
                "tmx_sha256": hash_file(path),
                "used_source_tile_ids": used_by_map[name],
                "lookup_offset": len(header) + len(atlas) * 32 + (0 if name == "special" else EVENT_TILE_COUNT * 2),
            }
            for name, path in map_paths.items()
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


def compile_dinosaur_asset(sprites_path: Path) -> tuple[bytes, dict[str, object]]:
    frames = compile_sprite_codes(sprites_path, DINOSAUR_CODES)
    streams = [encode_sparse_frame(frame, LEGACY_ENEMY_PEN_MAP) for frame in frames]
    header_bytes = 6
    index_bytes = 5 * len(streams)
    stream_offset = 0
    index = bytearray()
    frame_details = []
    for code, stream in zip(DINOSAUR_CODES, streams):
        index.extend((code, stream_offset & 0xFF, (stream_offset >> 8) & 0xFF,
                      len(stream) & 0xFF, (len(stream) >> 8) & 0xFF))
        frame_details.append({"source_sprite_code": code,
                              "offset_from_stream_data": stream_offset,
                              "bytes": len(stream),
                              "sha256": sha256(stream)})
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--special-map", type=Path, default=ROOT / "tiled/coco-special-screen.tmx")
    parser.add_argument("--extra-map", type=Path, default=ROOT / "tiled/coco-extra-screen.tmx")
    parser.add_argument("--tileset", type=Path, default=ROOT / "tiled/arcade-event-tiles.tsx")
    parser.add_argument("--tilesheet", type=Path, default=ROOT / "tiled/arcade-event-tiles.png")
    parser.add_argument("--sprites", type=Path, default=ROOT / "assets/arcade/sprites.json")
    parser.add_argument("--event-output", type=Path, default=ROOT / "build/ladybug-event-art.raw")
    parser.add_argument("--dinosaur-output", type=Path, default=ROOT / "build/ladybug-dinosaur-art.raw")
    parser.add_argument("--manifest-output", type=Path, default=ROOT / "build/ladybug-event-assets.json")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    event, event_metadata = compile_event_asset(
        args.special_map, args.extra_map, args.tileset, args.tilesheet
    )
    dinosaur, dinosaur_metadata = compile_dinosaur_asset(args.sprites)
    outputs = ((args.event_output, event), (args.dinosaur_output, dinosaur))
    for path, data in outputs:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
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
        f"event assets: {event_metadata['atlas_tiles']} shared tiles; "
        f"{len(event_metadata['maps']['special']['used_source_tile_ids'])} SPECIAL and "
        f"{len(event_metadata['maps']['extra']['used_source_tile_ids'])} EXTRA source tiles; "
        f"{len(event)} event bytes; {len(dinosaur)} dinosaur bytes"
    )


if __name__ == "__main__":
    main()
