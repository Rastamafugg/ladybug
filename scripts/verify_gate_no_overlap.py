#!/usr/bin/env python3
"""Fail unless a forced zero-association gate worklist is complete and in budget."""
import json
from pathlib import Path
from verify_gate_performance import sections, symbols

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
TARGET = 27000
meta = json.loads((BUILD / "gate-no-overlap.json").read_text(encoding="ascii"))
if meta["association_count"] != 0:
    raise SystemExit("no-overlap proof: selected gate is not zero-association")
enemy = symbols(BUILD / "ladybug-enemy-runtime.map")
resident = symbols(BUILD / "ladybug.map")
names = {**resident, **enemy}
parts = sections(BUILD / "perf-gate-no-overlap.raw.trace", names["frame_render_impl"])
if not parts:
    raise SystemExit("no-overlap proof: missing complete worklist")
lines, cycles = parts[0]
active = sum(cycle for line, cycle in zip(lines, cycles) if "| 13 " not in line)
if active > TARGET:
    raise SystemExit(f"no-overlap proof: {active} exceeds {TARGET}")
if sum(line.startswith(names["draw_gate_entities"] + "|") for line in lines) != 1:
    raise SystemExit("no-overlap proof: bounded selector did not execute once")
if any(line.startswith(names["replay_gate_entity_overlay"] + "|") for line in lines):
    raise SystemExit("no-overlap proof: cached entity replay ran despite zero association count")
report = {"gate_id": meta["gate_id"], "association_count": 0, "active_cycles": active,
          "target_cycles": TARGET, "passes_target": True,
          "pixel_evidence": "generated transition stream is used; no entity replay executed"}
(BUILD / "gate-no-overlap.json").write_text(json.dumps(report, indent=2) + "\n", encoding="ascii")
print(json.dumps(report))
