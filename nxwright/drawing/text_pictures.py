"""A component's text as the screen draws it, in the project's own font: a
picture as large as the component, clear but for the text's pixels, for the
page preview (page_drawing.py) and the samples of fonts (font_samples.py).

The font's glyphs and how they sit on a line come from the font itself
(project/zi_font.py). The text is written in the project's encoding, and the
font reads its bytes: a character of each byte, or, in a font in utf-8, of
each code point (zi_font.Font.characters_of), as the Editor's simulator
showed (tests/fixtures/utf-8-text/). These rules match the Editor's
simulator, pixel for pixel, on a test page (tests/fixtures/placing/):
  - A text's lines are split at its line breaks, "\\r\\n" (text_lines).
  - With `isbr` 1, a line wider than the component wraps before the first
    character that does not fit, inside a word or not.
  - `spax` pixels go between two characters, and `spay` between two lines.
  - The lines are aligned as one block, as wide as the widest line, each
    line starting at the block's left: `xcen` 0, 1, and 2 put the block at
    the left, the centre, and the right, and `ycen` 0, 1, and 2 at the top,
    the centre, and the bottom. Centring rounds down. A block wider than
    the component starts at its left, and one taller at its top, whatever
    `xcen` and `ycen` say (tests/fixtures/value-widgets/overflow.png).
  - With `pw` 1, each character shows as "*".
  - The text is drawn within the component's rectangle, and what falls
    outside is cut off.
The Editor's simulator matched these too (tests/fixtures/drawing-assumptions/,
page28): lines of different widths centred as one block, as they are put at
the right; a space where a line wraps kept as any character, at widths of
60 to 100; and a border (page_drawing.py) leaving the text where it is, at
each corner and in the middle.
A pixel of coverage c (0 to 7) takes c/7 of the text colour, the reading the
font research's drawings used, which the test page bears out on white.
"""
from nxwright import NxwrightError, listed_in_words
from nxwright.project.device_settings import TextCodec
from nxwright.project.zi_font import UTF8, pair_name


class MissingCharacter(NxwrightError):
    """Raised for a character the font lacks, or the project's encoding cannot write."""


def text_picture(text: str, font, encoding: str, values: dict, width: int, height: int,
                 colour: tuple, at: tuple = (None, None)) -> bytes:
    """Returns the RGBA pixels, row by row, of a `width` by `height` picture
    of `text` in `font` (a zi_font.Font), placed as the module's docstring
    says by `values`, the component's attributes: the text in the RGB colour
    `colour`, each pixel's coverage as its transparency, and the rest clear.
    `at`, (left, top), puts the block's left or top there in the picture in
    place of `xcen` or `ycen`, where it is not None, even outside the
    picture: a scrolling text's, as it moves. Raises MissingCharacter for a
    character `font` or `encoding` lacks."""
    spax, spay = values.get("spax", 0), values.get("spay", 0)
    lines = _laid_out(text, font, encoding, values, width)
    coverage = bytearray(width * height)
    block_width, block_height = _block_size(lines, font, spax, spay)
    # A table marked defaults = false may leave them out: the types' default is 1.
    left, top = at
    if top is None:
        top = aligned_start(values.get("ycen", 1), height, block_height)
    if left is None:
        left = aligned_start(values.get("xcen", 1), width, block_width)
    for number, characters in enumerate(lines):
        _draw_line(coverage, width, height, characters, left,
                   top + number * (font.height + spay), font.height, spax)
    return _rgba(coverage, colour)


def block_size(text: str, font, encoding: str, values: dict, width: int) -> tuple:
    """Returns the width and height, in pixels, of the block of lines
    text_picture makes of `text` in a picture `width` wide, wrapped and
    spaced as `values` say. Raises MissingCharacter as text_picture does."""
    lines = _laid_out(text, font, encoding, values, width)
    return _block_size(lines, font, values.get("spax", 0), values.get("spay", 0))


def _laid_out(text: str, font, encoding: str, values: dict, width: int) -> list:
    """Returns the lines of `text`, each a list of the font's Characters, as
    the module's docstring says: hidden by `pw`, and wrapped at `width` with
    `isbr`."""
    text = shown_text(text, values)
    lines = []
    for line in text_lines(text):
        characters = _characters(line, font, encoding)
        lines += _wrapped(characters, values.get("spax", 0), width) if values.get("isbr") \
            else [characters]
    return lines


def shown_text(text: str, values: dict) -> str:
    """The text as the screen shows it: each character a "*" with `pw` 1."""
    return "*" * len(text) if values.get("pw") else text


def _block_size(lines: list, font, spax: int, spay: int) -> tuple:
    """The width and height of a block of `lines`, `spay` between two."""
    return (max(_line_width(characters, spax) for characters in lines),
            len(lines) * font.height + max(len(lines) - 1, 0) * spay)


def text_size(text: str, font, encoding: str, spax: int = 0) -> tuple:
    """Returns the width and height, in pixels, that `text` takes in `font`
    (a zi_font.Font), as text_picture places it with `spax` pixels between
    characters and no wrapping. Raises MissingCharacter as text_picture
    does."""
    return _block_size([_characters(line, font, encoding) for line in text_lines(text)],
                       font, spax, 0)


def text_lines(text: str) -> list:
    """Returns a text's lines, split where a carriage return is followed by
    a line feed. A carriage return or a line feed alone breaks no line, and
    shows as a space, as the Editor's simulator drew them in a text, a
    sliding text, a select, and a combo box
    (tests/fixtures/drawing-assumptions/)."""
    return [line.replace("\r", " ").replace("\n", " ") for line in text.split("\r\n")]


def path_lines(path) -> list:
    """Returns the lines of a select's or a combo box's `path`, split as a
    text's are (text_lines); none when it is empty or no text."""
    return text_lines(path) if isinstance(path, str) and path else []


def lacking_note(text: str, font, encoding: str, values: dict = None):
    """Returns what a note says of `text`, drawn by text_picture in `font`
    (a zi_font.Font), hidden by the `pw` of `values`, when the font lacks
    some of its characters: each, named, and what the screen draws in their
    place, as zi_font.Font.characters_of draws it. None when it lacks none.
    In a two-byte font of the text's own encoding, it says instead which
    characters the font's grid has no place for (_unplaced_note). Raises
    MissingCharacter as text_picture does."""
    text = shown_text(text, values or {})
    if font.grid is not None and encoding == font.encoding:
        return _unplaced_note(text, font)
    codes = []
    for line in text_lines(text):
        data = _encoded(line, encoding)
        try:
            codes += font.lacking(data)
        except NxwrightError as error:
            raise MissingCharacter(str(error)) from None
    codes = list(dict.fromkeys(codes))
    if not codes:
        return None
    place = "its place" if len(codes) == 1 else "their place"
    if font.first_character is None:
        drawn = "nothing in %s, half the height wide" % place
    else:
        first = font.first_character.code
        drawn = "its first character, %s, in %s" % (
            "the space" if first == 0x20 else _character_name(font, first), place)
    return "font %s lacks %s; the screen draws %s" % (
        font.name, listed_in_words([_character_name(font, code) for code in codes]), drawn)


def _unplaced_note(text: str, font):
    """Returns what a note says of `text` in a two-byte font of its own
    encoding, when the font's grid has no place for some of its characters:
    each, and what the screen shows instead. None when each has its place.

    A character has its place when the screen reads its bytes, and no more,
    as one character, drawn from its own entry (zi_font.Font.spans_of). One
    without is a pair outside the grid, which the screen draws from the
    entry its place falls on, or from the font's first; or a character of
    one byte from 80, as shift-jis's half-width katakana, which the screen
    takes as a pair with the byte after it. A character the screen reads
    out of step, from within a span begun before it, is not drawn as itself
    either, and is not named apart: the note says the text after such a
    character shows as other characters, unless the screen is back in step
    after the one character it took. Raises MissingCharacter as
    text_picture does."""
    found = {}      # {character: what the screen shows, worded}
    for line in text_lines(text):
        data = _encoded(line, font.encoding)
        spans = {start: (length, drawn) for start, length, drawn in font.spans_of(data)}
        # Where each of the line's characters starts and ends in its bytes.
        bounds, offset = [], 0
        for character in line:
            size = len(_encoded(character, font.encoding))
            bounds.append((character, offset, offset + size))
            offset += size
        inside = {place for start, (length, _) in spans.items()
                  for place in range(start + 1, start + length)}
        for number, (character, start, end) in enumerate(bounds):
            own, span = data[start:end], spans.get(start)
            if start in inside or _placed(own, span):
                continue
            if span is None or start + span[0] <= end:
                shown = " as %s" % _shown_as(font, span)
            elif number + 1 < len(bounds) and bounds[number + 1][2] == start + span[0]:
                shown = ", with the character after it, as %s" % _shown_as(font, span)
            else:
                shown = ", with the text after it, as other characters"
            found.setdefault("%s (%s)" % (character, own.hex(" ")), shown)
    if not found:
        return None
    if len(found) == 1:
        (character, shown), = found.items()
        return "the font %s has no place for %s, which the screen shows%s" % (
            font.name, character, shown)
    return ("the font %s has no place for these characters, which the screen shows otherwise: "
            "%s" % (font.name, listed_in_words([character + shown
                                                for character, shown in found.items()])))


def _placed(own: bytes, span) -> bool:
    """Whether the screen reads a character's bytes, `own`, as itself: a span
    (length, Character) starting at them, as long, drawn from their entry."""
    if span is None or span[0] != len(own):
        return False
    return span[1].code == (own[0] if len(own) == 1 else own[0] | own[1] << 8)


def _shown_as(font, span) -> str:
    """What the screen shows for a span (length, Character), worded: nothing
    for no span or an empty glyph, else the character drawn, a pair with its
    bytes, as "、 (81 41)"."""
    if span is None or not any(span[1].coverages()):
        return "nothing"
    code = span[1].code
    if code == 0x20:
        return "a space"
    data = bytes([code & 0xff, code >> 8]) if code > 0xff else bytes([code])
    try:
        character = TextCodec(font.encoding).decode(data, "the font")
    except NxwrightError:
        character = None
    if character is None or not character.isprintable() or character.isspace():
        return pair_name(code) if code > 0xff else "character %d" % code
    return "%s (%s)" % (character, data.hex(" ")) if code > 0xff else character


def _character_name(font, code: int) -> str:
    """How a note names a character of `font`: its code point in utf-8, as
    U+00E9; in a two-byte font, a pair by its two bytes, as 81 40; else its
    byte, as character 233."""
    if font.encoding == UTF8:
        return "U+%04X" % code
    if font.grid is not None and code > 0xff:
        return pair_name(code)
    return "character %d" % code


def _encoded(line: str, encoding: str) -> bytes:
    """A line of text written in `encoding`. Raises MissingCharacter for a
    character the encoding cannot write."""
    try:
        return TextCodec(encoding).encode(line, "the text")
    except NxwrightError:
        raise MissingCharacter("the text %r holds a character %s cannot write"
                               % (line, encoding)) from None


def _characters(line: str, font, encoding: str) -> list:
    """Returns the font's Characters for a line of text, written in
    `encoding`, as the font reads its bytes (zi_font.Font.characters_of)."""
    data = _encoded(line, encoding)
    try:
        characters = font.characters_of(data)
    except NxwrightError as error:
        raise MissingCharacter(str(error)) from None
    if None in characters:
        # Only a one-byte font's table of no character has no first character
        # to draw in a lacking one's place, so the place is the byte's.
        raise MissingCharacter("font %s has no character %d"
                               % (font.name, data[characters.index(None)]))
    return characters


def _wrapped(characters: list, spax: int, width: int) -> list:
    """Returns a line's characters cut into lines no wider than `width`, each
    before the first character that does not fit; a line holds one character
    at least."""
    lines, start = [], 0
    while start < len(characters):
        end = start + 1
        while end < len(characters) and _line_width(characters[start:end + 1], spax) <= width:
            end += 1
        lines.append(characters[start:end])
        start = end
    return lines or [[]]


def _line_width(characters: list, spax: int) -> int:
    return sum(character.advance for character in characters) + spax * max(len(characters) - 1, 0)


def aligned_start(alignment: int, room: int, size: int) -> int:
    """Returns where a thing `size` long starts in `room`, aligned by an xcen
    or ycen value: at 0 when it is longer than `room`. A scrolling text is
    aligned across its way by its kept size (scrolling_text_drawing.py)."""
    if alignment == 1:
        return max((room - size) // 2, 0)
    if alignment == 2:
        return max(room - size, 0)
    return 0


def _draw_line(coverage: bytearray, width: int, height: int, characters: list, pen: int,
               top: int, font_height: int, spax: int):
    """Draws one line's glyphs into `coverage`, keeping the larger coverage
    where two glyphs overlap, and cutting what falls outside."""
    for character in characters:
        glyph, glyph_width = character.coverages(), character.width
        left = pen - character.left
        for row in range(font_height):
            y = top + row
            if not 0 <= y < height:
                continue
            for column in range(glyph_width):
                value = glyph[row * glyph_width + column]
                x = left + column
                if value and 0 <= x < width and value > coverage[y * width + x]:
                    coverage[y * width + x] = value
        pen += character.advance + spax


# Coverage 0 to 7 as an alpha from 0 to 255, rounded.
_ALPHAS = bytes((level * 255 + 3) // 7 for level in range(8)) + bytes(248)


def _rgba(coverage: bytearray, colour: tuple) -> bytes:
    pixels = bytearray(len(coverage) * 4)
    for channel, value in enumerate(colour):
        pixels[channel::4] = bytes([value]) * len(coverage)
    pixels[3::4] = bytes(coverage).translate(_ALPHAS)
    return bytes(pixels)
