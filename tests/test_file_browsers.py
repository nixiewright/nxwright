"""File browsers and selects in a simulation (testing/simulation.py): what
the screen lists, and what a touch and the code do to them, as three
Editor steps showed the Editor's simulator doing. The browser here is the
steps' own: 190 by 200, its attributes at their defaults, its icons 32
pixels square, its font 16 pixels high, on a card of two folders and eight
files."""
from pathlib import Path
import shutil
import tempfile
import unittest

from nxwright.testing.preview import Previews
from nxwright.source.source_folder import folder_reader
from nxwright.project.pictures import read_picture, write_png
from nxwright.drawing.file_browser_drawing import browser_layout
from nxwright.drawing.screen_pictures import paint_drawing
from nxwright.testing.simulation import Simulation
from tests.test_folder_check import fonts_first
from tests.test_live_debugging import LiveTestCase
from tests.test_page_drawing import differing_pixels
from tests.test_simulation import SimulationTestCase, placed, table

FONTS = Path(__file__).resolve().parent / "fixtures" / "fonts"
SCREENSHOTS = Path(__file__).resolve().parent / "fixtures" / "files"
# The card's entries in the order the Editor's simulator listed them.
LISTED = ["Drawings/", "presets/", "a long name that needs wrapping.cfg", "alpha.cfg",
          "Beta.cfg", "data.bin", "notes.txt", "photo.jpg", "readme.txt", "zeta.cfg"]


class BrowserTestCase(SimulationTestCase):
    """A page with the file browser `files` at the page's corner, the select
    `choice` beside it, and what their events saw, on a card folder."""
    files = {}

    def setUp(self):
        super().setUp()
        self._card = tempfile.TemporaryDirectory()
        self.card = Path(self._card.name).resolve()
        self.addCleanup(self._card.cleanup)
        for name in LISTED:
            if name.endswith("/"):
                (self.card / name).mkdir()
            else:
                (self.card / name).write_bytes(b"x")
        (self.card / "presets" / "inner.cfg").write_bytes(b"x")
        (self.root / "pictures").mkdir()
        for name in ("folder", "file"):
            (self.root / "pictures" / (name + ".png")).write_bytes(
                write_png(32, 32, bytes((255, 255, 255, 255)) * 32 * 32))
        (self.root / "fonts").mkdir(exist_ok=True)
        (self.root / "fonts" / "Sans16.zi").write_bytes((FONTS / "Sans16.zi").read_bytes())
        self.write("app.toml", fonts_first(self.text("app.toml")
                   .replace("pictures = []", 'pictures = ["folder", "file"]'), ["Sans16"]))
        self.program("page page0\n")
        self.page("page0", [
            table("files", "file-browser", x=0, y=0, w=190, h=200, dir="sd0/", **self.files),
            table("choice", "select", x=300, y=0, w=120, h=300, path="01\\r\\n02\\r\\n03\\r\\n04"),
            table("downSaw", "variable", val=99), table("upSaw", "variable", val=99),
            table("upTxt", "variable", sta=1, txt="", txt_maxl=60),
            table("upDir", "variable", sta=1, txt="", txt_maxl=60),
            placed("pick", "button", 500, 0), placed("enter", "button", 500, 100),
            placed("goUp", "button", 500, 200), placed("slide", "button", 500, 300)], """\
on files.down:
  downSaw.val = files.val

on files.up:
  upSaw.val = files.val
  upTxt.txt = files.txt
  upDir.txt = files.dir

on choice.down:
  downSaw.val = choice.val

on choice.up:
  upSaw.val = choice.val
  upTxt.txt = choice.txt

on pick.down:
  files.val = 3

on enter.down:
  files.dir = "sd0/presets/"

on goUp.down:
  files.up()

on slide.down:
  files.val_y = files.val_y + 60
""")
        self.simulation = Simulation(self.root, cards={"sd0/": self.card})

    def value(self, name: str):
        return self.simulation.values()[name]

    def touch(self, component: str, *points):
        """Presses `component` at the first point, moves the press through
        the others, and releases it."""
        self.simulation.press(component, *points[0])
        for point in points[1:]:
            self.simulation.move(*point)
        self.simulation.release()


class LayoutTest(unittest.TestCase):

    def test_columns_fit_inside_the_border_drawn(self):
        # As the Nextion Editor's simulator laid them out, its icons 40
        # pixels square and `spax` 24: as many columns as fit the width less
        # the border drawn on each side, `spax` added, centred. A 3D style's
        # edge is a pixel wide, and none is drawn without background
        # (`sta` 3) or with no style.
        for values, columns, left in (
                ({"w": 360}, 5, 32), ({"w": 380}, 6, 10), ({"w": 384}, 6, 12),
                ({"w": 400, "style": 1, "borderw": 10}, 6, 20),
                ({"w": 370, "style": 1, "borderw": 10}, 5, 37),
                ({"w": 360, "sta": 3}, 6, 0), ({"w": 360, "style": 0}, 6, 0)):
            with self.subTest(values=values):
                layout = browser_layout(values, (40, 40), 24)
                self.assertEqual((layout.columns, layout.left), (columns, left))

    def test_a_tap_above_the_first_row_takes_the_first_row(self):
        # In a border 10 wide, 5 pixels down, above the first entry and the
        # second: the Nextion Editor's simulator chose each. Left of the
        # first column, a tap still finds none.
        layout = browser_layout({"w": 370, "style": 1, "borderw": 10}, (40, 40), 24)
        self.assertEqual([layout.place_at(x, 5, 0) for x in (57, 121, 20)], [0, 1, None])
        # Scrolled by 122, the same tap chose f.txt, the first of the second
        # row, shown just inside the border.
        self.assertEqual(layout.place_at(57, 5, 122), 5)

    def test_the_scroll_leaves_twice_the_border(self):
        # Three rows of 120: `maxval_y` 200 in a browser 140 high with a
        # border of 10, and 220 with none, in the Nextion Editor's simulator.
        # With a border of 1, it gave 78 (ProbedScrollTest).
        for values, most in (({"w": 370, "style": 1, "borderw": 10}, 200),
                             ({"w": 360, "sta": 3}, 220)):
            with self.subTest(values=values):
                self.assertEqual(browser_layout(values, (40, 40), 24).most_scroll(13, 140), most)

    def test_the_first_row_starts_inside_the_border_drawn(self):
        # A 3D style's edges are a pixel wide on a colour (`sta` 1), and none
        # are drawn without background (`sta` 3); a border (`style` 1) is
        # `borderw` wide, and not drawn without background either.
        for values, top in (({"style": 2, "sta": 1}, 1), ({"style": 2, "sta": 3}, 0),
                            ({"style": 1, "sta": 1, "borderw": 2}, 2),
                            ({"style": 1, "sta": 3, "borderw": 2}, 0), ({"style": 0, "sta": 1}, 0)):
            with self.subTest(values=values):
                self.assertEqual(browser_layout(values, (32, 32), 16).top, top)


class ListingTest(BrowserTestCase):

    def test_folders_first_then_files_capitals_ignored(self):
        self.assertEqual(self.simulation.listings(), {"files": LISTED})
        self.assertEqual(self.value("files.qty"), 10)

    def test_a_start_page_lists_the_folder_given(self):
        # As from its page file's `dir`, the page opening on the values given.
        simulation = Simulation(self.root, "page0", {"files.dir": "sd0/presets/"},
                                cards={"sd0/": self.card})
        self.assertEqual(simulation.listings(), {"files": ["inner.cfg"]})

    def test_its_scroll_reaches_what_the_editor_showed(self):
        self.assertEqual((self.value("files.val_y"), self.value("files.maxval_y")), (0, 150))

    def test_each_listing_clears_the_selection(self):
        self.simulation.press("pick")
        self.assertEqual((self.value("files.val"), self.value("files.txt")), (3, "alpha.cfg"))
        self.simulation.press("slide")
        self.simulation.press("enter")
        self.assertEqual([self.value("files." + name) for name in ("dir", "val", "txt", "val_y")],
                         ["sd0/presets/", -1, "", 0])
        self.simulation.press("pick")
        self.simulation.press("goUp")
        self.assertEqual([self.value("files." + name) for name in ("dir", "val", "txt", "qty")],
                         ["sd0/", -1, "", 10])

    def test_val_y_set_by_code_kept_within_its_reach(self):
        self.simulation.press("slide")
        self.assertEqual(self.value("files.val_y"), 60)
        for _ in range(3):
            self.simulation.press("slide")
        # 32 past `maxval_y`, as a sliding text's code may scroll it. Of a
        # browser, only one whose entries all fit was seen: the Editor gave
        # 32 for 60 there. Beyond that case, this is assumed.
        self.assertEqual(self.value("files.val_y"), 182)


class IconSizesTest(BrowserTestCase):
    """A browser whose folder icon is 60 pixels square and file icon 32: laid
    out by the file icon, as the Editor's simulator laid out icons of two
    sizes, each cut to the file icon's (fixtures/drawing-assumptions/,
    page16)."""

    def setUp(self):
        super().setUp()
        (self.root / "pictures" / "folder.png").write_bytes(
            write_png(60, 60, bytes((255, 255, 255, 255)) * 60 * 60))
        self.simulation = Simulation(self.root, cards={"sd0/": self.card})

    def test_laid_out_by_the_file_icon(self):
        # As with icons of 32 alike (ListingTest).
        self.assertEqual(self.value("files.maxval_y"), 150)
        self.simulation.press("files", *BrowserTouchTest.ALPHA)
        self.simulation.release()
        self.assertEqual((self.value("files.val"), self.value("files.txt")), (3, "alpha.cfg"))


class ProbedScrollTest(SimulationTestCase):
    """A browser of 8 files and icons of 20 by 20 in a new folder, its font
    NotoSans24, as the Nextion Editor's simulator ran it: it gave
    `maxval_y` 78, and read `val_y` 500 back as 110, 32 past it."""

    def setUp(self):
        super().setUp()
        self._card = tempfile.TemporaryDirectory()
        self.addCleanup(self._card.cleanup)
        card = Path(self._card.name)
        (card / "probe").mkdir()
        for number in range(8):
            (card / "probe" / ("nxprobe_agent-c_%d.txt" % number)).write_bytes(b"x")
        (self.root / "pictures").mkdir()
        for name, colour in (("folder-icon", (255, 200, 0)), ("file-icon", (0, 120, 255))):
            (self.root / "pictures" / (name + ".png")).write_bytes(
                write_png(20, 20, bytes(colour + (255,)) * 20 * 20))
        self.write("app.toml", self.text("app.toml").replace(
            "pictures = []", 'pictures = ["folder-icon", "file-icon"]'))
        self.program("page page0\n")
        self.page("page0", [table("fb0", "file-browser", x=110, y=110, w=200, h=120,
                                  dir="sd0/probe/")])
        self.simulation = Simulation(self.root, cards={"sd0/": card})

    def test_its_scroll_as_the_editor_gave_it(self):
        values = self.simulation.values()
        self.assertEqual((values["fb0.qty"], values["fb0.maxval_y"]), (8, 78))
        self.simulation.serial_input("fb0.val_y=500")
        self.assertEqual(self.simulation.values()["fb0.val_y"], 110)


class ProbedColumnsTest(SimulationTestCase):
    """A browser 360 wide at (20, 20), its icons 40 pixels square, on a card
    of a.txt and b.txt, and a touch capture reading its `val` as the touch
    ends, as the Nextion Editor's simulator ran it. It drew 5 columns inside
    the 3D edge, centred: b.txt's icon from x 116 to 156."""

    def setUp(self):
        super().setUp()
        self._card = tempfile.TemporaryDirectory()
        self.addCleanup(self._card.cleanup)
        card = Path(self._card.name)
        for name in ("a.txt", "b.txt"):
            (card / name).write_bytes(b"x")
        (self.root / "pictures").mkdir()
        (self.root / "pictures" / "icon.png").write_bytes(
            write_png(40, 40, bytes((255, 0, 0, 255)) * 40 * 40))
        self.write("app.toml", self.text("app.toml").replace("pictures = []",
                                                             'pictures = ["icon"]'))
        self.program("page page0\n")
        self.page("page0", [
            table("tc0", "touch-capture"),
            table("fb0", "file-browser", x=20, y=20, w=360, h=240, dir="sd0/", pic1=0, pic2=0),
            table("seen", "variable", val=99)], """\
on tc0.up:
  seen.val = fb0.val
""")
        self.simulation = Simulation(self.root, cards={"sd0/": card})

    def test_a_tap_on_the_second_entry_chooses_it_for_the_capture_to_read(self):
        self.simulation.press("fb0", 136, 40)
        self.simulation.release()
        values = self.simulation.values()
        self.assertEqual((values["fb0.val"], values["fb0.txt"], values["seen.val"]),
                         (1, "b.txt", 1))


class NoFileIconTest(BrowserTestCase):
    """A browser whose file icon is none: the Editor's simulator listed its
    entries, but drew none, and kept `maxval_y` 0."""
    files = {"pic2": 65535}

    def test_lists_its_entries_and_draws_none(self):
        self.assertEqual((self.value("files.qty"), self.value("files.maxval_y")), (10, 0))
        drawing = Previews().drawing_of(
            self.simulation.source_folder, self.simulation.app, self.simulation.components(),
            listings=self.simulation.listings(), cards=self.simulation.cards)
        # Its background and its edges alone: no icon, and no name.
        self.assertEqual({shape["kind"] for shape in drawing["shapes"]
                          if shape["component"] == "files"}, {"colour"})


class PageFileValTest(BrowserTestCase):
    files = {"val": 2}

    def test_selects_nothing_as_the_page_opens(self):
        self.assertEqual((self.value("files.val"), self.value("files.txt")), (-1, ""))


class NoFoldersTest(BrowserTestCase):
    files = {"psta": 0}

    def test_lists_files_alone(self):
        self.assertEqual(self.simulation.listings(), {"files": LISTED[2:]})
        self.assertEqual(self.value("files.qty"), 8)

    def test_a_tap_on_a_place_past_the_last_entry_gives_their_number(self):
        # A tap where an entry would be, past the last, sets `val` to the
        # number of entries, wherever the place, its `txt` empty. Here the
        # place after the eighth file, in the third column of the third row.
        self.touch("files", (151, 187))
        self.assertEqual((self.value("files.val"), self.value("files.txt")), (8, ""))


class BrowserTouchTest(BrowserTestCase):
    # The middle of entry 3's icon (alpha.cfg), and of entry 1's (presets/):
    # three columns 56 pixels apart from 23, rows 88 apart from 1.
    ALPHA, PRESETS = (39, 105), (95, 17)

    def test_a_tap_on_a_file_selects_it_as_it_ends(self):
        self.simulation.press("files", *self.ALPHA)
        self.assertEqual((self.value("files.val"), self.value("downSaw.val")), (-1, -1))
        self.simulation.release()
        self.assertEqual((self.value("files.val"), self.value("files.txt")), (3, "alpha.cfg"))
        self.assertEqual((self.value("upSaw.val"), self.value("upTxt.txt")), (3, "alpha.cfg"))

    def test_held_still_it_is_not_drawn_again_until_the_release(self):
        # As the Nextion Editor's simulator drew one held over a `fill`
        # (tests/fixtures/drawing-assumptions/, page45): nothing a press
        # chooses shows before the release, and `left` 1 shows the scroll
        # bar's thumb only while a touch scrolls it.
        marks = len(self.simulation.painted())
        self.simulation.press("files", *self.ALPHA)
        self.assertEqual((self.simulation.drawing_inputs().pressed,
                          self.simulation.painted()[marks:]), (None, []))
        self.simulation.release()
        self.assertEqual((self.value("files.val"), self.simulation.painted()[-1]),
                         (3, ("redraw", "files")))

    def test_a_tap_on_a_name_selects_it_too(self):
        self.touch("files", (39, 1 + 88 + 32 + 40))
        self.assertEqual(self.value("files.val"), 3)

    def test_a_tap_on_a_folder_opens_it(self):
        self.touch("files", self.PRESETS)
        self.assertEqual([self.value(name) for name in ("files.dir", "files.val", "files.qty")],
                         ["sd0/presets/", -1, 1])
        self.assertEqual((self.value("upDir.txt"), self.value("upSaw.val")), ("sd0/presets/", -1))

    def test_a_tap_between_entries_chooses_none(self):
        # A tap between two entries' places, across or down, or right of the
        # last column, leaves none chosen, even one chosen before.
        self.touch("files", (60, 105))
        self.assertEqual((self.value("files.val"), self.value("files.dir")), (-1, "sd0/"))
        for gap in ((60, 105), (39, 85), (180, 105)):
            with self.subTest(gap=gap):
                self.touch("files", self.ALPHA)
                self.touch("files", gap)
                self.assertEqual((self.value("files.val"), self.value("files.txt")), (-1, ""))

    def test_a_tap_left_of_the_first_column_changes_nothing(self):
        # The entry chosen stays.
        self.touch("files", self.ALPHA)
        self.touch("files", (10, 105))
        self.assertEqual((self.value("files.val"), self.value("files.txt")), (3, "alpha.cfg"))

    def test_a_drag_scrolls_within_reach_and_selects_nothing(self):
        self.simulation.press("files", 39, 150)
        self.simulation.move(39, 77)
        self.assertEqual(self.value("files.val_y"), 73)
        self.simulation.move(39, -400)
        self.assertEqual(self.value("files.val_y"), 150)
        self.simulation.move(39, 600)
        self.assertEqual(self.value("files.val_y"), 0)
        self.simulation.move(39, 100)
        self.simulation.release()
        self.assertEqual((self.value("files.val"), self.value("upSaw.val")), (-1, -1))
        self.assertEqual(self.value("files.val_y"), 50)

    def test_a_tap_after_a_scroll_finds_the_entry_moved(self):
        self.touch("files", (39, 150), (39, 77))
        self.touch("files", (39, self.ALPHA[1] - 73))
        self.assertEqual(self.value("files.txt"), "alpha.cfg")

    def test_held_while_pressed(self):
        self.simulation.press("files", 39, 150)
        self.assertEqual(self.simulation.pressed(), "files")
        self.simulation.release()
        self.assertIsNone(self.simulation.pressed())


class SelectTest(BrowserTestCase):
    """The select `choice`, 300 high, its lines 42 apart."""

    def test_txt_empty_as_the_page_opens(self):
        self.assertEqual((self.value("choice.val"), self.value("choice.txt")), (0, ""))

    def test_val_set_by_code_sets_txt_and_path_does_not(self):
        self.simulation.serial_input("choice.val=2")
        self.assertEqual(self.value("choice.txt"), "03")
        self.simulation.serial_input('choice.path="one\\rtwo\\rthree"')
        self.assertEqual((self.value("choice.val"), self.value("choice.txt")), (2, "03"))

    def test_val_past_the_last_line_is_refused(self):
        # Refused without an answer, `val` and `txt` keeping theirs.
        sent = []
        simulation = Simulation(self.root, cards={"sd0/": self.card}, sending=sent.append)
        simulation.serial_input("choice.val=1")
        before = len(sent)
        for line in ("choice.val=4", "choice.val=-2"):
            with self.subTest(line):
                simulation.serial_input(line)
                values = simulation.values()
                self.assertEqual((values["choice.val"], values["choice.txt"]), (1, "02"))
        self.assertEqual(sent[before:], [])

    def test_a_drag_selects_the_line_it_ends_on(self):
        self.simulation.press("choice", 360, 150)
        self.simulation.move(360, 110)
        self.assertEqual(self.simulation.select_moves(), {"choice": -40})
        self.assertEqual(self.value("choice.val"), 0)
        self.simulation.release()
        self.assertEqual(self.simulation.select_moves(), {})
        self.assertEqual((self.value("choice.val"), self.value("choice.txt")), (1, "02"))
        self.assertEqual((self.value("downSaw.val"), self.value("upSaw.val"),
                          self.value("upTxt.txt")), (0, 1, "02"))

    def test_a_short_drag_settles_on_the_middle_line(self):
        self.touch("choice", (360, 150), (360, 140))
        self.assertEqual((self.value("choice.val"), self.value("choice.txt")), (0, "01"))

    def test_lines_repeat_round(self):
        self.touch("choice", (360, 150), (360, 192))
        self.assertEqual((self.value("choice.val"), self.value("choice.txt")), (3, "04"))
        self.touch("choice", (360, 150), (360, 150 - 2 * 42))
        self.assertEqual((self.value("choice.val"), self.value("choice.txt")), (1, "02"))

    def test_a_tap_changes_nothing(self):
        self.touch("choice", (360, 20))
        self.assertEqual((self.value("choice.val"), self.value("choice.txt")), (0, ""))
        self.assertEqual(self.value("upSaw.val"), 0)


def _step_folder(parent: Path) -> Path:
    """Copies the first Editor step's source folder into `parent`, with its
    font, and returns where."""
    root = parent / "app"
    shutil.copytree(SCREENSHOTS / "app", root)
    (root / "fonts").mkdir(exist_ok=True)
    (root / "fonts" / "Sans16.zi").write_bytes((FONTS / "Sans16.zi").read_bytes())
    return root


class DrawnAsTheEditorDrawsThemTest(unittest.TestCase):
    """The first Editor step's pages, fixtures/files/app/, simulated on its
    card and drawn, against the Editor's simulator showing them, each
    screenshot cropped to the screen: the browsers as the page opens
    (browsers.png), after a tap on a file (tap-file.png), and after a drag
    (scrolled.png); the other browsers (browsers2.png); the selects as their
    page opens (selects.png), and after a drag (select-drag.png). Each
    component's pixels must come within TOLERANCE of the screenshot's. The
    places, the texts, the fading, and the icons, in the screen's 16-bit
    colours, match but for a unit of colour here and there. Only the
    smoothed edges of one select's texts, in selects.png, differ by up to 5."""
    TOLERANCE = 1
    TEXT_EDGES_TOLERANCE = 5

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        root = _step_folder(Path(folder.name))
        card = Path(folder.name) / "card"
        card.mkdir()
        for name in LISTED:
            if name.endswith("/"):
                (card / name).mkdir()
            else:
                (card / name).write_bytes(b"x")
        self.simulation = Simulation(root, cards={"sd1/": card})

    def test_browsers(self):
        self.assert_drawn_as("browsers.png", ["plain", "style0", "style1", "twoLines", "sta3",
                                              "tight", "noFolders", "oneLine"])
        # alpha.cfg in `plain`, at the page's (8, 6).
        self.simulation.press("plain", 8 + 39, 6 + 105)
        self.simulation.release()
        self.assert_drawn_as("tap-file.png", ["plain"])
        self.simulation.press("plain", 47, 156)
        self.simulation.move(47, 83)
        self.simulation.release()
        self.assert_drawn_as("scrolled.png", ["plain"])

    def test_more_browsers(self):
        self.next_page()
        self.assert_drawn_as("browsers2.png", ["picked", "custom", "barAlways", "barNever",
                                               "leftNames", "cfgOnly"])

    def test_selects(self):
        self.next_page()
        self.next_page()
        self.assert_drawn_as("selects.png", ["plain", "picked", "noLines", "lowRows", "colours",
                                             "threeLines"], self.TEXT_EDGES_TOLERANCE)
        self.simulation.press("plain", 68, 156)
        self.simulation.move(68, 114)
        self.simulation.release()
        self.assert_drawn_as("select-drag.png", ["plain"])

    def next_page(self):
        self.simulation.press("next")
        self.simulation.release()

    def assert_drawn_as(self, screenshot: str, components: list, tolerance: int = TOLERANCE):
        simulation = self.simulation
        drawing = Previews().drawing_of(simulation.source_folder, simulation.app,
                                        simulation.components(), simulation.painted(), (0, 0),
                                        simulation.hidden(), simulation.waves(),
                                        simulation.pressed(), simulation.listings(),
                                        simulation.select_moves())
        drawn = paint_drawing(drawing)
        shown = read_picture((SCREENSHOTS / screenshot).read_bytes())
        places = {component["name"]: component for component in drawing["components"]}
        for name in components:
            place = places[name]
            with self.subTest(screenshot=screenshot, component=name):
                differing = [(x - place["x"], y - place["y"], shown.getpixel((x, y))[:3],
                              drawn.getpixel((x, y)))
                             for x, y in differing_pixels(drawn, shown, place, tolerance)]
                self.assertEqual(differing[:5], [], "%d pixels differ" % len(differing))


class AdapterTest(LiveTestCase):
    """The drawing the simulator's panel gets shows a file browser's entries."""

    def test_the_drawing_shows_the_entries(self):
        (self.root / "pictures").mkdir()
        for name in ("folder", "file"):
            (self.root / "pictures" / (name + ".png")).write_bytes(
                write_png(32, 32, bytes((255, 255, 255, 255)) * 32 * 32))
        self.write("app.toml", self.text("app.toml")
                   .replace("pictures = []", 'pictures = ["folder", "file"]'))
        self.page("page0", [table("files", "file-browser", x=0, y=0, w=190, h=200, dir="sd0/")])
        with tempfile.TemporaryDirectory() as card:
            (Path(card) / "a.cfg").write_bytes(b"x")
            self.launch(sdCard0=card)
            drawing = self.wait_for("nxwright/drawing")
            self.assertIn(("files", "picture", "file"),
                          [(shape["component"], shape["kind"], shape.get("picture"))
                           for shape in drawing["shapes"]])
            self.request("disconnect")


class PreviewTest(unittest.TestCase):
    """The page preview, which has no SD card: a file browser's background
    and border, without entries; a select's lines, from its page file.
    Neither is outlined."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = _step_folder(Path(folder.name))

    def shapes(self, page: str) -> dict:
        drawing = Previews().drawing(self.root, "pages/%s.page.toml" % page, folder_reader(self.root))
        shapes = {}
        for shape in drawing["shapes"]:
            shapes.setdefault(shape["component"], []).append(shape["kind"])
        return shapes

    def test_a_browser_without_entries(self):
        self.assertEqual(self.shapes("browsers")["plain"], ["colour"] * 5)

    def test_a_select_with_its_lines(self):
        # 300 high, its lines 42 apart: seven whole, and a sliver of one at
        # its top and its bottom. Its background, then its two rules.
        kinds = self.shapes("selects")["threeLines"]
        self.assertEqual((kinds[0], kinds.count("text"), kinds.count("colour")), ("colour", 9, 3))
