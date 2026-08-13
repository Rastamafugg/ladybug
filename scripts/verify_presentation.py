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
    PAGE_BYTES,
    ATTRACT_ACTOR_SURFACE_ADDRESS,
    ATTRACT_ACTOR_SURFACE_PAGE,
    ATTRACT_ACTOR_DESTINATION_ADDRESS,
    ATTRACT_ACTOR_PHASE_POINTER_ADDRESS,
    compile_attract_surfaces,
    compose_attract_frames,
    lzss_compress,
    coin_tile,
    compile_map,
    compile_screen,
    encode_map,
    load_chars,
    parse_attract_actors,
    parse_instruction_contract,
    title_framebuffer,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tiled-dir", type=Path, required=True)
    parser.add_argument("--chars", type=Path, required=True)
    parser.add_argument("--gameplay-map", type=Path, required=True)
    parser.add_argument("--gameplay-maze", type=Path, required=True)
    parser.add_argument("--gameplay-chars", type=Path, required=True)
    parser.add_argument("--gameplay-sprites", type=Path, required=True)
    parser.add_argument("--payload", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    return parser.parse_args()


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    args = parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="ascii"))
    chars = load_chars(args.chars)
    sprites = json.loads(args.gameplay_sprites.read_text(encoding="utf-8"))
    if isinstance(sprites, dict):
        sprites = sprites["sprites"]
    actors = parse_attract_actors(args.tiled_dir / MAP_FILES["attract"])
    _gameplay_map, gameplay_tiles, *_ = compile_screen(
        args.gameplay_map,
        args.gameplay_maze,
        args.gameplay_chars,
        args.gameplay_sprites,
    )
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
    instruction = parse_instruction_contract(
        args.tiled_dir / MAP_FILES["instructions"], chars, sprites, tiles, tile_ids
    )
    payload = args.payload.read_bytes()
    coin_bytes = coin_tile()
    if coin_bytes not in tiles:
        tiles.append(coin_bytes)
    gameplay_tile_ids = {tile: index for index, tile in enumerate(gameplay_tiles)}
    cold_ids = [index for index, tile in enumerate(tiles)
                if tile not in gameplay_tile_ids]
    shared_ids = [index for index, tile in enumerate(tiles)
                  if tile in gameplay_tile_ids]
    order = cold_ids + shared_ids
    remap = {old: new for new, old in enumerate(order)}
    maps = [bytes(remap[value] for value in data) for data in maps]
    event_table = bytearray(instruction["event_table"])
    event_bytes = len(event_table) // len(instruction["events"])
    for index, event in enumerate(instruction["events"]):
        if event["hud_tile_2_id"]:
            event_table[index * event_bytes + 10] = remap[event["hud_tile_2_id"]]
        if event["hud_destination"]:
            event_table[index * event_bytes + 11] = remap[event["hud_tile_id"]]
    instruction["event_table"] = bytes(event_table)
    ordered_tiles = [tiles[index] for index in order]
    cold_only_tiles = ordered_tiles[:len(cold_ids)]
    gameplay_lookup = bytes(
        gameplay_tile_ids[tile] for tile in ordered_tiles[len(cold_ids):]
    )
    encoded_maps = [encode_map(data) for data in maps]
    expected = bytearray(
        b"".join(cold_only_tiles) + gameplay_lookup +
        b"".join(encoded_maps)
    )
    event_count = len(instruction["events"])
    for padding in range(PAGE_BYTES):
        start = len(expected) + padding
        if all(
            (start + index * event_bytes) % PAGE_BYTES
            <= PAGE_BYTES - event_bytes
            for index in range(event_count)
        ):
            expected.extend(bytes(padding))
            break
    else:
        raise SystemExit("presentation proof: event table cannot be page-aligned")
    event_offset = len(expected)
    expected.extend(instruction["event_table"])
    colour_pointer_offset = len(expected)
    colour_streams = instruction["target_colour_streams"]
    expected.extend(bytes(len(colour_streams) * 2))
    for index, stream in enumerate(colour_streams):
        offset = len(expected)
        start = colour_pointer_offset + index * 2
        expected[start:start + 2] = offset.to_bytes(2, "big")
        expected.extend(stream)
    pointer_offset = len(expected)
    streams = [*instruction["death_streams"], instruction["angel_stream"]]
    expected.extend(bytes(len(streams) * 2))
    stream_offsets = []
    for stream in streams:
        page_offset = len(expected) % PAGE_BYTES
        if page_offset + len(stream) > PAGE_BYTES:
            expected.extend(bytes(PAGE_BYTES - page_offset))
        stream_offsets.append(len(expected))
        expected.extend(stream)
    for index, offset in enumerate(stream_offsets):
        start = pointer_offset + index * 2
        expected[start:start + 2] = offset.to_bytes(2, "big")
    if payload != bytes(expected):
        raise SystemExit("presentation proof: cold payload differs from independent compile")
    if len(tiles) != manifest["tile_count"]:
        raise SystemExit("presentation proof: tile count differs from manifest")
    if manifest.get("coin_tile") != remap[tiles.index(coin_bytes)]:
        raise SystemExit("presentation proof: coin tile differs from manifest")
    if manifest["cold_payload"]["bytes"] != len(payload):
        raise SystemExit("presentation proof: payload size differs from manifest")
    if manifest["cold_payload"]["sha256"] != digest(payload):
        raise SystemExit("presentation proof: payload hash differs from manifest")
    if manifest.get("map_output_offset") != MAP_OUTPUT_OFFSET:
        raise SystemExit("presentation proof: map output offset differs")
    if manifest.get("cold_only_tile_count") != len(cold_only_tiles):
        raise SystemExit("presentation proof: cold-only tile count differs")
    if manifest.get("gameplay_tile_base") != len(cold_only_tiles):
        raise SystemExit("presentation proof: gameplay tile base differs")
    if manifest.get("gameplay_lookup_offset") != len(cold_only_tiles) * 32:
        raise SystemExit("presentation proof: gameplay lookup offset differs")
    if manifest.get("gameplay_lookup_bytes") != len(gameplay_lookup):
        raise SystemExit("presentation proof: gameplay lookup size differs")
    if manifest.get("map_stream_total_bytes") != sum(map(len, encoded_maps)):
        raise SystemExit("presentation proof: encoded map size differs")
    choreography = manifest.get("instruction_choreography", {})
    if (choreography.get("event_table_offset") != event_offset or
            choreography.get("event_table_bytes") != len(instruction["event_table"]) or
            choreography.get("event_table_sha256") != digest(instruction["event_table"]) or
            choreography.get("death_pointer_offset") != pointer_offset or
            choreography.get("death_stream_offsets") != stream_offsets or
            choreography.get("death_stream_sha256") != [digest(stream) for stream in streams]):
        raise SystemExit("presentation proof: instruction choreography payload differs")
    destinations = b"".join(int(actor["destination"]).to_bytes(2, "big")
                            for actor in actors)
    destination_manifest = manifest.get("attract_actor_destinations", {})
    if (destination_manifest.get("bytes") != 14 or
            destination_manifest.get("sha256") != digest(destinations)):
        raise SystemExit("presentation proof: seven actor destinations differ")
    surfaces = compile_attract_surfaces(maps[0], ordered_tiles, sprites, actors)
    surface_manifest = manifest.get("attract_actor_surfaces", {})
    if (surface_manifest.get("bytes") != 2688 or
            surface_manifest.get("page") != ATTRACT_ACTOR_SURFACE_PAGE or
            surface_manifest.get("address") != ATTRACT_ACTOR_SURFACE_ADDRESS or
            surface_manifest.get("sha256") != digest(surfaces)):
        raise SystemExit("presentation proof: attract actor surfaces differ")
    attract_frames = compose_attract_frames(maps[0], ordered_tiles, surfaces, actors)
    if surface_manifest.get("phase_frame_sha256") != [digest(frame) for frame in attract_frames]:
        raise SystemExit("presentation proof: attract composed-frame hashes differ")
    phase_pointers = b"".join((ATTRACT_ACTOR_SURFACE_ADDRESS + phase * 896).to_bytes(2, "big")
                              for phase in range(3))
    compressed = lzss_compress(surfaces)
    metadata = destinations + phase_pointers
    bundle_manifest = manifest.get("attract_actor_bundle", {})
    if (bundle_manifest.get("compressed_bytes") != len(compressed) or
            bundle_manifest.get("expanded_bytes") != 2688 or
            bundle_manifest.get("destination_table_address") != ATTRACT_ACTOR_DESTINATION_ADDRESS or
            bundle_manifest.get("phase_pointer_address") != ATTRACT_ACTOR_PHASE_POINTER_ADDRESS or
            bundle_manifest.get("compressed_sha256") != digest(compressed) or
            bundle_manifest.get("metadata_bytes") != 20 or
            bundle_manifest.get("metadata_sha256") != digest(metadata)):
        raise SystemExit("presentation proof: attract actor loader bundle differs")
    for index, encoded in enumerate(encoded_maps):
        if manifest["map_stream_bytes"][index] != len(encoded):
            raise SystemExit(f"presentation proof: encoded map {index} size differs")
        if manifest["map_stream_offsets"][index] != (
                len(cold_only_tiles) * 32 + len(gameplay_lookup) +
                sum(map(len, encoded_maps[:index]))
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
    if manifest.get("static_frame_sha256") != [
            digest(title_framebuffer(data, ordered_tiles))
            for data in maps
    ]:
        raise SystemExit("presentation proof: static framebuffer hashes differ")
    if len(payload) > 4 * 0x2000:
        raise SystemExit("presentation proof: cold payload exceeds four pages")
    if len(payload) > 10874:
        raise SystemExit("presentation proof: cold payload exceeds PERF-004 minimum reduction limit")
    if len(payload) > manifest["cold_payload_limit"]:
        raise SystemExit("presentation proof: cold payload exceeds Plan A source limit")
    print(
        f"presentation proof: {len(maps)} maps, {len(tiles)} tiles, "
        f"{len(payload)} bytes, hashes and four-page bound valid"
    )


if __name__ == "__main__":
    main()
