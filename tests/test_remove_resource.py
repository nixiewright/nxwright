"""`nxwright remove`: removing a resource from a source folder, refused while
the folder uses it by name, or by a number that is its ID or a later one's,
as a removal gives each later resource of its kind an ID one lower."""
import contextlib
import io
from pathlib import Path
import tempfile
import tomllib
import unittest

from nxwright import NxwrightError
from nxwright.cli import main
from nxwright.project.pictures import write_png
from nxwright.project.truetype import NOTO_SANS
from nxwright.source.folder_check import check_folder
from nxwright.source.resource_removal import remove_resource
from nxwright.source.source_folder import folder_reader, new_source_folder, switch_to_nxlang
from nxwright.source.resource_adding import (add_animation, add_font, add_pictures, add_sound,
                                             add_video)
from tests.test_making_videos_and_sounds import SOURCES
from tests.test_media import SETTINGS


class RemoveResourceTestCase(unittest.TestCase):
    """A new source folder of an NX8048P050 holding two pictures, a and b;
    two fonts, NotoSans24 and NotoSans16; an animation, a video, and a
    sound; and page0 with its down event."""

    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.folder = Path(self._folder.name)
        self.source = self.folder / "app"
        new_source_folder(self.source, SETTINGS, "nextion")
        frames = []
        for name, colour in (("a", (255, 0, 0)), ("b", (0, 0, 255))):
            frame = self.folder / ("%s.png" % name)
            frame.write_bytes(write_png(8, 8, bytes(colour + (255,)) * 64))
            frames.append(frame)
        add_pictures(self.source, frames)
        add_font(self.source, NOTO_SANS, 16)
        add_animation(self.source, frames, 100, "blink")
        add_video(self.source, frames, name="clip")
        add_sound(self.source, SOURCES / "short22k.wav", "beep")
        page = self.source / "pages" / "page0.page.toml"
        page.write_text(page.read_text(encoding="utf-8").replace("events = []",
                                                                 'events = ["down"]'),
                        encoding="utf-8", newline="\n")

    def tearDown(self):
        self._folder.cleanup()

    def app(self) -> dict:
        return tomllib.loads((self.source / "app.toml").read_text(encoding="utf-8"))

    def add(self, name: str, kind: str, **values):
        """Adds a component to page0, at (0, 0), 100 by 50, with `values`."""
        text = "".join('%s = %s\n' % (key, '"%s"' % value if isinstance(value, str) else value)
                       for key, value in values.items())
        with open(self.source / "pages" / "page0.page.toml", "a", encoding="utf-8",
                  newline="\n") as file:
            file.write('\n[[component]]\nname = "%s"\ntype = "%s"\nx = 0\ny = 0\nw = 100\n'
                       'h = 50\n%s' % (name, kind, text))

    def write_code(self, *lines: str):
        """Writes page0's down event; its lines start at line 2 of page0.nx."""
        code = "".join("  %s\n" % line for line in lines)
        (self.source / "pages" / "page0.nx").write_text("on page0.down:\n" + code,
                                                         encoding="utf-8", newline="\n")

    def assert_refused(self, kind: str, name: str, *places: str):
        """Asserts removing `name` is refused, naming each of `places`, and
        that the folder is left as it was."""
        before = self.files()
        with self.assertRaises(NxwrightError) as refused:
            remove_resource(self.source, kind, name)
        for place in places:
            self.assertIn(place, str(refused.exception))
        self.assertEqual(self.files(), before)

    def files(self) -> dict:
        return {path.relative_to(self.source).as_posix(): path.read_bytes()
                for path in self.source.rglob("*") if path.is_file()}


class UnusedTest(RemoveResourceTestCase):

    def test_each_kind_is_removed(self):
        for kind, name, files in (("picture", "a", ["pictures/a.png"]),
                                  ("font", "NotoSans16", ["fonts/NotoSans16.zi"]),
                                  ("animation", "blink", ["animations/blink.gmov",
                                                          "animations/blink.screen.gmov"]),
                                  ("video", "clip", ["videos/clip.video"]),
                                  ("sound", "beep", ["sounds/beep.wav"])):
            with self.subTest(kind=kind):
                self.assertEqual(remove_resource(self.source, kind, name), (files, []))
                for path in files:
                    self.assertFalse((self.source / path).exists())
        app = self.app()
        self.assertEqual((app["pictures"], app["fonts"], app.get("animations", []),
                          app.get("videos", []), app.get("sounds", [])),
                         (["b"], ["NotoSans24"], [], [], []))
        check = check_folder(folder_reader(self.source), lambda path: (self.source / path).exists())
        self.assertEqual(check.errors(), [])

    def test_a_later_resource_takes_its_place(self):
        # b, by its name, is picture 0 once a is removed.
        self.add("p0", "picture", pic="b")
        self.write_code("p0.pic=@pic(b)")
        remove_resource(self.source, "picture", "a")
        self.assertEqual(self.app()["pictures"], ["b"])


class UsedByNameTest(RemoveResourceTestCase):

    def test_a_page_file_and_code(self):
        self.add("p0", "picture", pic="a")
        self.write_code("p0.pic=@pic(a)")
        self.assert_refused("picture", "a", "pages/page0.page.toml line", "pages/page0.nx line 2")


class UsedByNumberTest(RemoveResourceTestCase):

    def test_code_giving_its_id_or_a_later_ones(self):
        # Removing picture a, 0, renumbers b, 1: both numbers refuse.
        self.add("p0", "picture", pic="b")
        self.add("gm0", "gmov", vid="blink")
        self.write_code("p0.pic=1", "if(p0.pic==0)", "{", "}", "pic 0,0,1", "picq 0,0,8,8,1",
                        "xpic 0,0,8,8,0,0,1", 'xstr 0,0,8,8,0,0,1,0,0,2,"a"')
        self.assert_refused("picture", "a", "line 2:", "line 3:", "line 6:", "line 7:",
                            "line 8:", "line 9:")
        self.write_code('xstr 0,0,8,8,1,0,0,0,0,1,"a"', "play 0,0,0", "gm0.vid=0")
        self.assert_refused("font", "NotoSans24", "line 2:")
        self.assert_refused("sound", "beep", "line 3:")
        self.assert_refused("animation", "blink", "line 4:")

    def test_numbers_that_do_not_refuse(self):
        # Below its ID, past every ID, a name, not a picture, or in a quoted
        # text: removing b, 1.
        self.add("p0", "picture", pic="a")
        self.add("t0", "text", txt_maxl=20)
        self.write_code("p0.pic=0", "p0.pic=65535", "p0.pic=@pic(a)",
                        'xstr 0,0,8,8,0,0,1,0,0,1,"a"', 't0.txt="(p0.pic==1)"')
        remove_resource(self.source, "picture", "b")
        self.assertEqual(self.app()["pictures"], ["a"])

    def test_its_own_attribute_in_an_event(self):
        # In p0's event, '&pic&' is p0.pic.
        self.add("p0", "picture", pic="b", events=["down"])
        (self.source / "pages" / "page0.nx").write_text("on p0.down:\n  '&pic&'=1\n",
                                                         encoding="utf-8", newline="\n")
        self.assert_refused("picture", "a", "pages/page0.nx line 2")

    def test_an_nxlang_constant(self):
        self.add("p0", "picture", pic="b")
        switch_to_nxlang(self.source)
        (self.source / "pages" / "page0.nx").write_text(
            "const LOGO = 1\n\non page0.down:\n  p0.pic = LOGO\n", encoding="utf-8", newline="\n")
        self.assert_refused("picture", "a", "pages/page0.nx line 4")

    def test_a_page_file(self):
        # A number written there, and font 0 left to the defaults by a text.
        self.add("p0", "picture", pic=1)
        self.assert_refused("picture", "a", "pages/page0.page.toml line")
        self.add("t0", "text")
        self.assert_refused("font", "NotoSans24", "t0")


class RefusalTest(RemoveResourceTestCase):

    def test_a_name_or_kind_the_folder_lacks(self):
        with self.assertRaisesRegex(NxwrightError, "the folder has no picture named c"):
            remove_resource(self.source, "picture", "c")
        with self.assertRaisesRegex(NxwrightError, "colour is not a kind"):
            remove_resource(self.source, "colour", "a")

    def test_a_folder_whose_checks_find_an_error(self):
        self.write_code("zz.val=1")
        self.assert_refused("picture", "a", "pages/page0.nx", "zz")


class CommandTest(RemoveResourceTestCase):

    def test_it_says_what_it_removed_and_refused(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["remove", str(self.source), "picture", "a"]), 0)
        self.assertIn("pictures/a.png", output.getvalue())
        self.write_code("p0.pic=@pic(b)")
        self.add("p0", "picture")
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors):
            self.assertEqual(main(["remove", str(self.source), "picture", "b"]), 1)
        self.assertIn("pages/page0.nx line 2", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
