"""Reusing what a component painted in the last drawing of its page
(drawing/kept_paintings.py): a drawing made with reuse is the same as one
made without, whatever changed between the two drawings."""
import io
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from PIL import Image

from nxwright.drawing import page_drawing
from nxwright.drawing.kept_paintings import alike
from nxwright.project.pictures import write_png
from nxwright.source.page_source import Component
from nxwright.testing.preview import Previews
from nxwright.testing.sd_cards import FolderCards
from tests.test_zi_font import font_block, pairs_glyph

FONTS = Path(__file__).resolve().parent / "fixtures" / "fonts"


def _jpeg() -> bytes:
    """Returns a black JPEG picture of 4 by 2 pixels. The file is a JPEG
    because an external picture does not show a PNG
    (testing/external_pictures.py)."""
    file = io.BytesIO()
    Image.new("RGB", (4, 2)).save(file, "JPEG")
    return file.getvalue()


class KeptPaintingsTest(unittest.TestCase):
    """The tests draw a page of a folder that has the font `Sans20` and the
    pictures `back` (800 by 480), `logo` (64 by 64), and `later`, which has no
    file. An SD card given a folder contains `splash.jpg`. The page shows a
    component of each type the thermostat demo uses, an external picture, and
    a number component, whose type is not reused."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name).resolve() / "app"
        (self.root / "fonts").mkdir(parents=True)
        (self.root / "fonts" / "Sans20.zi").write_bytes((FONTS / "Sans20.zi").read_bytes())
        (self.root / "pictures").mkdir()
        self.write_picture("back", 800, 480, (0, 0, 255, 255))
        self.write_picture("logo", 64, 64, (255, 0, 0, 255))
        self.card = self.root.parent / "card"
        self.card.mkdir()
        (self.card / "splash.jpg").write_bytes(_jpeg())
        self.cards = FolderCards({"sd0/": self.card})
        self.app = {"pictures": ["back", "logo", "later"], "fonts": ["Sans20"],
                    "encoding": "iso-8859-1", "rotation": 0, "screen": "NX8048P050"}
        text = {"font": 0, "pco": 0, "xcen": 1, "ycen": 1}
        self.components = [
            Component("page", "page", {"x": 0, "y": 0, "w": 800, "h": 480, "sta": 2, "pic": 0}),
            Component("title", "text", dict(text, x=10, y=10, w=200, h=40, sta=1, bco=0xffff,
                                            txt="Hi")),
            Component("ok", "button", dict(text, x=10, y=60, w=100, h=40, sta=1, bco=0xffff,
                                           bco2=0x001f, style=4, txt="OK")),
            Component("zone", "hotspot", {"x": 0, "y": 0, "w": 50, "h": 50}),
            Component("photo", "picture", {"x": 300, "y": 10, "w": 64, "h": 64, "pic": 1}),
            Component("missing", "picture", {"x": 400, "y": 10, "w": 64, "h": 64, "pic": 2}),
            Component("knob", "slider", {"x": 10, "y": 120, "w": 300, "h": 64, "sta": 1,
                                         "bco": 0, "bco1": 0xffff, "psta": 1, "pic2": 1,
                                         "val": 50}),
            Component("chart", "waveform", {"x": 10, "y": 200, "w": 300, "h": 100, "sta": 1,
                                            "bco": 0, "ch": 1, "pco0": 0x07e0}),
            Component("exp0", "external-picture", {"x": 400, "y": 200, "w": 100, "h": 50,
                                                   "path": "sd0/splash.jpg"}),
            Component("count", "number", dict(text, x=10, y=320, w=100, h=40, sta=1,
                                              bco=0xffff, val=7)),
        ]
        self.waves = {"chart": {0: [10, 20, 30]}}

    def write_picture(self, name: str, width: int, height: int, colour: tuple):
        (self.root / "pictures" / (name + ".png")).write_bytes(
            write_png(width, height, bytes(colour) * (width * height)))

    def draw(self, previews: Previews, components: list = None, **given) -> dict:
        return previews.drawing_of(self.root, self.app, components or self.components,
                                   waves=self.waves, cards=self.cards, **given)

    def drawn_twice(self, change=lambda: None, **given) -> tuple:
        """Draws the page twice with one Previews, calling `change` between
        the two drawings, and checks that the second drawing is the same as
        one made without reuse, down to its shapes, its notes, and the files
        of its pictures. `given` goes to the second drawing. Returns both
        drawings."""
        previews = Previews()
        first = self.draw(previews)
        change()
        second = self.draw(previews, **given)
        self.assertEqual(second, self.draw(Previews(), **given))
        return first, second

    def reused(self, first: dict, second: dict) -> list:
        """The components that painted at least one shape in `first`, and
        whose shapes in `second` are the very same objects."""
        def shapes(drawing, name):
            return [shape for shape in drawing["shapes"] if shape["component"] == name]
        names = dict.fromkeys(shape["component"] for shape in first["shapes"])
        return [name for name in names
                if len(shapes(first, name)) == len(shapes(second, name))
                and all(map(lambda one, other: one is other, shapes(first, name),
                            shapes(second, name)))]

    def test_an_unchanged_page_reuses_each_painting(self):
        first, second = self.drawn_twice()
        self.assertEqual(self.reused(first, second),
                         ["page", "title", "ok", "photo", "missing", "knob", "chart", "exp0"])
        # The card's file is listed again, though the external picture was not painted again.
        self.assertIn(str(self.card / "splash.jpg"), second["pictureFiles"])
        self.assertIn("missing: pic 2 is not a picture of the folder", second["notes"])

    def test_a_type_not_reused_is_painted_each_time(self):
        with mock.patch.object(page_drawing, "paint_number", wraps=page_drawing.paint_number) \
                as numbers, mock.patch.object(page_drawing, "paint_slider",
                                              wraps=page_drawing.paint_slider) as sliders:
            self.drawn_twice()
        # With reuse, the number is painted in both drawings, and the slider
        # only in the first. The drawing without reuse paints each of them
        # once more.
        self.assertEqual((numbers.call_count, sliders.call_count), (3, 2))

    def test_a_component_drawn_again_within_a_drawing(self):
        # A `ref` paints the title a second time within the drawing, and that
        # time reuses the same painting.
        first, second = self.drawn_twice(painted=[("ref", "1")])
        self.assertIn("title", self.reused(first, second))

    def test_a_changed_value(self):
        # A simulation may change a value in place, so the kept painting keeps
        # a copy of the values it was painted from.
        def change():
            self.components[1].values["txt"] = "Ho"
        first, second = self.drawn_twice(change)
        self.assertNotIn("title", self.reused(first, second))
        self.assertIn("ok", self.reused(first, second))

    def test_a_value_alike_in_python_but_of_another_type(self):
        def change():
            self.components[6].values["val"] = 50.0
        first, second = self.drawn_twice(change)
        self.assertNotIn("knob", self.reused(first, second))

    def test_a_pressed_button(self):
        first, second = self.drawn_twice(pressed="ok")
        self.assertNotIn("ok", self.reused(first, second))
        self.assertIn("title", self.reused(first, second))

    def test_new_points_of_a_waveform(self):
        first, second = self.drawn_twice(lambda: self.waves["chart"][0].append(40))
        self.assertNotIn("chart", self.reused(first, second))

    def test_a_changed_font_file(self):
        # A font whose every glyph is a full 20 by 20 square.
        square = pairs_glyph([7] * 400)
        first, second = self.drawn_twice(lambda: (self.root / "fonts" / "Sans20.zi").write_bytes(
            font_block([(code, 20, 0, 0, square) for code in range(32, 127)], 20)))
        self.assertNotIn("title", self.reused(first, second))

    def test_a_changed_picture_file(self):
        # The slider's knob is the size of its picture.
        first, second = self.drawn_twice(lambda: self.write_picture("logo", 32, 48, (0, 0, 0, 255)))
        self.assertNotIn("knob", self.reused(first, second))
        self.assertNotEqual([shape for shape in first["shapes"] if shape["component"] == "knob"],
                            [shape for shape in second["shapes"] if shape["component"] == "knob"])

    def test_a_picture_file_that_appears(self):
        first, second = self.drawn_twice(lambda: self.write_picture("later", 8, 8,
                                                                    (0, 255, 0, 255)))
        self.assertEqual([shape["kind"] for shape in second["shapes"]
                          if shape["component"] == "missing"], ["picture"])
        self.assertNotIn("missing: pic 2 is not a picture of the folder", second["notes"])

    def test_a_changed_card_file(self):
        # A damaged PictureBox file shows the error marker.
        first, second = self.drawn_twice(lambda: (self.card / "splash.jpg").write_bytes(
            b"hmipicxi" + bytes(30)))
        self.assertEqual([shape["picture"] for shape in second["shapes"]
                          if shape["component"] == "exp0"], ["marker:100 by 50"])

    def test_a_card_file_that_appears(self):
        (self.card / "splash.jpg").unlink()
        first, second = self.drawn_twice(lambda: (self.card / "splash.jpg").write_bytes(
            _jpeg()))
        self.assertEqual([shape["kind"] for shape in second["shapes"]
                          if shape["component"] == "exp0"], ["picture"])

    def test_a_reordered_list_of_pictures(self):
        def change():
            self.app = dict(self.app, pictures=["logo", "back", "later"])
        first, second = self.drawn_twice(change)
        self.assertEqual(self.reused(first, second), ["title", "ok", "missing", "chart", "exp0"])

    def test_a_reordered_list_of_fonts(self):
        (self.root / "fonts" / "Other.zi").write_bytes(font_block(
            [(code, 20, 0, 0, pairs_glyph([7] * 400)) for code in range(32, 127)], 20))
        self.app["fonts"] = ["Sans20", "Other"]

        def change():
            self.app = dict(self.app, fonts=["Other", "Sans20"])
        first, second = self.drawn_twice(change)
        self.assertNotIn("title", self.reused(first, second))

    def test_the_folders_settings(self):
        for setting, value in (("encoding", "utf-8"), ("rotation", 180),
                               ("screen", "NX8048K050")):
            with self.subTest(setting=setting):
                original = self.app

                def change():
                    self.app = dict(original, **{setting: value})
                self.drawn_twice(change)
                self.app = original

    def test_a_page_left_and_entered_again(self):
        other = [Component("other", "page", {"x": 0, "y": 0, "w": 800, "h": 480, "sta": 1,
                                             "bco": 0}),
                 Component("title", "text", dict(self.components[1].values, txt="Elsewhere"))]
        previews = Previews()
        first = self.draw(previews)
        self.draw(previews, other)
        again = self.draw(previews)
        self.assertEqual(again, self.draw(Previews()))
        self.assertIn("title", self.reused(first, again))

    def test_alike(self):
        self.assertTrue(alike({"a": [1, (2, "x")]}, {"a": [1, (2, "x")]}))
        for first, second in ((1, True), (1, 1.0), ([1], (1,)), ({"a": [1]}, {"a": [True]}),
                              ({"a": 1}, {"b": 1})):
            with self.subTest(first=first, second=second):
                self.assertFalse(alike(first, second))


if __name__ == "__main__":
    unittest.main()
