"""The variable component, as the Nextion Editor 1.68.2 writes it on T, and
on P, where its values lie in its memory as P_ENTRIES gives them
(ResearchNotes/tft/variable-component.md gives each value, and how it was found).

A variable is one of a number or one of a text, by its sta, 0 or 1, and each
is written its own way (variant). So far it writes a variable at its
defaults but for its sta, its val, its txt, and its txt_maxl. One of a
number writes no txt or txt_maxl, and one of a text no val. Code may use
the attributes each writes, as the val of one of a number, the txt of one
of a text, and the sta of either.

A variable is not drawn: its blocks are one empty run, and it has no events.
Its memory is 4 bytes, its val in one of a number, then, in one of a text,
its txt: txt_maxl + 1 bytes, the whole rounded up to 4.

On P, its memory is 16 bytes, which start with its record's first 4 bytes
alone (P_HEAD_SIZE), as a file stream's do. Then come its sta, and its val
at 12 in one of a number, or, in one of a text, its txt_maxl and the place
of its txt, which lies after its page's components' memory, as a text's
txt does. Its entries keep T's numbers, and give 0xFFFF in place of its ID
and its page's, as on T (P_OWNER).
"""
import struct

from nxwright.project.attribute_values import number_from_bytes

from nxwright.tft.component_types import (P_DRAWN_ENTRIES, TXT_WORDS, TXT_MAXL_WORDS, from_to,
                                   packed_entries, text_fits, txt_maxl_covered,
                                   vscope_entry, with_txt)
from nxwright.tft.matching import Rule
from nxwright.tft.reasons import DOES_NOT_FIT, INVALID_VALUE

# What each of a variable's entries gives in place of its ID and its page's.
_NO_OWNER = 0xFFFF
# Where a variable of a text's txt lies in memory, from its base: after the
# 4 bytes a val would take.
_TXT = 4
# A variable of a number's memory on T, K, and F: its val, 4 bytes, signed.
MEMORY_FORMAT = "<i"


def _sta(page_object) -> int:
    return number_from_bytes(page_object.attribute("sta") or b"\x00")


# A variable has no event.
EVENTS = ()


class _Variable:
    """A variable of a number or of a text, with the members a type's module
    gives (component_types/__init__.py) but MATCHED: its entries, each
    attribute's entry, and its record's slots."""
    EVENTS = EVENTS
    DRAWN = False
    # On P: its memory, which starts with its record's first 4 bytes; the
    # owner its entries give; its texts; and its entries, by number within
    # the type: (name, place from its base, highest, lowest, code).
    P_MEMORY_SIZE, P_HEAD_SIZE, P_OWNER, P_TEXTS = 16, 4, _NO_OWNER, {}
    P_ENTRIES = {0: P_DRAWN_ENTRIES[0], 1: P_DRAWN_ENTRIES[1], 3: P_DRAWN_ENTRIES[3],
                 7: ("sta", 4, 1, 0, 0x121), 8: ("val", 12, 0x7FFFFFFF, -0x80000000, 0x439)}

    def __init__(self, entries: int, entry: dict, slots: dict):
        self.ENTRIES, self._entry, self._slots = entries, entry, slots

    def drawing(self, page_object, project, place) -> list:
        """Returns no blocks: a variable is not drawn."""
        return []

    def data(self, page_object, project, place) -> bytes:
        """Returns the variable's entries: its type, its ID, its vscope, its
        sta, and where its value lies in memory."""
        values = {"type": (page_object.attribute("type")[0], 255, 0, 0x101),
                  "id": (place.object_id, 255, 0, 0x101), "vscope": vscope_entry(page_object),
                  "sta": (_sta(page_object), 1, 0, 0x101)}
        values.update(self._values(page_object, place))
        return packed_entries({self._entry[name]: value for name, value in values.items()},
                              self.ENTRIES, place, _NO_OWNER)

    def _values(self, page_object, place) -> dict:
        return {"val": (place.base, 0x7FFFFFFF, -0x80000000, 0x439)}

    def memory(self, page_object, project) -> bytes:
        """Returns the variable's starting value: its val, 4 bytes, signed."""
        val = int.from_bytes(page_object.attribute("val") or b"\x00", "little", signed=True)
        return struct.pack(MEMORY_FORMAT, val)

    def record_slots(self) -> dict:
        """Returns the variable's slots in its record: {slot: entry within the
        type}."""
        return {slot: self._entry[name] for slot, name in self._slots.items()}

    def attribute_place(self, name: str) -> int:
        """Returns the entry, within the type, of the attribute `name`, any
        the type writes. Raises KeyError for another."""
        return self._entry[name]


class _TextVariable(_Variable):
    """A variable of a text: its txt where one of a number has its val, and
    its txt_maxl after it. On P, its txt lies after its page's components'
    memory, and its memory gives its txt_maxl at 6 and its txt's place at 8."""
    P_TEXTS = {8: ("txt", "txt_maxl", 6)}
    # On T, K, and F, where its txt lies in its memory, for the frame's
    # scratch image (frame._t_rooms).
    TXT_PLACE = _TXT
    P_ENTRIES = {**{entry: value for entry, value in _Variable.P_ENTRIES.items() if entry != 8},
                 8: ("txt", 0, 0, 0, 0x3F), 9: ("txt_maxl", 6, 0xFFFE, 0, 0x222)}

    def _values(self, page_object, place) -> dict:
        maxl = number_from_bytes(page_object.attribute("txt_maxl"))
        # The text's code gives its size in memory, txt_maxl + 1, in its second byte.
        return {"txt": (place.base + _TXT, 0, 0, (maxl + 1) << 8 | 0x3F),
                "txt_maxl": (maxl, 0xFFFE, 0, 0x202)}

    def memory(self, page_object, project) -> bytes:
        """Returns the variable's starting values: 4 zeros, then its text,
        padded with zeros."""
        return with_txt(bytes(_TXT), page_object)


_OF_A_NUMBER = _Variable(11, {"type": 0, "id": 1, "vscope": 3, "sta": 7, "val": 8},
                         {1: "vscope", 2: "sta", 20: "val", 49: "id", 62: "type"})
_OF_A_TEXT = _TextVariable(12, {"type": 0, "id": 1, "vscope": 3, "sta": 7, "txt": 8,
                                "txt_maxl": 9},
                           {1: "vscope", 2: "sta", 28: "txt", 29: "txt_maxl", 49: "id",
                            62: "type"})


def variant(page_object) -> _Variable:
    """Returns what describes the variable `page_object`: one of a text when
    its sta is 1, else one of a number."""
    return _OF_A_TEXT if _sta(page_object) == 1 else _OF_A_NUMBER


def _of_a_number(need) -> bool:
    """Whether the attribute `need` is of a variable of a number, its sta 0,
    which writes no txt or txt_maxl, so that any of them is taken: the
    Nextion Editor compiled one whose txt is longer than its txt_maxl."""
    return number_from_bytes(need.context.get("sta") or b"\x00") == 0


# The series this module's probes matched (matching.py): T, K in k_probes.py,
# P in p_probes.py, E in e_probes.py, and F in f_probes.py.
SERIES = ("T", "K", "P", "E", "F")

# What the variable has matched with probes (matching.py): a variable at its
# defaults, on each screen model of T and K at each rotation, and on P, E, and
# F, but for these.
MATCHED = [
    Rule("type", "variable", "a variable, its attributes at their defaults but for those "
         "below"),
    Rule("attribute", "variable.objname", "any name nxwright's build takes"),
    Rule("attribute", "variable.sta", "0, a variable of a number, or 1, a variable of a text",
         from_to(0, 1), INVALID_VALUE),
    # A val is 4 bytes, so every val a page file can give is covered.
    Rule("attribute", "variable.val", "any value, from -2147483648 to 2147483647, which a "
         "variable of a text does not write", lambda need: True),
    Rule("attribute", "variable.txt", TXT_WORDS + ", in a variable of a text; any, in one of "
         "a number, which does not write it", lambda need: _of_a_number(need) or text_fits(need)),
    Rule("attribute", "variable.txt_maxl", TXT_MAXL_WORDS + ", in a variable of a text; any, "
         "in one of a number, which does not write it",
         lambda need: _of_a_number(need) or txt_maxl_covered(need), DOES_NOT_FIT),
]
