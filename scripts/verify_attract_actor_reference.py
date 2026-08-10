#!/usr/bin/env python3
"""Verify the frame-indexed BUG-010 arcade title-actor oracle."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from build_screen import (
    compile_enemy_sprites,
    pack_sprite_2bpp,
    rotate_ccw,
)
from build_sparse_sprites import (
    ENEMY_PAGE_BASE,
    ENEMY_PAGE_COUNT,
    pack_indexed_frames,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REFERENCE = ROOT / "assets" / "arcade" / "attract_actor_reference.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument(
        "--raw-video",
        type=Path,
        help="optional BGRA32 capture produced by capture_mame_gameplay.py",
    )
    return parser.parse_args()


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def flip_horizontal(tile: list[list[int]]) -> list[list[int]]:
    return [list(reversed(row)) for row in tile]


def source_shape(sprites: list[list[list[int]]], code: int, flip: str):
    shape = rotate_ccw(sprites[code])
    if flip == "horizontal":
        shape = flip_horizontal(shape)
    elif flip != "none":
        raise ValueError(f"unsupported source flip {flip!r}")
    return shape


def rgb_frame(
    shape: list[list[int]], palette: list[list[int]], lookup: list[int]
) -> bytes:
    output = bytearray()
    for row in shape:
        for pen in row:
            output.extend((0, 0, 0) if not pen else palette[lookup[pen]])
    return bytes(output)


def sparse_frame(shape: list[list[int]]) -> bytes:
    return pack_sprite_2bpp([[0] + row[:15] for row in shape])


def schedule_phase(frame: int, schedule: dict[str, object]) -> int:
    first = int(schedule["first_frame"])
    initial = int(schedule["initial_hold_frames"])
    if frame < first + initial:
        return int(schedule["initial_phase"])
    phases = [int(value) for value in schedule["repeat_phases"]]
    hold = int(schedule["repeat_hold_frames"])
    return phases[((frame - first - initial) // hold) % len(phases)]


def validate_reference(reference: dict[str, object]) -> tuple[list[bytes], dict[str, int]]:
    provenance = reference["provenance"]
    plan = ROOT / provenance["capture_plan"]
    canonical_plan = plan.read_text(encoding="ascii").replace("\r\n", "\n").encode("ascii")
    if digest(canonical_plan) != provenance["capture_plan_sha256"]:
        raise SystemExit("attract oracle: capture-plan hash mismatch")

    interval = reference["title_interval"]
    first = int(interval["first_complete_frame"])
    last = int(interval["last_complete_frame"])
    if last - first + 1 != int(interval["duration_frames"]):
        raise SystemExit("attract oracle: inclusive title duration mismatch")
    schedule = reference["schedule"]
    if int(schedule["first_frame"]) != first or int(schedule["last_frame"]) != last:
        raise SystemExit("attract oracle: schedule does not cover the title interval")
    if [schedule_phase(frame, schedule) for frame in range(first, first + 22)] != (
        [0] * 6 + [1] * 8 + [2] * 8
    ):
        raise SystemExit("attract oracle: initial phase alignment is invalid")

    sprites = json.loads((ROOT / "assets/arcade/sprites.json").read_text())
    palette = json.loads((ROOT / "assets/arcade/palette.json").read_text())
    lookups = {
        "a": json.loads((ROOT / "assets/arcade/sprite_lookup_a.json").read_text()),
        "b": json.loads((ROOT / "assets/arcade/sprite_lookup_b.json").read_text()),
    }
    existing = compile_enemy_sprites(ROOT / "assets/arcade/sprites.json")
    appended: list[bytes] = []
    appended_indexes: dict[bytes, int] = {}

    transform = reference["coordinate_transform"]
    if transform["coco_x"] != "raw_y + 40" or transform["coco_y"] != "192 - raw_x - 16":
        raise SystemExit("attract oracle: unexpected coordinate transform")

    for actor_name, actor in reference["actors"].items():
        raw_x, raw_y = actor["raw_top_left"]
        coco_x, coco_y = actor["coco_pixel_top_left"]
        expected_x = raw_y + 40
        expected_y = 192 - raw_x - 16
        expected_destination = 0x2000 + expected_y * 160 + expected_x // 2
        if [coco_x, coco_y] != [expected_x, expected_y]:
            raise SystemExit(f"attract oracle: {actor_name} coordinate transform mismatch")
        if actor["presentation_destination"] != f"${expected_destination:04X}":
            raise SystemExit(f"attract oracle: {actor_name} destination mismatch")

        lookup = lookups[actor["palette_lookup"]["table"]][
            int(actor["palette_lookup"]["row"])
        ]
        codes = actor["source_sprite_codes_by_phase"]
        sparse_indexes = actor["sparse_indexes_by_phase"]
        hashes = actor["rgb_sha256_by_phase"]
        for phase, code in enumerate(codes):
            shape = source_shape(sprites, int(code), actor["source_flip"])
            if digest(rgb_frame(shape, palette, lookup)) != hashes[phase]:
                raise SystemExit(
                    f"attract oracle: {actor_name} phase {phase} RGB hash mismatch"
                )
            packed = sparse_frame(shape)
            matches = [index for index, frame in enumerate(existing) if frame == packed]
            target_index = int(sparse_indexes[phase])
            if matches:
                if target_index not in matches:
                    raise SystemExit(
                        f"attract oracle: {actor_name} phase {phase} sparse index mismatch"
                    )
            else:
                if packed not in appended_indexes:
                    appended_indexes[packed] = len(existing) + len(appended)
                    appended.append(packed)
                if target_index != appended_indexes[packed]:
                    raise SystemExit(
                        f"attract oracle: {actor_name} phase {phase} append index mismatch"
                    )

    base_payload, _, base_padding = pack_indexed_frames(
        existing, ENEMY_PAGE_BASE, ENEMY_PAGE_COUNT
    )
    projected_payload, projected_index, projected_padding = pack_indexed_frames(
        existing + appended, ENEMY_PAGE_BASE, ENEMY_PAGE_COUNT
    )
    projection = reference["sparse_projection"]
    measured = {
        "base_frames": len(existing),
        "appended_frames": len(appended),
        "projected_frames": len(existing) + len(appended),
        "base_bytes": len(base_payload),
        "projected_bytes": len(projected_payload),
        "net_bytes": len(projected_payload) - len(base_payload),
        "base_padding_bytes": base_padding,
        "projected_padding_bytes": projected_padding,
        "projected_last_page": projected_index[-1]["page"],
        "projected_end_address": (
            projected_index[-1]["address"] + projected_index[-1]["length"]
        ),
    }
    if any(int(projection[key]) != value for key, value in measured.items()):
        raise SystemExit("attract oracle: sparse capacity projection mismatch")
    return appended, measured


def validate_raw(reference: dict[str, object], raw_path: Path) -> None:
    raw = raw_path.read_bytes()
    provenance = reference["provenance"]
    width = int(provenance["video"]["width"])
    height = int(provenance["video"]["height"])
    frames = int(provenance["captured_frames"])
    stride = width * height * 4
    if len(raw) != frames * stride:
        raise SystemExit("attract oracle: raw-video byte count mismatch")
    if digest(raw) != provenance["raw_video_sha256"]:
        raise SystemExit("attract oracle: raw-video hash mismatch")

    for frame_number, expected in reference["boundary_frame_sha256"].items():
        number = int(frame_number)
        frame = raw[(number - 1) * stride:number * stride]
        if digest(frame) != expected:
            raise SystemExit(f"attract oracle: boundary frame {number} hash mismatch")

    schedule = reference["schedule"]
    first = int(schedule["first_frame"])
    last = int(schedule["last_frame"])
    for actor_name, actor in reference["actors"].items():
        x, y = actor["raw_top_left"]
        expected_hashes = actor["rgb_sha256_by_phase"]
        for frame_number in range(first, last + 1):
            frame = raw[(frame_number - 1) * stride:frame_number * stride]
            crop = bytearray()
            for row in range(y, y + 16):
                offset = (row * width + x) * 4
                for column in range(16):
                    blue, green, red = frame[offset:offset + 3]
                    crop.extend((red, green, blue))
                    offset += 4
            phase = schedule_phase(frame_number, schedule)
            if digest(bytes(crop)) != expected_hashes[phase]:
                raise SystemExit(
                    f"attract oracle: {actor_name} frame {frame_number} mismatch"
                )


def main() -> None:
    args = parse_args()
    reference = json.loads(args.reference.read_text(encoding="ascii"))
    appended, projection = validate_reference(reference)
    if args.raw_video:
        validate_raw(reference, args.raw_video)
    print(
        "attract oracle: 558 title frames, four stationary actors, "
        "6-frame initial phase, 8-frame recurring phases, "
        f"{len(appended)} appended sparse frames, "
        f"{projection['net_bytes']} projected sparse bytes"
    )


if __name__ == "__main__":
    main()
