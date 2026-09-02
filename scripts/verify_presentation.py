#!/usr/bin/env python3
"""Verify the six static presentation maps and their cold payload."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from build_presentation import (
    BLACK,
    GREEN,
    MAP_FILES,
    MAP_NAMES,
    MAP_OUTPUT_OFFSET,
    PAGE_BYTES,
    WHITE,
    ATTRACT_ACTOR_SURFACE_ADDRESS,
    ATTRACT_ACTOR_SURFACE_PAGE,
    ATTRACT_ACTOR_DESTINATION_ADDRESS,
    ATTRACT_ACTOR_PHASE_POINTER_ADDRESS,
    blend_native_surface,
    compile_attract_surfaces,
    compose_attract_frames,
    lzss_compress,
    coin_tile,
    compile_profile_maps,
    compile_screen,
    encode_map,
    framebuffer_destination,
    HIGH_SCORE_NAME_COLUMN,
    HIGH_SCORE_RECORD_ROWS,
    HIGH_SCORE_SCORE_COLUMN,
    load_chars,
    load_demo_route,
    load_demo_walk,
    parse_attract_actors,
    parse_enter_high_score_contract,
    enter_high_score_edge_masks,
    enter_high_score_full_edge_masks,
    parse_instruction_contract,
    perimeter_box_cells,
    pack_tile,
    recolor,
    replace_packed_colour,
    rotate_ccw,
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
    parser.add_argument("--demo-route", type=Path, required=True)
    parser.add_argument("--demo-walk", type=Path, required=True)
    parser.add_argument("--payload", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--tile-patches", type=Path, required=True)
    parser.add_argument("--development-profile", type=int, choices=(0, 1), default=0)
    parser.add_argument("--complete-profile", type=int, choices=(0, 1), default=0)
    parser.add_argument("--highscore-test-profile", type=int, choices=(0, 1), default=0)
    return parser.parse_args()


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def lzss_expand(stream: bytes, expected_bytes: int) -> bytes:
    output = bytearray()
    cursor = 0
    while len(output) < expected_bytes:
        if cursor >= len(stream):
            raise ValueError("compressed atlas ended before its output bound")
        flags = stream[cursor]
        cursor += 1
        for bit in range(8):
            if len(output) >= expected_bytes:
                break
            if flags & (1 << bit):
                if cursor >= len(stream):
                    raise ValueError("compressed atlas literal is truncated")
                output.append(stream[cursor])
                cursor += 1
                continue
            if cursor + 2 > len(stream):
                raise ValueError("compressed atlas match is truncated")
            token = int.from_bytes(stream[cursor:cursor + 2], "big")
            cursor += 2
            distance = token >> 4
            length = (token & 0x0F) + 3
            if distance == 0 or distance > len(output):
                raise ValueError("compressed atlas match distance is invalid")
            for _ in range(length):
                output.append(output[-distance])
                if len(output) > expected_bytes:
                    raise ValueError("compressed atlas exceeds its output bound")
    return bytes(output)


def main() -> None:
    args = parse_args()
    development_profile = bool(args.development_profile)
    complete_profile = bool(args.complete_profile)
    highscore_test_profile = bool(args.highscore_test_profile)
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
    maps, map_info = compile_profile_maps(
        args.tiled_dir, chars, tiles, tile_ids, development_profile,
        highscore_test_profile, complete_profile,
    )
    for name, data in zip(MAP_NAMES, maps):
        if len(data) != 960:
            raise SystemExit(f"presentation proof: {name} is not 960 cells")
    if development_profile:
        instruction = parse_instruction_contract(
            args.tiled_dir / MAP_FILES["instructions"], chars, sprites,
            tiles, tile_ids,
        )
    else:
        instruction = parse_instruction_contract(
            args.tiled_dir / MAP_FILES["instructions"], chars, sprites, [], {}
        )
    name_entry = (
        parse_enter_high_score_contract(
            args.tiled_dir / MAP_FILES["enter-high-score"], chars, sprites,
            tiles, tile_ids,
        )
        if highscore_test_profile or complete_profile
        else {
            "grid_tile_ids": [], "cursor_stream": b"", "node_tile_ids": [],
            "node_cells": [], "node_destinations": [],
            "action_records": [], "default_name_tile_ids": [],
            "top_right_destinations": [],
        }
    )
    _arcade_route, arcade_route_manifest = load_demo_route(args.demo_route)
    demo_walk, demo_walk_manifest = load_demo_walk(
        args.demo_walk, arcade_route_manifest
    )
    payload = args.payload.read_bytes()
    coin_bytes = coin_tile()
    if coin_bytes not in tiles:
        tiles.append(coin_bytes)
    if name_entry["grid_tile_ids"]:
        enter_map = maps[MAP_NAMES.index("enter-high-score")]
        base_ids = []
        green_ids = []
        for x, y in perimeter_box_cells():
            base_id = enter_map[y * 40 + x]
            base_ids.append(base_id)
            green_tile = replace_packed_colour(tiles[base_id], WHITE, GREEN)
            green_ids.append(tiles.index(green_tile) if green_tile in tiles else len(tiles))
            if green_ids[-1] == len(tiles):
                tiles.append(green_tile)
        name_entry["timer_base_tile_ids"] = base_ids
        name_entry["timer_green_tile_ids"] = green_ids
    gameplay_tile_ids = {tile: index for index, tile in enumerate(gameplay_tiles)}
    timer_green_tiles: list[bytes] = []
    timer_green_indexes: list[int] = []
    for tile_id in name_entry.get("timer_green_tile_ids", []):
        tile = tiles[int(tile_id)]
        if tile not in timer_green_tiles:
            timer_green_tiles.append(tile)
        timer_green_indexes.append(timer_green_tiles.index(tile))
    live_ids = set().union(*(set(data) for data in maps))
    live_ids.add(tiles.index(coin_bytes))
    if development_profile:
        live_ids.add(int(instruction["black_tile_id"]))
        for group in ("reward_tile_ids", "multiplier_tile_ids", "value_tile_ids"):
            for ids in instruction[group].values():
                live_ids.update(int(tile_id) for tile_id in ids)
        for event in instruction["events"]:
            if event["hud_destination"]:
                live_ids.add(int(event["hud_tile_id"]))
                if event["hud_tile_2_id"]:
                    live_ids.add(int(event["hud_tile_2_id"]))
    if name_entry["grid_tile_ids"]:
        for key in (
            "grid_tile_ids", "default_name_tile_ids", "top_name_tile_ids",
            "timer_base_tile_ids",
        ):
            live_ids.update(int(tile_id) for tile_id in name_entry[key])
        live_ids.update(
            int(tile_id) for tile_id in name_entry["node_tile_ids"]
            if tile_id not in (0xFD, 0xFE, 0xFF)
        )
        live_ids.update(
            int(tile_id) for _x, _y, tile_id in name_entry["action_records"]
            if tile_id not in (0xFD, 0xFE, 0xFF)
        )
        if complete_profile and name_entry["timer_green_tile_ids"]:
            live_ids.add(int(name_entry["timer_green_tile_ids"][0]))
    overlay_pairs: list[tuple[int, int]] = []
    if complete_profile:
        if len(live_ids) - 256 != 2:
            raise SystemExit("presentation proof: complete union is not a two-slot overlay")
        instruction_ids = set(maps[MAP_NAMES.index("instructions")])
        highscore_ids = set().union(*(
            set(maps[MAP_NAMES.index(name)])
            for name in ("game-over", "enter-high-score", "high-score")
        ))
        other_ids = set().union(*(
            set(maps[MAP_NAMES.index(name)])
            for name in ("attract", "level-start")
        ))
        instruction_candidates = sorted(
            tile_id for tile_id in instruction_ids - highscore_ids - other_ids
            if tile_id in live_ids and tiles[tile_id] not in gameplay_tile_ids
        )
        highscore_candidates = sorted(
            tile_id for tile_id in highscore_ids - instruction_ids - other_ids
            if tile_id in live_ids and tiles[tile_id] not in gameplay_tile_ids
        )
        overlay_pairs = list(zip(
            instruction_candidates[:2], highscore_candidates[:2]
        ))
        if len(overlay_pairs) != 2:
            raise SystemExit("presentation proof: phase-exclusive overlay pairs missing")
    elif len(live_ids) > 256:
        raise SystemExit("presentation proof: atlas exceeds one-byte tile IDs")
    overlay_replacements = {
        highscore_id: instruction_id
        for instruction_id, highscore_id in overlay_pairs
    }
    representatives = [
        tile_id for tile_id in sorted(live_ids)
        if tile_id not in overlay_replacements
    ]
    cold_ids = [index for index in representatives
                if tiles[index] not in gameplay_tile_ids]
    shared_ids = [index for index in representatives
                  if tiles[index] in gameplay_tile_ids]
    order = cold_ids + shared_ids
    representative_remap = {old: new for new, old in enumerate(order)}
    remap = {
        old: representative_remap[overlay_replacements.get(old, old)]
        for old in live_ids
    }
    instruction_patch = b"".join(
        tiles[instruction_id] for instruction_id, _ in overlay_pairs
    )
    highscore_patch = b"".join(
        tiles[highscore_id] for _, highscore_id in overlay_pairs
    )
    if args.tile_patches.read_bytes() != instruction_patch + highscore_patch:
        raise SystemExit("presentation proof: phase tile patch bytes differ")
    maps = [bytes(remap[value] for value in data) for data in maps]
    if development_profile:
        event_table = bytearray(instruction["event_table"])
        event_bytes = len(event_table) // len(instruction["events"])
        for index, event in enumerate(instruction["events"]):
            if event["hud_tile_2_id"]:
                event_table[index * event_bytes + 10] = remap[event["hud_tile_2_id"]]
            if event["hud_destination"]:
                event_table[index * event_bytes + 11] = remap[event["hud_tile_id"]]
        instruction["event_table"] = bytes(event_table)
    else:
        event_bytes = 12
        instruction["event_table"] = b""
        instruction["target_colour_streams"] = []
        instruction["cucumber_stream"] = b""
        instruction["death_streams"] = []
        instruction["angel_stream"] = b""
    if name_entry["grid_tile_ids"]:
        name_entry["grid_tile_ids"] = [
            remap[int(tile_id)] for tile_id in name_entry["grid_tile_ids"]
        ]
        name_entry["node_tile_ids"] = [
            tile_id if tile_id in (0xFD, 0xFE, 0xFF) else remap[int(tile_id)]
            for tile_id in name_entry["node_tile_ids"]
        ]
        name_entry["action_records"] = [
            [x, y, remap[int(tile_id)]]
            if tile_id not in (0xFD, 0xFE, 0xFF)
            else [x, y, tile_id]
            for x, y, tile_id in name_entry["action_records"]
        ]
        name_entry["default_name_tile_ids"] = [
            remap[int(tile_id)] for tile_id in name_entry["default_name_tile_ids"]
        ]
        name_entry["timer_base_tile_ids"] = [
            remap[int(tile_id)] for tile_id in name_entry["timer_base_tile_ids"]
        ]
        name_entry["timer_green_tile_ids"] = []
    ordered_tiles = [tiles[index] for index in order]
    rotated_chars = [rotate_ccw(tile) for tile in chars]
    omitted_glyphs = [
        code for code in range(37)
        if pack_tile(recolor(
            rotated_chars[code], (BLACK, WHITE, WHITE, WHITE)
        )) not in ordered_tiles
    ] if development_profile else []
    if manifest.get("development_omitted_glyph_codes") != omitted_glyphs:
        raise SystemExit("presentation proof: omitted development glyphs differ")
    cold_only_tiles = ordered_tiles[:len(cold_ids)]
    gameplay_lookup = bytes(
        gameplay_tile_ids[tile] for tile in ordered_tiles[len(cold_ids):]
    )
    encoded_maps = [encode_map(data) for data in maps]
    tile_atlas = b"".join(cold_only_tiles)
    stored_tile_atlas = (
        lzss_compress(tile_atlas) if highscore_test_profile else tile_atlas
    )
    if highscore_test_profile:
        expanded_tile_atlas = lzss_expand(stored_tile_atlas, len(tile_atlas))
        if expanded_tile_atlas != tile_atlas:
            raise SystemExit("presentation proof: compressed tile atlas does not expand")
    expected = bytearray(
        stored_tile_atlas + gameplay_lookup + b"".join(encoded_maps)
    )
    event_count = len(instruction["events"]) if development_profile else 0
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
        page_offset = len(expected) % PAGE_BYTES
        if page_offset + len(stream) > PAGE_BYTES:
            expected.extend(bytes(PAGE_BYTES - page_offset))
        offset = len(expected)
        start = colour_pointer_offset + index * 2
        expected[start:start + 2] = offset.to_bytes(2, "big")
        expected.extend(stream)
    cucumber_stream = instruction["cucumber_stream"]
    cucumber_page_offset = len(expected) % PAGE_BYTES
    if cucumber_page_offset + len(cucumber_stream) > PAGE_BYTES:
        expected.extend(bytes(PAGE_BYTES - cucumber_page_offset))
    cucumber_offset = len(expected)
    expected.extend(cucumber_stream)
    pointer_offset = len(expected)
    streams = (
        [*instruction["death_streams"], instruction["angel_stream"]]
        if development_profile else []
    )
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
    name_entry_cursor_offset = len(expected)
    expected.extend(name_entry["cursor_stream"])
    demo_route_offset = len(expected)
    expected.extend(demo_walk)
    name_entry_timer_tiles_offset = len(expected)
    expected.extend(b"".join(timer_green_tiles))
    name_entry_timer_offset = len(expected)
    for cell, green_index in zip(perimeter_box_cells(), timer_green_indexes):
        expected.extend(
            framebuffer_destination(cell).to_bytes(2, "big") +
            (name_entry_timer_tiles_offset + green_index * 32).to_bytes(2, "big")
        )
    name_entry_edge_mask_offset = len(expected)
    edge_masks = enter_high_score_edge_masks() if name_entry["grid_tile_ids"] else b""
    expected.extend(edge_masks)
    full_edge_mask_offset = len(expected)
    full_edge_masks = (
        enter_high_score_full_edge_masks(
            args.tiled_dir / MAP_FILES["enter-high-score"]
        ) if name_entry["grid_tile_ids"] else b""
    )
    expected.extend(full_edge_masks)
    action_table = bytes(
        byte
        for x, y, tile_id in name_entry.get("action_records", [])
        for byte in (x - 8, y, tile_id)
    )
    action_table_offset = len(expected)
    expected.extend(action_table)
    if payload != bytes(expected):
        raise SystemExit("presentation proof: cold payload differs from independent compile")
    if len(tiles) != manifest["tile_count"]:
        if len(ordered_tiles) != manifest["tile_count"]:
            raise SystemExit("presentation proof: tile count differs from manifest")
    overlay_manifest = manifest.get("phase_tile_overlay", {})
    if (
        overlay_manifest.get("enabled") != bool(overlay_pairs) or
        overlay_manifest.get("slot_ids") != [remap[left] for left, _ in overlay_pairs] or
        overlay_manifest.get("instruction_patch_bytes") != len(instruction_patch) or
        overlay_manifest.get("highscore_patch_bytes") != len(highscore_patch) or
        overlay_manifest.get("instruction_patch_sha256") != digest(instruction_patch) or
        overlay_manifest.get("highscore_patch_sha256") != digest(highscore_patch)
    ):
        raise SystemExit("presentation proof: phase tile overlay manifest differs")
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
    if manifest.get("tile_atlas_compressed_bytes") != len(stored_tile_atlas):
        raise SystemExit("presentation proof: compressed tile atlas size differs")
    if manifest.get("tile_atlas_expanded_bytes") != len(cold_only_tiles) * 32:
        raise SystemExit("presentation proof: expanded tile atlas size differs")
    expected_runtime_offset = PAGE_BYTES if highscore_test_profile else 0
    if manifest.get("tile_atlas_runtime_offset") != expected_runtime_offset:
        raise SystemExit("presentation proof: tile atlas runtime page offset differs")
    if manifest.get("gameplay_lookup_offset") != len(stored_tile_atlas):
        raise SystemExit("presentation proof: gameplay lookup offset differs")
    if manifest.get("gameplay_lookup_bytes") != len(gameplay_lookup):
        raise SystemExit("presentation proof: gameplay lookup size differs")
    if manifest.get("map_stream_total_bytes") != sum(map(len, encoded_maps)):
        raise SystemExit("presentation proof: encoded map size differs")
    choreography = manifest.get("instruction_choreography", {})
    if (choreography.get("emitted") != development_profile or
            choreography.get("event_table_offset") != event_offset or
            choreography.get("event_table_bytes") != len(instruction["event_table"]) or
            choreography.get("event_table_sha256") != digest(instruction["event_table"]) or
            choreography.get("cucumber_stream_offset") != cucumber_offset or
            choreography.get("cucumber_stream_bytes") != len(cucumber_stream) or
            choreography.get("death_pointer_offset") != pointer_offset or
            choreography.get("death_stream_offsets") != stream_offsets or
            choreography.get("death_stream_sha256") != [digest(stream) for stream in streams]):
        raise SystemExit("presentation proof: instruction choreography payload differs")
    route_manifest = manifest.get("demo_route", {})
    expected_route_manifest = {
        **demo_walk_manifest,
        "cold_offset": demo_route_offset,
        "bytes": len(demo_walk),
    }
    if route_manifest != expected_route_manifest:
        raise SystemExit("presentation proof: demo route provenance differs")
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
                len(stored_tile_atlas) + len(gameplay_lookup) +
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
    if manifest.get("development_profile") != bool(args.development_profile):
        raise SystemExit("presentation proof: development profile differs")
    if manifest.get("complete_profile") != complete_profile:
        raise SystemExit("presentation proof: complete profile differs")
    if manifest.get("highscore_test_profile") != highscore_test_profile:
        raise SystemExit("presentation proof: high-score test profile differs")
    name_manifest = manifest.get("high_score_name_entry", {})
    if (
        name_manifest.get("emitted") != bool(name_entry["grid_tile_ids"]) or
        name_manifest.get("cursor_stream_offset") != name_entry_cursor_offset or
        name_manifest.get("cursor_stream_bytes") != len(name_entry["cursor_stream"]) or
        name_manifest.get("cursor_stream_sha256") != digest(name_entry["cursor_stream"]) or
        name_manifest.get("grid_tile_ids") != name_entry["grid_tile_ids"] or
        name_manifest.get("node_tile_ids") != name_entry["node_tile_ids"] or
        name_manifest.get("node_cells") != [list(cell) for cell in name_entry["node_cells"]] or
        name_manifest.get("action_records") != name_entry.get("action_records", []) or
        name_manifest.get("default_name_tile_ids") != name_entry.get("default_name_tile_ids", []) or
        name_manifest.get("node_destinations") != name_entry["node_destinations"] or
        name_manifest.get("top_right_destinations") != name_entry.get("top_right_destinations", []) or
        name_manifest.get("timer_table_offset") != name_entry_timer_offset or
        name_manifest.get("timer_table_bytes") != len(name_entry.get("timer_base_tile_ids", [])) * 4 or
        name_manifest.get("timer_tile_data_offset") != name_entry_timer_tiles_offset or
        name_manifest.get("timer_tile_data_bytes") != len(timer_green_tiles) * 32 or
        name_manifest.get("timer_base_tile_ids") != name_entry.get("timer_base_tile_ids", []) or
        name_manifest.get("timer_green_tile_ids") != name_entry.get("timer_green_tile_ids", []) or
        name_manifest.get("edge_mask_table_offset") != name_entry_edge_mask_offset or
        name_manifest.get("edge_mask_table_bytes") != len(edge_masks) or
        name_manifest.get("edge_masks") != list(edge_masks) or
        name_manifest.get("full_edge_mask_table_offset") != full_edge_mask_offset or
        name_manifest.get("full_edge_mask_table_bytes") != len(full_edge_masks) or
        name_manifest.get("full_edge_masks") != list(full_edge_masks) or
        name_manifest.get("action_table_offset") != action_table_offset or
        name_manifest.get("action_table_bytes") != len(action_table) or
        name_manifest.get("action_table") != list(action_table)
    ):
        raise SystemExit("presentation proof: name-entry metadata differs")
    for entry, expected in zip(manifest["maps"], map_info):
        for field in ("authored_map_sha256", "authored_frame_sha256", "emission"):
            if entry.get(field) != expected[field]:
                raise SystemExit(
                    f"presentation proof: {entry['name']} {field} differs"
                )
    static_frame_hashes = []
    highscore_ordered_tiles = list(ordered_tiles)
    for slot_id, tile in zip(
            [remap[left] for left, _ in overlay_pairs],
            (highscore_patch[index:index + 32]
             for index in range(0, len(highscore_patch), 32))):
        highscore_ordered_tiles[slot_id] = tile
    for index, data in enumerate(maps):
        frame = title_framebuffer(
            data,
            highscore_ordered_tiles if index in (
                MAP_NAMES.index("game-over"),
                MAP_NAMES.index("enter-high-score"),
                MAP_NAMES.index("high-score"),
            ) else ordered_tiles,
        )
        if development_profile and index == MAP_NAMES.index("instructions"):
            blend_native_surface(
                frame, instruction["cucumber_destination"],
                instruction["cucumber_native"],
            )
        static_frame_hashes.append(digest(frame))
    if manifest.get("static_frame_sha256") != static_frame_hashes:
        raise SystemExit("presentation proof: static framebuffer hashes differ")
    expected_high_score = {
        "record_rows": list(HIGH_SCORE_RECORD_ROWS),
        "name_column": HIGH_SCORE_NAME_COLUMN,
        "score_column": HIGH_SCORE_SCORE_COLUMN,
        "name_destinations": [
            framebuffer_destination((HIGH_SCORE_NAME_COLUMN, row))
            for row in HIGH_SCORE_RECORD_ROWS
        ],
        "score_destinations": [
            framebuffer_destination((HIGH_SCORE_SCORE_COLUMN, row))
            for row in HIGH_SCORE_RECORD_ROWS
        ],
    }
    if manifest.get("high_score_table") != expected_high_score:
        raise SystemExit("presentation proof: high-score table metadata differs")
    if len(payload) > 4 * 0x2000:
        raise SystemExit("presentation proof: cold payload exceeds four pages")
    if not complete_profile and len(payload) > 10874:
        raise SystemExit("presentation proof: cold payload exceeds PERF-004 minimum reduction limit")
    if len(payload) > manifest["cold_payload_limit"]:
        raise SystemExit("presentation proof: cold payload exceeds Plan A source limit")
    print(
        f"presentation proof: {len(maps)} maps, {len(ordered_tiles)} tiles, "
        f"{len(payload)} bytes, hashes and four-page bound valid"
    )


if __name__ == "__main__":
    main()
