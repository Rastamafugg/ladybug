#!/usr/bin/env python3
"""Capture Lady Bug background RAM from MAME and derive the rotated maze grid."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import tempfile


RAM_START = 0xD000
RAM_SIZE = 0x0800
CODE_SIZE = 0x0400
RAW_WIDTH = 32
RAW_HEIGHT = 32
VISIBLE_RAW_X = range(1, 31)
VISIBLE_RAW_Y = range(4, 28)
VISIBLE_WIDTH = 24
VISIBLE_HEIGHT = 30
COCO_FIRST_ROW = 3
COCO_ROW_COUNT = 24


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mame", default="mame", help="MAME executable")
    parser.add_argument("--driver", default="ladybug", help="MAME driver")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("assets/arcade/maze_capture.json"),
        help="derived JSON output",
    )
    parser.add_argument(
        "--raw-output",
        type=Path,
        default=Path("assets/arcade/maze_capture.bin"),
        help="selected raw $D000-$D7FF dump",
    )
    parser.add_argument("--start-frame", type=int, default=2400)
    parser.add_argument("--end-frame", type=int, default=2700)
    parser.add_argument("--minimum-stable-frames", type=int, default=10)
    return parser.parse_args()


def lua_script(output_dir: Path, first_frame: int, last_frame: int) -> str:
    output = output_dir.as_posix()
    return f'''local frame = 0

local function dump_background(tag)
    local space = manager:machine().devices[":maincpu"].spaces["program"]
    local file = assert(io.open("{output}/bg_" .. tag .. ".bin", "wb"))
    local bytes = {{}}
    for address = 0xd000, 0xd7ff do
        bytes[#bytes + 1] = string.char(space:read_u8(address))
    end
    file:write(table.concat(bytes))
    file:close()
end

emu.register_frame_done(function()
    frame = frame + 1
    if frame >= {first_frame} and frame <= {last_frame} then
        dump_background(string.format("%04d", frame))
    end
end)
'''


def capture_frames(args: argparse.Namespace, directory: Path) -> dict[int, bytes]:
    script = directory / "capture.lua"
    with script.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(lua_script(directory, args.start_frame, args.end_frame))

    seconds = math.ceil(args.end_frame / 60) + 1
    command = [
        args.mame,
        args.driver,
        "-skip_gameinfo",
        "-nothrottle",
        "-sound",
        "none",
        "-video",
        "none",
        "-seconds_to_run",
        str(seconds),
        "-autoboot_delay",
        "0",
        "-autoboot_script",
        str(script),
    ]
    subprocess.run(command, check=True)

    frames: dict[int, bytes] = {}
    for path in sorted(directory.glob("bg_*.bin")):
        data = path.read_bytes()
        if len(data) != RAM_SIZE:
            raise ValueError(f"{path}: expected {RAM_SIZE} bytes, got {len(data)}")
        frames[int(path.stem.split("_")[1])] = data
    if not frames:
        raise RuntimeError("MAME produced no background-RAM samples")
    return frames


def tile_code(data: bytes, offset: int) -> int:
    return data[offset] | (((data[CODE_SIZE + offset] >> 3) & 1) << 8)


def looks_like_complete_maze(data: bytes) -> bool:
    codes = {tile_code(data, offset) for offset in range(CODE_SIZE)}
    attributes = data[CODE_SIZE:]
    return len(codes) >= 70 and sum(value != 0 for value in attributes) >= 350


def select_stable_maze(
    frames: dict[int, bytes], minimum_stable_frames: int
) -> tuple[int, int, bytes]:
    ordered = sorted(frames.items())
    index = 0
    while index < len(ordered):
        first_frame, data = ordered[index]
        last_index = index
        while (
            last_index + 1 < len(ordered)
            and ordered[last_index + 1][0] == ordered[last_index][0] + 1
            and ordered[last_index + 1][1] == data
        ):
            last_index += 1
        stable_count = last_index - index + 1
        if stable_count >= minimum_stable_frames and looks_like_complete_maze(data):
            return first_frame, ordered[last_index][0], data
        index = last_index + 1
    raise RuntimeError(
        "no complete maze state met the stability threshold; expand the frame range"
    )


def rotate_visible(data: bytes) -> tuple[list[list[int]], list[list[int]]]:
    """Apply MAME ROT270 to raw tile rows 4..27 and columns 1..30."""
    codes: list[list[int]] = []
    attributes: list[list[int]] = []
    for output_y in range(VISIBLE_HEIGHT):
        code_row: list[int] = []
        attribute_row: list[int] = []
        raw_x = 30 - output_y
        for output_x in range(VISIBLE_WIDTH):
            raw_y = 4 + output_x
            offset = raw_y * RAW_WIDTH + raw_x
            code_row.append(tile_code(data, offset))
            attribute_row.append(data[CODE_SIZE + offset])
        codes.append(code_row)
        attributes.append(attribute_row)
    return codes, attributes


def rotated_sheet_index(code: int) -> int:
    """Map a ROM code to the whole-sheet counter-clockwise-rotated PNG index."""
    return (31 - (code % 32)) * 16 + (code // 32)


def write_outputs(
    args: argparse.Namespace,
    version: str,
    first_frame: int,
    last_frame: int,
    data: bytes,
) -> None:
    visible_codes, visible_attributes = rotate_visible(data)
    sheet_indices = [
        [rotated_sheet_index(code) for code in row] for row in visible_codes
    ]
    coco_rows = slice(COCO_FIRST_ROW, COCO_FIRST_ROW + COCO_ROW_COUNT)
    sha256 = hashlib.sha256(data).hexdigest()

    document = {
        "schema": "ladybug-mame-background-capture-v1",
        "provenance": {
            "driver": args.driver,
            "mame_version": version,
            "sample_range": [args.start_frame, args.end_frame],
            "selected_stable_frames": [first_frame, last_frame],
            "raw_memory": {"start": RAM_START, "size": RAM_SIZE},
            "raw_sha256": sha256,
        },
        "mapping": {
            "raw_tilemap": [RAW_WIDTH, RAW_HEIGHT],
            "raw_visible_columns_inclusive": [VISIBLE_RAW_X.start, VISIBLE_RAW_X.stop - 1],
            "raw_visible_rows_inclusive": [VISIBLE_RAW_Y.start, VISIBLE_RAW_Y.stop - 1],
            "mame_rotation": 270,
            "rotated_visible_grid": [VISIBLE_WIDTH, VISIBLE_HEIGHT],
            "coco_maze_rows_inclusive": [
                COCO_FIRST_ROW,
                COCO_FIRST_ROW + COCO_ROW_COUNT - 1,
            ],
            "coco_maze_grid": [VISIBLE_WIDTH, COCO_ROW_COUNT],
            "whole_sheet_counterclockwise_rotation": {
                "source_grid": [32, 16],
                "rotated_grid": [16, 32],
            },
        },
        "visible_codes": visible_codes,
        "visible_attributes": visible_attributes,
        "visible_ccw_sheet_indices": sheet_indices,
        "coco_maze_codes": visible_codes[coco_rows],
        "coco_maze_attributes": visible_attributes[coco_rows],
        "coco_maze_ccw_sheet_indices": sheet_indices[coco_rows],
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.raw_output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(document, handle, indent=2)
        handle.write("\n")
    args.raw_output.write_bytes(data)
    print(
        f"capture: frames {first_frame}-{last_frame}, sha256 {sha256}\n"
        f"capture: wrote {args.raw_output} and {args.output}"
    )


def main() -> None:
    args = parse_args()
    version = subprocess.check_output([args.mame, "-version"], text=True).strip()
    with tempfile.TemporaryDirectory(prefix="ladybug-mame-") as temporary:
        frames = capture_frames(args, Path(temporary))
    first_frame, last_frame, data = select_stable_maze(
        frames, args.minimum_stable_frames
    )
    write_outputs(args, version, first_frame, last_frame, data)


if __name__ == "__main__":
    main()
