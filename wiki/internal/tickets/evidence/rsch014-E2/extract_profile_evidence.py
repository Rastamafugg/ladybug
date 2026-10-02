#!/usr/bin/env python3
"""Extract concise page-$34 fit and emitted-call evidence from a completed build."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def symbols(path: Path) -> dict[str, int]:
    result = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^Symbol: (\w+) .* = ([0-9A-Fa-f]+)$", line)
        if match:
            result[match.group(1)] = int(match.group(2), 16)
    return result


def calls(path: Path, binary: bytes, base: int) -> list[dict[str, object]]:
    result = []
    pattern = re.compile(
        r"^\s*([0-9A-Fa-f]{4,})\s+([0-9A-Fa-f]{6})\s+"
        r"\([^)]*\):\d+\s+lbsr\s+(\w+)\s*$",
        re.IGNORECASE,
    )
    for line in path.read_text(encoding="utf-8").splitlines():
        match = pattern.match(line)
        if not match:
            continue
        address = int(match.group(1), 16)
        encoded = bytes.fromhex(match.group(2))
        target_name = match.group(3)
        if encoded[0] != 0x17:
            raise ValueError(f"{path.name}: {address:04X} {target_name} is not LBSR")
        displacement = int.from_bytes(encoded[1:3], "big", signed=True)
        decoded = (address + 3 + displacement) & 0xFFFF
        offset = address - base
        if binary[offset:offset + 3] != encoded:
            raise ValueError(f"{path.name}: emitted bytes differ at {address:04X}")
        result.append({
            "address": f"${address:04X}",
            "bytes": encoded.hex().upper(),
            "target_name": target_name,
            "decoded_target": f"${decoded:04X}",
        })
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--profile", choices=("AD1", "AD0"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    build = root / "build"
    helper_bin = build / "ladybug-enemy-helper-page34.bin"
    enemy_bin = build / "ladybug-enemy-runtime.rom"
    helper_map = symbols(build / "ladybug-enemy-helper-page34.map")
    enemy_map = symbols(build / "ladybug-enemy-runtime.map")
    runtime_map = symbols(build / "ladybug.map")
    helper = helper_bin.read_bytes()
    enemy = enemy_bin.read_bytes()
    expected = {
        "efn_cache_guard": 0xA8A0,
        "efn_normal": 0xA8AC,
        "efn_preview": 0xA8C5,
        "enemy_frame_number": 0xA8D2,
    }
    if len(helper) != 87 or any(helper_map.get(k) != v for k, v in expected.items()):
        raise ValueError("helper image length or entry addresses differ")
    if enemy_map.get("enemy_frame_number") != expected["enemy_frame_number"]:
        raise ValueError("enemy module frame-selector alias differs")

    targeted = {"efn_cache_guard", "efn_normal", "efn_preview", "enemy_frame_number"}
    enemy_calls = [c for c in calls(build / "ladybug-enemy-runtime.lst", enemy, 0x0800)
                   if c["target_name"] in targeted]
    helper_calls = [c for c in calls(build / "ladybug-enemy-helper-page34.lst", helper, 0xA8A0)
                    if c["target_name"] in targeted]
    all_calls = enemy_calls + helper_calls
    target_addresses = {k: f"${v:04X}" for k, v in expected.items()}
    for call in all_calls:
        if call["decoded_target"] != target_addresses[call["target_name"]]:
            raise ValueError(f"LBSR target mismatch: {call}")
    wanted_counts = {"efn_cache_guard": 1, "efn_normal": 2,
                     "efn_preview": 2, "enemy_frame_number": 2}
    observed_counts = {name: sum(c["target_name"] == name for c in all_calls)
                       for name in wanted_counts}
    if observed_counts != wanted_counts:
        raise ValueError(f"LBSR call inventory differs: {observed_counts}")

    jsr_line = next(line for line in (build / "ladybug-enemy-helper-page34.lst").read_text().splitlines()
                    if re.search(r"\bjsr\s+ENEMY_MODULE_BUILD_CACHE\s*$", line, re.I))
    jsr_match = re.match(r"^\s*([0-9A-Fa-f]{4,})\s+([0-9A-Fa-f]{6})\s+", jsr_line)
    if not jsr_match:
        raise ValueError("cache-builder JSR bytes are missing")
    jsr_address = int(jsr_match.group(1), 16)
    jsr_bytes = bytes.fromhex(jsr_match.group(2))
    if jsr_bytes[0] != 0xBD or int.from_bytes(jsr_bytes[1:3], "big") != 0x0824:
        raise ValueError("cache-builder absolute JSR target differs")
    helper_offset = jsr_address - 0xA8A0
    if helper[helper_offset:helper_offset + 3] != jsr_bytes:
        raise ValueError("cache-builder JSR bytes differ from helper image")

    layout = json.loads((build / "ladybug-sparse-layout.json").read_text())
    segments = [s for s in layout["gmc"]["segments"]
                if s["target"] == "enemy_helper_page34"]
    if len(segments) != 1 or segments[0] != {
        "bank": 0,
        "source_offset": segments[0]["source_offset"],
        "source_address": segments[0]["source_address"],
        "destination_page": 0x34,
        "destination_address": 0xA8A0,
        "count": 87,
        "target": "enemy_helper_page34",
        "target_offset": 0,
    }:
        raise ValueError(f"page-$34 target segmentation differs: {segments}")
    bank0 = (build / "ladybug-gmc-bank0-overflow.bin").read_bytes()
    segment = segments[0]
    source_offset = segment["source_offset"]
    if bank0[source_offset:source_offset + 87] != helper:
        raise ValueError("staged source bytes differ from helper image")

    enemy_list = (build / "ladybug-enemy-runtime.lst").read_text(encoding="utf-8")
    pad = re.search(r"^([0-9A-Fa-f]{4,})\s+[0-9A-Fa-f]+\s+.*zmb\s+\$17A0-\*", enemy_list, re.M | re.I)
    if not pad:
        raise ValueError("fixed pre-LUT guard/padding is missing")
    pre_lut_end = int(pad.group(1), 16)
    if pre_lut_end > 0x17A0:
        raise ValueError("enemy code crosses fixed LUT address")

    receipt = build / "source-build-receipt.json"
    report = {
        "profile": args.profile,
        "build_receipt": {"path": "build/source-build-receipt.json", "sha256": sha(receipt)},
        "helper": {
            "bytes": len(helper),
            "address_start": "$A8A0",
            "address_end_exclusive": f"${0xA8A0 + len(helper):04X}",
            "reserved_logo_start": "$A8FD",
            "free_before_logo_bytes": 0xA8FD - (0xA8A0 + len(helper)),
            "sha256": sha(helper_bin),
            "entries": {k: f"${helper_map[k]:04X}" for k in expected},
            "emitted_lbsr": sorted(all_calls, key=lambda c: (c["address"], c["target_name"])),
            "cache_builder_jsr": {
                "address": f"${jsr_address:04X}",
                "bytes": jsr_bytes.hex().upper(),
                "target": "$0824",
            },
        },
        "enemy_module": {
            "bytes": len(enemy),
            "sha256": sha(enemy_bin),
            "end": f"${enemy_map['enemy_runtime_end']:04X}",
            "fixed_lut": f"${enemy_map['object_mask_lut']:04X}",
            "pre_lut_code_end": f"${pre_lut_end:04X}",
            "pre_lut_free_bytes": 0x17A0 - pre_lut_end,
            "active_stage_start": "$1800",
            "active_stage_free_bytes": 0x1800 - enemy_map["enemy_runtime_end"],
        },
        "resident_and_assets": {
            "resident_end": f"${runtime_map['resident_end']:04X}",
            "resident_free_before_E000": 0xE000 - runtime_map["resident_end"],
            "asset_end": f"${runtime_map['asset_end']:04X}",
            "asset_free_before_FE00": 0xFE00 - runtime_map["asset_end"],
        },
        "sparse_delivery": {
            "segments": len(layout["gmc"]["segments"]),
            "table_bytes": layout["gmc"]["sparse_copy_table_bytes"],
            "target_segment": segment,
            "source_spare_bytes": layout["gmc"]["spare_bytes"],
            "bank0_sha256": sha(build / "ladybug-gmc-bank0-overflow.bin"),
            "bank2_sha256": sha(build / "ladybug-sparse-bank2.bin"),
            "bank3_sha256": sha(build / "ladybug-sparse-bank3.bin"),
            "layout_sha256": sha(build / "ladybug-sparse-layout.json"),
            "loader_sha256": sha(build / "ladybug-sparse-loader.inc"),
            "rom_sha256": sha(build / "ladybug.rom"),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
