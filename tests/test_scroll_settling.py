"""A list's scroll values settle when an event ends, at a `doevents`, and
after a typed instruction, as the Nextion Editor's simulator settled them:
until then, code reads back what it set."""
import base64
import io
import tempfile
from pathlib import Path

from PIL import Image

from nxwright.project.pictures import write_png
from nxwright.testing.simulation import Simulation
from tests.test_page_drawing import screen_drawing
from tests.test_project_writer import edit_text
from tests.test_simulation import SimulationTestCase, placed, table


class SettlingTest(SimulationTestCase):
    """As the probe's page held them: a file browser 370 wide with a border
    of 10, on a card whose `list/` folder holds thirteen files; a data
    record of ten records; and a sliding text of one line. The button `go`
    runs the code a test gives, which reads values into the variables v0 to
    v2 in the same event."""

    def setUp(self):
        super().setUp()
        self._card = tempfile.TemporaryDirectory()
        self.addCleanup(self._card.cleanup)
        self.card = Path(self._card.name)
        (self.card / "list").mkdir()
        for letter in "abcdefghijklm":
            (self.card / "list" / ("%s.txt" % letter)).write_bytes(b"x")
        (self.root / "pictures").mkdir()
        (self.root / "pictures" / "icon.png").write_bytes(
            write_png(40, 40, bytes((255, 0, 0, 255)) * 40 * 40))
        self.write("app.toml", self.text("app.toml").replace("pictures = []",
                                                             'pictures = ["icon"]'))
        self.program("page page0\n")

    def simulation(self, code: str, browser_dir: str = "sd0/list/", load: str = None) -> Simulation:
        """A simulation of the page, `go`'s Touch Press event running `code`,
        and its `load` event `load`, if given, its data record given its ten
        records by typed instructions."""
        self.page("page0", [
            table("fb0", "file-browser", x=0, y=0, w=370, h=140, style=1, borderw=10,
                  dir=browser_dir, pic1=0, pic2=0),
            table("d0", "data-record", x=400, y=0, w=250, h=140, path="sd0/1.data",
                  dir="a^b", format="100^100"),
            table("st0", "sliding-text", x=400, y=200, w=250, h=140, txt="one line",
                  txt_maxl=20),
            placed("go", "button", 0, 300),
            table("v0", "variable"), table("v1", "variable"), table("v2", "variable")],
            "on go.down:\n" + "".join("  %s\n" % line for line in code.split("\n")))
        if load is not None:
            edit_text(self.root / "pages" / "page0.page.toml", "h = 480\n",
                      'h = 480\nevents = ["load"]\n')
            path = self.root / "pages" / "page0.nx"
            loading = "".join("  %s\n" % line for line in load.split("\n"))
            path.write_text("on page0.load:\n" + loading + "\n" + path.read_text(encoding="utf-8"),
                            encoding="utf-8", newline="\n")
        simulation = Simulation(self.root, cards={"sd0/": self.card})
        for number in range(10):
            simulation.serial_input('d0.insert("r%d^%d")' % (number, number))
        return simulation

    def pressed(self, code: str, browser_dir: str = "sd0/list/") -> dict:
        """The values once `go`'s Touch Press event, running `code`, ended."""
        simulation = self.simulation(code, browser_dir)
        simulation.press("go")
        return simulation.values()

    def test_a_value_set_reads_back_until_the_event_ends(self):
        values = self.pressed("fb0.val_y=500\nd0.val_y=500\nst0.val_y=500\n"
                              "v0.val=fb0.val_y\nv1.val=d0.val_y\nv2.val=st0.val_y")
        self.assertEqual([values["v%d.val" % n] for n in range(3)], [500, 500, 500])
        # Then 32 past `maxval_y`; a sliding text of one line no further than its top.
        self.assertEqual((values["fb0.val_y"], values["d0.val_y"], values["st0.val_y"]),
                         (values["fb0.maxval_y"] + 32, values["d0.maxval_y"] + 32, 0))

    def test_above_the_top_settles_32_pixels_up(self):
        values = self.pressed("fb0.val_y=-50\nd0.val_y=-50\nst0.val_y=-50\n"
                              "v0.val=fb0.val_y\nv1.val=d0.val_y\nv2.val=st0.val_y")
        self.assertEqual([values["v%d.val" % n] for n in range(3)], [-50, -50, -50])
        self.assertEqual((values["fb0.val_y"], values["d0.val_y"], values["st0.val_y"]),
                         (-32, -32, -32))

    def test_doevents_settles_them_within_the_event(self):
        values = self.pressed("fb0.val_y=500\nd0.val_y=500\nst0.val_y=500\ndoevents\n"
                              "v0.val=fb0.val_y\nv1.val=d0.val_y\nv2.val=st0.val_y")
        self.assertEqual([values["v%d.val" % n] for n in range(3)],
                         [values["fb0.maxval_y"] + 32, values["d0.maxval_y"] + 32, 0])

    def test_a_typed_value_reads_back_settled(self):
        simulation = self.simulation("")
        simulation.serial_input("d0.val_y=500")
        values = simulation.values()
        self.assertEqual(values["d0.val_y"], values["d0.maxval_y"] + 32)

    def test_a_browser_listed_in_an_event(self):
        # From `sd0/`, one row, to thirteen files: `qty` at once, `maxval_y`
        # once the event ends, 200, and a `val_y` of 500 no further than it.
        values = self.pressed('fb0.dir="sd0/list/"\nv0.val=fb0.qty\nv1.val=fb0.maxval_y\n'
                              "fb0.val_y=500", browser_dir="sd0/")
        self.assertEqual((values["v0.val"], values["v1.val"]), (13, 0))
        self.assertEqual((values["fb0.maxval_y"], values["fb0.val_y"]), (200, 200))

    def test_a_browser_listed_in_its_pages_load(self):
        # As the probe saw it there: listed, then scrolled to 500, it settles
        # at `maxval_y`, 200.
        simulation = self.simulation("", browser_dir="sd0/",
                                     load='fb0.dir="sd0/list/"\nfb0.val_y=500')
        values = simulation.values()
        self.assertEqual((values["fb0.maxval_y"], values["fb0.val_y"]), (200, 200))

    def test_a_data_records_columns(self):
        values = self.pressed("d0.val_x=999\nv0.val=d0.val_x")
        self.assertEqual((values["v0.val"], values["d0.val_x"]), (999, values["d0.maxval_x"]))
        self.assertEqual(self.pressed("d0.val_x=-50")["d0.val_x"], 0)

    def test_each_list_is_drawn_32_pixels_lower_at_32_above_the_top(self):
        def drawn_at(code: str) -> tuple:
            # The browser's first icon; the data record's first record, its
            # second row of texts, under the titles; and the first row the
            # sliding text's picture of its lines inks.
            simulation = self.simulation(code)
            simulation.press("go")
            shapes = screen_drawing(simulation)["shapes"]
            icon = min(shape["y"] for shape in shapes
                       if shape["component"] == "fb0" and shape["kind"] == "picture")
            rows = sorted({shape["y"] for shape in shapes
                           if shape["component"] == "d0" and shape["kind"] == "text"})
            lines = next(shape for shape in shapes
                         if shape["component"] == "st0" and shape["kind"] == "text")
            return icon, rows[1], lines["y"] + _first_inked_row(lines["image"])
        top = drawn_at("")
        above = drawn_at("fb0.val_y=-50\nd0.val_y=-50\nst0.val_y=-50")
        self.assertEqual([low - high for high, low in zip(top, above)], [32, 32, 32])


def _first_inked_row(image: str) -> int:
    """The first row of a drawing's picture, a PNG data URI, holding a pixel
    not wholly transparent."""
    picture = Image.open(io.BytesIO(base64.b64decode(image.split(",", 1)[1]))).convert("RGBA")
    alpha = picture.getchannel("A")
    return next(y for y in range(picture.height)
                if any(alpha.getpixel((x, y)) for x in range(picture.width)))
