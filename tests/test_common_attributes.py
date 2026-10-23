"""The attributes every type has, as the Editor's simulator showed them
(fixtures/attributes/): how opaque a component is drawn, `aph`, in the
font NotoSans20, and how components slide in as their page opens,
`effect`, `time`, and `first`."""
from pathlib import Path
import unittest

from nxwright.drawing.page_drawing import draw_page
from nxwright.drawing.screen_pictures import paint_drawing
from nxwright.project.pictures import read_picture
from nxwright.source.page_source import Component
from nxwright.testing.opening_effects import STEP, OpeningEffects
from tests.test_page_drawing import differing_pixels
from tests.test_scrolling_texts import ProbeFont, probe_components

FOLDER = Path(__file__).resolve().parent / "fixtures" / "attributes"


class OpacityTest(unittest.TestCase):
    """`aph`, against the Editor simulator's pictures, pixel for pixel."""

    def assert_drawn_alike(self, page: str, picture: str):
        components = probe_components(FOLDER / ("%s.page.toml" % page))
        drawn = paint_drawing(draw_page(components, ProbeFont()))
        shot = read_picture((FOLDER / picture).read_bytes())
        for component in components[1:]:
            with self.subTest(picture=picture, component=component.name):
                differing = differing_pixels(drawn, shot, component.values, 2)
                self.assertEqual(differing[:5], [], "%d pixels differ" % len(differing))

    def test_bars_from_clear_to_opaque(self):
        # Red bars of aph 0 to 127, each over the page's black and over a
        # white text. The Nextion Editor blends each channel by
        # under + (colour - under) * aph / 127, cut toward zero. The painter
        # blends by Pillow's rule, which stays within the comparison's
        # tolerance of 2.
        self.assert_drawn_alike("aph", "aph.png")

    def test_a_texts_words_over_its_background(self):
        # Blended part by part: the background, then the words over it, each
        # at aph 64; the same text opaque below it.
        self.assert_drawn_alike("parts", "parts.png")

    def test_what_is_marked(self):
        components = probe_components(FOLDER / "aph.page.toml")
        shapes = draw_page(components, ProbeFont())["shapes"]
        marks = {shape["component"]: shape.get("aph") for shape in shapes}
        # aph 0 adds no shape; 127, opaque, no mark; the page none.
        self.assertEqual({name: marks.get(name, "none") for name in ("r0", "r1", "r5", "page0")},
                         {"r0": "none", "r1": 16, "r5": None, "page0": None})

    def test_an_outline_stays_whole(self):
        # An outline stands in for what the preview cannot draw, such as a
        # picture the folder lacks, not for the screen's pixels: it is drawn
        # whole, whatever the component's aph.
        page = probe_components(FOLDER / "aph.page.toml")[0]
        for aph in (0, 64):
            missing = Component("p0", "picture", {"x": 10, "y": 10, "w": 50, "h": 50,
                                                  "pic": 3, "aph": aph})
            shapes = draw_page([page, missing], ProbeFont())["shapes"]
            with self.subTest(aph=aph):
                self.assertEqual([(shape["kind"], shape.get("aph")) for shape in shapes
                                  if shape["component"] == "p0"], [("outline", None)])


class OpeningEffectsTest(unittest.TestCase):
    """Components sliding in as their page opens (testing/opening_effects.py),
    as the Editor's simulator showed: a straight, steady slide from wholly
    off the screen beyond an edge or a corner, in groups by `first`, the
    highest first, the next group once the one before is in place."""

    # A text 120 by 60 at (420, 80), as the probe's e3, on a screen 800 by 480.
    PLACE = {"x": 420, "y": 80, "w": 120, "h": 60}

    def effects(self, *components, clock: int = 0) -> OpeningEffects:
        return OpeningEffects([(name, dict(self.PLACE, **values))
                               for name, values in components], (800, 480), clock)

    def test_where_each_effect_starts(self):
        starts = {1: (420, -60), 2: (420, 480), 3: (-120, 80), 4: (800, 80),
                  5: (-120, -60), 6: (800, -60), 7: (-120, 480), 8: (800, 480)}
        for effect, start in starts.items():
            with self.subTest(effect=effect):
                effects = self.effects(("t0", {"effect": effect, "time": 1000}))
                self.assertEqual(effects.place("t0", 0), start)

    def test_a_steady_slide_to_its_place(self):
        effects = self.effects(("t0", {"effect": 3, "time": 1000}), clock=500)
        self.assertEqual(effects.place("t0", 1000), (150, 80))     # halfway, from x -120
        self.assertIsNone(effects.place("t0", 1500))               # in place
        self.assertEqual(effects.waiting(500), set())

    def test_groups_by_first_the_highest_first(self):
        effects = self.effects(("a", {"effect": 3, "time": 600, "first": 0}),
                               ("b", {"effect": 3, "time": 400, "first": 50}),
                               ("c", {"effect": 1, "time": 200, "first": 50}),
                               ("d", {"effect": 3, "time": 300, "first": 100}))
        # d first; then b and c together, b the longer; then a.
        self.assertEqual(effects.waiting(0), {"a", "b", "c"})
        self.assertEqual(effects.waiting(300), {"a"})
        self.assertEqual(effects.place("c", 400), (420, 80 - 70))   # halfway: from -60 to 80
        self.assertIsNone(effects.place("c", 500))
        self.assertEqual(effects.waiting(699), {"a"})
        self.assertEqual(effects.waiting(700), set())
        self.assertIsNone(effects.place("a", 1300))

    def test_without_an_effect_nothing_moves(self):
        effects = self.effects(("t0", {"effect": 0, "time": 1000}))
        self.assertEqual((effects.place("t0", 0), effects.waiting(0), effects.next_step(0)),
                         (None, set(), None))

    def test_a_component_ended_is_in_place(self):
        # As when code hides or moves it, or a touch drags it (assumed).
        effects = self.effects(("t0", {"effect": 3, "time": 1000}),
                               ("t1", {"effect": 3, "time": 1000, "first": 5}))
        effects.end("t0")
        effects.end("t1")
        self.assertEqual((effects.place("t0", 100), effects.waiting(100)), (None, set()))

    def test_steps_while_any_slide_runs(self):
        effects = self.effects(("t0", {"effect": 3, "time": 100}))
        self.assertEqual(effects.next_step(0), STEP)
        self.assertEqual(effects.next_step(90), 100)    # its end, sooner than a step
        self.assertIsNone(effects.next_step(100))


if __name__ == "__main__":
    unittest.main()
