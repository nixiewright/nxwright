"""Reading a TFT file: the file the Nextion Editor's File > TFT file output
writes, and a Nextion screen runs (ResearchNotes/tft/tft-files.md).

A TFT file has five parts, back to back:

  - header 1, 0xC8 bytes, ending with its checksum;
  - header 2, 0xC8 bytes from 0xC8: 49 words, then their checksum. On T, K,
    P, and E, the first 19 are XORed with a key, and the others hold
    0xFFFFFFFF as stored. On F, every word is scrambled (encode_f_header_2);
  - 0xFF up to the section size, then the firmware and resources section: a
    table of 12 rows, then the firmware files, the pictures, and the fonts,
    and on P and E the animations, videos, and sounds, then zeros up to a
    multiple of the section size;
  - the user code, the part made from the project;
  - the file's checksum, its last 4 bytes.

Every checksum is the CRC of nxwright's stamps (project/stamp.py), in
one of two forms. The byte form feeds each byte as one 32-bit word. The word
form feeds 32-bit little-endian words.

The user code, as UserCode gives it, is the form every part of nxwright reads and
writes. Header 2 gives the places of its parts, counted from its start:

  - its blocks, up to 0xC8. A block is a 4-byte size, then that many bytes,
    and a 0 word ends a run of them. The first block comes first, then
    program.s's code, ended by a 0 word, then each of the project's macros,
    each ended by a 0 word, then each page's blocks;
  - from 0xC8 to 0xCC, nothing in every file seen;
  - from 0xCC to 0xD4, the int variables of program.s, 12 bytes each;
  - from 0xD4, the pages' data, each page's where its entry in the page index
    says;
  - from header 1's 0x58, the macros' table, 8 bytes a macro: the CRC of its
    name, then the place of its first block (ResearchNotes/tft/macros.md). A
    project without macros has none, and 0x58 gives the page index's place;
  - the page index, 16 bytes a page, or 12 before 1.63 (Layout), from 0xE0
    to 0xE4;
  - the object records, up to the file's checksum.

A page's entry in the page index holds, as seen: the number of objects on
the pages before it, and its own number of objects, two 2-byte numbers; the
place of its objects' table, a block of its own; the place of its data; and
a 4-byte number, on T the page's memory (ResearchNotes/tft/text-component.md).
The entries are in page ID order, so a page's ID is its entry's place in
the index. A page's blocks run up to the 0 word after its objects' table.
"""
from dataclasses import dataclass, field
import struct
from typing import Optional

from nxwright import NxwrightError
from nxwright.project.media_files import screen_crc

from nxwright.tft.firmware_versions import version_text

# A series as header 1's byte 0x15 stores it, as the project file's manifest
# does (project/screen_models.py).
SERIES = {0: "T", 1: "K", 3: "P", 6: "E", 100: "F"}
# The series whose section and file checksums are in the word form.
_WORD_FORM_SERIES = ("P", "E")

HEADER_1_SIZE = 0xC8
HEADER_2_END = 0x190
_HEADER_1_CHECKSUM = 0xC4
_HEADER_2_CHECKSUM = 0x18C
HEADER_2_WORDS = 49
# The words the key covers, 0x0C8 to 0x113. The others hold 0xFFFFFFFF as
# stored, on T, K, P, and E.
_KEYED_WORDS = 19
_KEY_CONSTANT = 0x5EE18C33
# The constants of F's scramble of header 2 (encode_f_header_2), the same on
# every F model.
_F_SCHEDULE = (0xCE, 0x21, 0x5E, 0x20, 0xE4, 0xE4, 0xFA, 0xC5)
_F_K_A, _F_K_B, _F_K_D = 0xC4, 0x20, 0x02
_F_B0, _F_D0 = 0x124F6584, 0x7BAD3BBF
_M32, _M31 = 0xFFFFFFFF, 0x7FFFFFFF
_FILE_CHECKSUM_CONSTANT = 0x4E
_DEVICE_ID = 0x2E

TABLE_ROWS = 12
TABLE_SIZE = 0x90
PAGE_INDEX_ENTRY_SIZE = 16
# A page's entry before 1.63: the same fields but the page's memory (IndexEntry).
_SHORT_INDEX_ENTRY = struct.Struct("<HHII")
VARIABLE_SIZE = 12
# A macro's entry in the macros' table: the CRC of its name, then its place.
MACRO_ENTRY_SIZE = 8
# A place and a count an older Nextion Editor gives as unset (Layout).
_UNSET_PLACE, _UNSET_COUNT = 0xFFFFFFFF, 0xFFFF

# The firmware files of rows 1 to 6 of the section's table, by series. Row 0
# is input.bin on every series, row 7 the pictures, and row 8 the fonts.
_FIRMWARE_FILES = {
    "T": ("asp0.dll", "cd0.dll", "qr0.bin", "syscom.bin", "h0-0.dll", "h1-0.dll"),
    "K": ("asp1.dll", "cd1.dll", "qr0.bin", "syscom.bin", "h0-1.dll", "h1-1.dll"),
    "F": ("asp100.dll", "cd100.dll", "qr0.bin", "syscom.bin", "h0-100.dll", "h1-100.dll"),
    "P": ("3.cc", "cdx.dll"),
    "E": ("6.cc", "cdx.dll"),
}

# Header 1's fields, as (place, size, what it holds), for naming a place.
HEADER_1_FIELDS = (
    (0x00, 1, "0"),
    (0x01, 2, "the Nextion Editor's version, its first two numbers"),
    (0x03, 1, "N"),
    (0x04, 4, "the main firmware file's place, plus its value at offset 1"),
    (0x08, 4, "the main firmware file's value at offset 5"),
    (0x0C, 4, "the screen's width and height, the longer side first"),
    (0x10, 4, "the screen's width and height"),
    (0x14, 1, "the rotation"),
    (0x15, 1, "the series code"),
    (0x16, 1, "the one-time update"),
    (0x17, 1, "the Nextion Editor's version, its third number"),
    (0x18, 4, "the second firmware file's place"),
    (0x1C, 2, "0"),
    (0x1E, 4, "the second firmware file's place again, on T, K, and F"),
    (0x22, 4, "the second firmware file's size"),
    (0x26, 4, "the main firmware file's place, on T, K, and F"),
    (0x2A, 4, "the main firmware file's size, on T, K, and F"),
    (0x2E, 4, "the device ID"),
    (0x32, 2, "0x21"),
    (0x34, 4, "the section size"),
    (0x38, 4, "0x0C"),
    (0x3C, 4, "the file's size"),
    (0x40, 4, "the firmware and resources section's size"),
    (0x44, 4, "that section's checksum"),
    (0x48, 4, "the memory file storage size, on P and E"),
    (0x4C, 8, "0xFF"),
    (0x54, 4, "0"),
    (0x58, 4, "the macros' table's place, counted from the user code's start"),
    (0x5C, 0x12, "0"),
    (0x6E, 2, "the number of macros"),
    (0x70, 0x54, "0xFF"),
    (0xC4, 4, "header 1's checksum"),
)

# Header 2's words, once the key is removed, by place.
HEADER_2_FIELDS = {
    0xC8: "where the user code's blocks end",
    0xCC: "where the int variables start, in the user code",
    0xD0: "the number of int variables",
    0xD4: "where the int variables end, in the user code",
    0xD8: "the section's place",
    0xDC: "the user code's place",
    0xE0: "the page index's place",
    0xE4: "where the page index ends",
    0xE8: "the pictures' place, or 0 when they are left out",
    0xEC: "on P and E, the place of row 9 of the section's table",
    0xF0: "on P and E, the place of row 10 of the section's table",
    0xF4: "on P and E, the place of row 11 of the section's table",
    0xF8: "the fonts' place, or 0 when they are left out",
    0xFC: "the first block's size, with its size word",
    0x100: "the number of pages, then the number of objects",
    0x104: "the number of pictures, then the number of animations, 2 bytes each",
    0x108: "the number of videos, then the number of sounds, 2 bytes each",
    0x10C: "the number of fonts",
    0x110: "3 in every file seen",
}
HEADER_2_FIELDS.update({HEADER_1_SIZE + 4 * number: "0xFFFFFFFF, without the key"
                        for number in range(_KEYED_WORDS, HEADER_2_WORDS)})


@dataclass(frozen=True)
class Layout:
    """How the Nextion Editors from the version `oldest` on, up to the
    oldest version of the newer layout after it, write a TFT file, where
    they write it otherwise than 1.68.2
    (ResearchNotes/tft/older-editors.md):

    - `macros_unset`: with no macros, header 1 gives the macros' table's
      place as 0xffffffff and their number as 0xffff, where 1.68.2 gives
      the page index's place and 0;
    - `first_blocks`: how many blocks start the user code before program.s's,
      whose size, with their size words, header 2's 0xFC gives. 1.68.2
      writes one;
    - `second_firmware_optional`: on P and E, the file may hold no second
      firmware file, its row of the section's table empty, and header 1's
      0x18 then 0;
    - `page_index_entry`: the size of a page's entry in the page index,
      PAGE_INDEX_ENTRY_SIZE, or 12 bytes before 1.63, without the last
      field, the page's memory (IndexEntry)."""
    oldest: tuple
    macros_unset: bool
    first_blocks: int
    second_firmware_optional: bool
    page_index_entry: int = PAGE_INDEX_ENTRY_SIZE


# The oldest release of the Nextion Editor whose files read_tft reads, and
# the oldest one probed. read_tft refuses a file made by any older release.
# The files seen that were made by the Nextion Editors 0.47 to 0.53 are laid
# out differently from header 1 on (ResearchNotes/tft/older-editors.md).
OLDEST_VERSION_READ = (1, 60, 1)
# Each layout, the newest first. A file takes the first whose `oldest` its
# version is not before, so a version no file has shown takes the layout of
# the newest one before it. The releases before 1.68.1 have no cdx.dll, P's
# second firmware file, so the files they make for P have none.
LAYOUTS = (Layout((1, 68, 2), False, 1, False), Layout((1, 68, 1), True, 1, False),
           Layout((1, 65, 0), True, 1, True), Layout((1, 63, 0), True, 3, True),
           Layout(OLDEST_VERSION_READ, True, 2, True, page_index_entry=_SHORT_INDEX_ENTRY.size))


def layout_of(version: tuple) -> Layout:
    """Returns the Layout of a file of the Nextion Editor's `version`, as
    header 1 gives it, such as (1, 63, 3). `version` must not be before
    OLDEST_VERSION_READ."""
    return next(layout for layout in LAYOUTS if tuple(version) >= layout.oldest)


class TftFileError(NxwrightError):
    """A TFT file that cannot be read, or whose checksums or sizes do not hold."""


def device_id_of(data: bytes):
    """Returns the device ID that header 1 of the TFT file `data` gives, the
    model's (nxwright's screen_models.model_with_id), or None when `data` is
    too short to give one. Its place is the same in every file nxwright has
    read, from the Nextion Editor 1.60.1 on."""
    if len(data) < _DEVICE_ID + 4:
        return None
    return data[_DEVICE_ID:_DEVICE_ID + 4]


def byte_form_crc(data: bytes) -> int:
    """Returns the stamp CRC of `data` in its byte form, each byte fed as one
    32-bit word, as nxwright's stamp.word_crc(CRC_START, data) computes it.
    It goes through media_files.screen_crc, with each byte spread over a
    little-endian word, which is many times faster."""
    spread = bytearray(4 * len(data))
    spread[0::4] = data
    return screen_crc(bytes(spread))


def series_crc(data: bytes, series: str) -> int:
    """Returns the CRC of `data` in the form `series` uses for its section and
    its file: the word form on P and E (media_files.screen_crc), the byte form
    on the others."""
    return screen_crc(data) if series in _WORD_FORM_SERIES else byte_form_crc(data)


def header_2_key(device_id: bytes, series: str):
    """Returns the key header 2's words are XORed with: the byte-form CRC of
    the device ID, XORed with 0x5EE18C33. None on F, whose header 2 is
    scrambled another way (encode_f_header_2)."""
    if series == "F":
        return None
    return byte_form_crc(device_id) ^ _KEY_CONSTANT


def encode_f_header_2(device_id: bytes, words: list) -> list:
    """Returns the stored form of header 2's plain `words` on F, from word 0
    on, for a screen whose header 1 gives `device_id`. Up to HEADER_2_WORDS
    words. Each word goes through three rounds, whose keys depend only on
    the device ID and the word's place. The rounds were found by a bit-level
    parity analysis of the words the Nextion Editor stored, then a Z3 solve,
    and checked on words and models the solve did not use
    (ResearchNotes/tft/f-series-header-2.md)."""
    stored = []
    for plain, (keys, partners) in zip(words, _f_header_2_rounds(device_id, len(words))):
        v = plain
        for key, partner in zip(keys, partners):
            v = ((v ^ key) + key + partner) & _M32
        stored.append(v)
    return stored


def decode_f_header_2(device_id: bytes, stored: list) -> list:
    """Returns the plain words of header 2's `stored` words on F, undoing
    encode_f_header_2. Each round is undone, the last first."""
    words = []
    for value, (keys, partners) in zip(stored, _f_header_2_rounds(device_id, len(stored))):
        v = value
        for key, partner in reversed(list(zip(keys, partners))):
            v = ((v - key - partner) & _M32) ^ key
        words.append(v)
    return words


def _f_header_2_rounds(device_id: bytes, count: int) -> list:
    """Returns each word's three keys and their partners, for `count` words."""
    if len(device_id) != 4:
        raise ValueError("a device ID is 4 bytes, not %d" % len(device_id))
    if count > HEADER_2_WORDS:
        raise ValueError("header 2 has %d words, not %d" % (HEADER_2_WORDS, count))
    a = int.from_bytes(device_id, "little")
    b, d = _F_B0, _F_D0
    rounds = []
    for i in range(count):
        s = _F_SCHEDULE[i % 8]
        partners = (a, b, d)
        key_0 = (a + b + (d << (s & 7))) & _M32
        a = _add_byte((a << 1) & _M32, s ^ _F_K_A, 0)
        key_1 = (a + b + d) & _M32
        b = _add_byte((b << 2) & _M32, s ^ _F_K_B, 8 * (3 - (s & 3)))
        # Key 2 adds the count, 4 for each word from 2 on, then flips every bit but the top one.
        key_2 = (((((a + b) & _M32) ^ d) + 4 * (i + 2)) & _M32) ^ _M31
        d = _add_byte((d << 3) & _M32, s ^ _F_K_D, 8 * (3 - (s & 3)))
        rounds.append(((key_0, key_1, key_2), partners))
    return rounds


def _add_byte(value: int, byte: int, place: int) -> int:
    """Returns `value` with `byte` added to its 8 bits from bit `place`,
    modulo 256, so that no carry reaches the bits above."""
    added = ((value >> place) + byte) & 0xFF
    return (value & ~(0xFF << place) & _M32) | (added << place)


def file_checksum(body: bytes, device_id: bytes, series: str) -> int:
    """Returns the checksum a TFT file ends with, given `body`, every byte
    before it (file_checksum_from_crc)."""
    return file_checksum_from_crc(series_crc(body, series), len(body) + 4, device_id)


def file_checksum_from_crc(crc: int, file_size: int, device_id: bytes) -> int:
    """Returns the checksum a TFT file of `file_size` bytes ends with, given
    `crc`, the series_crc of every byte before it. It is `crc`, its low byte
    XORed with the low byte of the file's size, the device ID's first byte,
    and 0x4E. This held for seven models over the five series, at 0 and 90
    degrees."""
    return crc ^ ((file_size ^ device_id[0] ^ _FILE_CHECKSUM_CONSTANT) & 0xFF)


def encode_blocks(blocks: list) -> bytes:
    """Returns `blocks` as the user code stores them: each its 4-byte size,
    then its bytes. An empty block is a 0 word."""
    return b"".join(struct.pack("<I", len(block)) + block for block in blocks)


def split_blocks(data: bytes):
    """Returns the blocks `data` holds, back to back, each without its size
    word, an empty one for each 0 word; or None when their sizes do not end
    exactly at the end of `data`."""
    blocks, at = [], 0
    while at < len(data):
        if at + 4 > len(data):
            return None
        size = struct.unpack_from("<I", data, at)[0]
        if at + 4 + size > len(data):
            return None
        blocks.append(data[at + 4:at + 4 + size])
        at += 4 + size
    return blocks


@dataclass(frozen=True)
class IndexEntry:
    """A page's entry in the page index. `objects_before` counts the objects
    on the pages before it, pages included. `table_place` and `data_place`
    are counted from the user code's start. `memory` is, on T, the page's
    memory: its 8 bytes, its components', and 4. An entry of 12 bytes, of a
    Nextion Editor before 1.63, has no `memory`: it is None."""
    objects_before: int
    objects: int
    table_place: int
    data_place: int
    memory: Optional[int]

    @classmethod
    def from_bytes(cls, entry: bytes) -> "IndexEntry":
        if len(entry) == _SHORT_INDEX_ENTRY.size:
            return cls(*_SHORT_INDEX_ENTRY.unpack(entry), None)
        return cls(*struct.unpack("<HHIII", entry))


@dataclass
class UserCode:
    """The user code, split into the parts the module's docstring describes.
    `blocks` is every block up to header 2's 0xC8, each without its size word,
    an empty one for each 0 word. `macros` is the macros' table, which lies
    between `data` and `page_index`. `index_entry_size` is the size of a
    page's entry in `page_index`, as the file's layout gives it
    (Layout.page_index_entry)."""
    blocks: list
    after_blocks: bytes
    variables: bytes
    data: bytes
    page_index: bytes
    records: bytes
    macros: bytes = b""
    index_entry_size: int = PAGE_INDEX_ENTRY_SIZE

    def to_bytes(self) -> bytes:
        """Returns the user code as a TFT file stores it."""
        return (encode_blocks(self.blocks) + self.after_blocks + self.variables + self.data
                + self.macros + self.page_index + self.records)

    def places(self) -> dict:
        """Returns {part: (start, end)}, counted from the user code's start,
        for its parts in order: "blocks", "after the blocks", "variables",
        "data", "macros", "page index", and "records". Header 2's 0xC8 is
        where "after the blocks" starts, 0xCC where "variables" starts, 0xD4
        where it ends, and 0xE0 and 0xE4 are where "page index" starts and
        ends. Header 1's 0x58 is where "macros" starts."""
        places, at = {}, 0
        for name, size in (("blocks", len(encode_blocks(self.blocks))),
                           ("after the blocks", len(self.after_blocks)),
                           ("variables", len(self.variables)), ("data", len(self.data)),
                           ("macros", len(self.macros)), ("page index", len(self.page_index)),
                           ("records", len(self.records))):
            places[name] = (at, at + size)
            at += size
        return places

    def block_places(self) -> list:
        """Returns where each block's size word is, from the user code's start."""
        places, at = [], 0
        for block in self.blocks:
            places.append(at)
            at += 4 + len(block)
        return places

    def macro_places(self) -> list:
        """Returns the places of the macros' first blocks, from the user
        code's start, in the macros' table's order."""
        return [struct.unpack_from("<I", self.macros, at + 4)[0]
                for at in range(0, len(self.macros) - MACRO_ENTRY_SIZE + 1, MACRO_ENTRY_SIZE)]

    def index_entries(self) -> list:
        """Returns the page index's entries, in order."""
        size = self.index_entry_size
        return [IndexEntry.from_bytes(self.page_index[at:at + size])
                for at in range(0, len(self.page_index) - size + 1, size)]

    def block_parts(self) -> list:
        """Returns the part each block belongs to, in order: "first block",
        "program.s", "macros", or "page N" (N its page ID), from the page
        index. Blocks the page index does not place, as after a page whose
        objects' table is not where its entry says, are "pages".

        program.s ends at its first 0 word, or, in a project with macros,
        before the first macro's block (macro_places). The macros end at the
        first 0 word after the last macro's first block. So a `return`, a 0
        word, in program.s without macros or in the last macro, ends its part
        early, and the blocks after it are named after the next part."""
        parts = ["first block"] if self.blocks else []
        at = 1
        starts = {place: number for number, place in enumerate(self.block_places())}
        macros = sorted(starts.get(place, len(self.blocks)) for place in self.macro_places())
        while at < len(self.blocks) and (not macros or at < macros[0]):
            parts.append("program.s")
            at += 1
            if not macros and not self.blocks[at - 1]:
                break
        if macros:
            end = next((number for number in range(macros[-1], len(self.blocks))
                        if not self.blocks[number]), len(self.blocks) - 1)
            parts.extend(["macros"] * (end + 1 - at))
            at = end + 1
        for page, entry in enumerate(self.index_entries()):
            table = starts.get(entry.table_place)
            if table is None or table < at:
                break
            end = next((number for number in range(table, len(self.blocks))
                        if not self.blocks[number]), None)
            if end is None:
                break
            parts.extend(["page %d" % page] * (end + 1 - at))
            at = end + 1
        return parts + ["pages"] * (len(self.blocks) - len(parts))

    def page_data(self) -> list:
        """Returns each page's data, in the page index's order, or None when
        the entries' data places do not split `data` from its start."""
        start = self.places()["data"][0]
        places = [entry.data_place - start for entry in self.index_entries()] + [len(self.data)]
        if places[0] != 0 or places != sorted(places):
            return None
        return [self.data[places[n]:places[n + 1]] for n in range(len(places) - 1)]


@dataclass(frozen=True)
class TableRow:
    """A row of the section's table: the place of its part in the section,
    its size, and what it holds."""
    place: int
    size: int
    name: str


@dataclass
class TftFile:
    """A TFT file, split into its parts. `header_2_words` are header 2's 49
    plain words: with the key removed, or on F unscrambled. `user_code` is
    None when the user code could not be split, and `user_code_bytes` always
    holds it whole. `problems` lists each checksum, size, or place the file
    states that does not hold, in words."""
    where: str
    data: bytes
    series: str
    header_2_words: list
    section_place: int
    table: list
    user_code_place: int
    user_code: UserCode
    problems: list = field(default_factory=list)

    @property
    def version(self) -> tuple:
        """The Nextion Editor's version that wrote the file, as header 1 gives
        it: (1, 68, 2) for the Nextion Editor 1.68.2."""
        return _version_of(self.data)

    @property
    def layout(self) -> Layout:
        """The Layout of the file, by its version (layout_of)."""
        return layout_of(self.version)

    @property
    def device_id(self) -> bytes:
        return device_id_of(self.data)

    @property
    def user_code_bytes(self) -> bytes:
        return self.data[self.user_code_place:len(self.data) - 4]

    def header_1_value(self, place: int) -> int:
        """Returns header 1's 4-byte value at `place`."""
        return struct.unpack_from("<I", self.data, place)[0]

    def header_2_value(self, place: int) -> int:
        """Returns header 2's plain word at `place`."""
        return self.header_2_words[(place - HEADER_1_SIZE) // 4]

    def section(self) -> bytes:
        """Returns the firmware and resources section, table included."""
        return self.data[self.section_place:self.user_code_place]

    def table_part(self, row: TableRow) -> bytes:
        """Returns the bytes of the part `row` gives."""
        start = self.section_place + row.place
        return self.data[start:start + row.size]


def read_tft(data: bytes, where: str, check: bool = True) -> TftFile:
    """Returns the TFT file `data` holds, split into its parts. `where` names
    it in messages, such as its file's name.

    Raises TftFileError when the file is too short to hold its headers, its
    series is not one of SERIES, it was made by a Nextion Editor older than
    OLDEST_VERSION_READ, or its section is not where header 1 says. With
    `check`, it also raises when any checksum, size, or place the file
    states does not hold, listing every one. Without `check`, those go in the
    file's `problems`, so that a file written wrong can still be read."""
    if len(data) < HEADER_2_END + 4:
        raise TftFileError("%s: %d bytes, too few for a TFT file's headers" % (where, len(data)))
    series = SERIES.get(data[0x15])
    if series is None:
        raise TftFileError("%s: header 1 gives series code %d, which is no series nxwright knows"
                           % (where, data[0x15]))
    # The message does not give the file's version. A newer file gives the
    # version's last number at header 1's 0x17, but in the files seen that
    # were made by 0.47, 0x17 has values from 103 to 164
    # (ResearchNotes/tft/older-editors.md).
    if _version_of(data) < OLDEST_VERSION_READ:
        oldest = version_text(OLDEST_VERSION_READ)
        raise TftFileError("%s was made by a Nextion Editor older than %s. nxwright reads only "
                           "files made by the Nextion Editor %s or later" % (where, oldest, oldest))
    # The section starts at the section size, header 1's 0x34, and runs for
    # header 1's 0x40 bytes, up to the user code.
    section_place, section_length = _u32(data, 0x34), _u32(data, 0x40)
    user_code_place = section_place + section_length
    if not (HEADER_2_END <= section_place
            and section_place + TABLE_SIZE <= user_code_place <= len(data) - 4):
        raise TftFileError("%s: header 1 puts the section at 0x%x, for 0x%x bytes, which the "
                           "file's %d bytes do not hold" % (where, section_place, section_length,
                                                            len(data)))
    words = _header_2_words(data, series)
    table = _table_rows(data, section_place, series)
    tft = TftFile(where, data, series, words, section_place, table, user_code_place, None)
    tft.user_code = _split_user_code(tft)
    _check(tft)
    if check and tft.problems:
        raise TftFileError("%s: %s" % (where, "; ".join(tft.problems)))
    return tft


def firmware_names(series: str) -> tuple:
    """Returns the names of the firmware files a TFT file of `series` holds,
    in the order of the section table's rows: input.bin, then the series'
    own."""
    return ("input.bin",) + _FIRMWARE_FILES[series]


def _version_of(data: bytes) -> tuple:
    """Returns the Nextion Editor's version that wrote the TFT file `data`,
    as header 1 gives it."""
    return data[1], data[2], data[0x17]


def _u32(data: bytes, place: int) -> int:
    return struct.unpack_from("<I", data, place)[0]


def _header_2_words(data: bytes, series: str) -> list:
    """Returns header 2's 49 plain words, from their stored form in `data`."""
    stored = [_u32(data, HEADER_1_SIZE + 4 * n) for n in range(HEADER_2_WORDS)]
    device_id = device_id_of(data)
    if series == "F":
        return decode_f_header_2(device_id, stored)
    key = header_2_key(device_id, series)
    return [word ^ key if n < _KEYED_WORDS else word for n, word in enumerate(stored)]


def _table_rows(data: bytes, section_place: int, series: str) -> list:
    """Returns the section's table, each row named for what it holds."""
    names = (firmware_names(series) + ("",) * 6)[:7]
    names += ("the pictures", "the fonts", "row 9", "row 10", "row 11")
    rows = []
    for number, name in enumerate(names):
        place, size, _ = struct.unpack_from("<III", data, section_place + 12 * number)
        rows.append(TableRow(place, size, name or "row %d" % number))
    return rows


def _split_user_code(tft: TftFile):
    """Returns the user code split by header 2's places, or None when its
    places do not split it, with the reason in the file's problems."""
    code = tft.user_code_bytes
    places = [tft.header_2_value(place) for place in (0xC8, 0xCC, 0xD4)]
    index = [tft.header_2_value(place) - tft.user_code_place for place in (0xE0, 0xE4)]
    bounds = places + index
    if bounds != sorted(bounds) or bounds[-1] > len(code):
        tft.problems.append("header 2's places of the user code's parts (0xC8, 0xCC, 0xD4, "
                            "0xE0, 0xE4) are not in order within its %d bytes" % len(code))
        return None
    blocks = split_blocks(code[:places[0]])
    if blocks is None:
        tft.problems.append("the user code's block sizes do not end at 0x%x, where header 2's "
                            "0xC8 says" % places[0])
        return None
    # The macros' table, from header 1's 0x58 up to the page index. An older
    # Nextion Editor gives 0xffffffff when there are none.
    macros = tft.header_1_value(0x58)
    if macros == _UNSET_PLACE and tft.layout.macros_unset:
        macros = index[0]
    if not (places[2] <= macros <= index[0]) or (index[0] - macros) % MACRO_ENTRY_SIZE:
        tft.problems.append("header 1's 0x58, the macros' table's place, is 0x%x, which does "
                            "not end %d-byte entries at the page index's place, 0x%x"
                            % (macros, MACRO_ENTRY_SIZE, index[0]))
        macros = index[0]
    return UserCode(blocks, code[places[0]:places[1]], code[places[1]:places[2]],
                    code[places[2]:macros], code[index[0]:index[1]], code[index[1]:],
                    code[macros:index[0]], tft.layout.page_index_entry)


def _check(tft: TftFile):
    """Adds to the file's problems each checksum, size, or place it states
    that does not hold."""
    data, problems = tft.data, tft.problems

    def expect(what: str, stated: int, actual: int):
        if stated != actual:
            problems.append("%s is 0x%x; it should be 0x%x" % (what, stated, actual))

    expect("header 1's checksum", _u32(data, _HEADER_1_CHECKSUM),
           byte_form_crc(data[:_HEADER_1_CHECKSUM]))
    expect("header 2's checksum", _u32(data, _HEADER_2_CHECKSUM),
           byte_form_crc(data[HEADER_1_SIZE:_HEADER_2_CHECKSUM]))
    expect("header 1's file size", _u32(data, 0x3C), len(data))
    expect("header 1's section checksum", _u32(data, 0x44),
           series_crc(tft.section(), tft.series))
    expect("the file's checksum", _u32(data, len(data) - 4),
           file_checksum(data[:-4], tft.device_id, tft.series))
    if set(data[HEADER_2_END:tft.section_place]) - {0xFF}:
        problems.append("the bytes between header 2 and the section are not all 0xFF")
    # The section's place is the section size, which its length is a multiple of.
    if (tft.user_code_place - tft.section_place) % tft.section_place:
        problems.append("the section's length, 0x%x, is not a multiple of the section size, "
                        "0x%x" % (tft.user_code_place - tft.section_place, tft.section_place))
    _check_table(tft)
    _check_firmware_places(tft, expect)
    _check_header_2(tft, expect)


def _check_table(tft: TftFile):
    """Checks that the table's rows follow one another from its end, and that
    zeros fill the section after them. A row the series does not use holds
    place 0 and size 0, a place no part can have, as the table is there."""
    at = TABLE_SIZE
    for row in tft.table:
        if row.place == 0 and row.size == 0:
            continue
        if row.place != at:
            tft.problems.append("the section's table puts %s at 0x%x, where the row before "
                                "it ends at 0x%x" % (row.name, row.place, at))
            return
        at = row.place + row.size
    if set(tft.section()[at:]) - {0}:
        tft.problems.append("the section's bytes after its table's last part are not all zeros")


def _check_firmware_places(tft: TftFile, expect):
    """Checks header 1's fields that give the firmware files' places and sizes."""
    main, second = tft.table[1], tft.table[2]
    main_place = tft.section_place + main.place
    # An older Nextion Editor's file of P or E may hold no second firmware
    # file, its row empty.
    absent = ((second.place, second.size) == (0, 0) and tft.layout.second_firmware_optional
              and tft.series in _WORD_FORM_SERIES)
    expect("header 1's 0x18, the second firmware file's place", tft.header_1_value(0x18),
           0 if absent else tft.section_place + second.place)
    expect("header 1's 0x22, the second firmware file's size", tft.header_1_value(0x22),
           second.size)
    if tft.series in _WORD_FORM_SERIES:
        for place in (0x04, 0x08, 0x1E, 0x26, 0x2A):
            expect("header 1's 0x%02X" % place, tft.header_1_value(place), 0)
        return
    expect("header 1's 0x1E", tft.header_1_value(0x1E), tft.section_place + second.place)
    expect("header 1's 0x26, the main firmware file's place", tft.header_1_value(0x26), main_place)
    expect("header 1's 0x2A, the main firmware file's size", tft.header_1_value(0x2A), main.size)
    if main.size >= 9:
        expect("header 1's 0x04", tft.header_1_value(0x04),
               main_place + tft.header_1_value(main_place + 1))
        expect("header 1's 0x08", tft.header_1_value(0x08), tft.header_1_value(main_place + 5))


def _check_header_2(tft: TftFile, expect):
    """Checks header 2's places and counts against the parts they point to,
    and that its words past those the key covers hold 0xFFFFFFFF."""
    if set(tft.header_2_words[_KEYED_WORDS:]) != {0xFFFFFFFF}:
        tft.problems.append("header 2's words from 0x%X are not all 0xFFFFFFFF"
                            % (HEADER_1_SIZE + 4 * _KEYED_WORDS))
    expect("header 2's 0xD8, the section's place", tft.header_2_value(0xD8), tft.section_place)
    expect("header 2's 0xDC, the user code's place", tft.header_2_value(0xDC),
           tft.user_code_place)
    # The pictures' place, or the fonts', is 0 when the device settings leave
    # them out of the file, which leaves their row empty.
    for place, row, what in ((0xE8, 7, "the pictures' place"), (0xF8, 8, "the fonts' place")):
        stated = tft.header_2_value(place)
        if not (stated == 0 and tft.table[row].size == 0):
            expect("header 2's 0x%X, %s" % (place, what), stated,
                   tft.section_place + tft.table[row].place)
    if tft.series in _WORD_FORM_SERIES:
        for place, row in ((0xEC, 9), (0xF0, 10), (0xF4, 11)):
            expect("header 2's 0x%X" % place, tft.header_2_value(place),
                   tft.section_place + tft.table[row].place)
    code = tft.user_code
    if code is None:
        return
    layout = tft.layout
    macros = len(code.macros) // MACRO_ENTRY_SIZE
    stated = struct.unpack_from("<H", tft.data, 0x6E)[0]
    if not (macros == 0 and stated == _UNSET_COUNT and layout.macros_unset):
        expect("header 1's 0x6E, the number of macros", stated, macros)
    if code.blocks:
        expect("header 2's 0xFC, the first block's size", tft.header_2_value(0xFC),
               len(encode_blocks(code.blocks[:layout.first_blocks])))
    if len(code.variables) % VARIABLE_SIZE:
        tft.problems.append("the int variables take %d bytes, not a multiple of %d"
                            % (len(code.variables), VARIABLE_SIZE))
    expect("header 2's 0xD0, the number of int variables", tft.header_2_value(0xD0),
           len(code.variables) // VARIABLE_SIZE)
    if len(code.page_index) % code.index_entry_size:
        tft.problems.append("the page index takes %d bytes, not a multiple of %d"
                            % (len(code.page_index), code.index_entry_size))
    expect("header 2's 0x100's low half, the number of pages", tft.header_2_value(0x100) & 0xFFFF,
           len(code.index_entries()))
    parts = code.block_parts()
    if "pages" in parts:
        tft.problems.append("the page index does not place the user code's blocks from block "
                            "%d on" % parts.index("pages"))
    if code.index_entries() and code.page_data() is None:
        tft.problems.append("the page index's data places do not split the pages' data")
