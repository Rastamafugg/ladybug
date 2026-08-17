#!/usr/bin/env python3
"""Verify BUG-018 enemy palettes against source pens and sparse commands."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGE_BYTES = 0x2000
WINDOW_BASE = 0xA000
PAGE_BASE = 0x35
LEGACY_MAP = (0, 12, 5, 2)
PART_ONE_MAP = (0, 9, 5, 6)
EXPECTED_PAYLOAD_SHA256 = "688af5ca9c98802096aa50cf47ef65b78077205f7d77a4d70415bbfb4d51029d"
EXPECTED_BYTES = 23_005
EXPECTED_PADDING = 290
BASELINE_REVISION = "7a04de6c2f3093ee1d3e2c1105a2bf1f12108e43"
BASELINE_INDEX_SHA256 = "c3c4aeb7eac8d150b204db43cbd7c3fd093dd077f687935aac52b8be467e1d9d"
BASELINE_COMMAND_LAYOUT_SHA256 = "a9987cf7d0cdd84905b8d7d8534b0063987b9fb1e781ad3c279505fd47ef6f02"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sheet_code(row: int, column: int) -> int:
    return column * 8 + (7 - row)


ENEMY_CODE_SETS = (
    tuple(sheet_code(row, 1) for row in (4, 5, 6, 5)),
    (sheet_code(6, 2), sheet_code(7, 2), sheet_code(0, 1), sheet_code(7, 2)),
    tuple(sheet_code(row, 3) for row in (2, 3, 4, 3)),
    tuple(sheet_code(row, 2) for row in (0, 1, 2, 1)),
    tuple(sheet_code(row, 4) for row in (4, 5, 6, 5)),
    (sheet_code(6, 5), sheet_code(7, 5), sheet_code(0, 4), sheet_code(7, 5)),
    tuple(sheet_code(row, 5) for row in (0, 1, 2, 1)),
    tuple(sheet_code(row, 6) for row in (2, 3, 4, 3)),
)


def rotate_ccw(tile: list[list[int]]) -> list[list[int]]:
    size = len(tile)
    return [[tile[x][size - 1 - y] for x in range(size)] for y in range(size)]


def rotate_cw(tile: list[list[int]]) -> list[list[int]]:
    size = len(tile)
    return [[tile[size - 1 - x][y] for x in range(size)] for y in range(size)]


def source_frames(path: Path) -> list[list[list[int]]]:
    sprites = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(sprites, list) or len(sprites) != 128:
        raise ValueError("sprite source must contain 128 frames")
    frames: list[list[list[int]]] = []
    for codes in ENEMY_CODE_SETS:
        direction = [rotate_ccw(sprites[code]) for code in codes]
        for _ in range(4):
            frames.extend([[[0] + row[:15] for row in frame] for frame in direction])
            direction = [rotate_cw(frame) for frame in direction]
    for code in (6, 7):
        frame = rotate_ccw(sprites[code])
        frame = [list(reversed(row)) for row in frame]
        frames.append([[0] + row[:15] for row in frame])
    return frames


def decode_frame(payload: bytes, frame_number: int) -> dict[str, object]:
    entry = payload[frame_number * 3:frame_number * 3 + 3]
    page = entry[0]
    address = (entry[1] << 8) | entry[2]
    offset = (page - PAGE_BASE) * PAGE_BYTES + address - WINDOW_BASE
    if offset < 390 or offset >= len(payload):
        raise ValueError(f"frame {frame_number} index is outside the payload")
    cursor = offset
    framebuffer_cursor = 0
    stage_cursor = 0
    pixels = [0] * 256
    written = [False] * 256
    layout: list[list[int]] = []
    while True:
        token = payload[cursor]
        cursor += 1
        if token == 0xFF:
            framebuffer_delta = (payload[cursor] << 8) | payload[cursor + 1]
            cursor += 2
            if framebuffer_delta == 0:
                break
            stage_delta = payload[cursor]
            cursor += 1
            extended = 1
        else:
            framebuffer_delta = token
            stage_delta = token if token < 0x80 else token - 152
            extended = 0
        framebuffer_cursor += framebuffer_delta
        stage_cursor += stage_delta
        row, byte_column = divmod(stage_cursor, 8)
        if framebuffer_cursor != row * 160 + byte_column or row >= 16:
            raise ValueError(f"frame {frame_number} destination streams diverge")
        control = payload[cursor]
        cursor += 1
        partial = bool(control & 0x80)
        count = control & 0x7F
        command_masks: list[int] = []
        for byte_index in range(count):
            pixel_base = row * 16 + (byte_column + byte_index) * 2
            if partial:
                mask, value = payload[cursor:cursor + 2]
                cursor += 2
                command_masks.append(mask)
                if mask == 0xF0:
                    pixels[pixel_base + 1] = value & 0x0F
                    written[pixel_base + 1] = True
                elif mask == 0x0F:
                    pixels[pixel_base] = value >> 4
                    written[pixel_base] = True
                else:
                    raise ValueError(f"frame {frame_number} invalid partial mask")
            else:
                value = payload[cursor]
                cursor += 1
                pixels[pixel_base] = value >> 4
                pixels[pixel_base + 1] = value & 0x0F
                written[pixel_base] = True
                written[pixel_base + 1] = True
        layout.append([
            extended, framebuffer_delta, stage_delta, int(partial), count,
            *command_masks,
        ])
        framebuffer_cursor += count
        stage_cursor += count
    return {
        "page": page,
        "address": address,
        "offset": offset,
        "end": cursor,
        "pixels": pixels,
        "written": written,
        "layout": layout,
    }


def expected_pixels(frame: list[list[int]], pen_map: tuple[int, int, int, int]) -> list[int]:
    return [pen_map[pixel] for row in frame for pixel in row]


def verify_oracle(
        decoded: list[dict[str, object]], frames: list[list[list[int]]],
        maps: list[tuple[int, int, int, int]]
) -> None:
    if len(decoded) != len(frames) or len(frames) != len(maps):
        raise ValueError("oracle frame/map cardinality differs")
    for frame_number, (actual, frame, pen_map) in enumerate(zip(decoded, frames, maps)):
        expected = expected_pixels(frame, pen_map)
        if actual["pixels"] != expected:
            mismatch = next(
                index for index, pair in enumerate(zip(actual["pixels"], expected))
                if pair[0] != pair[1]
            )
            y, x = divmod(mismatch, 16)
            raise ValueError(
                f"frame {frame_number} pixel ({x},{y}) is "
                f"{actual['pixels'][mismatch]}, expected {expected[mismatch]}"
            )
        expected_mask = [pixel != 0 for row in frame for pixel in row]
        if actual["written"] != expected_mask:
            raise ValueError(f"frame {frame_number} transparency/shape mask differs")


def require_rejection(
        name: str, decoded: list[dict[str, object]], frames: list[list[list[int]]],
        maps: list[tuple[int, int, int, int]]
) -> dict[str, object]:
    try:
        verify_oracle(decoded, frames, maps)
    except ValueError as error:
        return {"mutation": name, "rejected": True, "diagnostic": str(error)}
    raise RuntimeError(f"mutation {name} was not rejected")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--sprites", type=Path, default=ROOT / "assets/arcade/sprites.json")
    parser.add_argument("--payload", type=Path, default=ROOT / "build/ladybug-enemy-sparse.bin")
    parser.add_argument("--output", type=Path, default=ROOT / "build/bug018-static-oracle.json")
    parser.add_argument("--self-test-mutations", action="store_true")
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="ascii"))
    payload = args.payload.read_bytes()
    frames = source_frames(args.sprites)
    maps = [PART_ONE_MAP] * 16 + [LEGACY_MAP] * 114
    decoded = [decode_frame(payload, frame) for frame in range(130)]
    verify_oracle(decoded, frames, maps)

    if len(payload) != EXPECTED_BYTES or manifest["enemy"]["padding_bytes"] != EXPECTED_PADDING:
        raise SystemExit("BUG-018 oracle: payload capacity differs")
    if digest(payload) != EXPECTED_PAYLOAD_SHA256:
        raise SystemExit("BUG-018 oracle: payload hash differs from approved projection")
    if manifest["enemy"]["sha256"] != digest(payload):
        raise SystemExit("BUG-018 oracle: manifest payload hash differs")

    index_bytes = payload[:390]
    layout_bytes = json.dumps(
        [item["layout"] for item in decoded], separators=(",", ":")
    ).encode("ascii")
    index_sha256 = digest(index_bytes)
    command_layout_sha256 = digest(layout_bytes)
    if index_sha256 != BASELINE_INDEX_SHA256:
        raise SystemExit("BUG-018 oracle: index addresses differ from assignment baseline")
    if command_layout_sha256 != BASELINE_COMMAND_LAYOUT_SHA256:
        raise SystemExit("BUG-018 oracle: sparse command layout differs from assignment baseline")
    mutations: list[dict[str, object]] = []
    if args.self_test_mutations:
        old_phase = maps[:]
        old_phase[3] = LEGACY_MAP
        mutations.append(require_rejection("one-phase-old-map", decoded, frames, old_phase))
        swapped = maps[:]
        swapped[:16] = [(0, 6, 5, 9)] * 16
        mutations.append(require_rejection("part-one-pen-9-6-swap", decoded, frames, swapped))
        omitted_rotation = [[row[:] for row in frame] for frame in frames]
        omitted_rotation[4] = [row[:] for row in frames[0]]
        mutations.append(require_rejection("omitted-east-rotation", decoded, omitted_rotation, maps))
        later_recolour = maps[:]
        later_recolour[16] = PART_ONE_MAP
        mutations.append(require_rejection("later-family-recolour", decoded, frames, later_recolour))

    evidence = {
        "schema": "ladybug-bug018-static-palette-oracle-v1",
        "payload_sha256": digest(payload),
        "payload_bytes": len(payload),
        "padding_bytes": manifest["enemy"]["padding_bytes"],
        "baseline_revision": BASELINE_REVISION,
        "baseline_index_sha256": BASELINE_INDEX_SHA256,
        "current_index_sha256": index_sha256,
        "baseline_command_layout_sha256": BASELINE_COMMAND_LAYOUT_SHA256,
        "current_command_layout_sha256": command_layout_sha256,
        "part_one": {"frames": 16, "pen_map": list(PART_ONE_MAP), "pass": True},
        "later_gameplay": {"frames": 112, "pen_map": list(LEGACY_MAP), "pass": True},
        "attract_extra": {"frames": 2, "pen_map": list(LEGACY_MAP), "pass": True},
        "family_streams": manifest["enemy"]["palette_families"],
        "shape_and_transparency_masks_unchanged": True,
        "mutations": mutations,
        "pass": True,
    }
    args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="ascii")
    print(
        "BUG-018 oracle pass: 16 part-one, 112 later gameplay, and 2 appended "
        f"frames pixel-exact; {len(mutations)} mutations rejected"
    )


if __name__ == "__main__":
    main()
