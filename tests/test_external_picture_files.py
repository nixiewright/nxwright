"""External pictures in the simulator: which files a screen of each series
shows, the error marker a screen draws for a file it cannot show, a picture
file kept in memory, and a file that is missing.

The files that show, and the marker, are the ones a real NX8048P070
(Intelligent) and a real NX4848E040 (Edge) showed. The answers for a
missing file are the ones the Nextion Editor's simulator gave for an
NX8048P050."""
import base64
import io
from pathlib import Path
import tempfile

from PIL import Image

from nxwright.drawing.screen_pictures import paint_drawing
from nxwright.project.media_files import CARD_PICTURE_QUALITIES, card_picture_file
from nxwright.project.pictures import write_png
from nxwright.testing.external_pictures import (MARKER, NOTHING, PICTURE, error_marker,
                                                file_kind, shown)
from nxwright.testing.file_packets import packets
from nxwright.testing.preview import Previews
from nxwright.testing.simulation import Simulation
from tests.test_folder_check import edited_app
from tests.test_simulation import SimulationTestCase, table

RED_COLOUR, BLUE_COLOUR = (255, 0, 0), (0, 0, 255)


def _saved(colour: tuple, form: str) -> bytes:
    """Returns a picture of 4 by 2 pixels of `colour`, as a file in the
    Pillow format `form`, such as "JPEG"."""
    file = io.BytesIO()
    Image.new("RGB", (4, 2), colour).save(file, form, **(
        {"quality": 95, "subsampling": 0} if form == "JPEG" else {}))
    return file.getvalue()


def _xi(colour: tuple) -> bytes:
    """Returns a picture of 4 by 2 pixels of `colour`, as a .xi file, the
    kind PictureBox writes."""
    return card_picture_file(Image.new("RGBA", (4, 2), colour + (255,)),
                             CARD_PICTURE_QUALITIES["highest"], 0)


RED = _saved(RED_COLOUR, "JPEG")
BLUE = _saved(BLUE_COLOUR, "JPEG")
RED_XI = _xi(RED_COLOUR)
RED_PNG = write_png(4, 2, bytes([255, 0, 0, 255]) * 8)
RED_GIF = _saved(RED_COLOUR, "GIF")
TEXT = b"not a picture"
CUT_XI = b"hmipicxi" + bytes(30)
IGNORED = bytes.fromhex("06 ff ff ff")
XI = Path(__file__).resolve().parent / "fixtures" / "media" / "xi" / "odd-96-0.xi"
EDGE = "NX4848E040"


class ExternalPictureTestCase(SimulationTestCase):

    def started(self, path: str, files: dict = None, screen: str = None, w: int = 100,
                h: int = 50, **options) -> Simulation:
        """Starts a simulation whose page has an external picture, `p0`, of
        `w` by `h` pixels, that shows the file at `path`. `files` are the
        files kept in memory, {path: bytes}, and the project sets 4096 bytes
        aside for `ram/` files. The project's screen is an NX8048P050, of
        the Intelligent series, unless `screen` gives another. The bytes the
        simulation sends are in `self.sent`."""
        def settings(app):
            app.update(memory_file_storage_size=4096)
            if screen is not None:
                app.update(screen=screen)
        self.write("app.toml", edited_app(self.text("app.toml"), settings))
        self.page("page0", [table("p0", "external-picture", x=10, y=20, w=w, h=h, path=path)])
        self.sent = []
        self.previews = Previews()
        return Simulation(self.root, sending=self.sent.append,
                          values={"file contents": dict(files or {})}, **options)

    def drawing(self, simulation: Simulation) -> dict:
        return self.previews.simulation_drawing(simulation, simulation.drawing_inputs())

    def shapes(self, drawing: dict) -> list:
        return [shape for shape in drawing["shapes"] if shape["component"] == "p0"]

    def colour_shown(self, simulation: Simulation, at: tuple = (10, 20)) -> tuple:
        """The colour the painter draws at `at`, by default the external
        picture's top left."""
        return paint_drawing(self.drawing(simulation)).getpixel(at)[:3]

    def assertColour(self, colour: tuple, expected: tuple):
        """Checks `colour` against `expected`, give or take what a JPEG
        picture loses."""
        self.assertTrue(all(abs(one - other) <= 12 for one, other in zip(colour, expected)),
                        (colour, expected))

    def marker_of(self, drawing: dict) -> Image.Image:
        """The picture of the marker that `p0` shows in `drawing`."""
        shape, = self.shapes(drawing)
        self.assertEqual((shape["kind"], shape["x"], shape["y"], shape["rotation"]),
                         ("picture", 10, 20, 0))
        self.assertTrue(shape["picture"].startswith("marker:"), shape["picture"])
        data = drawing["pictureFiles"][shape["picture"]]["data"]
        return Image.open(io.BytesIO(base64.b64decode(data.split(",", 1)[1]))).convert("RGBA")

    def refusals(self) -> int:
        refusals = self.sent.count(IGNORED)
        self.sent.clear()
        return refusals


class WhatEachFileShowsTest(ExternalPictureTestCase):
    """Which kinds of file a screen shows depends on its series. The kind
    of a file comes from its bytes, whatever its name."""

    def test_the_kind_of_a_file_comes_from_its_bytes(self):
        kinds = [file_kind(data) for data in (RED_XI, RED, RED_PNG, RED_GIF, TEXT, b"")]
        self.assertEqual(len(set(kinds[:2])), 2)
        self.assertEqual(len(set(kinds[2:])), 1)
        # A file that starts as a JPEG or a .xi file, and cannot be read.
        self.assertEqual(file_kind(CUT_XI), file_kind(RED[:20]))
        self.assertNotIn(file_kind(CUT_XI), kinds)

    def test_what_each_series_shows(self):
        files = (RED_XI, RED, RED_PNG, RED_GIF, TEXT, CUT_XI, RED[:20])
        for series, expected in (
                ("P", (PICTURE, PICTURE, MARKER, MARKER, MARKER, MARKER, MARKER)),
                ("E", (PICTURE, MARKER, NOTHING, NOTHING, NOTHING, MARKER, MARKER)),
                # A screen nxwright does not know shows what the Intelligent series does.
                (None, (PICTURE, PICTURE, MARKER, MARKER, MARKER, MARKER, MARKER))):
            with self.subTest(series=series):
                self.assertEqual(tuple(shown(file_kind(data), series) for data in files),
                                 expected)

    def test_on_an_intelligent_screen(self):
        for name, data in (("p.jpg", RED), ("p.xi", RED_XI), ("p.png", RED)):
            with self.subTest(name=name):
                simulation = self.started("ram/" + name, {"ram/" + name: data})
                self.assertColour(self.colour_shown(simulation), RED_COLOUR)
        for name, data in (("p.png", RED_PNG), ("p.gif", RED_GIF), ("p.txt", TEXT),
                           ("p.jpg", RED_PNG), ("cut.xi", CUT_XI)):
            with self.subTest(name=name):
                simulation = self.started("ram/" + name, {"ram/" + name: data})
                self.marker_of(self.drawing(simulation))

    def test_on_an_edge_screen(self):
        simulation = self.started("ram/p.xi", {"ram/p.xi": RED_XI}, screen=EDGE)
        self.assertColour(self.colour_shown(simulation), RED_COLOUR)
        for name, data in (("p.jpg", RED), ("cut.xi", CUT_XI)):
            with self.subTest(name=name):
                simulation = self.started("ram/" + name, {"ram/" + name: data}, screen=EDGE)
                self.marker_of(self.drawing(simulation))
        for name, data in (("p.png", RED_PNG), ("p.txt", TEXT)):
            with self.subTest(name=name):
                simulation = self.started("ram/" + name, {"ram/" + name: data}, screen=EDGE)
                self.assertEqual(self.shapes(self.drawing(simulation)), [])

    def test_a_file_in_a_cards_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "p.png").write_bytes(RED_PNG)
            (Path(folder) / "p.jpg").write_bytes(RED)
            simulation = self.started("sd0/p.png", cards={"sd0/": Path(folder)})
            self.marker_of(self.drawing(simulation))
            simulation.serial_input('p0.path="sd0/p.jpg"')
            self.assertColour(self.colour_shown(simulation), RED_COLOUR)

    def test_the_log_gives_the_kinds_of_file_the_screen_shows(self):
        for screen, reason in (
                (None, "this screen shows only JPEG and .xi files. `nxwright sd-picture` "
                       "converts a picture to a .xi file."),
                (EDGE, "this screen shows only .xi files. `nxwright sd-picture` converts a "
                       "picture to a .xi file.")):
            with self.subTest(screen=screen):
                simulation = self.started("ram/p.png", {"ram/p.png": RED_PNG}, screen=screen)
                self.assertIn("p0 cannot show ram/p.png: " + reason,
                              [line for _, line in simulation.log])
                self.assertEqual(self.refusals(), 0)

    def test_the_log_says_when_a_file_is_damaged(self):
        simulation = self.started("ram/cut.xi", {"ram/cut.xi": CUT_XI})
        self.assertIn("p0 cannot show ram/cut.xi: the file is damaged",
                      [line for _, line in simulation.log])


class MarkerTest(ExternalPictureTestCase):
    """The error marker: "Show Picture Error!" in red on blue, from the
    component's top left, wrapped at its width and cut at its bottom."""

    def colours(self, marker: Image.Image) -> set:
        """Returns which of "blue", "red", and "clear" pixels `marker` has.
        A clear pixel is wholly transparent."""
        pixels = [marker.getpixel((x, y)) for y in range(marker.height)
                  for x in range(marker.width)]
        return {name for name, test in (
            ("blue", lambda p: p[3] == 255 and p[2] > 200 and p[0] < 60 and p[1] < 60),
            ("red", lambda p: p[3] == 255 and p[0] > 200 and p[2] < 60 and p[1] < 60),
            ("clear", lambda p: p[3] == 0)) if any(test(pixel) for pixel in pixels)}

    def test_one_line_in_a_wide_component(self):
        simulation = self.started("ram/p.txt", {"ram/p.txt": TEXT}, w=300, h=150)
        marker = self.marker_of(self.drawing(simulation))
        self.assertEqual(marker.height, 16)
        self.assertLess(marker.width, 300)
        self.assertEqual(self.colours(marker), {"blue", "red"})
        painted = paint_drawing(self.drawing(simulation))
        self.assertEqual(painted.getpixel((10, 20))[:3], BLUE_COLOUR)
        # Nothing is drawn below the marker, or to its right.
        page_colour = painted.getpixel((700, 400))[:3]
        self.assertEqual(painted.getpixel((10, 20 + 16))[:3], page_colour)
        self.assertEqual(painted.getpixel((10 + marker.width, 20))[:3], page_colour)

    def test_the_text_wraps_in_a_narrow_component(self):
        wide = Image.open(io.BytesIO(error_marker(300, 150)))
        narrow = Image.open(io.BytesIO(error_marker(wide.width - 30, 150))).convert("RGBA")
        self.assertEqual((narrow.height, narrow.width <= wide.width - 30), (32, True))
        # The second line is shorter, and the picture is clear beside it.
        self.assertEqual(self.colours(narrow), {"blue", "red", "clear"})
        self.assertEqual(narrow.getpixel((narrow.width - 1, 24))[3], 0)

    def test_the_text_stops_at_the_bottom_of_a_low_component(self):
        self.assertEqual(Image.open(io.BytesIO(error_marker(40, 30))).height, 32)
        self.assertEqual(Image.open(io.BytesIO(error_marker(40, 16))).height, 16)
        simulation = self.started("ram/p.txt", {"ram/p.txt": TEXT}, w=40, h=30)
        painted = paint_drawing(self.drawing(simulation))
        # The second line is cut at the component's bottom.
        self.assertEqual(painted.getpixel((10, 20 + 29))[:3], BLUE_COLOUR)
        self.assertEqual(painted.getpixel((10, 20 + 30))[:3], painted.getpixel((700, 400))[:3])

    def test_two_sizes_on_one_file(self):
        self.write("app.toml", edited_app(self.text("app.toml"),
                                          lambda app: app.update(memory_file_storage_size=4096)))
        self.page("page0", [table("p0", "external-picture", x=10, y=20, w=300, h=50,
                                  path="ram/p.txt"),
                            table("p1", "external-picture", x=10, y=200, w=40, h=50,
                                  path="ram/p.txt")])
        self.previews = Previews()
        simulation = Simulation(self.root, values={"file contents": {"ram/p.txt": TEXT}})
        drawing = self.drawing(simulation)
        names = [shape["picture"] for shape in drawing["shapes"]
                 if shape["component"] in ("p0", "p1")]
        self.assertEqual(len(set(names)), 2)
        heights = [Image.open(io.BytesIO(base64.b64decode(
            drawing["pictureFiles"][name]["data"].split(",", 1)[1]))).height for name in names]
        self.assertEqual((heights[0], heights[1] > 16), (16, True))

    def test_upright_on_a_turned_screen(self):
        self.write("app.toml", edited_app(self.text("app.toml"),
                                          lambda app: app.update(rotation=90)))
        simulation = self.started("ram/p.txt", {"ram/p.txt": TEXT}, w=300, h=150)
        marker = self.marker_of(self.drawing(simulation))
        self.assertEqual(marker.height, 16)

    def test_a_picture_sent_to_the_same_path_replaces_the_marker(self):
        simulation = self.started("ram/p.xi", {"ram/p.xi": TEXT})
        self.marker_of(self.drawing(simulation))
        simulation.serial_input('twfile "ram/p.xi",%d' % len(RED_XI))
        simulation.serial_received(b"".join(packets(RED_XI)))
        simulation.serial_input('p0.path="ram/p.xi"')
        self.assertColour(self.colour_shown(simulation), RED_COLOUR)

    def test_a_picture_written_over_a_file_in_a_cards_folder_replaces_the_marker(self):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / "p.xi"
            file.write_bytes(TEXT)
            simulation = self.started("sd0/p.xi", cards={"sd0/": Path(folder)})
            self.marker_of(self.drawing(simulation))
            file.write_bytes(RED_XI)
            self.assertColour(self.colour_shown(simulation), RED_COLOUR)

    def test_a_file_is_read_once_for_two_drawings(self):
        simulation = self.started("ram/p.txt", {"ram/p.txt": TEXT})
        first = self.drawing(simulation)
        data = simulation.values()["file contents"]["ram/p.txt"]
        readings = self.previews._memory_version("ram/p.txt", data)[2]
        self.assertEqual(len(readings), 1)
        kept = dict(readings)
        self.assertEqual(self.drawing(simulation)["shapes"], first["shapes"])
        self.assertEqual(self.previews._memory_version("ram/p.txt", data)[2], kept)


class MemoryFileTest(ExternalPictureTestCase):
    """An external picture shows a picture file that is kept in memory."""

    def test_a_jpeg_in_ram_and_on_a_card_given_no_folder(self):
        for path in ("ram/p.jpg", "sd0/p.jpg"):
            with self.subTest(path=path):
                simulation = self.started(path, {path: RED})
                drawing = self.drawing(simulation)
                shape, = self.shapes(drawing)
                self.assertEqual((shape["kind"], shape["card"], shape["x"], shape["y"]),
                                 ("picture", True, 10, 20))
                data = drawing["pictureFiles"][shape["picture"]]["data"]
                self.assertEqual(base64.b64decode(data.split(",", 1)[1]), RED)
                self.assertColour(self.colour_shown(simulation), RED_COLOUR)
                self.assertEqual(self.refusals(), 0)

    def test_a_picturebox_xi_file(self):
        simulation = self.started("ram/odd.xi", {"ram/odd.xi": XI.read_bytes()})
        drawing = self.drawing(simulation)
        shape, = self.shapes(drawing)
        found = drawing["pictureFiles"][shape["picture"]]
        self.assertTrue(found["data"].startswith("data:image/jpeg;base64,/9j/"))
        self.assertIn("mask", found)

    def test_new_bytes_show_in_the_next_drawing(self):
        simulation = self.started("ram/p.jpg", {"ram/p.jpg": RED})
        first = self.shapes(self.drawing(simulation))[0]["picture"]
        self.assertColour(self.colour_shown(simulation), RED_COLOUR)
        simulation.serial_input('twfile "ram/p.jpg",%d' % len(BLUE))
        simulation.serial_received(b"".join(packets(BLUE)))
        simulation.serial_input('p0.path="ram/p.jpg"')
        self.assertNotEqual(self.shapes(self.drawing(simulation))[0]["picture"], first)
        self.assertColour(self.colour_shown(simulation), BLUE_COLOUR)

    def test_a_picture_that_twfile_puts_in_ram(self):
        simulation = self.started("")
        self.assertEqual(self.shapes(self.drawing(simulation)), [])
        simulation.serial_input('twfile "ram/p.jpg",%d' % len(RED))
        simulation.serial_received(b"".join(packets(RED)))
        simulation.serial_input('p0.path="ram/p.jpg"')
        self.assertColour(self.colour_shown(simulation), RED_COLOUR)
        self.assertEqual(self.refusals(), 0)

    def test_two_files_with_the_same_bytes_have_two_names(self):
        simulation = self.started("ram/p.jpg", {"ram/p.jpg": RED, "sd0/p.jpg": RED})
        first = self.shapes(self.drawing(simulation))[0]["picture"]
        simulation.serial_input('p0.path="sd0/p.jpg"')
        self.assertNotEqual(self.shapes(self.drawing(simulation))[0]["picture"], first)
        self.assertColour(self.colour_shown(simulation), RED_COLOUR)

    def test_the_same_bytes_keep_their_name(self):
        simulation = self.started("ram/p.jpg", {"ram/p.jpg": RED})
        first = self.shapes(self.drawing(simulation))[0]["picture"]
        simulation.serial_input("sys0=1")
        self.assertEqual(self.shapes(self.drawing(simulation))[0]["picture"], first)

    def test_a_cards_folder_comes_before_memory(self):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder).resolve() / "p.jpg"
            file.write_bytes(RED)
            simulation = self.started("sd0/p.jpg", {"sd0/p.jpg": BLUE},
                                      cards={"sd0/": Path(folder)})
            drawing = self.drawing(simulation)
            shape, = self.shapes(drawing)
            self.assertEqual(shape["picture"], str(file))
            self.assertEqual(drawing["pictureFiles"][str(file)]["path"], str(file))

    def test_a_path_on_no_card_draws_nothing(self):
        simulation = self.started("p.jpg", {"p.jpg": RED})
        self.assertEqual(self.shapes(self.drawing(simulation)), [])


class MissingFileTest(ExternalPictureTestCase):
    """An external picture whose file is missing answers 0x06."""

    def log(self, simulation: Simulation) -> list:
        return [line for _, line in simulation.log]

    def test_when_its_page_opens(self):
        simulation = self.started("sd0/missing.jpg")
        self.assertEqual(self.refusals(), 1)
        self.assertIn("p0 cannot show sd0/missing.jpg: there is no such file",
                      self.log(simulation))
        self.assertEqual(self.shapes(self.drawing(simulation)), [])

    def test_when_a_page_change_opens_its_page(self):
        self.page("second", [table("p1", "external-picture", x=10, y=20, w=100, h=50,
                                   path="ram/missing.jpg")])
        simulation = self.started("")
        simulation.serial_input("page second")
        self.assertEqual(self.refusals(), 1)
        self.assertIn("p1 cannot show ram/missing.jpg: there is no such file",
                      self.log(simulation))

    def test_when_code_sets_its_path(self):
        simulation = self.started("ram/p.jpg", {"ram/p.jpg": RED, "ram/bad.jpg": TEXT})
        self.assertEqual(self.refusals(), 0)
        simulation.serial_input('p0.path="ram/missing.jpg"')
        self.assertEqual(self.refusals(), 1)
        self.assertIn("p0 cannot show ram/missing.jpg: there is no such file",
                      self.log(simulation))
        for path in ("ram/bad.jpg", "ram/p.jpg", ""):
            with self.subTest(path=path):
                simulation.serial_input('p0.path="%s"' % path)
                self.assertEqual(self.refusals(), 0)

    def test_with_a_card_given_a_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "p.jpg").write_bytes(RED)
            simulation = self.started("sd0/p.jpg", cards={"sd0/": Path(folder)})
            self.assertEqual(self.refusals(), 0)
            simulation.serial_input('p0.path="sd0/missing.jpg"')
            self.assertEqual(self.refusals(), 1)

    def test_an_empty_path_and_a_path_on_no_card_answer_nothing(self):
        simulation = self.started("")
        self.assertEqual(self.refusals(), 0)
        simulation.serial_input('p0.path="x.jpg"')
        self.assertEqual(self.refusals(), 0)

    def test_a_hidden_external_picture_answers_nothing(self):
        simulation = self.started("ram/p.jpg", {"ram/p.jpg": RED})
        simulation.serial_input("vis p0,0")
        simulation.serial_input('p0.path="ram/missing.jpg"')
        self.assertEqual(self.refusals(), 0)

    def test_an_external_picture_that_the_load_event_hides_answers_nothing(self):
        self.write("app.toml", edited_app(self.text("app.toml"),
                                          lambda app: app.update(memory_file_storage_size=4096)))
        self.page("page0", [table("p0", "external-picture", x=10, y=20, w=100, h=50,
                                  path="sd0/missing.jpg"),
                            table("p1", "external-picture", x=10, y=90, w=100, h=50,
                                  path="sd0/missing.jpg")],
                  "on page0.load:\n  vis p0,0\n")
        self.sent = []
        Simulation(self.root, sending=self.sent.append)
        self.assertEqual(self.refusals(), 1)

    def test_a_path_set_in_the_load_event_answers_once(self):
        self.write("app.toml", edited_app(self.text("app.toml"),
                                          lambda app: app.update(memory_file_storage_size=4096)))
        self.page("page0", [table("p0", "external-picture", x=10, y=20, w=100, h=50, path="")],
                  'on page0.load:\n  p0.path="ram/missing.jpg"\n')
        self.sent = []
        Simulation(self.root, sending=self.sent.append)
        self.assertEqual(self.refusals(), 1)

    def test_a_file_the_screen_does_not_show_is_logged_each_time(self):
        simulation = self.started("ram/bad.jpg", {"ram/bad.jpg": TEXT, "ram/p.jpg": RED})
        start = "p0 cannot show ram/bad.jpg: "
        logged = lambda: sum(line.startswith(start) for line in self.log(simulation))
        self.assertEqual((logged(), self.refusals()), (1, 0))
        simulation.serial_input('p0.path="ram/p.jpg"')
        simulation.serial_input('p0.path="ram/bad.jpg"')
        self.assertEqual((logged(), self.refusals()), (2, 0))
        self.assertEqual([entry for entry in self.log(simulation)
                          if entry.startswith("p0 cannot show ram/p.jpg")], [])
