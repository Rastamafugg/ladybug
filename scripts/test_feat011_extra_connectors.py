"""Source tests for the FEAT-011 map-specific connector generator."""

from __future__ import annotations

import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from generate_feat011_extra_connectors import (
    CONNECTOR_GROUP,
    SHARED_ENDPOINT,
    connector_points,
    prepare_map,
)

ROOT = Path(__file__).resolve().parents[1]
EXTRA_MAP = ROOT / "tiled/coco-extra-screen.tmx"


def tree_without_connectors(source: str) -> tuple:
    root = ET.fromstring(source)
    for group in list(root.findall("objectgroup")):
        if group.get("name") == CONNECTOR_GROUP:
            root.remove(group)

    def node_value(node: ET.Element) -> tuple:
        return (
            node.tag,
            tuple(sorted(node.attrib.items())),
            (node.text or "").strip(),
            tuple(node_value(child) for child in list(node)),
        )

    return node_value(root)


def replace_marker(source: str, cell: tuple[int, int], encoded_gid: int) -> str:
    root = ET.fromstring(source)
    layer = next(node for node in root.findall("layer")
                 if node.get("name") == "CoCo Event Sprite Locations")
    data = layer.find("data")
    values = [value.strip() for value in (data.text or "").replace("\n", "").split(",")
              if value.strip()]
    x, y = cell
    values[y * int(layer.get("width")) + x] = str(encoded_gid)
    data.text = "\n" + ",".join(values) + "\n"
    return ET.tostring(root, encoding="unicode")


class ExtraConnectorSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = EXTRA_MAP.read_text(encoding="utf-8")
        cls.generated = prepare_map(cls.source)

    def test_generated_group_preserves_all_other_map_content(self) -> None:
        self.assertEqual(tree_without_connectors(self.source),
                         tree_without_connectors(self.generated))

    def test_exact_twelve_routes_match_slot_order(self) -> None:
        root = ET.fromstring(self.generated)
        groups = [node for node in root.findall("objectgroup")
                  if node.get("name") == CONNECTOR_GROUP]
        self.assertEqual(len(groups), 1)
        objects = groups[0].findall("object")
        self.assertEqual(len(objects), 12)
        for slot, obj in enumerate(objects):
            points = tuple(tuple(int(value) for value in point.split(","))
                           for point in obj.find("polyline").get("points", "").split())
            self.assertEqual(obj.get("name"), f"slot-{slot:02d}")
            self.assertEqual(points, connector_points(slot, SHARED_ENDPOINT))
            for (x1, y1), (x2, y2) in zip(points, points[1:]):
                self.assertTrue(x1 == x2 or y1 == y2)

    def test_existing_generated_group_is_idempotent(self) -> None:
        self.assertEqual(prepare_map(self.generated), self.generated)

    def test_moved_shared_endpoint_is_rejected(self) -> None:
        changed = self.source.replace("80,96", "81,96", 1)
        with self.assertRaisesRegex(ValueError, "shared route endpoint"):
            prepare_map(changed)

    def test_diagonal_shared_route_leg_is_rejected(self) -> None:
        changed = self.source.replace("-16,88", "-17,89", 1)
        with self.assertRaisesRegex(ValueError, "diagonal leg"):
            prepare_map(changed)

    def test_missing_reserve_marker_is_rejected(self) -> None:
        changed = replace_marker(self.source, (33, 16), 0)
        with self.assertRaisesRegex(ValueError, "reserve slot"):
            prepare_map(changed)

    def test_wrong_reserve_facing_is_rejected(self) -> None:
        changed = replace_marker(self.source, (33, 16), 3221226017)
        with self.assertRaisesRegex(ValueError, "must face right/East"):
            prepare_map(changed)


if __name__ == "__main__":
    unittest.main()
