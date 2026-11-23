"""The checkbox component, as the Nextion Editor 1.68.2 writes it on T
(ResearchNotes/tft/checkbox-component.md gives each value, and how it was found),
and on P, where it has no drawing blocks, no switch of its val in its down
event, and its memory gives its values as on T, from 56 (P_ENTRIES).

So far it writes a checkbox at its defaults but for its place, its size, its
bco, its pco, its val, 1 when it is checked, and its style, with its
border's borderc and borderw. Its memory gives its style, its borderw and
borderc, then its bco, pco, and val, 12 bytes.

Its drawing is code of the Nextion Editor's own. It sets the system variable
sya0 to a quarter of its width, and sya1 to its width less twice sya0. It
fills its area with its bco. When its val is 1, it fills a square inside
it, sya1 wide and high, sya0 in from its top left, with its pco. Then it
draws its border, by its style: none (0), one of its borderc and borderw
(1), or a 3D border, sunken (2) or raised (3). Its down event starts with
code that switches its val between 0 and 1.

A style of 1 gives its borderw and borderc entries of their own, before
its bco's, so each later entry is numbered two on. So each checkbox is
written by the variant of its style (variant).
"""
from functools import lru_cache
import struct

from nxwright.project.attribute_values import number_from_bytes

from nxwright.tft.component_types import (BORDER_DARK, BORDER_LIGHT, FILL, P_DRAWN_ENTRIES, PLACE_WORDS,
                                   background_fill, border, entry_operand, flat_border, from_to,
                                   object_entries, packed_entries, place_and_size,
                                   place_fits_its_record, value_rule)
from nxwright.tft.control_statements import COMPARISONS, comparison_block, jump_block, size_of
from nxwright.tft.matching import Rule
from nxwright.tft.reasons import DOES_NOT_FIT, INVALID_VALUE
from nxwright.tft.statements import drawing_operand

EVENTS = ("down", "up")

# Its styles: no border, a border of one colour, and a 3D border, sunken or
# raised. nxwright's descriptions name the first "flat" and the second "a
# border".
_FLAT, BORDERED, _SUNKEN, _RAISED = 0, 1, 2, 3
# The entries of a checkbox of another style than 1. One of style 1 has two
# more.
_ENTRIES = 31
# Where each value lies in a checkbox's memory, from its base on T, and from
# _P_VALUES_AT on P, after its record's head and its effect's values.
_PLACES = {"style": 0, "borderw": 1, "borderc": 2, "bco": 4, "pco": 6, "val": 8}
_P_VALUES_AT = 56
# Its starting values on T, K, and F, in their order in memory, and their
# form there (memory).
MEMORY_VALUES = ("style", "borderw", "borderc", "bco", "pco", "val")
MEMORY_FORMAT = "<BBHHHB3x"
# Each attribute's entry, within the type, up to its style's.
_ENTRY = {"type": 0, "id": 1, "vscope": 3, "x": 9, "y": 10, "w": 11, "h": 12, "endx": 13,
          "endy": 14, "style": 19}
# The entries after its style's, in order: of style 1, its borderw and
# borderc come before its bco, so each later entry is two on.
_FOLLOWING = {BORDERED: ("borderw", "borderc", "bco", "pco", "val")}
_PLAIN = ("bco", "pco", "val")
# Each entry's highest value and code, by the attribute it gives.
_RANGES = {"style": (3, 0x121), "borderw": (255, 0x131), "borderc": (0xFFFF, 0x232),
           "bco": (0xFFFF, 0x232), "pco": (0xFFFF, 0x232), "val": (1, 0x131)}
# The record's slots that give an entry, and what each gives; a checkbox of
# style 1 gives its borderc in slot 60 and its borderw in slot 61 too.
_SLOTS = {1: "vscope", 4: "bco", 16: "pco", 20: "val", 42: "x", 43: "y", 44: "endx",
          45: "endy", 46: "w", 47: "h", 49: "id", 59: "style", 62: "type"}
_BORDER_SLOTS = {60: "borderc", 61: "borderw"}
# A checkbox's attributes at their defaults, as a new one's.
_DEFAULTS = {"style": _SUNKEN, "borderw": 2, "borderc": 0, "bco": 0xFFFF, "pco": 0, "val": 1}
# The system variables the drawing works the inner square out in: where it
# starts, from the checkbox's top left, and its side.
_INSET, _SIDE = "sya0", "sya1"


def _value(page_object, name: str) -> int:
    value = page_object.attribute(name)
    return _DEFAULTS[name] if value is None else number_from_bytes(value)


class _Checkbox:
    """A checkbox of the style `style`, with the members a type's module
    gives (component_types/__init__.py) but MATCHED."""
    EVENTS = EVENTS

    def __init__(self, style: int):
        self.style = style
        following = _FOLLOWING.get(style, _PLAIN)
        self.ENTRIES = _ENTRIES + len(following) - len(_PLAIN)
        self._entry = dict(_ENTRY)
        self._entry.update({name: _ENTRY["style"] + 1 + number
                            for number, name in enumerate(following)})
        slots = {**_SLOTS, **(_BORDER_SLOTS if style == BORDERED else {})}
        self._slots = {slot: self._entry[name] for slot, name in slots.items()}
        # On P, its values lie in its memory as on T, from _P_VALUES_AT.
        self.P_ENTRIES = {**P_DRAWN_ENTRIES, **{
            entry: (name, _P_VALUES_AT + _PLACES[name], _RANGES[name][0], 0, _RANGES[name][1])
            for name, entry in self._entry.items() if name in _PLACES}}

    # Its memory on P: what its record's head holds and its effect's values,
    # then its values, as on T (memory).
    P_MEMORY_SIZE = 68

    # The frame calls the type's background_fill, which is the plain fill.
    background_fill = staticmethod(background_fill)

    def drawing(self, page_object, project, place) -> list:
        """Returns the checkbox's drawing: sya0 set to its width over 4, sya1
        to its width less twice sya0, a fill of its area with its bco, a
        comparison of its val with 1, which jumps past the next fill when it
        fails, a fill of the square inside it with its pco, then its border.
        A style of 0 has no border. A style of 1 has one of its borderc and
        borderw. A style of 2 has a 3D border, dark then light, sunken, and
        a style of 3 one light then dark, raised."""
        x, y, w, h = place_and_size(page_object)
        series = project.settings.model.series
        inset, side = (drawing_operand(name, project) for name in (_INSET, _SIDE))

        def entry(name: str) -> bytes:
            return entry_operand(place.first_entry + self._entry[name])

        area = b"%d,%d,%d,%d," % (x, y, w, h)
        square = (FILL + b"%d+" % x + inset + b",%d+" % y + inset + b"," + side + b"," + side
                  + b"," + entry("pco"))
        blocks = [inset + b"=%d/4" % w, side + b"=%d-" % w + inset + b"-" + inset,
                  FILL + area + entry("bco"),
                  comparison_block(entry("val"), COMPARISONS[series]["=="], b"1",
                                   size_of([square])),
                  square]
        if self.style == BORDERED:
            blocks.append(flat_border(area, entry("borderc"), entry("borderw"), series))
        elif self.style == _SUNKEN:
            blocks.append(border(area, BORDER_DARK, BORDER_LIGHT, series))
        elif self.style == _RAISED:
            blocks.append(border(area, BORDER_LIGHT, BORDER_DARK, series))
        return blocks

    def data(self, page_object, project, place) -> bytes:
        """Returns the checkbox's entries: where each of its values lies in
        memory."""
        entries = object_entries(page_object, place.object_id)
        entries.update({entry: (place.base + _PLACES[name], _RANGES[name][0], 0,
                                _RANGES[name][1])
                        for name, entry in self._entry.items() if name in _PLACES})
        return packed_entries(entries, self.ENTRIES, place)

    def memory(self, page_object, project) -> bytes:
        """Returns the checkbox's starting values: its style, then its borderw,
        1 byte, and its borderc, 2 bytes, zeros but at a style of 1, its bco
        and pco, 2 bytes each, its val, then three 0 bytes."""
        values = {name: _value(page_object, name) for name in MEMORY_VALUES}
        if self.style != BORDERED:
            values["borderw"] = values["borderc"] = 0
        return struct.pack(MEMORY_FORMAT, *(values[name] for name in MEMORY_VALUES))

    def record_slots(self) -> dict:
        """Returns the checkbox's slots in its record: {slot: entry within the
        type}."""
        return dict(self._slots)

    def attribute_place(self, name: str) -> int:
        """Returns the entry, within the type, of the attribute `name`, any
        the type writes. Raises KeyError for another."""
        return self._entry[name]

    def event_start(self, page_object, project, place, event: str) -> list:
        """Returns the blocks the Nextion Editor writes at the start of the
        checkbox's down event, which switch its val (val_switch). Its up
        event has none."""
        if event != "down":
            return []
        return val_switch(entry_operand(place.first_entry + self._entry["val"]),
                          project.settings.model.series)


@lru_cache(maxsize=None)
def _of(style: int) -> _Checkbox:
    """Returns the variant of a checkbox of the style `style`, made once."""
    return _Checkbox(style)


def variant(page_object) -> _Checkbox:
    """Returns what describes the checkbox `page_object`: the variant of its
    style. A style its rule refuses is described as one of its default,
    sunken."""
    style = _value(page_object, "style")
    return _of(style if style in (_FLAT, BORDERED, _SUNKEN, _RAISED) else _SUNKEN)


# The radio's down event starts with these blocks too. They are here rather
# than in component_types/__init__.py, which control_statements imports.
def val_switch(val: bytes, series: str) -> list:
    """Returns the blocks on `series` that switch the val whose operand is
    `val` between 0 and 1, as a checkbox's and a radio's down events start:
    a comparison of the val with 1, which jumps past the next two blocks
    when it fails, the val set to 0, a jump past the next block, then the
    val set to 1."""
    unchecked, checked = val + b"=0", val + b"=1"
    jump = jump_block(size_of([checked]))
    return [comparison_block(val, COMPARISONS[series]["=="], b"1", size_of([unchecked, jump])),
            unchecked, jump, checked]


# The series this module's probes matched (matching.py): T, K in k_probes.py,
# P in p_probes.py, E in e_probes.py, and F in f_probes.py.
SERIES = ("T", "K", "P", "E", "F")

# What the checkbox has matched with probes (matching.py): a checkbox at its
# defaults, on each screen model of T and K at each rotation, and on P and E,
# but for these.
MATCHED = [
    Rule("type", "checkbox", "a checkbox, its attributes at their defaults but for those below"),
    Rule("attribute", "checkbox.objname", "any name nxwright's build takes"),
    Rule("attribute", "checkbox.x", PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT),
    Rule("attribute", "checkbox.y", PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT),
    Rule("attribute", "checkbox.w", PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT),
    Rule("attribute", "checkbox.h", PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT),
    Rule("attribute", "checkbox.bco", *value_rule("bco")),
    Rule("attribute", "checkbox.pco", *value_rule("pco")),
    Rule("attribute", "checkbox.val", "any value, written as it is: its drawing compares it "
         "with 1 as the screen runs"),
    Rule("attribute", "checkbox.style", "0, no border, 1, a border of its borderc and borderw, "
         "or 2 or 3, a 3D border, sunken or raised", from_to(0, 3), INVALID_VALUE),
    Rule("attribute", "checkbox.borderc", *value_rule("borderc")),
    Rule("attribute", "checkbox.borderw", *value_rule("borderw")),
]
