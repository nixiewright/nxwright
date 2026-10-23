"""`nxwright device`: changing a source folder's screen model, rotation, and
encoding, and the files that depend on them, as the Editor's Device window
does."""
import contextlib
import io
from pathlib import Path
import tempfile
import tomllib
import unittest

from nxwright import NxwrightError
from nxwright.cli import main
from nxwright.project.device_settings import DeviceSettings
from nxwright.project.media_files import video_rotation
from nxwright.project.pictures import write_png
from nxwright.project.screen_models import model_named
from nxwright.project.font_drawing import draw_font_block
from nxwright.project.truetype import NOTO_SANS, TrueTypeFont
from nxwright.project.zi_font import decode_font, grid_table_codes, turned_font
from nxwright.source.device_change import change_device
from nxwright.source.source_folder import export_dump, new_source_folder
from nxwright.source.resource_adding import add_animation, add_font, add_font_file, add_video
from tests.test_folder_check import edited_app
from tests.test_media import folder_files
from tests.test_zi_font import font_block, gb2312_font, grid_font


class DeviceChangeTestCase(unittest.TestCase):

    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.folder = Path(self._folder.name)
        self.source = self.folder / "app"

    def tearDown(self):
        self._folder.cleanup()

    def make(self, model: str, rotation: int = 0, encoding: str = "iso-8859-1"):
        """A new source folder of `model` at `rotation`, whose page0 holds
        t1, a text at 200, 400, 100 by 60."""
        new_source_folder(self.source, DeviceSettings(model_named(model), rotation, encoding),
                          "nextion")
        self.add('name = "t1"\ntype = "text"\nx = 200\ny = 400\nw = 100\nh = 60\n')

    def add(self, table: str):
        with open(self.source / "pages" / "page0.page.toml", "a", encoding="utf-8",
                  newline="\n") as file:
            file.write("\n[[component]]\n" + table)

    def app(self) -> dict:
        return tomllib.loads((self.source / "app.toml").read_text(encoding="utf-8"))

    def page(self) -> dict:
        return tomllib.loads((self.source / "pages" / "page0.page.toml").read_text(
            encoding="utf-8"))

    def add_media(self):
        """An animation, blink, and a video, clip, each of two frames 40 by
        24, made for the folder's rotation."""
        frames = []
        for number, colour in enumerate(((255, 0, 0, 255), (0, 0, 255, 255))):
            frame = self.folder / ("frame%d.png" % number)
            frame.write_bytes(write_png(40, 24, bytes(colour) * (40 * 24)))
            frames.append(frame)
        add_animation(self.source, frames, 100, "blink")
        add_video(self.source, frames, name="clip")


class ScreenModelTest(DeviceChangeTestCase):

    def test_a_model_of_another_size(self):
        # The page takes the new screen's size, and each component keeps its
        # place and size.
        self.make("NX4832K035")
        before = self.page()["component"]
        change = change_device(self.source, screen="NX8048K050")
        self.assertEqual(change.written, ["pages/page0.page.toml", "app.toml"])
        self.assertEqual(self.app()["screen"], "NX8048K050")
        page = self.page()
        self.assertEqual((page["page"]["w"], page["page"]["h"]), (800, 480))
        self.assertEqual(page["component"], before)
        self.assertEqual(change.refusals, [])
        export_dump(self.source, self.folder / "built")

    def test_a_page_file_of_crlf_line_endings(self):
        # It keeps them: only its w and h change.
        self.make("NX4832K035")
        page_file = self.source / "pages" / "page0.page.toml"
        before = page_file.read_bytes().replace(b"\n", b"\r\n")
        page_file.write_bytes(before)
        change_device(self.source, screen="NX8048K050")
        after = page_file.read_bytes()
        changed = [(old, new) for old, new in zip(before.split(b"\r\n"), after.split(b"\r\n"))
                   if old != new]
        self.assertEqual(changed, [(b"w = 320", b"w = 800")])
        self.assertEqual(after.count(b"\n"), after.count(b"\r\n"))

    def test_what_the_build_then_refuses(self):
        # t1, at 200, 400, lies past a screen 240 by 320, which the Editor's
        # compile refused on the Enhanced series ("Position Invalid").
        self.make("NX4832K035")
        change = change_device(self.source, screen="NX3224K024")
        self.assertEqual(len(change.refusals), 1)
        self.assertIn("t1", change.refusals[0])
        self.assertIn("reaches past the screen", change.refusals[0])

    def test_a_model_of_another_series(self):
        # The Editor kept a select on a Basic screen, which lacks the type,
        # and refused it as it compiled.
        self.make("NX8048P050")
        self.add('name = "s0"\ntype = "select"\nx = 0\ny = 0\nw = 120\nh = 120\n')
        change = change_device(self.source, screen="NX4832T035")
        self.assertEqual(self.app()["screen"], "NX4832T035")
        self.assertTrue(any("lacks the type select" in refusal for refusal in change.refusals),
                        change.refusals)


class RotationTest(DeviceChangeTestCase):

    def test_a_rotation(self):
        # The page is turned, each font turned as the Editor turns it, each
        # video made again for the new rotation, and each animation kept, as
        # the Editor keeps it.
        self.make("NX8048P050")
        self.add_media()
        before = folder_files(self.source)
        change = change_device(self.source, rotation=90)
        after = folder_files(self.source)
        self.assertEqual(self.app()["rotation"], 90)
        page = self.page()["page"]
        self.assertEqual((page["w"], page["h"]), (480, 800))
        fonts = [path for path in before if path.startswith("fonts/")]
        self.assertTrue(fonts)
        for path in fonts:
            self.assertEqual(after[path], turned_font(before[path], 90))
        for path in ("animations/blink.gmov", "animations/blink.screen.gmov"):
            self.assertEqual(after[path], before[path])
        self.assertEqual(video_rotation(after["videos/clip.video"]), 90)
        self.assertEqual(len(change.notes), 1)
        self.assertIn("videos/clip.video", change.notes[0])
        self.assertEqual(change.refusals, [])
        export_dump(self.source, self.folder / "built")

    def test_each_step_is_told_as_it_starts(self):
        # So that a long change, as a video coded again, shows what it does.
        self.make("NX8048P050")
        self.add_media()
        fonts = sorted(path for path in folder_files(self.source) if path.startswith("fonts/"))
        told = []
        change = change_device(self.source, rotation=90, told=told.append)
        self.assertEqual(told[0], "Resizing page 1 of 1 to 480 x 800: pages/page0.page.toml")
        self.assertEqual([line.split(": ")[1] for line in told
                          if line.startswith("Rotating font ")], fonts)
        self.assertIn("Rotating video 1 of 1 to 90 degrees, 2 frames: videos/clip.video", told)
        self.assertEqual(told[-2:], ["Writing %d file(s)" % len(change.written),
                                     "Checking the project for what the build will refuse"])

    def test_a_page_left_as_it_is_is_not_told(self):
        # Turned half a turn, a page keeps its size: nothing is resized.
        self.make("NX8048P050")
        told = []
        change_device(self.source, rotation=180, told=told.append)
        self.assertFalse([line for line in told if line.startswith("Resizing")], told)
        self.assertTrue([line for line in told if line.startswith("Rotating font ")], told)

    def test_a_gb2312_font_turned(self):
        self.make("NX4832T035", encoding="gb2312")
        font = self.folder / "Zh.zi"
        font.write_bytes(gb2312_font())
        add_font_file(self.source, font, "Zh")
        change_device(self.source, rotation=90)
        self.assertEqual((self.source / "fonts" / "Zh.zi").read_bytes(),
                         turned_font(gb2312_font(), 90))

    def test_a_font_nxwright_cannot_turn(self):
        # A font nxwright does not read, one character marked as in big5,
        # which is no grid of every position: the folder keeps every font at
        # its rotation, as `nxwright font` does.
        self.make("NX4832T035", encoding="big5")
        font = self.folder / "Wide.zi"
        font.write_bytes(font_block([(65, 1, 0, 0, bytes([3, 0b00100001]))], 1, encoding=16))
        add_font_file(self.source, font, "Wide")
        before = folder_files(self.source)
        with self.assertRaisesRegex(NxwrightError, r"fonts/Wide\.zi.*byte 5 at 0"):
            change_device(self.source, rotation=90)
        self.assertEqual(folder_files(self.source), before)

    def test_a_big5_font_turned(self):
        self.make("NX4832T035", encoding="big5")
        font = self.folder / "Ch.zi"
        font.write_bytes(grid_font("big5"))
        add_font_file(self.source, font, "Ch")
        change_device(self.source, rotation=90)
        self.assertEqual((self.source / "fonts" / "Ch.zi").read_bytes(),
                         turned_font(grid_font("big5"), 90))


class EncodingTest(DeviceChangeTestCase):

    def font_block(self, name: str) -> bytes:
        return (self.source / "fonts" / (name + ".zi")).read_bytes()

    def first_font(self) -> str:
        return self.app()["fonts"][0]

    def add_text(self, text: str):
        """Adds t2, a text of `text` in the folder's first font."""
        self.add('name = "t2"\ntype = "text"\nx = 0\ny = 100\nw = 200\nh = 40\ntxt = "%s"\n'
                 % text)

    def test_a_one_byte_font_made_utf8(self):
        # Each glyph keyed by its character, in a table of chosen characters,
        # which the screen searches by code (header byte 5 at 2). A text of
        # an "é" then builds, stored in utf-8.
        self.make("NX8048P050")
        self.add_text("Café")
        name = self.first_font()
        before = decode_font(self.font_block(name))
        change = change_device(self.source, encoding="utf-8")
        self.assertEqual(self.app()["encoding"], "utf-8")
        block = self.font_block(name)
        after = decode_font(block)
        self.assertEqual((after.encoding, block[5]), ("utf-8", 2))
        # iso-8859-1's bytes are the code points of their characters.
        self.assertEqual(sorted(after.characters), sorted(before.characters))
        self.assertEqual(after.characters[0xE9].coverages(), before.characters[0xE9].coverages())
        self.assertEqual(change.refusals, [])
        self.assertTrue(any("fonts/%s.zi" % name in note for note in change.notes),
                        change.notes)
        export_dump(self.source, self.folder / "built")

    def test_a_one_byte_font_made_another_one_byte(self):
        # iso-8859-2 has "é" at the same byte, and lacks "ñ", left out and
        # named. The font then leaves a gap, at the byte of iso-8859-2's own
        # character there, which the old font lacked: the screen searches it
        # by code. A text holding "ñ" is then refused by the build.
        self.make("NX8048P050")
        self.add_text("Año")
        name = self.first_font()
        before = decode_font(self.font_block(name))
        change = change_device(self.source, encoding="iso-8859-2")
        block = self.font_block(name)
        after = decode_font(block)
        self.assertEqual((after.encoding, block[5]), ("iso-8859-2", 2))
        self.assertEqual(after.characters[0xE9].coverages(), before.characters[0xE9].coverages())
        self.assertNotIn(0xF1, after.characters)
        # "ñ", U+00F1, among the run of those left out, a range.
        self.assertTrue(any("U+00EF to U+00F2" in note for note in change.notes), change.notes)
        self.assertTrue(any("t2" in refusal or "cannot store" in refusal
                            for refusal in change.refusals), change.refusals)

    def test_the_apps_name_is_kept(self):
        self.make("NX8048P050")
        app = self.source / "app.toml"
        app.write_text(edited_app(app.read_text(encoding="utf-8"),
                                  lambda data: data.update(name="Clock")), encoding="utf-8")
        change_device(self.source, rotation=90)
        self.assertEqual(tomllib.loads(app.read_text(encoding="utf-8"))["name"], "Clock")

    def test_a_utf8_font_made_one_byte(self):
        # The characters below the space are left out of a one-byte font,
        # which starts at it.
        self.make("NX8048P050", encoding="utf-8")
        name, _ = add_font(self.source, NOTO_SANS, 16)
        change = change_device(self.source, encoding="iso-8859-1")
        after = decode_font(self.font_block(name))
        self.assertEqual((after.encoding, min(after.characters)), ("iso-8859-1", 0x20))
        self.assertTrue(any("U+0000 to U+001F" in note for note in change.notes),
                        change.notes)
        export_dump(self.source, self.folder / "built")

    def test_a_font_the_new_encoding_takes_stays(self):
        # A keyboard's iso-8859-1 font in a utf-8 folder, which a folder made
        # iso-8859-1 takes as its own.
        self.make("NX8048P050", encoding="utf-8")
        typeface = TrueTypeFont(NOTO_SANS.read_bytes())
        font = self.folder / "Keys16.zi"
        font.write_bytes(draw_font_block("Keys16", typeface, 16, "iso-8859-1", 0))
        add_font_file(self.source, font, "Keys16")
        kept = self.font_block("Keys16")
        change_device(self.source, encoding="iso-8859-1")
        self.assertEqual(self.font_block("Keys16"), kept)

    def test_a_rotation_keeps_each_fonts_encoding(self):
        # An ascii font in an iso-8859-2 folder, as an extracted project
        # may hold, is turned, not converted, when the encoding stays.
        self.make("NX8048P050", encoding="iso-8859-2")
        font = self.source / "fonts" / "Small.zi"
        font.write_bytes(font_block([(65, 1, 0, 0, bytes([3, 0b00100001]))], 1, encoding=1))
        app_file = self.source / "app.toml"
        app_file.write_text(app_file.read_text(encoding="utf-8").replace(
            "fonts = [\n", 'fonts = [\n    "Small",\n'), encoding="utf-8", newline="\n")
        self.assertEqual(self.app()["fonts"][0], "Small")
        before = font.read_bytes()
        change = change_device(self.source, rotation=90)
        self.assertEqual(font.read_bytes(), turned_font(before, 90))
        self.assertFalse(any("converted" in note for note in change.notes), change.notes)

    def test_a_folder_made_gb2312_and_back(self):
        # Its font is converted each way, as the folder's texts are built in
        # the new encoding: "Café" in gb2312, then in iso-8859-1 again, its é
        # kept throughout; ÿ, which gb2312 lacks, is left out and named.
        self.make("NX8048P050")
        self.add_text("Café")
        name = self.first_font()
        before = decode_font(self.font_block(name))
        change = change_device(self.source, encoding="gb2312")
        made = decode_font(self.font_block(name))
        self.assertEqual((made.encoding, len(made.characters)), ("gb2312", 8273))
        self.assertEqual(made.characters[0xa6a8].coverages(), before.characters[0xe9].coverages())
        self.assertTrue(any("U+00FF" in note for note in change.notes), change.notes)
        self.assertEqual(change.refusals, [])
        export_dump(self.source, self.folder / "gb2312")
        change = change_device(self.source, encoding="iso-8859-1")
        # The 7,000-some Chinese characters it leaves out are counted, the
        # first named, so the note stays short.
        note, = [note for note in change.notes if "leaving out" in note]
        self.assertRegex(note, r"leaving out (U\+[0-9A-F]{4}(?: to U\+[0-9A-F]{4})?, ){64}"
                               r"and \d+ more characters, which iso-8859-1 lacks")
        back = decode_font(self.font_block(name))
        self.assertEqual(back.encoding, "iso-8859-1")
        self.assertEqual(back.characters[0xe9].coverages(), before.characters[0xe9].coverages())
        export_dump(self.source, self.folder / "back")

    def test_a_big5_font_made_utf8(self):
        # Each position's glyph goes to the character cp950 gives it: 中,
        # a4 a4, to U+4E2D.
        self.make("NX4832T035", encoding="big5")
        font = self.folder / "Ch.zi"
        font.write_bytes(grid_font("big5"))
        add_font_file(self.source, font, "Ch")
        change_device(self.source, encoding="utf-8")
        made = decode_font(self.font_block("Ch"))
        self.assertEqual(made.encoding, "utf-8")
        self.assertEqual(made.characters[0x4e2d].coverages(),
                         decode_font(grid_font("big5")).characters[0xa4a4].coverages())

    def test_a_folder_made_each_other_two_byte_encoding_and_back(self):
        # Its font is converted each way, ascii's C kept throughout; DEL, the
        # first character past ascii, which none of the three has, is left
        # out and named, as are the others they lack.
        for encoding in ("big5", "shift-jis", "ks_c_5601-1987"):
            with self.subTest(encoding=encoding):
                self.source = self.folder / encoding
                self.make("NX8048P050")
                name = self.first_font()
                before = decode_font(self.font_block(name))
                change = change_device(self.source, encoding=encoding)
                made = decode_font(self.font_block(name))
                self.assertEqual((made.encoding, len(made.characters)),
                                 (encoding, len(grid_table_codes(encoding))))
                self.assertEqual(made.characters[0x43].coverages(),
                                 before.characters[0x43].coverages())
                self.assertTrue(any("leaving out U+007F" in note for note in change.notes),
                                change.notes)
                change_device(self.source, encoding="iso-8859-1")
                back = decode_font(self.font_block(name))
                self.assertEqual((back.encoding, back.characters[0x43].coverages()),
                                 ("iso-8859-1", before.characters[0x43].coverages()))


class RefusalTest(DeviceChangeTestCase):

    def test_settings_given_their_present_values(self):
        self.make("NX4832K035")
        before = folder_files(self.source)
        change = change_device(self.source, screen="NX4832K035", rotation=0)
        self.assertEqual(change.written, [])
        self.assertEqual(folder_files(self.source), before)

    def test_a_font_whose_file_is_missing(self):
        self.make("NX4832K035")
        font = next((self.source / "fonts").iterdir())
        font.unlink()
        before = folder_files(self.source)
        with self.assertRaisesRegex(NxwrightError, "%s is missing" % font.name):
            change_device(self.source, rotation=90)
        self.assertEqual(folder_files(self.source), before)

    def test_what_is_not_a_setting(self):
        self.make("NX4832K035")
        before = folder_files(self.source)
        for settings, reason in (({}, "give a screen model, a rotation, or an encoding"),
                                 ({"screen": "NX0000Z000"}, "NX0000Z000"),
                                 ({"rotation": 45}, "45"),
                                 ({"encoding": "klingon"}, "klingon")):
            with self.subTest(reason=reason):
                with self.assertRaisesRegex(NxwrightError, reason):
                    change_device(self.source, **settings)
                self.assertEqual(folder_files(self.source), before)


class CommandTest(DeviceChangeTestCase):

    def test_it_says_what_it_wrote_and_what_the_build_refuses(self):
        self.make("NX4832K035")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["device", str(self.source), "--screen", "NX3224K024"]), 0)
        text = output.getvalue()
        for words in ("pages/page0.page.toml", "app.toml", "The build now refuses", "t1"):
            self.assertIn(words, text)

    def test_an_encoding(self):
        self.make("NX8048P050")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["device", str(self.source), "--encoding", "utf-8"]), 0)
        self.assertIn("converted to utf-8", output.getvalue())


if __name__ == "__main__":
    unittest.main()
