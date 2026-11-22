#!/usr/bin/env python3
"""Verify current-address complete gate intervals and report attribution."""

from __future__ import annotations

import json
import hashlib
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
BASELINE = {"diagonal/current": 32835, "final/pending projection": 36837}
TARGET = 27000
TRACE_PREFIX_RE = re.compile(r"^[0-9A-Fa-f]{4}\|")
# XRoar uses fixed-width byte and mnemonic columns before its trailing dt field.
# Keep the padding in the row body; a non-greedy split can consume the mnemonic
# column's trailing spaces as the dt separator and truncate short mnemonics.
TRACE_ROW_RE = re.compile(r"^([0-9A-Fa-f]{4})\|(.+)\s+dt=(-?\d+)\s*$")
TRACE_BYTES_RE = re.compile(r"^(?:[0-9A-Fa-f]{2})+$")
TRACE_MNEMONIC_RE = re.compile(r"^(?:[A-Za-z][A-Za-z0-9]*|\*)$")
TRACE_VECTOR_RE = re.compile(r"^\[(?:\?|SWI3|SWI2|FIRQ|IRQ|SWI|NMI|RESET)\]$")
LISTING_ROW_RE = re.compile(
    r"^([0-9A-Fa-f]{4})\s+([0-9A-Fa-f]{2,})\s+\([^)]*\):(\d+)\s+(.*)$"
)
MAP_RE = re.compile(r"^Symbol: (\w+) .* = ([0-9A-Fa-f]+)$")
EVENT_TICKS_PER_FAST_CYCLE = 8
SYNC_MINIMUM_ACTIVE_CYCLES = 4


@dataclass(frozen=True)
class TraceRow:
    line: str
    pc: str
    code: str
    mnemonic: str
    delta: int


def trace_fields(body: str) -> tuple[str, str]:
    start = len(body) - len(body.lstrip())
    match = re.match(r"[0-9A-Fa-f]+", body[start:])
    if not match:
        raise ValueError("trace row has no hexadecimal instruction/vector bytes")
    code = match.group(0).lower()
    if len(code) % 2 or len(code) > 16:
        raise ValueError("trace row has an invalid byte-string length")
    name_start = start + max(12, len(code))
    if len(body) < name_start + 6:
        raise ValueError("trace row is missing its instruction/vector name")
    name_field = body[name_start:name_start + 24].strip()
    mnemonic = (
        name_field
        if name_field.startswith("[")
        else body[name_start:name_start + 6].strip().upper()
    )
    return code, mnemonic


def symbols(path: Path) -> dict[str, str]:
    result = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = MAP_RE.match(line)
        if match:
            result[match.group(1)] = match.group(2).lower().zfill(4)
    return result


def timed_rows(path: Path) -> list[TraceRow]:
    rows = []
    for number, line in enumerate(path.read_text(encoding="ascii").splitlines(), 1):
        match = TRACE_ROW_RE.fullmatch(line)
        if not match:
            if TRACE_PREFIX_RE.match(line) or "dt=" in line:
                raise ValueError(f"{path}:{number}: malformed timed trace row: {line!r}")
            continue

        pc, body, raw_delta = match.groups()
        try:
            code, mnemonic = trace_fields(body)
        except ValueError as error:
            raise ValueError(f"{path}:{number}: {error}: {line!r}") from error
        if not TRACE_BYTES_RE.fullmatch(code):
            raise ValueError(f"{path}:{number}: malformed instruction/vector bytes: {line!r}")
        if not (TRACE_MNEMONIC_RE.fullmatch(mnemonic) or TRACE_VECTOR_RE.fullmatch(mnemonic)):
            raise ValueError(f"{path}:{number}: malformed instruction/vector name: {line!r}")
        is_vector = TRACE_VECTOR_RE.fullmatch(mnemonic) is not None
        if mnemonic == "SYNC" and code != "13":
            raise ValueError(f"{path}:{number}: SYNC row has unexpected opcode {code}")
        if code == "13" and not is_vector and mnemonic != "SYNC":
            raise ValueError(f"{path}:{number}: opcode 13 is not labeled SYNC")
        delta = int(raw_delta)
        if not -(1 << 31) <= delta < (1 << 31):
            raise ValueError(f"{path}:{number}: timed delta is outside XRoar's signed range")
        rows.append(TraceRow(line, pc.lower(), code, mnemonic, delta))
    if not rows:
        raise ValueError(f"{path}: trace contains no timing events")
    return rows


def listing_call_bytes(path: Path, pc: int, target: int) -> str:
    matches = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = LISTING_ROW_RE.match(line)
        if not match:
            continue
        address, code, _, source = match.groups()
        fields = source.strip().split(None, 1)
        if int(address, 16) != pc or len(fields) != 2:
            continue
        mnemonic, operand = fields
        if mnemonic.lower() == "jsr" and operand.split(";", 1)[0].strip().upper() == "AD_WORK_EXEC":
            matches.append(code.lower())
    expected = f"bd{target:04x}"
    if matches != [expected]:
        raise ValueError(
            f"{path}: expected one JSR AD_WORK_EXEC at {pc:04x} with bytes {expected}, found {matches}"
        )
    return expected


def sections(
    path: Path,
    frame_pc: str,
    expected_count: int | None = None,
    frame_bytes: str | None = None,
) -> list[tuple[list[str], list[int]]]:
    rows = timed_rows(path)
    if rows[0].pc != frame_pc.lower():
        raise ValueError(f"{path}: trace opens at {rows[0].pc}, expected {frame_pc}")
    if frame_bytes is not None:
        if rows[0].code != frame_bytes.lower() or rows[0].mnemonic != "JSR":
            raise ValueError(
                f"{path}: opening row is {rows[0].pc}|{rows[0].code} {rows[0].mnemonic}; "
                f"expected {frame_pc}|{frame_bytes} JSR"
            )
    for index, row in enumerate(rows[1:], 1):
        if row.delta < 0:
            raise ValueError(f"{path}: negative timed delta after the opening row at event {index}")
        if row.delta % EVENT_TICKS_PER_FAST_CYCLE:
            raise ValueError(
                f"{path}: event {index} delta {row.delta} is not an integral fast CPU cycle"
            )

    starts = [index for index, row in enumerate(rows) if row.pc == frame_pc.lower()]
    if not starts or starts[0] != 0:
        raise ValueError(f"{path}: trace does not start at {frame_pc}")
    if frame_bytes is not None and any(
        rows[index].code != frame_bytes.lower() or rows[index].mnemonic != "JSR"
        for index in starts
    ):
        raise ValueError(f"{path}: a frame boundary does not match the emitted {frame_bytes} JSR")
    if starts[-1] != len(rows) - 1:
        raise ValueError(f"{path}: trace ends after its last complete-frame boundary")

    actual_count = len(starts) - 1
    if actual_count < 1:
        raise ValueError(f"{path}: trace has no closed intervals")
    if expected_count is not None and actual_count != expected_count:
        raise ValueError(
            f"{path}: expected {expected_count} closed intervals, found {actual_count}"
        )

    all_cycles = [row.delta // EVENT_TICKS_PER_FAST_CYCLE for row in rows]
    # XRoar's first delta is invalid. The marker is a verified extended JSR,
    # whose exact eight-cycle cost replaces that invalid timestamp interval.
    if rows[0].mnemonic != "JSR" or not rows[0].code.startswith("bd") or len(rows[0].code) != 6:
        raise ValueError(f"{path}: cannot reconstruct opening cycle cost from {rows[0].code} {rows[0].mnemonic}")
    if frame_bytes is not None and rows[0].code != frame_bytes.lower():
        raise ValueError(f"{path}: opening JSR bytes do not match the current listing")
    all_cycles[0] = 8
    result = []
    for position in range(actual_count):
        start = starts[position]
        end = starts[position + 1]
        result.append(([row.line for row in rows[start:end]], all_cycles[start:end]))
    return result


def active_cycle_values(lines: list[str], elapsed_cycles: list[int]) -> tuple[list[int], int]:
    """Keep SYNC's four active instruction cycles and remove only its wait."""
    if len(lines) != len(elapsed_cycles):
        raise ValueError("trace rows and cycle values have different lengths")
    active = []
    sync_wait = 0
    for line, cycles in zip(lines, elapsed_cycles):
        row = timed_rows_from_line(line)
        if row.mnemonic == "SYNC":
            if cycles < SYNC_MINIMUM_ACTIVE_CYCLES:
                raise ValueError(
                    f"SYNC row at {row.pc} has {cycles} cycles; minimum is "
                    f"{SYNC_MINIMUM_ACTIVE_CYCLES}"
                )
            sync_wait += cycles - SYNC_MINIMUM_ACTIVE_CYCLES
            active.append(SYNC_MINIMUM_ACTIVE_CYCLES)
        else:
            active.append(cycles)
    return active, sync_wait


def timed_rows_from_line(line: str) -> TraceRow:
    match = TRACE_ROW_RE.fullmatch(line)
    if not match:
        raise ValueError(f"malformed timed trace row: {line!r}")
    pc, body, raw_delta = match.groups()
    code, mnemonic = trace_fields(body)
    return TraceRow(line, pc.lower(), code, mnemonic, int(raw_delta))


def calls(lines: list[str], cycles: list[int], entry: str) -> list[int]:
    pcs = [line[:4].lower() for line in lines]
    result = []
    for index, pc in enumerate(pcs):
        if pc != entry or index == 0:
            continue
        return_pc = f"{int(pcs[index - 1], 16) + 3:04x}"
        try:
            end = pcs.index(return_pc, index + 1)
        except ValueError:
            continue
        result.append(sum(cycles[index - 1:end]))
    return result


def main() -> None:
    # Raw traces are intentionally untracked.  Require them to be newer than
    # the maps from which their PCs are decoded; retained JSON need not share
    # HEAD because verification itself regenerates that evidence.
    maps = [BUILD / "ladybug.map", BUILD / "ladybug-enemy-runtime.map"]
    for trace in (BUILD / "perf-gate.raw.trace", BUILD / "perf-gate-reversed.raw.trace"):
        if not trace.exists() or trace.stat().st_mtime < max(path.stat().st_mtime for path in maps):
            raise SystemExit("gate performance: capture current traces first: python scripts/capture_performance_baseline.py --skip-build --gate-only")
    resident = symbols(BUILD / "ladybug.map")
    enemy = symbols(BUILD / "ladybug-enemy-runtime.map")
    frame_pc = resident.get("ad_dispatch_work")
    if frame_pc is None:
        raise ValueError("resident map is missing the active ad_dispatch_work marker")
    names = {**resident, **enemy}
    wanted = (
        "framebuffer_prepare_back", "actor_closure_restore",
        "framebuffer_project_damage", "frame_render_background",
        "gate_compose_impl", "draw_gate_transition", "draw_gate_entities",
        "mark_gate_enemy_overlap", "actor_closure_draw", "rub_full",
        "rub_horizontal", "rub_vertical", "draw_enemy_fb",
    )
    active_entry_pc = resident.get("AD_WORK_EXEC")
    if active_entry_pc is None:
        raise ValueError("resident map is missing AD_WORK_EXEC")
    frame_bytes = listing_call_bytes(
        BUILD / "ladybug.lst", int(frame_pc, 16), int(active_entry_pc, 16)
    )

    report = []
    intervals = sections(
        BUILD / "perf-gate.raw.trace",
        frame_pc,
        expected_count=2,
        frame_bytes=frame_bytes,
    )
    phases = ("diagonal/current", "final/pending projection")
    owners = ("A", "B")
    for index, (lines, cycle_values) in enumerate(intervals):
        phase = phases[index]
        owner = owners[index]
        active_values, sync_wait = active_cycle_values(lines, cycle_values)
        item = {
            "phase": phase,
            "worklist": phase,
            "framebuffer_target": owner,
            "active_cycles": sum(active_values),
            "sync_wait_cycles_excluded": sync_wait,
        }
        item["calls"] = {
            name: {"count": len(values), "cycles": values}
            for name in wanted
            if (values := calls(lines, active_values, names[name]))
        }
        item["baseline_cycles"] = BASELINE[phase]
        item["improvement_cycles"] = BASELINE[phase] - item["active_cycles"]
        item["target_margin_cycles"] = TARGET - item["active_cycles"]
        item["passes_target"] = item["active_cycles"] <= TARGET
        if item["calls"].get("gate_compose_impl", {}).get("count") != 1:
            raise ValueError(f"owner {owner} did not coalesce to one gate composition")
        if item["calls"].get("draw_gate_entities", {}).get("count") != 1:
            raise ValueError(f"owner {owner} did not use bounded entity selection")
        report.append(item)
    reversed_report = []
    reversed_intervals = sections(
        BUILD / "perf-gate-reversed.raw.trace",
        frame_pc,
        expected_count=2,
        frame_bytes=frame_bytes,
    )
    reversed_targets = ("B", "A")
    for index, (lines, cycle_values) in enumerate(reversed_intervals):
        phase = phases[index]
        target = reversed_targets[index]
        active_values, sync_wait = active_cycle_values(lines, cycle_values)
        item = {
            "phase": phase,
            "worklist": phase,
            "framebuffer_target": target,
            "starting_owner": "reversed (front=A, back=B)",
            "active_cycles": sum(active_values),
            "sync_wait_cycles_excluded": sync_wait,
        }
        item["calls"] = {
            name: {"count": len(values), "cycles": values}
            for name in wanted
            if (values := calls(lines, active_values, names[name]))
        }
        item["target_margin_cycles"] = TARGET - item["active_cycles"]
        item["passes_target"] = item["active_cycles"] <= TARGET
        if item["calls"].get("gate_compose_impl", {}).get("count") != 1:
            raise ValueError(f"reversed {phase} did not coalesce to one gate composition")
        if item["calls"].get("draw_gate_entities", {}).get("count") != 1:
            raise ValueError(f"reversed {phase} did not use bounded entity selection")
        reversed_report.append(item)
    payload = BUILD / "ladybug-gate-transitions.bin"
    if payload.stat().st_size != 832:
        raise ValueError("generated six-stream gate payload changed size")
    output = {
        "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "baseline_revision": "82e1524",
        "baseline_artifact": "historical gate attribution capture",
        "material_sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in ("src/main.s", "src/enemy_runtime.s", "scripts/verify_gate_performance.py")},
        "measurement_contract": (
            "closed ad_dispatch_work-to-next-ad_dispatch_work active interval; "
            "the first invalid timing delta is replaced by the verified extended JSR cost; "
            "vector rows are counted; SYNC keeps its four instruction cycles and excludes only "
            "the additional wait cycles; symbols and opening bytes are checked against the "
            "resident map and listing"
        ),
        "scenario": (
            "gate-0 diagonal on A, alternate-owner final projection on B; "
            "four horizontal enemies and one bounded overlapping static entity"
        ),
        "generated_cases": 168,
        "payload_bytes": payload.stat().st_size,
        "payload_sha256": hashlib.sha256(payload.read_bytes()).hexdigest(),
        "target_cycles": TARGET,
        "target_met": (
            len(report) == 2
            and len(reversed_report) == 2
            and all(item["passes_target"] for item in report + reversed_report)
        ),
        "worklists": report,
        "reversed_start_owner": reversed_report,
        "reversed_start_trace": "build/perf-gate-reversed.raw.trace",
    }
    (BUILD / "gate-performance.json").write_text(
        json.dumps(output, indent=2) + "\n", encoding="ascii"
    )
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
