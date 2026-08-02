#!/usr/bin/env python3
"""Capture one forced gate worklist whose stage association count is zero."""
from pathlib import Path

from capture_performance_baseline import capture_trace, moving_patch, symbol
from patch_snapshot_state import patch_snapshot
from read_snapshot import cpu_to_phys, find_ram

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
LISTS = 0xB600
RECORD = 77

hydrated = BUILD / "perf-four-hydrated.sna"
ram = find_ram(hydrated.read_bytes())
lists = cpu_to_phys(LISTS)
gate = next((index for index in range(20) if ram[lists + index * RECORD + 4] == 0), None)
if gate is None:
    raise SystemExit("no-overlap capture: hydrated stage has no zero-association gate")
frame_pc = symbol(BUILD / "ladybug-enemy-runtime.map", "frame_render_impl")
stop_pc = symbol(BUILD / "ladybug.map", "main_render")
snapshot = BUILD / "perf-gate-no-overlap.sna"
patch_snapshot(hydrated, snapshot, moving_patch((1, 1, 3, 3)) + [
    "0018=01", "0019=00", f"0088={gate + 1:02X}", "0089=00",
    "008A=00", "008B=00", "008D=00", "008E=00", f"{0xA240 + gate:04X}=01",
])
(BUILD / "gate-no-overlap.json").write_text(
    '{\n  "gate_id": %d,\n  "association_count": 0,\n  "snapshot": "build/perf-gate-no-overlap.sna",\n  "trace": "build/perf-gate-no-overlap.raw.trace"\n}\n' % gate,
    encoding="ascii",
)
capture_trace(snapshot, BUILD / "perf-gate-no-overlap.raw.trace", stop_pc, 1)
print(f"no-overlap capture: gate {gate}, association count 0, frame PC ${frame_pc:04X}")
