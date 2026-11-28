#!/usr/bin/env python3
"""Compile the authored GMC loading screen into its compact boot asset."""

from __future__ import annotations

import argparse
import xml.etree.ElementTree as ET
from pathlib import Path

from build_screen import BLACK, PALETTE, WHITE, load_chars, pack_tile, parse_csv, recolor, rotate_ccw


def compile_loading(tmx: Path, chars_path: Path) -> bytes:
    root = ET.parse(tmx).getroot()
    if (root.get("width"), root.get("height"), root.get("tilewidth"),
            root.get("tileheight")) != ("40", "24", "8", "8"):
        raise ValueError("loading TMX must be a 40×24 map of 8×8 tiles")
    tileset = root.find("tileset")
    if tileset is None or tileset.attrib != {"firstgid": "1", "source": "chars_raw2bpp.tsx"}:
        raise ValueError("loading TMX must use the raw character tileset")

    layers = {layer.get("name"): parse_csv(layer.find("data"), layer.get("name"))
              for layer in root.findall("layer")}
    if layers["Background"] != [8] * 960:
        raise ValueError("loading screen background must be uniformly black")

    chars = load_chars(chars_path)

    def glyphs(layer: str, row: int, expected_ids: tuple[int, ...]) -> list[bytes]:
        records = [(i, gid) for i, gid in enumerate(layers[layer]) if gid]
        expected = list(zip(range(row * 40 + 16, row * 40 + 23), expected_ids))
        if records != expected:
            raise ValueError(f"{layer} must use the authored characters at columns 16–22")
        packed = []
        for _, gid in records:
            sheet = gid - 1
            code = (sheet % 16) * 32 + (31 - sheet // 16)
            packed.append(pack_tile(recolor(rotate_ccw(chars[code]),
                                            (BLACK, WHITE, WHITE, WHITE))))
        return packed

    word = glyphs("Loading Text", 11, (161, 113, 337, 289, 209, 129, 241))
    if any(any(tile[:4] + tile[28:]) for tile in word):
        raise ValueError("LOADING glyphs must have blank first and last rows")
    dots = glyphs("Loading Animation", 12, (290,) * 7)
    dot = dots[0]
    offsets = (21, 25)
    if [(i, value) for i, value in enumerate(dot) if value] != [(i, 0x66) for i in offsets]:
        raise ValueError("loading dot must occupy one white byte on each of two rows")

    rows = b"".join(tile[i:i + 4] for i in range(4, 28, 4) for tile in word)
    return rows + bytes(dot[i] for i in offsets) + bytes(PALETTE)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tmx", type=Path)
    parser.add_argument("chars", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    asset = compile_loading(args.tmx, args.chars)
    args.output.write_bytes(asset)


if __name__ == "__main__":
    main()
