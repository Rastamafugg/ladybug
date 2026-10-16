"""Prepared offline fixture check. Parent executes only after freezing the card."""

from __future__ import annotations

from binding import CAPSULE, classify_binding, expected_bindings, load_manifest, sha256_bytes, verify_static_capsule


def observed(binding: dict[str, object], *, artifact_sha256: str | None = None,
             region: str | None = None, address: str | None = None,
             length: int | None = None, digest: str | None = None) -> dict[str, object]:
    return {
        "artifact_sha256": artifact_sha256 or binding["artifact_sha256"],
        "region": region or binding["region"],
        "address": address or binding["address"],
        "length": length if length is not None else binding["length"],
        "sha256": digest or binding["sha256"],
    }


def main() -> int:
    manifest = load_manifest()
    failures = verify_static_capsule(manifest)
    if failures:
        raise SystemExit("capsule pin mismatch: " + ", ".join(failures))

    expected = expected_bindings(manifest)
    build = CAPSULE / "build"
    rom_hash = manifest["capsule"]["rom_sha256"]
    rom = (build / "ladybug.rom").read_bytes()
    resident_source = (build / "ladybug-runtime.rom").read_bytes()
    resident_slice = rom[0x4000:0x7E00]
    positives = {
        "resident_bank1": sha256_bytes(rom[0x4000:0x7E00]),
        "resident_authored": sha256_bytes(resident_source[:0x3E00]),
        "resident_packaged": sha256_bytes(resident_slice),
        "presentation": sha256_bytes((build / "ladybug-presentation-runtime.bin").read_bytes()),
        "instruction_copy": sha256_bytes((build / "ladybug-instruction-runtime.bin").read_bytes()),
        "demo_copy": sha256_bytes((build / "ladybug-demo-runtime.bin").read_bytes()),
    }
    for name, digest in positives.items():
        if not classify_binding(expected[name], observed(expected[name], digest=digest))["accepted"]:
            raise SystemExit(f"positive fixture rejected: {name}")

    wrong_artifact = classify_binding(
        expected["presentation"],
        observed(expected["presentation"], artifact_sha256="0" * 64),
    )
    if wrong_artifact["accepted"] or "artifact_sha256" not in wrong_artifact["mismatches"]:
        raise SystemExit("wrong-artifact negative was not rejected")

    demo = manifest["bindings"]["demo_copy"]
    wrong_module = classify_binding(
        expected["instruction_copy"],
        observed(expected["instruction_copy"], length=demo["length"], digest=demo["sha256"]),
    )
    if wrong_module["accepted"] or not {"length", "sha256"}.issubset(wrong_module["mismatches"]):
        raise SystemExit("wrong-module negative was not rejected")

    print("prepared offline binding fixtures: 6 positives, wrong-artifact and wrong-module negatives")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
