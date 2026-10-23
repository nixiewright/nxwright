"""Typeface files read and drawn through FreeType (truetype.py): the Noto
Sans that nxwright ships, the same as an OpenType file of PostScript
outlines and as a collection, and small TrueType files the tests build.

tests/fixtures/fonts/NotoSans-Latin1.otf and NotoSans-Latin1.ttc were made
from nxwright's Noto Sans with fontTools, cut down to the characters of
iso-8859-1: the first with its outlines written as PostScript (CFF) ones,
the second a collection of it and the same renamed "Noto Sans Second"."""
from dataclasses import replace
import itertools
from pathlib import Path
import struct
from types import SimpleNamespace
import unittest

import freetype

from nxwright import NxwrightError
from nxwright.project.truetype import MISSING_GLYPH, NOTO_SANS, TrueTypeFont


def simple_glyph(*contours) -> bytes:
    """A simple glyph's glyf record, each contour [(x, y, on curve)], its
    coordinates stored in two bytes each."""
    points = [point for contour in contours for point in contour]
    ends = [end - 1 for end in itertools.accumulate(len(contour) for contour in contours)]
    xs = [x for x, _, _ in points]
    ys = [y for _, y, _ in points]
    record = struct.pack(">hhhhh", len(contours), min(xs), min(ys), max(xs), max(ys))
    record += struct.pack(">%dHH" % len(ends), *ends, 0)
    record += bytes(1 if on_curve else 0 for _, _, on_curve in points)
    for values in (xs, ys):
        record += b"".join(struct.pack(">h", value - before)
                           for before, value in zip([0] + values, values))
    return record


def composite_glyph(glyph: int, dx: int, dy: int) -> bytes:
    """A composite glyph's glyf record, of one part: `glyph` moved by dx and
    dy font units, given as two signed bytes."""
    xy_values = 0x0002
    return struct.pack(">hhhhhHHbb", -1, 0, 0, 0, 0, xy_values, glyph, dx, dy)


def character_map(characters: dict) -> bytes:
    """A cmap of one Windows subtable of format 4, mapping {character:
    glyph}: a segment for each character, then the last segment, at 0xffff."""
    codes = sorted((ord(character), glyph) for character, glyph in characters.items())
    codes.append((0xffff, 0))
    segments = len(codes)
    subtable = struct.pack(">7H", 4, 16 + 8 * segments, 0, 2 * segments, 0, 0, 0)
    subtable += struct.pack(">%dH" % segments, *(code for code, _ in codes))
    subtable += struct.pack(">H", 0)
    subtable += struct.pack(">%dH" % segments, *(code for code, _ in codes))
    subtable += struct.pack(">%dH" % segments, *((glyph - code) & 0xffff for code, glyph in codes))
    subtable += bytes(2 * segments)
    return struct.pack(">HHHHI", 0, 1, 3, 1, 12) + subtable


def name_table(names: dict) -> bytes:
    """A name table of Windows' records in US English, {name number: text}."""
    records, strings = b"", b""
    for number, text in sorted(names.items()):
        encoded = text.encode("utf-16-be")
        records += struct.pack(">6H", 3, 1, 0x409, number, len(encoded), len(strings))
        strings += encoded
    return struct.pack(">HHH", 0, len(names), 6 + len(records)) + records + strings


def truetype_file(glyphs: list, characters: dict, names: dict = None) -> bytes:
    """A TrueType file of `glyphs`, glyf records, 1000 units per em, glyph n
    advancing 500 + n units, with a character map of format 4 giving
    `characters`, {character: glyph}, and with `names` a name table."""
    glyf, places = b"", [0]
    for record in glyphs:
        glyf += record + bytes(len(record) % 2)
        places.append(len(glyf))
    count = len(glyphs)
    head = bytearray(54)
    struct.pack_into(">H", head, 18, 1000)
    hhea = bytearray(36)
    struct.pack_into(">hh", hhea, 4, 800, -200)
    struct.pack_into(">H", hhea, 34, count)
    loca = struct.pack(">%dH" % (count + 1), *(place // 2 for place in places))
    tables = {"cmap": character_map(characters), "glyf": glyf, "head": bytes(head),
              "hhea": bytes(hhea), "loca": loca, "maxp": struct.pack(">IH", 0x5000, count),
              "hmtx": b"".join(struct.pack(">Hh", 500 + glyph, 0) for glyph in range(count))}
    if names is not None:
        tables["name"] = name_table(names)
    directory = bytearray(b"\x00\x01\x00\x00" + struct.pack(">HHHH", len(tables), 0, 0, 0))
    body = b""
    for tag, table in tables.items():
        directory += struct.pack(">4sIII", tag.encode(), 0,
                                 12 + 16 * len(tables) + len(body), len(table))
        body += table + bytes(-len(table) % 4)
    return bytes(directory + body)


# A square whose top-left corner is a curve.
SQUARE = [(0, 0, True), (10, 0, True), (10, 10, True), (0, 10, False)]
# Glyph 0 is the missing-character glyph, 1 the square, and 2 the square
# moved, as a composite glyph.
GLYPHS = [
    simple_glyph([(0, 0, True), (5, 0, True), (5, 5, True)]),
    simple_glyph(SQUARE),
    composite_glyph(1, 100, -40),
]


FONTS = Path(__file__).resolve().parent / "fixtures" / "fonts"


class SmallFilesTest(unittest.TestCase):

    def test_characters_and_advances(self):
        font = TrueTypeFont(truetype_file(GLYPHS, {"A": 1, "é": 2}))
        self.assertEqual((font.units_per_em, font.ascender, font.descender), (1000, 800, -200))
        self.assertEqual((font.glyph_of("A"), font.glyph_of("é"), font.glyph_of("B")),
                         (1, 2, None))
        self.assertEqual([font.advance(glyph) for glyph in (0, 1, 2)], [500, 501, 502])

    def test_the_typeface_name(self):
        for names, expected in (
                (None, ""),
                ({1: "Test Sans", 2: "Regular"}, "Test Sans"),
                ({1: "Test Sans", 2: "Bold"}, "Test Sans Bold"),
                # The typographic names come first, where a file has them.
                ({1: "Test Sans Light", 2: "Regular", 16: "Test Sans", 17: "Light"},
                 "Test Sans Light"),
                ({2: "Bold"}, "")):
            with self.subTest(names=names):
                font = TrueTypeFont(truetype_file(GLYPHS, {"A": 1}, names=names))
                self.assertEqual(font.typeface_name(), expected)

    def test_a_glyph_drawn(self):
        # Glyph 1, a square of 10 units on the baseline whose top-left corner
        # is a curve, at 0.25 pixels a unit: 2.5 pixels. Unsmoothed, each
        # pixel is full or empty, the curve leaving two empty.
        font = TrueTypeFont(truetype_file(GLYPHS, {"A": 1}))
        drawn = font.drawn(1, 0.25, False)
        self.assertEqual((drawn.left, drawn.top, drawn.width, drawn.rows, list(drawn.coverages)),
                         (0, 3, 3, 3, [0, 0, 255] + [255] * 6))
        # Glyph 2, made of glyph 1 moved by 100 and -40 units, is drawn 25
        # pixels right and 10 down.
        self.assertEqual(font.drawn(2, 0.25, False), replace(drawn, left=25, top=-7))
        # Smoothed, the edges are partly covered.
        smoothed = font.drawn(1, 0.25, True)
        self.assertTrue(any(0 < coverage < 255 for coverage in smoothed.coverages))
        self.assertEqual(max(smoothed.coverages), 255)

    def test_a_glyph_the_typeface_holds_as_a_bitmap(self):
        # A typeface may hold a glyph as a bitmap of a bit a pixel for some
        # sizes, as SimSun does for small ones, which FreeType gives even when
        # asked to smooth. It is drawn as it is, each pixel full or empty.
        font = TrueTypeFont(truetype_file(GLYPHS, {"A": 1}))
        bitmap = SimpleNamespace(pixel_mode=freetype.FT_PIXEL_MODE_MONO, width=3, rows=2,
                                 pitch=2, buffer=[0b10100000, 0, 0b01000000, 0])
        slot = SimpleNamespace(bitmap=bitmap, bitmap_left=1, bitmap_top=2,
                               render=lambda mode: None)
        font._face = SimpleNamespace(set_char_size=lambda *size: None,
                                     load_glyph=lambda glyph, flags: None, glyph=slot)
        for smoothed in (True, False):
            with self.subTest(smoothed=smoothed):
                drawn = font.drawn(1, 0.5, smoothed)
                self.assertEqual((drawn.left, drawn.top, drawn.width, drawn.rows,
                                  list(drawn.coverages)),
                                 (1, 2, 3, 2, [255, 0, 255, 0, 255, 0]))
        # One of gray levels keeps them smoothed, and is made full or empty
        # where the font is not smoothed.
        slot.bitmap = SimpleNamespace(pixel_mode=freetype.FT_PIXEL_MODE_GRAY, width=3, rows=1,
                                      pitch=4, buffer=[200, 100, 128, 0])
        self.assertEqual(list(font.drawn(1, 0.5, True).coverages), [200, 100, 128])
        self.assertEqual(list(font.drawn(1, 0.5, False).coverages), [255, 0, 255])

    def test_what_is_no_font_is_refused(self):
        file = truetype_file(GLYPHS, {"A": 1})
        for data in (b"GIF89a" + file, file[:12]):
            with self.subTest(data=data[:6]):
                with self.assertRaisesRegex(NxwrightError, "not a font FreeType reads"):
                    TrueTypeFont(data)


class NotoSansTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.font = TrueTypeFont(NOTO_SANS.read_bytes())

    def test_metrics(self):
        font = self.font
        self.assertEqual((font.units_per_em, font.ascender, font.descender), (1000, 1069, -293))
        self.assertEqual(font.typeface_name(), "Noto Sans")
        self.assertIsNone(font.glyph_of("؀"))
        self.assertTrue(any(font.drawn(MISSING_GLYPH, 0.02, True).coverages))
        # The no-break space draws nothing, with the space's advance.
        space, no_break = font.glyph_of(" "), font.glyph_of(" ")
        self.assertFalse(any(font.drawn(no_break, 0.02, True).coverages))
        self.assertEqual(font.advance(no_break), font.advance(space))


class OtherFilesTest(unittest.TestCase):
    """An OpenType file and a collection are read and drawn as the TrueType
    file they were made from."""

    def test_as_noto_sans(self):
        noto = TrueTypeFont(NOTO_SANS.read_bytes())
        for name in ("NotoSans-Latin1.otf", "NotoSans-Latin1.ttc"):
            with self.subTest(name):
                font = TrueTypeFont((FONTS / name).read_bytes())
                self.assertEqual((font.typeface_name(), font.ascender, font.descender),
                                 ("Noto Sans", 1069, -293))
                for character in "Aéÿ":
                    self.assertEqual(font.advance(font.glyph_of(character)),
                                     noto.advance(noto.glyph_of(character)))
                    self.assertTrue(any(font.drawn(font.glyph_of(character), 0.02,
                                                   True).coverages))


if __name__ == "__main__":
    unittest.main()
