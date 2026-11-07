"""Comparing two TFT files: which part, and which block of the user code,
first differs, with the bytes around it.

Each file is cut into pieces, in file order, each named for what it holds:
header 1's fields, header 2's words, the section's table rows and the parts
they give, each block of the user code, and so on. The two lists are compared
piece by piece. So a block one file has and the other lacks shows as the
first piece that differs, not as every byte after it moved.
"""
from dataclasses import dataclass
import struct

from nxwright.tft.tft_file import (HEADER_1_FIELDS, HEADER_1_SIZE, HEADER_2_END, HEADER_2_FIELDS,
                            HEADER_2_WORDS, PAGE_INDEX_ENTRY_SIZE, TABLE_SIZE, TftFile,
                            encode_blocks)

# How many bytes to show either side of the first byte that differs.
CONTEXT = 12


@dataclass(frozen=True)
class Piece:
    """A piece of a TFT file: what it is, its place in the file, its bytes."""
    name: str
    place: int
    data: bytes


@dataclass(frozen=True)
class Difference:
    """Where two files first differ: the piece, as each file has it, and the
    first byte within it that differs, counted from the piece's start. When
    one file has a piece the other lacks, that file's piece is None."""
    a: Piece
    b: Piece
    offset: int


def pieces(tft: TftFile) -> list:
    """Returns the file's pieces, in file order (the module's docstring)."""
    data, found = tft.data, []

    def add(name: str, place: int, size: int):
        found.append(Piece(name, place, data[place:place + size]))

    for place, size, what in HEADER_1_FIELDS:
        add("header 1, 0x%02X (%s)" % (place, what), place, size)
    for number in range(HEADER_2_WORDS):
        place = HEADER_1_SIZE + 4 * number
        what = HEADER_2_FIELDS.get(place, "not known")
        found.append(Piece("header 2, 0x%X (%s)" % (place, what), place,
                           struct.pack("<I", tft.header_2_words[number])))
    add("header 2's checksum", HEADER_2_END - 4, 4)
    add("the 0xFF bytes before the section", HEADER_2_END, tft.section_place - HEADER_2_END)
    for number, row in enumerate(tft.table):
        add("the section's table, row %d (%s)" % (number, row.name),
            tft.section_place + 12 * number, 12)
    end = TABLE_SIZE
    for row in tft.table:
        if row.size:
            add("the section, %s" % row.name, tft.section_place + row.place, row.size)
            end = max(end, row.place + row.size)
    add("the section's zeros after its parts", tft.section_place + end,
        tft.user_code_place - tft.section_place - end)
    found.extend(_user_code_pieces(tft))
    add("the file's checksum", len(data) - 4, 4)
    return found


def _user_code_pieces(tft: TftFile) -> list:
    """Returns the user code's pieces: each block, named by its part and its
    number within it, then the parts after the blocks, page by page where the
    page index splits them."""
    code, place = tft.user_code, tft.user_code_place
    if code is None:
        return [Piece("user code, not split", place, tft.user_code_bytes)]
    found, counts = [], {}
    for block, part, at in zip(code.blocks, code.block_parts(), code.block_places()):
        number = counts[part] = counts.get(part, -1) + 1
        found.append(Piece("user code, %s, block %d" % (part, number), place + at,
                           encode_blocks([block])))
    places = code.places()
    found.append(Piece("user code, after the blocks", place + places["after the blocks"][0],
                       code.after_blocks))
    found.append(Piece("user code, variables", place + places["variables"][0], code.variables))
    start = places["data"][0]
    page_data = code.page_data()
    entries = code.index_entries()
    if page_data is None:
        found.append(Piece("user code, data", place + start, code.data))
    else:
        for page, (entry, data) in enumerate(zip(entries, page_data)):
            found.append(Piece("user code, page %d's data" % page, place + entry.data_place,
                               data))
    if code.macros:
        found.append(Piece("user code, macros' table", place + places["macros"][0],
                           code.macros))
    start = places["page index"][0]
    for number in range(len(entries)):
        at = PAGE_INDEX_ENTRY_SIZE * number
        found.append(Piece("user code, page index, entry %d" % number, place + start + at,
                           code.page_index[at:at + PAGE_INDEX_ENTRY_SIZE]))
    start = places["records"][0]
    found.append(Piece("user code, records", place + start, code.records))
    return found


def differences(a: TftFile, b: TftFile) -> list:
    """Returns the first Difference between `a` and `b` in each part where
    they differ, in file order. A piece's part is its name before its first
    comma: "header 1", "header 2", "the section's table", "the section", "user
    code", and so on. An empty list means the files are the same."""
    found, parts = [], set()
    for a_piece, b_piece in _paired(pieces(a), pieces(b)):
        if a_piece is not None and b_piece is not None and a_piece.data == b_piece.data:
            continue
        part = part_of(a_piece or b_piece)
        if part not in parts:
            parts.add(part)
            offset = 0 if a_piece is None or b_piece is None \
                else _first_byte_differing(a_piece.data, b_piece.data)
            found.append(Difference(a_piece, b_piece, offset))
    return found


def _paired(a_pieces: list, b_pieces: list) -> list:
    """Returns the pieces of both files paired by name, with None for the
    file that lacks a piece, in the order of their places. A piece's name is
    unique within its file."""
    a_names = {piece.name for piece in a_pieces}
    b_by_name = {piece.name: piece for piece in b_pieces}
    pairs = [(piece, b_by_name.get(piece.name)) for piece in a_pieces]
    pairs += [(None, piece) for piece in b_pieces if piece.name not in a_names]
    return sorted(pairs, key=lambda pair: (pair[0] or pair[1]).place)


def part_of(piece: Piece) -> str:
    """Returns the part of the file `piece` belongs to: its name before its
    first comma."""
    return piece.name.split(",", 1)[0]


def _first_byte_differing(a: bytes, b: bytes) -> int:
    """Returns the first place where `a` and `b` differ, or the shorter's
    length when one starts the other."""
    return next((at for at in range(min(len(a), len(b))) if a[at] != b[at]), min(len(a), len(b)))


def report(a: TftFile, b: TftFile) -> str:
    """Returns, in words, where `a` and `b` first differ in each part, with
    the bytes around it in each, the byte that differs in brackets. Or that
    they are the same."""
    found = differences(a, b)
    if not found:
        return "%s and %s are the same, byte for byte" % (a.where, b.where)
    lines = ["%s and %s differ:" % (a.where, b.where)]
    for difference in found:
        lines.append("- %s:" % part_of(difference.a or difference.b))
        for tft, piece in ((a, difference.a), (b, difference.b)):
            if piece is None:
                lines.append("  %s: has no piece there" % tft.where)
            else:
                lines.append("  %s: %s, at 0x%x, byte %d of it:\n      %s" % (
                    tft.where, piece.name, piece.place, difference.offset,
                    _bytes_around(piece.data, difference.offset)))
    return "\n".join(lines)


def _bytes_around(data: bytes, offset: int) -> str:
    """Returns `data`'s bytes either side of `offset`, as hex, the byte at
    `offset` in brackets, or a mark where the piece ends there."""
    start = max(0, offset - CONTEXT)
    before = data[start:offset].hex(" ")
    if offset >= len(data):
        return "%s%s[end]" % ("... " if start else "", before)
    after = data[offset + 1:offset + 1 + CONTEXT].hex(" ")
    return "%s%s [%02x] %s%s" % ("... " if start else "", before, data[offset], after,
                                 " ..." if offset + 1 + CONTEXT < len(data) else "")
