#!/usr/bin/env python3
"""Verify BUG-016 presentation layer ownership and marker diagnostics."""

from __future__ import annotations

import argparse
import copy
import json
import xml.etree.ElementTree as ET
from pathlib import Path

from build_presentation import (
    GID_MASK,
    INSTRUCTION_RAW_SPRITE_MARKERS,
    LEVEL_START_METADATA,
    MAP_FILES,
    MAP_NAMES,
    PRESENTATION_LAYER_CONTRACTS,
    layer_records,
    parse_csv,
    validate_presentation_layers,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tiled-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    return parser.parse_args()


def layer(root: ET.Element, name: str) -> ET.Element:
    return next(item for item in root.findall("layer") if item.get("name") == name)


def replace_cell(target: ET.Element, cell: tuple[int, int], gid: int) -> None:
    data = target.find("data")
    cells = parse_csv(data, target.get("name", ""))
    cells[cell[1] * 40 + cell[0]] = gid
    if data is None:
        raise AssertionError("layer has no data")
    data.text = ",".join(str(value) for value in cells)


def require_failure(
    root: ET.Element, path: Path, expected: str, label: str,
) -> None:
    try:
        validate_presentation_layers(root, path)
    except ValueError as error:
        if expected not in str(error):
            raise SystemExit(
                f"BUG-016 proof: {label} produced wrong diagnostic: {error}"
            ) from error
        return
    raise SystemExit(f"BUG-016 proof: {label} was accepted")


def marker_manifest(records: dict[tuple[int, int], int]) -> list[dict[str, object]]:
    return [
        {"cell": list(cell), "gid": value & GID_MASK, "flags": value & ~GID_MASK}
        for cell, value in sorted(records.items())
    ]


def main() -> None:
    args = parse_args()
    roots: dict[str, tuple[Path, ET.Element]] = {}
    contracts: dict[str, dict[str, object]] = {}
    for name in MAP_NAMES:
        path = args.tiled_dir / MAP_FILES[name]
        root = ET.parse(path).getroot()
        result = validate_presentation_layers(root, path)
        if result["role"] != name:
            raise SystemExit(f"BUG-016 proof: {name} role differs from filename")
        roots[name] = (path, root)
        contracts[name] = result

    instruction_path, instruction_root = roots["instructions"]
    instruction_records = layer_records(layer(instruction_root, "Sprite Locations"))
    raw_instruction = {
        cell: value for cell, value in instruction_records.items()
        if cell in INSTRUCTION_RAW_SPRITE_MARKERS
    }
    if raw_instruction != INSTRUCTION_RAW_SPRITE_MARKERS:
        raise SystemExit("BUG-016 proof: instruction raw-sprite markers differ")

    level_path, level_root = roots["level-start"]
    level_records = layer_records(layer(level_root, "Sprite Locations"))
    raw_level = {
        cell: value for cell, value in level_records.items()
        if (value & GID_MASK) == 633
    }
    expected_level = {
        cell: value for cell, value in LEVEL_START_METADATA.items()
        if (value & GID_MASK) == 633
    }
    if raw_level != expected_level:
        raise SystemExit("BUG-016 proof: level-start raw-sprite markers differ")

    duplicate = copy.deepcopy(roots["attract"][1])
    duplicate.append(copy.deepcopy(layer(duplicate, "Attract Title and Prompts")))
    require_failure(duplicate, roots["attract"][0], "missing/duplicate",
                    "duplicate static layer")

    unknown = copy.deepcopy(roots["game-over"][1])
    extra = copy.deepcopy(layer(unknown, "Game Over Overlay"))
    extra.set("name", "Unexpected Visible Layer")
    unknown.append(extra)
    require_failure(unknown, roots["game-over"][0], "unexpected=",
                    "unexpected visible layer")

    raw_static = copy.deepcopy(level_root)
    replace_cell(layer(raw_static, "Level Start Panel"), (0, 0), 633)
    require_failure(raw_static, level_path, "unsupported tileset 'sprites_raw2bpp'",
                    "raw sprite in static layer")

    unknown_marker = copy.deepcopy(instruction_root)
    replace_cell(layer(unknown_marker, "Sprite Locations"), (0, 0), 633)
    require_failure(unknown_marker, instruction_path, "extra=[(0, 0)]",
                    "unknown raw-sprite marker")

    wrong_character = copy.deepcopy(instruction_root)
    replace_cell(layer(wrong_character, "Sprite Locations"), (28, 7), 455)
    require_failure(wrong_character, instruction_path, "wrong=[(28, 7)]",
                    "misplaced instruction character metadata")

    if args.manifest:
        manifest = json.loads(args.manifest.read_text(encoding="ascii"))
        if manifest.get("map_count") != len(MAP_NAMES):
            raise SystemExit("BUG-016 proof: manifest map count differs")
        if manifest.get("layer_contracts") != contracts:
            raise SystemExit("BUG-016 proof: manifest layer contracts differ")
        markers = manifest.get("raw_sprite_markers", {})
        if markers.get("instructions") != marker_manifest(INSTRUCTION_RAW_SPRITE_MARKERS):
            raise SystemExit("BUG-016 proof: manifest instruction markers differ")
        if markers.get("level-start") != marker_manifest(expected_level):
            raise SystemExit("BUG-016 proof: manifest level-start markers differ")

    deferred = sum(len(contract["deferred"]) for contract in
                   PRESENTATION_LAYER_CONTRACTS.values())
    print(
        f"BUG-016 proof: {len(contracts)} role contracts, "
        f"{len(raw_instruction) + len(raw_level)} raw markers, "
        f"{deferred} deferred logo layers, 5 negative diagnostics valid"
    )


if __name__ == "__main__":
    main()
