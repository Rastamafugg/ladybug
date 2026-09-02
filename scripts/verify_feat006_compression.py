#!/usr/bin/env python3
"""Retain FEAT-006 stream identity, bounds, decoder, and capacity evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from gmc_lzss import decompress


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--require-source-margin", type=int, default=2048)
    parser.add_argument("--boot-map", type=Path, default=BUILD / "ladybug-gmc-boot.map")
    parser.add_argument("--bank0", type=Path, default=BUILD / "ladybug-gmc-bank0-overflow.bin")
    parser.add_argument("--bank2", type=Path, default=BUILD / "ladybug-sparse-bank2.bin")
    parser.add_argument("--bank3", type=Path, default=BUILD / "ladybug-sparse-bank3.bin")
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="ascii"))
    streams = manifest.get("compression", {}).get("streams", [])
    required = {"page39", "presentation_page_3a", "presentation_page_3b", "audio_page_3d"}
    if {stream["name"] for stream in streams} != required:
        raise SystemExit("FEAT-006 compression proof: required four-stream set differs")
    banks = {0: args.bank0.read_bytes(), 2: args.bank2.read_bytes(), 3: args.bank3.read_bytes()}
    rows = []
    destinations = []
    sources = []
    for stream in streams:
        start = stream["source_offset"]
        end = start + stream["compressed_bytes"]
        packed = banks[stream["bank"]][start:end]
        expanded = decompress(packed, stream["raw_bytes"])
        if sha(packed) != stream["compressed_sha256"]:
            raise SystemExit(f"FEAT-006 compression proof: {stream['name']} staged hash differs")
        if sha(expanded) != stream["raw_sha256"] or not stream.get("round_trip_exact"):
            raise SystemExit(f"FEAT-006 compression proof: {stream['name']} expansion differs")
        destination = (stream["destination_page"], stream["destination_address"], stream["destination_end"])
        if not (0xA000 <= destination[1] <= destination[2] <= 0xC000):
            raise SystemExit(f"FEAT-006 compression proof: {stream['name']} crosses a destination page")
        destinations.append((stream["name"], *destination))
        sources.append((stream["name"], stream["bank"], start, end))
        rows.append({**stream, "staged_sha256": sha(packed), "expanded_sha256": sha(expanded), "byte_exact": True})
    for intervals in (destinations, sources):
        for index, left in enumerate(intervals):
            for right in intervals[index + 1:]:
                if left[1] == right[1] and left[3] > right[2] and right[3] > left[2]:
                    raise SystemExit(f"FEAT-006 compression proof: overlap between {left[0]} and {right[0]}")

    map_text = args.boot_map.read_text(encoding="utf-8")
    symbols = {name: int(value, 16) for name, value in re.findall(
        r"^Symbol: (decompress_gmc_streams|decompress_attract_surfaces) .* = ([0-9A-Fa-f]+)$",
        map_text, re.MULTILINE,
    )}
    decoder_bytes = symbols["decompress_attract_surfaces"] - symbols["decompress_gmc_streams"]
    margin = manifest["gmc"]["spare_bytes"]
    if margin < args.require_source_margin:
        raise SystemExit(f"FEAT-006 compression proof: source margin {margin} < {args.require_source_margin}")
    evidence = {
        "status": "pass", "codec": manifest["compression"]["codec"],
        "decoder_bytes": decoder_bytes, "source_margin_bytes": margin,
        "required_source_margin_bytes": args.require_source_margin,
        "streams": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="ascii")
    print(f"FEAT-006 compression proof: 4 byte-exact page-bounded streams; decoder {decoder_bytes} bytes; source margin {margin}/{args.require_source_margin}")


if __name__ == "__main__":
    main()
