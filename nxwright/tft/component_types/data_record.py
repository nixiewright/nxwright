"""The data record component, a type the P and E series have and T and K
have not, as the Nextion Editor 1.68.2 writes it on P, where its values lie
in its memory as P_ENTRIES gives them
(ResearchNotes/tft/data-record-component.md).

As nxwright's descriptions of its attributes give it, a data record keeps
records in a data file, its path, under columns titled by its dir, each
record's fields separated by "^". Its format gives the column widths,
separated by "^", such as "100^100". Code adds a record with its insert,
deletes some with its delete, changes one with its up, and deletes every
record with its clear.

On P, a data record has no drawing blocks: the screen draws it from its
memory. It is global on P, its vscope 1 (nxwright refuses 0 there), so its
memory lies in the int area, after the int variables (frame.py). Its
memory, 252 bytes, starts with what its record's head holds. Then it gives
its values, its init and its autoleft, which no entry gives, each of its
five texts' room and place, its path, format, dir, filter, and txt, then the
size of its buffer and where that buffer lies. Its texts lie after the
global objects' memory, and its buffer after them, before every page's
memory.

A style of 1, a border of one colour, gives its borderc and borderw entries
after its style's, each later entry two on, so each data record is written
by the variant of its style (variant).
"""
from functools import lru_cache
import struct

from nxwright.tft.component_types import (P_DRAWN_ENTRIES, PLACE_WORDS, attribute_number, from_to,
                                   p_border_and_background_rules, place_fits_its_record,
                                   room_covered, text_in_room, value_rule, with_p_background)
from nxwright.tft.instructions.undocumented_commands import init_block
from nxwright.tft.matching import Rule
from nxwright.tft.reasons import DOES_NOT_FIT, INVALID_VALUE
from nxwright.tft.statements import TEXT, expression, method_call_covered, operand_pattern

EVENTS = ("down", "up")
# The highest value of an entry of 4 bytes.
_LARGEST = 0x7FFFFFFF
# Its entries on P, by number within the type: (name, place from its base,
# highest, lowest, code), its font's highest and its texts' codes set by
# component_types.p_table. 16 to 18 stay empty, where an effect's first and
# time go (component_types.with_p_effect), and so do 25, 27, 32, 34, 41,
# 51, and 54. Its vscope's lowest is 1, as it is always global.
P_ENTRIES = {
    **P_DRAWN_ENTRIES, 3: ("vscope", 2, 1, 1, 0x121), 19: ("sta", 56, 3, 0, 0x121),
    20: ("style", 57, 3, 0, 0x121), 21: ("font", 61, 0, 0, 0x131),
    22: ("bco", 62, 0xFFFF, 0, 0x232),
    23: ("pco", 64, 0xFFFF, 0, 0x232), 24: ("xcen", 66, 2, 0, 0x131),
    26: ("path", 0, 0, 0, 0x3F), 28: ("lenth", 76, 255, 2, 0x429),
    29: ("maxval", 80, _LARGEST, 1, 0x429), 30: ("dez", 84, 12, 1, 0x222),
    31: ("format", 0, 0, 0, 0x3F), 33: ("dir", 0, 0, 0, 0x3F), 35: ("mode", 100, 1, 0, 0x131),
    36: ("dis", 101, 1, 0, 0x131), 37: ("order", 102, 1, 0, 0x131),
    38: ("qty", 104, _LARGEST, -_LARGEST - 1, 0x429), 39: ("spax", 108, 255, 0, 0x131),
    40: ("hig", 109, 255, 1, 0x131), 42: ("left", 111, 2, 0, 0x131),
    43: ("gdc", 112, 0xFFFF, 0, 0x232), 44: ("gdw", 114, 255, 0, 0x131),
    45: ("gdh", 115, 255, 0, 0x131), 46: ("bco1", 116, 0xFFFF, 0, 0x232),
    47: ("pco1", 118, 0xFFFF, 0, 0x232), 48: ("bco2", 120, 0xFFFF, 0, 0x232),
    49: ("pco2", 122, 0xFFFF, 0, 0x232), 50: ("filter", 0, 0, 0, 0x3F),
    52: ("val", 132, _LARGEST, -_LARGEST - 1, 0x439), 53: ("txt", 0, 0, 0, 0x2F),
    **{entry: (name, at, _LARGEST, -_LARGEST - 1, 0x439) for entry, name, at in (
        (55, "insert", 144), (56, "delete", 148), (57, "up", 152), (58, "clear", 156))},
    59: ("ch", 160, 32, 0, 0x131),
    60: ("maxval_y", 164, _LARGEST, -_LARGEST - 1, 0x429),
    61: ("val_y", 168, _LARGEST, -_LARGEST - 1, 0x439),
    62: ("maxval_x", 172, _LARGEST, -_LARGEST - 1, 0x429),
    63: ("val_x", 176, _LARGEST, -_LARGEST - 1, 0x439)}
# How many entries it has without a border of one colour, the last ones
# empty.
ENTRIES = 74
# Its style of a border of one colour, which gives its borderc's and
# borderw's entries after its style's, each later entry two on.
_BORDERED = 1
_STYLE = 20
_BORDER_ENTRIES = {21: ("borderc", 58, 0xFFFF, 0, 0x232), 22: ("borderw", 60, 255, 0, 0x131)}
# The top byte of the owner field of these attributes' entries
# (component_types.p_component_entries); every other entry gives 0 there.
P_OWNER_TOPS = {"path": 0x81, "format": 0x02, "hig": 0x01, "gdw": 0x03, "gdh": 0x04,
                "val": 0x80, "insert": 0x9C, "delete": 0x9D, "up": 0x9E, "clear": 0x9F}
# Its memory on P, and its texts (P_TEXTS): where in its memory the place of
# each lies, which no entry gives, and the attribute that gives its room,
# which none gives either, in the order they lie.
P_MEMORY_SIZE = 252
P_TEXTS = {72: ("path", "path_m", 70), 88: ("format", "format_m", 86),
           96: ("dir", "dir_m", 94), 128: ("filter", "filter_m", 126),
           140: ("txt", "txt_m", 138)}
# The values of its memory on P that no entry gives, by attribute: where
# each lies, 1 byte.
P_UNENTERED = {"init": 67, "autoleft": 110}
# Its buffer: its size, and where in its memory that size and its place lie.
_BUFFER_SIZE = 10752
_BUFFER_SIZE_AT, _BUFFER_PLACE_AT = 180, 184


class _DataRecord:
    """A data record with a border of one colour or without (`bordered`),
    with the members a type's module gives (component_types/__init__.py) but
    MATCHED."""
    EVENTS = EVENTS
    # On P, the frame reads these of the variant.
    P_MEMORY_SIZE, P_TEXTS, P_OWNER_TOPS = P_MEMORY_SIZE, P_TEXTS, P_OWNER_TOPS

    def __init__(self, bordered: bool):
        if bordered:
            self.P_ENTRIES = {entry + 2 * (entry > _STYLE): value
                              for entry, value in P_ENTRIES.items()}
            self.P_ENTRIES.update(_BORDER_ENTRIES)
            self.ENTRIES = ENTRIES + 2
        else:
            self.P_ENTRIES, self.ENTRIES = P_ENTRIES, ENTRIES
        self._entry_of = {name: entry for entry, (name, *_) in self.P_ENTRIES.items()}

    def attribute_place(self, name: str) -> int:
        """Returns the entry, within the type, of the attribute `name`, any
        the variant writes (P_ENTRIES), its methods among them, which code
        names, as in `data0.val` or `data0.clear()`. Raises KeyError for
        another, such as borderc without a border of one colour."""
        return self._entry_of[name]

    @staticmethod
    def load_start(page_object, project, place, places: dict) -> list:
        """Returns the block the data record adds to its page's load section,
        before the page's own load code: `init`, then its ID as text."""
        return [init_block(place.object_id)]

    @staticmethod
    def buffer_size(page_object, project) -> int:
        """Returns the size of the data record's buffer, after the texts of
        the global objects."""
        return _BUFFER_SIZE

    @staticmethod
    def p_memory_extras(page_object, project, place) -> dict:
        """Returns the bytes of the data record's memory on P that no entry
        gives: its init and its autoleft, its buffer's size, and where its
        buffer lies, place.buffer_place."""
        extras = {at: bytes([attribute_number(page_object, name)])
                  for name, at in P_UNENTERED.items()}
        extras.update({_BUFFER_SIZE_AT: struct.pack("<I", _BUFFER_SIZE),
                       _BUFFER_PLACE_AT: struct.pack("<I", place.buffer_place)})
        return extras


@lru_cache(maxsize=None)
def _of(bordered: bool) -> _DataRecord:
    """Returns the variant of a data record with a border of one colour or
    without, made once."""
    return _DataRecord(bordered)


def variant(page_object):
    """Returns what describes the data record `page_object`: the variant of
    its style, with its border's entries at a style of 1, its entries as its
    sta changes them (component_types.with_p_background)."""
    return with_p_background(_of(attribute_number(page_object, "style") == _BORDERED),
                             page_object)


# Each of its texts, and the attribute that gives its room. Each is written
# as its bytes, whatever its characters (component_types.text_in_room). Its
# format's widths, dir's headings, and fields in code are separated by "^".
_TEXTS = (("path", "path_m"), ("format", "format_m"), ("dir", "dir_m"),
          ("filter", "filter_m"), ("txt", "txt_m"))


# Where a method takes a record: one operand of any kind, a text between
# double quotes, its fields between "^", a txt, or a number, which the
# screen then adds nothing for.
_RECORD = r"(?:%s|%s)" % (operand_pattern(("number", "text")), TEXT)
# Where a method takes a number: operands joined by the arithmetic
# operators, each a hexadecimal number, a number, a name, or an attribute
# other than a txt.
_NUMBER = expression(operand_pattern(("number",)))
# Each method's arguments: insert a record; delete where to start and how
# many; up a record and its place; clear none.
_ARGUMENTS = {"insert": _RECORD, "delete": ",".join((_NUMBER, _NUMBER)),
              "up": ",".join((_RECORD, _NUMBER)), "clear": ""}


def _call_covered(need) -> bool:
    """Whether the line of code `need` is a call of a method of a data record
    of its page, of the arguments each method takes (_ARGUMENTS). nxwright's
    build refuses another number of arguments."""
    return method_call_covered(need, "data-record", _ARGUMENTS)


# The series this module's probes matched (matching.py): P in p_probes.py,
# and E in e_probes.py. T and K have no data record.
SERIES = ("P", "E")

# What the data record has matched with probes (matching.py): a data record
# at its defaults, on P and E, but for these.
MATCHED = [
    Rule("type", "data-record",
         "a data record, its attributes at their defaults but for those below"),
    Rule("attribute", "data-record.objname", "any name nxwright's build takes"),
    *[Rule("attribute", "data-record." + name,
           PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT)
      for name in ("x", "y", "w", "h")],
    # Its border and what lies behind it, as its probes on P and E showed.
    *[Rule("attribute", "data-record." + name, words, covers, reason)
      for name, words, covers, reason in p_border_and_background_rules()],
    Rule("attribute", "data-record.font", "any font of the project"),
    *[Rule("attribute", "data-record." + text, "any characters, no more than its " + room,
           text_in_room(room))
      for text, room in _TEXTS],
    # The Nextion Editor refuses 256 in these three, as nxwright's memory
    # table records.
    *[Rule("attribute", "data-record." + room, "from 1 to %d, its %s fitting it" % (high, text),
           room_covered(text, high))
      for text, room, high in (("path", "path_m", 255), ("dir", "dir_m", 255),
                               ("txt", "txt_m", 255))],
    *[Rule("attribute", "data-record." + room, "from 0 to 65534, the most the Nextion Editor "
           "takes (\"Out of range\" past it), its %s fitting it" % text,
           room_covered(text, 0xFFFE, low=0))
      for text, room in (("format", "format_m"), ("filter", "filter_m"))],
    Rule("attribute", "data-record.lenth", "any value, written as it is"),
    Rule("attribute", "data-record.maxval", "any value, written as it is"),
    *[Rule("attribute", "data-record." + name, "from -2147483648 to 2147483647, its entry's "
           "limits", from_to(-_LARGEST - 1, _LARGEST))
      for name in ("val", "qty", "maxval_y", "val_y", "maxval_x", "val_x")],
    Rule("attribute", "data-record.dez", "any value, written as it is"),
    Rule("attribute", "data-record.hig", "any value, written as it is"),
    Rule("attribute", "data-record.left", "any value, written as it is"),
    Rule("attribute", "data-record.style", "0, 1, 2, or 3", from_to(0, 3), INVALID_VALUE),
    Rule("attribute", "data-record.ch", "any value, written as it is"),
    *[Rule("attribute", "data-record." + name, "from 0 to 255", from_to(0, 255))
      for name in ("gdw", "gdh")],
    *[Rule("attribute", "data-record." + name, "0 or 1", from_to(0, 1))
      for name in ("autoleft", "init")],
    Rule("attribute", "data-record.order", "0, 1, or any other value that fits in its byte, "
         "written as it is"),
    Rule("attribute", "data-record.dis", "any value, written as it is"),
    # Whether the screen creates its file when the file does not exist: at
    # 0, it does not, and the Nextion Editor compiles it only with that
    # file on its virtual SD card.
    Rule("attribute", "data-record.mode", "0, its file read only if it exists, 1, its file "
         "created if it does not, or any other value that fits in its byte, written as it is"),
    Rule("attribute", "data-record.molloc", "any value, which changes nothing in the file"),
    Rule("attribute", "data-record.molloc_s", "any value, which changes nothing in the file"),
    Rule("code", None, "a call of a method of a data record of the line's page: insert of one "
         "operand of any kind, a text of any characters, with the escapes \\\\, \\\", and "
         "\\r, a txt, or a number; delete of two numbers, each one operand or several joined "
         "by the arithmetic operators, each a number, a hexadecimal number of 1 to 4 bytes, "
         "program.s's int variables, system variables, colours' names, or an attribute other "
         "than a txt of a component on its page; up of such an operand and such a number; and "
         "clear; the arguments between commas without spaces; in an event; on P and E",
         _call_covered),
] + [Rule("attribute", "data-record." + name, *value_rule(name))
     for name in ("bco", "pco", "bco1", "pco1", "bco2", "pco2", "gdc", "xcen", "spax",
                  "borderc", "borderw")]
