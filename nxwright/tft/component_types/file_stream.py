"""The file stream component, a type the P and E series have and T and K
have not, as the Nextion Editor 1.68.2 writes it on P, where its values lie
in its memory as P_ENTRIES gives them
(ResearchNotes/tft/file-stream-component.md).

As nxwright's descriptions of its attributes give it, a file stream reads
and writes a file on the SD card: code calls its methods, open, read,
write, close, and find, and reads its val, where the next read or write
takes place, its qty, the open file's size, and its en, whether a file is
open.

A file stream is not drawn and has no events, so on P it has no blocks but
the 0 word. Its memory, 44 bytes, starts with its record's first 4 bytes
alone (P_HEAD_SIZE): its type, ID, vscope, and kind. Then it gives its val,
qty, and en, each method's value, the size of its buffer, and where that
buffer lies. The buffer is memory the screen sets aside for it at the end
of its page's memory, after the texts, as for a waveform on T.

The Nextion Editor adds two lines of its own for each file stream: `init`
and its ID in its page's load section, and a call of its close at the end
of its page's unload event. A call of a method is its entry as an
operand, then its arguments as a command's, between parentheses:
`fs0.close()` is 01, close's entry, then `()` (statements.METHOD_CALL).
"""
import struct

from nxwright.tft.component_types import P_DRAWN_ENTRIES, from_to, object_name
from nxwright.tft.instructions.undocumented_commands import init_block
from nxwright.tft.matching import Rule
from nxwright.tft.statements import TEXT, expression, method_call_covered, operand_pattern

EVENTS = ()
DRAWN = False
# The highest value of an entry of 4 bytes.
_LARGEST = 0x7FFFFFFF
# Its entries on P, by number within the type: (name, place from its base,
# highest, lowest, code). Its type, ID, and vscope are those a drawn
# component has, but that a file stream cannot be global: its vscope's
# highest is 0. Its methods' values follow its val, qty, and en.
P_ENTRIES = {
    0: P_DRAWN_ENTRIES[0], 1: P_DRAWN_ENTRIES[1], 3: ("vscope", 2, 0, 0, 0x121),
    7: ("val", 4, _LARGEST, 0, 0x439), 8: ("qty", 8, _LARGEST, 0, 0x429),
    9: ("en", 12, 1, 0, 0x121),
    **{entry: (name, at, _LARGEST, -_LARGEST - 1, 0x439) for entry, name, at in (
        (10, "open", 16), (11, "read", 20), (12, "write", 24), (13, "close", 28),
        (14, "find", 32))}}
# How many entries it has, the last ones empty.
ENTRIES = 19
# The entry of each attribute it writes, by name.
_ENTRY_OF = {name: entry for entry, (name, *_) in P_ENTRIES.items()}
# Its memory on P, which starts with its record's first 4 bytes.
P_MEMORY_SIZE = 44
P_HEAD_SIZE = 4
# The byte each method's entry gives in the top byte of its owner's field.
P_OWNER_TOPS = {"open": 0x9C, "read": 0x9D, "write": 0x9E, "close": 0x9F, "find": 0xA0}
# Its buffer: its size, the same whatever its molloc and molloc_s, and
# where in its memory that size and its place lie.
_BUFFER_SIZE = 10752
_BUFFER_SIZE_AT, _BUFFER_PLACE_AT = 36, 40


def attribute_place(name: str) -> int:
    """Returns the entry, within the type, of the attribute `name`, any the
    type writes (P_ENTRIES), its methods among them, which code names, as
    in `fs0.val` or `fs0.close()`. Raises KeyError for another."""
    return _ENTRY_OF[name]


def buffer_size(page_object, project) -> int:
    """Returns the size of the file stream's buffer, at the end of its
    page's memory."""
    return _BUFFER_SIZE


def p_memory_extras(page_object, project, place) -> dict:
    """Returns the bytes of the file stream's memory on P that no entry
    gives: its buffer's size, and where its buffer lies, place.buffer_place."""
    return {_BUFFER_SIZE_AT: struct.pack("<I", _BUFFER_SIZE),
            _BUFFER_PLACE_AT: struct.pack("<I", place.buffer_place)}


def load_start(page_object, project, place, places: dict) -> list:
    """Returns the block the file stream adds to its page's load section:
    `init`, then its ID as text."""
    return [init_block(place.object_id)]


def unload_lines(page_object) -> list:
    """Returns the line the Nextion Editor adds for the file stream at the
    end of its page's unload event: a call of its close."""
    return ["%s.close()" % object_name(page_object)]


# One operand of any kind: a text between double quotes, a txt, or a number,
# as where a method takes a path or a txt.
_OPERAND = r"(?:%s|%s)" % (operand_pattern(("number", "text")), TEXT)
# Where a method takes a number: operands joined by the arithmetic
# operators, each a hexadecimal number, a number, a name, or an attribute
# other than a txt.
_NUMBER = expression(operand_pattern(("number",)))
# Each method's arguments: open and find a path; read and write a txt, then
# two numbers; close none. The Nextion Editor compiled a number, or a text,
# where a path or a txt goes.
_ARGUMENTS = {"open": _OPERAND, "find": _OPERAND,
              "read": ",".join((_OPERAND, _NUMBER, _NUMBER)),
              "write": ",".join((_OPERAND, _NUMBER, _NUMBER)), "close": ""}


def _call_covered(need) -> bool:
    """Whether the line of code `need` is a call of a method of a file
    stream of its page, of the arguments each method takes (_ARGUMENTS).
    nxwright's build refuses another number of arguments."""
    return method_call_covered(need, "file-stream", _ARGUMENTS)


# The series this module's probes matched (matching.py): P in p_probes.py,
# and E in e_probes.py. T and K have no file stream.
SERIES = ("P", "E")

# What the file stream has matched with probes (matching.py): a file
# stream at its defaults, on P and E, but for these.
MATCHED = [
    Rule("type", "file-stream",
         "a file stream, its attributes at their defaults but for those below"),
    Rule("attribute", "file-stream.objname", "any name nxwright's build takes"),
    Rule("attribute", "file-stream.val", "any value, written as it is"),
    Rule("attribute", "file-stream.qty", "any value, written as it is"),
    Rule("attribute", "file-stream.en", "0, 1, or any other value that fits in its byte, written "
         "as it is"),
    Rule("attribute", "file-stream.molloc", "any value, which changes nothing in the file"),
    Rule("attribute", "file-stream.molloc_s", "any value, which changes nothing in the file"),
    Rule("code", None, "a call of a method of a file stream of the line's page: open and find "
         "of one operand of any kind, a text of any characters, with the escapes \\\\, "
         "\\\", and \\r, a txt, or a number; read and write of such an operand, then two "
         "numbers, each one operand or several joined by the arithmetic operators, each a "
         "number, a hexadecimal number "
         "of 1 to 4 bytes, program.s's int variables, system variables, colours' names, or an "
         "attribute other than a txt of a component on its page; and close; the arguments "
         "between commas without spaces; in an event; on P and E", _call_covered),
]
