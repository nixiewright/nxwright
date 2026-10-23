"""Drawing fonts from typeface files: Noto Sans, drawn as the Editor's fonts
drawn from it are, and written and read back."""
from dataclasses import replace
from pathlib import Path
import re
from types import SimpleNamespace
import unittest

from nxwright import NxwrightError
from nxwright.project.device_settings import TextCodec
from nxwright.project.font_drawing import (check_drawable, code_point_ranges, code_points_of,
                                           draw_characters, draw_font, lacking_characters)
from nxwright.project.truetype import NOTO_SANS, TrueTypeFont
from nxwright.project.zi_font import Glyph, decode_font, encode_font, grid_table_codes
from tests.test_truetype import GLYPHS, truetype_file
from tests.test_zi_font import utf8_fixture

FONTS = Path(__file__).resolve().parent / "fixtures" / "fonts"
# Bytes the Editor's iso-8859-1 fonts give widths of their own: DEL, 0x84,
# the next-line control, and the soft hyphen (font_drawing.py).
OWN_WIDTHS = (0x7f, 0x84, 0x85, 0xad)


class DrawingTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.noto = TrueTypeFont(NOTO_SANS.read_bytes())

    def test_advances_as_the_editors(self):
        # Sans12 is of the lowest height the generator makes.
        for name in ("Sans12.zi", "Sans16.zi", "Sans20.zi", "Sans100.zi",
                     "NotoSans20-unsmoothed.zi"):
            with self.subTest(font=name):
                editors = decode_font((FONTS / name).read_bytes())
                glyphs = draw_font(self.noto, editors.height, "iso-8859-1")
                self.assertEqual([glyph.code for glyph in glyphs], sorted(editors.characters))
                for glyph in glyphs:
                    if glyph.code not in OWN_WIDTHS:
                        self.assertLessEqual(
                            abs(glyph.advance - editors.characters[glyph.code].advance), 1,
                            "character %#x" % glyph.code)

    def test_pixels_close_to_the_editors(self):
        # Over every character, aligned at the pen, the pixels more than a
        # level from the Editor's: at most this share of those the Editor's
        # font inks, measured with FreeType 2.13.2 and rounded up to a percent.
        for name, font, most in (
                ("Sans12", (FONTS / "Sans12.zi").read_bytes(), 0.64),
                ("Sans16", (FONTS / "Sans16.zi").read_bytes(), 0.79),
                ("Sans20", (FONTS / "Sans20.zi").read_bytes(), 0.40),
                ("Sans100", (FONTS / "Sans100.zi").read_bytes(), 0.32),
                ("NotoSans20-unsmoothed", (FONTS / "NotoSans20-unsmoothed.zi").read_bytes(), 0.37),
                ("NotoSans17", utf8_fixture("NotoSans17"), 0.28)):
            with self.subTest(font=name):
                editors = decode_font(font)
                glyphs = draw_characters(self.noto, editors.height, editors.encoding,
                                         sorted(editors.characters), editors.smoothed)
                inked = apart = 0
                for glyph in glyphs:
                    character = editors.characters[glyph.code]
                    theirs = _inked_from_the_pen(character, character.coverages(),
                                                 editors.height)
                    ours = _inked_from_the_pen(glyph, glyph.coverages, editors.height)
                    inked += len(theirs)
                    apart += sum(abs(theirs.get(pixel, 0) - ours.get(pixel, 0)) > 1
                                 for pixel in theirs.keys() | ours.keys())
                self.assertLessEqual(apart, most * inked)

    def test_overhangs(self):
        # As in the Editor's Sans100, the hook of j reaches left of the pen,
        # and the top of f past its advance.
        glyphs = {glyph.code: glyph for glyph in draw_font(self.noto, 100, "iso-8859-1")}
        self.assertGreater(glyphs[ord("j")].left, 0)
        self.assertGreater(glyphs[ord("f")].right, 0)
        self.assertEqual((glyphs[ord("H")].left, glyphs[ord("H")].right), (0, 0))
        # windows-1258's combining grave accent takes no room: it lies left of
        # the pen, over the character before it.
        grave = [glyph for glyph in draw_font(self.noto, 100, "windows-1258")
                 if glyph.code == 0xcc][0]
        self.assertEqual((grave.advance, grave.right), (0, 0))
        self.assertGreater(grave.left, 0)
        self.assertTrue(any(grave.coverages))

    def test_written_and_read_back_at_each_rotation(self):
        for encoding, last in (("ascii", 0x7e), ("iso-8859-1", 0xff), ("windows-1257", 0xff),
                               ("windows-1258", 0xff)):
            glyphs = draw_font(self.noto, 16, encoding)
            for rotation in (0, 90, 180, 270):
                with self.subTest(encoding=encoding, rotation=rotation):
                    font = decode_font(encode_font("Noto16", encoding, 16, rotation, glyphs))
                    self.assertEqual(sorted(font.characters), list(range(0x20, last + 1)))
                    for glyph in glyphs:
                        self.assertEqual(tuple(font.characters[glyph.code].coverages()),
                                         glyph.coverages, "character %#x" % glyph.code)

    def test_the_characters_of_the_encoding(self):
        glyphs = {glyph.code: glyph for glyph in draw_font(self.noto, 20, "iso-8859-1")}
        # DEL, the next-line control, and the soft hyphen are empty, a pixel wide.
        for code in (0x7f, 0x85, 0xad):
            self.assertEqual((glyphs[code].advance, glyphs[code].coverages), (1, (0,) * 20))
        # The other control characters are the missing-character glyph.
        missing = glyphs[0x80]
        self.assertTrue(any(missing.coverages))
        for code in [*range(0x81, 0x85), *range(0x86, 0xa0)]:
            self.assertEqual(glyphs[code], replace(missing, code=code))
        # The no-break space is empty, as wide as the space.
        self.assertFalse(any(glyphs[0xa0].coverages))
        self.assertEqual(glyphs[0xa0].advance, glyphs[0x20].advance)
        # A byte the encoding leaves undefined gets the missing-character glyph.
        baltic = {glyph.code: glyph for glyph in draw_font(self.noto, 20, "windows-1257")}
        self.assertEqual(baltic[0x81], replace(missing, code=0x81))

    def test_without_smoothing(self):
        glyphs = draw_font(self.noto, 16, "iso-8859-1", smoothed=False)
        self.assertEqual({value for glyph in glyphs for value in glyph.coverages}, {0, 7})
        block = encode_font("Noto16", "iso-8859-1", 16, 0, glyphs, smoothed=False)
        self.assertEqual(block[30], (FONTS / "NotoSans20-unsmoothed.zi").read_bytes()[30])
        # The dots of ü are each less than half of every pixel they touch;
        # FreeType's dropout control keeps them.
        by_code = {glyph.code: glyph for glyph in glyphs}
        u, u_umlaut = by_code[ord("u")], by_code[ord("ü")]
        self.assertGreater(sum(u_umlaut.coverages), sum(u.coverages))

    def test_a_typeface_lacking_some_characters_of_the_encoding(self):
        # Noto Sans lacks koi8-r's 56 box-drawing characters. The font holds
        # the others, with a gap past which the screen finds them by code,
        # and a warning says what it lacks.
        lacking = {character.encode("koi8-r")[0]
                   for character in lacking_characters(self.noto, "koi8-r")}
        self.assertEqual(len(lacking), 56)
        glyphs = draw_font(self.noto, 24, "koi8-r")
        self.assertEqual([glyph.code for glyph in glyphs],
                         [code for code in range(0x20, 0x100) if code not in lacking])
        self.assertEqual(encode_font("NotoSans24", "koi8-r", 24, 0, glyphs)[5], 2)
        self.assertEqual(check_drawable(self.noto, 24, "koi8-r"),
                         "the typeface file lacks 56 characters of koi8-r, such as '─' "
                         "(U+2500); the font leaves them out, and the screen shows the font's "
                         "first character, the space, in their place")
        # A typeface that lacks none: no warning, and the font as before.
        self.assertIsNone(check_drawable(self.noto, 24, "iso-8859-1"))

    def test_refusals(self):
        for arguments, pattern in (
                ((16, "windows-1252"), "a font in windows-1252 cannot be drawn"),
                # The heights the Editor's generator makes.
                ((11, "iso-8859-1"), "height 11 is not from 12 to 254"),
                ((255, "iso-8859-1"), "height 255 is not from 12 to 254")):
            with self.subTest(pattern=pattern), self.assertRaisesRegex(NxwrightError, pattern):
                draw_font(self.noto, *arguments)
        # A character the typeface lacks, asked for by its byte.
        with self.assertRaisesRegex(NxwrightError, r"the typeface file lacks 1 characters? of "
                                                   r"koi8-r, such as '─' \(U\+2500\)"):
            draw_characters(self.noto, 16, "koi8-r", [0x41, 0x80])
        # Metrics that leave the font no height are refused before anything else is read.
        flat = SimpleNamespace(ascender=-293, descender=-293)
        with self.assertRaisesRegex(NxwrightError, "ascender, -293, is not above its descender"):
            draw_font(flat, 16, "iso-8859-1")
        # Bytes a font has no character for, which draw_characters is given.
        for encoding, code in (("iso-8859-1", 0x0a), ("ascii", 0x80)):
            with self.subTest(code=code), self.assertRaisesRegex(
                    NxwrightError, "a font in %s has no character for byte %d" % (encoding, code)):
                draw_characters(self.noto, 16, encoding, [0x41, code])

    def test_some_characters_drawn_as_in_the_whole_font(self):
        whole = {glyph.code: glyph for glyph in draw_font(self.noto, 24, "iso-8859-1", False)}
        self.assertEqual(draw_characters(self.noto, 24, "iso-8859-1", [0x41, 0x67, 0xe9], False),
                         [whole[0x41], whole[0x67], whole[0xe9]])


class Gb2312DrawingTest(unittest.TestCase):
    """Fonts in gb2312 drawn from a typeface: every position of the grid and
    the ascii characters, in the table's order (docs/format.md, gb2312
    fonts). Noto Sans has GB2312's Greek and Cyrillic, but none of its
    Chinese characters."""

    @classmethod
    def setUpClass(cls):
        cls.noto = TrueTypeFont(NOTO_SANS.read_bytes())
        cls.glyphs = {glyph.code: glyph for glyph in draw_font(cls.noto, 12, "gb2312")}

    def test_every_position_in_the_tables_order(self):
        glyphs = draw_font(self.noto, 12, "gb2312")
        self.assertEqual([glyph.code for glyph in glyphs], grid_table_codes("gb2312"))
        block = encode_font("Noto12", "gb2312", 12, 0, glyphs)
        self.assertEqual(len(decode_font(block).characters), 8273)

    def test_what_each_position_holds(self):
        def code(character: str) -> int:
            first, second = character.encode("gb2312")
            return first | second << 8

        # GB2312's α and Ж, and ascii's A, drawn from the typeface.
        for character in ("α", "Ж"):
            self.assertTrue(any(self.glyphs[code(character)].coverages), character)
        self.assertTrue(any(self.glyphs[0x41].coverages))
        # 中, which it lacks, and a2 ab, which neither GB2312 nor GBK names:
        # empty, as wide as the font is tall.
        for empty in (code("中"), 0xaba2):
            glyph = self.glyphs[empty]
            self.assertEqual((glyph.advance, glyph.left, glyph.right, any(glyph.coverages)),
                             (12, 0, 0, False))

    def test_its_warning(self):
        self.assertEqual(check_drawable(self.noto, 12, "gb2312"),
                         "the typeface file lacks 7282 characters of gb2312, such as "
                         "'\\u3000' (U+3000); the font leaves them out, and the screen shows "
                         "nothing in their place, the height wide")

    def test_refusals(self):
        euro = TrueTypeFont(truetype_file(GLYPHS, {"€": 1}))
        with self.assertRaisesRegex(NxwrightError, "the typeface file has none of the "
                                                   "characters of gb2312"):
            draw_font(euro, 12, "gb2312")
        with self.assertRaisesRegex(NxwrightError, "a font in gb2312 holds every character of "
                                                   "its encoding"):
            draw_font(self.noto, 12, "gb2312", characters=[0x41])
        with self.assertRaisesRegex(NxwrightError, "a font in gb2312 has no character 81 40"):
            draw_characters(self.noto, 12, "gb2312", [0x41, 0x4081])


class OtherGridsDrawingTest(unittest.TestCase):
    """Fonts in big5, shift-jis, and ks_c_5601-1987 drawn from a typeface, as
    in gb2312: every position of the grid and the ascii characters, each
    position as the code page the folder's texts are stored by gives it,
    cp950, cp932, and cp949 (docs/format.md, Two-byte fonts). Noto Sans has
    their Greek and Cyrillic, but none of their Chinese characters, kana, or
    Hangul."""

    # Per encoding: a Greek letter's bytes, a character Noto Sans lacks,
    # and how many of the encoding's characters it lacks.
    CASES = {"big5": ("a3 5c", "中", 13578), "shift-jis": ("83 bf", "亜", 6741),
             "ks_c_5601-1987": ("a5 e1", "가", 3132)}

    @classmethod
    def setUpClass(cls):
        cls.noto = TrueTypeFont(NOTO_SANS.read_bytes())

    def test_every_position_in_the_tables_order(self):
        for encoding in self.CASES:
            with self.subTest(encoding=encoding):
                glyphs = draw_font(self.noto, 12, encoding)
                self.assertEqual([glyph.code for glyph in glyphs], grid_table_codes(encoding))
                block = encode_font("Noto12", encoding, 12, 0, glyphs)
                self.assertEqual(len(decode_font(block).characters),
                                 len(grid_table_codes(encoding)))

    def test_what_each_position_holds(self):
        for encoding, (alpha, lacked, _) in self.CASES.items():
            with self.subTest(encoding=encoding):
                glyphs = {glyph.code: glyph for glyph in draw_font(self.noto, 12, encoding)}
                first, second = bytes.fromhex(alpha)
                self.assertTrue(any(glyphs[first | second << 8].coverages))
                first, second = lacked.encode(TextCodec(encoding).codec_name)
                glyph = glyphs[first | second << 8]
                self.assertEqual((glyph.advance, glyph.left, glyph.right, any(glyph.coverages)),
                                 (12, 0, 0, False))

    def test_its_warning(self):
        for encoding, (_, _, lacking) in self.CASES.items():
            with self.subTest(encoding=encoding):
                self.assertEqual(check_drawable(self.noto, 12, encoding),
                                 "the typeface file lacks %d characters of %s, such as "
                                 "'\\u3000' (U+3000); the font leaves them out, and the screen "
                                 "shows nothing in their place, the height wide"
                                 % (lacking, encoding))


class Utf8DrawingTest(unittest.TestCase):
    """Fonts in utf-8 drawn from Noto Sans: the code points asked for, the
    controls as the Editor's generator draws them, and a code point Unicode
    leaves unassigned as the box. A character the typeface lacks is refused:
    the generator draws it from another typeface Windows picks."""

    @classmethod
    def setUpClass(cls):
        cls.noto = TrueTypeFont(NOTO_SANS.read_bytes())

    def test_the_generators_first_two_blocks(self):
        glyphs = {glyph.code: glyph for glyph in draw_font(self.noto, 20, "utf-8")}
        self.assertEqual(sorted(glyphs), list(range(0x100)))
        # U+0020 to U+00FF are iso-8859-1's bytes 20 to ff, controls included.
        latin = {glyph.code: glyph for glyph in draw_font(self.noto, 20, "iso-8859-1")}
        for code in range(0x20, 0x100):
            self.assertEqual(glyphs[code], latin[code], hex(code))
        # Of U+0000 to U+001F, these are empty, a pixel wide; the others the box.
        empty = (0x00, 0x02, 0x09, 0x0a, 0x0b, 0x0d, 0x1c, 0x1d, 0x1e, 0x1f)
        for code in range(0x20):
            self.assertEqual(glyphs[code], Glyph(code, 1, 0, 0, (0,) * 20) if code in empty
                             else replace(latin[0x80], code=code), hex(code))

    def test_the_characters_asked_for(self):
        cyrillic = draw_font(self.noto, 20, "utf-8", characters=code_points_of("20-7e,400-4ff"))
        self.assertEqual([glyph.code for glyph in cyrillic],
                         [*range(0x20, 0x7f), *range(0x400, 0x500)])
        # Within a pixel of the generator's advances, as a one-byte font's are.
        editors = decode_font(utf8_fixture("NotoSans20-cyrillic")).characters
        self.assertEqual([glyph.code for glyph in cyrillic
                          if abs(glyph.advance - editors[glyph.code].advance) > 1], [])

    def test_an_unassigned_code_point_is_the_box(self):
        # Hebrew's U+05C8 and U+05CF, which no version of Unicode assigns.
        box = draw_characters(self.noto, 20, "utf-8", [0x80])[0]
        self.assertEqual(draw_characters(self.noto, 20, "utf-8", [0x5c8, 0x5cf]),
                         [replace(box, code=0x5c8), replace(box, code=0x5cf)])

    def test_characters_the_typeface_lacks(self):
        # Noto Sans has no Hebrew letters: the font holds the others, and
        # the space; a warning says what it lacks, and what the screen shows
        # in their place in a table of chosen characters and in a full one.
        asked = code_points_of("41-5a,5d0-5ea")
        glyphs = draw_font(self.noto, 20, "utf-8", characters=asked)
        self.assertEqual([glyph.code for glyph in glyphs], [0x20, *range(0x41, 0x5b)])
        self.assertEqual(check_drawable(self.noto, 20, "utf-8", asked),
                         "the typeface file lacks 27 of the characters asked for, such as 'א' "
                         "(U+05D0); the font leaves them out, and the screen shows the font's "
                         "first character, the space, in their place")
        self.assertEqual(check_drawable(self.noto, 20, "utf-8", asked, full_table=True),
                         "the typeface file lacks 27 of the characters asked for, such as 'א' "
                         "(U+05D0); the font leaves them out, and the screen shows nothing in "
                         "their place, half the height wide")

    def test_refusals(self):
        # Noto Sans has none of the Hebrew letters, all a font would hold.
        with self.assertRaisesRegex(NxwrightError, "the typeface file has none of the "
                                                   "characters asked for"):
            draw_font(self.noto, 20, "utf-8", characters=code_points_of("5d0-5ea"))
        with self.assertRaisesRegex(NxwrightError, r"a font in utf-8 has no character U\+10000"):
            draw_characters(self.noto, 20, "utf-8", [0x41, 0x10000])
        # Asked for of a whole font too, before what the typeface lacks is sorted out.
        for name, call in (
                ("draw_font", lambda: draw_font(self.noto, 20, "utf-8",
                                                characters=[0x41, 0x10000])),
                ("check_drawable", lambda: check_drawable(self.noto, 20, "utf-8",
                                                          characters=[0x41, 0x10000]))):
            with self.subTest(call=name), self.assertRaisesRegex(
                    NxwrightError, r"a font in utf-8 has no character U\+10000"):
                call()
        with self.assertRaisesRegex(NxwrightError, "a font in iso-8859-1 holds every character "
                                                   "of its encoding"):
            draw_font(self.noto, 20, "iso-8859-1", characters=[0x41])

    def test_checked_without_drawing(self):
        # What draw_font refuses, quickly, as for the Fonts panel's form.
        self.assertIsNone(check_drawable(self.noto, 20, "iso-8859-1"))
        self.assertIsNone(check_drawable(self.noto, 20, "utf-8", code_points_of("20-7e,400-4ff")))
        # A typeface that lacks some is drawn without them, with a warning.
        self.assertIn("lacks 88 of", check_drawable(self.noto, 20, "utf-8",
                                                    code_points_of("590-5ff")))
        self.assertIn("lacks 56 characters of koi8-r", check_drawable(self.noto, 20, "koi8-r"))
        with self.assertRaisesRegex(NxwrightError, "height 11 is not from 12 to 254"):
            check_drawable(self.noto, 11, "utf-8")

    def test_ranges_of_code_points(self):
        self.assertEqual(code_points_of("20-22, 41,400-401"),
                         [0x20, 0x21, 0x22, 0x41, 0x400, 0x401])
        # In order, each once.
        self.assertEqual(code_points_of("41,20-41"), list(range(0x20, 0x42)))
        for text, pattern in (
                (" ", "no characters are given"),
                ("20,zz", "'zz' is not a code point in hexadecimal, nor a range of them such "
                          "as 400-4ff"),
                ("4ff-400", "the range 4ff-400 ends before it starts"),
                ("ff-10000", "U+10000 lies past U+FFFF, the last a font in utf-8 holds"),
                ("0-ffff", "U+D800 to U+DFFF are surrogates, not characters: leave them out, "
                           "as in 0-d7ff,e000-ffff")):
            with self.subTest(text=text), self.assertRaisesRegex(NxwrightError, re.escape(pattern)):
                code_points_of(text)

    def test_code_points_written_as_ranges(self):
        # code_points_of's inverse: runs, single code points, and gaps.
        for points, ranges in (([0x20, 0x21, 0x22, 0x41, 0x400, 0x401], "20-22,41,400-401"),
                               ([0], "0"), ([0xd7ff, 0xe000], "d7ff,e000")):
            with self.subTest(ranges=ranges):
                self.assertEqual(code_point_ranges(points), ranges)
                self.assertEqual(code_points_of(ranges), points)
        # Surrogates, which code_points_of refuses, are left out.
        self.assertEqual(code_point_ranges([0x41, 0xd800, 0xdfff]), "41")


def _inked_from_the_pen(glyph, levels, height: int) -> dict:
    """Returns {(x from the pen, y): level} of the inked pixels of a Glyph,
    or of a font's Character, whose levels, row by row, are `levels`."""
    width = glyph.left + glyph.advance + glyph.right
    return {(column - glyph.left, row): levels[row * width + column]
            for row in range(height) for column in range(width) if levels[row * width + column]}
