"""`nxwright replace`, which writes a new file into a resource's place, keeping
its ID, and `nxwright rename`, which renames a resource and each use of its
name (source/resource_replacing.py and source/resource_renaming.py)."""
import contextlib
import io
import json
from pathlib import Path
import shutil
from unittest import mock

from nxwright import NxwrightError
from nxwright.cli import main
from nxwright.project.device_settings import DeviceSettings
from nxwright.project.media_files import animation_frames, video_frames
from nxwright.project.pictures import write_png
from nxwright.project.screen_models import model_named
from nxwright.project.truetype import NOTO_SANS
from nxwright.project.zi_font import decode_font, font_facts
from nxwright.source.folder_check import check_folder
from nxwright.source.resource_adding import add_font
from nxwright.source.resource_removal import remove_keeping_ids
from nxwright.source.resource_renaming import rename_resource
from nxwright.source.resource_replacing import current_settings, replace_resource
from nxwright.source.source_folder import folder_reader, new_source_folder, switch_to_nxlang
from tests.test_making_videos_and_sounds import SOURCES
from tests.test_remove_resource import RemoveResourceTestCase


class FolderTestCase(RemoveResourceTestCase):
    """RemoveResourceTestCase's folder: pictures a and b, fonts NotoSans24
    and NotoSans16, the animation blink (100 ms frames), the video clip, and
    the sound beep."""

    def picture(self, name: str, colour: tuple, size: int = 8) -> Path:
        path = self.folder / ("%s.png" % name)
        path.write_bytes(write_png(size, size, bytes(colour + (255,)) * size * size))
        return path

    def builds(self) -> bool:
        return not check_folder(folder_reader(self.source),
                                lambda path: (self.source / path).exists()).errors()


class CurrentSettingsTest(FolderTestCase):

    def test_each_kind(self):
        self.assertEqual(current_settings(self.source, "picture", "a"), {})
        self.assertEqual(current_settings(self.source, "font", "NotoSans16"),
                         {"height": 16, "smoothed": True})
        self.assertEqual(current_settings(self.source, "animation", "blink"), {"duration": 100})
        self.assertEqual(current_settings(self.source, "video", "clip"),
                         {"rate": 12, "size": [8, 8]})
        self.assertEqual(current_settings(self.source, "sound", "beep"), {})

    def test_a_utf_8_font_gives_its_characters(self):
        folder = self.folder / "utf8"
        new_source_folder(folder, DeviceSettings(model_named("NX4832T035"), 0, "utf-8"),
                          "nextion")
        add_font(folder, NOTO_SANS, 16, characters="41-43")
        self.assertEqual(current_settings(folder, "font", "NotoSans16"),
                         {"height": 16, "smoothed": True, "characters": "20,41-43",
                          "fullTable": False})

    def test_a_placeholder_gives_none(self):
        remove_keeping_ids(self.source, "font", "NotoSans16")
        self.assertEqual(current_settings(self.source, "font", "empty-slot-1"), {})


class ReplaceTest(FolderTestCase):

    def test_a_picture_keeps_its_name_and_id(self):
        self.add("p0", "picture", pic="a")
        green = self.picture("green", (0, 255, 0))
        self.assertEqual(replace_resource(self.source, "picture", "a", [green])[0], "a")
        self.assertEqual(self.app()["pictures"], ["a", "b"])
        self.assertEqual((self.source / "pictures" / "a.png").read_bytes(), green.read_bytes())
        self.assertTrue(self.builds())

    def test_settings_default_to_the_current_ones(self):
        replace_resource(self.source, "font", "NotoSans16", [NOTO_SANS])
        facts = font_facts((self.source / "fonts" / "NotoSans16.zi").read_bytes())
        self.assertEqual((facts.height, facts.smoothed), (16, True))
        green = self.picture("green", (0, 255, 0))
        replace_resource(self.source, "animation", "blink", [green, green])
        frames = animation_frames((self.source / "animations" / "blink.screen.gmov").read_bytes())
        self.assertEqual(frames.starts, (0, 100))
        replace_resource(self.source, "video", "clip", [green], rate=5)
        self.assertEqual(video_frames((self.source / "videos" / "clip.video").read_bytes()).rate, 5)

    def test_settings_given(self):
        replace_resource(self.source, "font", "NotoSans16", [NOTO_SANS], height=20,
                         smoothed=False)
        facts = font_facts((self.source / "fonts" / "NotoSans16.zi").read_bytes())
        self.assertEqual((facts.height, facts.smoothed), (20, False))
        replace_resource(self.source, "sound", "beep", [SOURCES / "short22k.wav"])
        self.assertEqual(self.app()["sounds"], ["beep"])

    def test_a_utf_8_font_keeps_its_characters(self):
        folder = self.folder / "utf8"
        new_source_folder(folder, DeviceSettings(model_named("NX4832T035"), 0, "utf-8"),
                          "nextion")
        add_font(folder, NOTO_SANS, 16, characters="41-43")
        replace_resource(folder, "font", "NotoSans16", [NOTO_SANS], height=18)
        font = decode_font((folder / "fonts" / "NotoSans16.zi").read_bytes())
        self.assertEqual(sorted(font.characters), [0x20, 0x41, 0x42, 0x43])

    def test_a_placeholder_takes_a_new_name_and_no_defaults(self):
        remove_keeping_ids(self.source, "font", "NotoSans16")
        with self.assertRaisesRegex(NxwrightError, "height"):
            replace_resource(self.source, "font", "empty-slot-1", [NOTO_SANS])
        replace_resource(self.source, "font", "empty-slot-1", [NOTO_SANS], new_name="Small",
                         height=14)
        self.assertEqual(self.app()["fonts"], ["NotoSans24", "Small"])

    def test_refusals_write_nothing(self):
        self.add("p0", "picture", pic="a")
        green = self.picture("green", (0, 255, 0))
        before = self.files()
        for replace, message in (
                (lambda: replace_resource(self.source, "picture", "a", [green], new_name="c",
                                          checked=True),
                 "cannot give the picture a another name"),
                (lambda: replace_resource(self.source, "picture", "c", [green]),
                 "no picture named c"),
                (lambda: replace_resource(self.source, "sound", "beep",
                                          [SOURCES / "short22k.wav"], height=3),
                 "height"),
                (lambda: replace_resource(self.source, "picture", "a", []), "a file")):
            with self.subTest(message=message), self.assertRaisesRegex(NxwrightError, message):
                replace()
            self.assertEqual(self.files(), before)

    def test_the_command_searches_for_the_old_name_only_when_asked(self):
        self.add("p0", "picture", pic="a")
        green = self.picture("green", (0, 255, 0))
        arguments = ["replace", str(self.source), "picture", "a", str(green), "--name", "c"]
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors):
            self.assertEqual(main(arguments + ["--checked"]), 1)
        self.assertIn("cannot give the picture a another name", errors.getvalue())
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(arguments), 0)
        self.assertEqual(self.app()["pictures"][0], "c")

    def test_a_new_name_is_given_without_a_search_unless_checked(self):
        self.add("p0", "picture", pic="a")
        green = self.picture("green", (0, 255, 0))
        with mock.patch("nxwright.source.resource_removal.check_folder",
                        side_effect=AssertionError("the folder was built")):
            self.assertEqual(replace_resource(self.source, "picture", "a", [green],
                                              new_name="c")[0], "c")
        self.assertEqual(self.app()["pictures"][0], "c")
        # p0 still gives the old name, so the folder no longer builds.
        check = check_folder(folder_reader(self.source), lambda path: (self.source / path).exists())
        self.assertNotEqual(check.errors(), [])

    def test_the_command(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["replace", str(self.source), "animation", "blink",
                                   "--settings"]), 0)
        self.assertEqual(json.loads(output.getvalue()), {"duration": 100})
        green = self.picture("green", (0, 255, 0))
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["replace", str(self.source), "picture", "b", str(green)]), 0)
            self.assertEqual(main(["replace", str(self.source), "font", "NotoSans16",
                                   str(NOTO_SANS), "--height", "20", "--no-smoothing"]), 0)
        self.assertFalse(font_facts((self.source / "fonts" / "NotoSans16.zi")
                                    .read_bytes()).smoothed)


class RenameTest(FolderTestCase):

    def test_uses_in_page_files_and_code_follow(self):
        self.add("p0", "picture", pic="a")
        self.write_code("p0.pic=@pic(a)")
        written = rename_resource(self.source, "picture", "a", "logo")
        self.assertIn("pictures/logo.png", written)
        self.assertEqual(self.app()["pictures"], ["logo", "b"])
        self.assertFalse((self.source / "pictures" / "a.png").exists())
        self.assertIn('pic = "logo"', (self.source / "pages" / "page0.page.toml").read_text())
        self.assertIn("@pic(logo)", (self.source / "pages" / "page0.nx").read_text())
        self.assertTrue(self.builds())

    def test_each_kind(self):
        for kind, name, new, path in (("font", "NotoSans16", "Small", "fonts/Small.zi"),
                                      ("animation", "blink", "flash",
                                       "animations/flash.screen.gmov"),
                                      ("video", "clip", "film", "videos/film.video"),
                                      ("sound", "beep", "chime", "sounds/chime.wav")):
            with self.subTest(kind=kind):
                rename_resource(self.source, kind, name, new)
                self.assertTrue((self.source / path).is_file())
        self.assertTrue(self.builds())

    def test_nxlang_code(self):
        self.add("p0", "picture", pic="b")
        switch_to_nxlang(self.source)
        (self.source / "pages" / "page0.nx").write_text(
            "on page0.down:\n  p0.pic = @pic(a)\n", encoding="utf-8", newline="\n")
        rename_resource(self.source, "picture", "a", "logo")
        self.assertIn("@pic(logo)", (self.source / "pages" / "page0.nx").read_text())

    def test_a_picture_with_a_source_file_into_a_subfolder(self):
        (self.source / "pictures" / "a.source.png").write_bytes(
            (self.source / "pictures" / "a.png").read_bytes())
        rename_resource(self.source, "picture", "a", "day/a")
        self.assertTrue((self.source / "pictures" / "day" / "a.png").is_file())
        self.assertTrue((self.source / "pictures" / "day" / "a.source.png").is_file())
        self.assertFalse((self.source / "pictures" / "a.source.png").exists())

    def test_a_change_of_letter_case(self):
        self.add("p0", "picture", pic="a")
        rename_resource(self.source, "picture", "a", "A")
        self.assertEqual(self.app()["pictures"], ["A", "b"])
        self.assertIn("A.png", [path.name for path in (self.source / "pictures").iterdir()])
        self.assertTrue(self.builds())

    def test_refusals_write_nothing(self):
        before = self.files()
        for kind, name, new, message in (("picture", "a", "b", "has a picture named b"),
                                         ("picture", "a", "B", "has a picture named b"),
                                         ("picture", "c", "d", "no picture named c"),
                                         ("picture", "a", "a b", "name"),
                                         ("picture", "a", "a", "already")):
            with self.subTest(new=new), self.assertRaisesRegex(NxwrightError, message):
                rename_resource(self.source, kind, name, new)
            self.assertEqual(self.files(), before)

    def test_a_rename_builds_the_folder_only_when_checked(self):
        self.write_code("zz.val=1")
        before = self.files()
        with self.assertRaisesRegex(NxwrightError, "the folder's checks find an error"):
            rename_resource(self.source, "picture", "a", "logo", checked=True)
        self.assertEqual(self.files(), before)
        with mock.patch("nxwright.source.resource_renaming.check_folder",
                        side_effect=AssertionError("the folder was built")):
            rename_resource(self.source, "picture", "a", "logo")
        self.assertEqual(self.app()["pictures"], ["logo", "b"])

    def test_a_checked_rename_writes_the_same_files(self):
        self.add("p0", "picture", pic="a")
        checked = self.folder / "checked"
        shutil.copytree(self.source, checked)
        self.assertEqual(rename_resource(checked, "picture", "a", "logo", checked=True),
                         rename_resource(self.source, "picture", "a", "logo"))
        self.assertEqual(self.files(checked), self.files())

    def test_the_command_builds_the_folder_only_when_asked(self):
        self.write_code("zz.val=1")
        arguments = ["rename", str(self.source), "picture", "a", "logo"]
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors):
            self.assertEqual(main(arguments + ["--checked"]), 1)
        self.assertIn("the folder's checks find an error", errors.getvalue())
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(arguments), 0)
        self.assertEqual(self.app()["pictures"], ["logo", "b"])

    def test_a_failed_write_leaves_the_folder_as_it_was(self):
        self.add("p0", "picture", pic="a")
        before = self.files()
        real = Path.write_bytes

        def failing(path, data):
            if path.name == "page0.page.toml":
                raise OSError("disk full")
            return real(path, data)

        with mock.patch.object(Path, "write_bytes", failing), self.assertRaises(OSError):
            rename_resource(self.source, "picture", "a", "logo")
        self.assertEqual(self.files(), before)

    def test_the_command(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["rename", str(self.source), "sound", "beep", "chime"]), 0)
        self.assertIn("chime", output.getvalue())
        self.assertEqual(self.app()["sounds"], ["chime"])


if __name__ == "__main__":
    import unittest
    unittest.main()
