#!/usr/bin/env python3
"""Capture frame-indexed Lady Bug sprite, input, and background activity from MAME."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import shutil
import subprocess
import tempfile


CONTROL_SPECS = {
    # MAME 0.220 ioport_field::set_value takes a logical digital state,
    # independent of the field's active-high/active-low electrical polarity.
    "coin1": (":COIN", 0x01, 1, 0),
    "start1": (":IN0", 0x20, 1, 0),
    "left": (":CONTP1", 0x01, 1, 0),
    "down": (":CONTP1", 0x02, 1, 0),
    "right": (":CONTP1", 0x04, 1, 0),
    "up": (":CONTP1", 0x08, 1, 0),
}

DEFAULT_PLAN = {
    "actions": [
        {"frame": 60, "control": "coin1", "pressed": True},
        {"frame": 63, "control": "coin1", "pressed": False},
        {"frame": 90, "control": "start1", "pressed": True},
        {"frame": 95, "control": "start1", "pressed": False},
    ]
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mame", default="mame")
    parser.add_argument("--driver", default="ladybug")
    parser.add_argument("--frames", type=int, default=900)
    parser.add_argument("--recognize-from", type=int, default=1)
    parser.add_argument("--skip-player-recognition", action="store_true",
                        help="retain captures without the expensive full-frame player scan")
    parser.add_argument("--video-from", type=int, default=1,
                        help="first frame written to the optional raw-video stream")
    parser.add_argument("--plan", type=Path)
    parser.add_argument(
        "--output", type=Path, default=Path("assets/arcade/gameplay_reference.json")
    )
    parser.add_argument("--raw-video", type=Path,
                        help="optionally retain the BGRA32 frame stream")
    parser.add_argument("--raw-work-ram", type=Path,
                        help="optionally retain the $6000-$6fff frame stream")
    return parser.parse_args()


def load_plan(path: Path | None) -> dict[str, object]:
    plan = DEFAULT_PLAN if path is None else json.loads(path.read_text(encoding="utf-8"))
    actions = plan.get("actions")
    if not isinstance(actions, list):
        raise ValueError("input plan must contain an actions list")
    for action in actions:
        if not isinstance(action, dict):
            raise ValueError("every input action must be an object")
        if action.get("control") not in CONTROL_SPECS:
            raise ValueError(f"unknown control {action.get('control')!r}")
        if type(action.get("frame")) is not int or type(action.get("pressed")) is not bool:
            raise ValueError("actions require integer frame and boolean pressed")
    return plan


def lua_table(plan: dict[str, object]) -> str:
    lines = ["local actions = {"]
    for action in plan["actions"]:  # type: ignore[index]
        tag, mask, pressed, released = CONTROL_SPECS[action["control"]]  # type: ignore[index]
        value = pressed if action["pressed"] else released  # type: ignore[index]
        lines.append(
            f'  {{{action["frame"]}, "{tag}", 0x{mask:02x}, 0x{value:02x}, '
            f'"{action["control"]}", {str(action["pressed"]).lower()}}},'
        )
    lines.append("}")
    return "\n".join(lines)


def lua_script(output: Path, video_output: Path, background_output: Path,
               work_ram_output: Path,
               plan: dict[str, object], last_frame: int, video_from: int) -> str:
    return f'''local frame = 0
local finished = false
local space = nil
local ioports = nil
local video = nil
local out = assert(io.open("{output.as_posix()}", "w"))
local vout = assert(io.open("{video_output.as_posix()}", "wb"))
local bout = assert(io.open("{background_output.as_posix()}", "wb"))
local rout = assert(io.open("{work_ram_output.as_posix()}", "wb"))

{lua_table(plan)}

local function find_field(tag, mask)
    local port = assert(ioports[tag], "missing input port " .. tag)
    for name, field in pairs(port.fields) do
        if field.mask == mask then return field, name end
    end
    error(string.format("missing field %s mask %02x", tag, mask))
end

local function initialize()
    local machine = manager:machine()
    space = machine.devices[":maincpu"].spaces["program"]
    ioports = machine:ioport().ports
    video = machine:video()
    for _, action in ipairs(actions) do
        action.field, action.field_name = find_field(action[2], action[3])
    end
    local width, height = video:size()
    out:write(string.format("M\\t%d\\t%d\\n", width, height))
end

local function apply_actions()
    for _, action in ipairs(actions) do
        if action[1] == frame then
            action.field:set_value(action[4])
            out:write(string.format("I\\t%d\\t%s\\t%s\\t%s\\n",
                frame, action[5], tostring(action[6]), action.field_name))
        end
    end
end

local function dump_frame()
    if frame >= {video_from} then vout:write(video:pixels()) end
    local bytes = {{}}
    for address = 0xd000, 0xd7ff do
        bytes[#bytes + 1] = string.char(space:read_u8(address))
    end
    bout:write(table.concat(bytes))
    bytes = {{}}
    for address = 0x6000, 0x6fff do
        bytes[#bytes + 1] = string.char(space:read_u8(address))
    end
    rout:write(table.concat(bytes))
end

emu.register_frame_done(function()
    if finished then return end
    if frame == 0 then initialize() end
    frame = frame + 1
    apply_actions()
    dump_frame()
    out:flush()
    if frame >= {last_frame} then
        out:close(); vout:close(); bout:close(); rout:close(); finished = true
    end
end)
'''


def parse_log(path: Path) -> tuple[int, int, list[dict[str, object]]]:
    width = height = 0
    inputs: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        fields = line.split("\t")
        if fields[0] == "M":
            width, height = int(fields[1]), int(fields[2])
        elif fields[0] == "I":
            inputs.append(
                {
                    "frame": int(fields[1]),
                    "control": fields[2],
                    "pressed": fields[3] == "true",
                    "field": fields[4],
                }
            )
    if not width or not height:
        raise RuntimeError("MAME capture did not report video dimensions")
    return width, height, inputs


def rotate_ccw(tile: list[list[int]]) -> list[list[int]]:
    size = len(tile)
    return [[tile[x][size - 1 - y] for x in range(size)] for y in range(size)]


def rotate_cw(tile: list[list[int]]) -> list[list[int]]:
    size = len(tile)
    return [[tile[size - 1 - x][y] for x in range(size)] for y in range(size)]


def player_templates() -> list[tuple[int, int, list[tuple[int, int, tuple[int, int, int]]]]]:
    root = Path(__file__).resolve().parents[1]
    sprites = json.loads((root / "assets/arcade/sprites.json").read_text(encoding="utf-8"))
    palette = json.loads((root / "assets/arcade/palette.json").read_text(encoding="utf-8"))
    lookup = json.loads((root / "assets/arcade/sprite_lookup_a.json").read_text(encoding="utf-8"))[0]
    templates = []
    for code, sprite in enumerate(sprites[:3]):
        pixels = rotate_ccw(sprite)
        for direction in range(4):
            templates.append(
                (code, direction, [
                    (x, y, tuple(palette[lookup[int(pen)]]))
                    for y, row in enumerate(pixels)
                    for x, pen in enumerate(row)
                    if int(pen)
                ])
            )
            pixels = rotate_cw(pixels)
    return templates


def locate_player_frames(raw: bytes, width: int, height: int, frames: int,
                         recognize_from: int):
    stride = width * height * 4
    if len(raw) != stride * frames:
        raise RuntimeError(f"video capture has {len(raw)} bytes; expected {stride * frames}")
    templates = player_templates()
    positions: dict[str, list[dict[str, int]]] = {}
    for frame_number in range(max(1, recognize_from), frames + 1):
        frame = raw[(frame_number - 1) * stride:frame_number * stride]
        matches: list[tuple[int, int, int]] = []
        for code, direction, template in templates:
            # A red body pixel is a selective anchor.  Comparing it before the
            # rest of the opaque sprite avoids millions of tuple allocations.
            anchor = next((point for point in template if point[2] == (255, 0, 0)),
                          template[0])
            adx, ady, acolor = anchor
            expected_anchor = bytes((acolor[2], acolor[1], acolor[0]))
            for y in range(height - 15):
                for x in range(width - 15):
                    offset = ((y + ady) * width + x + adx) * 4
                    if frame[offset:offset + 3] != expected_anchor:
                        continue
                    matched = True
                    for dx, dy, color in template:
                        offset = ((y + dy) * width + x + dx) * 4
                        if (frame[offset] != color[2] or
                                frame[offset + 1] != color[1] or
                                frame[offset + 2] != color[0]):
                            matched = False
                            break
                    if matched:
                        matches.append((x, y, code, direction))
        if matches:
            positions[str(frame_number)] = [
                {"x": x, "y": y, "code": code, "direction": direction}
                for x, y, code, direction in sorted(set(matches))
            ]
    return positions


def background_changes(raw: bytes, frames: int) -> dict[str, list[list[int]]]:
    stride = 0x800
    if len(raw) != stride * frames:
        raise RuntimeError("background capture size mismatch")
    changes: dict[str, list[list[int]]] = {}
    previous = raw[:stride]
    for frame in range(2, frames + 1):
        current = raw[(frame - 1) * stride:frame * stride]
        delta = [[0xD000 + offset, value] for offset, value in enumerate(current)
                 if value != previous[offset]]
        if delta:
            changes[str(frame)] = delta
        previous = current
    return changes


def memory_changes(raw: bytes, frames: int, base: int) -> dict[str, list[list[int]]]:
    """Return frame-indexed byte changes for a fixed-size memory capture."""
    stride = len(raw) // frames
    if stride * frames != len(raw):
        raise RuntimeError("memory capture size mismatch")
    changes: dict[str, list[list[int]]] = {}
    previous = raw[:stride]
    for frame in range(2, frames + 1):
        current = raw[(frame - 1) * stride:frame * stride]
        delta = [[base + offset, value] for offset, value in enumerate(current)
                 if value != previous[offset]]
        if delta:
            changes[str(frame)] = delta
        previous = current
    return changes


def main() -> None:
    args = parse_args()
    plan = load_plan(args.plan)
    version = subprocess.check_output([args.mame, "-version"], text=True).strip()
    with tempfile.TemporaryDirectory(prefix="ladybug-gameplay-") as temporary:
        directory = Path(temporary)
        raw = directory / "capture.tsv"
        video_raw = directory / "video.bin"
        background_raw = directory / "background.bin"
        work_ram_raw = directory / "work-ram.bin"
        script = directory / "capture.lua"
        with script.open("w", encoding="utf-8", newline="\n") as handle:
            handle.write(lua_script(
                raw, video_raw, background_raw, work_ram_raw, plan, args.frames,
                args.video_from
            ))
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
            str(math.ceil(args.frames / 60) + 1),
            "-autoboot_delay",
            "0",
            "-autoboot_script",
            str(script),
        ]
        subprocess.run(command, check=True)
        width, height, inputs = parse_log(raw)
        video_frames = args.frames - args.video_from + 1
        positions = {} if args.skip_player_recognition else locate_player_frames(
            video_raw.read_bytes(), width, height, video_frames,
            max(1, args.recognize_from - args.video_from + 1)
        )
        if args.video_from != 1:
            positions = {str(int(frame) + args.video_from - 1): matches
                         for frame, matches in positions.items()}
        changes = background_changes(background_raw.read_bytes(), args.frames)
        work_ram_changes = memory_changes(work_ram_raw.read_bytes(), args.frames, 0x6000)
        if args.raw_video:
            args.raw_video.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(video_raw, args.raw_video)
        if args.raw_work_ram:
            args.raw_work_ram.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(work_ram_raw, args.raw_work_ram)
    document = {
        "schema": "ladybug-mame-gameplay-capture-v2",
        "provenance": {"driver": args.driver, "mame_version": version, "frames": args.frames},
        "plan": plan,
        "video": {"width": width, "height": height, "pixel_format": "BGRA32",
                  "first_frame": args.video_from},
        "inputs": inputs,
        "player": positions,
        "background_changes": changes,
        "work_ram_changes": work_ram_changes,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(document, indent=2) + "\n")
    print(
        f"gameplay capture: {len(positions)} player frames, "
        f"{len(changes)} background-change frames, "
        f"{len(work_ram_changes)} work-RAM-change frames -> {args.output}"
    )


if __name__ == "__main__":
    main()
