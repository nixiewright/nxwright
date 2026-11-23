"""The progress bar component, as the Nextion Editor 1.68.2 writes it on T
and on K (ResearchNotes/tft/progress-bar-component.md gives each value, and how
it was found), and on P, where it has no drawing blocks and its memory
gives its values as on T, from 56 (P_ENTRIES).

So far it writes a progress bar at its defaults but for its place, its size,
its val, from 0 to 100, its colours, bco and pco, its corners, dis, which way
it fills, dez, and whether it is drawn in colours or pictures, its sta, bpic,
and ppic. Its memory gives its sta, dez, val, dis, bco, and pco, 8 bytes.

Its drawing is code of the Nextion Editor's own: it sets the system variable
sya0 to the filled length, val times its w over 100, or its h when it fills
upward, then draws that much of its area filled, from its left or from its
bottom, and the rest empty. In colours, its sta 0, it fills the parts with
its pco and its bco. In pictures, its sta 1, it shows the same parts of its
ppic and its bpic, with xpic, and its bpic and ppic take the places of its
bco and pco in memory and in its entries. Its dis is then 0 in memory, and
has no entry, so each later entry is numbered one down. So each progress bar
is written by the variant of its sta (variant).
"""
from functools import lru_cache
import struct

from nxwright.project.attribute_values import number_from_bytes

from nxwright.tft.component_types import (FILL, P_DRAWN_ENTRIES, PLACE_WORDS, XPIC, background_fill,
                                   entry_operand, from_to, object_entries, packed_entries,
                                   place_and_size, place_fits_its_record, value_rule)
from nxwright.tft.matching import Rule
from nxwright.tft.reasons import DOES_NOT_FIT, INVALID_VALUE
from nxwright.tft.statements import drawing_operand

EVENTS = ("down", "up")

# How a progress bar is drawn, by its sta: in colours, or in pictures.
_COLOURS, _PICTURES = 0, 1
# The attributes that give its empty and its filled parts, by its sta.
PARTS = {_COLOURS: ("bco", "pco"), _PICTURES: ("bpic", "ppic")}
# The entries of one drawn in colours. One drawn in pictures has one fewer.
_ENTRIES = 33
# Where each value lies in a progress bar's memory, from its base: its empty
# part's colour or picture, then its filled part's.
_PLACES = {"sta": 0, "dez": 1, "val": 2, "dis": 3, "empty": 4, "filled": 6}
# Its starting values on T, K, and F, by what each gives, in their order in
# memory, and their form there (memory).
MEMORY_VALUES = ("sta", "dez", "val", "dis", "empty", "filled")
MEMORY_FORMAT = "<BBBBHH"
# Each attribute's entry, within the type, but those of its parts and dis.
_ENTRY = {"type": 0, "id": 1, "vscope": 3, "x": 9, "y": 10, "w": 11, "h": 12, "endx": 13,
          "endy": 14, "sta": 19, "dez": 20, "val": 21}
# The entries after its val's, in order, by what each gives, by its sta.
_FOLLOWING = {_COLOURS: ("dis", "empty", "filled"), _PICTURES: ("empty", "filled")}
# The record's slots that give an entry, and what each gives, by its sta.
_SLOTS = {1: "vscope", 2: "sta", 20: "val", 30: "dez", 42: "x", 43: "y", 44: "endx",
          45: "endy", 46: "w", 47: "h", 49: "id", 62: "type"}
_PART_SLOTS = {_COLOURS: {4: "empty", 16: "filled", 55: "dis"},
               _PICTURES: {31: "empty", 32: "filled"}}
# A progress bar's attributes at their defaults, as a new one's.
_DEFAULTS = {"sta": 0, "dez": 0, "val": 50, "dis": 25, "bco": 48631, "pco": 1024,
             "bpic": 0xFFFF, "ppic": 0xFFFF}
# The highest val, which the filled length divides by.
_FULL = 100
# Each entry's highest value and code, by the attribute it gives. A
# picture's highest is the project's last picture, which data sets on T,
# and p_table on P (P_LAST_RESOURCE).
_RANGES = {"sta": (1, 0x121), "dez": (1, 0x121), "val": (_FULL, 0x131), "dis": (100, 0x131),
           "bco": (0xFFFF, 0x232), "pco": (0xFFFF, 0x232), "bpic": (None, 0x232),
           "ppic": (None, 0x232)}
# Where its values start in its memory on P: after its record's head and its
# effect's values.
_P_VALUES_AT = 56
# The system variable the drawing works the filled length out in.
_LENGTH = "sya0"


def _value(page_object, name: str) -> int:
    value = page_object.attribute(name)
    return _DEFAULTS[name] if value is None else number_from_bytes(value)


class _ProgressBar:
    """A progress bar of the sta `sta`, with the members a type's module
    gives (component_types/__init__.py) but MATCHED."""
    EVENTS = EVENTS

    def __init__(self, sta: int):
        self.sta = sta
        empty, filled = PARTS[sta]
        self._names = {"empty": empty, "filled": filled}
        following = _FOLLOWING[sta]
        self.ENTRIES = _ENTRIES if sta == _COLOURS else _ENTRIES - 1
        # By what each entry gives, then by the attribute that gives it.
        self._entry_of = dict(_ENTRY)
        self._entry_of.update({value: _ENTRY["val"] + 1 + number
                               for number, value in enumerate(following)})
        self._entry = {self._names.get(value, value): entry
                       for value, entry in self._entry_of.items()}
        self._slots = {slot: self._entry_of[value]
                       for slot, value in {**_SLOTS, **_PART_SLOTS[sta]}.items()}
        # On P, its values lie in its memory as on T, from _P_VALUES_AT, and
        # its entries keep T's numbers.
        self.P_ENTRIES = dict(P_DRAWN_ENTRIES)
        for value, at in _PLACES.items():
            if value in self._entry_of:
                name = self._names.get(value, value)
                highest, code = _RANGES[name]
                self.P_ENTRIES[self._entry_of[value]] = (name, _P_VALUES_AT + at, highest, 0,
                                                         code)

    # Its memory on P: what its record's head holds and its effect's values,
    # then its values, as on T (memory). A picture's highest is the project's
    # last picture.
    P_MEMORY_SIZE = 64
    P_LAST_RESOURCE = {"bpic": "picture", "ppic": "picture"}

    # The frame calls the type's background_fill, which is the plain fill.
    background_fill = staticmethod(background_fill)

    def drawing(self, page_object, project, place) -> list:
        """Returns the progress bar's drawing: sya0 set to its val times its
        width, or its height when it fills upward, over 100; then its filled
        part, from its left or from its bottom, sya0 long, and its empty
        part, the rest: fills of its pco and bco in colours, or the same
        parts of its ppic and bpic in pictures."""
        x, y, w, h = place_and_size(page_object)
        length = drawing_operand(_LENGTH, project)
        upward = _value(page_object, "dez") == 1

        def entry(value: str) -> bytes:
            return entry_operand(place.first_entry + self._entry_of[value])

        def numbers(*parts) -> bytes:
            return b",".join(part if isinstance(part, bytes) else b"%d" % part for part in parts)

        set_length = length + b"=" + entry("val") + b"*%d/%d" % (h if upward else w, _FULL)
        rest = (b"%d-" % h if upward else b"%d-" % w) + length
        if upward:
            # From its bottom, y + h - 1 written out, then +1 less its length.
            bottom = b"%d+1-" % (y + h - 1) + length
            filled = (x, bottom, w, length) + ((0, rest) if self.sta == _PICTURES else ())
            empty = (x, y, w, rest) + ((0, 0) if self.sta == _PICTURES else ())
        else:
            filled = (x, y, length, h) + ((0, 0) if self.sta == _PICTURES else ())
            empty = (b"%d+" % x + length, y, rest, h) + (
                (length, 0) if self.sta == _PICTURES else ())
        command = XPIC if self.sta == _PICTURES else FILL
        return [set_length,
                command + numbers(*filled, entry("filled")),
                command + numbers(*empty, entry("empty"))]

    def data(self, page_object, project, place) -> bytes:
        """Returns the progress bar's entries: where each of its values lies
        in memory. A picture's ID is from 0 to the project's last picture."""
        last = project.resource_count("picture") - 1
        ranges = dict(_RANGES, bpic=(last, 0x232), ppic=(last, 0x232))
        entries = object_entries(page_object, place.object_id)
        for value, at in _PLACES.items():
            if value in self._entry_of:
                most, code = ranges[self._names.get(value, value)]
                entries[self._entry_of[value]] = (place.base + at, most, 0, code)
        return packed_entries(entries, self.ENTRIES, place)

    def memory(self, page_object, project) -> bytes:
        """Returns the progress bar's starting values: its sta, dez, val, and
        dis, 1 byte each, then its empty part's colour or picture and its
        filled part's, 2 bytes each. Drawn in pictures, its dis is 0."""
        values = {value: _value(page_object, self._names.get(value, value))
                  for value in MEMORY_VALUES}
        if self.sta != _COLOURS:
            values["dis"] = 0
        return struct.pack(MEMORY_FORMAT, *(values[value] for value in MEMORY_VALUES))

    def record_slots(self) -> dict:
        """Returns the progress bar's slots in its record: {slot: entry within
        the type}."""
        return dict(self._slots)

    def attribute_place(self, name: str) -> int:
        """Returns the entry, within the type, of the attribute `name`, any
        the type writes. Raises KeyError for another."""
        return self._entry[name]


@lru_cache(maxsize=None)
def _of(sta: int) -> _ProgressBar:
    """Returns the variant of a progress bar of the sta `sta`, made once."""
    return _ProgressBar(sta)


def variant(page_object) -> _ProgressBar:
    """Returns what describes the progress bar `page_object`: the variant of
    its sta. A sta its rules refuse, as nxwright's build does, is described
    as one drawn in colours."""
    sta = _value(page_object, "sta")
    return _of(sta if sta in PARTS else _COLOURS)


# The series this module's probes matched (matching.py): T, K in k_probes.py,
# P in p_probes.py, E in e_probes.py, and F in f_probes.py.
SERIES = ("T", "K", "P", "E", "F")

# What the progress bar has matched with probes (matching.py): a progress bar
# at its defaults, on each screen model of T and K at each rotation, and on P
# and E, but for these.
MATCHED = [
    Rule("type", "progress-bar", "a progress bar, its attributes at their defaults but for "
         "those below"),
    Rule("attribute", "progress-bar.objname", "any name nxwright's build takes"),
    Rule("attribute", "progress-bar.x", PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT),
    Rule("attribute", "progress-bar.y", PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT),
    Rule("attribute", "progress-bar.w", PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT),
    Rule("attribute", "progress-bar.h", PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT),
    Rule("attribute", "progress-bar.val", "any value, written as it is"),
    Rule("attribute", "progress-bar.sta", "0, drawn in colours, or 1, in pictures",
         from_to(0, 1), INVALID_VALUE),
    # nxwright draws the bar upward for a dez of 1, and across for 0.
    # nxwright's build refuses any other value.
    Rule("attribute", "progress-bar.dez", "0, filled across, or 1, upward", from_to(0, 1),
         INVALID_VALUE),
    Rule("attribute", "progress-bar.dis", "any value, written as it is"),
] + [Rule("attribute", "progress-bar." + name, *value_rule(name)) for name in ("bco", "pco")
] + [
    # A picture's ID is 2 bytes in memory, written as it is, whichever
    # picture it is, and only at the sta that shows it.
    Rule("attribute", "progress-bar." + name, "any value from 0 to 65535, written as it is: a "
         "picture of the project, or 65535 for none") for name in ("bpic", "ppic")]
