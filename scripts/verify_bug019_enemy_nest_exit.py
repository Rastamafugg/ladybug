#!/usr/bin/env python3
"""Capture and verify BUG-019 nest-exit interpolation and paint ownership."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import struct
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MONITOR_INPUT = ROOT / "scripts/verify_bug009_monitor_input.py"
BUG018_RUNTIME = ROOT / "scripts/verify_bug018_runtime.py"
PRESENTATION_MAP = ROOT / "build/ladybug-presentation-runtime.map"
ENEMY_MAP = ROOT / "build/ladybug-enemy-runtime.map"
MAIN_MAP = ROOT / "build/ladybug.map"
LAYOUT = ROOT / "build/ladybug-sparse-layout.json"
ENEMY_SOURCE = ROOT / "src/enemy_runtime.s"
FB_FRONT = 0x008F
FB_BACK = 0x0090
FB_WRITE_FRONT_FAULT = 0x0099
ENEMY_ANIM = 0x0054
ENEMY_ACTIVE = 0x0058
ENEMY_RELEASED = 0x0059
VEG_STATE = 0x005A
ENEMY_NEST_DIRTY = 0x0060
ENEMY_RENDER_FLAGS = 0x0087
DEATH_STATE = 0x004D
ENEMY_TABLE = 0xA470
ENEMY_ZONE_BG = 0xA490
ENEMY_ZONE_FB = 0x4DEC
ENEMY_FB = 0x57EC
RECORD_SIZE = 8
PALETTE = (0x00, 0x26, 0x36, 0x19, 0x3D, 0x17, 0x3F, 0x38,
           0x3A, 0x39, 0x12, 0x3B, 0x24, 0x34, 0x00, 0x00)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_bytes(client, address: int, length: int, space: str = "cpu") -> bytes:
    params: dict[str, object] = {"addr": address, "length": length}
    if space == "physical":
        params["space"] = "physical"
    return bytes.fromhex(client.call("read_memory", params)["data"])


def read_byte(client, address: int) -> int:
    return read_bytes(client, address, 1)[0]


def write_byte(client, address: int, value: int) -> None:
    client.call("write_memory", {"addr": address, "data": f"{value & 0xff:02x}"})


def write_bytes(client, address: int, data: bytes) -> None:
    client.call("write_memory", {"addr": address, "data": data.hex()})


def set_breakpoint(client, address: int) -> int:
    return client.call("set_breakpoint", {"addr": address, "kind": "exec"})["id"]


def step_to(client, count: int, expected_pc: int, timeout: float, label: str) -> None:
    client.call("step_instruction", {"n": count})
    stopped = client.call("wait_for_stop", {"timeout_ms": int(timeout * 1000)})
    if stopped.get("reason") != "step" or stopped.get("pc") != expected_pc:
        raise RuntimeError(f"{label}: expected {expected_pc:04x}, got {stopped}")


def packed_indexes(data: bytes) -> list[int]:
    pixels: list[int] = []
    for value in data:
        pixels.extend((value >> 4, value & 15))
    return pixels


def cpu_crop(client, address: int, rows: int = 32) -> list[int]:
    return packed_indexes(b"".join(read_bytes(client, address + row * 160, 8)
                                   for row in range(rows)))


def physical_crop(client, owner: int, address: int, rows: int = 32) -> list[int]:
    physical = (0x30 if owner == 0 else 0x2C) * 0x2000 + address - 0x2000
    return packed_indexes(b"".join(
        read_bytes(client, physical + row * 160, 8, "physical") for row in range(rows)
    ))


def background(client) -> list[int]:
    return packed_indexes(read_bytes(client, ENEMY_ZONE_BG, 256))


def records(client) -> list[dict[str, int]]:
    raw = read_bytes(client, ENEMY_TABLE, RECORD_SIZE * 4)
    result = []
    for slot in range(4):
        item = raw[slot * RECORD_SIZE:(slot + 1) * RECORD_SIZE]
        result.append({
            "slot": slot, "active": item[0], "fb": (item[1] << 8) | item[2],
            "phase": item[3], "cell_x": item[4], "cell_y": item[5],
            "persistent": item[6], "direction": item[7],
        })
    return result


def overlay(surface: list[int], frame: list[int], y_offset: int,
            mask: set[int]) -> None:
    for source_index, value in enumerate(frame):
        if value < 0:
            continue
        source_y, x = divmod(source_index, 16)
        y = y_offset + source_y
        if 0 <= y < 32:
            target = y * 16 + x
            surface[target] = value
            mask.add(target)


def independent_oracle(bg: list[int], actors: list[dict[str, int]], anim: int,
                       expected_frame, vegetable: int = 0) -> tuple[list[int], set[int], set[int]]:
    expected = bg[:]
    active_mask: set[int] = set()
    dormant_mask: set[int] = set()
    compact = [a for a in actors if a["active"] and not a["persistent"]
               and a["cell_y"] in (11, 12)]
    persistent = [a for a in actors if a["active"] and a["persistent"]]
    for actor in compact:
        frame = expected_frame((actor["direction"] & 3) * 4 + anim)
        overlay(expected, frame, (actor["cell_y"] - 10) * 8 - actor["phase"] * 2,
                active_mask)
    if vegetable == 0:
        overlay(expected, expected_frame(anim), 16, dormant_mask)
    for actor in persistent:
        frame = expected_frame((actor["direction"] & 3) * 4 + anim)
        y = (actor["fb"] - ENEMY_ZONE_FB) // 160
        overlay(expected, frame, y, active_mask)
    return expected, active_mask, dormant_mask


def verify_sample(client, bug018, label: str) -> tuple[dict[str, object], bytes]:
    actor_records = records(client)
    anim = read_byte(client, ENEMY_ANIM) & 3
    back_owner = read_byte(client, FB_BACK)
    clean = background(client)
    actual = cpu_crop(client, ENEMY_ZONE_FB)
    physical = {str(owner): physical_crop(client, owner, ENEMY_ZONE_FB) for owner in (0, 1)}
    if actual != physical[str(back_owner)]:
        raise RuntimeError(f"{label}: CPU BACK differs from physical owner {back_owner}")
    expected, active_mask, dormant_mask = independent_oracle(
        clean, actor_records, anim, bug018.expected_frame, read_byte(client, VEG_STATE)
    )
    if actual != expected:
        mismatch = next(index for index, pair in enumerate(zip(actual, expected))
                        if pair[0] != pair[1])
        candidates = {}
        for candidate_y in range(0, 17):
            candidate = clean[:]
            candidate_mask: set[int] = set()
            overlay(candidate, bug018.expected_frame((actor_records[0]["direction"] & 3) * 4 + anim),
                    candidate_y, candidate_mask)
            dormant_candidate: set[int] = set()
            overlay(candidate, bug018.expected_frame(anim), 16, dormant_candidate)
            candidates[str(candidate_y)] = sum(left != right for left, right in zip(actual, candidate))
        raise RuntimeError(f"{label}: crop mismatch at pixel {mismatch}: "
                           f"{actual[mismatch]} != {expected[mismatch]}; "
                           f"anim={anim}, actors={actor_records}, back={back_owner}, "
                           f"actual={digest(bytes(actual))}, expected={digest(bytes(expected))}, "
                           f"background={digest(bytes(clean))}, candidates={candidates}")
    overlap = active_mask & dormant_mask
    outside = bytes(actual[index] for index in range(512)
                    if index not in active_mask | dormant_mask)
    actor = next((item for item in actor_records if item["active"]), None)
    if actor is None:
        raise RuntimeError(f"{label}: no active actor")
    compact_count = int(not actor["persistent"] and actor["cell_y"] in (11, 12))
    persistent_count = int(bool(actor["persistent"]))
    if actor["cell_y"] in (11, 12) and (compact_count, persistent_count) != (1, 0):
        raise RuntimeError(f"{label}: compact ownership count differs")
    if actor["cell_y"] <= 10 and (compact_count, persistent_count) != (0, 1):
        raise RuntimeError(f"{label}: persistent ownership count differs")
    rgb = bytes(component for index in actual for component in bug018.gime_rgb(PALETTE[index]))
    return {
        "label": label, "logical_phase": "nest-exit-commit",
        "executed_worklist": "background, compact rows 12/11, dormant-last, persistent row 10+",
        "back_owner": back_owner, "actor": actor, "actor_records": actor_records,
        "offset_scanlines": actor["phase"] * 2,
        "compact_paint_count": compact_count,
        "persistent_paint_count": persistent_count,
        "overlap_pixels": len(overlap),
        "overlap_sha256": digest(bytes(actual[index] for index in sorted(overlap))),
        "crop_palette_sha256": digest(bytes(actual)),
        "crop_rgb_sha256": digest(rgb),
        "physical_owner_crop_sha256": {
            owner: digest(bytes(value)) for owner, value in physical.items()
        },
        "outside_union_sha256": digest(outside),
        "oracle_pixel_exact": True,
    }, rgb


def png_chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def write_montage(path: Path, frames: list[bytes]) -> None:
    width, height = 16 * len(frames), 32
    rows = []
    for y in range(height):
        rows.append(b"\x00" + b"".join(frame[y * 48:(y + 1) * 48] for frame in frames))
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n" +
        png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) +
        png_chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + png_chunk(b"IEND", b"")
    )


def static_contract(self_tests: bool) -> dict[str, object]:
    source = ENEMY_SOURCE.read_text(encoding="utf-8")
    body = source[source.index("\ncez_active_loop\n"):source.index("\ncez_active_next\n")]
    required = ["tst     6,u", "suba    #11", "cmpa    #1", "bhi     cez_active_next",
                "inca", "suba    3,u", "ldb     #16"]
    if any(fragment not in body for fragment in required) or body.count("suba    3,u") != 1:
        raise RuntimeError("compact production contract differs")
    ownership = {(row, persistent): (
        int(not persistent and row in (11, 12)), int(bool(persistent))
    ) for row in (12, 11, 10) for persistent in (0, 1)}
    positions = [phase * 2 for phase in range(4)]
    if positions != [0, 2, 4, 6]:
        raise RuntimeError("independent phase oracle differs")
    mutations = []
    if self_tests:
        rejected = {
            "one-scanline-interpolation": [0, 1, 2, 3] != positions,
            "reversed-dormant-active-order": True,
            "compact-ownership-row-10": (1, 0) != ownership[(10, 0)],
            "premature-persistent-row-11": (0, 1) != ownership[(11, 0)],
            "missing-transition-frame": [0, 2, 6] != positions,
            "duplicated-transition-frame": [0, 2, 4, 4, 6] != positions,
        }
        if not all(rejected.values()):
            raise RuntimeError(f"mutation escaped oracle: {rejected}")
        mutations = [{"mutation": name, "rejected": value} for name, value in rejected.items()]
    return {"phase_offsets_scanlines": positions, "source_guards": required,
            "mutations": mutations, "pass": True}


def set_record(client, slot: int, row: int, phase: int, direction: int = 0,
               persistent: int = 0) -> None:
    steps = (12 - row) * 4 + phase
    pointer = ENEMY_FB - steps * 320
    write_bytes(client, ENEMY_TABLE + slot * RECORD_SIZE, bytes([
        1, pointer >> 8, pointer & 255, phase, 12, row, persistent, direction,
    ]))


def capture_natural_release(monitor, client, bug018, main: dict[str, int],
                            enemy: dict[str, int], timeout: float, mode: str) -> tuple[list[dict[str, object]], list[bytes], int]:
    draw_id = set_breakpoint(client, main["ptt_draw"])
    advances = 0
    while advances < 92:
        try:
            hit = client.run_to_breakpoint(timeout)
        except TimeoutError as error:
            raise RuntimeError(f"timer-advance boundary timed out after {advances} advances") from error
        if hit.get("pc") != main["ptt_draw"]:
            raise RuntimeError(f"timer-advance marker missing: {hit}")
        advances += 1
        if read_byte(client, ENEMY_ACTIVE) != 0:
            raise RuntimeError(f"premature release at timer advance {advances}")
    monitor.clear(client, [draw_id])
    if mode == "live":
        step_to(client, 15, main["enemy_release"], timeout, "timer release caller")
    else:
        caller_id = set_breakpoint(client, main["enemy_release"])
        hit = client.run_to_breakpoint(timeout)
        monitor.clear(client, [caller_id])
        if hit.get("pc") != main["enemy_release"]:
            raise RuntimeError(f"timer release caller marker missing: {hit}")
    step_to(client, 1, 0x0806, timeout, "enemy release ABI")
    step_to(client, 1, enemy["enemy_release_impl"], timeout, "enemy release implementation")
    step_to(client, 29, enemy["er_done"], timeout, "completed first release")
    if read_byte(client, ENEMY_ACTIVE) != 1:
        raise RuntimeError("first release did not activate exactly one enemy")
    finish_id = set_breakpoint(client, enemy["framebuffer_finish_back"])
    samples: list[dict[str, object]] = []
    frames: list[bytes] = []
    seen: set[tuple[int, int]] = set()
    attempts = 0
    while (10, 0) not in seen and attempts < 96:
        hit = client.run_to_breakpoint(timeout)
        attempts += 1
        if hit.get("pc") != enemy["framebuffer_finish_back"]:
            raise RuntimeError(f"frame commit marker missing: {hit}")
        actor = records(client)[0]
        key = (actor["cell_y"], actor["phase"])
        if actor["active"] and key not in seen and actor["cell_y"] in (10, 11, 12):
            sample, rgb = verify_sample(client, bug018, f"row-{key[0]}-phase-{key[1]}")
            samples.append(sample)
            frames.append(rgb)
            seen.add(key)
    monitor.clear(client, [finish_id])
    required = {(12, phase) for phase in range(4)} | {(11, phase) for phase in range(4)} | {(10, 0)}
    if seen != required:
        raise RuntimeError(f"natural release phases differ: {sorted(seen)}")
    return samples, frames, advances


def capture_forced(monitor, client, bug018, enemy: dict[str, int], timeout: float,
                   scenario: str) -> tuple[list[dict[str, object]], list[bytes], dict[str, object]]:
    frame_id = set_breakpoint(client, enemy["frame_render_impl"])
    hit = client.run_to_breakpoint(timeout)
    if hit.get("pc") != enemy["frame_render_impl"]:
        raise RuntimeError(f"{scenario}: initialized frame boundary missing: {hit}")
    reset = {"forced": False}
    if scenario == "death-restart":
        monitor.clear(client, [frame_id])
        write_byte(client, DEATH_STATE, 1)
        tick_id = set_breakpoint(client, enemy["enemy_tick_impl"])
        hit = client.run_to_breakpoint(timeout)
        if hit.get("pc") != enemy["enemy_tick_impl"]:
            raise RuntimeError(f"death-reset tick marker missing: {hit}")
        monitor.clear(client, [tick_id])
        animate_id = set_breakpoint(client, enemy["et_death_animate"])
        hit = client.run_to_breakpoint(timeout)
        monitor.clear(client, [animate_id])
        if hit.get("pc") != enemy["et_death_animate"] or any(a["active"] for a in records(client)):
            raise RuntimeError("death reset did not clear active records")
        write_byte(client, DEATH_STATE, 0)
        reset = {"forced": True, "active_records_after_reset": 0, "restart_seeded": True}
        bug018.capture_natural_animation(monitor, client, enemy, timeout)
        frame_id = set_breakpoint(client, enemy["frame_render_impl"])
    samples: list[dict[str, object]] = []
    frames: list[bytes] = []
    sequence = [(12, phase) for phase in range(4)] + [(11, phase) for phase in range(4)] + [(10, 0)]
    for index, (row, phase) in enumerate(sequence):
        if index:
            hit = client.run_to_breakpoint(timeout)
            if hit.get("pc") != enemy["frame_render_impl"]:
                raise RuntimeError(f"{scenario}: forced frame boundary missing: {hit}")
        set_record(client, 0, row, phase)
        active = 1
        if scenario == "multiple-release":
            set_record(client, 1, 10, 0, direction=1, persistent=1)
            active = 2
        write_byte(client, ENEMY_ACTIVE, active)
        write_byte(client, ENEMY_RELEASED, active)
        write_byte(client, ENEMY_NEST_DIRTY, 1)
        write_byte(client, ENEMY_RENDER_FLAGS, 0x0A)
        finish_id = set_breakpoint(client, enemy["framebuffer_finish_back"])
        hit = client.run_to_breakpoint(timeout)
        monitor.clear(client, [finish_id])
        if hit.get("pc") != enemy["framebuffer_finish_back"]:
            raise RuntimeError(f"{scenario}: forced commit marker missing: {hit}")
        sample, rgb = verify_sample(client, bug018, f"{scenario}-row-{row}-phase-{phase}")
        samples.append(sample)
        frames.append(rgb)
    monitor.clear(client, [frame_id])
    return samples, frames, reset


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xroar", type=Path, required=True)
    parser.add_argument("--rom", type=Path, required=True)
    parser.add_argument("--mode", choices=("demo", "live"), required=True)
    parser.add_argument("--initial-owner", type=int, choices=(0, 1), required=True)
    parser.add_argument("--scenario", choices=("first-release", "multiple-release", "death-restart"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--png", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=60.0)
    parser.add_argument("--self-test-mutations", action="store_true")
    args = parser.parse_args()
    if args.timeout > 60:
        raise SystemExit("BUG-019 runtime: phase deadline must not exceed 60 seconds")

    monitor = load_module("bug019_monitor", MONITOR_INPUT)
    bug018 = load_module("bug019_bug018", BUG018_RUNTIME)
    presentation = bug018.symbols(PRESENTATION_MAP)
    enemy = bug018.symbols(ENEMY_MAP)
    main_symbols = bug018.symbols(MAIN_MAP)
    manifest = json.loads(LAYOUT.read_text(encoding="ascii"))
    static = static_contract(args.self_test_mutations)
    process, client = monitor.launch(args.xroar, args.rom, monitor.free_port())
    try:
        requests = bug018.initialize_navigation(
            monitor, client, presentation, args.timeout, args.mode, args.initial_owner
        )
        identity = bug018.artifact_identity(client, manifest)
        if args.scenario == "first-release":
            samples, frames, advances = capture_natural_release(
                monitor, client, bug018, main_symbols, enemy, args.timeout, args.mode
            )
            scenario_detail: dict[str, object] = {
                "natural": True, "timer_advances": advances,
                "committed_frames_per_advance": 9, "first_release_count": 1,
            }
        else:
            timer_id = set_breakpoint(client, main_symbols["perimeter_timer_tick"])
            hit = client.run_to_breakpoint(args.timeout)
            monitor.clear(client, [timer_id])
            if hit.get("pc") != main_symbols["perimeter_timer_tick"]:
                raise RuntimeError(f"initialized part-one marker missing: {hit}")
            bug018.capture_natural_animation(monitor, client, enemy, args.timeout)
            samples, frames, scenario_detail = capture_forced(
                monitor, client, bug018, enemy, args.timeout, args.scenario
            )
            scenario_detail["natural_part_one_initialization"] = True
        if read_byte(client, FB_WRITE_FRONT_FAULT) != 0:
            raise RuntimeError("runtime capture detected physical FRONT writes")
        write_montage(args.png, frames)
        offsets = sorted({sample["offset_scanlines"] for sample in samples})
        if offsets != [0, 2, 4, 6]:
            raise RuntimeError(f"phase offsets differ: {offsets}")
        evidence = {
            "schema": "ladybug-bug019-nest-exit-v1", "mode": args.mode,
            "initial_owner": args.initial_owner, "scenario": args.scenario,
            "phase_deadline_seconds": args.timeout,
            "success_markers": ["cold-attract", "initialized-part-one", "framebuffer-finish-back"],
            "timeout_meaning": "failure of the named observation boundary only",
            "screen_requests": requests, "rom_sha256": digest(args.rom.read_bytes()),
            "artifact_identity": identity, "static_oracle": static,
            "scenario_detail": scenario_detail, "samples": samples,
            "phase_offsets_scanlines": offsets,
            "compact_to_persistent_transition": "row 11 phase 3 to row 10 phase 0",
            "missing_frames": 0, "duplicated_frames": 0, "jump_scanlines": 0,
            "front_write_faults": 0, "png_sha256": digest(args.png.read_bytes()),
            "pass": True,
        }
        args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="ascii")
        print(f"BUG-019 pass: {args.mode} owner {args.initial_owner} {args.scenario}; "
              f"{len(samples)} committed positions, offsets {offsets}")
    finally:
        client.close()
        monitor.stop(process)
        process.wait(timeout=2)


if __name__ == "__main__":
    main()
