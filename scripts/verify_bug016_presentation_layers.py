#!/usr/bin/env python3
"""Verify BUG-016 presentation layer ownership and marker diagnostics."""

from __future__ import annotations

import argparse
import copy
import json
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

import build_screen as screen
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


def require_gameplay_failure(
    root: ET.Element, path: Path, expected: str, label: str,
) -> None:
    try:
        screen.validate_gameplay_sprite_locations(root, path)
    except ValueError as error:
        if expected not in str(error):
            raise SystemExit(
                f"BUG-059 proof: {label} produced wrong diagnostic: {error}"
            ) from error
        return
    raise SystemExit(f"BUG-059 proof: {label} was accepted")


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
        expected_role = "options" if name == "keybind-options" else name
        if result["role"] != expected_role:
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

    gameplay_path = args.tiled_dir / "coco-screen.tmx"
    gameplay_root = ET.parse(gameplay_path).getroot()
    gameplay_layer = screen.validate_gameplay_sprite_locations(
        gameplay_root, gameplay_path,
    )
    gameplay_records = layer_records(gameplay_layer)
    if gameplay_records != screen.GAMEPLAY_SPRITE_LOCATIONS:
        raise SystemExit("BUG-059 proof: gameplay sprite marker differs")

    assets = args.tiled_dir.parent / "assets" / "arcade"
    baseline_compilation = screen.compile_screen(
        gameplay_path, assets / "maze.json", assets / "chars.json",
        assets / "sprites.json",
    )
    original_parse = screen.ET.parse

    def changed_metadata_parse(path: Path):
        tree = original_parse(path)
        if Path(path).resolve() == gameplay_path.resolve():
            replace_cell(
                layer(tree.getroot(), "Sprite Locations"), (32, 13), 634,
            )
        return tree

    # Bypass only the exact-value check on this in-memory alternate marker so
    # the compiler's layer-identity skip can be compared independently.
    def accept_metadata_for_exclusion_check(
        root: ET.Element, path: Path,
    ) -> ET.Element:
        return layer(root, "Sprite Locations")

    with patch.object(screen.ET, "parse", side_effect=changed_metadata_parse):
        with patch.object(
            screen, "validate_gameplay_sprite_locations",
            side_effect=accept_metadata_for_exclusion_check,
        ):
            changed_marker_compilation = screen.compile_screen(
                gameplay_path, assets / "maze.json", assets / "chars.json",
                assets / "sprites.json",
            )
    if changed_marker_compilation != baseline_compilation:
        raise SystemExit(
            "BUG-059 proof: gameplay Sprite Locations affected static output"
        )

    missing_game_layer = copy.deepcopy(gameplay_root)
    missing_game_layer.remove(
        layer(missing_game_layer, "Sprite Locations"),
    )
    require_gameplay_failure(
        missing_game_layer, gameplay_path,
        "expected one Sprite Locations layer; found 0", "missing gameplay layer",
    )

    duplicate_game_layer = copy.deepcopy(gameplay_root)
    duplicate_game_layer.append(copy.deepcopy(
        layer(duplicate_game_layer, "Sprite Locations"),
    ))
    require_gameplay_failure(
        duplicate_game_layer, gameplay_path,
        "expected one Sprite Locations layer; found 2",
        "duplicate gameplay layer",
    )

    missing_marker = copy.deepcopy(gameplay_root)
    replace_cell(layer(missing_marker, "Sprite Locations"), (32, 13), 0)
    require_gameplay_failure(
        missing_marker, gameplay_path, "missing=[(32, 13)]",
        "missing gameplay marker",
    )

    extra_marker = copy.deepcopy(gameplay_root)
    replace_cell(layer(extra_marker, "Sprite Locations"), (33, 13), 633)
    require_gameplay_failure(
        extra_marker, gameplay_path, "extra=[(33, 13)]",
        "extra gameplay marker",
    )

    wrong_coordinate = copy.deepcopy(gameplay_root)
    wrong_location_layer = layer(wrong_coordinate, "Sprite Locations")
    replace_cell(wrong_location_layer, (32, 13), 0)
    replace_cell(wrong_location_layer, (31, 13), 633)
    require_gameplay_failure(
        wrong_coordinate, gameplay_path,
        "missing=[(32, 13)], extra=[(31, 13)]",
        "misplaced gameplay marker",
    )

    wrong_gid = copy.deepcopy(gameplay_root)
    replace_cell(layer(wrong_gid, "Sprite Locations"), (32, 13), 8)
    require_gameplay_failure(
        wrong_gid, gameplay_path, "wrong=[(32, 13)]",
        "non-sprite gameplay marker GID",
    )

    original_tileset_ranges = screen.tileset_ranges

    def wrong_sprite_dimensions(root: ET.Element, path: Path):
        ranges = original_tileset_ranges(root, path)
        sprites = next(item for item in ranges
                       if item["name"] == "sprites_raw2bpp")
        sprites["tilewidth"] = 8
        return ranges

    wrong_dimensions = copy.deepcopy(gameplay_root)
    with patch.object(
        screen, "tileset_ranges", side_effect=wrong_sprite_dimensions,
    ):
        require_gameplay_failure(
            wrong_dimensions, gameplay_path,
            "expected sprites_raw2bpp (16, 16)",
            "wrong gameplay sprite dimensions",
        )

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
        if markers.get("gameplay") != marker_manifest(
            screen.GAMEPLAY_SPRITE_LOCATIONS,
        ):
            raise SystemExit("BUG-059 proof: manifest gameplay marker differs")

    deferred = sum(len(contract["deferred"]) for contract in
                   PRESENTATION_LAYER_CONTRACTS.values())
    print(
        f"BUG-016 proof: {len(contracts)} role contracts, "
        f"{len(raw_instruction) + len(raw_level)} raw markers, "
        f"{deferred} deferred logo layers, 5 presentation negative diagnostics; "
        "BUG-059 gameplay marker valid, metadata excluded, "
        "7 negative diagnostics"
    )


if __name__ == "__main__":
    main()
