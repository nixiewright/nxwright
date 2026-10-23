"""Sliding texts, drawn and laid out (drawing/sliding_text_drawing.py), against
the Editor's simulator running two pages of fixtures/sliding-text/:
scrolled.page.toml, five sliding texts scrolled by code to 25 and to 1000,
and lines.page.toml, four scrolled a pixel at a time or to 1000, all in the
font NotoSans20. readings.toml says what each picture showed."""
from pathlib import Path
import tomllib
import unittest

from PIL import Image

from nxwright.drawing.page_drawing import draw_page, inside_box
from nxwright.drawing.screen_pictures import paint_drawing
from nxwright.drawing.sliding_text_drawing import sliding_layout
from nxwright.project.pictures import read_picture
from nxwright.source.page_source import Component
from tests.test_page_drawing import differing_pixels
from tests.test_scrolling_texts import FONT, ProbeFont, probe_components

FOLDER = Path(__file__).resolve().parent / "fixtures" / "sliding-text"
READINGS = tomllib.loads((FOLDER / "readings.toml").read_text(encoding="utf-8"))

# Where nxwright's drawing differs from the Editor's pictures, by page and
# picture. In "scrolled", code pushed se's two lines up past where they fit,
# and the Editor then wrapped its first line one character sooner. In
# "lines", the Editor drew sa's scroll bar's thumb one pixel higher than
# nxwright places it, as at about one `val_y` in three, for no rule found.
DIFFERING = {("scrolled", "scrolled-25.png"): {"se"}, ("scrolled", "scrolled-1000.png"): {"se"},
             ("lines", "lines-1000.png"): {"sa"}}


def sliding_texts(page: str) -> list:
    """The page of `page`.page.toml and its sliding texts."""
    return probe_components(FOLDER / ("%s.page.toml" % page), "sliding-text")


def scrolled_to(component: Component, val_y: int, **values) -> Component:
    """`component` scrolled to `val_y`, with `values` changed, its `maxval_y`
    worked out as the screen does."""
    values = dict(component.values, **values)
    layout = sliding_layout(values, FONT, "iso-8859-1", inside_box(values))
    return Component(component.name, component.type,
                     dict(values, val_y=val_y, maxval_y=layout.most))


class EditorSlidingTextTest(unittest.TestCase):

    def test_drawn_as_the_editor_shows_them(self):
        for page in ("scrolled", "lines"):
            components = sliding_texts(page)
            for picture, readings in READINGS[page]["val_y"].items():
                moved = [scrolled_to(component, readings[component.name])
                         for component in components[1:]]
                drawn = paint_drawing(draw_page(components[:1] + moved, ProbeFont()))
                shot = read_picture((FOLDER / picture).read_bytes())
                for component in moved:
                    if component.name in DIFFERING.get((page, picture), ()):
                        continue
                    with self.subTest(picture=picture, component=component.name):
                        self.assert_drawn_alike(component, drawn, shot)

    def assert_drawn_alike(self, component: Component, drawn: Image.Image, shot):
        differing = differing_pixels(drawn, shot, component.values, 2)
        self.assertEqual(differing[:5], [], "%d pixels differ" % len(differing))

    def test_how_far_they_scroll(self):
        # `maxval_y` as the screen worked it out, and the farthest code may
        # scroll each, where `val_y` 1000 left it. Of "lines", sa and sb
        # moved a pixel at a time, never to 1000.
        for page, last in (("scrolled", "scrolled-1000.png"), ("lines", "lines-1000.png")):
            for component in sliding_texts(page)[1:]:
                layout = sliding_layout(component.values, FONT, "iso-8859-1",
                                        inside_box(component.values))
                with self.subTest(page=page, component=component.name):
                    self.assertEqual(layout.most, READINGS[page]["maxval_y"][component.name])
                    if not (page == "lines" and component.name in ("sa", "sb")):
                        self.assertEqual(layout.farthest,
                                         READINGS[page]["val_y"][last][component.name])


class FarthestTest(unittest.TestCase):

    def test_drawn_no_further_than_code_may_scroll_it(self):
        # As the simulator settles `val_y`, so that the preview shows what it
        # would of a page file's: up to 32 pixels above the top too.
        page, sa = sliding_texts("scrolled")[:2]
        self.assertEqual(draw_page([page, scrolled_to(sa, 1000)], ProbeFont())["shapes"],
                         draw_page([page, scrolled_to(sa, 82)], ProbeFont())["shapes"])
        self.assertEqual(draw_page([page, scrolled_to(sa, -1000)], ProbeFont())["shapes"],
                         draw_page([page, scrolled_to(sa, -32)], ProbeFont())["shapes"])


class ScrollBarTest(unittest.TestCase):
    """The scroll bar's thumb, by `left`: 0 never, 1 while drawn pressed, as a
    simulation draws one a touch scrolls (Simulation._drawn_pressed), 2 always,
    and none when the lines fit."""

    def setUp(self):
        self.page, *self.texts = sliding_texts("scrolled")

    def drawn(self, component: Component, pressed: bool = False) -> list:
        return draw_page([self.page, component], ProbeFont(),
                         pressed=component.name if pressed else None)["shapes"]

    def test_by_left(self):
        sb = self.texts[1]
        shown = self.drawn(scrolled_to(sb, 25, left=2))
        hidden = self.drawn(scrolled_to(sb, 25, left=1))
        self.assertNotEqual(shown, hidden)
        self.assertEqual(self.drawn(scrolled_to(sb, 25, left=1), pressed=True), shown)
        self.assertEqual(self.drawn(scrolled_to(sb, 25, left=0), pressed=True), hidden)

    def test_none_when_the_lines_fit(self):
        _, *texts = sliding_texts("lines")
        s3 = texts[3]
        self.assertEqual(scrolled_to(s3, 0).values["maxval_y"], 0)
        self.assertEqual(self.drawn(scrolled_to(s3, 0, left=2)),
                         self.drawn(scrolled_to(s3, 0, left=0)))


if __name__ == "__main__":
    unittest.main()
