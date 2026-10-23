"""Drawing a font from a typeface file (truetype.py): the characters of a
one-byte encoding, code points in utf-8, or the positions of a two-byte
encoding, at a height in pixels, as the Glyphs that encode_font writes
(zi_font.py).

The characters are those of the Editor's fonts. In a one-byte encoding,
they are every byte from 0x20, to 0x7e in ascii and to 0xff in the others,
each drawn by the typeface file's glyph for the character the encoding
reads it as. In utf-8, they are the code points asked for, U+0000 to U+00FF
by default, as the generator's first two blocks. In a two-byte encoding,
they are every position of the grid and the ascii characters
(zi_font.grid_table_codes), a position drawn as the character the folder's
code page gives it (TextCodec.codec_name): GBK for gb2312, as in the
Nextion Editor's own gb2312 font, and cp950, cp932, and cp949 for big5,
shift-jis, and ks_c_5601-1987. A position the code page gives none, or
whose character the file lacks, is empty, as wide as the font is tall.

DEL, the next-line control (U+0085), and the soft hyphen are drawn empty,
one pixel wide. Any other control character the file lacks, as iso-8859-1's
others from 0x80 to 0x9f, and a byte the encoding leaves undefined, get the
file's missing-character glyph. Those are as the Editor's iso-8859-1 fonts
have them, but for two widths: its DEL is as wide as a letter, and its 0x84
has the space's advance. The generator draws utf-8's U+007F to U+00FF alike.
Of utf-8's U+0000 to U+001F, those the generator draws empty are drawn
empty, a pixel wide, and the others get the missing-character glyph, as
there; but its U+0002 and U+000A are wider, and its U+000C is the glyph at
a width of its own. A code point Unicode leaves unassigned, by the table of
the Python running nxwright (unicodedata), gets the missing-character glyph
too, as in the generator's fonts. Any other character the file lacks is
left out of the font, and a warning says so (drawn_codes, font_warning):
the generator draws it from another typeface Windows picks, which nxwright
cannot. A one-byte font then has a gap, past which the screen finds each
character by its code (zi_font.encode_font).

The outlines are scaled so that the font's ascender and descender span the
height, as in the Editor's fonts: there, each advance is within a pixel of
the typeface file's, scaled so, and each advance here is that, rounded. The
baseline is put on a whole pixel, as in the Editor's small fonts, so that
the flat bottoms of letters are sharp: on the one above, so that the
descenders stay inside the font.

FreeType draws each glyph (truetype.TrueTypeFont.drawn). Smoothed, it uses
its light hinting, and a pixel's coverage, from 0 to 7, is seven times the
share FreeType gives it, rounded. Without smoothing, it draws in
monochrome, unhinted, its dropout control keeping the parts thinner than a
pixel, such as the dots of a small "ü".

The Editor draws with Windows' own hinting, which FreeType does not have, so
its glyphs and nxwright's still differ in their pixels. Of FreeType's ways
of drawing, these two come closest to the Editor's fonts drawn from Noto
Sans (tests/fixtures/fonts), counting the pixels more than one level apart,
but at 16 pixels: there, unhinted drawing comes a little closer, and one
way is kept for every height.
"""
import math
import re
import unicodedata

from nxwright import NxwrightError
from nxwright.project.device_settings import TextCodec
from nxwright.project.truetype import MISSING_GLYPH, TrueTypeFont
from nxwright.project.zi_font import (FONT_ENCODINGS, GRID_ENCODINGS, UTF8, Glyph, encode_font,
                                      grid_table_codes, pair_name)

# The heights the Editor's generator makes, in pixels. Its list offers 16 to
# 254, as the vendor's description says, but a height can be typed, from 12.
# Typed lower, the generator made a 12-pixel font; typed 255, a 254-pixel one.
_LOWEST, _HIGHEST = 12, 254
# The control characters drawn empty, a pixel wide. Of U+0000 to U+001F, the
# generator's utf-8 fonts have these empty.
_DRAWN_EMPTY = ("\x00", "\x02", "\t", "\n", "\x0b", "\r", "\x1c", "\x1d", "\x1e", "\x1f",
                "\x7f", "\x85", "\xad")
# A character the typeface file has no glyph for, and the generator draws
# from another typeface.
_LACKING = object()
# A position of a two-byte font drawn empty, as wide as the font is tall: one
# with no character, or whose character the typeface file lacks. Its table
# keeps every position, as the screen finds a character by its place.
_EMPTY_POSITION = object()
# The last code point of a font in utf-8.
_LAST_CODE_POINT = 0xffff
# A utf-8 font's characters, unless others are asked for: the generator's
# first two blocks.
_FIRST_TWO_BLOCKS = range(0x100)
# The space, which every font of chosen characters the generator writes holds.
_SPACE = 0x20
# The code points utf-16 pairs to write those past U+FFFF: no characters.
_SURROGATES = range(0xd800, 0xe000)
# A code point in hexadecimal, or a range of them, as code_points_of reads.
_CODE_POINTS = re.compile(r"([0-9A-Fa-f]+)(?:-([0-9A-Fa-f]+))?")


def draw_font(font: TrueTypeFont, height: int, encoding: str, smoothed: bool = True,
              characters=None, full_table: bool = False) -> list:
    """Returns the Glyphs of a font's characters, drawn from a typeface
    file, `height` pixels tall, smoothed or not: in a one-byte encoding,
    every character of the encoding; in utf-8, the code points `characters`
    in increasing order, U+0000 to U+00FF by default, and the space unless
    the font is to be a `full_table` (font_codes); but those the typeface
    file lacks (drawn_codes). Raises NxwrightError for a two-byte encoding,
    `characters` in a one-byte encoding, a height that is not from 12 to
    254, a font whose ascender is not above its descender, or a typeface
    that has none of the characters."""
    _check_drawing(font, height, encoding)
    return draw_characters(font, height, encoding,
                           drawn_codes(font, encoding, characters, full_table)[0], smoothed)


def draw_font_block(name: str, font: TrueTypeFont, height: int, encoding: str, rotation: int,
                    smoothed: bool = True, characters=None, full_table: bool = False) -> bytes:
    """Returns the block of a font named `name`, drawn from a typeface file
    as draw_font draws it, and stored at `rotation` (zi_font.encode_font):
    in utf-8, a table of its characters alone, or a `full_table`. Raises
    NxwrightError where either refuses."""
    return encode_font(name, encoding, height, rotation,
                       draw_font(font, height, encoding, smoothed, characters, full_table),
                       smoothed, full_table)


def check_drawable(font: TrueTypeFont, height: int, encoding: str, characters=None,
                   full_table: bool = False):
    """Returns the warning of the characters the typeface lacks of a font
    draw_font would draw (font_warning), or None. Raises NxwrightError where
    draw_font would refuse to draw it, as it does, without drawing it:
    quickly, as for a form asking for one."""
    _check_drawing(font, height, encoding)
    # drawn_codes has looked up each glyph, as drawing it would.
    return _warning(*drawn_codes(font, encoding, characters, full_table), encoding, full_table)


def drawn_codes(font: TrueTypeFont, encoding: str, characters=None,
                full_table: bool = False) -> tuple:
    """Returns (the codes draw_font draws, the characters the typeface file
    lacks): the codes of font_codes, but those of characters the file has no
    glyph for, which the generator would draw from another typeface. A
    two-byte font keeps every position, one the file lacks drawn empty
    (_EMPTY_POSITION), and the characters lacking are the encoding's own.
    Raises NxwrightError where font_codes does, for an encoding no project
    can have, and for a typeface that has none of the characters but
    control characters, which a font draws without the file's glyphs."""
    _check_encoding(encoding)
    wanted = font_codes(encoding, characters, full_table)
    _check_codes(wanted, encoding)
    two_byte = encoding in GRID_ENCODINGS
    codes, drawn, lacking = [], [], []
    for code in wanted:
        glyph = _glyph_of_code(font, code, encoding)
        if glyph is _LACKING:
            if two_byte:
                codes.append(code)
            if not two_byte or _of_the_encoding(code, encoding):
                lacking.append(_character_of(code, encoding))
        else:
            codes.append(code)
            if glyph is not _EMPTY_POSITION:
                drawn.append(code)
    # The space a utf-8 font of chosen characters adds is none of those asked for.
    asked = set(characters) if encoding == UTF8 and characters is not None else set(wanted)
    if lacking and not any(code in asked
                           and unicodedata.category(_character_of(code, encoding)) != "Cc"
                           for code in drawn):
        raise NxwrightError("the typeface file has none of the %s"
                            % ("characters asked for" if encoding == UTF8
                               else "characters of %s" % encoding))
    return codes, lacking


def font_warning(font: TrueTypeFont, encoding: str, characters=None, full_table: bool = False):
    """Returns what a warning says of the characters the typeface file lacks
    of a font draw_font would draw, left out of it (drawn_codes): how many,
    one of them, and what the screen shows in their place, as it shows a
    character a font lacks (zi_font.Font.characters_of). None when it lacks
    none."""
    return _warning(*drawn_codes(font, encoding, characters, full_table), encoding, full_table)


def lacking_words(codes: list, lacking: list, encoding: str, full_table: bool = False):
    """Returns how warnings word what a font of `codes` lacks, the
    characters `lacking` its typeface lacks (drawn_codes): (how many and one
    of them, what the screen shows in their place), as ("56 characters of
    koi8-r, such as '─' (U+2500)", "the font's first character, the
    space, in their place"). None when it lacks none."""
    if not lacking:
        return None
    if encoding == UTF8 and full_table:
        shown = "nothing in their place, half the height wide"
    elif encoding in GRID_ENCODINGS:
        shown = "nothing in their place, the height wide"
    else:
        first = codes[0]
        shown = "the font's first character, %s, in their place" % (
            "the space" if first == _SPACE else
            "U+%04X" % first if encoding == UTF8 else "character %d" % first)
    return _how_many(lacking, encoding), shown


def _warning(codes: list, lacking: list, encoding: str, full_table: bool):
    """font_warning's words, of drawn_codes' codes and lacking characters."""
    words = lacking_words(codes, lacking, encoding, full_table)
    if words is None:
        return None
    return ("the typeface file lacks %s; the font leaves them out, and the screen shows %s"
            % words)


def font_codes(encoding: str, characters=None, full_table: bool = False):
    """Returns the codes of the characters draw_font draws: every byte a
    one-byte encoding has a character for, or in utf-8 the code points
    `characters`, U+0000 to U+00FF by default. A utf-8 font that is no
    `full_table` holds the space too, as the generator adds it to the
    characters typed for "Specified character": when the characters start
    above it, a character the font lacks then shows as a space's gap, its
    first character (zi_font.Font.characters_of). In a two-byte encoding,
    they are every position of its table, in its order
    (zi_font.grid_table_codes). Raises NxwrightError for `characters` in
    another encoding than utf-8."""
    if encoding == UTF8:
        codes = _FIRST_TWO_BLOCKS if characters is None else characters
        return codes if full_table else sorted(set(codes) | {_SPACE})
    if characters is not None:
        raise NxwrightError("a font in %s holds every character of its encoding; characters "
                            "are chosen in utf-8 only" % encoding)
    return grid_table_codes(encoding) if encoding in GRID_ENCODINGS else _codes(encoding)


def draw_characters(font: TrueTypeFont, height: int, encoding: str, codes,
                    smoothed: bool = True) -> list:
    """Returns the Glyphs of `codes`, in their order, drawn as draw_font
    draws them: bytes of a one-byte encoding, which it does for each byte a
    font has a character for, code points in utf-8, or positions of a
    two-byte encoding. Drawing a few is quicker than drawing the whole font,
    as for a sample of it. Raises NxwrightError where draw_font does, for a
    code a font has no character for, and, but in a two-byte encoding, for
    one whose character the typeface file lacks."""
    glyphs_of_codes = _glyphs_of_codes(font, height, encoding, codes)
    scale = height / (font.ascender - font.descender)
    baseline = math.floor(font.ascender * scale)
    return [_drawn_glyph(font, code, glyph, scale, baseline, height, smoothed)
            for code, glyph in glyphs_of_codes.items()]


def _glyphs_of_codes(font: TrueTypeFont, height: int, encoding: str, codes) -> dict:
    """Returns {code: the glyph drawing it} (_glyph_of_code) of `codes`.
    Raises NxwrightError where draw_characters does."""
    _check_encoding(encoding)
    _check_codes(codes, encoding)
    _check_drawing(font, height, encoding)
    glyphs_of_codes = {code: _glyph_of_code(font, code, encoding) for code in codes}
    if encoding in GRID_ENCODINGS:
        # A two-byte font keeps every position: one the typeface lacks is
        # drawn empty (drawn_codes).
        return {code: _EMPTY_POSITION if glyph is _LACKING else glyph
                for code, glyph in glyphs_of_codes.items()}
    # draw_font asks for those the typeface has (drawn_codes); a caller
    # asking for one it lacks is refused.
    lacking = [_character_of(code, encoding) for code, glyph in glyphs_of_codes.items()
               if glyph is _LACKING]
    if lacking:
        raise NxwrightError("the typeface file lacks %s" % _how_many(lacking, encoding))
    return glyphs_of_codes


def _check_encoding(encoding: str):
    if encoding not in FONT_ENCODINGS:
        raise NxwrightError("a font in %s cannot be drawn: it is no encoding a project can have"
                            % encoding)


def _check_codes(codes, encoding: str):
    """Refuses a code no font of `encoding` has a character for: past
    U+FFFF in utf-8, a position outside a two-byte font's table, or a byte
    of a one-byte encoding with none."""
    if encoding == UTF8:
        outside = [code for code in codes if not 0 <= code <= _LAST_CODE_POINT]
        if outside:
            raise NxwrightError("a font in utf-8 has no character U+%04X" % outside[0])
    elif encoding in GRID_ENCODINGS:
        positions = set(grid_table_codes(encoding))
        outside = [code for code in codes if code not in positions]
        if outside:
            named = pair_name(outside[0]) if outside[0] > 0xff else "for byte %d" % outside[0]
            raise NxwrightError("a font in %s has no character %s" % (encoding, named))
    else:
        outside = [code for code in codes if code not in _codes(encoding)]
        if outside:
            raise NxwrightError("a font in %s has no character for byte %d"
                                % (encoding, outside[0]))


def _check_drawing(font: TrueTypeFont, height: int, encoding: str):
    """Refuses a font of an encoding nxwright draws none in, of a height the
    generator does not make, or of a typeface with no height: before any of
    its glyphs is read."""
    _check_encoding(encoding)
    if not _LOWEST <= height <= _HIGHEST:
        raise NxwrightError("height %d is not from %d to %d" % (height, _LOWEST, _HIGHEST))
    if font.ascender <= font.descender:
        raise NxwrightError("the typeface file's ascender, %d, is not above its descender, %d"
                            % (font.ascender, font.descender))


def _character_of(code: int, encoding: str):
    """The character a code of a font stands for: a code point in utf-8, a
    byte of a one-byte encoding, which its font has a character for, or a
    position of a two-byte encoding, as the folder's code page has it
    (TextCodec.codec_name), or None for a position it gives none."""
    if encoding == UTF8:
        return chr(code)
    codec = TextCodec(encoding).codec_name
    if code > 0xff:
        try:
            return bytes([code & 0xff, code >> 8]).decode(codec)
        except UnicodeDecodeError:
            return None
    return bytes([code]).decode(codec)


def _of_the_encoding(code: int, encoding: str) -> bool:
    """Whether a code of a font is a character of its encoding itself, as a
    GB2312 character of a gb2312 font's position, where _character_of may
    give one only its code page, GBK, has (TextCodec.own_codec_name)."""
    try:
        bytes([code & 0xff, code >> 8] if code > 0xff else [code]).decode(
            TextCodec(encoding).own_codec_name)
    except UnicodeDecodeError:
        return False
    return True


def _how_many(lacking: list, encoding: str) -> str:
    """Says how many characters, `lacking`, a typeface lacks, and gives the
    first: "56 characters of koi8-r, such as '─' (U+2500)"."""
    which = ("of the characters asked for" if encoding == UTF8 else
             "%s of %s" % ("character" if len(lacking) == 1 else "characters", encoding))
    return "%d %s, such as %r (U+%04X)" % (len(lacking), which, lacking[0], ord(lacking[0]))


def lacking_characters(font: TrueTypeFont, encoding: str) -> list:
    """Returns the characters of an encoding, one-byte or two-byte, that a
    typeface lacks, in the order of a font's table. Control characters are
    left out, since a font draws them without the file's glyphs. A font of
    the encoding drawn from it leaves them out, or empty (drawn_codes)."""
    return list(_lacking_characters(font, encoding))


def lacks_a_letter(font: TrueTypeFont, encoding: str) -> bool:
    """Whether a typeface lacks a letter of an encoding, by Unicode's
    categories, among the characters lacking_characters gives. It stops at
    the first, so that a typeface lacking one of a two-byte encoding's
    thousands is soon told."""
    return any(unicodedata.category(character).startswith("L")
               for character in _lacking_characters(font, encoding))


def _lacking_characters(font: TrueTypeFont, encoding: str):
    """Yields lacking_characters' characters, one at a time."""
    for code in font_codes(encoding):
        if _of_the_encoding(code, encoding) and _glyph_of_code(font, code, encoding) is _LACKING:
            yield _character_of(code, encoding)


def code_points_of(ranges: str) -> list:
    """Returns the code points `ranges` gives, in increasing order, each once:
    code points in hexadecimal and ranges of them, apart by commas, such as
    "20-7e,400-4ff". Raises NxwrightError for anything else, a range that ends
    before it starts, a code point past U+FFFF, a surrogate, or none at all."""
    code_points = set()
    for part in (part.strip() for part in ranges.split(",")):
        if not part:
            continue
        match = _CODE_POINTS.fullmatch(part)
        if match is None:
            raise NxwrightError("%r is not a code point in hexadecimal, nor a range of them "
                                "such as 400-4ff" % part)
        first, last = int(match[1], 16), int(match[2] or match[1], 16)
        if last < first:
            raise NxwrightError("the range %s ends before it starts" % part)
        if last > _LAST_CODE_POINT:
            raise NxwrightError("U+%04X lies past U+%04X, the last a font in utf-8 holds"
                                % (last, _LAST_CODE_POINT))
        if first < _SURROGATES.stop and last >= _SURROGATES.start:
            raise NxwrightError("U+D800 to U+DFFF are surrogates, not characters: leave them "
                                "out, as in 0-d7ff,e000-ffff")
        code_points.update(range(first, last + 1))
    if not code_points:
        raise NxwrightError("no characters are given")
    return sorted(code_points)


def code_point_ranges(code_points: list) -> str:
    """Returns `code_points`, in increasing order, as code_points_of reads
    them: runs as "first-last" and single code points, in hexadecimal, apart
    by commas, such as "20-7e,400-4ff". Surrogates, which it refuses, are
    left out."""
    runs = []
    for code_point in code_points:
        if code_point in _SURROGATES:
            continue
        if runs and runs[-1][1] == code_point - 1:
            runs[-1][1] = code_point
        else:
            runs.append([code_point, code_point])
    return ",".join("%x" % first if first == last else "%x-%x" % (first, last)
                    for first, last in runs)


def _codes(encoding: str) -> range:
    """Returns the bytes a font of a one-byte encoding has a character for."""
    return range(0x20, 0x7f if encoding == "ascii" else 0x100)


def _glyph_of_code(font: TrueTypeFont, code: int, encoding: str):
    """Returns the glyph drawing a code: a byte of a one-byte encoding, a
    code point in utf-8, or a position of a two-byte encoding. It is a glyph
    number, None to draw it empty, _EMPTY_POSITION for a two-byte font's
    position with no character, or _LACKING."""
    if encoding == UTF8:
        return _glyph_of(font, chr(code))
    try:
        character = _character_of(code, encoding)
    except UnicodeDecodeError:
        return MISSING_GLYPH
    if character is None:
        return _EMPTY_POSITION
    return _glyph_of(font, character)


def _glyph_of(font: TrueTypeFont, character: str):
    """Returns the glyph drawing a character, as _glyph_of_code says. A
    control character the file lacks gets the missing-character glyph, and
    so does a code point Unicode leaves unassigned, as the generator draws
    them."""
    if character in _DRAWN_EMPTY:
        return None
    glyph = font.glyph_of(character)
    if glyph is not None:
        return glyph
    return MISSING_GLYPH if unicodedata.category(character) in ("Cc", "Cn") else _LACKING


def _drawn_glyph(font: TrueTypeFont, code: int, glyph, scale: float, baseline: int,
                 height: int, smoothed: bool) -> Glyph:
    """Draws a glyph, `glyph` being its number in the typeface file, None
    for one drawn empty, or _EMPTY_POSITION."""
    if glyph is None:
        return Glyph(code, 1, 0, 0, (0,) * height)
    if glyph is _EMPTY_POSITION:
        return Glyph(code, height, 0, 0, (0,) * (height * height))
    advance = round(font.advance(glyph) * scale)
    drawn = font.drawn(glyph, scale, smoothed)
    # The rows of the font its pixels fall on, and its columns from the pen.
    levels = {}
    for row in range(drawn.rows):
        y = baseline - drawn.top + row
        if not 0 <= y < height:
            continue
        for column in range(drawn.width):
            level = round(7 * drawn.coverages[row * drawn.width + column] / 255)
            if level:
                levels[(drawn.left + column, y)] = level
    if not levels:
        return Glyph(code, advance, 0, 0, (0,) * (advance * height))
    # The overhangs are the columns of ink left of the pen, and past the
    # advance.
    inked = [x for x, _ in levels]
    left = max(0, -min(inked))
    right = max(0, max(inked) + 1 - advance)
    return Glyph(code, advance, left, right,
                 tuple(levels.get((x, y), 0) for y in range(height)
                       for x in range(-left, advance + right)))
