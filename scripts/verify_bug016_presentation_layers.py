#!/usr/bin/env python3
"""Verify shared presentation contracts and optional BUG-060 partition evidence."""

from __future__ import annotations

import argparse
import copy
import hashlib
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
    compile_map,
    layer_records,
    parse_csv,
    title_framebuffer,
    validate_presentation_layers,
)


WORKSPACE = Path(__file__).resolve().parents[1]
EXECUTION_EVIDENCE = (
    WORKSPACE / "wiki/internal/tickets/evidence/rsch014-ready-060/bug060-execution.json"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tiled-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument(
        "--partition-receipt", type=Path,
        help="run frozen BUG-060 authored owner, GID-map, and framebuffer checks",
    )
    parser.add_argument(
        "--execution-evidence", type=Path,
        help=f"BUG-060 execution hashes (default: {EXECUTION_EVIDENCE})",
    )
    args = parser.parse_args()
    if args.execution_evidence and not args.partition_receipt:
        parser.error("--execution-evidence requires --partition-receipt")
    return args


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


def gid_list_hash(values: list[int]) -> str:
    encoded = json.dumps(values, separators=(",", ":")).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def verify_partition_map(
    root: ET.Element, path: Path, expected: dict[str, object],
    template: dict[int, int], static_hashes: dict[str, str],
    check_file_hash: bool = True,
) -> None:
    if check_file_hash:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != expected["candidate_sha256"]:
            raise ValueError(f"{path}: candidate TMX hash differs from partition evidence")

    static_names = expected["candidate_static_layers"]
    layers = root.findall("layer")
    names = [item.get("name", "") for item in layers]
    if any(names.count(name) != 1 for name in static_names):
        raise ValueError(f"{path}: partition has a missing or duplicate static layer")
    by_name = {item.get("name", ""): item for item in layers}
    values = {name: parse_csv(by_name[name].find("data"), name)
              for name in static_names}

    if values["Background"] != [8] * 960:
        raise ValueError(f"{path}: Background must contain exactly 960 GID8 blank cells")
    border_values = values.get("Arcade Maze Border", [0] * 960)
    actual_border = {index: gid for index, gid in enumerate(border_values)
                     if gid & GID_MASK}
    wanted = template if expected["border_cells"] else {}
    if actual_border != wanted:
        raise ValueError(f"{path}: Arcade Maze Border differs from the exact template")

    for name in static_names:
        if gid_list_hash(values[name]) != static_hashes.get(name):
            raise ValueError(f"{path}: static layer contents differ for {name!r}")

    owners: list[int] = []
    for index in range(960):
        active = [name for name in static_names if values[name][index] & GID_MASK]
        if not active or active[0] != "Background":
            raise ValueError(f"{path}: cell {index} has missing or non-base visual ownership")
        if any((values[name][index] & GID_MASK) == 8 for name in active[1:]):
            raise ValueError(f"{path}: cell {index} has a duplicate blank visual owner")
        owners.append(static_names.index(active[-1]))
    if owners != expected["final_static_owner_grid"]:
        mismatch = next(index for index, pair in enumerate(zip(
            owners, expected["final_static_owner_grid"],
        )) if pair[0] != pair[1])
        raise ValueError(f"{path}: static owner differs from retained grid at cell {mismatch}")

    nonstatic = {
        item.get("name", ""): gid_list_hash(parse_csv(item.find("data"), item.get("name", "")))
        for item in layers if item.get("name", "") not in static_names
    }
    if nonstatic != expected["preserved_nonstatic_layers"]:
        raise ValueError(f"{path}: nonstatic layer contents changed")


def require_partition_failure(
    root: ET.Element, path: Path, expected: dict[str, object],
    template: dict[int, int], static_hashes: dict[str, str],
    diagnostic: str, label: str,
) -> None:
    try:
        verify_partition_map(
            root, path, expected, template, static_hashes, check_file_hash=False,
        )
    except (ValueError, StopIteration) as error:
        if diagnostic not in str(error):
            raise SystemExit(
                f"BUG-060 proof: {label} produced wrong diagnostic: {error}"
            ) from error
        return
    raise SystemExit(f"BUG-060 proof: {label} was accepted")


def main() -> None:
    args = parse_args()
    receipt = None
    execution = None
    template: dict[int, int] = {}
    if args.partition_receipt:
        evidence_path = args.execution_evidence or EXECUTION_EVIDENCE
        receipt = json.loads(args.partition_receipt.read_text(encoding="ascii"))
        execution = json.loads(evidence_path.read_text(encoding="ascii"))
        template = {
            y * 40 + x: gid for x, y, gid in receipt["border_template"]
        }
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

    if receipt is not None and execution is not None:
        for filename, expected in receipt["maps"].items():
            path = args.tiled_dir / filename
            root = ET.parse(path).getroot()
            execution_map = execution["maps"][filename]
            expected = {**expected, "candidate_sha256": execution_map["candidate_sha256"]}
            static_hashes = execution_map["static_layer_gid_sha256"]
            if filename != "coco-screen.tmx":
                role = next(name for name, mapping in MAP_FILES.items()
                            if mapping == filename)
                if contracts[role]["static_layers"] != expected["candidate_static_layers"]:
                    raise SystemExit(f"BUG-060 proof: {filename} static tuple differs from oracle")
            verify_partition_map(root, path, expected, template, static_hashes)

            assets = args.tiled_dir.parent / "assets" / "arcade"
            if filename == "coco-screen.tmx":
                compiled, tiles, *_ = screen.compile_screen(
                    path, assets / "maze.json", assets / "chars.json",
                    assets / "sprites.json",
                )
                map_bytes = bytes(compiled)
            else:
                tiles = []
                map_bytes, _ = compile_map(
                    path, screen.load_chars(assets / "chars.json"), tiles, {},
                )
                map_bytes = bytes(map_bytes)
            frame = title_framebuffer(map_bytes, tiles)
            if hashlib.sha256(map_bytes).hexdigest() != expected["compiled_map_sha256"]:
                raise SystemExit(f"BUG-060 proof: {filename} compiled GID map differs")
            if hashlib.sha256(frame).hexdigest() != expected["packed_pen_sha256"]:
                raise SystemExit(f"BUG-060 proof: {filename} packed-pen frame differs")

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

    missing_background = copy.deepcopy(roots["instructions"][1])
    missing_background.remove(layer(missing_background, "Background"))
    require_failure(missing_background, roots["instructions"][0], "missing/duplicate",
                    "missing Background layer")

    duplicate_background = copy.deepcopy(roots["instructions"][1])
    duplicate_background.append(copy.deepcopy(layer(duplicate_background, "Background")))
    require_failure(duplicate_background, roots["instructions"][0], "missing/duplicate",
                    "duplicate Background layer")

    wrong_background = copy.deepcopy(roots["instructions"][1])
    replace_cell(layer(wrong_background, "Background"), (0, 0), 9)
    require_failure(wrong_background, roots["instructions"][0], "Background must contain",
                    "nonblank Background cell")

    if receipt is not None and execution is not None:
        instruction_expected = receipt["maps"][roots["instructions"][0].name]
        instruction_hashes = execution["maps"][roots["instructions"][0].name][
            "static_layer_gid_sha256"
        ]
        changed_border = copy.deepcopy(roots["instructions"][1])
        border_cell = receipt["border_template"][0]
        replace_cell(layer(changed_border, "Arcade Maze Border"),
                     (border_cell[0], border_cell[1]), 0)
        require_partition_failure(
            changed_border, roots["instructions"][0], instruction_expected,
            template, instruction_hashes,
            "Arcade Maze Border differs from the exact template",
            "border ownership drift",
        )

        changed_art = copy.deepcopy(roots["instructions"][1])
        art_layer = layer(changed_art, "Instructions Overlay")
        art_cells = parse_csv(art_layer.find("data"), "Instructions Overlay")
        art_index = next(index for index, gid in enumerate(art_cells) if gid & GID_MASK)
        replace_cell(art_layer, (art_index % 40, art_index // 40), 0)
        require_partition_failure(
            changed_art, roots["instructions"][0], instruction_expected,
            template, instruction_hashes, "static layer contents differ",
            "nonborder art ownership drift",
        )

    unchanged_options = ET.parse(args.tiled_dir / "coco-options-screen.tmx").getroot()
    options_background = ET.Element(
        "layer", {"id": str(max(int(item.get("id", "0"))
                                for item in unchanged_options.findall("layer")) + 1),
                   "name": "Background", "width": "40", "height": "24"},
    )
    ET.SubElement(options_background, "data", {"encoding": "csv"}).text = ",".join(
        "8" for _ in range(960)
    )
    unchanged_options.append(options_background)
    require_failure(
        unchanged_options, args.tiled_dir / "coco-options-screen.tmx",
        "unexpected=['Background']", "Background on unchanged options map",
    )

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
    negative_count = 9 + (2 if receipt is not None else 0)
    partition_result = (
        "BUG-060 explicit partition snapshot validated: exact 9-map owner grids, "
        "135-cell border template, and compiled-map/frame hashes valid; "
        if receipt is not None else
        "BUG-060 shared Background/schema guards valid; frozen snapshot not requested; "
    )
    print(
        f"BUG-016 proof: {len(contracts)} role contracts, "
        f"{len(raw_instruction) + len(raw_level)} raw markers, "
        f"{deferred} deferred logo layers, {negative_count} presentation negative diagnostics; "
        f"{partition_result}"
        "BUG-059 gameplay marker valid, metadata excluded, "
        "7 negative diagnostics"
    )


if __name__ == "__main__":
    main()
