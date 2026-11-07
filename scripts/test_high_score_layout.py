"""Qualify the saved High Score rectangle contract against independent fixtures."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

import build_presentation as presentation
from shared_text import apply_fixed_colour_runs
from verify_shared_text import verify_score_field


ROOT = Path(__file__).resolve().parents[1]
MAP = ROOT / "tiled" / "coco-high-score-screen.tmx"
FIELDS = ("Name", "Score")


def marker_name(rank: int, field: str) -> str:
    return f"Rank_{rank:02d}_{field}"


def read_layout(path: Path) -> tuple[ET.Element, ET.Element]:
    root = ET.parse(path).getroot()
    layer = next(
        item for item in root.findall("objectgroup")
        if item.get("name") == "High Score Data Layout"
    )
    return root, layer


def write_fixture(root: ET.Element, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    for tileset in root.findall('tileset'):
        tileset.set('source', str((MAP.parent / tileset.get('source')).resolve()))
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)
    return path


class HighScoreLayoutTests(unittest.TestCase):
    def fixture(self, mutate):
        root, layer = read_layout(MAP)
        mutate(root, layer)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        return write_fixture(root, Path(directory.name) / "fixture.tmx")

    def assert_rejected(self, mutate):
        fixture = self.fixture(mutate)
        with self.assertRaises(ValueError):
            presentation.parse_high_score_layout(fixture)

    def test_authored_rectangles_convert_to_nine_unique_destinations(self):
        root, layer = read_layout(MAP)
        width, height = int(root.get("width")), int(root.get("height"))
        objects = {obj.get("name"): obj for obj in layer.findall("object")}
        expected_names = {
            marker_name(rank, field)
            for rank in range(1, 10)
            for field in FIELDS
        }
        self.assertEqual(set(objects), expected_names)

        independent = []
        claimed = set()
        for rank in range(1, 10):
            row = {}
            for field in FIELDS:
                obj = objects[marker_name(rank, field)]
                self.assertEqual(float(obj.get("width")), 56)
                self.assertEqual(float(obj.get("height")), 8)
                x_px, y_px = float(obj.get("x")), float(obj.get("y"))
                self.assertEqual(x_px % 8, 0)
                self.assertEqual(y_px % 8, 0)
                x, y = int(x_px / 8), int(y_px / 8)
                self.assertGreaterEqual(x, 0)
                self.assertGreaterEqual(y, 0)
                self.assertLessEqual(x + 7, width)
                self.assertLess(y, height)
                field_cells = {(column, y) for column in range(x, x + 7)}
                self.assertFalse(claimed & field_cells)
                claimed |= field_cells
                # Scores use six right-aligned cells in the seven-cell rectangle.
                draw_x = x + (1 if field == "Score" else 0)
                destination = 0x2000 + y * 1280 + draw_x * 4
                row[field.lower()] = (x, y, destination)
            independent.append(row)

        actual = presentation.parse_high_score_layout(MAP)
        self.assertEqual(len(actual), 9)
        self.assertEqual([item["record_index"] for item in actual], list(range(9)))
        self.assertEqual(len({tuple(item["name_cell"]) for item in actual}), 9)
        for rank, (expected, placement) in enumerate(zip(independent, actual), 1):
            self.assertEqual(placement["slot"], f"RANK_{rank:02d}")
            self.assertEqual(placement["name_cell"], list(expected["name"][:2]))
            self.assertEqual(placement["score_cell"], list(expected["score"][:2]))
            self.assertEqual(placement["name_destination"], expected["name"][2])
            self.assertEqual(placement["score_destination"], expected["score"][2])
            self.assertEqual(placement["name_cell_width"], 7)
            self.assertEqual(placement["score_cell_width"], 7)
            self.assertEqual(placement["score_draw_cells"], 6)
            self.assertEqual(placement["score_max_digits"], 6)

    def test_missing_marker_is_rejected(self):
        def mutate(_root, layer):
            obj = next(o for o in layer.findall("object")
                       if o.get("name") == marker_name(4, "Name"))
            layer.remove(obj)
        self.assert_rejected(mutate)

    def test_duplicate_marker_name_is_rejected(self):
        def mutate(_root, layer):
            obj = next(o for o in layer.findall("object")
                       if o.get("name") == marker_name(4, "Name"))
            layer.append(copy.deepcopy(obj))
        self.assert_rejected(mutate)

    def test_non_56_by_8_rectangle_is_rejected(self):
        def mutate(_root, layer):
            obj = next(o for o in layer.findall("object")
                       if o.get("name") == marker_name(4, "Name"))
            obj.set("width", "48")
        self.assert_rejected(mutate)

    def test_off_grid_rectangle_is_rejected(self):
        def mutate(_root, layer):
            obj = next(o for o in layer.findall("object")
                       if o.get("name") == marker_name(4, "Name"))
            obj.set("x", "121")
        self.assert_rejected(mutate)

    def test_out_of_screen_rectangle_is_rejected(self):
        def mutate(_root, layer):
            obj = next(o for o in layer.findall("object")
                       if o.get("name") == marker_name(4, "Name"))
            obj.set("x", "272")
        self.assert_rejected(mutate)

    def test_name_score_overlap_is_rejected(self):
        def mutate(_root, layer):
            obj = next(o for o in layer.findall("object")
                       if o.get("name") == marker_name(1, "Score"))
            obj.set("x", "120")
        self.assert_rejected(mutate)

    def test_overlap_with_title_is_rejected(self):
        def mutate(_root, layer):
            obj = next(o for o in layer.findall("object")
                       if o.get("name") == marker_name(1, "Name"))
            obj.set("x", "80")
            obj.set("y", "32")
        self.assert_rejected(mutate)

    def test_overlap_with_logo_base_is_rejected(self):
        def mutate(_root, layer):
            obj = next(o for o in layer.findall("object")
                       if o.get("name") == marker_name(1, "Name"))
            obj.set("x", "72")
            obj.set("y", "136")
        self.assert_rejected(mutate)

    def score_fixture(self, offsets, codes=None):
        codes = codes or [9] + [0] * (len(offsets) - 1)
        def mutate(root, layout):
            marker = next(o for o in layout.findall('object') if o.get('name') == 'Rank_01_Score')
            x, y = int(float(marker.get('x')) / 8), int(float(marker.get('y')) / 8)
            layer = next(item for item in root.findall('layer') if item.get('name') == 'High Score Names and Scores')
            cells = [int(v.strip()) for v in layer.findtext('data').split(',')]
            for column in range(x, x + 7):
                cells[y * 40 + column] = 0
            for offset, code in zip(offsets, codes):
                # Independent raw-sheet convention for digits/letter A.
                cells[y * 40 + x + offset] = (31 - code) * 16 + 1
            layer.find('data').text = ','.join(map(str, cells))
        return self.fixture(mutate)

    def test_short_five_digit_and_full_capacity_suffixes(self):
        for count in (1, 5, 6):
            with self.subTest(count=count):
                path = self.score_fixture(list(range(7 - count, 7)))
                root, layer = read_layout(path)
                marker = next(o for o in layer.findall('object') if o.get('name') == 'Rank_01_Score')
                x, y = int(float(marker.get('x')) / 8), int(float(marker.get('y')) / 8)
                placement = presentation.parse_high_score_layout(path)[0]
                self.assertEqual(placement['authored_score_cells'], [[x + d, y] for d in range(7 - count, 7)])
                self.assertEqual(placement['score_max_digits'], 6)
                self.assertEqual(placement['score_destination'], 0x2000 + y * 1280 + (x + 1) * 4)

    def test_score_rejects_padding_errors_gaps_letters_and_overcapacity(self):
        cases = [([], []), ([0, 1, 2, 3, 4], None), ([2, 3, 5, 6], None),
                 (list(range(7)), None), ([2, 3, 4, 5, 6], [10, 0, 0, 0, 0])]
        for offsets, codes in cases:
            with self.subTest(offsets=offsets, codes=codes), self.assertRaises(ValueError):
                presentation.parse_high_score_layout(self.score_fixture(offsets, codes))

    def test_named_colours_follow_marker_and_leave_padding_alone(self):
        config = json.loads((ROOT / 'assets/arcade/text-colours.json').read_text())
        path = self.score_fixture([2, 3, 4, 5, 6])
        root, layout = read_layout(path)
        marker = next(o for o in layout.findall('object') if o.get('name') == 'Rank_01_Score')
        x, y = int(float(marker.get('x')) / 8), int(float(marker.get('y')) / 8)
        resolved = presentation.high_score_field_colour_cells(path, config)
        self.assertNotIn((x, y), resolved)
        self.assertNotIn((x + 1, y), resolved)
        for column in range(x + 2, x + 7):
            self.assertEqual(resolved[column, y], 1)

    def test_named_rule_survives_moving_score_field(self):
        config = json.loads((ROOT / 'assets/arcade/text-colours.json').read_text())
        expected = {}
        def mutate(root, layout):
            marker = next(o for o in layout.findall('object') if o.get('name') == 'Rank_09_Score')
            x, y = int(float(marker.get('x')) / 8), int(float(marker.get('y')) / 8)
            new_y = 5  # controlled empty spacer row in this fixture
            marker.set('y', str(new_y * 8))
            layer = next(item for item in root.findall('layer') if item.get('name') == 'High Score Names and Scores')
            cells = [int(v.strip()) for v in layer.findtext('data').split(',')]
            for column in range(x, x + 7):
                cells[new_y * 40 + column] = cells[y * 40 + column]
                cells[y * 40 + column] = 0
            layer.find('data').text = ','.join(map(str, cells))
            expected.update(x=x, old_y=y, new_y=new_y)
        path = self.fixture(mutate)
        resolved = presentation.high_score_field_colour_cells(path, config)
        self.assertFalse(any((column, expected['old_y']) in resolved for column in range(expected['x'], expected['x'] + 7)))
        self.assertTrue(any((column, expected['new_y']) in resolved for column in range(expected['x'], expected['x'] + 7)))

    def test_named_rules_reject_missing_duplicate_and_unknown_fields(self):
        base = json.loads((ROOT / 'assets/arcade/text-colours.json').read_text())
        variants = [copy.deepcopy(base) for _ in range(3)]
        variants[0]['field_runs'].pop()
        variants[1]['field_runs'].append(copy.deepcopy(variants[1]['field_runs'][0]))
        variants[2]['field_runs'][0]['field'] = 'Rank_10_Score'
        for config in variants:
            with self.assertRaises(ValueError):
                presentation.high_score_field_colour_cells(MAP, config)

    def test_fixed_override_still_rejects_background(self):
        with self.assertRaisesRegex(ValueError, 'not a text cell'):
            apply_fixed_colour_runs({}, [{'screen': 'high-score', 'x': 24, 'y': 4, 'width': 1, 'colour': 1}])
        cells = {('high-score', 185): {'colour': 6}}
        apply_fixed_colour_runs(cells, [{'screen': 'high-score', 'x': 25, 'y': 4, 'width': 1, 'colour': 1}])
        self.assertEqual(cells['high-score', 185]['colour'], 1)

    def test_verifier_distinguishes_authored_length_and_capacity(self):
        for count in (1, 5, 6):
            columns = list(range(30 - count, 30))
            placement = {'score_cell': [23, 4], 'score_cell_width': 7, 'score_max_digits': 6,
                         'score_draw_cells': 6, 'score_destination': 0x3460,
                         'authored_score_cells': [[column, 4] for column in columns]}
            cells = {('high-score', column, 4): {'code': 0, 'colour': 1} for column in columns}
            verify_score_field(placement, copy.deepcopy(placement), cells, 1)
            bad = dict(cells)
            bad.pop(('high-score', 29, 4))
            with self.assertRaises(AssertionError):
                verify_score_field(placement, copy.deepcopy(placement), bad, 1)


if __name__ == "__main__":
    unittest.main()
