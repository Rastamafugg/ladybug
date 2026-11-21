"""One-time check that High Score fields come from the named Tiled layout."""
from __future__ import annotations

import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

import build_presentation as presentation


ROOT = Path(__file__).resolve().parents[1]
MAP = ROOT / "tiled" / "coco-high-score-screen.tmx"


class HighScoreLayoutMigrationTests(unittest.TestCase):
    def test_named_layout_generates_blank_runtime_score_destinations(self):
        root = ET.parse(MAP).getroot()
        self.assertNotIn(
            "High Score Names and Scores",
            [layer.get("name") for layer in root.findall("layer")],
        )
        layout = next(
            layer for layer in root.findall("objectgroup")
            if layer.get("name") == "High Score Data Layout"
        )
        objects = {item.get("name"): item for item in layout.findall("object")}
        expected_names = {
            f"Rank_{rank:02d}_{field}"
            for rank in range(1, 10)
            for field in ("Name", "Score")
        }
        self.assertEqual(set(objects), expected_names)

        expected_rows = (4, 6, 7, 8, 9, 10, 11, 12, 13)
        actual = presentation.parse_high_score_layout(MAP)
        map_root, flattened, _ = presentation.flatten_map(MAP)
        self.assertEqual(len(actual), 9)
        for rank, (row, placement) in enumerate(zip(expected_rows, actual), 1):
            name_obj = objects[f"Rank_{rank:02d}_Name"]
            score_obj = objects[f"Rank_{rank:02d}_Score"]
            self.assertEqual((float(name_obj.get("x")), float(name_obj.get("y"))), (120, row * 8))
            self.assertEqual((float(score_obj.get("x")), float(score_obj.get("y"))), (184, row * 8))
            self.assertEqual((float(name_obj.get("width")), float(name_obj.get("height"))), (56, 8))
            self.assertEqual((float(score_obj.get("width")), float(score_obj.get("height"))), (56, 8))
            self.assertEqual(placement["record_index"], rank - 1)
            self.assertEqual(placement["name_destination"], 0x2000 + row * 1280 + 15 * 4)
            self.assertEqual(placement["score_destination"], 0x2000 + row * 1280 + 24 * 4)
            self.assertEqual(placement["authored_score_cells"], [])
            x, y = placement["score_cell"]
            for column in range(x, x + placement["score_cell_width"]):
                gid = flattened[y * 40 + column] & presentation.GID_MASK
                self.assertIn(presentation.raw_char_code(map_root, MAP, gid), (-1, 255))


if __name__ == "__main__":
    unittest.main()
