"""Decoding font blocks (.zi): the demo's fonts, and fonts the tests build;
and writing them, checked against the fonts the Editor wrote."""
from dataclasses import replace
from functools import cache
import gzip
from pathlib import Path
import struct
import unittest

from nxwright import NxwrightError
from nxwright.project.zi_font import (HEADER_SIZE, FontFacts, Glyph, converted_font,
                                      decode_font, decodes, encode_font, font_facts,
                                      grid_table_codes, turned_font)

FONTS = Path(__file__).resolve().parent / "fixtures" / "fonts"


def font_block(characters: list, height: int, orientation: int = 0x0a, encoding: int = 3,
               version: int = 6, name: str = "Test") -> bytes:
    """Builds a font block as the Editor lays one out (zi_font.py), from
    `characters`, [(code, advance, left overhang, right overhang, glyph bytes)]."""
    description = (name + "iso-8859-1").encode("latin-1")
    table = bytearray()
    glyphs = bytearray()
    for code, advance, left, right, glyph in characters:
        place = len(characters) * 10 + len(glyphs)
        table += struct.pack("<HBBBHBH", code, advance, left, right, place & 0xffff,
                             place >> 16, len(glyph))
        glyphs += glyph
    header = bytearray(HEADER_SIZE)
    header[0], header[3], header[4] = 4, orientation, encoding
    header[7], header[16] = height, version
    header[17], header[32] = len(description), len(name)
    struct.pack_into("<I", header, 12, len(characters))
    struct.pack_into("<I", header, 36, len(characters))
    body = description + table + glyphs
    struct.pack_into("<I", header, 20, len(body))
    return bytes(header + body)


def utf8_font(orientation: int = 0x0a) -> bytes:
    """Builds a utf-8 font, 1 pixel high, as docs/format.md lays out the one
    the Editor's generator made: a 10-byte entry for every code point to
    U+FFFF, of which only "A" is chosen, with a glyph of one full pixel; that
    glyph on a multiple of 8 bytes from the table's start, its place counted
    in units of 8 bytes."""
    name = b"Wide"
    description = name + b"utf-8"
    table = bytearray()
    for code_point in range(0x10000):
        if code_point == 0x41:
            units = 0x10000 * 10 // 8
            table += struct.pack("<HBBBHBH", 0x41, 1, 0, 0, units & 0xffff, units >> 16, 2)
        else:
            table += struct.pack("<HBBBHBH", 0, 10, 0, 0, 0, 0, 0)
    body = description + table + bytes([3, 0b00100001])
    header = bytearray(HEADER_SIZE)
    header[0:5] = bytes([4, 0xff, 0, orientation, 24])
    header[5], header[7], header[8:12] = 1, 1, bytes([0xff, 0xff, 0, 0xff])
    struct.pack_into("<I", header, 12, 0x10000)
    header[16], header[17] = 6, len(description)
    struct.pack_into("<I", header, 20, len(body))
    struct.pack_into("<I", header, 24, HEADER_SIZE)
    header[28:34] = bytes([0xff, 0, 1, 1, len(name), 1])
    struct.pack_into("<I", header, 36, 1)
    return bytes(header) + body


def grid_glyphs(encoding: str, height: int) -> list:
    """Glyphs for every entry of a two-byte font's table, in its order
    (zi_font.grid_table_codes): two pixels wide, or one for an ascii
    character, each with a pattern of its own place for its coverages, so
    that a test tells them apart."""
    glyphs = []
    for index, code in enumerate(grid_table_codes(encoding)):
        width = 1 if code < 0x80 else 2
        glyphs.append(Glyph(code, width, 0, 0,
                            tuple((index + pixel) % 8 for pixel in range(width * height))))
    return glyphs


@cache
def grid_font(encoding: str, height: int = 2, name: str = "Grid") -> bytes:
    """A two-byte font laid out as the Nextion Editor's, of grid_glyphs,
    upright: the Editor's own are the vendor's, and are not kept here."""
    return encode_font(name, encoding, height, 0, grid_glyphs(encoding, height))


def gb2312_glyphs(height: int) -> list:
    """grid_glyphs of a gb2312 font."""
    return grid_glyphs("gb2312", height)


def gb2312_font(height: int = 2) -> bytes:
    """grid_font of gb2312, named Zh."""
    return grid_font("gb2312", height, "Zh")


def pairs_glyph(coverages: list) -> bytes:
    """Codes coverages as an eight-level glyph, two pixels per byte (11cccddd),
    the last alone (10000ccc) when there is an odd one out."""
    glyph = bytearray([3])
    for index in range(0, len(coverages) - 1, 2):
        glyph.append(0xc0 | coverages[index] << 3 | coverages[index + 1])
    if len(coverages) % 2:
        glyph.append(0x80 | coverages[-1])
    return bytes(glyph)


class DemoFontTest(unittest.TestCase):

    def test_every_glyph_decodes_to_its_rectangle(self):
        for path in sorted(FONTS.glob("*.zi")):
            font = decode_font(path.read_bytes())
            self.assertEqual((font.encoding, font.rotation, len(font.characters)),
                             ("iso-8859-1", 0, 224))
            for character in font.characters.values():
                with self.subTest(font=path.name, code=character.code):
                    self.assertEqual(len(character.coverages()), character.width * font.height)

    def test_a_glyph_written_out(self):
        font = decode_font((FONTS / "Sans20.zi").read_bytes())
        self.assertEqual((font.name, font.height), ("Sans20", 20))
        mark = font.characters[ord("!")]
        self.assertEqual((mark.advance, mark.left, mark.right), (4, 0, 0))
        rows = ["0000"] * 5 + ["0530"] * 5 + ["0420", "0310", "0310", "0630", "0630"] + ["0000"] * 5
        self.assertEqual(mark.coverages(), [int(digit) for row in rows for digit in row])
        stop = font.characters[ord(".")]
        rows = ["0000"] * 13 + ["0770"] * 2 + ["0000"] * 5
        self.assertEqual(stop.coverages(), [int(digit) for row in rows for digit in row])

    def test_overhangs(self):
        characters = decode_font((FONTS / "Sans100.zi").read_bytes()).characters
        self.assertEqual((characters[ord("J")].left, characters[ord("f")].right), (6, 3))

    def test_a_font_turned_by_180_decodes_upright(self):
        upright = decode_font((FONTS / "Sans20.zi").read_bytes())
        turned = decode_font(font_block(
            [(code, character.advance, character.left, character.right,
              pairs_glyph(character.coverages()[::-1]))
             for code, character in sorted(upright.characters.items())],
            upright.height, orientation=0x0c))
        self.assertEqual(turned.rotation, 180)
        for code, character in upright.characters.items():
            self.assertEqual(turned.characters[code].coverages(), character.coverages(), code)


    def test_the_editors_turned_fonts_decode_upright(self):
        # Sans20 as the Editor stored it in copies of the demo's project
        # turned to each rotation.
        upright = decode_font((FONTS / "Sans20.zi").read_bytes())
        for rotation in (90, 180, 270):
            turned = decode_font((FONTS / "turned" / ("Sans20-%d.zi" % rotation)).read_bytes())
            self.assertEqual((turned.rotation, turned.height, len(turned.characters)),
                             (rotation, upright.height, len(upright.characters)))
            for code, character in upright.characters.items():
                with self.subTest(rotation=rotation, code=code):
                    stored = turned.characters[code]
                    self.assertEqual((stored.advance, stored.left, stored.right, stored.coverages()),
                                     (character.advance, character.left, character.right,
                                      character.coverages()))


def utf8_fixture(name: str) -> bytes:
    """A utf-8 font of fixtures/fonts/utf-8, kept compressed: its table alone
    is 655,360 bytes."""
    return gzip.decompress((FONTS / "utf-8" / (name + ".zi.gz")).read_bytes())


class Utf8FontTest(unittest.TestCase):
    """Fonts in utf-8 the Editor's generator made of Noto Sans, 20 pixels
    high: NotoSans20, of U+0000 to U+00FF; NotoSans20-cyrillic, of U+0000 to
    U+007F and U+0400 to U+04FF; and NotoSans20-90, NotoSans20 as the Editor
    stored it in a project at 90 degrees."""

    def test_the_chosen_characters(self):
        for name, stored, codes in (
                ("NotoSans20", "NotoSans20", set(range(0x100))),
                ("NotoSans20-cyrillic", "Noto20Cyr", set(range(0x80)) | set(range(0x400, 0x500)))):
            font = decode_font(utf8_fixture(name))
            self.assertEqual((font.name, font.encoding, font.height, font.rotation),
                             (stored, "utf-8", 20, 0))
            self.assertEqual(set(font.characters), codes)
            for character in font.characters.values():
                with self.subTest(font=name, code=character.code):
                    self.assertEqual(len(character.coverages()), character.width * font.height)

    def test_the_editors_turned_font_decodes_upright(self):
        # The Editor stored U+0000's glyph, 1 by 20 pixels, as 25 empty
        # pixels: it is read as the empty glyph it is upright.
        upright = decode_font(utf8_fixture("NotoSans20"))
        turned = decode_font(utf8_fixture("NotoSans20-90"))
        self.assertEqual((turned.rotation, set(turned.characters)), (90, set(upright.characters)))
        for code, character in upright.characters.items():
            with self.subTest(code=code):
                stored = turned.characters[code]
                self.assertEqual((stored.advance, stored.left, stored.right, stored.coverages()),
                                 (character.advance, character.left, character.right,
                                  character.coverages()))

    def test_a_texts_characters_are_its_code_points(self):
        font = decode_font(utf8_fixture("NotoSans20-cyrillic"))
        # α is not chosen, and U+1F600 lies past the table: the Editor's
        # simulator drew each as nothing, half the height wide.
        drawn = font.characters_of("Бα😀".encode("utf-8"))
        self.assertIs(drawn[0], font.characters[0x411])
        for blank in drawn[1:]:
            self.assertEqual((blank.advance, blank.left, blank.right, blank.coverages()),
                             (10, 0, 0, [0] * 200))
        with self.assertRaisesRegex(NxwrightError, "not utf-8"):
            font.characters_of("é".encode("iso-8859-1"))

    def test_a_one_byte_fonts_characters_are_its_bytes(self):
        # A byte the font lacks, as 01, is drawn as its table's first
        # character, the space, as the Editor's simulator drew one.
        font = decode_font((FONTS / "Sans20.zi").read_bytes())
        self.assertEqual(font.characters_of(b"A\xe9\x01"),
                         [font.characters[0x41], font.characters[0xe9], font.characters[0x20]])
        self.assertEqual(font.lacking(b"A\x01\xe9\x01\t"), [0x01, 0x09])

    def test_the_layout_docs_format_gives(self):
        font = decode_font(utf8_font())
        self.assertEqual((set(font.characters), font.characters[0x41].coverages()), ({0x41}, [7]))


CHOSEN_CHARACTERS = FONTS / "chosen-characters"


def chosen_characters_fixture(name: str) -> bytes:
    """A font of fixtures/fonts/chosen-characters (ChosenCharactersTest)."""
    return (CHOSEN_CHARACTERS / (name + ".zi")).read_bytes()


class ChosenCharactersTest(unittest.TestCase):
    """Fonts whose table holds only their chosen characters, as the Editor's
    font generator writes them for its Range choices "Specified character"
    and "ASCII Character", each beside the Editor's copy of it turned to 90
    degrees. In utf-8: NotoSans16-specified, of " 0AzéΩ€"; NotoSans16-ascii,
    of U+0020 to U+007E; and NotoSans32-u0001, of U+0001, which the
    generator draws as the missing-character box, the space, and "A". In
    iso-8859-1: NotoSans16-latin1-specified, of " 0Azé"."""
    CODES = {"NotoSans16-specified": [0x20, 0x30, 0x41, 0x7a, 0xe9, 0x3a9, 0x20ac],
             "NotoSans16-ascii": list(range(0x20, 0x7f)),
             "NotoSans32-u0001": [0x01, 0x20, 0x41],
             "NotoSans16-latin1-specified": [0x20, 0x30, 0x41, 0x7a, 0xe9]}

    def test_their_characters(self):
        for name, codes in self.CODES.items():
            for suffix, rotation in (("", 0), ("-90", 90)):
                with self.subTest(font=name + suffix):
                    font = decode_font(chosen_characters_fixture(name + suffix))
                    self.assertEqual((sorted(font.characters), font.rotation), (codes, rotation))
                    for character in font.characters.values():
                        character.coverages()
        letter = decode_font(chosen_characters_fixture("NotoSans16-specified")).characters[0x41]
        self.assertEqual((letter.advance, letter.left, letter.right), (8, 0, 0))

    def test_turned_as_the_editor_turns_them(self):
        for name in self.CODES:
            with self.subTest(font=name):
                upright = chosen_characters_fixture(name)
                turned = chosen_characters_fixture(name + "-90")
                self.assertEqual(turned_font(upright, 90), turned)
                self.assertEqual(turned_font(turned, 0), upright)
                self.assertEqual(turned_font(upright, 0), upright)

    def test_a_lacking_character_is_drawn_as_the_first(self):
        # The Editor's simulator drew "q", and U+1F600 past the table's end,
        # as the table's first character, here U+0001's box.
        font = decode_font(chosen_characters_fixture("NotoSans32-u0001"))
        first, letter = font.characters[0x01], font.characters[0x41]
        self.assertEqual(font.characters_of("Aq😀A".encode("utf-8")),
                         [letter, first, first, letter])

    def test_written_as_the_generator_writes_them(self):
        # Of "Specified character", in utf-8 and in iso-8859-1, whose table
        # leaves gaps: byte 5 at 2, and bytes 10 and 11 the encoding's range.
        for name in ("NotoSans16-specified", "NotoSans32-u0001", "NotoSans16-latin1-specified"):
            with self.subTest(font=name):
                block = chosen_characters_fixture(name)
                font = decode_font(block)
                self.assertEqual(encode_font(font.name, font.encoding, font.height, 0,
                                             glyphs_of(font), font.smoothed), block)
        # A one-byte font without a gap keeps its bytes: byte 5 at 1, and
        # bytes 10 and 11 its first and last character.
        whole = encode_font("Whole", "iso-8859-1", 1, 0,
                            [Glyph(code, 1, 0, 0, (7,)) for code in (0x41, 0x42)])
        self.assertEqual((whole[5], whole[10], whole[11]), (1, 0x41, 0x42))
        gapped = encode_font("Gapped", "ascii", 1, 0,
                             [Glyph(code, 1, 0, 0, (7,)) for code in (0x20, 0x41)])
        self.assertEqual((gapped[5], gapped[10], gapped[11]), (2, 0x20, 0x7e))
        self.assertEqual(sorted(decode_font(gapped).characters), [0x20, 0x41])

    def test_places_in_units_of_8_turned(self):
        # A utf-8 table of chosen characters whose glyph places count in
        # units of 8 bytes (byte 33 at 1), which no font seen used: its
        # glyph, one full pixel, at byte 16 of the table, place 2. Turned,
        # its places are written in bytes, and byte 33 says so.
        description, glyph = b"Testutf-8", bytes([3, 0b00100001])
        body = (description + struct.pack("<HBBBHBH", 0x41, 1, 0, 0, 2, 0, len(glyph))
                + bytes(6) + glyph)
        header = bytearray(HEADER_SIZE)
        header[0], header[3], header[4], header[7], header[16] = 4, 0x0a, 24, 1, 6
        header[17], header[32], header[33] = len(description), 4, 1
        for offset, value in ((12, 1), (20, len(body)), (36, 1)):
            struct.pack_into("<I", header, offset, value)
        turned = turned_font(bytes(header) + body, 90)
        self.assertEqual(turned[33], 0)
        self.assertEqual(decode_font(turned).characters[0x41].coverages(), [7])


class GlyphCodeTest(unittest.TestCase):

    def coverages(self, glyph: bytes, width: int, height: int = 1) -> list:
        font = decode_font(font_block([(65, width, 0, 0, glyph)], height))
        return font.characters[65].coverages()

    def test_eight_level_codes(self):
        cases = [(0b00000011, [0, 0, 0]), (0b00100010, [7, 7]), (0b01000010, [0, 0, 7]),
                 (0b01100001, [0, 7, 7]), (0b10010101, [0, 0, 5]), (0b11011001, [3, 1])]
        for code, expected in cases:
            with self.subTest(code=bin(code)):
                self.assertEqual(self.coverages(bytes([3, code]), len(expected)), expected)

    def test_two_level_codes(self):
        cases = [(0b00000010, [0, 0]), (0b00100010, [7, 7]), (0b01000001, [0, 7]),
                 (0b01100001, [0, 7, 7]), (0b10000001, [0, 7, 7, 7]),
                 (0b10100001, [0, 7, 7, 7, 7]), (0b11010010, [0, 0, 7, 7])]
        for code, expected in cases:
            with self.subTest(code=bin(code)):
                self.assertEqual(self.coverages(bytes([1, code]), len(expected)), expected)

    def test_an_empty_glyph(self):
        # As a gb2312 font's empty positions are, at any size and rotation:
        # two levels, runs of 31 empty pixels, then the rest.
        for width, height in ((1, 1), (30, 1), (31, 1), (32, 1), (31, 2), (16, 16), (100, 100)):
            count = width * height
            expected = bytes([1] + [31] * ((count - 1) // 31) + [count - 31 * ((count - 1) // 31)])
            for rotation in (0, 90):
                with self.subTest(width=width, height=height, rotation=rotation):
                    block = encode_font("A", "iso-8859-1", height, rotation,
                                        [Glyph(65, width, 0, 0, (0,) * count)])
                    self.assertEqual(table_entries(block)[0][4], expected)

    def test_a_run_goes_on_into_the_next_row(self):
        self.assertEqual(self.coverages(bytes([3, 0b00100011, 0b00000001]), 2, 2), [7, 7, 7, 0])


class RefusalTest(unittest.TestCase):

    def refuses(self, block: bytes, pattern: str):
        with self.assertRaisesRegex(NxwrightError, pattern):
            for character in decode_font(block).characters.values():
                character.coverages()

    def test_refusals(self):
        glyph = [(65, 1, 0, 0, bytes([3, 0b00100001]))]
        self.refuses(b"\x04" * 10, "shorter than its 44-byte header")
        self.refuses(font_block(glyph, 1, version=5), "version 5")
        self.refuses(font_block(glyph, 1, encoding=16), "big5")
        # A utf-8 table of chosen characters, which the screen searches by code.
        self.refuses(font_block(glyph + [(64, 1, 0, 0, bytes([3, 0b00100001]))], 1, encoding=24),
                     "the font's table lists U\\+0040 after U\\+0041")
        self.refuses(font_block(glyph, 1, encoding=99), "encoding 99 is not known")
        self.refuses(font_block(glyph, 1, orientation=0x0e), "orientation 0x0e")
        self.refuses(font_block(glyph, 1)[:-1], "runs past the font's end")
        self.refuses(font_block([(65, 1, 0, 0, bytes([2, 1]))], 1), "starts with 2")
        self.refuses(font_block([(65, 2, 0, 0, bytes([3, 0b00100001]))], 1),
                     "decodes to 1 pixels, where its 2 by 1 glyph holds 2")
        block = bytearray(font_block(glyph, 1))
        struct.pack_into("<I", block, 36, 1000)
        self.refuses(bytes(block), "character table runs past its end")


class FactsTest(unittest.TestCase):
    """What a font's header says, read without decoding the font."""

    def test_the_editors_fonts(self):
        self.assertEqual(font_facts((FONTS / "NotoSans20-unsmoothed.zi").read_bytes()),
                         FontFacts("NotoSans20", "iso-8859-1", 0, 20, False, 224))
        self.assertEqual(font_facts((FONTS / "turned" / "Sans20-90.zi").read_bytes()),
                         FontFacts("Sans20", "iso-8859-1", 90, 20, True, 224))

    def test_a_font_that_does_not_decode(self):
        self.assertEqual(font_facts(utf8_font(0x0b)), FontFacts("Wide", "utf-8", 90, 1, True, 1))
        # A font of one character marked as in big5: its facts read, but not
        # its layout, which is no grid of every position.
        block = font_block([(65, 1, 0, 0, bytes([3, 0b00100001]))], 1, encoding=16)
        self.assertEqual(font_facts(block), FontFacts("Test", "big5", 0, 1, False, 1))
        with self.assertRaisesRegex(NxwrightError,
                                    "a font in big5 of byte 5 at 0 has not been seen"):
            decode_font(block)

    def test_the_kinds_of_font_decoded(self):
        glyph = [(65, 1, 0, 0, bytes([3, 0b00100001]))]
        for block, decoded in (((FONTS / "Sans20.zi").read_bytes(), True),
                               (font_block(glyph, 1)[:-1], True),
                               (utf8_font(), True),
                               (font_block(glyph, 1, encoding=16), False),
                               (gb2312_font(), True),
                               (font_block(glyph, 1, version=5), False),
                               (font_block(glyph, 1, orientation=0x0e), False),
                               (bytes(10), False)):
            with self.subTest(length=len(block)):
                self.assertEqual(decodes(block), decoded)

    def test_a_name_beyond_ascii(self):
        # The Nextion Editor stores a font's name in utf-8, whatever the
        # font's encoding (worked out from fonts it made).
        glyph = [Glyph(65, 1, 0, 0, (7,))]
        for name, encoding in (("Café", "iso-8859-1"), ("16中文", "iso-8859-1"),
                               ("Café", "utf-8")):
            with self.subTest(name=name, encoding=encoding):
                block = encode_font(name, encoding, 1, 0, glyph)
                self.assertEqual(block[HEADER_SIZE:HEADER_SIZE + block[32]], name.encode("utf-8"))
                self.assertEqual(font_facts(block).name, name)

    def test_a_name_written_in_latin_1_before(self):
        # nxwright wrote a name beyond ascii in latin-1 before: one that is no
        # utf-8 still reads as it was written.
        block = font_block([(65, 1, 0, 0, bytes([3, 0b00100001]))], 1, name="Café")
        self.assertEqual(font_facts(block).name, "Café")

    def test_refusals(self):
        glyph = [(65, 1, 0, 0, bytes([3, 0b00100001]))]
        for block, pattern in ((bytes([4]) * 10, "shorter than its 44-byte header"),
                               (font_block(glyph, 1, encoding=99), "encoding 99 is not known"),
                               (font_block(glyph, 1, orientation=0x0e), "orientation 0x0e")):
            with self.subTest(pattern=pattern), self.assertRaisesRegex(NxwrightError, pattern):
                font_facts(block)


def glyphs_of(font) -> list:
    """Returns a decoded font's characters as the Glyphs that write it."""
    return [Glyph(character.code, character.advance, character.left, character.right,
                  tuple(character.coverages()))
            for character in font.characters.values()]


def table_entries(block: bytes) -> list:
    """Returns (code, advance, left, right, glyph bytes) of each entry of a
    font block's character table."""
    table = HEADER_SIZE + block[17]
    count, = struct.unpack_from("<I", block, 36)
    entries = []
    for index in range(count):
        code, advance, left, right, low, high, length = struct.unpack_from(
            "<HBBBHBH", block, table + index * 10)
        start = table + (low | high << 16)
        entries.append((code, advance, left, right, block[start:start + length]))
    return entries


class WriteTest(unittest.TestCase):
    """The Editor's own fonts written again: Sans16, Sans20, and Sans100 at
    rotation 0, from themselves, and Sans20 at 90, 180, and 270, from the
    upright Sans20, as the Editor turned it in copies of the demo's project;
    and NotoSans20-unsmoothed, which its generator made from Noto Sans with
    "Anti-aliasing of fonts" left unticked."""

    CASES = [("Sans12.zi", "Sans12.zi", 0, True),
             ("Sans16.zi", "Sans16.zi", 0, True), ("Sans20.zi", "Sans20.zi", 0, True),
             ("Sans100.zi", "Sans100.zi", 0, True),
             ("Sans20.zi", "turned/Sans20-90.zi", 90, True),
             ("Sans20.zi", "turned/Sans20-180.zi", 180, True),
             ("Sans20.zi", "turned/Sans20-270.zi", 270, True),
             ("NotoSans20-unsmoothed.zi", "NotoSans20-unsmoothed.zi", 0, False)]

    def test_the_editors_fonts_written_again(self):
        for source, expected, rotation, smoothed in self.CASES:
            with self.subTest(font=expected):
                upright = decode_font((FONTS / source).read_bytes())
                editors = (FONTS / expected).read_bytes()
                written = encode_font(upright.name, upright.encoding, upright.height, rotation,
                                      glyphs_of(upright), smoothed=smoothed)
                # Glyph by glyph first, to name the first that differs; then the whole file.
                for mine, theirs in zip(table_entries(written), table_entries(editors),
                                        strict=True):
                    self.assertEqual(mine, theirs, "character %d" % mine[0])
                self.assertEqual(written, editors)

    def test_a_font_turned_as_the_editor_turns_it(self):
        upright = (FONTS / "Sans20.zi").read_bytes()
        for rotation in (90, 180, 270):
            with self.subTest(rotation=rotation):
                self.assertEqual(turned_font(upright, rotation),
                                 (FONTS / "turned" / ("Sans20-%d.zi" % rotation)).read_bytes())
        # Its smoothing is kept: the generator's unsmoothed font, turned and back.
        unsmoothed = (FONTS / "NotoSans20-unsmoothed.zi").read_bytes()
        self.assertEqual(turned_font(turned_font(unsmoothed, 90), 0), unsmoothed)

    def test_a_partial_pixel_after_empty_ones(self):
        # Coded with the empty pixels before it, unless the next pixel has the
        # same coverage: then the empty pixels go alone, and the two in a pair.
        for coverages, codes in (((0, 3, 4), [3, 0x8b, 0x84]), ((0, 3, 3), [3, 0x01, 0xdb])):
            with self.subTest(coverages=coverages):
                block = encode_font("A", "iso-8859-1", 1, 0, [Glyph(65, 3, 0, 0, coverages)])
                self.assertEqual(table_entries(block)[0][4], bytes(codes))

    def test_a_font_of_95_characters(self):
        # As the docs record of the Editor's ascii fonts: two zero bytes after
        # the character table, before the first glyph.
        glyphs = [Glyph(code, 1, 0, 0, (7,)) for code in range(0x20, 0x7f)]
        block = encode_font("A", "ascii", 1, 0, glyphs)
        table = HEADER_SIZE + block[17]
        self.assertEqual(block[table + 95 * 10:table + 95 * 10 + 2], bytes(2))
        self.assertEqual(table_entries(block)[0][4], bytes([1, 0x21]))
        self.assertEqual(sorted(decode_font(block).characters), list(range(0x20, 0x7f)))

    def test_refusals(self):
        glyph = Glyph(65, 1, 0, 0, (7,))
        for arguments, pattern in (
                (("A", "big5", 1, 0, [glyph]), "big5"),
                (("A", "iso-8859-1", 1, 45, [glyph]), "rotation 45"),
                (("A", "iso-8859-1", 1, 0, [Glyph(65, 2, 0, 0, (7,))]),
                 "character 65 has 1 coverages, where its 2 by 1 glyph holds 2"),
                (("A", "iso-8859-1", 1, 0, [Glyph(65, 1, 0, 0, (8,))]),
                 "character 65 has a coverage of 8"),
                (("A", "iso-8859-1", 1, 0, [glyph, glyph]), "by increasing code"),
                (("A", "iso-8859-1", 0, 0, [Glyph(65, 1, 0, 0, ())]), "height 0 is not from 1 to 255"),
                (("A", "iso-8859-1", 1, 0, [Glyph(300, 1, 0, 0, (7,))]),
                 "character 300: a font in iso-8859-1 has codes from 0 to 255"),
                (("A", "utf-8", 1, 0, [Glyph(0x10000, 1, 0, 0, (7,))]),
                 "character 65536: a font in utf-8 has codes from 0 to 65535"),
                (("A", "iso-8859-1", 1, 0, [Glyph(65, 256, 0, 0, (7,) * 256)]),
                 "character 65: its advance and overhangs must each fit a byte"),
                # Its description is its name and its encoding's name, under 256 bytes.
                (("A" * 246, "iso-8859-1", 1, 0, [glyph]),
                 "the font's name is longer than 245 bytes"),
                # The name is written in utf-8, two bytes for each é.
                (("é" * 123, "iso-8859-1", 1, 0, [glyph]),
                 "the font's name is longer than 245 bytes"),
                # 765 by 255 partly covered pixels code in pairs to more bytes
                # than a glyph's two-byte length holds.
                (("A", "iso-8859-1", 255, 0, [Glyph(65, 255, 255, 255, (3,) * 765 * 255)]),
                 "character 65's glyph is longer than its table entry holds"),
                (("A", "iso-8859-1", 1, 0, [Glyph(65, 2, 0, 0, (7, 3))], False),
                 "character 65 has partly covered pixels, in a font that is not smoothed")):
            with self.subTest(pattern=pattern), self.assertRaisesRegex(NxwrightError, pattern):
                encode_font(*arguments)


class Utf8WriteTest(unittest.TestCase):
    """Fonts in utf-8 written again: the generator's, upright, from their
    own glyphs; and the Editor's turned ones, from the upright fonts:
    NotoSans20 at 90, and NotoSans17 at 180 and 270. Their codes not chosen
    take half the height, rounded down, as their advance: 10 and 8."""

    CASES = [("NotoSans20", "NotoSans20", 0), ("NotoSans20-cyrillic", "NotoSans20-cyrillic", 0),
             ("NotoSans17", "NotoSans17", 0), ("NotoSans20-hebrew", "NotoSans20-hebrew", 0),
             ("NotoSans20", "NotoSans20-90", 90), ("NotoSans17", "NotoSans17-180", 180),
             ("NotoSans17", "NotoSans17-270", 270)]

    def assert_same_bytes(self, written: bytes, editors: bytes):
        # A font is 655 KB: the first byte that differs says more than a diff.
        first = next((place for place, (mine, theirs) in enumerate(zip(written, editors))
                      if mine != theirs), None)
        self.assertEqual((first, len(written)), (None, len(editors)))

    def test_the_editors_fonts_written_again(self):
        # As full tables, which these are.
        for source, expected, rotation in self.CASES:
            with self.subTest(font=expected):
                upright = decode_font(utf8_fixture(source))
                self.assert_same_bytes(encode_font(upright.name, "utf-8", upright.height,
                                                   rotation, glyphs_of(upright), full_table=True),
                                       utf8_fixture(expected))

    def test_turned_as_the_editor_turns_them(self):
        # Turned, U+0000 has no glyph of its own: its entry gives U+0001's
        # place. Turned back upright, it has its own again.
        self.assert_same_bytes(turned_font(utf8_fixture("NotoSans17"), 180),
                               utf8_fixture("NotoSans17-180"))
        self.assert_same_bytes(turned_font(utf8_fixture("NotoSans20-90"), 0),
                               utf8_fixture("NotoSans20"))


class Gb2312FontTest(unittest.TestCase):
    """Fonts in gb2312, laid out as the font of the Nextion Editor's Chinese
    input keyboard (docs/format.md, Two-byte fonts): an entry for every
    position of the two bytes' grid, row by row, then the ascii characters."""

    @classmethod
    def setUpClass(cls):
        cls.block = gb2312_font()
        cls.font = decode_font(cls.block)

    def entry_code(self, index: int) -> bytes:
        """The code of the table's entry `index`, as stored."""
        start = HEADER_SIZE + self.block[17] + index * 10
        return self.block[start:start + 2]

    def test_its_header(self):
        block = self.block
        self.assertEqual(block[0:5], bytes([4, 0xff, 0, 0x0a, 2]))
        self.assertEqual((block[5], block[7], block[8:12]),
                         (1, 2, bytes([0xa1, 0xf7, 0xa1, 0xfe])))
        # 87 rows of 94 positions, and the 95 ascii characters.
        self.assertEqual((struct.unpack_from("<I", block, 12)[0],
                          struct.unpack_from("<I", block, 36)[0]), (8273, 8273))
        self.assertEqual((block[16], block[28:32], block[33]), (6, bytes([0xff, 0, 1, 1]), 0))

    def test_its_table(self):
        # Each code is the character's two bytes, the first stored first.
        self.assertEqual([self.entry_code(index) for index in (0, 1, 93, 94, 8177, 8178, 8272)],
                         [b"\xa1\xa1", b"\xa1\xa2", b"\xa1\xfe", b"\xa2\xa1", b"\xf7\xfe",
                          b" \x00", b"~\x00"])
        self.assertEqual(glyphs_of(self.font), gb2312_glyphs(2))

    def test_a_texts_characters(self):
        def codes(data: bytes) -> list:
            return [character.code for character in self.font.characters_of(data)]
        # A byte below 80 is a character of its own; one from 80, the first of two.
        self.assertEqual(codes("中a".encode("gb2312")), [0xd0d6, 0x61])
        # A pair outside the grid is the entry its place falls on: e9 31 the
        # 6,656th from 0; f8 a1, past the grid, the first ascii entry, the
        # space.
        table = list(self.font.characters)
        self.assertEqual(codes(b"\xe9\x31\xf8\xa1"), [table[6656], 0x20])
        # A lone first byte at the text's end draws nothing.
        self.assertEqual(codes(b"A\xe9"), [0x41])
        # A place before the table's first entry is drawn as its first
        # character, and the font lacks it.
        self.assertEqual(self.font.characters_of(b"\x81\x40"), [self.font.first_character])
        self.assertEqual(self.font.lacking(b"A\x81\x40"), [0x4081])

    def test_turned(self):
        turned = turned_font(self.block, 90)
        self.assertEqual(turned[3], 0x0b)
        self.assertEqual(turned_font(turned, 0), self.block)
        # Each glyph turned as a one-byte font's is.
        glyphs = gb2312_glyphs(2)
        for index in (0, 6656, 8272):
            with self.subTest(index=index):
                alone = encode_font("A", "iso-8859-1", 2, 90, [replace(glyphs[index], code=0x41)])
                self.assertEqual(table_entries(turned)[index][4], table_entries(alone)[0][4])

    def test_refusals(self):
        table = HEADER_SIZE + self.block[17]
        swapped = bytearray(self.block)
        swapped[table:table + 2] = self.block[table + 10:table + 12]
        swapped[table + 10:table + 12] = self.block[table:table + 2]
        other_layout = bytearray(self.block)
        other_layout[5] = 2
        # A header of another grid, even one its table would fit.
        other_grid = bytearray(self.block)
        other_grid[8:12] = bytes([0xa1, 0xa1, 0xa1, 0xa1])
        for block, pattern in ((swapped, "the table's entry 0 gives a1 a2, where a1 a1 goes"),
                               (other_layout, "a font in gb2312 of byte 5 at 2"),
                               (other_grid, "a font in gb2312 has a grid of a1 to f7 by a1 to fe, "
                                            "where this one's is a1 to a1 by a1 to a1"),
                               (font_block([(65, 1, 0, 0, bytes([3, 0b00100001]))], 1,
                                           encoding=16), "a font in big5 of byte 5 at 0")):
            with self.subTest(pattern=pattern), self.assertRaisesRegex(NxwrightError, pattern):
                decode_font(bytes(block))
        with self.assertRaisesRegex(NxwrightError, "a font in gb2312 holds a glyph for every "
                                                   "position of its grid"):
            encode_font("Zh", "gb2312", 2, 0, gb2312_glyphs(2)[:-1])

    def test_converted_to_another_encoding(self):
        # Each position's glyph goes to the character GBK gives it, as
        # nxwright draws one, and positions it gives none are left out,
        # unnamed: 中 is d6 d0, é a8 a6, and § a1 ec.
        zhong, e_acute, section = 0xd0d6, 0xa6a8, 0xeca1
        utf8 = decode_font(converted_font(self.block, "utf-8", 0)[0])
        self.assertEqual(len(utf8.characters), 7445 + 33 + 95)
        for code, code_point in ((zhong, 0x4e2d), (e_acute, 0xe9), (0x41, 0x41)):
            self.assertEqual(utf8.characters[code_point].coverages(),
                             self.font.characters[code].coverages())
        # In iso-8859-1, what both have is kept, and the rest named.
        block, left_out = converted_font(self.block, "iso-8859-1", 0)
        latin1 = decode_font(block)
        for code, byte in ((e_acute, 0xe9), (section, 0xa7)):
            self.assertEqual(latin1.characters[byte].coverages(),
                             self.font.characters[code].coverages())
        self.assertIn(0x4e2d, left_out)

    def test_converted_from_another_encoding(self):
        # Sans20, in iso-8859-1: its é and A go to their positions; a
        # position none of its characters has is empty, as wide as the font
        # is tall; and a character gb2312 lacks, as ÿ, is named.
        sans = decode_font((FONTS / "Sans20.zi").read_bytes())
        block, left_out = converted_font((FONTS / "Sans20.zi").read_bytes(), "gb2312", 0)
        zh = decode_font(block)
        self.assertEqual((zh.encoding, len(zh.characters)), ("gb2312", 8273))
        for code, byte in ((0xa6a8, 0xe9), (0x41, 0x41)):
            self.assertEqual(zh.characters[code].coverages(), sans.characters[byte].coverages())
        empty = zh.characters[0xd0d6]
        self.assertEqual((empty.advance, empty.left, empty.right, any(empty.coverages())),
                         (20, 0, 0, False))
        self.assertIn(0xff, left_out)


class OtherGridsTest(unittest.TestCase):
    """Fonts in big5, shift-jis, and ks_c_5601-1987, laid out as the Nextion
    Editor's font generator writes them (docs/format.md, Two-byte fonts):
    gb2312's layout, on each encoding's own grid, whose ranges may skip a
    gap."""

    # Per encoding: byte 4; bytes 8 to 11, each range's first and last
    # value; bytes 1 and 2, the second byte's gap; bytes 28 and 29, the
    # first byte's; and the table's entries.
    HEADERS = {"big5": (16, "a0 f9 40 fe", "7e 22", "ff 00", 14225),
               "shift-jis": (23, "81 ef 40 fc", "7e 01", "9f 40", 8931),
               "ks_c_5601-1987": (15, "a1 c8 a1 fe", "ff 00", "ff 00", 3855)}
    # Per encoding, (an entry's place, its code as stored).
    ENTRIES = {"big5": [(0, "a0 40"), (62, "a0 7e"), (63, "a0 a1"), (157, "a1 40"),
                        (14129, "f9 fe"), (14130, "20 00")],
               "shift-jis": [(0, "81 40"), (62, "81 7e"), (63, "81 80"), (187, "81 fc"),
                             (5828, "e0 40"), (8835, "ef fc"), (8836, "20 00")],
               "ks_c_5601-1987": [(0, "a1 a1"), (3759, "c8 fe"), (3760, "20 00")]}

    def test_their_headers(self):
        for encoding, (code, grid, second_gap, first_gap, entries) in self.HEADERS.items():
            with self.subTest(encoding=encoding):
                block = grid_font(encoding)
                self.assertEqual((block[4], block[5], block[8:12].hex(" "), block[1:3].hex(" "),
                                  block[28:30].hex(" ")), (code, 1, grid, second_gap, first_gap))
                self.assertEqual((struct.unpack_from("<I", block, 12)[0],
                                  struct.unpack_from("<I", block, 36)[0]), (entries, entries))

    def test_their_tables(self):
        for encoding, entries in self.ENTRIES.items():
            with self.subTest(encoding=encoding):
                block = grid_font(encoding)
                table = HEADER_SIZE + block[17]
                self.assertEqual([block[table + place * 10:table + place * 10 + 2].hex(" ")
                                  for place, _ in entries], [code for _, code in entries])
                self.assertEqual(glyphs_of(decode_font(block)), grid_glyphs(encoding, 2))

    def test_a_texts_characters(self):
        # The screen's place of a pair: each byte's index from its range's
        # first value, less the gap past the value before it. A place
        # outside the table draws its first character, which the font lacks.
        cases = {
            "big5": [(b"\xa4\x40", 628), (b"\xa4\x7f", 657), (b"\xa4\xa0", 690),
                     (b"\xa4\xa1", 691), (b"\xfa\x40", 14130), (b"\xfb\x40", None)],
            "shift-jis": [(b"\x81\x7f", 62), (b"\x81\x80", 63), (b"\xd5\x40", 3760),
                          (b"\xe0\x40", 5828), (b"\xb1\x41", None), (b"\xf0\x40", 8836)],
            "ks_c_5601-1987": [(b"\xb0\xa1", 1410), (b"\xca\xa1", 3854), (b"\xcb\xa1", None)]}
        for encoding, pairs in cases.items():
            font = decode_font(grid_font(encoding))
            table = list(font.characters.values())
            for data, place in pairs:
                with self.subTest(encoding=encoding, data=data.hex(" ")):
                    expected = font.first_character if place is None else table[place]
                    self.assertEqual(font.characters_of(b"A" + data), [table[-62], expected])
                    if place is None:
                        self.assertEqual(font.lacking(data), [data[0] | data[1] << 8])
            # A lone first byte at the text's end draws nothing.
            self.assertEqual(font.characters_of(b"A\xc8"), [table[-62]])

    def test_turned(self):
        for encoding in self.HEADERS:
            with self.subTest(encoding=encoding):
                block = grid_font(encoding)
                turned = turned_font(block, 90)
                self.assertEqual((turned[3], turned[1:3], turned[28:30]),
                                 (0x0b, block[1:3], block[28:30]))
                self.assertEqual(turned_font(turned, 0), block)

    def test_refusals(self):
        # A header whose gap is not its encoding's.
        no_gap = bytearray(grid_font("big5"))
        no_gap[1:3] = b"\xff\x00"
        with self.assertRaisesRegex(NxwrightError, "a font in big5 has a grid of a0 to f9 by 40 "
                                                   "to fe, skipping 34 after 7e"):
            decode_font(bytes(no_gap))

    def test_converted_between_them(self):
        # A character's glyph goes to its position in the other encoding: 中
        # is d6 d0 in gb2312, a4 a4 in big5, and 92 86 in shift-jis. The grid
        # of ks_c_5601-1987 holds no Hanja, so it is left out there, and
        # named.
        zhong = decode_font(gb2312_font()).characters[0xd0d6].coverages()
        for encoding, code in (("big5", 0xa4a4), ("shift-jis", 0x8692)):
            with self.subTest(encoding=encoding):
                made = decode_font(converted_font(gb2312_font(), encoding, 0)[0])
                self.assertEqual((made.encoding, made.characters[code].coverages()),
                                 (encoding, zhong))
        _, left_out = converted_font(gb2312_font(), "ks_c_5601-1987", 0)
        self.assertIn(0x4e2d, left_out)


if __name__ == "__main__":
    unittest.main()
