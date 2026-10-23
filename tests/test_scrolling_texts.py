"""Scrolling texts, drawn (drawing/scrolling_text_drawing.py) and moving
(testing/scrolling_texts.py), against the Editor's simulator running
fixtures/scrolling-text/page.toml: six scrolling texts, two each way across
and one each way up and down, in the font NotoSans20, stepping 20 pixels
every 1000 ms."""
from pathlib import Path
import tomllib
import unittest

from nxwright.drawing.page_drawing import DrawingResources, draw_page, inside_box
from nxwright.drawing.screen_pictures import paint_drawing
from nxwright.drawing.text_pictures import block_size
from nxwright.language.resource_names import ResourceNames
from nxwright.project.component_defaults import DEFAULTS_FILE, defaults_from_toml
from nxwright.project.pictures import read_picture
from nxwright.project.zi_font import decode_font
from nxwright.source.page_source import Component, page_components
from nxwright.testing.scrolling_texts import UNUSED_PLACE, ScrollingText
from tests.test_page_drawing import differing_pixels

FOLDER = Path(__file__).resolve().parent / "fixtures" / "scrolling-text"
FONT = decode_font((FOLDER.parent / "fonts" / "NotoSans20.zi").read_bytes())
READINGS = tomllib.loads((FOLDER / "readings.toml").read_text(encoding="utf-8"))
# The pictures kept, by their place among the readings.
PICTURES = {"p10.png": 10, "p13.png": 13, "p19.png": 19}


class ProbeFont(DrawingResources):
    """The resources of the Editor probes of moving texts: one font,
    NotoSans20, and no pictures."""

    def picture(self, picture_id):
        return None

    def picture_size(self, picture_id):
        return None

    def font(self, font_id):
        return FONT


def probe_components(page_file: Path, kind: str = None) -> list:
    """The page of a probe's `page_file` and its components of type `kind`,
    or all of them when None, as the build reads them."""
    components = page_components(
        page_file.read_text(encoding="utf-8"), page_file.name, ResourceNames([], ["NotoSans20"]),
        defaults_from_toml(DEFAULTS_FILE.read_text(encoding="utf-8"), "defaults"), "iso-8859-1")
    return components[:1] + [component for component in components[1:]
                             if kind is None or component.type == kind]


def scrolling_texts() -> list:
    """The page and its scrolling texts."""
    return probe_components(FOLDER / "page.toml", "scrolling-text")


def laid_out_size(values: dict) -> tuple:
    """The width and height of a scrolling text's text in NotoSans20, from
    its attributes `values`, as the simulation measures it."""
    return block_size(values["txt"], FONT, "iso-8859-1", values, inside_box(values)["w"])


def measured(component: Component) -> Component:
    """`component` with its text's width and height in `vvs2` and `vvs3`, as
    the screen measures them as its page opens (scrolling_texts.py)."""
    width, height = laid_out_size(component.values)
    return Component(component.name, component.type,
                     dict(component.values, vvs2=width, vvs3=height))


class EditorScrollingTextTest(unittest.TestCase):

    def test_drawn_where_the_editor_shows_them(self):
        page, *texts = scrolling_texts()
        components = [page] + [measured(text) for text in texts]
        for picture, index in PICTURES.items():
            scrolled = {name: places[index] for name, places in READINGS.items()}
            drawn = paint_drawing(draw_page(components, ProbeFont(), scrolled=scrolled))
            shot = read_picture((FOLDER / picture).read_bytes())
            for component in components[1:]:
                with self.subTest(picture=picture, component=component.name):
                    differing = differing_pixels(drawn, shot, component.values, 2)
                    self.assertEqual(differing[:5], [], "%d pixels differ" % len(differing))

    def test_at_rest_in_the_preview_as_a_text_is_drawn(self):
        page, *texts = scrolling_texts()
        for text in texts:
            with self.subTest(component=text.name):
                as_text = Component(text.name, "text", text.values)
                self.assertEqual(draw_page([page, text], ProbeFont())["shapes"],
                                 draw_page([page, as_text], ProbeFont())["shapes"])


class MotionTest(unittest.TestCase):
    """Each scrolling text, stepped from its start, passes through what the
    Editor's simulator showed, in order."""

    def test_as_the_editors_simulator_moved_them(self):
        for component in scrolling_texts()[1:]:
            with self.subTest(component=component.name):
                fields = {"%s.%s" % (component.name, key): value
                          for key, value in component.values.items()}
                moving = ScrollingText(component.name, laid_out_size)
                moving.start(fields, 0)
                places = [moving.place(fields)]
                for _ in range(150):
                    moving.step(fields, moving.due)
                    places.append(moving.place(fields))
                self.assert_passes_through(places, READINGS[component.name])

    def assert_passes_through(self, places: list, readings: list):
        """Asserts that `readings` come in `places` in order, one reading
        repeated, as when no step came between two pictures, standing for
        one place."""
        position = 0
        for reading in [value for index, value in enumerate(readings)
                        if index == 0 or value != readings[index - 1]]:
            self.assertIn(reading, places[position:], "%r: not reached in order" % reading)
            position = places.index(reading, position) + 1

    def test_the_place_not_used_holds_32767(self):
        fields = {"up.dir": 3, "up.y": 100, "up.h": 100, "up.en": 1, "up.tim": 1000,
                  "up.dis": 20, "up.txt": "Up"}
        moving = ScrollingText("up", lambda values: (20, 20))
        moving.start(fields, 0)
        self.assertEqual((fields["up.vvs0"], fields["up.vvs1"]), (UNUSED_PLACE, 200))


if __name__ == "__main__":
    unittest.main()
