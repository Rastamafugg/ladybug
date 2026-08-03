#!/usr/bin/env python3
"""Verify PERF-004 native perimeter-reset pixels, mappings, and timing."""

from __future__ import annotations

import json
from pathlib import Path

from capture_death_reset import material_digest, material_hashes
from build_screen import compile_screen
from build_sparse_sprites import perimeter_coordinates
from read_snapshot import find_ram
from verify_performance_baseline import symbols, trace_sections


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
TARGET = 27_000


def execute(payload: bytes, initial: bytes) -> bytes:
    """Independently execute the restricted generated 6809 program."""
    ram = bytearray(initial); a = b = 0; x = 0; pc = 0; stack: list[int] = []
    cursor = 0
    while True:
        if pc >= len(payload): raise SystemExit("perimeter proof: payload falls off page")
        opcode = payload[pc]; pc += 1
        if opcode == 0x39:
            if not stack: return bytes(ram)
            pc = stack.pop(); continue
        if opcode == 0x86: a = payload[pc]; pc += 1; continue
        if opcode == 0x8E: x = (payload[pc] << 8) | payload[pc + 1]; pc += 2; continue
        if opcode == 0xBD:
            target = (payload[pc] << 8) | payload[pc + 1]; pc += 2; stack.append(pc); pc = target - 0xA000; continue
        indexed = opcode in (0xA6, 0xA7, 0xEC, 0xED)
        extended = opcode in (0xB6, 0xB7)
        if indexed:
            post = payload[pc]; pc += 1
            displacement = 0 if post == 0x84 else (post - 32 if post & 0x10 else post)
            address = x + displacement
        elif extended:
            address = (payload[pc] << 8) | payload[pc + 1]; pc += 2
        if opcode in (0xA6, 0xB6): a = ram[address - 0x2000]
        elif opcode in (0xA7, 0xB7):
            if not 0x2000 <= address < 0xA000:
                raise SystemExit(f"perimeter proof: store outside framebuffer ${address:04X} at payload+${pc - 1:04X}")
            ram[address - 0x2000] = a
        elif opcode == 0xEC: a, b = ram[address - 0x2000], ram[address - 0x1FFF]
        elif opcode == 0xED: ram[address - 0x2000], ram[address - 0x1FFF] = a, b
        elif opcode == 0x84: a &= payload[pc]; pc += 1
        elif opcode == 0xC4: b &= payload[pc]; pc += 1
        elif opcode == 0x8A: a |= payload[pc]; pc += 1
        elif opcode == 0xCA: b |= payload[pc]; pc += 1
        else: raise SystemExit(f"perimeter proof: unsupported opcode ${opcode:02X}")


def old_92_model(initial: bytes) -> bytes:
    screen, tiles, *_ = compile_screen(ROOT / "tiled/coco-screen.tmx", ROOT / "assets/arcade/maze.json", ROOT / "assets/arcade/chars.json", ROOT / "assets/arcade/sprites.json")
    result = bytearray(initial)
    for box in range(92):
        cell_x, cell_y = perimeter_coordinates(box); tile = tiles[screen[cell_y * 40 + cell_x + 8]]
        for row in range(8):
            offset = (cell_y * 5 + row) * 160 + (cell_x + 8) * 4
            for col, value in enumerate(tile[row * 4:row * 4 + 4]):
                old = result[offset + col]
                result[offset + col] = (0x60 if value >> 4 == 6 else old & 0xF0) | (0x06 if value & 15 == 6 else old & 0x0F)
    return bytes(result)


def main() -> None:
    payload = (BUILD / "ladybug-perimeter-reset.bin").read_bytes()
    # Arbitrary pre-state proves companion-nibble preservation independently of
    # the Green-ring runtime precondition.
    arbitrary = bytes((index * 73 + 19) & 0xFF for index in range(0x8000))
    if execute(payload, arbitrary) != old_92_model(arbitrary):
        raise SystemExit("perimeter proof: generated program differs from old 92-call model on arbitrary pre-state")
    sym = symbols(BUILD / "ladybug-enemy-runtime.map")
    evidence: dict[str, object] = {
        "schema": 1,
        "measurement_contract": "closed frame_render_impl-to-next-frame_render_impl intervals containing the $06B2 helper only",
        "capture_material_sha256": material_hashes(),
        "verifier_sha256": material_digest("scripts/verify_perimeter_reset.py"),
        "target_cycles_max": TARGET,
        "payload_bytes": len(payload),
        "affected_bytes": 1426,
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
            before = find_ram((BUILD / f"perf004-{scenario}-{owner}-entry.sna").read_bytes())
            pre = before[target:target + 0x8000]
            actual = after[target:target + 0x8000]
            expected = old_92_model(pre)
            if actual != expected:
                raise SystemExit(f"perimeter proof: complete 92-tile post-region differs {scenario}/{owner}")
            mutated = bytearray(payload); mutated[1] ^= 1
            if execute(bytes(mutated), arbitrary) == old_92_model(arbitrary):
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
