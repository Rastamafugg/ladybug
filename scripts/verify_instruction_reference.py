#!/usr/bin/env python3
"""Verify the frame-indexed BUG-011 arcade instruction oracle."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REFERENCE = ROOT / "assets" / "arcade" / "instruction_reference.json"


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


def canonical_digest(path: Path) -> str:
    return digest(path.read_bytes().replace(b"\r\n", b"\n"))


def colour_at(frame: int, clock: dict[str, object]) -> str:
    first_transition = int(clock["first_transition_frame"])
    if frame < first_transition:
        return str(clock["starting_colour"])
    dwell = int(clock["dwell_frames"])
    order = [str(value) for value in clock["repeat_order"]]
    return order[((frame - first_transition) // dwell) % len(order)]


def validate_reference(reference: dict[str, object]) -> list[dict[str, object]]:
    if reference.get("schema") != "ladybug-mame-instruction-reference-v1":
        raise SystemExit("instruction oracle: unexpected schema")

    provenance = reference["provenance"]
    plan = ROOT / str(provenance["capture_plan"])
    if canonical_digest(plan) != provenance["capture_plan_sha256"]:
        raise SystemExit("instruction oracle: capture-plan hash mismatch")

    interval = reference["instruction_interval"]
    first = int(interval["first_complete_frame"])
    last = int(interval["last_complete_frame"])
    if last - first + 1 != int(interval["duration_frames"]):
        raise SystemExit("instruction oracle: inclusive duration mismatch")
    if int(interval["next_screen_first_partial_frame"]) != last + 1:
        raise SystemExit("instruction oracle: next-screen boundary is not contiguous")

    clock = reference["colour_clock"]
    if int(clock["dwell_frames"]) != 30:
        raise SystemExit("instruction oracle: colour dwell is not 30 frames")
    if clock["values"] != {"red": 800, "yellow": 300, "blue": 100}:
        raise SystemExit("instruction oracle: point-value mapping mismatch")
    if [colour_at(frame, clock) for frame in (745, 776, 806, 836)] != [
        "red", "yellow", "blue", "red"
    ]:
        raise SystemExit("instruction oracle: starting colour alignment mismatch")
    last_transition = int(clock["last_transition_frame"])
    if colour_at(last_transition, clock) != "red":
        raise SystemExit("instruction oracle: terminal colour mismatch")
    if int(clock["freeze_frame"]) != 2197:
        raise SystemExit("instruction oracle: colour freeze boundary mismatch")

    rows = reference["rows"]
    expected = [
        ("EXTRA", "yellow", list("EXTRA")),
        ("SPECIAL", "red", list("SPECIAL")),
        ("HEARTS", "blue", ["heart_x2", "heart_x3", "heart_x5"]),
    ]
    if len(rows) != len(expected):
        raise SystemExit("instruction oracle: all three rows are required")
    all_targets: list[dict[str, object]] = []
    prior_consume = first - 1
    hashes = reference["event_frame_sha256"]
    for row, (name, trigger_colour, target_names) in zip(rows, expected):
        if row["name"] != name or row["trigger_colour"] != trigger_colour:
            raise SystemExit(f"instruction oracle: {name} row contract mismatch")
        targets = row["targets"]
        if [target["name"] for target in targets] != target_names:
            raise SystemExit(f"instruction oracle: {name} target order mismatch")
        for target in targets:
            trigger = int(target["trigger_frame"])
            consume = int(target["consume_frame"])
            motion = int(target["motion_first_frame"])
            if colour_at(trigger, clock) != trigger_colour:
                raise SystemExit(
                    f"instruction oracle: {name}/{target['name']} trigger colour mismatch"
                )
            if trigger < prior_consume or consume != trigger + 16 or motion >= consume:
                raise SystemExit(
                    f"instruction oracle: {name}/{target['name']} event order mismatch"
                )
            if str(trigger) not in hashes or str(consume) not in hashes:
                raise SystemExit(
                    f"instruction oracle: {name}/{target['name']} frame evidence missing"
                )
            prior_consume = consume
            all_targets.append(target)

    extra, special, hearts = rows
    if (
        int(extra["reward_frame"]) != int(extra["targets"][-1]["consume_frame"])
        or int(extra["next_row_actor_frame"]) != int(extra["reward_frame"]) + 1
        or int(special["reward_frame"]) != int(special["targets"][-1]["consume_frame"])
        or int(special["next_row_actor_frame"]) != int(special["reward_frame"]) + 1
    ):
        raise SystemExit("instruction oracle: reward/row boundary mismatch")
    if [int(target["multiplier"]) for target in hearts["targets"]] != [2, 3, 5]:
        raise SystemExit("instruction oracle: heart multiplier sequence mismatch")
    skull = hearts["skull"]
    if (
        int(skull["motion_first_frame"]) <= int(hearts["targets"][-1]["consume_frame"])
        or int(skull["last_ladybug_frame"]) + 1 != int(skull["collision_frame"])
    ):
        raise SystemExit("instruction oracle: skull collision order mismatch")

    death = reference["death_sequence"]
    impact = death["impact"]
    if (
        int(impact["first_frame"]) != int(skull["collision_frame"])
        or int(impact["last_frame"]) - int(impact["first_frame"]) + 1 != 30
        or int(impact["duration_frames"]) != 30
    ):
        raise SystemExit("instruction oracle: impact timing mismatch")
    ordered = death["ordered_frames"]
    if len(ordered) != 13:
        raise SystemExit("instruction oracle: all thirteen death surfaces are required")
    expected_first = int(impact["last_frame"]) + 1
    for index, item in enumerate(ordered):
        item_first = int(item["first_frame"])
        item_last = int(item["last_frame"])
        if item_first != expected_first or item_last - item_first + 1 != 5:
            raise SystemExit(f"instruction oracle: death surface {index} timing mismatch")
        expected_first = item_last + 1
    angel = death["angel_hold"]
    if (
        int(angel["first_frame"]) != expected_first
        or int(angel["last_frame"]) != last
        or int(angel["duration_frames"]) != 65
        or not angel["stationary"]
    ):
        raise SystemExit("instruction oracle: stationary angel hold mismatch")
    if len({impact["crop_sha256"], *[item["crop_sha256"] for item in ordered], angel["crop_sha256"]}) != 15:
        raise SystemExit("instruction oracle: death surfaces are not discriminating")

    contract = reference["implementation_contract"]
    if contract["point_values"] != clock["values"]:
        raise SystemExit("instruction oracle: implementation values diverge from source")
    return all_targets


class RawVideo:
    def __init__(self, path: Path, provenance: dict[str, object]):
        video = provenance["video"]
        self.path = path
        self.first = int(video["first_frame"])
        self.width = int(video["width"])
        self.height = int(video["height"])
        self.stride = self.width * self.height * 4
        expected = int(video["retained_frames"]) * self.stride
        if path.stat().st_size != expected:
            raise SystemExit("instruction oracle: raw-video byte count mismatch")
        hasher = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                hasher.update(block)
        if hasher.hexdigest() != provenance["raw_video_sha256"]:
            raise SystemExit("instruction oracle: raw-video hash mismatch")

    def frame(self, number: int) -> bytes:
        offset = (number - self.first) * self.stride
        if offset < 0:
            raise SystemExit(f"instruction oracle: frame {number} precedes retained video")
        with self.path.open("rb") as stream:
            stream.seek(offset)
            frame = stream.read(self.stride)
        if len(frame) != self.stride:
            raise SystemExit(f"instruction oracle: frame {number} is absent")
        return frame

    def crop(self, number: int, xywh: list[int]) -> bytes:
        x, y, width, height = [int(value) for value in xywh]
        frame = self.frame(number)
        rows = bytearray()
        for row in range(y, y + height):
            start = (row * self.width + x) * 4
            rows.extend(frame[start:start + width * 4])
        return bytes(rows)


def validate_raw(
    reference: dict[str, object], targets: list[dict[str, object]], path: Path
) -> None:
    raw = RawVideo(path, reference["provenance"])
    frame_hashes = {
        **reference["boundary_frame_sha256"],
        **reference["event_frame_sha256"],
    }
    for number, expected in frame_hashes.items():
        if digest(raw.frame(int(number))) != expected:
            raise SystemExit(f"instruction oracle: frame {number} hash mismatch")

    for target in targets:
        motion = int(target["motion_first_frame"])
        if raw.frame(motion) == raw.frame(motion - 1):
            raise SystemExit(
                f"instruction oracle: {target['name']} motion boundary is static"
            )

    death = reference["death_sequence"]
    crop = death["crop_xywh"]
    runs = [death["impact"], *death["ordered_frames"], death["angel_hold"]]
    for index, run in enumerate(runs):
        expected = run["crop_sha256"]
        for number in range(int(run["first_frame"]), int(run["last_frame"]) + 1):
            if digest(raw.crop(number, crop)) != expected:
                raise SystemExit(
                    f"instruction oracle: death run {index} frame {number} mismatch"
                )

    clock = reference["colour_clock"]
    rgb = clock["source_rgb"]
    for number in range(
        int(clock["first_complete_frame"]), int(clock["last_transition_frame"]) + 1
    ):
        expected_rgb = bytes(rgb[colour_at(number, clock)])
        crop_bytes = raw.crop(number, [40, 155, 12, 13])
        pixels = [
            bytes((crop_bytes[i + 2], crop_bytes[i + 1], crop_bytes[i]))
            for i in range(0, len(crop_bytes), 4)
        ]
        if pixels.count(expected_rgb) != 43:
            raise SystemExit(
                f"instruction oracle: colour/value icon frame {number} mismatch"
            )


def main() -> None:
    args = parse_args()
    reference = json.loads(args.reference.read_text(encoding="ascii"))
    targets = validate_reference(reference)
    if args.raw_video:
        validate_raw(reference, targets, args.raw_video)
    print(
        "instruction oracle: 30-frame colour dwell, 15 ordered pickups, skull, "
        "30+13x5 death frames, 65-frame held angel, and next-screen boundary verified"
    )


if __name__ == "__main__":
    main()
