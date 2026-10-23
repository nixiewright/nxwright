"""Typeface files, read and drawn through FreeType (freetype-py): TrueType
(".ttf") and OpenType (".otf") files, and collections of them (".ttc"), of
which the first typeface is read. What drawing a font from one needs
(font_drawing.py): which glyph draws each character, the glyphs' advances,
the typeface's name and metrics, and each glyph drawn at a size.

A glyph is drawn smoothed with FreeType's light hinting, which moves an
outline's horizontal edges onto whole pixels, as the Editor's fonts have
them; or unsmoothed, unhinted, in monochrome, FreeType's dropout control
keeping the parts of a glyph thinner than a pixel. font_drawing.py gives
how close each comes to the Editor's fonts.

Glyph 0 is the missing-character glyph, drawn for a character the file lacks.
"""
from dataclasses import dataclass
import functools
import io
from pathlib import Path

import freetype

from nxwright import NxwrightError

# The TrueType file nxwright ships, for its keyboards' fonts and a new
# folder's first font: Noto Sans, under the SIL Open Font License, whose text
# is beside it.
NOTO_SANS = Path(__file__).resolve().parent / "fonts" / "NotoSans-Regular.ttf"
# The suffixes of the files read here.
TYPEFACE_SUFFIXES = (".ttf", ".otf", ".ttc")
MISSING_GLYPH = 0
# The name table's names read: the typographic family and style, and the
# family and style, which a file without the first two gives alone.
_FAMILY, _STYLE, _TYPOGRAPHIC_FAMILY, _TYPOGRAPHIC_STYLE = 1, 2, 16, 17
# The name records read, by platform: Unicode's, and Windows' in Unicode.
_UNICODE, _WINDOWS = 0, 3
_WINDOWS_UNICODE_ENCODINGS = (1, 10)
_US_ENGLISH = 0x409


@dataclass(frozen=True)
class DrawnGlyph:
    """A glyph drawn at a size: `coverages`, `width` by `rows` bytes, row by
    row from the top, each from 0 to 255, its left column `left` pixels right
    of the pen, its top row `top` pixels above the baseline."""
    left: int
    top: int
    width: int
    rows: int
    coverages: bytes


class TrueTypeFont:
    """A typeface file's characters: which glyph draws each, the glyphs'
    advances in font units, and each glyph drawn at a size; and the
    typeface's `units_per_em`, and its `ascender` and `descender`, how far it
    reaches above and below the baseline in font units.

    It holds a FreeType face, which keeps the size last set and the glyph
    last drawn. So, as with any FreeType face, one thread at a time may use
    it: two drawing at once would mix their glyphs."""

    def __init__(self, data: bytes):
        """Reads the file. Raises NxwrightError for one FreeType does not
        read as a typeface whose outlines it can draw at any size."""
        try:
            self._face = freetype.Face(io.BytesIO(data))
        except freetype.FT_Exception as error:
            raise NxwrightError("the file is not a font FreeType reads: %s" % error) from None
        if not self._face.is_scalable:
            raise NxwrightError("the font file holds pictures of its glyphs at set sizes, "
                                "with no outlines to draw them at another")
        self.units_per_em = self._face.units_per_EM
        self.ascender, self.descender = self._face.ascender, self._face.descender
        self._size = None       # the size the face is set to, in 64ths of a pixel an em

    def glyph_of(self, character: str):
        """Returns the glyph that draws a character, or None when the file
        lacks it."""
        return self._face.get_char_index(ord(character)) or None

    def advance(self, glyph: int) -> int:
        """Returns how far the pen moves after a glyph, in font units."""
        return self._face.get_advance(glyph, freetype.FT_LOAD_NO_SCALE)

    def typeface_name(self) -> str:
        """Returns the typeface's name, with its style unless that is
        "Regular": "Noto Sans", "Noto Sans Bold". Returns "" for a file that
        does not name it."""
        names = self._names()
        family = names.get(_TYPOGRAPHIC_FAMILY) or names.get(_FAMILY) or ""
        style = names.get(_TYPOGRAPHIC_STYLE) or names.get(_STYLE) or ""
        return family if style in ("", "Regular") or not family else family + " " + style

    def drawn(self, glyph: int, scale: float, smoothed: bool) -> DrawnGlyph:
        """Returns `glyph` drawn at `scale` pixels a font unit: smoothed,
        with FreeType's light hinting, its coverages from 0 to 255; or
        unsmoothed, unhinted, each pixel 0 or 255. A glyph the typeface holds
        as a bitmap for that size, as SimSun does for small ones, is drawn as
        FreeType gives it: one of a bit a pixel each pixel 0 or 255, and one
        of gray levels as above. Raises NxwrightError for a glyph FreeType
        cannot draw, as in a damaged file, or draws in another form, as in
        colour."""
        size = round(self.units_per_em * scale * 64)
        try:
            if size != self._size:
                self._face.set_char_size(size, 0, 72, 72)
                self._size = size
            if smoothed:
                self._face.load_glyph(glyph, freetype.FT_LOAD_TARGET_LIGHT)
                self._face.glyph.render(freetype.FT_RENDER_MODE_NORMAL)
            else:
                self._face.load_glyph(glyph, freetype.FT_LOAD_NO_HINTING)
                self._face.glyph.render(freetype.FT_RENDER_MODE_MONO)
        except freetype.FT_Exception as error:
            raise NxwrightError("glyph %d cannot be drawn: %s" % (glyph, error)) from None
        slot = self._face.glyph
        bitmap = slot.bitmap
        buffer = bytes(bitmap.buffer)
        if bitmap.pixel_mode == freetype.FT_PIXEL_MODE_GRAY:
            coverages = b"".join(buffer[row * bitmap.pitch:row * bitmap.pitch + bitmap.width]
                                 for row in range(bitmap.rows))
            if not smoothed:
                # Gray levels FreeType gives as they are, as a typeface's own
                # bitmap, are made full or empty.
                coverages = bytes(255 if coverage >= 128 else 0 for coverage in coverages)
        elif bitmap.pixel_mode != freetype.FT_PIXEL_MODE_MONO:
            raise NxwrightError("glyph %d is drawn in a form nxwright does not read "
                                "(FreeType's pixel mode %d)" % (glyph, bitmap.pixel_mode))
        else:
            # A monochrome row holds a bit a pixel, the first pixel the
            # highest bit of its first byte.
            coverages = bytes(
                255 if buffer[row * bitmap.pitch + column // 8] & (0x80 >> column % 8) else 0
                for row in range(bitmap.rows) for column in range(bitmap.width))
        return DrawnGlyph(slot.bitmap_left, slot.bitmap_top, bitmap.width, bitmap.rows, coverages)

    def _names(self) -> dict:
        """Returns the name table's names, by name number: Windows' records
        in US English where they are, else Windows' or Unicode's in any
        language."""
        names = {}
        for index in range(self._face.sfnt_name_count):
            record = self._face.get_sfnt_name(index)
            if not (record.platform_id == _UNICODE or record.platform_id == _WINDOWS
                    and record.encoding_id in _WINDOWS_UNICODE_ENCODINGS):
                continue
            if record.name_id not in names or (record.platform_id, record.language_id) == \
                    (_WINDOWS, _US_ENGLISH):
                names[record.name_id] = record.string.decode("utf-16-be", "replace")
        return names


@functools.cache
def noto_sans() -> TrueTypeFont:
    """Returns NOTO_SANS read, once per process. Its callers share it, one
    thread at a time (TrueTypeFont)."""
    return TrueTypeFont(NOTO_SANS.read_bytes())
