"""How page files and defaults files write a number attribute's stored bytes.

A number attribute is stored as 1, 2, or 4 bytes, low byte first. A 4-byte
one whose top bit is set is written negative, as the Editor's attribute
panel shows it: a number's `val` of -42, stored as 0xFFFFFFD6, is written
-42, and a file browser's `val` of 0xFFFFFFFF is written -1. Either
spelling of such a value is read back. Values of 1 and 2 bytes are
unsigned. A dump (project/page_text.py) writes every value unsigned.

`dir` and `vvs2`, on the types where they are numbers, as a scrolling
text's, were written as texts of their stored bytes before nxwright told
them apart from the texts of the same names on other types. Such a text is
still read (page_text.text_form_number).
"""

_FOUR_BYTES = 4
_TOP_BIT = 1 << 31
_ALL = 1 << 32


def number_to_bytes(value: int, width: int) -> bytes:
    """Returns the `width` stored bytes of a number attribute's `value`: a
    negative 4-byte value as its 32 bits. Raises OverflowError when `value`
    does not fit."""
    if width == _FOUR_BYTES and -_TOP_BIT <= value < 0:
        value += _ALL
    return value.to_bytes(width, "little")


def number_from_bytes(data: bytes) -> int:
    """Returns a number attribute's value, as page files and defaults files
    write it, from its stored bytes: 4 bytes whose top bit is set as a
    negative number, any other unsigned."""
    value = int.from_bytes(data, "little")
    if len(data) == _FOUR_BYTES and value & _TOP_BIT:
        value -= _ALL
    return value
