#!/usr/bin/env python3
"""Verify FEAT-003 profile selection and artifact isolation."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPLETE_SHA256 = "b065057e74b448ea22acbafe5dcb4773f46d338fd9f66c99dd37b68e7fcb05fc"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--profile",
        choices=("highscore-test", "development", "release", "complete"),
    )
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--rom", type=Path, default=ROOT / "build/ladybug.rom")
    parser.add_argument(
        "--presentation-manifest", type=Path,
        default=ROOT / "build/ladybug-presentation.json",
    )
    parser.add_argument(
        "--sparse-manifest", type=Path,
        default=ROOT / "build/ladybug-sparse-layout.json",
    )
    parser.add_argument(
        "--module", type=Path,
        default=ROOT / "build/ladybug-presentation-runtime.bin",
    )
    args = parser.parse_args()
    profile = args.profile or ("complete" if args.bundle else None)
    if profile is None:
        parser.error("--profile is required unless --bundle selects the complete baseline")
    if args.bundle and profile != "complete":
        parser.error("--bundle is valid only for the complete profile")

    presentation = json.loads(args.presentation_manifest.read_text(encoding="ascii"))
    sparse = json.loads(args.sparse_manifest.read_text(encoding="ascii"))
    expected = {
        "highscore-test": (False, False, True),
        "development": (True, False, False),
        "release": (False, False, False),
        "complete": (True, True, False),
    }[profile]
    actual = (
        presentation.get("development_profile"),
        presentation.get("complete_profile"),
        presentation.get("highscore_test_profile"),
    )
    if actual != expected:
        raise SystemExit(f"FEAT-003 isolation: profile flags {actual} != {expected}")
    if sparse.get("aux_runtime", {}).get("role") != profile:
        raise SystemExit("FEAT-003 isolation: auxiliary runtime role differs")
    emitted = presentation.get("high_score_name_entry", {}).get("emitted")
    if emitted != (profile == "highscore-test"):
        raise SystemExit("FEAT-003 isolation: name-entry emission differs")
    compressed = (
        presentation["tile_atlas_compressed_bytes"] !=
        presentation["tile_atlas_expanded_bytes"]
    )
    if compressed != (profile == "highscore-test"):
        raise SystemExit("FEAT-003 isolation: atlas storage mode differs")
    if len(args.module.read_bytes()) > 1280:
        raise SystemExit("FEAT-003 isolation: presentation module exceeds 1280 bytes")

    build_source = (ROOT / "scripts/build.sh").read_text(encoding="utf-8")
    if not re.search(
        r'LADYBUG_PROFILE="\$\{LADYBUG_PROFILE:-highscore-test\}"', build_source
    ):
        raise SystemExit("FEAT-003 isolation: unset profile default differs")
    rom_hash = hashlib.sha256(args.rom.read_bytes()).hexdigest()
    if profile == "complete" and rom_hash != COMPLETE_SHA256:
        raise SystemExit(
            f"FEAT-003 isolation: complete ROM hash {rom_hash} != {COMPLETE_SHA256}"
        )
    if args.bundle:
        baseline = args.bundle / "ladybug.rom"
        if not baseline.is_file():
            raise SystemExit(f"FEAT-003 isolation: bundle ROM missing: {baseline}")
        if args.rom.read_bytes() != baseline.read_bytes():
            raise SystemExit("FEAT-003 isolation: complete ROM differs byte-for-byte from bundle")
    print(
        f"FEAT-003 isolation: profile={profile} module={args.module.stat().st_size}/1280 "
        f"rom={rom_hash} passed"
    )


if __name__ == "__main__":
    main()
