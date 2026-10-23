"""nxwright keyboard: one of nxwright's keyboard pages added to a source
folder."""
from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
import re
import tempfile
import tomllib
import unittest

from nxwright import NxwrightError
from nxwright.cli import main
from nxwright.project.device_settings import DeviceSettings
from nxwright.project.screen_models import model_named
from nxwright.project.font_drawing import draw_font_block
from nxwright.project.truetype import NOTO_SANS, TrueTypeFont
from nxwright.project.zi_font import decode_font
from nxwright.source.keyboards import keyboard
from nxwright.source.project_files import build
from nxwright.source.source_folder import new_source_folder
from nxwright.source.resource_adding import add_font, add_font_file
from nxwright.source.keyboard_adding import add_keyboard
from tests.test_folder_check import edited_app
from tests.test_font_command import folder_files
from tests.test_zi_font import utf8_fixture


class KeyboardCommandTest(unittest.TestCase):

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.temp = Path(temporary.name)

    def new_folder(self, encoding: str = "iso-8859-1", language: str = "nextion",
                   name: str = None) -> Path:
        """Starts a source folder on NX4832T035 at rotation 90: a page 480
        pixels by 320."""
        folder = self.temp / (name or "%s-%s" % (encoding, language))
        new_source_folder(folder, DeviceSettings(model_named("NX4832T035"), 90, encoding),
                          language)
        return folder

    def add_page(self, folder: Path, name: str, header: str = ""):
        """Adds a blank page to a folder, its header holding `header`."""
        (folder / "pages" / (name + ".page.toml")).write_text(
            '[page]\nname = "%s"\ntype = "page"\n%sx = 0\ny = 0\nw = 480\nh = 320\n'
            % (name, header), encoding="utf-8")
        (folder / "pages" / (name + ".nx")).write_text("", encoding="utf-8")
        app = folder / "app.toml"
        app.write_text(edited_app(app.read_text(encoding="utf-8"),
                                  lambda data: data["pages"].append(name)), encoding="utf-8")

    def test_each_keyboard_added_and_built(self):
        for language in ("nextion", "nxlang"):
            with self.subTest(language=language):
                folder = self.new_folder(language=language)
                with redirect_stdout(io.StringIO()) as printed:
                    for kind in ("keyboard", "keypad", "speed-dial"):
                        self.assertEqual(main(["keyboard", str(folder), kind]), 0)
                self.assertTrue(printed.getvalue().startswith(
                    "Added the keyboard page keybdA, with the font NotoSans"))
                app = tomllib.loads((folder / "app.toml").read_text(encoding="utf-8"))
                self.assertEqual(app["pages"], ["page0", "keybdA", "keybdB", "keybdC"])
                for page, kind in (("keybdA", "keyboard"), ("keybdB", "keypad"),
                                   ("keybdC", "speed-dial")):
                    header = tomllib.loads((folder / "pages" / (page + ".page.toml"))
                                           .read_text(encoding="utf-8"))["page"]
                    self.assertEqual((header["system_page"], header["w"], header["h"]),
                                     (kind, 480, 320))
                for name in app["fonts"]:
                    font = decode_font((folder / "fonts" / (name + ".zi")).read_bytes())
                    self.assertEqual((font.name, font.rotation, font.encoding),
                                     (name, 90, "iso-8859-1"))
                build(folder, self.temp / ("%s.HMI" % language))

    def test_a_font_in_another_encoding_comes_with_a_warning(self):
        # A big5 folder holding the keypad's font in iso-8859-1, as a folder
        # made before nxwright drew fonts in big5 may: the keyboard uses it as
        # it is, and warns.
        latin = self.new_folder("iso-8859-1")
        _, name, _ = add_keyboard(latin, "keypad")
        folder = self.new_folder("big5")
        add_font_file(folder, latin / "fonts" / (name + ".zi"))
        with redirect_stderr(io.StringIO()) as warned, redirect_stdout(io.StringIO()):
            self.assertEqual(main(["keyboard", str(folder), "keypad"]), 0)
        self.assertIn("warning: the keyboard's font, %s, is in iso-8859-1, not in the "
                      "folder's big5" % name, warned.getvalue())
        self.assertEqual(decode_font((folder / "fonts" / (name + ".zi")).read_bytes())
                         .encoding, "iso-8859-1")
        # An encoding Noto Sans covers gets its own font, and no warning.
        folder = self.new_folder("windows-1257")
        _, name, warning = add_keyboard(folder, "keypad")
        self.assertIsNone(warning)
        self.assertEqual(decode_font((folder / "fonts" / (name + ".zi")).read_bytes()).encoding,
                         "windows-1257")

    def test_a_gb2312_font(self):
        # Drawn from Noto Sans, which has none of GB2312's Chinese characters:
        # a caller's Chinese text shows them empty, not garbled. A gb2312
        # folder still takes an iso-8859-1 font, as a keyboard took there
        # before.
        folder = self.new_folder("gb2312")
        _, name, warning = add_keyboard(folder, "keypad")
        font = decode_font((folder / "fonts" / (name + ".zi")).read_bytes())
        self.assertEqual((font.encoding, len(font.characters)), ("gb2312", 8273))
        self.assertEqual(warning, "the keyboard's font, %s, is drawn from Noto Sans, which lacks "
                                  "7282 characters of gb2312, such as '\\u3000' (U+3000): a "
                                  "caller's text in them shows nothing in their place, the "
                                  "height wide" % name)
        latin1 = self.temp / "Latin1.zi"
        latin1.write_bytes(draw_font_block("Latin1", TrueTypeFont(NOTO_SANS.read_bytes()), 20,
                                           "iso-8859-1", 0))
        self.assertEqual(add_font_file(folder, latin1)[0], "Latin1")

    def test_a_font_in_the_other_two_byte_encodings(self):
        # As in gb2312: drawn from Noto Sans, which has none of their Chinese
        # characters, kana, or Hangul, so a caller's text in them shows
        # empty, not garbled.
        for encoding, lacking in (("big5", 13578), ("shift-jis", 6741),
                                  ("ks_c_5601-1987", 3132)):
            with self.subTest(encoding=encoding):
                folder = self.new_folder(encoding)
                _, name, warning = add_keyboard(folder, "keypad")
                font = decode_font((folder / "fonts" / (name + ".zi")).read_bytes())
                self.assertEqual(font.encoding, encoding)
                self.assertEqual(warning, "the keyboard's font, %s, is drawn from Noto Sans, "
                                          "which lacks %d characters of %s, such as '\\u3000' "
                                          "(U+3000): a caller's text in them shows nothing in "
                                          "their place, the height wide"
                                          % (name, lacking, encoding))

    def test_the_command_says_the_size_of_a_two_byte_font(self):
        # A font in a two-byte encoding holds every character of its grid,
        # so it is large, as the Chinese keyboard's is. A one-byte font's
        # size is not said.
        for encoding, said in (("big5", True), ("iso-8859-1", False)):
            with self.subTest(encoding=encoding):
                folder = self.new_folder(encoding)
                with redirect_stdout(io.StringIO()) as printed, redirect_stderr(io.StringIO()):
                    self.assertEqual(main(["keyboard", str(folder), "keypad"]), 0)
                name = re.search(r"with the font (\w+)", printed.getvalue()).group(1)
                font = folder / "fonts" / (name + ".zi")
                size = "%s (%d KB)" % (name, round(font.stat().st_size / 1024))
                self.assertEqual(size in printed.getvalue(), said, printed.getvalue())

    def test_a_font_without_what_noto_sans_lacks(self):
        # koi8-r, whose box-drawing characters Noto Sans lacks: the keyboard's
        # font is in koi8-r without them, and a caller's Cyrillic shows as it
        # is. A koi8-r folder still takes an iso-8859-1 font, as a keyboard
        # took there before.
        folder = self.new_folder("koi8-r")
        _, name, warning = add_keyboard(folder, "keypad")
        font = decode_font((folder / "fonts" / (name + ".zi")).read_bytes())
        self.assertEqual((font.encoding, len(font.characters)), ("koi8-r", 224 - 56))
        self.assertEqual(font.lacking("Жук".encode("koi8-r")), [])
        self.assertEqual(warning, "the keyboard's font, %s, is drawn from Noto Sans, which lacks "
                                  "56 characters of koi8-r, such as '─' (U+2500): a "
                                  "caller's text in them shows the font's first character, the "
                                  "space, in their place" % name)
        latin1 = self.temp / "Latin1.zi"
        latin1.write_bytes(draw_font_block("Latin1", TrueTypeFont(NOTO_SANS.read_bytes()), 20,
                                           "iso-8859-1", 90))
        self.assertEqual(add_font_file(folder, latin1)[0], "Latin1")

    def test_a_utf8_folder_gets_a_utf8_font(self):
        # Of U+0000 to U+00FF, the characters of iso-8859-1, as a table of
        # them alone: a caller's "café" shows as it is.
        folder = self.new_folder("utf-8")
        _, name, warning = add_keyboard(folder, "keypad")
        font = decode_font((folder / "fonts" / (name + ".zi")).read_bytes())
        self.assertEqual((font.encoding, font.rotation), ("utf-8", 90))
        self.assertEqual(sorted(font.characters), list(range(0x100)))
        self.assertIsNone(font.advances)     # a table of chosen characters, not a full one
        self.assertEqual(font.lacking("café".encode("utf-8")), [])
        self.assertEqual(warning, "the keyboard's font, %s, holds the characters U+0000 to U+00FF: "
                                  "a caller's text in another character shows the font's first "
                                  "character in its place, a pixel's gap" % name)

    def test_a_font_of_its_name_is_used_as_it_is(self):
        folder = self.new_folder()
        name = keyboard("keypad", 480, 320).font_name
        height = int(name[len("NotoSans"):])
        add_font(folder, NOTO_SANS, height, smoothed=False)
        before = (folder / "fonts" / (name + ".zi")).read_bytes()
        self.assertEqual(add_keyboard(folder, "keypad"), ("keybdB", name, None))
        self.assertEqual((folder / "fonts" / (name + ".zi")).read_bytes(), before)
        app = tomllib.loads((folder / "app.toml").read_text(encoding="utf-8"))
        # After the font a new folder starts with.
        self.assertEqual(app["fonts"], ["NotoSans24", name])

    def test_a_utf8_font_of_its_name_is_used_as_it_is(self):
        # A font in utf-8 from the Editor's generator, stored at the folder's rotation.
        folder = self.new_folder("utf-8")
        name = keyboard("keypad", 480, 320).font_name
        (folder / "fonts").mkdir(exist_ok=True)
        (folder / "fonts" / (name + ".zi")).write_bytes(utf8_fixture("NotoSans20-90"))
        app = folder / "app.toml"
        app.write_text(edited_app(app.read_text(encoding="utf-8"),
                                  lambda data: data.update(fonts=[name])), encoding="utf-8")
        self.assertEqual(add_keyboard(folder, "keypad"), ("keybdB", name, None))

    def test_refusals_change_nothing(self):
        added = self.new_folder(name="added")
        add_keyboard(added, "keyboard")
        stock = self.new_folder(name="stock")
        self.add_page(stock, "kb", 'system_page = "keyboard"\n')
        taken = self.new_folder(name="taken")
        self.add_page(taken, "keybdC")
        stray = self.new_folder(name="stray")
        (stray / "pages" / "keybdB.page.toml").write_text("", encoding="utf-8")
        # A font of the keyboard's font's name but for its letter case.
        cased = self.new_folder(name="cased")
        keypad_font = keyboard("keypad", 480, 320).font_name
        add_font(cased, NOTO_SANS, 20, name=keypad_font.lower())
        unset = self.temp / "unset"
        unset.mkdir()
        (unset / "app.toml").write_text('format = 1\nlanguage = "nextion"\npages = []\n'
                                        'pictures = []\nfonts = []\n', encoding="utf-8")
        for folder, kind, message in (
                (added, "keyboard", "the folder has the keyboard already: page keybdA"),
                (stock, "keyboard", "the folder has the keyboard already: page kb"),
                (taken, "speed-dial", "the folder has a page named keybdC that is not the "
                                      "speed-dial"),
                (stray, "keypad", "keybdB.page.toml is already there, though app.toml does "
                                  "not list it"),
                (unset, "keypad", "app.toml gives no screen settings"),
                (cased, "keypad", "fonts: %s and %s are the same name"
                                  % (keypad_font.lower(), keypad_font))):
            with self.subTest(message=message):
                before = folder_files(folder)
                with self.assertRaisesRegex(NxwrightError, re.escape(message)):
                    add_keyboard(folder, kind)
                self.assertEqual(folder_files(folder), before)
