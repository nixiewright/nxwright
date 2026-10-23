"""Combo boxes, drawn and laid out (drawing/combo_box_drawing.py), against the
Editor's simulator showing the pages of fixtures/combo-box/ on a grey page,
in the font NotoSans20: closed.page.toml, closed boxes of each look;
open.page.toml and colours.page.toml, lists open each way, scrolled, in
each `mode` and colour; and shapes.page.toml, 28 boxes rounded by `dis`."""
from pathlib import Path
import unittest

from nxwright.drawing.combo_box_drawing import (DOWN, LEFT, RIGHT, UP, arrow_points,
                                                corner_radius, list_layout)
from nxwright.drawing.page_drawing import draw_page
from nxwright.drawing.screen_pictures import paint_drawing
from nxwright.project.pictures import read_picture
from nxwright.source.page_source import Component
from tests.test_page_drawing import combo_box_differences
from tests.test_scrolling_texts import ProbeFont, probe_components

FOLDER = Path(__file__).resolve().parent / "fixtures" / "combo-box"


def page_components_of(page: str, opened: bool) -> list:
    """The page of `page`.page.toml and every component, its combo boxes'
    lists open when `opened`, as the probe's button opened them."""
    components = probe_components(FOLDER / ("%s.page.toml" % page))
    return [component if component.type != "combo-box" or not opened else
            Component(component.name, component.type, dict(component.values, down=1))
            for component in components]


class EditorComboBoxTest(unittest.TestCase):

    def test_drawn_as_the_editor_shows_them(self):
        for page, opened in (("closed", False), ("open", True), ("colours", True),
                             ("shapes", False)):
            components = page_components_of(page, opened)
            drawn = paint_drawing(draw_page(components, ProbeFont()))
            shot = read_picture((FOLDER / ("%s.png" % page)).read_bytes())
            for component in components[1:]:
                if component.type != "combo-box":
                    continue
                with self.subTest(page=page, component=component.name):
                    differing = combo_box_differences(component, drawn, shot)
                    self.assertEqual(differing[:5], [], "%d pixels differ" % len(differing))



class LayoutTest(unittest.TestCase):
    """Where the Editor's simulator placed the parts of open lists, as the
    pictures' rows and columns of colour showed them."""

    def values(self, **values) -> dict:
        return dict({"x": 20, "y": 20, "w": 140, "h": 42,
                     "path": "40V\r60V\r80V\r100V\r120V\r140V"}, **values)

    def test_opening_down_with_marks(self):
        layout = list_layout(self.values(), 6)
        self.assertEqual([box["y"] for _, box in layout.items], [84, 134, 184, 234])
        # The last mark lies a pixel nearer its items than `vvs1`.
        self.assertEqual([(box["y"], box["h"], pointing) for box, pointing in layout.marks],
                         [(70, 12, UP), (277, 12, DOWN)])

    def test_opening_up_right_and_left(self):
        up = list_layout(self.values(y=420, dir=0, qty=3), 6)
        self.assertEqual([box["y"] for _, box in up.items], [256, 306, 356])
        self.assertEqual(up.area["y"] + up.area["h"], 412)
        # Opening right, the list starts a pixel nearer than `vvs0`.
        right = list_layout(self.values(x=200, y=340, w=100, dir=3), 6)
        self.assertEqual([box["x"] for _, box in right.items], [321, 371, 421, 471])
        self.assertEqual([pointing for _, pointing in right.marks], [LEFT, RIGHT])
        left = list_layout(self.values(x=650, y=420, dir=2), 6)
        self.assertEqual([box["x"] for _, box in left.items], [436, 486, 536, 586])
        self.assertEqual(left.area["x"] + left.area["w"], 642)

    def test_without_marks(self):
        # Mode 0 keeps no room for them, and a list that fits has none.
        self.assertEqual([box["y"] for _, box in list_layout(self.values(mode=0), 6).items],
                         [70, 120, 170, 220])
        fitting = list_layout(self.values(qty=6, hig=30, vvs0=0), 6)
        self.assertEqual((fitting.marks, fitting.items[0][1]["y"]), ((), 62))

    def test_the_items_shown_follow_val(self):
        self.assertEqual(list_layout(self.values(val=4), 6).first, 2)
        self.assertEqual(list_layout(self.values(val=1), 6).first, 1)
        self.assertEqual(list_layout(self.values(), 6, first=9).first, 2)
        self.assertIsNone(list_layout(self.values(path=""), 0))

    def test_corners(self):
        # dis percent of half the shorter side, rounded up, at most half it less a pixel.
        self.assertEqual([corner_radius(120, 42, dis) for dis in (5, 25, 50, 100)],
                         [2, 6, 11, 20])
        self.assertEqual(corner_radius(40, 100, 50), 10)
        self.assertEqual(corner_radius(120, 42, 0), 0)

    def test_arrows_point_their_way(self):
        self.assertEqual(arrow_points(DOWN, 139, 31), [(133, 28), (145, 28), (139, 34)])
        self.assertEqual(arrow_points(LEFT, 470, 101), [(473, 95), (473, 107), (467, 101)])


class PreviewTest(unittest.TestCase):

    def test_a_page_files_open_list_shows(self):
        # The preview draws what the page file gives: `down` 1 shows the list.
        page, d1 = page_components_of("open", False)[:2]
        closed = draw_page([page, d1], ProbeFont())["shapes"]
        opened = draw_page([page, Component(d1.name, d1.type, dict(d1.values, down=1))],
                           ProbeFont())["shapes"]
        self.assertGreater(len(opened), len(closed))
        self.assertTrue(any(shape["y"] >= d1.values["y"] + d1.values["h"] for shape in opened))


if __name__ == "__main__":
    unittest.main()
