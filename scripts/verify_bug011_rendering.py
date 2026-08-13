#!/usr/bin/env python3
"""Verify BUG-011 dual-owner hydration, east-facing art, and exact restoration."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from build_screen import compile_player_sprites
import verify_bug011_runtime as runtime


SPRITES = runtime.ROOT / "assets/arcade/sprites.json"
HELPER_MAP = runtime.ROOT / "build/ladybug-instruction-runtime.map"
PEN_MAP = (0x0, 0xC, 0x5, 0x2)
PLAYER_FB = 0x000B
PRES_OUT = 0x00B7


def write_word(client, address: int, value: int) -> None:
    client.call("write_memory", {
        "addr": address, "data": value.to_bytes(2, "big").hex(),
    })


def native_frame(packed: bytes) -> bytes:
    output = bytearray()
    for value in packed:
        pixels = (
            (value >> 6) & 3,
            (value >> 4) & 3,
            (value >> 2) & 3,
            value & 3,
        )
        output.extend((
            (PEN_MAP[pixels[0]] << 4) | PEN_MAP[pixels[1]],
            (PEN_MAP[pixels[2]] << 4) | PEN_MAP[pixels[3]],
        ))
    return bytes(output)


def frame_rect(source: bytes, destination: int) -> bytes:
    offset = destination - runtime.VISIBLE_START
    return b"".join(
        source[offset + row * 160:offset + row * 160 + 8]
        for row in range(16)
    )


def blend_frame(target: bytearray, destination: int, sprite: bytes) -> None:
    offset = destination - runtime.VISIBLE_START
    for row in range(16):
        for column in range(8):
            pixel = sprite[row * 8 + column]
            mask = (0xF0 if not pixel & 0xF0 else 0) | (
                0x0F if not pixel & 0x0F else 0
            )
            index = offset + row * 160 + column
            target[index] = (target[index] & mask) | pixel


def recoloured_surface(source: bytes, colour: int, heart: bool) -> bytes:
    output = bytearray()
    for value in source:
        packed = 0
        for shift in (4, 0):
            pixel = (value >> shift) & 0x0F
            if pixel:
                pixel = colour if not heart or pixel == 4 else pixel
            packed |= pixel << shift
        output.append(packed)
    return bytes(output)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xroar", type=Path, default=Path(
        "/mnt/d/retro/ladybug/docs/reference/xroar/src/xroar"
    ))
    parser.add_argument("--rom", type=Path, default=runtime.ROOT / "build/ladybug.rom")
    parser.add_argument("--output", type=Path,
                        default=runtime.ROOT / "build/bug011-rendering.json")
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()

    monitor = runtime.load_monitor()
    symbols = runtime.symbols(runtime.PRESENTATION_MAP)
    process, client = runtime.launch_fast(monitor, args.xroar, args.rom)
    try:
        ids = monitor.setup(client, [symbols["instructions_tick"]])
        hit = client.run_to_breakpoint(args.timeout)
        monitor.clear(client, ids)
        if hit.get("pc") != symbols["instructions_tick"]:
            raise SystemExit(f"BUG-011 rendering: instruction entry timeout: {hit}")

        helper = runtime.HELPER.read_bytes()
        live_helper = runtime.read_bytes(client, 0x0300, len(helper))
        if live_helper != helper:
            raise SystemExit("BUG-011 rendering: installed helper identity differs")

        manifest = json.loads(runtime.MANIFEST.read_text(encoding="ascii"))
        expected_static = manifest["static_frame_sha256"][1]
        static_frames = {owner: runtime.read_owner(client, owner) for owner in (0, 1)}
        static_hashes = {
            owner: runtime.digest(frame) for owner, frame in static_frames.items()
        }
        if any(value != expected_static for value in static_hashes.values()):
            raise SystemExit(
                "BUG-011 rendering: instruction owners differ at entry: "
                f"{static_hashes} expected={expected_static}"
            )
        choreography = manifest["instruction_choreography"]
        for index, event in enumerate(choreography["events"][:15]):
            destinations = [event["hud_destination"]]
            if event["hud_tile_2_id"]:
                destinations.append(event["hud_destination"] + 4)
            for destination in destinations:
                colours = {
                    nibble for value in runtime.frame_tile(
                        static_frames[0], destination
                    ) for nibble in (value >> 4, value & 15) if nibble
                }
                if colours != {7}:
                    raise SystemExit(
                        "BUG-011 rendering: initial HUD target is highlighted; "
                        f"target={index} destination=${destination:04X} "
                        f"colours={sorted(colours)}"
                    )
        skull = choreography["events"][15]["target_destination"]
        skull_colours = {
            nibble for value in frame_rect(static_frames[0], skull)
            for nibble in (value >> 4, value & 15) if nibble
        }
        if skull_colours != {6}:
            raise SystemExit(
                f"BUG-011 rendering: skull is not white: {sorted(skull_colours)}"
            )
        reward_colours = {}
        for name in ("life", "coin"):
            pixels = b"".join(
                runtime.expected_tile(manifest, tile_id)
                for tile_id in choreography["reward_tile_ids"][name]
            )
            reward_colours[name] = {
                nibble for value in pixels
                for nibble in (value >> 4, value & 15) if nibble
            }
        if reward_colours["life"] != {2, 5, 12}:
            raise SystemExit(
                "BUG-011 rendering: life reward palette differs: "
                f"{sorted(reward_colours['life'])}"
            )
        if reward_colours["coin"] != {6, 7}:
            raise SystemExit(
                "BUG-011 rendering: coin reward palette differs: "
                f"{sorted(reward_colours['coin'])}"
            )

        # Enter the first motion boundary quickly. The resident timer increments
        # before each helper call: 105 -> init at 106, then movement at 107/108.
        write_word(client, runtime.PRES_TIMER, 105)
        helper_symbols = runtime.symbols(HELPER_MAP)
        saved_pc = helper_symbols["player_underlay_saved"]
        saved_ids = monitor.setup(client, [saved_pc])
        saved_hit = client.run_to_breakpoint(args.timeout)
        monitor.clear(client, saved_ids)
        if saved_hit.get("pc") != saved_pc:
            raise SystemExit(f"BUG-011 rendering: underlay capture timeout: {saved_hit}")

        first_owner = runtime.read_byte(client, runtime.FB_BACK)
        first_destination = runtime.read_word(client, PRES_OUT)
        if first_destination != choreography["anchors"][0]:
            raise SystemExit(
                "BUG-011 rendering: actor is not on the authored first row; "
                f"actual=${first_destination:04X} "
                f"expected=${choreography['anchors'][0]:04X}"
            )
        initial_frame = runtime.read_owner(client, first_owner)
        for index, event in enumerate(choreography["events"][:15]):
            original = frame_rect(
                static_frames[first_owner], event["target_destination"]
            )
            expected = recoloured_surface(original, 1, index >= 12)
            actual = frame_rect(initial_frame, event["target_destination"])
            if actual != expected:
                differences = [
                    (offset, actual[offset], expected[offset], original[offset])
                    for offset in range(len(actual))
                    if actual[offset] != expected[offset]
                ][:8]
                raise SystemExit(
                    "BUG-011 rendering: complete collectible colour surface differs; "
                    f"target={index} actual={runtime.digest(actual)} "
                    f"expected={runtime.digest(expected)} differences={differences}"
                )
        save_under_address = 0xA300 if first_owner == 0 else 0xAB00
        saved_underlay = runtime.read_bytes(client, save_under_address, 128)
        expected_underlay = frame_rect(static_frames[first_owner], first_destination)
        if saved_underlay != expected_underlay:
            raise SystemExit(
                "BUG-011 rendering: selected owner did not capture clean underlay; "
                f"owner={first_owner} par5=${runtime.read_byte(client, runtime.PAR5):02X} "
                f"fb_init={runtime.read_byte(client, 0x009A)} "
                f"bg_ptr=${runtime.read_word(client, 0x00A2):04X} "
                f"live={runtime.digest(saved_underlay)} "
                f"expected={runtime.digest(expected_underlay)} "
                f"live16={saved_underlay[:16].hex()} "
                f"expected16={expected_underlay[:16].hex()}"
            )

        return_pc = symbols["instructions_runtime_return"]
        return_ids = monitor.setup(client, [return_pc])
        first = client.run_to_breakpoint(args.timeout)
        if first.get("pc") != return_pc:
            raise SystemExit(f"BUG-011 rendering: init return timeout: {first}")

        first_frame_index = runtime.read_byte(client, runtime.PRES_ACTOR_FRAME)
        if not 4 <= first_frame_index <= 7:
            raise SystemExit(
                f"BUG-011 rendering: player frame {first_frame_index} is not east-facing"
            )
        if runtime.read_word(client, PLAYER_FB) != first_destination:
            raise SystemExit("BUG-011 rendering: player save-under address differs")
        metadata = 0xA900 if first_owner == 0 else 0xAA00
        metadata_valid = runtime.read_byte(client, metadata + 2)
        metadata_destination = runtime.read_word(client, metadata + 4)
        if metadata_valid != 1 or metadata_destination != first_destination:
            raise SystemExit(
                "BUG-011 rendering: owner metadata did not retain player underlay; "
                f"owner={first_owner} valid={metadata_valid} "
                f"destination=${metadata_destination:04X}"
            )
        retained_after_draw = runtime.read_bytes(client, save_under_address, 128)
        if retained_after_draw != saved_underlay:
            raise SystemExit(
                "BUG-011 rendering: player draw or metadata capture altered underlay; "
                f"before={runtime.digest(saved_underlay)} "
                f"after={runtime.digest(retained_after_draw)}"
            )

        east_frames = [native_frame(frame) for frame in compile_player_sprites(SPRITES)]

        movement_hits = []
        for _ in range(8):
            movement_hit = client.run_to_breakpoint(args.timeout)
            if movement_hit.get("pc") != return_pc:
                raise SystemExit(
                    f"BUG-011 rendering: movement return timeout: {movement_hit}"
                )
            owner = runtime.read_byte(client, runtime.FB_BACK)
            destination = runtime.read_word(client, PRES_OUT)
            movement_hits.append((owner, destination))
            if owner == first_owner and destination > first_destination:
                break
        else:
            raise SystemExit(
                "BUG-011 rendering: same owner did not receive a moved frame; "
                f"hits={movement_hits}"
            )
        monitor.clear(client, return_ids)
        if runtime.read_byte(client, runtime.FB_BACK) != first_owner:
            raise SystemExit("BUG-011 rendering: selected movement owner changed")

        moved_destination = runtime.read_word(client, PRES_OUT)
        moved_frame_index = runtime.read_byte(client, runtime.PRES_ACTOR_FRAME)
        movement_bytes = moved_destination - first_destination
        if not 1 <= movement_bytes <= 8:
            raise SystemExit(
                "BUG-011 rendering: controlled movement destination differs: "
                f"${first_destination:04X} -> ${moved_destination:04X}"
            )
        if runtime.read_word(client, PLAYER_FB) != moved_destination:
            raise SystemExit("BUG-011 rendering: moved save-under address differs")

        moved_frame = runtime.read_owner(client, first_owner)
        expected_moved = bytearray(static_frames[first_owner])
        blend_frame(expected_moved, moved_destination, east_frames[moved_frame_index])
        first_offset = first_destination - runtime.VISIBLE_START
        union = [
            first_offset + row * 160 + column
            for row in range(16) for column in range(8 + movement_bytes)
        ]
        differences = [
            index for index in union
            if moved_frame[index] != expected_moved[index]
        ]
        if differences:
            raise SystemExit(
                "BUG-011 rendering: prior footprint was not restored exactly; "
                f"owner={first_owner} first=${first_destination:04X} moved=${moved_destination:04X} "
                f"frame={moved_frame_index} hits={movement_hits} differences={differences[:16]} "
                f"count={len(differences)} "
                f"samples={[(index, moved_frame[index], expected_moved[index], static_frames[first_owner][index]) for index in differences[:8]]} "
                f"actual={runtime.digest(moved_frame)} "
                f"expected={runtime.digest(bytes(expected_moved))}"
            )

        evidence = {
            "schema": "ladybug-bug011-rendering-v1",
            "rom_sha256": runtime.digest(args.rom.read_bytes()),
            "helper_sha256": runtime.digest(helper),
            "phase": "instruction entry and first same-owner movement",
            "success_markers": [
                f"instructions_tick=${symbols['instructions_tick']:04X}",
                f"instructions_runtime_return=${return_pc:04X}",
            ],
            "deadline_seconds_per_marker": args.timeout,
            "timeout_meaning": "natural entry or controlled helper return was not reached",
            "initial_owner_sha256": static_hashes,
            "expected_static_sha256": expected_static,
            "owner": first_owner,
            "first_destination": first_destination,
            "moved_destination": moved_destination,
            "first_frame": first_frame_index,
            "moved_frame": moved_frame_index,
            "movement_hits": movement_hits,
            "initial_save_under_sha256": runtime.digest(saved_underlay),
            "complete_colour_surfaces": 15,
            "moved_frame_sha256": runtime.digest(moved_frame),
            "exact_restoration": True,
        }
        args.output.write_text(
            json.dumps(evidence, indent=2) + "\n", encoding="ascii"
        )
        print(
            "BUG-011 rendering: both instruction owners hydrated, east-facing "
            "player pixels matched, and the first same-owner movement restored "
            "the prior footprint exactly"
        )
    finally:
        client.close()
        runtime.stop(process)
        process.wait(timeout=2)


if __name__ == "__main__":
    main()
