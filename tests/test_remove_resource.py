"""`nxwright remove`: removing a resource from a source folder. With
`--checked`, a removal is refused while the folder uses the resource by name,
or by a number that is its ID or a later one's, because a removal gives each
later resource of its kind an ID one lower."""
import contextlib
import io
import json
from pathlib import Path
import shutil
import tempfile
import tomllib
import unittest
from unittest import mock

from nxwright import NxwrightError
from nxwright.cli import main
from nxwright.project.device_settings import DeviceSettings
from nxwright.project.pictures import write_png
from nxwright.project.screen_models import model_named
from nxwright.project.truetype import NOTO_SANS
from nxwright.project.zi_font import decode_font
from nxwright.source.folder_check import check_folder
from nxwright.source.resource_removal import remove_keeping_ids, remove_resource, removal_report
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
        """Asserts a checked removal of `name` is refused, naming each of
        `places`, and that the folder is left as it was."""
        before = self.files()
        with self.assertRaises(NxwrightError) as refused:
            remove_resource(self.source, kind, name, checked=True)
        for place in places:
            self.assertIn(place, str(refused.exception))
        self.assertEqual(self.files(), before)

    def files(self, source: Path = None) -> dict:
        source = source or self.source
        return {path.relative_to(source).as_posix(): path.read_bytes()
                for path in source.rglob("*") if path.is_file()}


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

    def test_a_checked_removal_writes_the_same_files(self):
        for remove in (remove_resource, remove_keeping_ids):
            with self.subTest(remove=remove.__name__):
                checked = self.folder / ("checked-" + remove.__name__)
                plain = self.folder / ("plain-" + remove.__name__)
                shutil.copytree(self.source, checked)
                shutil.copytree(self.source, plain)
                self.assertEqual(remove(checked, "picture", "a", checked=True),
                                 remove(plain, "picture", "a"))
                self.assertEqual(self.files(checked), self.files(plain))

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

    def test_it_is_removed_without_a_search_unless_checked(self):
        self.add("p0", "picture", pic="a")
        self.write_code("p0.pic=@pic(a)")
        code = (self.source / "pages" / "page0.nx").read_bytes()
        with mock.patch("nxwright.source.resource_removal.check_folder",
                        side_effect=AssertionError("the folder was checked")), \
                mock.patch("nxwright.source.resource_removal.references",
                           side_effect=AssertionError("the uses were searched")):
            self.assertEqual(remove_resource(self.source, "picture", "a"),
                             (["pictures/a.png"], []))
        self.assertEqual(self.app()["pictures"], ["b"])
        # The uses are left as they were, so the folder no longer builds.
        self.assertEqual((self.source / "pages" / "page0.nx").read_bytes(), code)
        check = check_folder(folder_reader(self.source), lambda path: (self.source / path).exists())
        self.assertNotEqual(check.errors(), [])


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
        for checked in (False, True):
            with self.assertRaisesRegex(NxwrightError, "the folder has no picture named c"):
                remove_resource(self.source, "picture", "c", checked=checked)
            with self.assertRaisesRegex(NxwrightError, "colour is not a kind"):
                remove_resource(self.source, "colour", "a", checked=checked)

    def test_a_folder_whose_checks_find_an_error(self):
        self.write_code("zz.val=1")
        self.assert_refused("picture", "a", "pages/page0.nx", "zz")
        # A removal that is not checked does not build the folder, so the error does not
        # stop it.
        remove_resource(self.source, "picture", "a")
        self.assertEqual(self.app()["pictures"], ["b"])


class ReportTest(RemoveResourceTestCase):
    """What `remove --report` says a removal would affect, writing nothing."""

    def report(self, kind: str, name: str) -> dict:
        before = self.files()
        report = removal_report(self.source, kind, name)
        self.assertEqual(self.files(), before)
        return report

    def test_unused_and_last(self):
        self.assertEqual(self.report("picture", "b"), {
            "kind": "picture", "name": "b", "id": 1, "encoding": "iso-8859-1", "last": True,
            "later": [], "uses": []})
        self.assertEqual(self.report("picture", "a")["later"], ["b"])
        self.assertFalse(self.report("picture", "a")["last"])

    def test_uses_by_name_by_its_own_id_and_by_a_later_one(self):
        self.add("p0", "picture", pic="a")
        self.write_code("p0.pic=0", "p0.pic=1")
        uses = self.report("picture", "a")["uses"]
        self.assertEqual([(use["by"], use["of"]) for use in uses],
                         [("name", "itself"), ("number", "itself"), ("number", "later")])
        self.assertEqual([(use["path"], use["line"], use["text"]) for use in uses[1:]],
                         [("pages/page0.nx", 2, "p0.pic=0"), ("pages/page0.nx", 3, "p0.pic=1")])
        self.assertEqual(uses[0]["path"], "pages/page0.page.toml")

    def test_a_number_the_defaults_give(self):
        self.add("t0", "text")
        uses = self.report("font", "NotoSans24")["uses"]
        self.assertEqual([(use["by"], use["of"]) for use in uses], [("number", "itself")])
        self.assertIn("takes 0 from the defaults", uses[0]["text"])

    def test_the_command_prints_json(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["remove", str(self.source), "picture", "a", "--report"]), 0)
        self.assertEqual(json.loads(output.getvalue())["later"], ["b"])
        self.assertIn("pictures/a.png", self.files())
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors):
            self.assertEqual(main(["remove", str(self.source), "picture", "a", "--report",
                                   "--keep-ids"]), 1)
        self.assertIn("--keep-ids", errors.getvalue())


class KeepIdsTest(RemoveResourceTestCase):
    """`remove --keep-ids`: a placeholder takes the resource's place."""

    def test_each_kind_leaves_a_placeholder(self):
        for kind, name, listed, files in (
                ("picture", "a", "pictures", ["pictures/empty-slot-1.png"]),
                ("font", "NotoSans24", "fonts", ["fonts/empty-slot-1.zi"]),
                ("animation", "blink", "animations", ["animations/empty-slot-1.gmov",
                                                      "animations/empty-slot-1.screen.gmov"]),
                ("video", "clip", "videos", ["videos/empty-slot-1.video"]),
                ("sound", "beep", "sounds", ["sounds/empty-slot-1.wav"])):
            with self.subTest(kind=kind):
                count = len(self.app()[listed])
                self.assertEqual(remove_keeping_ids(self.source, kind, name)[0], "empty-slot-1")
                self.assertEqual(len(self.app()[listed]), count)
                self.assertEqual(self.app()[listed][0], "empty-slot-1")
                for path in files:
                    self.assertTrue((self.source / path).is_file())
        check = check_folder(folder_reader(self.source), lambda path: (self.source / path).exists())
        self.assertEqual(check.errors(), [])

    def test_a_later_resource_keeps_its_id(self):
        # b stays picture 1, so a number for it is no use of a.
        self.add("p0", "picture", pic=1)
        self.write_code("p0.pic=1")
        remove_keeping_ids(self.source, "picture", "a")
        self.assertEqual(self.app()["pictures"], ["empty-slot-1", "b"])
        self.assertFalse((self.source / "pictures" / "a.png").exists())

    def test_the_lowest_free_number_and_a_placeholder_replaced(self):
        remove_keeping_ids(self.source, "picture", "a")
        self.assertEqual(remove_keeping_ids(self.source, "picture", "b")[0], "empty-slot-2")
        # Another placeholder in its place keeps its name.
        self.assertEqual(remove_keeping_ids(self.source, "picture", "empty-slot-1")[0],
                         "empty-slot-1")
        self.assertEqual(self.app()["pictures"], ["empty-slot-1", "empty-slot-2"])

    def test_a_font_in_utf_8_holds_the_space_alone(self):
        folder = self.folder / "utf8"
        new_source_folder(folder, DeviceSettings(model_named("NX4832T035"), 0, "utf-8"),
                          "nextion")
        add_font(folder, NOTO_SANS, 16)
        remove_keeping_ids(folder, "font", "NotoSans16")
        font = decode_font((folder / "fonts" / "empty-slot-1.zi").read_bytes())
        self.assertEqual(sorted(font.characters), [0x20])

    def test_a_use_of_the_resource_itself_refuses_when_checked(self):
        self.write_code("p0.pic=0")
        self.add("p0", "picture")
        before = self.files()
        with self.assertRaisesRegex(NxwrightError, "line 2"):
            remove_keeping_ids(self.source, "picture", "a", checked=True)
        self.assertEqual(self.files(), before)
        self.assertEqual(remove_keeping_ids(self.source, "picture", "a")[0], "empty-slot-1")

    def test_the_command(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["remove", str(self.source), "sound", "beep", "--keep-ids"]), 0)
        self.assertIn("empty-slot-1", output.getvalue())
        self.assertEqual(self.app()["sounds"], ["empty-slot-1"])


class CommandTest(RemoveResourceTestCase):

    def test_it_says_what_it_removed_and_what_a_checked_removal_refused(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["remove", str(self.source), "picture", "a"]), 0)
        self.assertIn("pictures/a.png", output.getvalue())
        self.write_code("p0.pic=@pic(b)")
        self.add("p0", "picture")
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors):
            self.assertEqual(main(["remove", str(self.source), "picture", "b", "--checked"]),
                             1)
        self.assertIn("pages/page0.nx line 2", errors.getvalue())
        self.assertIn("pictures/b.png", self.files())
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["remove", str(self.source), "picture", "b"]), 0)
        self.assertNotIn("pictures/b.png", self.files())


if __name__ == "__main__":
    unittest.main()
