"""Shared fail-closed identity classifier for FEAT-010 cold-menu evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
CAPSULE = ROOT / "repro" / "feat010-manual-review-20261016" / "capsule"
MANIFEST_PATH = Path(__file__).with_name("manifest.json")
RESIDENT_SOURCE_ROM = "build/ladybug-runtime.rom"
RESIDENT_SOURCE_ROM_SHA256 = "0f865b28b003c7c39fc03bd0468dcb6184cfe602a64cd952053a15139974d6fc"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def load_manifest() -> dict[str, Any]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def expected_bindings(manifest: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    manifest = manifest or load_manifest()
    capsule = manifest["capsule"]
    rom_sha = capsule["rom_sha256"]
    rows = manifest["bindings"]
    return {
        "resident_bank1": {
            "artifact_sha256": rom_sha,
            "region": rows["resident_bank1"]["region"],
            "address": rows["resident_bank1"]["address"],
            "length": rows["resident_bank1"]["length"],
            "sha256": rows["resident_bank1"]["artifact_sha256"],
        },
        "resident_authored": {
            "artifact_sha256": RESIDENT_SOURCE_ROM_SHA256,
            "region": "resident-authored-runtime-rom-slice",
            "address": "0x0000",
            "length": rows["resident_bank1"]["length"],
            "sha256": rows["resident_bank1"]["artifact_sha256"],
        },
        "resident_packaged": {
            "artifact_sha256": rom_sha,
            "region": "gmc-bank1-rom-slice",
            "address": "0x4000",
            "length": rows["resident_bank1"]["length"],
            "sha256": rows["resident_bank1"]["artifact_sha256"],
        },
        "presentation": {
            "artifact_sha256": rom_sha,
            "region": rows["presentation"]["region"],
            "address": rows["presentation"]["address"],
            "length": rows["presentation"]["length"],
            "sha256": rows["presentation"]["sha256"],
        },
        "instruction_copy": {
            "artifact_sha256": rom_sha,
            "region": rows["instruction_copy"]["region"],
            "address": rows["instruction_copy"]["destination_address"],
            "length": rows["instruction_copy"]["length"],
            "sha256": rows["instruction_copy"]["sha256"],
        },
        "demo_copy": {
            "artifact_sha256": rom_sha,
            "region": rows["demo_copy"]["region"],
            "address": rows["demo_copy"]["destination_address"],
            "length": rows["demo_copy"]["length"],
            "sha256": rows["demo_copy"]["sha256"],
        },
    }


def classify_binding(expected: dict[str, Any], observed: dict[str, Any]) -> dict[str, Any]:
    """Classify one dump; every pinned identity field must match exactly."""
    fields = ("artifact_sha256", "region", "address", "length", "sha256")
    mismatches = [field for field in fields if observed.get(field) != expected.get(field)]
    return {"accepted": not mismatches, "mismatches": mismatches}


def verify_static_capsule(manifest: dict[str, Any] | None = None) -> list[str]:
    """Check immutable capsule pins and derive the bank1 slice from the ROM."""
    manifest = manifest or load_manifest()
    cap = manifest["capsule"]
    # CAPSULE already names the capsule root; paths below are build-relative.
    build = CAPSULE / "build"
    checks = [
        (build / "ladybug.rom", cap["rom_sha256"]),
        (build / "source-build-receipt.json", cap["receipt_sha256"]),
        (build / "ladybug-sparse-layout.json", cap["sparse_layout_sha256"]),
        (build / "ladybug.map", cap["main_map_sha256"]),
        (build / "ladybug-presentation-runtime.map", cap["presentation_map_sha256"]),
    ]
    for row in manifest["bindings"].values():
        artifact = row.get("artifact")
        if artifact:
            checks.append((CAPSULE / artifact, row["sha256"]))
    failures = [str(path) for path, digest in checks if not path.is_file() or sha256_file(path) != digest]
    rom = (build / "ladybug.rom").read_bytes()
    bank = rom[0x4000:0x7E00]
    resident = manifest["bindings"]["resident_bank1"]
    if len(bank) != resident["length"] or sha256_bytes(bank) != resident["artifact_sha256"]:
        failures.append("packaged ROM bank1 slice")
    source_path = CAPSULE / RESIDENT_SOURCE_ROM
    if not source_path.is_file() or sha256_file(source_path) != RESIDENT_SOURCE_ROM_SHA256:
        failures.append("authored resident runtime ROM artifact")
    else:
        authored_slice = source_path.read_bytes()[:resident["length"]]
        if authored_slice != bank:
            failures.append("authored resident slice differs from packaged ROM bank1 slice")
    return failures
