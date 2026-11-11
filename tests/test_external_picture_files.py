"""External pictures in the simulator: a picture file kept in memory, and a
file that is missing. Each expected answer is the one the Nextion Editor's
simulator gave for an NX8048P050."""
import base64
from pathlib import Path
import tempfile

from nxwright.drawing.screen_pictures import paint_drawing
from nxwright.project.pictures import write_png
from nxwright.testing.preview import Previews
from nxwright.testing.simulation import Simulation
from tests.test_folder_check import edited_app
from tests.test_simulation import SimulationTestCase, table

RED = write_png(4, 2, bytes([255, 0, 0, 255]) * 8)
BLUE = write_png(4, 2, bytes([0, 0, 255, 255]) * 8)
IGNORED = bytes.fromhex("06 ff ff ff")
XI = Path(__file__).resolve().parent / "fixtures" / "media" / "xi" / "odd-96-0.xi"


class ExternalPictureTestCase(SimulationTestCase):

    def started(self, path: str, files: dict = None, **options) -> Simulation:
        """Starts a simulation whose page has an external picture, `p0`, that
        shows the file at `path`. `files` are the files kept in memory,
        {path: bytes}, and the project sets 4096 bytes aside for `ram/`
        files. The bytes the simulation sends are in `self.sent`."""
        self.write("app.toml", edited_app(self.text("app.toml"),
                                          lambda app: app.update(memory_file_storage_size=4096)))
        self.page("page0", [table("p0", "external-picture", x=10, y=20, w=100, h=50,
                                  path=path)])
        self.sent = []
        self.previews = Previews()
        return Simulation(self.root, sending=self.sent.append,
                          values={"file contents": dict(files or {})}, **options)

    def drawing(self, simulation: Simulation) -> dict:
        return self.previews.simulation_drawing(simulation, simulation.drawing_inputs())

    def shapes(self, drawing: dict) -> list:
        return [shape for shape in drawing["shapes"] if shape["component"] == "p0"]

    def colour_shown(self, simulation: Simulation) -> tuple:
        """The colour the painter draws at the external picture's top left."""
        return paint_drawing(self.drawing(simulation)).getpixel((10, 20))[:3]

    def refusals(self) -> int:
        refusals = self.sent.count(IGNORED)
        self.sent.clear()
        return refusals


class MemoryFileTest(ExternalPictureTestCase):
    """An external picture shows a picture file that is kept in memory."""

    def test_a_png_in_ram_and_on_a_card_given_no_folder(self):
        for path in ("ram/p.png", "sd0/p.png"):
            with self.subTest(path=path):
                simulation = self.started(path, {path: RED})
                drawing = self.drawing(simulation)
                shape, = self.shapes(drawing)
                self.assertEqual((shape["kind"], shape["card"], shape["x"], shape["y"]),
                                 ("picture", True, 10, 20))
                data = drawing["pictureFiles"][shape["picture"]]["data"]
                self.assertEqual(base64.b64decode(data.split(",", 1)[1]), RED)
                self.assertEqual(self.colour_shown(simulation), (255, 0, 0))
                self.assertEqual(self.refusals(), 0)

    def test_a_picturebox_xi_file(self):
        simulation = self.started("ram/odd.xi", {"ram/odd.xi": XI.read_bytes()})
        drawing = self.drawing(simulation)
        shape, = self.shapes(drawing)
        found = drawing["pictureFiles"][shape["picture"]]
        self.assertTrue(found["data"].startswith("data:image/jpeg;base64,/9j/"))
        self.assertIn("mask", found)

    def test_new_bytes_show_in_the_next_drawing(self):
        simulation = self.started("ram/p.png", {"ram/p.png": RED})
        first = self.shapes(self.drawing(simulation))[0]["picture"]
        self.assertEqual(self.colour_shown(simulation), (255, 0, 0))
        simulation.serial_input('twfile "ram/p.png",%d' % len(BLUE))
        simulation.serial_received(BLUE)
        simulation.serial_input('p0.path="ram/p.png"')
        self.assertNotEqual(self.shapes(self.drawing(simulation))[0]["picture"], first)
        self.assertEqual(self.colour_shown(simulation), (0, 0, 255))

    def test_a_picture_that_twfile_puts_in_ram(self):
        simulation = self.started("")
        self.assertEqual(self.shapes(self.drawing(simulation)), [])
        simulation.serial_input('twfile "ram/p.png",%d' % len(RED))
        simulation.serial_received(RED)
        simulation.serial_input('p0.path="ram/p.png"')
        self.assertEqual(self.colour_shown(simulation), (255, 0, 0))
        self.assertEqual(self.refusals(), 0)

    def test_two_files_with_the_same_bytes_have_two_names(self):
        simulation = self.started("ram/p.png", {"ram/p.png": RED, "sd0/p.png": RED})
        first = self.shapes(self.drawing(simulation))[0]["picture"]
        simulation.serial_input('p0.path="sd0/p.png"')
        self.assertNotEqual(self.shapes(self.drawing(simulation))[0]["picture"], first)
        self.assertEqual(self.colour_shown(simulation), (255, 0, 0))

    def test_the_same_bytes_keep_their_name(self):
        simulation = self.started("ram/p.png", {"ram/p.png": RED})
        first = self.shapes(self.drawing(simulation))[0]["picture"]
        simulation.serial_input("sys0=1")
        self.assertEqual(self.shapes(self.drawing(simulation))[0]["picture"], first)

    def test_a_cards_folder_comes_before_memory(self):
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder).resolve() / "p.png"
            file.write_bytes(RED)
            simulation = self.started("sd0/p.png", {"sd0/p.png": BLUE},
                                      cards={"sd0/": Path(folder)})
            drawing = self.drawing(simulation)
            shape, = self.shapes(drawing)
            self.assertEqual(shape["picture"], str(file))
            self.assertEqual(drawing["pictureFiles"][str(file)]["path"], str(file))

    def test_a_bad_file_and_a_path_on_no_card_draw_nothing(self):
        cases = (("ram/bad.png", {"ram/bad.png": b"not a picture"}),
                 ("ram/cut.xi", {"ram/cut.xi": b"hmipicxi" + bytes(30)}),
                 ("p.png", {"p.png": RED}))
        for path, files in cases:
            with self.subTest(path=path):
                simulation = self.started(path, files)
                page_colour = paint_drawing(self.drawing(simulation)).getpixel((300, 300))[:3]
                self.assertEqual(self.colour_shown(simulation), page_colour)


class MissingFileTest(ExternalPictureTestCase):
    """An external picture whose file is missing answers 0x06."""

    def log(self, simulation: Simulation) -> list:
        return [line for _, line in simulation.log]

    def test_when_its_page_opens(self):
        simulation = self.started("sd0/missing.png")
        self.assertEqual(self.refusals(), 1)
        self.assertIn("p0 cannot show sd0/missing.png: there is no such file",
                      self.log(simulation))

    def test_when_a_page_change_opens_its_page(self):
        self.page("second", [table("p1", "external-picture", x=10, y=20, w=100, h=50,
                                   path="ram/missing.png")])
        simulation = self.started("")
        simulation.serial_input("page second")
        self.assertEqual(self.refusals(), 1)
        self.assertIn("p1 cannot show ram/missing.png: there is no such file",
                      self.log(simulation))

    def test_when_code_sets_its_path(self):
        simulation = self.started("ram/p.png", {"ram/p.png": RED, "ram/bad.png": b"no picture"})
        self.assertEqual(self.refusals(), 0)
        simulation.serial_input('p0.path="ram/missing.png"')
        self.assertEqual(self.refusals(), 1)
        self.assertIn("p0 cannot show ram/missing.png: there is no such file",
                      self.log(simulation))
        for path in ("ram/bad.png", "ram/p.png", ""):
            with self.subTest(path=path):
                simulation.serial_input('p0.path="%s"' % path)
                self.assertEqual(self.refusals(), 0)

    def test_with_a_card_given_a_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            (Path(folder) / "p.png").write_bytes(RED)
            simulation = self.started("sd0/p.png", cards={"sd0/": Path(folder)})
            self.assertEqual(self.refusals(), 0)
            simulation.serial_input('p0.path="sd0/missing.png"')
            self.assertEqual(self.refusals(), 1)

    def test_an_empty_path_and_a_path_on_no_card_answer_nothing(self):
        simulation = self.started("")
        self.assertEqual(self.refusals(), 0)
        simulation.serial_input('p0.path="x.png"')
        self.assertEqual(self.refusals(), 0)

    def test_a_hidden_external_picture_answers_nothing(self):
        simulation = self.started("ram/p.png", {"ram/p.png": RED})
        simulation.serial_input("vis p0,0")
        simulation.serial_input('p0.path="ram/missing.png"')
        self.assertEqual(self.refusals(), 0)

    def test_an_external_picture_that_the_load_event_hides_answers_nothing(self):
        self.write("app.toml", edited_app(self.text("app.toml"),
                                          lambda app: app.update(memory_file_storage_size=4096)))
        self.page("page0", [table("p0", "external-picture", x=10, y=20, w=100, h=50,
                                  path="sd0/missing.png"),
                            table("p1", "external-picture", x=10, y=90, w=100, h=50,
                                  path="sd0/missing.png")],
                  "on page0.load:\n  vis p0,0\n")
        self.sent = []
        Simulation(self.root, sending=self.sent.append)
        self.assertEqual(self.refusals(), 1)

    def test_a_path_set_in_the_load_event_answers_once(self):
        self.write("app.toml", edited_app(self.text("app.toml"),
                                          lambda app: app.update(memory_file_storage_size=4096)))
        self.page("page0", [table("p0", "external-picture", x=10, y=20, w=100, h=50, path="")],
                  'on page0.load:\n  p0.path="ram/missing.png"\n')
        self.sent = []
        Simulation(self.root, sending=self.sent.append)
        self.assertEqual(self.refusals(), 1)

    def test_a_file_that_is_not_a_picture_is_logged(self):
        simulation = self.started("ram/bad.png", {"ram/bad.png": b"no picture",
                                                  "ram/p.png": RED})
        line = "p0 cannot show ram/bad.png: the file is not a picture"
        self.assertEqual((self.log(simulation).count(line), self.refusals()), (1, 0))
        simulation.serial_input('p0.path="ram/p.png"')
        simulation.serial_input('p0.path="ram/bad.png"')
        self.assertEqual((self.log(simulation).count(line), self.refusals()), (2, 0))
        self.assertEqual([entry for entry in self.log(simulation)
                          if entry.startswith("p0 cannot show ram/p.png")], [])
