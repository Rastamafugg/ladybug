#!/usr/bin/env python3
"""Compare verified pre-cleanup and current C3 high-score cold-frame crops."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = Path(__file__).resolve().parents[7]
PRE = ROOT / "build"
C3 = ROOT / "worktrees/menu-name-prep/build"
EXPECTED_PRE_ROM = "b452413b9e2d0e4d6e57e87a63d22b44ffed2a4cbb87c3c9c9e07a5d81992b55"
EXPECTED_C3_ROM = "e3a6cb1c9b9c3d959bc911433aea2b681b22a06608eeee40c8b9c14fae2f7982"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_static():
    path = HERE / "bug100_logo_r_composition_probe.py"
    spec = importlib.util.spec_from_file_location("bug100_static", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load existing SharedText/cold-frame decoder")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def decode(static, build: Path) -> dict:
    receipt = json.loads((build / "source-build-receipt.json").read_text(encoding="utf-8"))
    artifact_checks = {}
    for name in ("ladybug.rom", "ladybug-presentation-cold.bin", "ladybug_shared_text.inc"):
        expected = receipt["artifacts"][name]
        actual = sha((build / name).read_bytes())
        artifact_checks[name] = {"expected": expected, "actual": actual, "matches": expected == actual}
        if expected != actual:
            raise RuntimeError(f"receipt artifact mismatch: {build}/{name}")
    manifest = json.loads((build / "ladybug-presentation.json").read_text(encoding="utf-8"))
    cold = (build / "ladybug-presentation-cold.bin").read_bytes()
    if sha(cold) != manifest["cold_payload"]["sha256"]:
        raise RuntimeError(f"manifest cold-payload digest mismatch: {build}")
    include = (build / "ladybug_shared_text.inc").read_text(encoding="utf-8")
    font = static.include_bytes(include, "font", "colour_lut")
    index = next(i for i, record in enumerate(manifest["maps"]) if record["name"] == "high-score")
    frame = static.decode_static_frame(cold, manifest, font, index)
    region = static.region_bytes(frame, 31, 13)
    report = static.foreground_report(frame, 31, 13, 1)
    records = manifest["highscore_logo"]["records"]
    phase_reports = []
    phase_region_hashes = []
    for phase in (0, 1):
        composed = bytearray(frame)
        for destination, phase0_ptr, phase1_ptr in records:
            tile_ptr = (phase0_ptr, phase1_ptr)[phase]
            static.overlay_tile(composed, destination, cold[tile_ptr:tile_ptr + 32])
        phase_region = static.region_bytes(composed, 31, 13)
        phase_region_hashes.append(sha(phase_region))
        phase_reports.append(static.foreground_report(composed, 31, 13, 1))
    destinations = [
        {"x": (destination - 0x2000) % 1280 // 4,
         "y": (destination - 0x2000) // 1280}
        for destination, _, _ in records
    ]
    return {
        "revision": receipt["revision"],
        "receipt_state": receipt["state"],
        "receipt_profile": receipt["profile"],
        "rom_sha256": artifact_checks["ladybug.rom"]["actual"],
        "artifact_checks": artifact_checks,
        "cold_payload_sha256": sha(cold),
        "high_score_map_index": index,
        "r_crop_sha256": sha(region),
        "r_crop_hex": region.hex(),
        "r_pixels": report,
        "deferred_logo": {
            "record_count": len(records),
            "record_destinations": destinations,
            "phase0_r": phase_reports[0],
            "phase1_r": phase_reports[1],
            "phase0_r_sha256": phase_region_hashes[0],
            "phase1_r_sha256": phase_region_hashes[1],
            "r_unchanged_in_both_deferred_phases": phase_region_hashes == [sha(region), sha(region)],
        },
    }


def main() -> None:
    static = load_static()
    old = decode(static, PRE)
    c3 = decode(static, C3)
    if old["rom_sha256"] != EXPECTED_PRE_ROM:
        raise RuntimeError("pre-cleanup root ROM is not the preserved expected build")
    if c3["rom_sha256"] != EXPECTED_C3_ROM:
        raise RuntimeError("C3 ROM is not the exact current parent build")
    result = {
        "question": "Do the preserved pre-cleanup high-score cold asset or either deferred logo phase differ from the exact C3 R crop?",
        "method": "Reuse the existing manifest/cold-payload/SharedText font decoder; decode high-score map 3 and apply each receipted build's 12 deferred logo records for both phases, then crop base cells x31,y13–14.",
        "pre_cleanup": old,
        "c3": c3,
        "comparison": {
            "r_crop_bytes_equal": old["r_crop_hex"] == c3["r_crop_hex"],
            "r_crop_hash_equal": old["r_crop_sha256"] == c3["r_crop_sha256"],
            "deferred_record_destinations_equal": old["deferred_logo"]["record_destinations"] == c3["deferred_logo"]["record_destinations"],
            "old_and_c3_r_regions_equal_in_both_deferred_phases": (
                old["deferred_logo"]["phase0_r_sha256"] == c3["deferred_logo"]["phase0_r_sha256"] == old["r_crop_sha256"]
                and old["deferred_logo"]["phase1_r_sha256"] == c3["deferred_logo"]["phase1_r_sha256"] == old["r_crop_sha256"]
            ),
            "pre_cleanup_has_white_foreground": old["r_pixels"]["white_foreground_pixels"] > 0,
            "c3_has_white_foreground": c3["r_pixels"]["white_foreground_pixels"] > 0,
        },
        "limits": "This compares receipted cold/static asset output and the actual two deferred logo phases. It does not identify live runtime writers or independently validate that the historical user screenshot came from this pre-cleanup ROM.",
    }
    target = HERE / "bug100-precleanup-vs-c3-cold-crop.json"
    target.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
