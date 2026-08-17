#!/usr/bin/env python3
"""Capture natural and forced BUG-018 part-one enemy palette runtime proof."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import struct
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MONITOR_INPUT = ROOT / "scripts/verify_bug009_monitor_input.py"
PRESENTATION_MAP = ROOT / "build/ladybug-presentation-runtime.map"
ENEMY_MAP = ROOT / "build/ladybug-enemy-runtime.map"
MAIN_MAP = ROOT / "build/ladybug.map"
LAYOUT = ROOT / "build/ladybug-sparse-layout.json"
PAYLOAD = ROOT / "build/ladybug-enemy-sparse.bin"
BANKS = {
    0: ROOT / "build/ladybug-gmc-bank0-overflow.bin",
    2: ROOT / "build/ladybug-sparse-bank2.bin",
    3: ROOT / "build/ladybug-sparse-bank3.bin",
}
SPRITES = ROOT / "assets/arcade/sprites.json"
PAGE_BYTES = 0x2000
FB_FRONT = 0x008F
FB_BACK = 0x0090
FB_WRITE_FRONT_FAULT = 0x0099
ENEMY_ANIM = 0x0054
PRES_CREDITS = 0x00A8
PART_ONE_MAP = (0, 9, 5, 6)
PALETTE = (0x00, 0x26, 0x36, 0x19, 0x3D, 0x17, 0x3F, 0x38,
           0x3A, 0x39, 0x12, 0x3B, 0x24, 0x34, 0x00, 0x00)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_monitor():
    spec = importlib.util.spec_from_file_location("bug009_monitor", MONITOR_INPUT)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load monitor client")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def symbols(path: Path) -> dict[str, int]:
    return {
        name: int(value, 16)
        for name, value in re.findall(
            r"^Symbol: (\w+) .* = ([0-9A-Fa-f]+)$",
            path.read_text(encoding="ascii"), re.MULTILINE,
        )
    }


def read_bytes(client, address: int, length: int, space: str = "cpu") -> bytes:
    params: dict[str, object] = {"addr": address, "length": length}
    if space == "physical":
        params["space"] = "physical"
    return bytes.fromhex(client.call("read_memory", params)["data"])


def read_byte(client, address: int) -> int:
    return read_bytes(client, address, 1)[0]


def write_byte(client, address: int, value: int) -> None:
    client.call("write_memory", {"addr": address, "data": f"{value & 0xff:02x}"})


def register(client, name: str) -> int:
    return int(client.call("read_registers")[name.lower()])


def set_breakpoint(client, address: int) -> int:
    return client.call("set_breakpoint", {"addr": address, "kind": "exec"})["id"]


def initialize_navigation(monitor, client, module: dict[str, int], timeout: float,
                          mode: str, initial_owner: int) -> list[int]:
    start_id = set_breakpoint(client, module["start_screen"])
    hit = client.run_to_breakpoint(timeout)
    if hit.get("pc") != module["start_screen"] or register(client, "a") != 0:
        raise RuntimeError(f"{mode}: cold-attract success marker missing: {hit}")
    monitor.clear(client, [start_id])
    write_byte(client, FB_FRONT, initial_owner)
    write_byte(client, FB_BACK, 1 - initial_owner)
    requests = [0]
    if mode == "live":
        attract_id = set_breakpoint(client, module["attract_tick"])
        hit = client.run_to_breakpoint(timeout)
        if hit.get("pc") != module["attract_tick"]:
            raise RuntimeError(f"live: attract input marker missing: {hit}")
        monitor.clear(client, [attract_id])
        client.call("inject_key", {"key": 5, "action": "press"})
        start_id = set_breakpoint(client, module["start_screen"])
        hit = client.run_to_breakpoint(timeout)
        client.call("inject_key", {"key": 5, "action": "release"})
        if hit.get("pc") != module["start_screen"] or register(client, "a") != 3:
            raise RuntimeError(f"live: credit screen success marker missing: {hit}")
        requests.append(3)
        monitor.clear(client, [start_id])
        credit_id = set_breakpoint(client, module["credit_tick"])
        hit = client.run_to_breakpoint(timeout)
        if hit.get("pc") != module["credit_tick"] or read_byte(client, PRES_CREDITS) != 1:
            raise RuntimeError(f"live: credited state success marker missing: {hit}")
        monitor.clear(client, [credit_id])
        client.call("inject_key", {"key": 1, "action": "press"})
        start_id = set_breakpoint(client, module["start_screen"])
        hit = client.run_to_breakpoint(timeout)
        client.call("inject_key", {"key": 1, "action": "release"})
        if hit.get("pc") != module["start_screen"] or register(client, "a") != 2:
            raise RuntimeError(f"live: part-one request success marker missing: {hit}")
        requests.append(2)
        monitor.clear(client, [start_id])
    return requests


def artifact_identity(client, manifest: dict[str, object]) -> dict[str, object]:
    payload = PAYLOAD.read_bytes()
    staged = bytearray(len(payload))
    coverage = bytearray(len(payload))
    for segment in manifest["gmc"]["segments"]:
        if segment["target"] != "enemy":
            continue
        bank = BANKS[int(segment["bank"])].read_bytes()
        source = int(segment["source_offset"])
        target = int(segment["target_offset"])
        count = int(segment["count"])
        staged[target:target + count] = bank[source:source + count]
        coverage[target:target + count] = b"\x01" * count
    if not all(coverage) or bytes(staged) != payload:
        raise RuntimeError("bank-staged enemy payload differs from generated payload")
    live = b"".join(
        read_bytes(client, page * PAGE_BYTES, PAGE_BYTES, "physical")
        for page in range(0x35, 0x38)
    )[:len(payload)]
    if live != payload:
        raise RuntimeError("live physical sparse pages differ from generated payload")
    selected = []
    for entry in manifest["enemy"]["index"][:16]:
        start = int(entry["payload_offset"])
        end = start + int(entry["length"])
        if live[start:end] != payload[start:end]:
            raise RuntimeError(f"live selected frame {entry['frame']} differs")
        selected.append({
            "frame": entry["frame"], "page": entry["page"],
            "address": entry["address"], "length": entry["length"],
            "sha256": digest(payload[start:end]),
        })
    return {
        "authored_sprite_source_sha256": digest(SPRITES.read_bytes()),
        "generated_payload_sha256": digest(payload),
        "bank_staged_payload_sha256": digest(bytes(staged)),
        "live_physical_payload_sha256": digest(live),
        "selected_part_one_entries": selected,
        "all_equal": True,
    }


def gime_rgb(code: int) -> tuple[int, int, int]:
    return (
        (170 if code & 0x20 else 0) + (85 if code & 0x04 else 0),
        (170 if code & 0x10 else 0) + (85 if code & 0x02 else 0),
        (170 if code & 0x08 else 0) + (85 if code & 0x01 else 0),
    )


def crop_indexes(client, owner: int, address: int) -> list[int]:
    if not 0x2000 <= address <= 0x97F8:
        raise RuntimeError(f"enemy framebuffer pointer is invalid: {address:04x}")
    physical = (0x30 if owner == 0 else 0x2C) * PAGE_BYTES + address - 0x2000
    output = []
    for row in range(16):
        packed = read_bytes(client, physical + row * 160, 8, "physical")
        for value in packed:
            output.extend((value >> 4, value & 0x0F))
    return output


def cpu_crop_indexes(client, address: int) -> list[int]:
    output = []
    for row in range(16):
        for value in read_bytes(client, address + row * 160, 8):
            output.extend((value >> 4, value & 0x0F))
    return output


def stage_indexes(client, address: int) -> list[int]:
    output = []
    for value in read_bytes(client, address, 128):
        output.extend((value >> 4, value & 0x0F))
    return output


def validate_crop(after: list[int], clean_background: list[int], frame_number: int) -> bytes:
    expected = expected_frame(frame_number)
    for index, value in enumerate(expected):
        if value < 0:
            if after[index] != clean_background[index]:
                raise RuntimeError(
                    f"frame {frame_number} outside-mask pixel {index} changed "
                    f"from {clean_background[index]} to {after[index]}"
                )
        elif after[index] != value:
            raise RuntimeError(
                f"frame {frame_number} pixel {index} is {after[index]}, expected {value}"
            )
    sprite_indexes = bytes(after[index] for index, value in enumerate(expected) if value >= 0)
    expected_indexes = bytes(value for value in expected if value >= 0)
    if sprite_indexes != expected_indexes or not set(sprite_indexes) <= set(PART_ONE_MAP[1:]):
        raise RuntimeError("live sprite palette indexes differ")
    return sprite_indexes


def step_nest_commit(client, enemy: dict[str, int], timeout: float) -> None:
    client.call("step_instruction", {"n": 10})
    stopped = client.call("wait_for_stop", {"timeout_ms": int(timeout * 1000)})
    if stopped.get("reason") != "step" or stopped.get("pc") != enemy["cez_commit_row"]:
        raise RuntimeError(f"natural commit-loop entry missing: {stopped}")
    client.call("step_instruction", {"n": 176})
    stopped = client.call("wait_for_stop", {"timeout_ms": int(timeout * 1000)})
    if stopped.get("reason") != "step":
        raise RuntimeError(f"natural commit-loop completion missing: {stopped}")


def png_chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def write_png(path: Path, rgb: bytes, width: int = 16, height: int = 16) -> None:
    rows = b"".join(b"\x00" + rgb[y * width * 3:(y + 1) * width * 3] for y in range(height))
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n" +
        png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) +
        png_chunk(b"IDAT", zlib.compress(rows, 9)) + png_chunk(b"IEND", b"")
    )


def expected_frame(frame_number: int) -> list[int]:
    payload = PAYLOAD.read_bytes()
    entry = payload[frame_number * 3:frame_number * 3 + 3]
    cursor = (entry[0] - 0x35) * PAGE_BYTES + ((entry[1] << 8) | entry[2]) - 0xA000
    framebuffer_cursor = 0
    stage_cursor = 0
    pixels = [0] * 256
    mask = [False] * 256
    while True:
        token = payload[cursor]
        cursor += 1
        if token == 0xFF:
            fb_delta = (payload[cursor] << 8) | payload[cursor + 1]
            cursor += 2
            if fb_delta == 0:
                break
            stage_delta = payload[cursor]
            cursor += 1
        else:
            fb_delta = token
            stage_delta = token if token < 0x80 else token - 152
        framebuffer_cursor += fb_delta
        stage_cursor += stage_delta
        row, column = divmod(stage_cursor, 8)
        control = payload[cursor]
        cursor += 1
        partial = bool(control & 0x80)
        count = control & 0x7F
        for index in range(count):
            target = row * 16 + (column + index) * 2
            if partial:
                preserve, value = payload[cursor:cursor + 2]
                cursor += 2
                if preserve == 0xF0:
                    pixels[target + 1] = value & 15
                    mask[target + 1] = True
                else:
                    pixels[target] = value >> 4
                    mask[target] = True
            else:
                value = payload[cursor]
                cursor += 1
                pixels[target:target + 2] = [value >> 4, value & 15]
                mask[target:target + 2] = [True, True]
        framebuffer_cursor += count
        stage_cursor += count
    return [pixels[index] if mask[index] else -1 for index in range(256)]


def capture_draw(monitor, client, enemy: dict[str, int], timeout: float,
                 forced: tuple[int, int] | None) -> dict[str, object]:
    while True:
        draw_id = set_breakpoint(client, enemy["draw_enemy_stage"])
        hit = client.run_to_breakpoint(timeout)
        monitor.clear(client, [draw_id])
        if hit.get("pc") != enemy["draw_enemy_stage"]:
            raise RuntimeError(f"part-one stage draw success marker missing: {hit}")
        stage_address = register(client, "x")
        # The cold cache builder uses $1800 and never publishes that temporary
        # surface. The natural dormant actor is composed at $1880 and committed.
        if stage_address == 0x1880:
            break
    direction = register(client, "b") & 3
    phase = read_byte(client, ENEMY_ANIM) & 3
    if forced is not None:
        direction, phase = forced
        client.call("write_registers", {"b": direction})
        write_byte(client, ENEMY_ANIM, phase)
    stage_offset = stage_address - 0x1800
    stage_row, byte_column = divmod(stage_offset, 8)
    address = 0x4DEC + stage_row * 160 + byte_column
    owner = read_byte(client, FB_BACK)
    clean_background = stage_indexes(client, stage_address)
    done_id = set_breakpoint(client, enemy["sparse_decode_done"])
    hit = client.run_to_breakpoint(timeout)
    monitor.clear(client, [done_id])
    if hit.get("pc") != enemy["sparse_decode_done"]:
        raise RuntimeError(f"stage sparse-decode marker missing: {hit}")
    stage_after = stage_indexes(client, stage_address)
    validate_crop(stage_after, clean_background, direction * 4 + phase)
    client.call("step_instruction", {"n": 8})
    stopped = client.call("wait_for_stop", {"timeout_ms": int(timeout * 1000)})
    if stopped.get("reason") != "step" or stopped.get("pc") != enemy["cez_commit_row"]:
        raise RuntimeError(f"stage commit-loop entry missing: {stopped}")
    client.call("step_instruction", {"n": 352})
    stopped = client.call("wait_for_stop", {"timeout_ms": int(timeout * 1000)})
    if stopped.get("reason") != "step":
        raise RuntimeError(f"stage commit-loop completion missing: {stopped}")
    after = cpu_crop_indexes(client, address)
    physical_matches = [candidate for candidate in (0, 1)
                        if crop_indexes(client, candidate, address) == after]
    if not physical_matches:
        raise RuntimeError("CPU-visible committed crop matches neither physical framebuffer")
    sprite_indexes = validate_crop(
        after, clean_background, direction * 4 + phase
    )
    rgb = bytes(component for index in after for component in gime_rgb(PALETTE[index]))
    return {
        "coverage": "forced" if forced is not None else "natural",
        "direction": direction, "phase": phase, "back_owner": owner,
        "physical_owner_matches": physical_matches,
        "stage_address": stage_address,
        "framebuffer_address": address,
        "crop_palette_sha256": digest(bytes(after)),
        "crop_rgb_sha256": digest(rgb),
        "sprite_palette_sha256": digest(sprite_indexes),
        "outside_mask_unchanged": True,
        "palette_indexes": sorted(set(sprite_indexes)),
        "rgb": rgb,
    }


def capture_natural_animation(monitor, client, enemy: dict[str, int], timeout: float) -> dict[str, object]:
    animation_id = set_breakpoint(client, enemy["compose_enemy_animation"])
    hit = client.run_to_breakpoint(timeout)
    monitor.clear(client, [animation_id])
    if hit.get("pc") != enemy["compose_enemy_animation"]:
        raise RuntimeError(f"natural animation success marker missing: {hit}")
    # Keep the palette probe on the part-one dormant actor if the long
    # presentation path has reached the later vegetable boundary.
    write_byte(client, 0x005A, 0)
    phase = read_byte(client, ENEMY_ANIM) & 3
    owner = read_byte(client, FB_BACK)
    clean_background = stage_indexes(client, 0xA510)
    step_nest_commit(client, enemy, timeout)
    after = cpu_crop_indexes(client, 0x57EC)
    physical_matches = [candidate for candidate in (0, 1)
                        if crop_indexes(client, candidate, 0x57EC) == after]
    if not physical_matches:
        raise RuntimeError("natural crop matches neither physical framebuffer")
    sprite_indexes = validate_crop(after, clean_background, phase)
    rgb = bytes(component for index in after for component in gime_rgb(PALETTE[index]))
    return {
        "coverage": "natural", "direction": 0, "phase": phase,
        "back_owner": owner, "framebuffer_address": 0x57EC,
        "physical_owner_matches": physical_matches,
        "crop_palette_sha256": digest(bytes(after)),
        "crop_rgb_sha256": digest(rgb),
        "sprite_palette_sha256": digest(sprite_indexes),
        "outside_mask_unchanged": True,
        "palette_indexes": sorted(set(sprite_indexes)),
    }


def prime_forced_render(monitor, client, enemy: dict[str, int], timeout: float) -> None:
    frame_id = set_breakpoint(client, enemy["frame_render_impl"])
    hit = client.run_to_breakpoint(timeout)
    monitor.clear(client, [frame_id])
    if hit.get("pc") != enemy["frame_render_impl"]:
        raise RuntimeError(f"forced render boundary missing: {hit}")
    client.call("write_memory", {"addr": 0xA470, "data": "00" * 32})
    write_byte(client, 0x0058, 0)
    write_byte(client, 0x005A, 0)
    write_byte(client, 0x0060, 1)
    write_byte(client, 0x0087, 0x0A)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xroar", type=Path, required=True)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--mode", choices=("demo", "live"), required=True)
    parser.add_argument("--initial-owner", type=int, choices=(0, 1), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--png", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()
    if args.timeout > 60:
        raise SystemExit("BUG-018 runtime: phase deadline must not exceed 60 seconds")

    monitor = load_monitor()
    presentation = symbols(PRESENTATION_MAP)
    enemy = symbols(ENEMY_MAP)
    main_symbols = symbols(MAIN_MAP)
    manifest = json.loads(LAYOUT.read_text(encoding="ascii"))
    process, client = monitor.launch(args.xroar, args.rom, monitor.free_port())
    try:
        requests = initialize_navigation(
            monitor, client, presentation, args.timeout, args.mode, args.initial_owner
        )
        identity = artifact_identity(client, manifest)
        timer_id = set_breakpoint(client, main_symbols["perimeter_timer_tick"])
        hit = client.run_to_breakpoint(args.timeout)
        monitor.clear(client, [timer_id])
        if hit.get("pc") != main_symbols["perimeter_timer_tick"]:
            raise RuntimeError(f"part-one gameplay success marker missing: {hit}")
        natural = []
        for _ in range(16):
            sample = capture_natural_animation(monitor, client, enemy, args.timeout)
            natural.append(sample)
            if {item["phase"] for item in natural} == {0, 1, 2, 3}:
                break
        if {item["phase"] for item in natural} != {0, 1, 2, 3}:
            raise RuntimeError("natural observation did not reach all four animation phases")

        forced = []
        final_rgb = b""
        pending = [(direction, phase, owner)
                   for direction in range(4) for phase in range(4) for owner in range(2)]
        attempts = 0
        while pending and attempts < 128:
            direction, phase, wanted_owner = pending[0]
            prime_forced_render(monitor, client, enemy, args.timeout)
            sample = capture_draw(monitor, client, enemy, args.timeout, (direction, phase))
            attempts += 1
            final_rgb = sample.pop("rgb")
            forced.append(sample)
            if sample["back_owner"] == wanted_owner:
                pending.pop(0)
        if pending:
            raise RuntimeError(f"forced owner/direction/phase coverage missing: {pending}")
        if read_byte(client, FB_WRITE_FRONT_FAULT) != 0:
            raise RuntimeError("runtime capture detected writes to physical FRONT")
        write_png(args.png, final_rgb)
        evidence = {
            "schema": "ladybug-bug018-runtime-v1",
            "mode": args.mode,
            "initial_owner": args.initial_owner,
            "phase_deadline_seconds": args.timeout,
            "success_markers": [
                "cold-attract", "credited-part-one" if args.mode == "live" else "natural-demo",
                "part-one-stage-draw", "part-one-framebuffer-commit",
            ],
            "timeout_meaning": "failure of the named observation boundary only",
            "screen_requests": requests,
            "palette_probe_state": "natural initialized part-one dormant actor",
            "rom_sha256": digest(args.rom.read_bytes()),
            "artifact_identity": identity,
            "natural_samples": natural,
            "natural_directions": sorted({item["direction"] for item in natural}),
            "natural_phases": sorted({item["phase"] for item in natural}),
            "forced_samples": forced,
            "forced_direction_phase_owner_cases": 32,
            "owners_converged": sorted({item["back_owner"] for item in forced}) == [0, 1],
            "outside_mask_unchanged": all(item["outside_mask_unchanged"] for item in natural + forced),
            "front_write_faults": 0,
            "png_sha256": digest(args.png.read_bytes()),
            "pass": True,
        }
        args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="ascii")
        print(
            f"BUG-018 runtime pass: {args.mode} initial owner {args.initial_owner}, "
            f"{len(natural)} natural samples, 32 forced direction/phase/owner cases"
        )
    finally:
        client.close()
        monitor.stop(process)
        process.wait(timeout=2)


if __name__ == "__main__":
    main()
