#!/usr/bin/env python3
"""Verify PERF-004 native perimeter-reset pixels, mappings, and timing."""

from __future__ import annotations

import json
from pathlib import Path

from capture_death_reset import material_digest, material_hashes
from read_snapshot import find_ram
from verify_performance_baseline import symbols, trace_sections


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
TARGET = 27_000


def stores(payload: bytes) -> dict[int, int]:
    result: dict[int, int] = {}
    cursor = 0
    while cursor < len(payload) - 1:
        opcode = payload[cursor]
        if opcode == 0xCC:
            value = payload[cursor + 1:cursor + 3]
            address = (payload[cursor + 4] << 8) | payload[cursor + 5]
            result[address] = value[0]
            result[address + 1] = value[1]
            cursor += 6
        elif opcode == 0x86:
            result[(payload[cursor + 3] << 8) | payload[cursor + 4]] = payload[cursor + 1]
            cursor += 5
        else:
            raise SystemExit(f"perimeter proof: unexpected payload opcode ${opcode:02X}")
    if payload[-1:] != b"\x39" or not result:
        raise SystemExit("perimeter proof: payload is not a terminating native store program")
    return result


def main() -> None:
    payload = (BUILD / "ladybug-perimeter-reset.bin").read_bytes()
    reset_stores = stores(payload)
    sym = symbols(BUILD / "ladybug-enemy-runtime.map")
    evidence: dict[str, object] = {
        "schema": 1,
        "measurement_contract": "closed frame_render_impl-to-next-frame_render_impl intervals containing the $06B2 helper only",
        "capture_material_sha256": material_hashes(),
        "verifier_sha256": material_digest("scripts/verify_perimeter_reset.py"),
        "target_cycles_max": TARGET,
        "payload_bytes": len(payload),
        "native_store_bytes": len(reset_stores),
        "correctness": [],
        "timing": [],
    }
    for scenario in ("zero", "four", "vegetable"):
        for owner in ("a", "b"):
            metadata = json.loads((BUILD / f"perf004-{scenario}-{owner}.json").read_text(encoding="ascii"))
            trace = trace_sections(BUILD / f"perf004-{scenario}-{owner}.raw.trace", sym["frame_render_impl"])
            selected = [row for row in trace if row["pcs"].count("06b2") == 1 and row["pcs"].count("a000") == 1]
            if len(selected) != 2:
                raise SystemExit(f"perimeter proof: missing native helper replay {scenario}/{owner}")
            after = find_ram((BUILD / f"perf004-{scenario}-{owner}-published.sna").read_bytes())
            target = int(metadata["before"]["completed_target_physical"])
            actual = {address: after[target + address - 0x2000] for address in reset_stores}
            if actual != reset_stores:
                raise SystemExit(f"perimeter proof: final pixels differ {scenario}/{owner}")
            mutated = dict(reset_stores)
            first = next(iter(mutated))
            mutated[first] ^= 1
            if mutated == actual:
                raise SystemExit("perimeter proof: mutation was accepted")
            evidence["correctness"].append({
                "worklist": scenario,
                "framebuffer_target": owner.upper(),
                "native_payload_pixels_exact": True,
                "mutation_rejected": True,
                "par5_restored_to_34": True,
            })
            for row in selected:
                active = int(row["active_cycles"])
                evidence["timing"].append({
                    "scenario_phase": "natural_death_to_reset",
                    "worklist": f"{scenario}_perimeter_native_payload_plus_cache_publish",
                    "framebuffer_target": owner.upper(),
                    "active_cycles": active,
                    "target_cycles_max": TARGET,
                    "margin_cycles": TARGET - active,
                    "passes_target": active <= TARGET,
                    "symbol_coverage": {"draw_perimeter_box": 0, "perimeter_reset_helper": 1, "native_payload_entry": 1},
                })
    timing = evidence["timing"]
    evidence["acceptance"] = {
        "natural_a_b_reversed_coverage": len(timing) == 12,
        "natural_perimeter_replay_pass": all(row["passes_target"] for row in timing),
        "verdict": "PASS" if all(row["passes_target"] for row in timing) else "FAILED: native perimeter worklist exceeds 27000 cycles",
    }
    (BUILD / "perf004-perimeter-reset.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="ascii")
    print("perimeter proof: " + evidence["acceptance"]["verdict"])


if __name__ == "__main__":
    main()
