"""Font blocks (".zi"): reading what a font's header says, decoding a font,
to draw its text, and writing one, such as a font turned to a rotation, or
converted to another encoding.

The layout below was worked out from fonts the Editor made (docs/format.md,
Fonts, says from which). Numbers of more than one byte are little-endian.

A version 6 font is four parts, back to back:
  1. a 44-byte header. What the published notes alone say is marked
     "(notes)": the community notes by hagronnestad, which docs/format.md
     names.
       +0        always 4
       +1..2     ff 00. In a two-byte font, the gap in its second byte's
                 range: the last value before it, and how many values it
                 skips, as 7e 22 in big5 (ByteRange). (notes) In a big5
                 font, a low byte to skip, and how many.
       +3        the orientation: 0x0a at rotation 0, 0x0b at 90, 0x0c at 180,
                 0x0d at 270
       +4        the encoding, numbered as ENCODINGS numbers a project's:
                 1 for ascii, 3 for iso-8859-1
       +5        the font generator's Range choice, it seems: 0 in the fonts
                 of its "ASCII Character", 2 of its "Specified character",
                 and 1 in the others seen. (notes) The multi-byte mode: 0
                 for one byte, 1 for two bytes, 2 for a subset.
       +6        0: each character has its own width. (notes) Version 3
                 fonts store their one width here.
       +7        the height, in pixels; every glyph is this tall
       +8..9     0 in one-byte encodings. In a two-byte encoding, the first
                 and last value of a character's first byte.
       +10..11   the first and last character of the encoding: 20 and 7e in
                 ascii, 20 and ff in iso-8859-1, also in the iso-8859-1 font
                 of fewer characters seen. In a two-byte encoding, the first
                 and last value of the second byte.
       +12..15   the number of entries in the character table: 95 for ascii,
                 224 for iso-8859-1
       +16       the format version, 6
       +17       the length of the description
       +18..19   0
       +20..23   the number of bytes after the header
       +24..27   44: where the description starts
       +28..29   ff 00. In a two-byte font, the gap in its first byte's
                 range, as +1..2, as 9f 40 in shift-jis. (notes) As +1..2,
                 for the high byte.
       +30       1 in a smoothed font, 0 in one the generator made with
                 "Anti-aliasing of fonts" unticked, whose pixels are all
                 empty or full
       +31       1. (notes) 1 for a width per character, 0 for one width.
       +32       the length of the font's name, the description's first part
       +33       0. (notes) 1 when the glyphs' places count in units of 8
                 bytes, for fonts over 16 MB.
       +34..35   0
       +36..39   the number of characters the font holds: as +12..15, but in
                 a full utf-8 table (below). (notes) Fewer in a font
                 limited to a subset of its encoding.
       +40..43   0
  2. the description: the font's name, then its encoding's name, such as
     "Sans16iso-8859-1";
  3. the character table, 10 bytes per character, by increasing code: the
     encoding's every character, or those the generator was given. Zero
     bytes follow it up to the next multiple of 8 bytes from its start:
     two after 95 characters, none after 224. The table gives each glyph's
     place, so a reader needs neither fact.
       +0..1     the character's code: its byte, in a one-byte encoding
       +2        the advance: how far the pen moves right after it
       +3        the left overhang: the glyph's columns left of the pen
       +4        the right overhang: its columns past the advance
       +5..7     where its glyph starts, counted from the start of the table
       +8..9     the glyph's length in bytes
  4. the glyphs.

A font in utf-8 (encoding 24) has +8..11 at ff ff 00 ff, and an entry's
code is its character's code point. Its table is of one of two kinds:
  - a full table, which the generator writes for its Range choice "All
    characters": +12..15 is 65,536, an entry for every code point to
    U+FFFF, by code point, chosen or not. +33 is 1, and each glyph starts
    on a multiple of 8 bytes. +36..39 counts the characters chosen. A code
    point not chosen has code 0, an advance of half the height, and a glyph
    0 bytes long.
  - a table of chosen characters, which it writes for "ASCII Character"
    and "Specified character": laid out as a one-byte font's.

A font in a two-byte encoding, gb2312, big5, shift-jis, or
ks_c_5601-1987, as the Nextion Editor's font generator makes one, has +5 at
1, and its grid (_GRIDS) in +8..11, +1..2, and +28..29: the range of a
character's first byte, its row, and of its second, its column, each maybe
skipping a gap. gb2312's is a1 to f7 by a1 to fe, 87 rows of 94 positions.
Its table has an entry for every position, row by row, then for the 95
ascii characters, from the space to "~". An entry's code is its
character's two bytes, the first byte low, as stored, so a1 a2 is code
a2a1. The glyphs are laid out as a one-byte font's. The screen finds a
pair's entry by its place, counted from the table's first: the first
byte's index times the row's length, plus the second byte's, each index
counted from its range's first value, less the gap past it
(ByteRange.index), even for a byte outside its range (text_codes).

A glyph is a rectangle of pixels, as wide as the advance plus both
overhangs, and as tall as the font; its left edge lies the left overhang
before the pen. Each pixel has a coverage, from 0 (empty) to 7 (full): how
much of the text colour it takes. The pixels are one stream, row by row from
the top, each row from left to right, coded in bytes after a first byte that
says which codes follow:
  3 (eight levels):  000nnnnn  n empty         001nnnnn  n full
                     010nnnnn  n empty, 1 full 011nnnnn  n empty, 2 full
                     10nnnccc  n empty, 1 of coverage c
                     11cccddd  1 of coverage c, then 1 of coverage d
  1 (two levels):    the first four as above, then
                     100nnnnn  n empty, 3 full 101nnnnn  n empty, 4 full
                     11nnnmmm  n empty, m full
A run may go on into the next row.

At other rotations, the Editor turns the font as it enters the project. The
header changes only at +3 and +20..23, the table keeps its layout and the
upright character's advance and overhangs, and each glyph's stream then
runs:
  at 90:   column by column from the left, each column from the bottom up;
  at 180:  row by row from the bottom, each row from right to left: the
           upright stream reversed;
  at 270:  column by column from the right, each column from the top down.
A full utf-8 table is turned alike, but for U+0000, which has no glyph of its
own in a turned font: its entry keeps its glyph's length and gives the place
of the next glyph, U+0001's. No table of chosen characters seen held U+0000.
A two-byte font is turned as a one-byte font is, its table kept in its
order. Other versions have not been seen, and are refused.

Writing a font (encode_font) lays it out as the Editor does, and codes each
glyph as the Editor's fonts show it chooses, among the codes that could hold
the same pixels. Every glyph of the six fonts in tests/fixtures/fonts follows
these choices:
  - two levels when every pixel is empty or full; else eight;
  - a run of empty pixels gives runs of 31 first. The rest, r, then goes
    with what follows it: 1 or 2 full pixels, as "r empty, 1 (2) full"; in
    two levels, 3 or 4 full, as "r empty, 3 (4) full", or up to 7 full after
    at most 7 empty, as "n empty, m full"; in eight levels, a partial pixel
    after at most 7 empty, as "r empty, 1 of coverage c", unless the next
    pixel has the same coverage. Otherwise the r empty pixels are coded alone;
  - a run of full pixels gives runs of 31 first, then the rest alone, but a
    lone full pixel before a partial one, in eight levels, goes in a pair
    with it;
  - any other partial pixel goes in a pair with the next pixel, or, the last
    of the glyph, alone, as "0 empty, 1 of coverage c".
Written again, the six fonts come out as the Editor's, byte for byte, and so
do the fonts of tests/fixtures/fonts/utf-8 and
tests/fixtures/fonts/chosen-characters, upright and turned.
"""
from dataclasses import dataclass, field
from functools import cache
import struct

from nxwright import NxwrightError
from nxwright.project.device_settings import ENCODINGS, TextCodec, encoding_code
from nxwright.project.screen_copy import stored_order

HEADER_SIZE = 44
# Where the header keeps the length of the font's name, which follows it.
_NAME_LENGTH = 32
_ENTRY = struct.Struct("<HBBBHBH")      # code, advance, overhangs, place (low, high), length
_VERSION = 6
# The orientation byte: the rotation the font is stored at.
_ORIENTATIONS = {0x0a: 0, 0x0b: 90, 0x0c: 180, 0x0d: 270}
_ORIENTATION_BYTES = {rotation: byte for byte, rotation in _ORIENTATIONS.items()}
# The longest run a single code holds.
_MOST_RUN = 31
# A glyph's place is 3 bytes long.
_MOST_PLACE = 2 ** 24
UTF8 = "utf-8"


@dataclass(frozen=True)
class ByteRange:
    """The values one byte of a two-byte font's characters takes, the first
    byte or the second: from `low` to `high`, but for a gap of `gap` values
    after `before_gap`, as big5's second byte skips 7f to a0. The header
    stores `low` and `high` at +8..9 for the first byte and +10..11 for the
    second, and `before_gap` and `gap` at +28..29 and +1..2: ff 00 for no
    gap."""
    low: int
    high: int
    before_gap: int = 0xff
    gap: int = 0

    @property
    def size(self) -> int:
        """How many values the range has."""
        return self.high - self.low + 1 - self.gap

    def values(self) -> list:
        """The range's values, in order, but its gap."""
        return [value for value in range(self.low, self.high + 1)
                if not self.before_gap < value <= self.before_gap + self.gap]

    def index(self, value: int) -> int:
        """Where `value` falls among the range's values, as the screen counts
        it: from `low`, less the gap past `before_gap`. So a value in the gap
        counts back from the gap's end, and one outside the range falls
        outside 0 to size - 1."""
        return value - self.low - (self.gap if value > self.before_gap else 0)

    def described(self) -> str:
        """The range as a message gives it: "40 to fe, skipping 34 after 7e"."""
        text = "%02x to %02x" % (self.low, self.high)
        if not self.gap:
            return text
        return "%s, skipping %d after %02x" % (text, self.gap, self.before_gap)


# Encodings whose characters take two bytes, each with its grid: the
# ByteRange of a character's first byte, then of its second, as the Nextion
# Editor's font generator lays out a font of every character.
_GRIDS = {"gb2312": (ByteRange(0xa1, 0xf7), ByteRange(0xa1, 0xfe)),
          "big5": (ByteRange(0xa0, 0xf9), ByteRange(0x40, 0xfe, 0x7e, 0x22)),
          "shift-jis": (ByteRange(0x81, 0xef, 0x9f, 0x40), ByteRange(0x40, 0xfc, 0x7e, 0x01)),
          "ks_c_5601-1987": (ByteRange(0xa1, 0xc8), ByteRange(0xa1, 0xfe))}
# The two-byte encodings.
GRID_ENCODINGS = frozenset(_GRIDS)
# The encodings of one byte per character.
ONE_BYTE_ENCODINGS = frozenset(ENCODINGS.values()) - GRID_ENCODINGS - {UTF8}
# The encodings fonts are read, written, turned, converted, and made in from
# a typeface: every encoding a project can have.
FONT_ENCODINGS = ONE_BYTE_ENCODINGS | {UTF8} | GRID_ENCODINGS
# A font's header without a gap in a range: ff 00.
_NO_GAP = bytes([0xff, 0])
# A full utf-8 table has an entry for every code point to U+FFFF.
_UTF8_ENTRIES = 0x10000
# The header's first fields, which FontHeader holds, take its first 16 bytes.
_FIRST_FIELDS_SIZE = 16
# The space, where every one-byte font starts. The last character of ascii,
# whose fonts end at "~"; those of the other one-byte encodings end at ff.
_SPACE, _ASCII_LAST = 0x20, 0x7e
_EIGHT_LEVELS, _TWO_LEVELS = 3, 1


@dataclass
class Character:
    """One character of a font: its code, its advance, its overhangs, and its
    glyph, decoded when `coverages` is first asked for."""
    code: int
    advance: int
    left: int                  # columns of the glyph left of the pen
    right: int                 # columns past the advance
    _glyph: bytes = field(repr=False)
    _height: int = field(repr=False)
    _rotation: int = field(repr=False)    # the rotation it is stored at
    _coverages: list = field(default=None, repr=False)

    @property
    def width(self) -> int:
        """The glyph's width: the advance and both overhangs."""
        return self.advance + self.left + self.right

    def coverages(self) -> list:
        """Returns the glyph's coverages, 0 to 7, row by row from the top, each
        row from left to right, upright. Raises NxwrightError for a glyph that
        does not decode to exactly its rectangle."""
        if self._coverages is None:
            pixels = _decode_glyph(self._glyph, self.code)
            if len(pixels) != self.width * self._height:
                raise NxwrightError("character %d decodes to %d pixels, where its %d by %d "
                                    "glyph holds %d" % (self.code, len(pixels), self.width,
                                                        self._height, self.width * self._height))
            self._coverages = _upright(pixels, self.width, self._height, self._rotation)
        return self._coverages


@dataclass(frozen=True)
class Glyph:
    """One character to write: its code, its advance and overhangs, as a
    Character has them, and its coverages, 0 to 7, upright, row by row from
    the top, each row from left to right."""
    code: int
    advance: int
    left: int
    right: int
    coverages: tuple

    @property
    def width(self) -> int:
        """The glyph's width: the advance and both overhangs."""
        return self.advance + self.left + self.right


@dataclass
class Font:
    """A decoded font block."""
    name: str
    encoding: str              # a name of ENCODINGS
    height: int
    rotation: int              # the rotation it is stored at
    characters: dict           # {code: Character}; in utf-8, the chosen, by code point
    smoothed: bool
    # In a full utf-8 table, the advance it gives each code point to U+FFFF;
    # None in a table of chosen characters.
    advances: bytes = field(default=None, repr=False)
    # In a table of chosen characters, of a one-byte encoding or utf-8, and in
    # a two-byte font's, its first Character, which the screen draws for a
    # character it lacks; None in a full utf-8 table, and in a table of no
    # character.
    first_character: Character = field(default=None, repr=False)
    # In a two-byte font, its grid: the ByteRange of a character's first
    # byte, then of its second (_GRIDS); None in other fonts.
    grid: tuple = field(default=None, repr=False)

    def spans_of(self, data: bytes) -> list:
        """Returns [(start, length, Character)] of a two-byte font's text,
        `data`: where each character the screen draws starts in the bytes,
        how many it takes, one or two, and the Character drawn, as
        characters_of gives them. Raises NxwrightError for a font of no
        grid."""
        if self.grid is None:
            raise NxwrightError("font %s is not in a two-byte encoding" % self.name)
        return [(start, length, self.characters.get(code) or self._lacking(code))
                for start, length, code in _pair_spans(data, self.grid)]

    def characters_of(self, data: bytes) -> list:
        """Returns the Characters the screen draws for a text's bytes, `data`,
        in order.

        A font in utf-8 reads the bytes as utf-8, a character of one to four
        bytes; a two-byte font, as _pair_codes says; a font in another
        encoding, a character of each byte. The screen draws a character the
        font lacks as its table's first character, the space in a one-byte
        font, and so in a utf-8 table of chosen characters, a code point past
        U+FFFF among them. In a full utf-8 table, it draws a code point not
        chosen as nothing, at the advance its table entry gives, half the
        height, and one past U+FFFF the same. The first character is None
        only in a table of none.

        Raises NxwrightError for bytes that are not utf-8, in a font in utf-8."""
        return [self.characters.get(code) or self._lacking(code) for code in self._codes(data)]

    def lacking(self, data: bytes) -> list:
        """Returns the codes of the characters a text's bytes, `data`, hold
        that the font lacks, each once, in the order they come: bytes in a
        one-byte encoding, code points in utf-8, and in a two-byte font, a
        byte or a pair. Raises NxwrightError as characters_of does."""
        return list(dict.fromkeys(code for code in self._codes(data)
                                  if code not in self.characters))

    def _codes(self, data: bytes) -> list:
        """The codes of a text's bytes, as the font reads them (text_codes)."""
        try:
            return text_codes(data, self.encoding)
        except UnicodeDecodeError:
            raise NxwrightError("the text is not utf-8, which font %s reads" % self.name) from None

    def _lacking(self, code: int):
        """The Character the screen draws for a character the font does not
        hold: a table of chosen characters' first, or, in a full utf-8
        table, an empty one."""
        if self.advances is None:
            return self.first_character
        advance = self.advances[code] if code < len(self.advances) else self.height // 2
        return Character(code, advance, 0, 0, b"", self.height, self.rotation,
                         [0] * (advance * self.height))


@dataclass(frozen=True)
class FontFacts:
    """What a font block's header says, read without decoding the font, so
    for a font in any encoding: its name, encoding, the rotation it is stored
    at, height, whether it is smoothed, and how many characters its table
    holds."""
    name: str
    encoding: str              # a name of ENCODINGS
    rotation: int
    height: int
    smoothed: bool
    character_count: int


@dataclass
class FontHeader:
    """The fields of a font's header that its first 16 bytes hold, read for a
    font in any encoding, even one not known."""
    height: int
    first_character: int
    last_character: int
    character_count: int       # the characters of the encoding (+12)
    encoding: str              # a name of ENCODINGS, or None for one not known


def parse_font_header(block: bytes) -> FontHeader:
    """Returns the fields the start of a font block holds (the module's
    docstring lays them out). Raises NxwrightError when the block is too
    short to hold them."""
    if len(block) < _FIRST_FIELDS_SIZE:
        raise NxwrightError("font block is shorter than its header")
    count, = struct.unpack_from("<I", block, 12)
    return FontHeader(block[7], block[10], block[11], count, ENCODINGS.get(block[4]))


def read_font_header(path) -> FontHeader:
    """Returns the fields the start of the font file `path` holds, reading
    only them, however large the font. Raises OSError when the file cannot
    be read, and NxwrightError when it is too short to hold them."""
    with open(path, "rb") as file:
        return parse_font_header(file.read(_FIRST_FIELDS_SIZE))


def stored_name(block: bytes):
    """Returns the bytes of the name a font block's header stores, or None
    when the block is too short to hold the header and the whole name."""
    if len(block) < HEADER_SIZE:
        return None
    name = block[HEADER_SIZE:HEADER_SIZE + block[_NAME_LENGTH]]
    return name if len(name) == block[_NAME_LENGTH] else None


def font_facts(block: bytes) -> FontFacts:
    """Returns what a font block's header says (the module's docstring lays
    it out). Raises NxwrightError for a block shorter than the header and
    the name it stores, or whose encoding or orientation is not known."""
    name = stored_name(block)
    if name is None:
        raise NxwrightError("the font is shorter than its %d-byte header and the name it stores"
                            % HEADER_SIZE)
    encoding = ENCODINGS.get(block[4])
    if encoding is None:
        raise NxwrightError("the font's encoding %d is not known" % block[4])
    if block[3] not in _ORIENTATIONS:
        raise NxwrightError("the font's orientation 0x%02x is not known" % block[3])
    count, = struct.unpack_from("<I", block, 36)
    return FontFacts(name_text(name), encoding, _ORIENTATIONS[block[3]], block[7],
                     block[30] == 1, count)


def name_text(name: bytes) -> str:
    """Returns the text of the name a font block stores (stored_name). The
    Nextion Editor stores it in utf-8, whatever the font's encoding. A name
    that is no utf-8 is read as latin-1, as nxwright wrote names before."""
    try:
        return name.decode("utf-8")
    except UnicodeDecodeError:
        return name.decode("latin-1")


def decodes(block: bytes) -> bool:
    """Returns whether a font block is of the kind decode_font reads
    (_decodable_facts). Whether it is whole is another matter, which decoding
    it shows."""
    try:
        _decodable_facts(block)
    except NxwrightError:
        return False
    return True


def _decodable_facts(block: bytes) -> FontFacts:
    """Returns a font block's facts when it is of the kind decode_font reads:
    version 6, of every position of its grid in a two-byte encoding, with an
    orientation seen. Raises NxwrightError, naming what it found, for any
    other."""
    facts = font_facts(block)
    if block[16] != _VERSION:
        raise NxwrightError("the font is of version %d; only version %d is read"
                            % (block[16], _VERSION))
    # Byte 5 at 1 is the layout of every position, and the header's grid
    # (_header_grid) the generator's; nxwright reads no other layout or grid.
    grid = _GRIDS.get(facts.encoding)
    if grid is not None and block[5] != 1:
        raise NxwrightError("a font in %s of byte 5 at %d has not been seen; only one of every "
                            "position, byte 5 at 1, is read" % (facts.encoding, block[5]))
    if grid is not None and _header_grid(block) != grid:
        raise NxwrightError("a font in %s has a grid of %s by %s, where this one's is %s by %s"
                            % (facts.encoding, grid[0].described(), grid[1].described(),
                               *(byte_range.described() for byte_range in _header_grid(block))))
    return facts


def _header_grid(block: bytes) -> tuple:
    """The grid a two-byte font's header gives: the ByteRange of a
    character's first byte, from +8..9 and +28..29, then of its second, from
    +10..11 and +1..2."""
    return (ByteRange(block[8], block[9], block[28], block[29]),
            ByteRange(block[10], block[11], block[1], block[2]))


def decode_font(block: bytes) -> Font:
    """Decodes a font block's header and character table; each glyph is
    decoded when first asked for. Raises NxwrightError, naming what it found,
    for a block this module does not read: another version, a two-byte
    encoding but gb2312, an orientation not seen, a utf-8 table of chosen
    characters whose codes do not increase or that holds none, a gb2312
    table that does not hold every position and ascii character in order,
    or a table or glyph that runs past the block."""
    facts = _decodable_facts(block)
    height, rotation = facts.height, facts.rotation
    utf8 = facts.encoding == UTF8
    # A two-byte font's grid, which _decodable_facts checked bytes 8 to 11
    # give, and the codes its table holds in order.
    grid = _GRIDS.get(facts.encoding)
    expected = _table_codes_of(grid) if grid is not None else None
    # A one-byte font's table holds the characters the header counts. A
    # utf-8 font's counts its entries: a full table's, 65,536, are every
    # code point, chosen or not.
    count = struct.unpack_from("<I", block, 12)[0] if utf8 else facts.character_count
    full_table = utf8 and count == _UTF8_ENTRIES
    if utf8 and count == 0:
        raise NxwrightError("the font's table holds no character")
    if expected is not None and count != len(expected):
        raise NxwrightError("the font's table holds %d characters, where its grid and ascii "
                            "hold %d" % (count, len(expected)))
    table = HEADER_SIZE + block[17]
    if table + count * _ENTRY.size > len(block):
        raise NxwrightError("the font's character table runs past its end")
    # The glyphs' places count in bytes, or in units of 8 bytes when byte 33 is 1.
    unit = 8 if block[33] == 1 else 1
    characters, advances = {}, bytearray(count) if full_table else None
    entries = _ENTRY.iter_unpack(block[table:table + count * _ENTRY.size])
    previous = None
    for index, (code, advance, left, right, low, high, length) in enumerate(entries):
        if full_table:
            advances[index] = advance
            if length == 0:
                continue        # a code point not chosen
            if code != index:
                raise NxwrightError("the table entry of U+%04X gives character %d"
                                    % (index, code))
        elif utf8:
            # The screen searches a utf-8 table of chosen characters by code.
            if previous is not None and code <= previous:
                raise NxwrightError("the font's table lists U+%04X after U+%04X"
                                    % (code, previous))
            previous = code
        elif expected is not None and code != expected[index]:
            # The screen finds a two-byte font's entry by its place.
            raise NxwrightError("the table's entry %d gives %s, where %s goes"
                                % (index, _code_name(code), _code_name(expected[index])))
        start = table + (low | high << 16) * unit
        if start + length > len(block) or length < 1:
            raise NxwrightError("the glyph of character %d runs past the font's end" % code)
        # No text shows U+0000, as a 0 byte ends it, and its glyph is empty.
        # In a full table the Editor turned, its entry gives U+0001's glyph
        # (_utf8_layout), so it is not decoded.
        empty = [0] * ((advance + left + right) * height) if full_table and code == 0 else None
        characters[code] = Character(code, advance, left, right, block[start:start + length],
                                     height, rotation, empty)
    first = None if full_table else next(iter(characters.values()), None)
    return Font(facts.name, facts.encoding, height, rotation, characters, facts.smoothed,
                bytes(advances) if full_table else None, first, grid)


def text_codes(data: bytes, encoding: str) -> list:
    """Returns the codes a font in `encoding` reads a text's bytes, `data`,
    as (Font.characters_of): code points in utf-8; in a two-byte encoding,
    bytes and pairs (_pair_codes); in another, bytes. Raises
    UnicodeDecodeError for bytes that are not utf-8, in utf-8."""
    if encoding in _GRIDS:
        return _pair_codes(data, _GRIDS[encoding])
    if encoding == UTF8:
        return [ord(character) for character in data.decode(UTF8)]
    return list(data)


def counted_characters(data: bytes, encoding: str) -> list:
    """Returns a text's bytes, `data`, split into the characters the
    screen's text commands count, `strlen`, `substr`, and `-=`, each as its
    bytes. In utf-8, they are its characters, and in a one-byte encoding,
    its bytes.

    In a two-byte encoding, a byte above the lowest first byte of its grid
    takes the byte after it, or stands alone at the text's end. Any other
    byte is a character of its own. So gb2312's "　", a1 a1, counts as two
    characters, and shift-jis's half-width "ｱ", b1, takes the byte after it.
    The Nextion Editor's simulator counted so. Drawing takes every byte from
    80 as a pair's first instead (_pair_spans). big5's bound was seen only
    from a1, as its code page gives no first byte below it."""
    if encoding in _GRIDS:
        lowest = _GRIDS[encoding][0].low
        characters, index = [], 0
        while index < len(data):
            length = 2 if data[index] > lowest else 1
            characters.append(data[index:index + length])
            index += length
        return characters
    if encoding == UTF8:
        return [character.encode(UTF8, "surrogateescape")
                for character in data.decode(UTF8, "surrogateescape")]
    return [bytes([byte]) for byte in data]


def _pair_codes(data: bytes, grid: tuple) -> list:
    """The codes of a text's bytes in a two-byte font of `grid`, as the
    screen reads them (_pair_spans)."""
    return [code for _, _, code in _pair_spans(data, grid)]


def _pair_spans(data: bytes, grid: tuple) -> list:
    """Returns [(start, length, code)] of a text's bytes in a two-byte font
    of `grid`, as the screen reads them. A byte below 80 is a character of
    its own, and a byte from 80 the first of two. A pair's entry is the one
    its place falls on, counted from the table's first: the first byte's
    index times the row's length, plus the second byte's (ByteRange.index),
    even for a byte outside its range or in its gap. A place outside the
    table gives the pair's own code, which the font lacks, so it is drawn as
    the font's first character. A lone first byte at the text's end is no
    character: the screen draws nothing for it."""
    first, second = grid
    table = _grid_table(grid)
    spans, index = [], 0
    while index < len(data):
        byte = data[index]
        if byte < 0x80:
            spans.append((index, 1, byte))
            index += 1
            continue
        if index + 1 == len(data):
            break
        place = first.index(byte) * second.size + second.index(data[index + 1])
        spans.append((index, 2, table[place] if 0 <= place < len(table)
                      else byte | data[index + 1] << 8))
        index += 2
    return spans


@cache
def _grid_table(grid: tuple) -> tuple:
    """The codes of a two-byte font's table of `grid`, in order
    (_table_codes_of), kept for each grid."""
    return tuple(_table_codes_of(grid))


def grid_table_codes(encoding: str) -> list:
    """Returns the codes of a font's table in `encoding`, a two-byte encoding
    whose fonts nxwright reads (_GRIDS), in their order (_table_codes_of).
    Raises NxwrightError for another encoding."""
    if encoding not in _GRIDS:
        raise NxwrightError("a font in %s has no grid of two-byte characters" % encoding)
    return _table_codes_of(_GRIDS[encoding])


def _table_codes_of(grid: tuple) -> list:
    """Returns the codes of a two-byte font's table of `grid`, in order: every
    position, row by row, each row's columns in order, a range's gap left
    out, each code the character's two bytes, the first byte low, as the
    table stores it; then the ascii characters from the space to "~"."""
    first, second = grid
    columns = second.values()
    return ([row | column << 8 for row in first.values() for column in columns]
            + list(range(_SPACE, _ASCII_LAST + 1)))


def pair_name(code: int) -> str:
    """How a message names a two-byte character by its code (Font): its two
    bytes, in the order a text holds them, as a1 a2 for code a2a1."""
    return "%02x %02x" % (code & 0xff, code >> 8)


def _code_name(code: int) -> str:
    """How a message names a code of a two-byte font's table: a pair's two
    bytes (pair_name), or a one-byte character's byte, as 41."""
    return pair_name(code) if code > 0xff else "%02x" % code


def _upright(pixels: list, width: int, height: int, rotation: int) -> list:
    """Returns a glyph's coverages, stored at `rotation` in the order the
    screen stores a picture (screen_copy.stored_order), row by row from the
    top, each row from left to right."""
    upright = [0] * len(pixels)
    for stored, pixel in enumerate(stored_order(width, height, rotation)):
        upright[pixel] = pixels[stored]
    return upright


def _decode_glyph(glyph: bytes, code: int) -> list:
    """Returns the coverages of a glyph's stream, as stored."""
    levels = glyph[0]
    if levels not in (_EIGHT_LEVELS, _TWO_LEVELS):
        raise NxwrightError("the glyph of character %d starts with %d, not 1 or 3"
                            % (code, levels))
    pixels = []
    for byte in glyph[1:]:
        kind, value = byte >> 6, byte & 0x3f
        if kind == 0:
            pixels += [7 if value & 0x20 else 0] * (value & 0x1f)
        elif kind == 1:
            pixels += [0] * (value & 0x1f) + [7] * (2 if value & 0x20 else 1)
        elif levels == _EIGHT_LEVELS:
            if kind == 2:
                pixels += [0] * (value >> 3) + [value & 7]
            else:
                pixels += [value >> 3, value & 7]
        elif kind == 2:
            pixels += [0] * (value & 0x1f) + [7] * (4 if value & 0x20 else 3)
        else:
            pixels += [0] * (value >> 3) + [7] * (value & 7)
    return pixels


def encode_font(name: str, encoding: str, height: int, rotation: int, glyphs: list,
                smoothed: bool = True, full_table: bool = False) -> bytes:
    """Returns the font block of `glyphs`, Glyphs by increasing code, `height`
    pixels tall, in `encoding`, stored turned to `rotation`. In utf-8, the
    glyphs are the code points chosen, in a table of them alone, as the
    generator writes its "Specified character", or, with `full_table`, in a
    full table; the module's docstring lays out both. A one-byte font whose
    characters leave a gap is laid out as "Specified character" too, so that
    the screen finds a character by its code, not by its place. In a two-byte
    encoding, the glyphs are every position of its grid and the ascii
    characters, in the table's order (grid_table_codes). Its name is `name`.
    Its header says whether it is `smoothed`; one that is not holds only
    empty and full pixels. Raises NxwrightError for an encoding not known, a
    rotation that is not 0, 90, 180, or 270, a code past the encoding's
    last, a two-byte font lacking a position, a glyph whose coverages do not
    fill its rectangle with values from 0 to 7, or a partly covered pixel in
    a font that is not smoothed."""
    utf8 = encoding == UTF8
    grid = _GRIDS.get(encoding)
    code = encoding_code(encoding)
    orientation = _orientation_byte(rotation)
    if not 1 <= height <= 255:
        raise NxwrightError("height %d is not from 1 to 255" % height)
    # The Nextion Editor stores the name in utf-8, whatever the encoding.
    name_bytes = name.encode("utf-8")
    # The description, the name and the encoding's name, has a one-byte length.
    if len(name_bytes) + len(encoding) > 255:
        raise NxwrightError("the font's name is longer than %d bytes" % (255 - len(encoding)))
    codes = [glyph.code for glyph in glyphs]
    if grid is not None:
        if codes != _table_codes_of(grid):
            raise NxwrightError("a font in %s holds a glyph for every position of its grid, "
                                "row by row, then for each ascii character from the space"
                                % encoding)
    else:
        if codes != sorted(set(codes)) or not codes:
            raise NxwrightError("a font's characters go by increasing code, each once")
        last = _UTF8_ENTRIES - 1 if utf8 else 0xff
        outside = [code for code in (codes[0], codes[-1]) if not 0 <= code <= last]
        if outside:
            raise NxwrightError("character %d: a font in %s has codes from 0 to %d"
                                % (outside[0], encoding, last))
    if not smoothed:
        for glyph in glyphs:
            if not set(glyph.coverages) <= {0, 7}:
                raise NxwrightError("character %d has partly covered pixels, in a font that "
                                    "is not smoothed" % glyph.code)
    full = utf8 and full_table
    gapped = not utf8 and grid is None and codes != list(range(codes[0], codes[-1] + 1))
    description = name_bytes + encoding.encode("latin-1")
    body = description + _laid_out(glyphs, height, rotation, full)
    header = bytearray(HEADER_SIZE)
    header[0] = 4
    header[1:3] = header[28:30] = _NO_GAP
    # Byte 5 is 1, as the generator writes a font of every character of its
    # encoding and a full utf-8 table, the screen finding an entry by its
    # place; 2, as it writes "Specified character", the screen searching
    # the table by code, as a table leaving characters out needs.
    header[3], header[4] = orientation, code
    header[5] = 2 if gapped or (utf8 and not full) else 1
    header[7] = height
    if utf8:
        header[8:12] = b"\xff\xff\x00\xff"
        # A full table has an entry for every code point to U+FFFF, the
        # glyphs' places in units of 8 bytes; a table of chosen characters
        # one for each, the places in bytes.
        struct.pack_into("<I", header, 12, _UTF8_ENTRIES if full else len(glyphs))
        header[33] = 1 if full else 0
    elif grid is not None:
        # The grid: the range of a character's first byte, then of its
        # second, and the gap each skips (ByteRange).
        first, second = grid
        header[8:12] = bytes([first.low, first.high, second.low, second.high])
        header[1:3] = bytes([second.before_gap, second.gap])
        header[28:30] = bytes([first.before_gap, first.gap])
        struct.pack_into("<I", header, 12, len(glyphs))
    else:
        # Past a gap, the encoding's first and last character, as the
        # generator wrote its iso-8859-1 font of "Specified character".
        header[10], header[11] = ((_SPACE, _ASCII_LAST if encoding == "ascii" else 0xff)
                                  if gapped else (codes[0], codes[-1]))
        struct.pack_into("<I", header, 12, len(glyphs))
    header[16], header[17] = _VERSION, len(description)
    struct.pack_into("<I", header, 20, len(body))
    struct.pack_into("<I", header, 24, HEADER_SIZE)
    header[30:32] = bytes([smoothed, 1])
    header[32] = len(name_bytes)
    struct.pack_into("<I", header, 36, len(glyphs))
    return bytes(header) + body


def _orientation_byte(rotation: int) -> int:
    """Returns the orientation byte of a font stored at `rotation`. Raises
    NxwrightError for a rotation that is not 0, 90, 180, or 270."""
    if rotation not in _ORIENTATION_BYTES:
        raise NxwrightError("rotation %r is not 0, 90, 180, or 270" % rotation)
    return _ORIENTATION_BYTES[rotation]


def _laid_out(glyphs: list, height: int, rotation: int, full_table: bool) -> bytes:
    """Returns the character table and the glyphs of `glyphs`, Glyphs by
    increasing code, `height` pixels tall, stored at `rotation`: a full utf-8
    table (_utf8_layout) or a table of chosen characters (_chosen_layout).
    Raises NxwrightError for a glyph whose coverages do not fill its
    rectangle with values from 0 to 7, or whose codes are longer than its
    table entry holds."""
    streams = [_glyph_stream(glyph, height, rotation) for glyph in glyphs]
    for glyph, stream in zip(glyphs, streams):
        if len(stream) > 0xffff:
            raise NxwrightError("character %d's glyph is longer than its table entry holds"
                                % glyph.code)
    if full_table:
        table, glyph_bytes = _utf8_layout(glyphs, streams, height, rotation)
    else:
        table, glyph_bytes = _chosen_layout(glyphs, streams)
    return table + glyph_bytes


def _chosen_layout(glyphs: list, streams: list) -> tuple:
    """Returns (the character table, the glyphs' bytes) of a table of chosen
    characters, in a one-byte encoding or utf-8: an entry for each glyph,
    zero bytes up to the next multiple of 8 bytes from the table's start,
    then the glyphs back to back, each glyph's place counted in bytes from
    the table's start."""
    size = len(glyphs) * _ENTRY.size
    gap = bytes(-size % 8)
    table, place = bytearray(), size + len(gap)
    for glyph, stream in zip(glyphs, streams):
        if place + len(stream) >= _MOST_PLACE:
            raise NxwrightError("the font is too large for its character table")
        table += _ENTRY.pack(glyph.code, glyph.advance, glyph.left, glyph.right,
                             place & 0xffff, place >> 16, len(stream))
        place += len(stream)
    return bytes(table) + gap, b"".join(streams)


def _utf8_layout(glyphs: list, streams: list, height: int, rotation: int) -> tuple:
    """Returns (the character table, the glyphs' bytes) of a full utf-8 table:
    an entry for every code point to U+FFFF, then the glyphs, each on the next
    multiple of 8 bytes from the table's start, padded with zeros, its place
    counted in units of 8. A code point not chosen has code 0, half the
    height as its advance, and no glyph."""
    table = bytearray(_ENTRY.pack(0, height // 2, 0, 0, 0, 0, 0) * _UTF8_ENTRIES)
    glyph_bytes = bytearray()
    for glyph, stream in zip(glyphs, streams):
        glyph_bytes += bytes(-len(glyph_bytes) % 8)
        units = (len(table) + len(glyph_bytes)) // 8
        if units >= _MOST_PLACE:
            raise NxwrightError("the font is too large for its character table")
        _ENTRY.pack_into(table, glyph.code * _ENTRY.size, glyph.code, glyph.advance, glyph.left,
                         glyph.right, units & 0xffff, units >> 16, len(stream))
        # In a font the Editor turned, U+0000 has no glyph of its own: its
        # entry gives the next glyph's place.
        if glyph.code != 0 or rotation == 0:
            glyph_bytes += stream
    return bytes(table), bytes(glyph_bytes)


def two_byte_sample(name: str, encoding: str, height: int, glyphs: list,
                    smoothed: bool = True) -> Font:
    """Returns the Font of a two-byte font of which `glyphs` are a few of its
    positions, upright, the others not held: for a sample of a text, as
    writing every position (encode_font) would make it slow. It reads a
    text as the whole font does (text_codes). `glyphs` hold the table's
    first position, which it draws for a character it lacks. Raises
    NxwrightError for an encoding of no grid, a code outside the table, or
    `glyphs` without its first position."""
    table = grid_table_codes(encoding)
    positions = set(table)
    outside = [glyph.code for glyph in glyphs if glyph.code not in positions]
    if outside:
        raise NxwrightError("a font in %s has no position %s" % (encoding, _code_name(outside[0])))
    characters = {glyph.code: Character(glyph.code, glyph.advance, glyph.left, glyph.right, b"",
                                        height, 0, list(_checked(glyph, height)))
                  for glyph in glyphs}
    if table[0] not in characters:
        raise NxwrightError("a sample of a font in %s must hold its first position, %s"
                            % (encoding, _code_name(table[0])))
    return Font(name, encoding, height, 0, characters, smoothed, None, characters[table[0]],
                _GRIDS[encoding])


def turned_font(block: bytes, rotation: int) -> bytes:
    """Returns a font block written again, stored at `rotation`: its header
    kept but for the orientation and the length after it, its description
    kept, and its table laid out as before, a full utf-8 table or a table of
    chosen characters, each glyph turned. Raises NxwrightError for a block
    decode_font refuses, one whose glyph does not decode to its rectangle,
    and a rotation that is not 0, 90, 180, or 270."""
    font = decode_font(block)
    # A two-byte font's table goes by its grid, not by increasing code.
    characters = (font.characters.items() if font.grid is not None
                  else sorted(font.characters.items()))
    glyphs = [Glyph(code, character.advance, character.left, character.right,
                    tuple(character.coverages()))
              for code, character in characters]
    # Only a full utf-8 table gives every code point an advance.
    full_table = font.advances is not None
    header = bytearray(block[:HEADER_SIZE])
    header[3] = _orientation_byte(rotation)
    # Byte 33 says how the places count, which is the layout's: in units of
    # 8 bytes in a full table, in bytes in a table of chosen characters.
    header[33] = 1 if full_table else 0
    body = (block[HEADER_SIZE:HEADER_SIZE + block[17]]
            + _laid_out(glyphs, font.height, rotation, full_table))
    struct.pack_into("<I", header, 20, len(body))
    return bytes(header) + body


def converted_font(block: bytes, encoding: str, rotation: int) -> tuple:
    """Returns (the font block of `block`'s glyphs in `encoding`, stored at
    `rotation`, the code points of the characters left out). Each glyph is
    keyed by the character its code stands for in the font's encoding, as
    the folder's texts read it (TextCodec): a two-byte font's position, as
    its code page has it, GBK for gb2312. In a one-byte encoding or utf-8,
    it is written as a table of chosen characters (encode_font), which the
    screen searches by code. In a two-byte encoding, it goes to its
    character's position, and every other position is empty, as wide as the
    font is tall, as a two-byte font holds every one. A character
    `encoding` lacks, or its grid has no place for, is left out, and so is
    one below the space, where a one-byte font and a two-byte font's ascii
    start. A code that stands for no character of the font's encoding is
    left out too, unnamed, as no text holds it.

    Raises NxwrightError as decode_font does, for an `encoding` not known,
    and for a font none of whose characters `encoding` has."""
    font = decode_font(block)
    old_codec, new_codec = TextCodec(font.encoding), TextCodec(encoding)
    grid = _GRIDS.get(encoding)
    positions = set(_grid_table(grid)) if grid is not None else None
    glyphs, left_out = [], []
    for code, character in sorted(font.characters.items()):
        if font.encoding == UTF8:
            text = chr(code)
        else:
            try:
                text = old_codec.decode(_code_bytes(code), "the font")
            except NxwrightError:
                continue
        if encoding == UTF8:
            new_code = ord(text)
        else:
            try:
                new_code = _code_of_bytes(new_codec.encode(text, "the font"), positions)
            except NxwrightError:
                new_code = None
            if new_code is None:
                left_out.append(ord(text))
                continue
        glyphs.append(Glyph(new_code, character.advance, character.left, character.right,
                            tuple(character.coverages())))
    if not glyphs:
        raise NxwrightError("none of its characters is in %s" % encoding)
    if grid is not None:
        held = {glyph.code: glyph for glyph in glyphs}
        empty = (0,) * (font.height * font.height)
        glyphs = [held.get(code) or Glyph(code, font.height, 0, 0, empty)
                  for code in _grid_table(grid)]
    else:
        glyphs.sort(key=lambda glyph: glyph.code)
    return (encode_font(font.name, encoding, font.height, rotation, glyphs, font.smoothed),
            left_out)


def _code_bytes(code: int) -> bytes:
    """The bytes a text holds for a code of a font's table: a pair's two,
    the first low in its code, or a one-byte character's byte."""
    return bytes([code & 0xff, code >> 8]) if code > 0xff else bytes([code])


def _code_of_bytes(data: bytes, positions) -> int:
    """The code of a font's table a character's bytes in its encoding take:
    in a one-byte encoding, its byte from the space; in a two-byte one, of
    the table's `positions`, its pair or its ascii byte. None for bytes the
    table has no place for."""
    code = data[0] | data[1] << 8 if len(data) == 2 else data[0] if len(data) == 1 else None
    if code is None or code < _SPACE:
        return None
    if positions is not None:
        return code if code in positions else None
    return code if len(data) == 1 else None


def _glyph_stream(glyph: Glyph, height: int, rotation: int) -> bytes:
    """Returns a glyph's bytes, stored at `rotation` (_glyph_codes), after
    checking it (_checked). An empty glyph, as a gb2312 font's empty
    positions are by the thousand, is coded at once: its stream, runs of
    empty pixels, is the same at every rotation."""
    size = _checked_size(glyph, height)
    if glyph.coverages.count(0) == size:
        return _empty_codes(size)
    return _glyph_codes(_turned(_checked(glyph, height), glyph.width, height, rotation))


def _empty_codes(count: int) -> bytes:
    """The bytes of a glyph of `count` empty pixels, as _glyph_codes codes
    them: two levels, then runs of _MOST_RUN empty pixels, then the rest."""
    if count == 0:
        return bytes([_TWO_LEVELS])
    runs, rest = divmod(count - 1, _MOST_RUN)
    return bytes([_TWO_LEVELS] + [_MOST_RUN] * runs + [rest + 1])


def _checked(glyph: Glyph, height: int) -> tuple:
    """Returns a glyph's coverages, after checking they fill its rectangle with
    values from 0 to 7."""
    _checked_size(glyph, height)
    wrong = [value for value in glyph.coverages if value not in range(8)]
    if wrong:
        raise NxwrightError("character %d has a coverage of %r" % (glyph.code, wrong[0]))
    return glyph.coverages


def _checked_size(glyph: Glyph, height: int) -> int:
    """Returns the number of a glyph's pixels, after checking its advance and
    overhangs each fit a byte, and its coverages fill its rectangle."""
    if not all(0 <= value <= 255 for value in (glyph.advance, glyph.left, glyph.right)):
        raise NxwrightError("character %d: its advance and overhangs must each fit a byte"
                            % glyph.code)
    size = glyph.width * height
    if len(glyph.coverages) != size:
        raise NxwrightError("character %d has %d coverages, where its %d by %d glyph holds %d"
                            % (glyph.code, len(glyph.coverages), glyph.width, height, size))
    return size


def _turned(pixels: tuple, width: int, height: int, rotation: int) -> list:
    """Returns upright coverages in the order of a glyph stored at
    `rotation`: the reverse of _upright."""
    return [pixels[pixel] for pixel in stored_order(width, height, rotation)]


def _glyph_codes(pixels: list) -> bytes:
    """Returns a glyph's bytes for its stream of coverages, coded as the
    module's docstring says the Editor codes one."""
    two_levels = set(pixels) <= {0, 7}
    out = [_TWO_LEVELS if two_levels else _EIGHT_LEVELS]
    position, count = 0, len(pixels)

    def run_of(value: int) -> int:
        end = position
        while end < count and pixels[end] == value:
            end += 1
        return end - position

    while position < count:
        pixel = pixels[position]
        if pixel == 0:
            empty = run_of(0)
            position += empty
            while empty > _MOST_RUN:
                out.append(_MOST_RUN)
                empty -= _MOST_RUN
            following = pixels[position] if position < count else None
            full = run_of(7) if following == 7 else 0
            if full in (1, 2):
                out.append((0x40 if full == 1 else 0x60) | empty)
                position += full
            elif two_levels and full in (3, 4):
                out.append((0x80 if full == 3 else 0xa0) | empty)
                position += full
            elif two_levels and full and empty <= 7 and full <= 7:
                out.append(0xc0 | empty << 3 | full)
                position += full
            # A partial pixel followed by an equal one is left to go in a pair
            # with it.
            elif (not two_levels and following not in (None, 0, 7) and empty <= 7
                  and pixels[position + 1:position + 2] != [following]):
                out.append(0x80 | empty << 3 | following)
                position += 1
            else:
                out.append(empty)
        elif pixel == 7:
            full = run_of(7)
            while full > _MOST_RUN:
                out.append(0x20 | _MOST_RUN)
                position += _MOST_RUN
                full -= _MOST_RUN
            following = pixels[position + full] if position + full < count else None
            if not two_levels and full == 1 and following not in (None, 0):
                out.append(0xc0 | 7 << 3 | following)
                position += 2
            else:
                out.append(0x20 | full)
                position += full
        elif position + 1 < count:
            out.append(0xc0 | pixel << 3 | pixels[position + 1])
            position += 2
        else:
            out.append(0x80 | pixel)
            position += 1
    return bytes(out)
