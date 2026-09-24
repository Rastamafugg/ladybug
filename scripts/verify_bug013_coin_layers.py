#!/usr/bin/env python3
"""Verify BUG-013 semantic layers, exact authored slots, and sparse output."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import build_presentation as b
import verify_presentation as v


ROOT = Path(__file__).resolve().parents[1]
TMX = ROOT / "tiled/coco-high-score-screen.tmx"
MANIFEST = ROOT / "build/ladybug-presentation.json"
COLD = ROOT / "build/ladybug-presentation-cold.bin"
APPROVED_ANCHORS = [
    [1, 21], [4, 21], [7, 21], [31, 21], [34, 21], [37, 21],
    [1, 18], [4, 18], [7, 18], [31, 18], [34, 18], [37, 18],
]


def must_reject(action, label: str) -> None:
    try:
        action()
    except (ValueError, SystemExit):
        return
    raise AssertionError(f"malformed coin layer was accepted: {label}")


def main() -> None:
    root = ET.parse(TMX).getroot()
    role = b.screen_role(root, TMX)
    contract = b.validate_presentation_layers(root, TMX)
    assert role == "high-score"
    assert contract["static_layers"] == ["High Score Table and Branding"]
    assert contract["metadata_layers"] == ["Coin Positions"]
    assert contract["runtime_layers"] == []
    compiled_root, flattened, sources = b.flatten_map(TMX)
    base = next(x for x in compiled_root.findall("layer")
                if x.get("name") == "High Score Table and Branding")
    base_cells = b.parse_csv(base.find("data"), base.get("name", ""))
    assert flattened == base_cells, "static high-score map includes a non-base layer"
    assert all(source in ("", "High Score Table and Branding") for source in sources)
    assert [list(x) for x in b.high_score_coin_slots(root, TMX)["anchors"]] == APPROVED_ANCHORS
    slots = b.high_score_coin_slots(root, TMX)
    assert len(slots["quadrant_gids"]) == 4

    manifest = json.loads(MANIFEST.read_text(encoding="ascii"))
    overlay = manifest["coin_overlay"]
    assert manifest["coin_destinations"] == [
        b.framebuffer_destination(tuple(anchor)) for anchor in APPROVED_ANCHORS
    ]
    assert overlay["slot_count"] == 12
    cold = COLD.read_bytes()
    offset, size = overlay["sparse_offset"], overlay["sparse_bytes"]
    stream = cold[offset:offset + size]
    assert len(stream) == size and hashlib.sha256(stream).hexdigest() == overlay["sparse_sha256"]
    quadrants = b.high_score_coin_quadrant_tiles(
        root, TMX, b.load_chars(ROOT / "assets/arcade/chars.json"), False
    )
    native = b.compose_coin_native(quadrants)
    expected_stream = b.encode_sparse_native(native, 16, 8)
    assert stream == expected_stream, "cold coin stream differs from authored quadrants"
    surface, consumed = v.decode_sparse_native(stream, 16, 8)
    assert consumed == size and len(surface) == 128 and surface == native

    coin_layer = next(x for x in root.findall("layer") if x.get("name") == "Coin Positions")
    cells = b.parse_csv(coin_layer.find("data"), "Coin Positions")
    coin_layer.find("data").text = ",".join(map(str, cells[:-1]))
    must_reject(lambda: b.high_score_coin_slots(root, TMX), "truncated CSV")

    root = ET.parse(TMX).getroot()
    layer = next(x for x in root.findall("layer") if x.get("name") == "Coin Positions")
    cells = b.parse_csv(layer.find("data"), "Coin Positions")
    anchor_index = APPROVED_ANCHORS[0][1] * b.SCREEN_WIDTH + APPROVED_ANCHORS[0][0]
    cells[anchor_index + 1] += 1
    layer.find("data").text = ",".join(map(str, cells))
    must_reject(lambda: b.high_score_coin_slots(root, TMX), "nonidentical quadrant")

    root = ET.parse(TMX).getroot()
    layer = next(x for x in root.findall("layer") if x.get("name") == "Coin Positions")
    layer.set("name", "Coin Metadata")
    must_reject(lambda: b.validate_presentation_layers(root, TMX), "renamed semantic layer")
    root = ET.parse(TMX).getroot()
    root.append(copy.deepcopy(next(x for x in root.findall("layer")
                                   if x.get("name") == "Coin Positions")))
    must_reject(lambda: b.validate_presentation_layers(root, TMX), "duplicate semantic layer")

    print(
        "BUG-013 coin layers: exact base/runtime ownership, 12 ordered authored "
        f"2x2 slots, {size}-byte sparse stream ({hashlib.sha256(stream).hexdigest()}), "
        "and four malformed-layer rejection cases passed"
    )


if __name__ == "__main__":
    main()
