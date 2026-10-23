"""Samples: a text drawn in a font as the screen draws it, for nxwright's
Fonts panel in VS Code. The text is drawn by the page preview's
text_picture (text_pictures.py), at the left and top of a picture as large
as the text, as a text component exactly that large shows it: a glyph's
overhang past either end of a line is cut.

The text is written in the folder's encoding, and the font reads its bytes
as the screen does (text_pictures.py): each byte as the font's character
for that byte, as the Editor draws a font in another encoding than the
project's (docs/format.md), or, in a font in utf-8, each code point.

The panel's box is nxwright's own, not the screen's: each line break typed
in it ends a line, however it is written, where a screen's text breaks a
line only at a carriage return and a line feed (text_pictures.text_lines).
"""
import re

from nxwright import NxwrightError
from nxwright.drawing.text_pictures import lacking_note, text_lines, text_picture, text_size
from nxwright.project.device_settings import TextCodec
from nxwright.project.font_drawing import draw_characters, drawn_codes
from nxwright.project.pictures import write_png
from nxwright.project.truetype import TrueTypeFont
from nxwright.project.zi_font import (GRID_ENCODINGS, UTF8, Font, decode_font, encode_font,
                                      text_codes, two_byte_sample)


def font_sample(font: Font, text: str, encoding: str, colour: tuple) -> bytes:
    """Returns a PNG picture of `text` in `font`, a decoded font, written in
    `encoding`: the text in the RGB colour `colour`, each pixel's coverage as
    its transparency, and the rest clear. A character the font lacks is
    drawn as the screen draws it (zi_font.Font.characters_of), which
    sample_note says. Raises NxwrightError for a text with no character to
    draw, and MissingCharacter (text_pictures.py) for a character the
    encoding cannot write."""
    text = _typed_lines(text)
    width, height = text_size(text, font, encoding)
    if not width:
        raise NxwrightError("the sample has no text")
    return write_png(width, height, text_picture(text, font, encoding, {"xcen": 0, "ycen": 0},
                                                 width, height, colour))


def sample_note(font: Font, text: str, encoding: str):
    """Returns what the note under a sample of `text` in `font` says of the
    characters the font lacks (text_pictures.lacking_note), or None."""
    return lacking_note(_typed_lines(text), font, encoding)


def sample_font(typeface: TrueTypeFont, height: int, encoding: str, smoothed: bool,
                text: str, characters=None, full_table: bool = False) -> Font:
    """Returns the font `nxwright font` would draw from a typeface file,
    `height` pixels tall, in `encoding`, smoothed or not, a `full_table` or
    not in utf-8, holding only the characters of `text`, for a sample of it.
    Drawing only those keeps a sample quick, even at large heights. Its
    characters are the codes the font reads the text's bytes as in
    `encoding`, or its code points in utf-8 (zi_font.text_codes), among
    those the font would hold (font_drawing.drawn_codes). It holds the
    font's first character too, but in a full table, as the screen draws
    that one for a character the font lacks, and is laid out as the font
    will be; a two-byte font is a Font of those positions alone
    (zi_font.two_byte_sample), as writing every one would be slow. Its line
    breaks are no characters: they end lines, as text_picture draws them.
    Raises NxwrightError where draw_characters and font_codes do, for a
    character the encoding cannot write, and for a text of none of the
    font's characters."""
    written = "".join(text_lines(_typed_lines(text)))
    held = drawn_codes(typeface, encoding, characters, full_table)[0]
    wanted = (set(map(ord, written)) if encoding == UTF8
              else set(text_codes(TextCodec(encoding).encode(written, "the sample"), encoding)))
    # Those the font would not hold are left out, as the screen draws them,
    # the rest kept in the font's order.
    codes = [code for code in held if code in wanted]
    if wanted and not codes:
        raise NxwrightError("the font would contain none of the sample's characters")
    if not codes:
        raise NxwrightError("the sample has no text")
    if not (encoding == UTF8 and full_table) and codes[0] != held[0]:
        codes.insert(0, held[0])
    glyphs = draw_characters(typeface, height, encoding, codes, smoothed)
    if encoding in GRID_ENCODINGS:
        return two_byte_sample("sample", encoding, height, glyphs, smoothed)
    return decode_font(encode_font("sample", encoding, height, 0, glyphs, smoothed, full_table))


def _typed_lines(text: str) -> str:
    """Returns a sample's `text` with each line break typed in it, a
    carriage return, a line feed, or both, written as a screen's text
    writes one, both, so that it ends a line there."""
    return "\r\n".join(re.split(r"\r\n|\r|\n", text))
