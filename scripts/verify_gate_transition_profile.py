#!/usr/bin/env python3
"""Verify generated gate-transition streams against controlled live traces."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
BUDGET = 29_666
PIVOT_FRAMEBUFFER = 0x2000 + 3 * 1280 + (5 + 8) * 4
TRACE_RE = re.compile(r"^[0-9a-f]{4}\|.* dt=(\d+)$")
REGISTER_RE = re.compile(r" a=([0-9a-f]{2}).* x=([0-9a-f]{4}) ")
MAP_RE = re.compile(r"^Symbol: (\w+) .* = ([0-9A-Fa-f]+)$")
BASELINE = {
    "A": {"frame_cycles": 36_738, "gate_cycles": 9_419},
    "B": {"frame_cycles": 46_131, "gate_cycles": 17_565},
}
BASELINE_ENTITY_FILTER_CYCLES = 569


def symbols() -> dict[str, str]:
    result = {}
    for line in (BUILD / "ladybug-enemy-runtime.map").read_text(
        encoding="utf-8"
    ).splitlines():
        match = MAP_RE.match(line)
        if match:
            result[match.group(1)] = match.group(2).lower().zfill(4)
    main_map = (BUILD / "ladybug.map").read_text(encoding="utf-8").splitlines()
    for line in main_map:
        match = MAP_RE.match(line)
        if match and match.group(1) == "dgt_store":
            result["dgt_store"] = f"{int(match.group(2), 16) + 2:04x}"
    required = {
        "frame_render_impl",
        "gate_compose_impl",
        "draw_gate_transition",
        "draw_gate_entities",
        "dgt_store",
    }
    missing = required - result.keys()
    if missing:
        raise ValueError("missing profile symbols: " + ", ".join(sorted(missing)))
    return result


def decode_stream(payload: bytes, stream_id: int) -> list[tuple[int, int]]:
    offsets = [
        int.from_bytes(payload[index:index + 2], "big")
        for index in range(0, 12, 2)
    ]
    start = offsets[stream_id]
    end = offsets[stream_id + 1] if stream_id < 5 else len(payload)
    stream = payload[start:end]
    cursor = 0
    destination = int.from_bytes(stream[0:2], "big", signed=True)
    cursor = 2
    writes = []
    while True:
        length = stream[cursor]
        cursor += 1
        if length == 0:
            raise ValueError(f"gate stream {stream_id} has a zero-length run")
        for _index in range(length):
            writes.append((PIVOT_FRAMEBUFFER + destination, stream[cursor]))
            destination += 1
            cursor += 1
        token = stream[cursor]
        cursor += 1
        if token == 0xFF:
            break
        if token == 0:
            delta = int.from_bytes(stream[cursor:cursor + 2], "big")
            cursor += 2
        else:
            delta = token
        if delta == 0:
            raise ValueError(f"gate stream {stream_id} does not advance")
        destination += delta
    if cursor != len(stream):
        raise ValueError(f"gate stream {stream_id} has trailing bytes")
    return writes


def call_segment(
    pcs: list[str], cycles: list[int], entry_pc: str
) -> tuple[int, int]:
    entry = pcs.index(entry_pc)
    call = entry - 1
    return_pc = f"{int(pcs[call], 16) + 3:04x}"
    end = next(
        index
        for index in range(entry + 1, len(pcs))
        if pcs[index] == return_pc
    )
    return end - call, sum(cycles[call:end])


def profile(
    owner: str, stream_id: int, names: dict[str, str], payload: bytes
) -> dict[str, object]:
    path = BUILD / f"gate-delta-owner-{owner.lower()}.trace"
    lines = [
        line
        for line in path.read_text(encoding="ascii").splitlines()
        if TRACE_RE.match(line)
    ]
    if not lines or not lines[0].startswith(names["frame_render_impl"] + "|"):
        raise ValueError(f"{path}: trace does not begin at frame_render_impl")
    cycles = [int(TRACE_RE.match(line).group(1)) // 8 for line in lines]
    cycles[0] = 9
    sync = {index for index, line in enumerate(lines) if "| 13 " in line}
    active_cycles = sum(cycles) - sum(cycles[index] for index in sync)
    pcs = [line[:4] for line in lines]

    expected_writes = decode_stream(payload, stream_id)
    live_writes = []
    for line in lines:
        if line.startswith(names["dgt_store"] + "|"):
            match = REGISTER_RE.search(line)
            if not match:
                raise ValueError(f"{path}: transition store lacks register state")
            value = int(match.group(1), 16)
            postincrement_x = int(match.group(2), 16)
            live_writes.append((postincrement_x - 1, value))
    if live_writes != expected_writes:
        raise ValueError(f"{path}: live transition writes differ from generated stream")

    gate_instructions, gate_cycles = call_segment(
        pcs, cycles, names["gate_compose_impl"]
    )
    transition_instructions, transition_cycles = call_segment(
        pcs, cycles, names["draw_gate_transition"]
    )
    entity_instructions, entity_cycles = call_segment(
        pcs, cycles, names["draw_gate_entities"]
    )
    projected_gate = (
        gate_cycles - entity_cycles + BASELINE_ENTITY_FILTER_CYCLES
    )
    baseline = BASELINE[owner]
    projected_frame = (
        baseline["frame_cycles"] - baseline["gate_cycles"] + projected_gate
    )
    return {
        "stream_id": stream_id,
        "writes": len(live_writes),
        "active_instructions": len(lines) - len(sync),
        "active_cycles": active_cycles,
        "gate_composition": {
            "instructions": gate_instructions,
            "cycles_with_live_overlapping_entity": gate_cycles,
            "transition_instructions": transition_instructions,
            "transition_cycles_with_entity": transition_cycles,
            "entity_filter_instructions": entity_instructions,
            "entity_filter_cycles": entity_cycles,
            "projected_like_for_like_cycles": projected_gate,
            "cycles_saved_vs_prior": baseline["gate_cycles"] - projected_gate,
        },
        "projected_four_enemy_frame": {
            "active_cycles": projected_frame,
            "budget_margin_cycles": BUDGET - projected_frame,
            "passes_strict_budget": projected_frame < BUDGET,
        },
    }


def digest(path: Path) -> str:
    data = path.read_bytes()
    if len(data) != 30_720:
        raise ValueError(f"{path}: framebuffer capture is {len(data)} bytes")
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    names = symbols()
    payload = (BUILD / "ladybug-gate-transitions.bin").read_bytes()
    if len(payload) != 832:
        raise ValueError("gate transition payload size changed")
    owners = {
        "A": profile("A", 2, names, payload),
        "B": profile("B", 5, names, payload),
    }
    captures = {
        name: digest(BUILD / f"gate-delta-{name}.bin")
        for name in ("before", "diagonal", "final")
    }
    if len(set(captures.values())) != 3:
        raise ValueError("controlled gate framebuffer captures did not change")
    report = {
        "captured": "2026-07-27",
        "hardware_budget_cycles": BUDGET,
        "scenario": (
            "live gate-0 horizontal-to-vertical transition; owner A diagonal "
            "style 0, owner B authoritative final; one overlapping static entity"
        ),
        "payload": {
            "bytes": len(payload),
            "streams": 6,
            "verified_generation_cases": 168,
            "format": (
                "signed initial destination; delta, run length, opaque bytes; "
                "0x00 extended delta; 0xFF end"
            ),
        },
        "owners": owners,
        "framebuffer_sha256": captures,
        "artifacts": {
            "owner_a_trace": "build/gate-delta-owner-a.trace",
            "owner_b_trace": "build/gate-delta-owner-b.trace",
            "before": "build/gate-delta-before.bin",
            "diagonal": "build/gate-delta-diagonal.bin",
            "final": "build/gate-delta-final.bin",
        },
    }
    (BUILD / "gate-transition-profile.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="ascii"
    )
    for owner, values in owners.items():
        gate = values["gate_composition"]
        projected = values["projected_four_enemy_frame"]
        print(
            f"gate delta {owner}: {values['writes']} live writes, "
            f"{gate['projected_like_for_like_cycles']} projected gate cycles, "
            f"{projected['active_cycles']} projected frame cycles"
        )


if __name__ == "__main__":
    main()
