"""Samples of text drawn in a font, for the Fonts panel: in a font already
made, and in a font about to be drawn from a typeface file."""
from pathlib import Path
import unittest

from nxwright import NxwrightError
from nxwright.drawing.font_samples import font_sample, sample_font, sample_note
from nxwright.drawing.text_pictures import MissingCharacter, text_picture
from nxwright.project.font_drawing import draw_font
from nxwright.project.pictures import read_picture
from nxwright.project.truetype import NOTO_SANS, TrueTypeFont
from nxwright.project.zi_font import decode_font, encode_font

FONTS = Path(__file__).resolve().parent / "fixtures" / "fonts"
WHITE = (255, 255, 255)


class FontSampleTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.sans20 = decode_font((FONTS / "Sans20.zi").read_bytes())
        cls.noto = TrueTypeFont(NOTO_SANS.read_bytes())

    def pixels(self, png: bytes) -> tuple:
        """Returns a PNG's width, height, and its pixels as RGBA bytes."""
        image = read_picture(png)
        return image.width, image.height, image.tobytes()

    def test_a_sample_of_a_font(self):
        width = sum(self.sans20.characters[ord(character)].advance for character in "Living room")
        expected = text_picture("Living room", self.sans20, "iso-8859-1", {"xcen": 0, "ycen": 0},
                                width, 20, WHITE)
        self.assertEqual(self.pixels(font_sample(self.sans20, "Living room", "iso-8859-1", WHITE)),
                         (width, 20, expected))

    def test_text_in_another_encoding_than_the_fonts(self):
        # Each byte of "é" in utf-8 is drawn as the iso-8859-1 font's character, "Ã©".
        self.assertEqual(font_sample(self.sans20, "é", "utf-8", WHITE),
                         font_sample(self.sans20, "Ã©", "iso-8859-1", WHITE))

    def test_a_font_about_to_be_drawn(self):
        # Of two lines: the line break is no character of the font. It holds
        # the font's first character too, the space.
        text = "Ågé\n21.5°"
        drawn = sample_font(self.noto, 24, "iso-8859-1", True, text)
        self.assertEqual(sorted(drawn.characters),
                         sorted(set(" Ågé21.5°".encode("iso-8859-1"))))
        whole = decode_font(encode_font("Whole", "iso-8859-1", 24, 0,
                                        draw_font(self.noto, 24, "iso-8859-1")))
        self.assertEqual(font_sample(drawn, text, "iso-8859-1", WHITE),
                         font_sample(whole, text, "iso-8859-1", WHITE))
        # A tab, which the encoding writes and the font lacks, is drawn as
        # the screen draws it, as the font's first character.
        drawn = sample_font(self.noto, 24, "iso-8859-1", True, "a\tb")
        self.assertEqual(sorted(drawn.characters), sorted(b" ab"))
        self.assertEqual(font_sample(drawn, "a\tb", "iso-8859-1", WHITE),
                         font_sample(whole, "a\tb", "iso-8859-1", WHITE))

    def test_a_font_in_utf8_about_to_be_drawn(self):
        # Its characters are the text's code points, not its bytes.
        text = "Жук\nü"
        held = [*range(0x100), *range(0x400, 0x500)]
        drawn = sample_font(self.noto, 24, "utf-8", True, text, held)
        # And the font's first, U+0000, which the generator draws empty.
        self.assertEqual(sorted(drawn.characters), [0, *sorted(map(ord, "Жукü"))])
        whole = decode_font(encode_font("Whole", "utf-8", 24, 0,
                                        draw_font(self.noto, 24, "utf-8", characters=held)))
        self.assertEqual(font_sample(drawn, text, "utf-8", WHITE),
                         font_sample(whole, text, "utf-8", WHITE))

    def test_a_font_in_utf8_of_some_characters(self):
        # Those of the text it does not hold are drawn as the screen draws
        # them: the font's first character, the space, which its table of
        # chosen characters holds; in a full table, nothing, half the height
        # wide.
        drawn = sample_font(self.noto, 24, "utf-8", True, "Жук", characters=[0x416, 0x41])
        self.assertEqual(sorted(drawn.characters), [0x20, 0x416])
        self.assertEqual(read_picture(font_sample(drawn, "Жук", "utf-8", WHITE)).width,
                         drawn.characters[0x416].advance + 2 * drawn.characters[0x20].advance)
        self.assertEqual(sample_note(drawn, "Жук", "utf-8"),
                         "font sample lacks U+0443 and U+043A; the screen draws its first "
                         "character, the space, in their place")
        full = sample_font(self.noto, 24, "utf-8", True, "Жук", characters=[0x416, 0x41],
                           full_table=True)
        self.assertEqual(sorted(full.characters), [0x416])
        self.assertEqual(read_picture(font_sample(full, "Жук", "utf-8", WHITE)).width,
                         full.characters[0x416].advance + 2 * 12)
        with self.assertRaisesRegex(NxwrightError, "the font would contain none of the sample's "
                                                   "characters"):
            sample_font(self.noto, 24, "utf-8", True, "Жук", characters=range(0x100))

    def test_a_character_the_font_lacks(self):
        # An ascii font lacks é: drawn as its first character, the space, as
        # the screen draws it, and named.
        ascii_font = decode_font(encode_font("Small", "ascii", 16, 0,
                                             draw_font(self.noto, 16, "ascii")))
        self.assertEqual(font_sample(ascii_font, "aéb", "iso-8859-1", WHITE),
                         font_sample(ascii_font, "a b", "iso-8859-1", WHITE))
        self.assertEqual(sample_note(ascii_font, "aéb", "iso-8859-1"),
                         "font Small lacks character 233; the screen draws its first character, "
                         "the space, in its place")
        self.assertIsNone(sample_note(ascii_font, "a b", "iso-8859-1"))

    def test_a_character_the_typeface_lacks(self):
        # Noto Sans lacks koi8-r's box-drawing characters, so the font will
        # too: the sample draws one as the screen will, the space, and its
        # note says so.
        drawn = sample_font(self.noto, 24, "koi8-r", True, "Жук─")
        self.assertNotIn(0x80, drawn.characters)
        self.assertEqual(font_sample(drawn, "Жук─", "koi8-r", WHITE),
                         font_sample(drawn, "Жук ", "koi8-r", WHITE))
        self.assertEqual(sample_note(drawn, "Жук─", "koi8-r"),
                         "font sample lacks character 128; the screen draws its first "
                         "character, the space, in its place")

    def test_no_sample(self):
        for call, error, pattern in (
                (lambda: font_sample(self.sans20, "", "iso-8859-1", WHITE), NxwrightError,
                 "the sample has no text"),
                (lambda: font_sample(self.sans20, "\n", "iso-8859-1", WHITE), NxwrightError,
                 "the sample has no text"),
                (lambda: font_sample(self.sans20, "温度", "iso-8859-1", WHITE), MissingCharacter,
                 "holds a character iso-8859-1 cannot write"),
                (lambda: sample_font(self.noto, 24, "iso-8859-1", True, ""), NxwrightError,
                 "the sample has no text"),
                (lambda: sample_font(self.noto, 24, "iso-8859-1", True, "温"), NxwrightError,
                 "iso-8859-1 cannot store '温'"),
                (lambda: sample_font(self.noto, 300, "iso-8859-1", True, "a"), NxwrightError,
                 "height 300 is not from 12 to 254"),
                (lambda: sample_font(self.noto, 24, "utf-8", True, "א",
                                     [0x5d0]), NxwrightError,
                 "the typeface file has none of the characters asked for")):
            with self.subTest(pattern=pattern), self.assertRaisesRegex(error, pattern):
                call()


if __name__ == "__main__":
    unittest.main()
