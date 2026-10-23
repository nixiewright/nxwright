"""nxwright font: a font drawn from a typeface file, or a ready-made font
file, added to a source folder."""
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
from nxwright.project.font_drawing import draw_font
from nxwright.project.screen_models import model_named
from nxwright.project.truetype import NOTO_SANS, TrueTypeFont
from nxwright.project.zi_font import (Glyph, decode_font, encode_font, font_facts, grid_table_codes,
                                      turned_font)
from nxwright.source.project_files import build
from nxwright.source.source_folder import new_source_folder
from nxwright.source.resource_adding import add_font, add_font_file
from tests.test_truetype import simple_glyph, truetype_file
from tests.test_zi_font import (chosen_characters_fixture, font_block, gb2312_font, grid_font,
                                utf8_font, utf8_fixture)

# The Editor's generator's file, upright, in iso-8859-1, without smoothing.
GENERATORS = Path(__file__).resolve().parent / "fixtures" / "fonts" / "NotoSans20-unsmoothed.zi"


def folder_files(folder: Path) -> dict:
    """Returns every file of a folder, by its path in the folder, with its bytes."""
    return {path.relative_to(folder).as_posix(): path.read_bytes()
            for path in folder.rglob("*") if path.is_file()}


class FontCommandTest(unittest.TestCase):

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.temp = Path(temporary.name)

    def new_folder(self, encoding: str = "iso-8859-1") -> Path:
        """Starts a source folder at rotation 90, in `encoding`."""
        folder = self.temp / ("folder-" + encoding)
        new_source_folder(folder, DeviceSettings(model_named("NX4832T035"), 90, encoding),
                          "nextion")
        return folder

    def test_fonts_added_and_built(self):
        folder = self.new_folder()
        with redirect_stdout(io.StringIO()) as printed:
            self.assertEqual(main(["font", str(folder), str(NOTO_SANS), "20"]), 0)
            self.assertEqual(main(["font", str(folder), str(NOTO_SANS), "16", "--name", "Keys",
                                   "--no-smoothing"]), 0)
        self.assertEqual(printed.getvalue().splitlines(),
                         ["Added the font NotoSans20 to %s" % folder,
                          "Added the font Keys to %s" % folder])
        # After the font a new folder starts with.
        self.assertEqual(tomllib.loads((folder / "app.toml").read_text(encoding="utf-8"))["fonts"],
                         ["NotoSans24", "NotoSans20", "Keys"])
        font = decode_font((folder / "fonts" / "NotoSans20.zi").read_bytes())
        self.assertEqual((font.name, font.height, font.rotation, font.encoding,
                          len(font.characters)), ("NotoSans20", 20, 90, "iso-8859-1", 224))
        # Without smoothing, each pixel is empty or full, and the header says so.
        block = (folder / "fonts" / "Keys.zi").read_bytes()
        self.assertEqual(block[30], 0)
        self.assertEqual({value for character in decode_font(block).characters.values()
                          for value in character.coverages()}, {0, 7})
        build(folder, self.temp / "project.HMI")
        self.assertTrue((self.temp / "project.HMI").is_file())

    def test_a_utf8_font_of_the_characters_asked_for(self):
        folder = self.new_folder("utf-8")
        with redirect_stdout(io.StringIO()) as printed:
            self.assertEqual(main(["font", str(folder), str(NOTO_SANS), "20",
                                   "--characters", "20-7e,400-4ff"]), 0)
        self.assertEqual(printed.getvalue(), "Added the font NotoSans20 to %s\n" % folder)
        # A table of the characters chosen, as the generator's "Specified
        # character" writes one: byte 5 at 2, and some kilobytes.
        block = (folder / "fonts" / "NotoSans20.zi").read_bytes()
        font = decode_font(block)
        self.assertEqual((font.encoding, font.rotation, sorted(font.characters)),
                         ("utf-8", 90, [*range(0x20, 0x7f), *range(0x400, 0x500)]))
        self.assertEqual(block[5], 2)
        self.assertLess(len(block), 100_000)
        # The generator's first two blocks by default.
        add_font(folder, NOTO_SANS, 16)
        self.assertEqual(sorted(decode_font((folder / "fonts" / "NotoSans16.zi").read_bytes())
                                .characters), list(range(0x100)))
        # The space, which the generator adds to the characters typed.
        add_font(folder, NOTO_SANS, 17, characters="41-5a")
        self.assertEqual(sorted(decode_font((folder / "fonts" / "NotoSans17.zi").read_bytes())
                                .characters), [0x20, *range(0x41, 0x5b)])
        # A full table, asked for: an entry for every code point to U+FFFF.
        with redirect_stdout(io.StringIO()) as printed:
            self.assertEqual(main(["font", str(folder), str(NOTO_SANS), "18",
                                   "--characters", "41-5a", "--full-table"]), 0)
        self.assertEqual(printed.getvalue(),
                         "Added the font NotoSans18 to %s. A font in utf-8 of a full table is at "
                         "least 655 KB, whatever characters it contains.\n" % folder)
        block = (folder / "fonts" / "NotoSans18.zi").read_bytes()
        self.assertEqual((block[5], sorted(decode_font(block).characters)),
                         (1, list(range(0x41, 0x5b))))
        self.assertGreater(len(block), 655_360)
        build(folder, self.temp / "project.HMI")
        # A one-byte encoding holds every character of its own.
        with self.assertRaisesRegex(NxwrightError, "a full table is for a utf-8 folder"):
            add_font(self.new_folder(), NOTO_SANS, 18, full_table=True)

    def test_a_font_of_the_characters_the_typeface_has(self):
        # Noto Sans lacks koi8-r's 56 box-drawing characters: the font holds
        # the others, with a gap the screen reads by code, and a warning says
        # what it lacks.
        warning = ("the typeface file lacks 56 characters of koi8-r, such as '─' (U+2500); the "
                   "font leaves them out, and the screen shows the font's first character, the "
                   "space, in their place")
        folder = self.new_folder("koi8-r")
        self.assertEqual(add_font(folder, NOTO_SANS, 20), ("NotoSans20", warning))
        block = (folder / "fonts" / "NotoSans20.zi").read_bytes()
        self.assertEqual((block[5], len(decode_font(block).characters)), (2, 224 - 56))
        with redirect_stdout(io.StringIO()) as printed, redirect_stderr(io.StringIO()) as said:
            self.assertEqual(main(["font", str(folder), str(NOTO_SANS), "18"]), 0)
        self.assertEqual(printed.getvalue(), "Added the font NotoSans18 to %s\n" % folder)
        self.assertEqual(said.getvalue(), "nxwright font: warning: %s\n" % warning)

    def test_a_font_in_each_two_byte_encoding(self):
        # Every position of the encoding's grid and the ascii characters, a
        # character the typeface lacks empty, as the warning says.
        for encoding, lacking in (("big5", 13578), ("shift-jis", 6741),
                                  ("ks_c_5601-1987", 3132)):
            with self.subTest(encoding=encoding):
                folder = self.new_folder(encoding)
                name, warning = add_font(folder, NOTO_SANS, 20)
                self.assertEqual(warning, "the typeface file lacks %d characters of %s, such as "
                                          "'\\u3000' (U+3000); the font leaves them out, and "
                                          "the screen shows nothing in their place, the height "
                                          "wide" % (lacking, encoding))
                font = decode_font((folder / "fonts" / (name + ".zi")).read_bytes())
                self.assertEqual((font.encoding, len(font.characters)),
                                 (encoding, len(grid_table_codes(encoding))))

    def test_a_typeface_without_a_name_a_font_may_have(self):
        # The font is named after its file instead.
        square = simple_glyph([(0, 0, True), (400, 0, True), (400, 600, True), (0, 600, True)])
        characters = {chr(code): 1 for code in range(0x20, 0x7f)}
        folder = self.new_folder("ascii")
        for file_name, names in (("Squares.ttf", None), ("Blocks.ttf", {1: "方块"})):
            with self.subTest(names=names):
                path = self.temp / file_name
                path.write_bytes(truetype_file([square, square], characters, names=names))
                self.assertEqual(add_font(folder, path, 16), (Path(file_name).stem + "16", None))

    def test_refusals_change_nothing(self):
        folder = self.new_folder()
        add_font(folder, NOTO_SANS, 20)
        (folder / "fonts" / "Stray.zi").write_bytes(b"not listed")
        utf8 = self.new_folder("utf-8")
        koi8 = self.new_folder("koi8-r")
        unset = self.temp / "unset"
        unset.mkdir()
        (unset / "app.toml").write_text('format = 1\nlanguage = "nextion"\npages = []\n'
                                        'pictures = []\nfonts = []\n', encoding="utf-8")
        for target, arguments, message in (
                (unset, (NOTO_SANS, 20), "app.toml gives no screen settings"),
                (folder, (NOTO_SANS, 24, "notosans20"), "the folder has a font named NotoSans20"),
                (folder, (NOTO_SANS, 24, "Stray"),
                 "Stray.zi is already there, though app.toml does not list it"),
                (folder, (NOTO_SANS, 24, "two words"), "fonts: 'two words' is not a valid name"),
                (folder, (NOTO_SANS, 11), "height 11 is not from 12 to 254"),
                (folder, (self.temp / "missing.ttf", 20), "missing.ttf is missing"),
                (folder, (NOTO_SANS, 24, "Big", True, "20-7e"),
                 "a font in iso-8859-1 holds every character of its encoding; characters are "
                 "chosen in utf-8 only"),
                (utf8, (NOTO_SANS, 20, None, True, "5d0-5ea"),
                 "the typeface file has none of the characters asked for"),
                (utf8, (NOTO_SANS, 20, None, True, "4ff-400"),
                 "the range 4ff-400 ends before it starts")):
            with self.subTest(message=message):
                before = folder_files(target)
                with self.assertRaisesRegex(NxwrightError, re.escape(message)):
                    add_font(target, *arguments)
                self.assertEqual(folder_files(target), before)


class FontFileTest(unittest.TestCase):
    """A ready-made font file (.zi) added to a source folder."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.temp = Path(temporary.name)

    def new_folder(self, encoding: str = "iso-8859-1", rotation: int = 0) -> Path:
        folder = self.temp / ("folder-%s-%d" % (encoding, rotation))
        new_source_folder(folder, DeviceSettings(model_named("NX4832T035"), rotation, encoding),
                          "nextion")
        return folder

    def font_file(self, name: str, block: bytes) -> Path:
        path = self.temp / name
        path.write_bytes(block)
        return path

    def test_copied_at_the_folders_rotation_after_its_fonts(self):
        folder = self.new_folder()
        add_font(folder, NOTO_SANS, 16)
        self.assertEqual(add_font_file(folder, GENERATORS), ("NotoSans20", None))
        self.assertEqual((folder / "fonts" / "NotoSans20.zi").read_bytes(),
                         GENERATORS.read_bytes())
        self.assertEqual(tomllib.loads((folder / "app.toml").read_text(encoding="utf-8"))["fonts"],
                         ["NotoSans24", "NotoSans16", "NotoSans20"])
        build(folder, self.temp / "project.HMI")

    def test_turned_to_the_folders_rotation(self):
        folder = self.new_folder(rotation=90)
        self.assertEqual(add_font_file(folder, GENERATORS, "Keys"), ("Keys", None))
        block = (folder / "fonts" / "Keys.zi").read_bytes()
        # The font keeps the name stored in it, as one renamed in a folder does.
        facts = font_facts(block)
        self.assertEqual((facts.name, facts.rotation, facts.smoothed), ("NotoSans20", 90, False))
        upright, turned = decode_font(GENERATORS.read_bytes()), decode_font(block)
        for code, character in upright.characters.items():
            self.assertEqual(turned.characters[code].coverages(), character.coverages(), code)

    def test_the_encodings_a_folder_takes(self):
        ascii_font = self.font_file("Small.zi", encode_font(
            "Small", "ascii", 16, 0, draw_font(TrueTypeFont(NOTO_SANS.read_bytes()), 16, "ascii")))
        self.assertEqual(add_font_file(self.new_folder(), ascii_font), ("Small", None))
        # Where Noto Sans does not cover the folder's encoding, as nxwright's keyboards do.
        for encoding in ("utf-8", "koi8-r"):
            with self.subTest(encoding=encoding):
                name, warning = add_font_file(self.new_folder(encoding), GENERATORS)
                self.assertEqual(warning, "the font NotoSans20 is in iso-8859-1, not in the "
                                          "folder's %s: text in characters beyond ascii shows "
                                          "garbled in it" % encoding)

    def test_a_font_nxwright_does_not_decode(self):
        # Copied as it is at the folder's rotation; refused at another, below.
        wide = self.font_file("Wide.zi", font_block([(65, 1, 0, 0, bytes([3, 0b00100001]))], 1,
                                                    encoding=16, name="Wide"))
        folder = self.new_folder("big5")
        self.assertEqual(add_font_file(folder, wide), ("Wide", None))
        self.assertEqual((folder / "fonts" / "Wide.zi").read_bytes(), wide.read_bytes())

    def test_a_gb2312_font_turned(self):
        # Turned as a one-byte font is, its table kept in its order.
        folder = self.new_folder("gb2312", 90)
        self.assertEqual(add_font_file(folder, self.font_file("Zh.zi", gb2312_font())),
                         ("Zh", None))
        self.assertEqual((folder / "fonts" / "Zh.zi").read_bytes(),
                         turned_font(gb2312_font(), 90))

    def test_the_other_two_byte_fonts_turned(self):
        for encoding in ("big5", "shift-jis", "ks_c_5601-1987"):
            with self.subTest(encoding=encoding):
                folder = self.new_folder(encoding, 90)
                self.assertEqual(add_font_file(folder, self.font_file("Grid.zi",
                                                                      grid_font(encoding))),
                                 ("Grid", None))
                self.assertEqual((folder / "fonts" / "Grid.zi").read_bytes(),
                                 turned_font(grid_font(encoding), 90))

    def test_a_utf8_font_turned_as_the_editor_turns_it(self):
        upright = self.font_file("NotoSans20.zi", utf8_fixture("NotoSans20"))
        folder = self.new_folder("utf-8", 90)
        self.assertEqual(add_font_file(folder, upright), ("NotoSans20", None))
        self.assertEqual((folder / "fonts" / "NotoSans20.zi").read_bytes(),
                         utf8_fixture("NotoSans20-90"))

    def test_a_utf8_font_of_chosen_characters_turned_as_the_editor_turns_it(self):
        upright = self.font_file("specified16.zi",
                                 chosen_characters_fixture("NotoSans16-specified"))
        folder = self.new_folder("utf-8", 90)
        self.assertEqual(add_font_file(folder, upright), ("specified16", None))
        self.assertEqual((folder / "fonts" / "specified16.zi").read_bytes(),
                         chosen_characters_fixture("NotoSans16-specified-90"))

    def test_refusals_change_nothing(self):
        folder = self.new_folder()
        add_font_file(folder, GENERATORS)
        koi8 = self.font_file("Cyrillic.zi", encode_font("Cyrillic", "koi8-r", 1, 0,
                                                         [Glyph(0x41, 1, 0, 0, (7,))]))
        unset = self.temp / "unset"
        unset.mkdir()
        (unset / "app.toml").write_text('format = 1\nlanguage = "nextion"\npages = []\n'
                                        'pictures = []\nfonts = []\n', encoding="utf-8")
        for target, arguments, message in (
                (unset, (GENERATORS,), "app.toml gives no screen settings"),
                (folder, (self.font_file("Text.zi", b"hello"),),
                 "Text.zi is not a font: the font is shorter than its 44-byte header"),
                # Cut short, at the folder's rotation: read whole, though not turned.
                (folder, (self.font_file("Cut.zi", GENERATORS.read_bytes()[:-1]),),
                 "Cut.zi is not a font: the glyph of character 255 runs past the font's end"),
                (folder, (koi8,), "the font is in koi8-r, and a folder in iso-8859-1 takes "
                                  "fonts in iso-8859-1 or ascii"),
                (folder, (GENERATORS,), "the folder has a font named NotoSans20"),
                # A font in utf-8 is read whole too.
                (self.new_folder("utf-8"), (self.font_file("CutWide.zi", utf8_font()[:-1]),),
                 "CutWide.zi is not a font: the glyph of character 65 runs past the font's end"),
                (self.new_folder("big5", 90), (self.font_file("Wide.zi", font_block(
                    [(65, 1, 0, 0, bytes([3, 0b00100001]))], 1, encoding=16)),),
                 "the font is stored at rotation 0, where the folder's is 90, and nxwright "
                 "cannot turn it: a font in big5 of byte 5 at 0 has not been seen")):
            with self.subTest(message=message):
                before = folder_files(target)
                with self.assertRaisesRegex(NxwrightError, re.escape(message)):
                    add_font_file(target, *arguments)
                self.assertEqual(folder_files(target), before)

    def test_the_command(self):
        folder = self.new_folder("utf-8")
        with redirect_stdout(io.StringIO()) as printed, redirect_stderr(io.StringIO()) as said:
            self.assertEqual(main(["font", str(folder), str(GENERATORS), "--name", "Text"]), 0)
            self.assertEqual(main(["font", str(folder), str(GENERATORS), "20"]), 1)
            self.assertEqual(main(["font", str(folder), str(GENERATORS), "--characters", "20-7e"]),
                             1)
            self.assertEqual(main(["font", str(folder), str(GENERATORS), "--full-table"]), 1)
            self.assertEqual(main(["font", str(folder), str(NOTO_SANS)]), 1)
        self.assertEqual(printed.getvalue(), "Added the font Text to %s\n" % folder)
        self.assertEqual(said.getvalue().splitlines(), [
            "nxwright font: warning: the font Text is in iso-8859-1, not in the folder's utf-8: "
            "text in characters beyond ascii shows garbled in it",
            "nxwright font: a font file (.zi) is added as it is; give no height, no "
            "--no-smoothing, no --characters, and no --full-table",
            "nxwright font: a font file (.zi) is added as it is; give no height, no "
            "--no-smoothing, no --characters, and no --full-table",
            "nxwright font: a font file (.zi) is added as it is; give no height, no "
            "--no-smoothing, no --characters, and no --full-table",
            "nxwright font: a font drawn from a typeface file needs a height"])
