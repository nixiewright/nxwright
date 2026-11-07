"""The gauge component, as the Nextion Editor 1.68.2 writes it on T
(ResearchNotes/tft/gauge-component.md gives each value, and how it was found).

So far it writes a gauge at its defaults but for its place, its size, its
val, the needle's angle in degrees, the values of its needle and colours
that its memory alone gives, and its sta, what lies behind it: a crop of a
picture (0), a colour (1), or a picture (2). T and K refuse its default
sta, 3, which puts nothing behind it. Its drawing draws what lies behind
it, then the command that draws its needle, from the middle of its area, as
long as half its height. Its memory gives its sta, bco, val, format, up, down, left, pco,
pco2, hig, wid, vvs0, vvs1, and vvs2, 24 bytes. A picture's ID, its pic or
its picc, takes its bco's place in memory and its entry, so each gauge is
written by the variant of its sta (variant).

On P, it has no drawing blocks. Its memory gives its values as on T, from
56, but its entries are its own there: every value in its memory has one
but its wid (P_ENTRIES), so code there names them by those numbers
(component_types.code_entry). P and E take its default sta of 3 too. Then
it has no entry for what lies behind it, and each later entry is one
down, 40 in all; its memory keeps 0 where what lies behind it lies.
"""
from functools import lru_cache
import struct

from nxwright.project.attribute_values import number_from_bytes

from nxwright.tft.component_types import (FILL, P_DRAWN_ENTRIES, PIC, PLACE_WORDS, STA_WORDS, XPIC,
                                   background_fill, entry_operand, from_to, object_entries,
                                   packed_entries, place_and_size, place_fits_its_record,
                                   sta_covered, value_rule)
from nxwright.tft.matching import Rule
from nxwright.tft.reasons import DOES_NOT_FIT, INVALID_VALUE

EVENTS = ("down", "up")
ENTRIES = 41

# What lies behind a gauge, by its sta: a crop of a picture, a colour, or a
# picture; and the attribute that gives it. Its default sta, 3, puts nothing
# behind it, which P and E take alone.
_CROP, _COLOUR, _PICTURE, _NOTHING = 0, 1, 2, 3
BACKGROUNDS = {_CROP: "picc", _COLOUR: "bco", _PICTURE: "pic"}
# Where each value with an entry lies in a gauge's memory, from its base,
# by what it gives: what lies behind it, whichever attribute gives it.
_PLACES = {"sta": 0, "background": 2, "val": 4, "pco": 14, "wid": 20}
# Each attribute's entry, within the type, and the entries its needle's
# command gives that the gauge leaves empty.
_ENTRY = {"type": 0, "id": 1, "vscope": 3, "x": 9, "y": 10, "w": 11, "h": 12, "endx": 13,
          "endy": 14, "sta": 19, "background": 20, "val": 21, "pco": 26, "wid": 29}
_EMPTY_ENTRIES = (22, 27, 28)
# The record's slots that give an entry, and which entry, but that of what
# lies behind it (_BACKGROUND_SLOTS).
_SLOTS = {1: "vscope", 2: "sta", 16: "pco", 18: "wid", 20: "val", 42: "x", 43: "y",
          44: "endx", 45: "endy", 46: "w", 47: "h", 49: "id", 62: "type"}
_BACKGROUND_SLOTS = {"bco": 4, "picc": 5, "pic": 6}
# The values its memory gives, in order, and their form there: its sta, a 0
# byte, what lies behind it, whichever attribute gives it, then those its
# needle and its colours give.
MEMORY_VALUES = ("sta", "background", "val", "format", "up", "down", "left", "pco", "pco2",
                 "hig", "wid", "vvs0", "vvs1", "vvs2")
MEMORY_FORMAT = "<BxHHHHHHHHBxBBBB"
# A gauge's attributes at their defaults, as a new one's on T and K.
_DEFAULTS = {"sta": 1, "bco": 65535, "pic": 65535, "picc": 65535, "val": 0, "format": 0,
             "up": 32767, "down": 30, "left": 0, "pco": 1024, "pco2": 63488, "hig": 24,
             "wid": 2, "vvs0": 1, "vvs1": 7, "vvs2": 2}
# The highest val, in degrees.
_HIGHEST_VAL = 360
# The command that draws a gauge's needle, by series, and the zeros that end
# its arguments. K and F number the command as T does.
_NEEDLE = {"T": b"\x09\x0a\x08", "K": b"\x09\x0a\x08", "F": b"\x09\x0a\x08"}
_NEEDLE_END = b",0,0,0,0,0"
# Where its values start in its memory on P: after its record's head and its
# effect's values. They lie as on T (memory).
P_VALUES_AT = 56
# Its entries on P, by number within the type: (name, place from its base,
# highest, lowest, code). Unlike T's, every value in its memory has one but
# its wid, whose entry on T, 29, is empty there; "background" is the
# attribute of its sta's (BACKGROUNDS), its highest set per variant.
_P_ENTRIES = {19: ("sta", 56, 3, 0, 0x121), 20: ("background", 58, None, 0, 0x232),
              21: ("val", 60, _HIGHEST_VAL, 0, 0x232),
              22: ("format", 62, _HIGHEST_VAL, 0, 0x232),
              23: ("up", 64, 32767, -32766, 0x238), 24: ("down", 66, 32767, -32766, 0x238),
              25: ("left", 68, 1024, 0, 0x232), 26: ("pco", 70, 0xFFFF, 0, 0x232),
              27: ("pco2", 72, 0xFFFF, 0, 0x232), 28: ("hig", 74, 100, 0, 0x131),
              30: ("vvs0", 77, 128, 0, 0x131), 31: ("vvs1", 78, 128, 0, 0x131),
              32: ("vvs2", 79, 128, 0, 0x131)}


def _value(page_object, name: str) -> int:
    value = page_object.attribute(name)
    return _DEFAULTS[name] if value is None else number_from_bytes(value)


class _Gauge:
    """A gauge of the sta `sta`, with the members a type's module gives
    (component_types/__init__.py) but MATCHED."""
    EVENTS = EVENTS
    ENTRIES = ENTRIES

    def __init__(self, sta: int):
        self.sta = sta
        self._slots = {slot: _ENTRY[name] for slot, name in _SLOTS.items()}
        background_entry = _ENTRY["background"]
        if sta == _NOTHING:
            # With nothing behind it, on P and E alone, it has no entry for
            # what lies behind it, and each later entry is one down. Its
            # memory keeps 0 there, as no entry gives a value.
            self.background = None
            self._entry = {name: entry for name, entry in _ENTRY.items()
                           if name != "background"}
            self.ENTRIES = ENTRIES - 1
            self.P_ENTRIES = {**P_DRAWN_ENTRIES, **{
                number - (number > background_entry): value
                for number, value in _P_ENTRIES.items() if number != background_entry}}
            return
        self.background = BACKGROUNDS[sta]
        self._entry = {self.background if name == "background" else name: entry
                       for name, entry in _ENTRY.items()}
        self._slots[_BACKGROUND_SLOTS[self.background]] = background_entry
        # On P, what lies behind it has a colour's highest, or the project's
        # last picture (P_LAST_RESOURCE).
        _, at, _, lowest, code = _P_ENTRIES[background_entry]
        highest = 0xFFFF if sta == _COLOUR else None
        self.P_ENTRIES = {**P_DRAWN_ENTRIES, **_P_ENTRIES,
                          background_entry: (self.background, at, highest, lowest, code)}

    # Its memory on P: what its record's head holds and its effect's values,
    # then its values, as on T (memory).
    P_MEMORY_SIZE = 80
    P_LAST_RESOURCE = {"pic": "picture", "picc": "picture"}

    def p_memory_extras(self, page_object, project, place) -> dict:
        """Returns the byte of the gauge's memory on P that no entry gives:
        its wid, as its page file gives it."""
        return {P_VALUES_AT + _PLACES["wid"]: bytes([_value(page_object, "wid")])}

    # The frame calls the type's background_fill, which is the plain fill.
    background_fill = staticmethod(background_fill)

    def drawing(self, page_object, project, place) -> list:
        """Returns the gauge's drawing: what lies behind it, a fill of its
        area with its bco, its pic at its place, or the part of its picc
        where it lies, by its entry 20; then its needle's command: the
        middle of its area, half its height, then the entries of its val,
        plus entry 22, its wid, its pco, and entries 27 and 28, then five
        zeros. Its place and size are written as text, as in `100/2+10`."""
        x, y, w, h = place_and_size(page_object)

        def entry(number: int) -> bytes:
            return entry_operand(place.first_entry + number)

        background = entry(_ENTRY["background"])
        if self.sta == _PICTURE:
            behind = PIC + b"%d,%d," % (x, y) + background
        elif self.sta == _CROP:
            behind = XPIC + b"%d,%d,%d,%d,%d,%d," % (x, y, w, h, x, y) + background
        else:
            behind = FILL + b"%d,%d,%d,%d," % (x, y, w, h) + background
        empty_22, empty_27, empty_28 = (entry(number) for number in _EMPTY_ENTRIES)
        return [behind,
                _NEEDLE[project.settings.model.series] + b"%d/2+%d,%d/2+%d,%d/2," % (w, x, h, y, h)
                + entry(_ENTRY["val"]) + b"+" + empty_22 + b","
                + b",".join([entry(_ENTRY["wid"]), entry(_ENTRY["pco"]), empty_27, empty_28])
                + _NEEDLE_END]

    def data(self, page_object, project, place) -> bytes:
        """Returns the gauge's entries: where its sta, what lies behind it,
        its val, pco, and wid lie in memory. A picture's ID is from 0 to the
        project's last picture. Its needle's other entries are left
        empty."""
        pictures = project.resource_count("picture")
        background = ((0xFFFF, 0, 0x232) if self.sta == _COLOUR
                      else (pictures - 1, 0, 0x232))
        ranges = {"sta": (2, 0, 0x121), "background": background,
                  "val": (_HIGHEST_VAL, 0, 0x232), "pco": (0xFFFF, 0, 0x232),
                  "wid": (20, 1, 0x131)}
        entries = object_entries(page_object, place.object_id)
        entries.update({_ENTRY[name]: (place.base + at,) + ranges[name]
                        for name, at in _PLACES.items()})
        return packed_entries(entries, ENTRIES, place)

    def memory(self, page_object, project) -> bytes:
        """Returns the gauge's starting values: its sta, a zero, what lies
        behind it, its val, format, up, down, left, pco, and pco2, its hig,
        a zero, then its wid, vvs0, vvs1, and vvs2, as its page file gives
        them."""
        values = [_value(page_object, self.background if name == "background" else name)
                  for name in MEMORY_VALUES]
        return struct.pack(MEMORY_FORMAT, *values)

    def record_slots(self) -> dict:
        """Returns the gauge's slots in its record: {slot: entry within the
        type}."""
        return dict(self._slots)

    def attribute_place(self, name: str) -> int:
        """Returns the entry, within the type, of the attribute `name`, any
        the type writes. Raises KeyError for another."""
        return self._entry[name]


@lru_cache(maxsize=None)
def _of(sta: int) -> _Gauge:
    """Returns the variant of a gauge of the sta `sta`, made once."""
    return _Gauge(sta)


def variant(page_object) -> _Gauge:
    """Returns what describes the gauge `page_object`: the variant of its
    sta. The variant of nothing behind it, a sta of 3, describes it on P
    and E alone, where its members on T are never called: nxwright's build
    refuses a sta of 3 on T, K, and F."""
    return _of(_value(page_object, "sta"))


# The series this module's probes matched (matching.py): T, K in k_probes.py,
# P in p_probes.py, E in e_probes.py, and F in f_probes.py.
SERIES = ("T", "K", "P", "E", "F")

# What the gauge has matched with probes (matching.py): a gauge at its
# defaults, on each screen model of T and K at each rotation, and on P and E,
# but for these.
MATCHED = [
    Rule("type", "gauge", "a gauge, its attributes at their defaults but for those below"),
    Rule("attribute", "gauge.objname", "any name nxwright's build takes"),
    Rule("attribute", "gauge.x", PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT),
    Rule("attribute", "gauge.y", PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT),
    Rule("attribute", "gauge.w", PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT),
    Rule("attribute", "gauge.h", PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT),
    Rule("attribute", "gauge.sta", STA_WORDS, sta_covered, INVALID_VALUE),
    Rule("attribute", "gauge.val", "any value, written as it is"),
    Rule("attribute", "gauge.format", "from 0 to 360 degrees, or any other value that fits in "
         "its 2 bytes, written as it is"),
    Rule("attribute", "gauge.up", "any value, written as it is"),
    Rule("attribute", "gauge.down", "any value, written as it is"),
    Rule("attribute", "gauge.left", "any value, written as it is"),
    Rule("attribute", "gauge.hig", "any value, written as it is"),
    Rule("attribute", "gauge.wid", "any value, written as it is"),
] + [Rule("attribute", "gauge." + name, *value_rule(name)) for name in ("bco", "pco", "pco2")
] + [Rule("attribute", "gauge." + name, "any value, written as it is")
     for name in ("vvs0", "vvs1", "vvs2")] + [
    # A picture's ID is 2 bytes in memory, written as it is, whichever
    # picture it is, and only at the sta that shows it.
    Rule("attribute", "gauge." + name, "any value from 0 to 65535, written as it is: a "
         "picture of the project, or 65535 for none") for name in ("pic", "picc")]
