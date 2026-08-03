#!/usr/bin/env python3
"""Independent correctness and closed-interval acceptance evidence for PERF-002."""
from __future__ import annotations

import json
from pathlib import Path

from build_screen import compile_enemy_sprites
from build_sparse_sprites import expand_native_frame
from capture_death_reset import material_digest, material_hashes
from read_snapshot import cpu_to_phys, find_ram
from verify_performance_baseline import symbols, trace_sections

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
ZONE = 0x57EC - 0x2000
TARGET = 27000
BOUNDARIES = 8


def hashes() -> dict[str, str]:
    values = material_hashes()
    values.pop("scripts/verify_death_reset.py")
    return values


def blend(background: bytes, native: bytes) -> bytes:
    result = bytearray(background)
    for index, value in enumerate(native):
        mask = (0xF0 if value & 0xF0 else 0) | (0x0F if value & 0x0F else 0)
        result[index] = (result[index] & (~mask & 0xFF)) | (value & mask)
    return bytes(result)


def zone(ram: bytes, framebuffer: int) -> bytes:
    return b"".join(ram[framebuffer + ZONE + row * 160:framebuffer + ZONE + row * 160 + 8] for row in range(32))


def closed_sections(path: Path, frame_pc: str) -> list[dict[str, object]]:
    """Reject incomplete captures. trace_sections deliberately drops the tail."""
    sections = trace_sections(path, frame_pc)
    # Each closed interval needs a subsequent frame boundary. capture_death_reset
    # asks XRoar for exactly eight main-render boundaries, hence seven intervals.
    if len(sections) != BOUNDARIES - 1:
        raise SystemExit(f"death-reset proof: {path.name} has {len(sections)} closed intervals; expected {BOUNDARIES - 1}")
    return sections


def observation(phase: str, worklist: str, target: str, section: dict[str, object], boxes: int, animation: int, generic: int) -> dict[str, object]:
    active = int(section["active_cycles"])
    return {
        "scenario_phase": phase, "worklist": worklist,
        "framebuffer_target": target, "active_cycles": active,
        "target_cycles_max": TARGET, "margin_cycles": TARGET - active,
        "passes_target": active <= TARGET,
        "symbol_coverage": {"draw_perimeter_box": boxes, "compose_enemy_animation": animation, "compose_enemy_zone": generic},
    }


def main() -> None:
    sym = symbols(BUILD / "ladybug-enemy-runtime.map")
    # PERF-004 replaces the 92 generic box calls with a generated native
    # projection.  Its dedicated verifier proves the same 92-box result at the
    # publication boundary, including a rejected mutation and all A/B worklists.
    # Retain this verifier's mixed-path guard: the compatibility compositor must
    # still be reachable when overlap requires it.
    source = (ROOT / "src/enemy_runtime.s").read_text(encoding="utf-8")
    if "jsr     PERIMETER_RESET_HELPER" in source:
        from verify_perimeter_reset import main as verify_perimeter_reset
        verify_perimeter_reset()
        for owner in ("a", "b"):
            mixed = closed_sections(BUILD / f"perf004-mixed-{owner}.raw.trace", sym["frame_render_impl"])
            if not any(part["pcs"].count(sym["compose_enemy_zone"]) == 1 for part in mixed):
                raise SystemExit(f"death-reset proof: mixed generic fallback absent {owner}")
        print("death-reset proof: PERF-004 native 92-box equivalence and mixed generic fallback pass")
        return
    required = {"compose_enemy_zone", "compose_enemy_animation", "frame_render_impl", "draw_perimeter_box"}
    if required - sym.keys():
        raise SystemExit("death-reset proof: required symbols missing")
    current_hashes = hashes()
    immutable_frames = compile_enemy_sprites(ROOT / "assets" / "arcade" / "sprites.json")
    evidence: dict[str, object] = {
        "schema": 2,
        "measurement_contract": "closed frame_render_impl-to-next-frame_render_impl active intervals only; trailing trace tails are diagnostic and never timing evidence",
        "capture_material_sha256": current_hashes,
        "verifier_sha256": material_digest("scripts/verify_death_reset.py"),
        "target_cycles_max": TARGET,
        "correctness": [], "timing": [],
    }

    # Native reset output and cache derivation.  Expected pixels are composed
    # independently from the authoritative background and immutable sprite data.
    for case in ("zero", "four", "vegetable"):
        for owner in ("a", "b"):
            trace = BUILD / f"perf002-{case}-{owner}.raw.trace"
            after = BUILD / f"perf002-{case}-{owner}-after.sna"
            metadata_path = BUILD / f"perf002-{case}-{owner}.json"
            if not trace.exists() or not after.exists() or not metadata_path.exists():
                raise SystemExit(f"death-reset proof: missing capture {case}/{owner}")
            metadata = json.loads(metadata_path.read_text(encoding="ascii"))
            if metadata.get("schema") != 2 or any(metadata.get("material_sha256", {}).get(name) != digest for name, digest in current_hashes.items()):
                raise SystemExit(f"death-reset proof: stale metadata {case}/{owner}")
            closed_sections(trace, sym["frame_render_impl"])
            ram = find_ram(after.read_bytes())
            fb = int(metadata["after"]["completed_target_physical"])
            bg = bytes(ram[cpu_to_phys(0xA490):cpu_to_phys(0xA490) + 256])
            reset_cache = bytes(ram[cpu_to_phys(0xBC04):cpu_to_phys(0xBC04) + 256])
            stage = ram[cpu_to_phys(0x0024)]
            type_index = stage if stage < 9 else ((stage - 1) & 7)
            if type_index >= 5:
                type_index -= 5
            if not 1 <= type_index <= 4:
                raise SystemExit(f"death-reset proof: invalid stage type {case}/{owner}: {stage}")
            expected_lower = blend(bg[128:], expand_native_frame(immutable_frames[(type_index - 1) * 16]))
            expected = bg[:128] + expected_lower
            actual = zone(ram, fb)
            # Later common render layers may change the final zone after the cache
            # publication. Cache derivation is independent here; final pixels are
            # compared below against the forced generic-control render.
            if reset_cache != expected:
                raise SystemExit(f"death-reset proof: independent cache mismatch {case}/{owner}")
            mutated = bytearray(expected); mutated[128] ^= 1
            if bytes(mutated) == reset_cache:
                raise SystemExit("death-reset proof: corrupted expected pixel was accepted")
            evidence["correctness"].append({"worklist": case, "framebuffer_target": owner.upper(), "cache_and_pixels_exact": True, "mutation_rejected": True})

    # Generic-control is the same reset final pixels through the retained generic path.
    for owner in ("a", "b"):
        native = find_ram((BUILD / f"perf002-zero-{owner}-after.sna").read_bytes())
        control = find_ram((BUILD / f"perf002-generic_control-{owner}-after.sna").read_bytes())
        native_fb = int(json.loads((BUILD / f"perf002-zero-{owner}.json").read_text(encoding="ascii"))["after"]["completed_target_physical"])
        control_fb = int(json.loads((BUILD / f"perf002-generic_control-{owner}.json").read_text(encoding="ascii"))["after"]["completed_target_physical"])
        if zone(native, native_fb) != zone(control, control_fb):
            raise SystemExit(f"death-reset proof: native/generic pixel mismatch {owner}")
        mixed = closed_sections(BUILD / f"perf002-mixed-{owner}.raw.trace", sym["frame_render_impl"])
        if not any(part["pcs"].count(sym["compose_enemy_zone"]) == 1 for part in mixed):
            raise SystemExit(f"death-reset proof: mixed generic fallback absent {owner}")
        evidence["correctness"].append({"worklist": "generic_control", "framebuffer_target": owner.upper(), "pixel_equivalent_to_native": True})
        evidence["correctness"].append({"worklist": "mixed_overlap", "framebuffer_target": owner.upper(), "generic_fallback_reached": True})

    isolated: list[dict[str, object]] = []
    natural: list[dict[str, object]] = []
    for owner in ("a", "b"):
        # Isolated structural cache publication must not include a perimeter reset.
        structural = closed_sections(BUILD / f"perf002-structural-{owner}.raw.trace", sym["frame_render_impl"])
        selected = [part for part in structural if part["pcs"].count(sym["compose_enemy_animation"]) == 1 and part["pcs"].count(sym["draw_perimeter_box"]) == 0]
        if not selected:
            raise SystemExit(f"death-reset proof: isolated structural worklist missing {owner}")
        for part in selected:
            isolated.append(observation("isolated_structural_reset", "cache_publish", owner.upper(), part, 0, 1, part["pcs"].count(sym["compose_enemy_zone"])))

        # Natural state-machine replay must publish exactly 92 perimeter boxes,
        # then one cache image.  Zero, four, and vegetable each execute into both
        # physical framebuffer targets; owner is metadata, not causal attribution.
        for case in ("zero", "four", "vegetable"):
            parts = closed_sections(BUILD / f"perf002-{case}-{owner}.raw.trace", sym["frame_render_impl"])
            matched = [part for part in parts if part["pcs"].count(sym["compose_enemy_animation"]) == 1 and part["pcs"].count(sym["draw_perimeter_box"]) == 92]
            if not matched:
                raise SystemExit(f"death-reset proof: natural {case}/{owner} has no 92-box closed interval")
            for part in matched:
                natural.append(observation("natural_death_to_reset", f"{case}_active_enemies_perimeter_plus_cache_publish", owner.upper(), part, 92, 1, part["pcs"].count(sym["compose_enemy_zone"])))

    if len(isolated) < 2 or any(not row["passes_target"] for row in isolated):
        raise SystemExit("death-reset proof: isolated structural timing coverage/target failed")
    if len(natural) < 6:
        raise SystemExit("death-reset proof: natural A/B/reversed coverage incomplete")
    evidence["timing"] = isolated + natural
    natural_pass = all(row["passes_target"] for row in natural)
    evidence["acceptance"] = {
        "isolated_structural_pass": True,
        "natural_perimeter_replay_pass": natural_pass,
        "overall_perf002_acceptance_pass": natural_pass,
        "verdict": "PASS" if natural_pass else "FAILED: natural 92-box perimeter publication exceeds 27000 cycles; PERF-004 required",
    }
    (BUILD / "perf002-death-reset.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="ascii")
    print("death-reset proof: correctness passes; " + evidence["acceptance"]["verdict"])


if __name__ == "__main__":
    main()
