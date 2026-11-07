"""Compares what two TFT files hold, as the decompiler's round trip does
(round_trip.py): the original, and the file compiled again from the source
folder the decompiler wrote for it.

The two are not compared byte for byte. A file keeps each name only as its
checksum, and a name no guess matched comes back as a readable name, such as
text3, whose checksum differs. Several tables are sorted by those checksums,
and their rows move too. Instead, each user code is read as the decoded file
reads it (decoded_file.read_decoded), and the two are compared field by
field, names by their text alone. Every other piece of the files is compared byte
for byte, as comparison.py cuts them: the headers, the section, and the
user code's records, page index, and data. Only the pieces that hold a
name's checksum, and the file's checksum, which covers them, are left to
the decoded file.
"""
from dataclasses import dataclass, fields, is_dataclass
import re

from nxwright.tft.comparison import pieces
from nxwright.tft.decompiling.decoded_file import DecodedFile, Name, read_decoded
from nxwright.tft.tft_file import TftFile

# The pieces that hold names' checksums, or cover them, by comparison.py's
# names: the int variables' table, the macros' table, and the file's
# checksum; and each block of the user code, such as "user code, page 0,
# block 3", as its blocks hold the page list and each page's objects' table.
_HOLDING_NAMES = ("user code, variables", "user code, macros' table", "the file's checksum")
_BLOCK = re.compile(r"user code, .+, block \d+")


@dataclass(frozen=True)
class Mismatch:
    """A place where two files hold something different: `where`, a field
    of the decoded file, such as "pages[0].objects[1].entries[4]", or a
    piece compared byte for byte, such as "user code, records"; then what
    the original holds there, and what the other file holds, None for a
    piece it lacks."""
    where: str
    original: object
    again: object


@dataclass(frozen=True)
class ReadForComparison:
    """What the comparison reads of a TFT file: its decoded file, and its
    pieces compared byte for byte, {name: bytes}."""
    decoded: DecodedFile
    pieces: dict


def read_for_comparison(tft: TftFile, decoded: DecodedFile = None) -> ReadForComparison:
    """Returns what the comparison reads of `tft`, whose decoded file is
    `decoded`, when given, as the decompile decoded it. Raises DecodeError
    when its user code cannot be decoded."""
    return ReadForComparison(read_decoded(tft) if decoded is None else decoded,
                             {piece.name: piece.data for piece in pieces(tft)})


def mismatches(original: TftFile, again: TftFile) -> list:
    """Returns each Mismatch between what `original` and `again` contain
    (compared_mismatches). Raises DecodeError when either file's user code
    cannot be decoded."""
    return compared_mismatches(read_for_comparison(original), read_for_comparison(again))


def compared_mismatches(original: ReadForComparison, again: ReadForComparison) -> list:
    """Returns each Mismatch between what `original` and `again` contain, in
    the order of the decoded file's fields, then of each piece compared
    byte for byte, in `original`'s order, then those `again` alone has. An
    empty list means the two contain the same."""
    found = _decoded_mismatches(original.decoded, again.decoded, "")
    ours, theirs = original.pieces, again.pieces
    for name in list(ours) + [name for name in theirs if name not in ours]:
        if not _holds_names(name) and ours.get(name) != theirs.get(name):
            found.append(Mismatch(name, ours.get(name), theirs.get(name)))
    return found


def _holds_names(piece_name: str) -> bool:
    """Whether the piece `piece_name` holds names' checksums, or covers them
    (_HOLDING_NAMES)."""
    return piece_name in _HOLDING_NAMES or _BLOCK.fullmatch(piece_name) is not None


def _decoded_mismatches(original, again, where: str) -> list:
    """Returns each Mismatch between `original` and `again`, two values of
    the decoded file at `where`: a Name by its text alone, a dataclass field
    by field, a list item by item once their lengths agree, a dict by its
    keys then each value, and any other value as it is."""
    if isinstance(original, Name) and isinstance(again, Name):
        return [] if original.text == again.text else [Mismatch(where, original.text, again.text)]
    if is_dataclass(original) and type(original) is type(again):
        found = []
        for each in fields(original):
            found += _decoded_mismatches(getattr(original, each.name), getattr(again, each.name),
                                         "%s.%s" % (where, each.name) if where else each.name)
        return found
    if isinstance(original, list) and isinstance(again, list):
        if len(original) != len(again):
            return [Mismatch(where + ", its length", len(original), len(again))]
        found = []
        for number, (one, other) in enumerate(zip(original, again)):
            found += _decoded_mismatches(one, other, "%s[%d]" % (where, number))
        return found
    if isinstance(original, dict) and isinstance(again, dict):
        if list(original) != list(again):
            return [Mismatch(where + ", its keys", list(original), list(again))]
        found = []
        for key in original:
            found += _decoded_mismatches(original[key], again[key], "%s[%r]" % (where, key))
        return found
    return [] if original == again else [Mismatch(where, original, again)]
