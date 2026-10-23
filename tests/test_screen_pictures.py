"""Pictures of what a simulation's screen shows, painted as the simulator's
panel paints them (nxwright/drawing/screen_pictures.py), and the drawing
they are painted from (testing/preview.py, Previews.simulation_drawing)."""
import base64
import io
from pathlib import Path
import tempfile
import unittest

from PIL import Image

from nxwright.drawing.screen_pictures import ScreenPictures, paint_drawing
from nxwright.project.pictures import write_png
from nxwright.testing.preview import Previews
from nxwright.testing.simulation import Simulation
from tests.test_simulation import SimulationTestCase, placed

RED, GREEN, BLUE = "#ff0000", "#00ff00", "#0000ff"


def drawing(*shapes, start=1, entry=1, transparent=False, width=4, height=2, **more) -> dict:
    """A simulation's drawing of a page `width` by `height`, of `shapes`."""
    return dict({"width": width, "height": height, "transparent": transparent,
                 "shapes": list(shapes), "page": "page0", "dim": 100, "asleep": False,
                 "start": start, "entry": entry, "pictureFiles": {}}, **more)


def colour(x: int, y: int, w: int, h: int, hex_colour: str, **more) -> dict:
    return dict({"kind": "colour", "x": x, "y": y, "w": w, "h": h, "colour": hex_colour},
                **more)


def pixels_of(png: bytes, *points) -> list:
    """The colours of a PNG's pixels at `points`, (x, y) each."""
    image = Image.open(io.BytesIO(png)).convert("RGB")
    return [image.getpixel(point) for point in points]


def data_url(png: bytes) -> str:
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


class ScreenPicturesTest(unittest.TestCase):

    def picture(self, *drawings) -> bytes:
        pictures = ScreenPictures()
        for shown in drawings:
            pictures.shown(shown)
        return pictures.picture()

    def test_the_latest_drawing_as_a_png(self):
        png = self.picture(drawing(colour(0, 0, 4, 2, BLUE)), drawing(colour(0, 0, 4, 2, RED)))
        self.assertEqual(pixels_of(png, (0, 0), (3, 1)), [(255, 0, 0), (255, 0, 0)])

    def test_nothing_shown_yet(self):
        with self.assertRaises(ValueError):
            ScreenPictures().picture()

    def test_its_brightness_and_sleep(self):
        # As the panel shows it: `dim` 50 shows every colour at half, and a
        # sleeping screen is dark.
        self.assertEqual(pixels_of(self.picture(drawing(colour(0, 0, 4, 2, RED), dim=50)),
                                   (0, 0)), [(128, 0, 0)])
        self.assertEqual(pixels_of(self.picture(drawing(colour(0, 0, 4, 2, RED), asleep=True)),
                                   (0, 0)), [(0, 0, 0)])

    def test_a_page_without_background_over_the_screen_it_was_entered_over(self):
        before = drawing(colour(0, 0, 4, 2, RED))
        entered = drawing(colour(0, 0, 1, 1, BLUE), entry=2, transparent=True)
        self.assertEqual(pixels_of(self.picture(before, entered), (0, 0), (1, 0)),
                         [(0, 0, 255), (255, 0, 0)])
        # Drawn again, it is laid over the same screen, not over itself.
        again = drawing(colour(2, 0, 1, 1, BLUE), entry=2, transparent=True)
        self.assertEqual(pixels_of(self.picture(before, entered, again), (0, 0), (2, 0)),
                         [(255, 0, 0), (0, 0, 255)])
        # A backdrop shape shows that screen again over what was painted.
        covered = drawing(colour(0, 0, 4, 2, GREEN),
                          {"kind": "backdrop", "x": 1, "y": 0, "w": 1, "h": 1},
                          entry=2, transparent=True)
        self.assertEqual(pixels_of(self.picture(before, covered), (0, 0), (1, 0)),
                         [(0, 255, 0), (255, 0, 0)])

    def test_a_picture_asked_for_between_drawings_of_one_page(self):
        # Painting a picture lets go of nothing the next drawing of the same
        # page is drawn over.
        pictures = ScreenPictures()
        pictures.shown(drawing(colour(0, 0, 4, 2, RED)))
        pictures.shown(drawing(colour(0, 0, 1, 1, BLUE), entry=2, transparent=True))
        pictures.picture()
        pictures.shown(drawing(colour(2, 0, 1, 1, BLUE), entry=2, transparent=True))
        self.assertEqual(pixels_of(pictures.picture(), (0, 0), (2, 0)),
                         [(255, 0, 0), (0, 0, 255)])

    def test_black_after_a_start(self):
        before = drawing(colour(0, 0, 4, 2, RED))
        started = drawing(colour(0, 0, 1, 1, BLUE), start=2, transparent=True)
        self.assertEqual(pixels_of(self.picture(before, started), (1, 0)), [(0, 0, 0)])

    def test_many_pages_without_background_in_turn(self):
        # Each entered over the one before. Up to eight of them in turn, the
        # first's red still shows where none of them painted. Past eight,
        # the oldest drawings are let go unpainted, and what lay under them
        # shows black there. What the later pages painted still shows.
        for pages, shown_at_the_corner in ((8, (255, 0, 0)), (9, (0, 0, 0)), (40, (0, 0, 0))):
            with self.subTest(pages=pages):
                shown = [drawing(colour(0, 0, 4, 2, RED))]
                for entry in range(2, pages + 2):
                    shown.append(drawing(colour(entry % 2, 1, 1, 1, BLUE), entry=entry,
                                         transparent=True))
                self.assertEqual(pixels_of(self.picture(*shown), (3, 0), (0, 1), (1, 1)),
                                 [shown_at_the_corner, (0, 0, 255), (0, 0, 255)])

    def test_pictures_read_from_the_drawing_in_the_screens_colours(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "dot.png"
            path.write_bytes(write_png(2, 1, bytes((200, 100, 50, 255)) * 2))
            # Half transparent: the screen keeps no alpha, so it is flattened
            # on white, as the build stores it.
            half = data_url(write_png(1, 1, bytes((255, 0, 0, 128))))
            files = {"dot": {"path": str(path), "version": "1"},
                     "half": {"data": half, "version": "1"}}
            png = self.picture(drawing(
                {"kind": "picture", "picture": "dot", "x": 0, "y": 0, "w": 2, "h": 1,
                 "sx": 0, "sy": 0},
                {"kind": "picture", "picture": "half", "x": 2, "y": 0, "w": 1, "h": 1,
                 "sx": 0, "sy": 0, "opaque": True},
                # Not among the drawing's pictures: left out.
                {"kind": "picture", "picture": "gone", "x": 3, "y": 0, "w": 1, "h": 1,
                 "sx": 0, "sy": 0},
                pictureFiles=files))
        # 5 bits of red and blue, 6 of green, widened by repeating their top bits.
        self.assertEqual(pixels_of(png, (0, 0), (2, 0), (3, 0)),
                         [(206, 101, 49), (255, 125, 123), (0, 0, 0)])

    def test_a_cards_picture_in_its_own_colours_through_its_mask(self):
        card = data_url(write_png(2, 1, bytes((200, 100, 50, 255)) * 2))
        mask = data_url(write_png(2, 1, bytes((0, 0, 0, 0, 0, 0, 0, 255))))
        png = self.picture(drawing(
            {"kind": "picture", "picture": "photo", "x": 0, "y": 0, "w": 2, "h": 1,
             "sx": 0, "sy": 0, "card": True},
            pictureFiles={"photo": {"data": card, "mask": mask, "version": "1"}}))
        self.assertEqual(pixels_of(png, (0, 0), (1, 0)), [(0, 0, 0), (200, 100, 50)])

    def test_plain_text_and_an_outline(self):
        # Written in an ordinary font, close enough to read.
        png = self.picture(drawing(
            {"kind": "plainText", "x": 0, "y": 0, "w": 30, "h": 20, "text": "WW",
             "colour": GREEN, "size": 16, "xcen": 0, "ycen": 0},
            {"kind": "outline", "x": 40, "y": 0, "w": 30, "h": 20, "label": "tm0"},
            width=80, height=20))
        image = Image.open(io.BytesIO(png)).convert("RGB")
        text = {image.getpixel((x, y)) for x in range(30) for y in range(20)}
        self.assertIn((0, 255, 0), text)
        self.assertEqual({image.getpixel((x, y)) for x in range(30, 40) for y in range(20)},
                         {(0, 0, 0)})
        self.assertEqual(image.getpixel((40, 0)), (255, 64, 255))

    def test_painted_over_a_screen_given(self):
        # As the tests compare a page with the Nextion Editor's pictures:
        # painted alone, over a screen given for a page without background.
        under = Image.new("RGB", (4, 2), (255, 0, 0))
        page = paint_drawing(drawing(colour(0, 0, 1, 1, BLUE), transparent=True), under)
        self.assertEqual((page.getpixel((0, 0)), page.getpixel((1, 0))),
                         ((0, 0, 255), (255, 0, 0)))


class SimulationDrawingTest(SimulationTestCase):

    def test_what_the_screen_needs_beside_the_page_drawing(self):
        self.program("dim=40\npage page0\n")
        self.page("page0", [placed("t0", "text", 0, 0)])
        simulation = Simulation(self.root)
        drawing = Previews().simulation_drawing(simulation, simulation.drawing_inputs())
        self.assertEqual({key: drawing[key] for key in ("page", "dim", "asleep", "start",
                                                        "entry", "width")},
                         {"page": "page0", "dim": 40, "asleep": False, "start": 1,
                          "entry": 1, "width": 800})
        self.assertIn("pictureFiles", drawing)
