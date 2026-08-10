#!/usr/bin/env python3
"""Verify the PERF-004 physical-page and boot-synthesis ownership contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--bootstrap", type=Path, required=True)
    parser.add_argument("--helper", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="ascii"))
    perimeter = manifest["perimeter_reset"]
    cold = manifest["presentation_cold"]
    if (
        perimeter["page"] != 0x20 or
        perimeter["address"] != 0xA000 or
        not perimeter.get("boot_synthesized") or
        perimeter.get("source_bytes") != 0
    ):
        raise SystemExit("allocation proof: perimeter reset is not boot-synthesized at $20")
    if cold["page"] != 0x3A or cold["page_count"] != 4:
        raise SystemExit("allocation proof: presentation cold pages moved from $3A-$3D")
    for segment in manifest["gmc"]["segments"]:
        if segment["target"] == "perimeter_reset":
            raise SystemExit("allocation proof: perimeter reset still has a loader segment")
        if segment["destination_page"] == 0x20:
            raise SystemExit("allocation proof: another payload owns physical page $20")
        if segment["destination_page"] in (0x21, 0x22):
            raise SystemExit(
                "allocation proof: payload overlaps boot-only resident/asset staging"
            )
    bootstrap = args.bootstrap.read_text(encoding="ascii")
    helper = args.helper.read_bytes()
    if "synthesize_perimeter_reset" not in bootstrap:
        raise SystemExit("allocation proof: boot synthesizer is not in the bootstrap")
    if "PERIMETER_SCREEN_MAP" not in bootstrap or "PERIMETER_SCREEN_TILES" not in bootstrap:
        raise SystemExit("allocation proof: bootstrap does not consume authored screen assets")
    if "RESIDENT_STAGE_PAGE equ $21" not in bootstrap:
        raise SystemExit("allocation proof: resident staging page is not $21")
    if "ASSET_STAGE_PAGE equ $22" not in bootstrap:
        raise SystemExit("allocation proof: asset staging page is not $22")
    synthesis_setup = bootstrap.split("copy_assets", 1)[1].split(
        "lbsr    synthesize_perimeter_reset", 1
    )[0]
    if "sta     GMC_BANK" in synthesis_setup:
        raise SystemExit(
            "allocation proof: boot synthesis hides bank-1 authored assets"
        )
    if "sta     SAM_ALLRAM" not in bootstrap:
        raise SystemExit("allocation proof: staged payloads are not followed by all-RAM")
    if helper[5:6] != b"\x20":
        raise SystemExit("allocation proof: helper does not map physical page $20")
    print("allocation proof: page $20 is boot-synthesized perimeter ownership; $3A-$3D remain cold presentation")


if __name__ == "__main__":
    main()
