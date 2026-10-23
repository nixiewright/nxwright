"""The installed typefaces nxwright can draw a font from. The tests find
them in folders they make, never in the computer's own fonts, which differ
from machine to machine and may not be shared."""
import os
from pathlib import Path
import string
import sys
import tempfile
import unicodedata
import unittest
from unittest import mock

from nxwright.project.device_settings import TextCodec
from nxwright.project.installed_typefaces import Typeface, font_folders, installed_typefaces
from nxwright.project.truetype import NOTO_SANS
from nxwright.project.zi_font import grid_table_codes
from tests.test_truetype import FONTS, GLYPHS, truetype_file


def renamed_noto_sans(family: str, file: Path = NOTO_SANS) -> bytes:
    """Noto Sans, from `file`, under another family name, nine characters
    long, as its name table's records hold "Noto Sans": a second typeface
    that has every character of iso-8859-1."""
    return file.read_bytes().replace("Noto Sans".encode("utf-16-be"),
                                     family.encode("utf-16-be"))


class InstalledTypefacesTest(unittest.TestCase):

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.temp = Path(temporary.name)

    def write(self, relative: str, data: bytes) -> Path:
        path = self.temp / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def test_the_typefaces_listed(self):
        toto = self.write("first/toto.ttf", renamed_noto_sans("Toto Sans"))
        # Noto Sans again, which the list has already, from the file nxwright ships.
        self.write("first/noto.ttf", NOTO_SANS.read_bytes())
        # A typeface lacking characters of the encoding, and a file that is no font.
        self.write("first/tiny.ttf", truetype_file(GLYPHS, {"A": 1}, names={1: "Tiny"}))
        self.write("first/broken.ttf", b"not a font")
        # An OpenType file, and a collection, listed by its first typeface.
        otto = self.write("first/otto.otf", renamed_noto_sans("Otto Sans",
                                                              FONTS / "NotoSans-Latin1.otf"))
        coll = self.write("first/coll.ttc", renamed_noto_sans("Coll Sans",
                                                              FONTS / "NotoSans-Latin1.ttc"))
        # A file of another kind is not looked at.
        self.write("first/other.fon", renamed_noto_sans("Fony Sans"))
        # In a subfolder of the second folder, with its suffix in capitals.
        abcd = self.write("second/sub/ABCD.TTF", renamed_noto_sans("Abcd Sans"))
        # Toto Sans again, which the first folder gave already.
        self.write("second/toto.ttf", renamed_noto_sans("Toto Sans"))
        listed = installed_typefaces("iso-8859-1", [self.temp / "first", self.temp / "second",
                                                    self.temp / "missing"])
        self.assertEqual(listed, [Typeface("Noto Sans", NOTO_SANS), Typeface("Abcd Sans", abcd),
                                  Typeface("Coll Sans", coll), Typeface("Otto Sans", otto),
                                  Typeface("Toto Sans", toto)])

    def test_noto_sans_first_in_every_one_byte_encoding(self):
        # Even where it lacks characters: koi8-r's box-drawing ones, or
        # windows-874's Thai letters, which a font drawn from it leaves out.
        for encoding in ("ascii", "koi8-r", "windows-874"):
            with self.subTest(encoding=encoding):
                self.assertEqual(installed_typefaces(encoding, []),
                                 [Typeface("Noto Sans", NOTO_SANS)])

    def test_a_typeface_lacking_symbols_but_no_letter(self):
        # A Noto Sans by another name lacks koi8-r's box-drawing characters,
        # symbols, and is listed; it lacks windows-874's Thai letters, and
        # is not.
        toto = self.write("toto.ttf", renamed_noto_sans("Toto Sans"))
        self.assertEqual(installed_typefaces("koi8-r", [self.temp]),
                         [Typeface("Noto Sans", NOTO_SANS), Typeface("Toto Sans", toto)])
        self.assertEqual(installed_typefaces("windows-874", [self.temp]),
                         [Typeface("Noto Sans", NOTO_SANS)])

    def test_utf8_takes_every_typeface(self):
        # Which characters a font in utf-8 holds is chosen as it is drawn,
        # so a typeface lacking some is listed: drawing leaves those out.
        tiny = self.write("tiny.ttf", truetype_file(GLYPHS, {"A": 1}, names={1: "Tiny"}))
        self.write("broken.ttf", b"not a font")
        self.assertEqual(installed_typefaces("utf-8", [self.temp]),
                         [Typeface("Noto Sans", NOTO_SANS), Typeface("Tiny", tiny)])

    def test_gb2312_lists_the_typefaces_of_its_letters(self):
        # Noto Sans first, though it has none of GB2312's Chinese characters;
        # then a typeface that has every letter of a gb2312 font, ascii's
        # among them, its symbols aside; and not one of ascii's letters alone.
        letters = {letter: 1 for letter in string.ascii_letters}
        for first in range(0xa1, 0xf8):
            for second in range(0xa1, 0xff):
                try:
                    character = bytes([first, second]).decode("gb2312")
                except UnicodeDecodeError:
                    continue
                if unicodedata.category(character).startswith("L"):
                    letters[character] = 1
        han = self.write("han.ttf", truetype_file(GLYPHS, letters, names={1: "Han Sans"}))
        self.write("tiny.ttf", truetype_file(GLYPHS, {"A": 1}, names={1: "Tiny"}))
        self.assertEqual(installed_typefaces("gb2312", [self.temp]),
                         [Typeface("Noto Sans", NOTO_SANS), Typeface("Han Sans", han)])

    def test_the_other_two_byte_encodings_list_the_typefaces_of_their_letters(self):
        # As in gb2312: a typeface that has every letter of the grid's
        # characters, each as the folder's code page gives it. big5's 13,000
        # letters are more than the test's typeface files hold (truetype_file,
        # one segment of its character map each), so in big5 only Noto Sans
        # first, and Tiny left out.
        self.write("tiny.ttf", truetype_file(GLYPHS, {"A": 1}, names={1: "Tiny"}))
        self.assertEqual(installed_typefaces("big5", [self.temp]),
                         [Typeface("Noto Sans", NOTO_SANS)])
        for encoding in ("shift-jis", "ks_c_5601-1987"):
            with self.subTest(encoding=encoding):
                letters = {letter: 1 for letter in string.ascii_letters}
                for code in grid_table_codes(encoding):
                    if code < 0x100:
                        continue        # an ascii character, among the letters already
                    data = bytes([code & 0xff, code >> 8])
                    try:
                        data.decode(encoding)
                    except UnicodeDecodeError:
                        continue
                    character = data.decode(TextCodec(encoding).codec_name)
                    if unicodedata.category(character).startswith("L"):
                        letters[character] = 1
                name = "Han Sans %s" % encoding
                han = self.write("%s.ttf" % encoding, truetype_file(GLYPHS, letters,
                                                                   names={1: name}))
                listed = installed_typefaces(encoding, [self.temp])
                self.assertEqual((listed[0], Typeface(name, han) in listed,
                                  "Tiny" in [typeface.name for typeface in listed]),
                                 (Typeface("Noto Sans", NOTO_SANS), True, False))

    def test_the_systems_font_folders(self):
        with mock.patch.object(sys, "platform", "win32"), mock.patch.dict(
                os.environ, {"WINDIR": r"W:\Windows", "LOCALAPPDATA": r"L:\Local"}):
            self.assertEqual(font_folders(),
                             [Path(r"W:\Windows") / "Fonts",
                              Path(r"L:\Local") / "Microsoft" / "Windows" / "Fonts"])
        with mock.patch.object(sys, "platform", "darwin"):
            self.assertEqual(font_folders()[:2], [Path("/System/Library/Fonts"),
                                                  Path("/Library/Fonts")])
        with mock.patch.object(sys, "platform", "linux"):
            self.assertEqual(font_folders()[:2], [Path("/usr/share/fonts"),
                                                  Path("/usr/local/share/fonts")])


if __name__ == "__main__":
    unittest.main()
