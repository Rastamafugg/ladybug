#!/usr/bin/env python3
"""Verify the six static presentation maps and their cold payload."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from build_presentation import (
    MAP_FILES,
    MAP_NAMES,
    MAP_OUTPUT_OFFSET,
    coin_tile,
    compile_map,
    encode_map,
    load_chars,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tiled-dir", type=Path, required=True)
    parser.add_argument("--chars", type=Path, required=True)
    parser.add_argument("--payload", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    return parser.parse_args()


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    args = parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="ascii"))
    chars = load_chars(args.chars)
    tiles: list[bytes] = []
    tile_ids: dict[bytes, int] = {}
    maps = []
    for name in MAP_NAMES:
        data, _info = compile_map(
            args.tiled_dir / MAP_FILES[name], chars, tiles, tile_ids
        )
        if len(data) != 960:
            raise SystemExit(f"presentation proof: {name} is not 960 cells")
        maps.append(data)
    payload = args.payload.read_bytes()
    encoded_maps = [encode_map(data) for data in maps]
    coin_bytes = coin_tile()
    if coin_bytes not in tiles:
        tiles.append(coin_bytes)
    expected = b"".join(tiles) + b"".join(encoded_maps)
    if payload != expected:
        raise SystemExit("presentation proof: cold payload differs from independent compile")
    if len(tiles) != manifest["tile_count"]:
        raise SystemExit("presentation proof: tile count differs from manifest")
    if manifest.get("coin_tile") != tiles.index(coin_bytes):
        raise SystemExit("presentation proof: coin tile differs from manifest")
    if manifest["cold_payload"]["bytes"] != len(payload):
        raise SystemExit("presentation proof: payload size differs from manifest")
    if manifest["cold_payload"]["sha256"] != digest(payload):
        raise SystemExit("presentation proof: payload hash differs from manifest")
    if manifest.get("map_output_offset") != MAP_OUTPUT_OFFSET:
        raise SystemExit("presentation proof: map output offset differs")
    if manifest.get("map_stream_total_bytes") != sum(map(len, encoded_maps)):
        raise SystemExit("presentation proof: encoded map size differs")
    for index, encoded in enumerate(encoded_maps):
        if manifest["map_stream_bytes"][index] != len(encoded):
            raise SystemExit(f"presentation proof: encoded map {index} size differs")
        if manifest["map_stream_offsets"][index] != (
                len(tiles) * 32 + sum(map(len, encoded_maps[:index]))
        ):
            raise SystemExit(f"presentation proof: encoded map {index} offset differs")
        decoded = bytearray()
        for cursor in range(0, len(encoded), 2):
            decoded.extend(bytes((encoded[cursor + 1],)) * encoded[cursor])
        if bytes(decoded) != maps[index]:
            raise SystemExit(f"presentation proof: encoded map {index} does not decode")
    for entry, data in zip(manifest["maps"], maps):
        if entry["sha256"] != digest(data):
            raise SystemExit(f"presentation proof: {entry['name']} hash differs")
    if len(payload) > 4 * 0x2000:
        raise SystemExit("presentation proof: cold payload exceeds four pages")
    if len(payload) > manifest["cold_payload_limit"]:
        raise SystemExit("presentation proof: cold payload exceeds Plan A source limit")
    print(
        f"presentation proof: {len(maps)} maps, {len(tiles)} tiles, "
        f"{len(payload)} bytes, hashes and four-page bound valid"
    )


if __name__ == "__main__":
    main()
