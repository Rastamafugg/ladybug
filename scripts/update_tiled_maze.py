#!/usr/bin/env python3
"""Replace the Tiled screen layer with GIDs from the MAME background capture."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--capture",
        type=Path,
        default=Path("assets/arcade/maze_capture.json"),
    )
    parser.add_argument(
        "--map",
        type=Path,
        default=Path("tiled/black-and-whitte-screen.tmx"),
    )
    parser.add_argument("--layer-id", default="1")
    return parser.parse_args()


def csv_rows(indices: list[list[int]]) -> str:
    return "\n".join(
        ",".join(str(index + 1) for index in row) + "," for row in indices
    )


def main() -> None:
    args = parse_args()
    capture = json.loads(args.capture.read_text(encoding="utf-8"))
    indices = capture["visible_ccw_sheet_indices"]
    if len(indices) != 30 or any(len(row) != 24 for row in indices):
        raise ValueError("capture must contain a 30-row by 24-column visible grid")

    document = ET.parse(args.map)
    root = document.getroot()
    if root.get("width") != "24" or root.get("height") != "30":
        raise ValueError("Tiled map must be 24 columns by 30 rows")
    layer = root.find(f"./layer[@id='{args.layer_id}']")
    if layer is None:
        raise ValueError(f"Tiled layer id {args.layer_id} was not found")
    data = layer.find("data")
    if data is None or data.get("encoding") != "csv":
        raise ValueError("target Tiled layer must use CSV encoding")

    text = args.map.read_text(encoding="utf-8")
    pattern = re.compile(
        r'(<layer\b[^>]*\bid="'
        + re.escape(args.layer_id)
        + r'"[^>]*>.*?<data\s+encoding="csv">)\s*.*?(\s*</data>)',
        re.DOTALL,
    )
    replacement = r"\1\n" + csv_rows(indices) + r"\2"
    updated, count = pattern.subn(replacement, text, count=1)
    if count != 1:
        raise ValueError("could not replace the target CSV layer")
    with args.map.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(updated)
    print(f"tiled: wrote 24x30 capture grid to {args.map}")


if __name__ == "__main__":
    main()
