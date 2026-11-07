"""The number component, as the Nextion Editor 1.68.2 writes it on T and K
(ResearchNotes/tft/number-component.md gives each value, and how it was found),
and on P, where its values lie in its memory as P_ENTRIES gives them
(ResearchNotes/tft/p-series.md).

So far it writes a number at its defaults but for its place, its size, its
val, and the values below. On T and K, its memory is its sta, style,
borderc, borderw, font, what lies behind it, pco, xcen, ycen, val, lenth,
format, isbr, spax, and spay, 24 bytes.

Its sta sets what lies behind it: a crop of a picture, its picc (0), its
bco (1), or a picture, its pic (2). The picture's ID takes its bco's place
in memory and its entry. On P and E, a sta of 3 puts nothing behind it: it
has no entry for what lies behind it, and its memory keeps 0 there. Its
style, its border, has an entry at a sta of 1 alone: none (0), a border of
its borderc and borderw (1), or a 3D border, sunken (2) or raised (3). A
style of 1 gives its borderc and borderw entries too. Each changes the
number of every later entry, so each number is written by the variant of
its sta and its style (variant), and so is an xfloat (xfloat.py).
"""
from functools import lru_cache
import struct

from nxwright.tft.component_types import (BORDER_DARK, BORDER_LIGHT, PLACE_WORDS, SETBRUSH,
                                   attribute_number, background_fill, border,
                                   border_and_background_rules, entry_operand, flat_border,
                                   object_entries, p_entries_by_value, packed_entries,
                                   place_and_size, place_fits_its_record, value_rule)
from nxwright.tft.matching import Rule
from nxwright.tft.reasons import DOES_NOT_FIT

EVENTS = ("down", "up")

# What lies behind a number, by its sta: a crop of a picture, a colour, or a
# picture; and the attribute that gives it. A sta of 3 puts nothing behind
# it, on P and E alone.
_CROP, COLOUR, _PICTURE, _NOTHING = 0, 1, 2, 3
_BACKGROUNDS = {_CROP: "picc", COLOUR: "bco", _PICTURE: "pic"}
# Its styles: no border, a border of one colour, and a 3D border, sunken or
# raised.
_FLAT, BORDERED, _SUNKEN, _RAISED = 0, 1, 2, 3
# Where each value lies in a number's memory, from its base, by what it
# gives.
_PLACES = {"sta": 0, "style": 1, "borderc": 2, "borderw": 4, "font": 5, "background": 6,
           "pco": 8, "xcen": 10, "ycen": 11, "val": 12, "lenth": 16, "format": 17, "isbr": 20,
           "spax": 21, "spay": 22}
# Its starting values on T, K, and F, by what each gives, in their order in
# memory, and their form there. The two values after its val are a number's
# lenth and format, and an xfloat's vvs0 and vvs1 (memory_of).
MEMORY_VALUES = ("sta", "style", "borderc", "borderw", "font", "background", "pco", "xcen",
                 "ycen", "val", "lenth", "format", "isbr", "spax", "spay")
MEMORY_FORMAT = "<BBHBBHHBBiBB2xBBBx"
# The entries every object drawn has, and its sta's, each by its attribute.
_ENTRY = {"type": 0, "id": 1, "vscope": 3, "x": 9, "y": 10, "w": 11, "h": 12, "endx": 13,
          "endy": 14, "sta": 19}
# The entries after its sta's, in order, by what each gives. First come its
# style's entry, at a sta of 1 alone, one left empty, and its border's two,
# at a style of 1 alone, which _Number adds. Then come these, what lies
# behind it among them, and _EMPTY_AFTER empty entries.
_FOLLOWING = ("font", "background", "pco", "xcen", "ycen", "val", "lenth", "format", "isbr",
              "spax", "spay")
_EMPTY_AFTER = 8
# The record's slots that give an entry, and what each gives, but those of
# what lies behind it, its style, and its border (_ATTRIBUTE_SLOTS).
_SLOTS = {1: "vscope", 2: "sta", 16: "pco", 20: "val", 25: "font", 26: "xcen", 27: "ycen",
          41: "lenth", 42: "x", 43: "y", 44: "endx", 45: "endy", 46: "w", 47: "h", 49: "id",
          54: "isbr", 56: "spax", 57: "spay", 62: "type", 64: "format"}
_ATTRIBUTE_SLOTS = {"bco": 4, "picc": 5, "pic": 6, "style": 59, "borderc": 60, "borderw": 61}
# The command that draws a number's val, as its lenth and format give it.
_DRAW_NUMBER = {"T": b"\x09\x11\x04", "K": b"\x09\x13\x04", "F": b"\x09\x15\x04"}

# On P, a number keeps every value in its memory, which starts with what its
# record's head holds (ResearchNotes/tft/p-series.md), then gives its values as
# on T (_PLACES), from 56. Its entries keep T's numbers, by its sta and
# style: by what each gives, (place from its base, highest, lowest, code),
# its font's highest set by component_types.p_table.
_P_PLACES = {"sta": (56, 3, 0, 0x121), "style": (57, 3, 0, 0x121),
             "borderc": (58, 0xFFFF, 0, 0x232), "borderw": (60, 255, 0, 0x131),
             "font": (61, 0, 0, 0x131), "background": (62, 0xFFFF, 0, 0x232),
             "pco": (64, 0xFFFF, 0, 0x232), "xcen": (66, 2, 0, 0x131),
             "ycen": (67, 2, 0, 0x131), "val": (68, 2 ** 31 - 1, -2 ** 31, 0x439),
             "lenth": (72, 15, 0, 0x131), "format": (73, 2, 0, 0x131),
             "isbr": (76, 1, 0, 0x131), "spax": (77, 255, 0, 0x131),
             "spay": (78, 255, 0, 0x131)}
# A number's memory on P.
P_MEMORY_SIZE = 80


class _Number:
    """A number of the sta `sta` and the style `style`, with the members a
    type's module gives (component_types/__init__.py) but MATCHED, and those
    an xfloat takes of it: look, border_blocks, entry_values, and memory_of."""
    EVENTS = EVENTS
    # On P, the frame reads these of the variant, and its P_ENTRIES. A
    # picture's highest is the project's last picture.
    P_MEMORY_SIZE = P_MEMORY_SIZE
    P_LAST_RESOURCE = {"pic": "picture", "picc": "picture"}

    def __init__(self, sta: int, style: int, border_entries: bool):
        self.sta, self.style, self.border_entries = sta, style, border_entries
        # With nothing behind it, it has no entry for what lies behind it, so
        # each later entry is one down. On P, its memory keeps 0 there, as
        # no entry gives a value.
        self._names = {"background": _BACKGROUNDS[sta]} if sta != _NOTHING else {}
        order = (["style"] if sta == COLOUR else []) + [None]
        order += (["borderc", "borderw"] if border_entries else [])
        order += [value for value in _FOLLOWING
                  if value != "background" or sta != _NOTHING]
        self.ENTRIES = _ENTRY["sta"] + 1 + len(order) + _EMPTY_AFTER
        # By what each entry gives, then by the attribute that gives it.
        self._entry_of = dict(_ENTRY)
        self._entry_of.update({value: _ENTRY["sta"] + 1 + number
                               for number, value in enumerate(order) if value is not None})
        self._entry = {self._names.get(value, value): entry
                       for value, entry in self._entry_of.items()}
        self._slots = {slot: self._entry[name] for slot, name in _SLOTS.items()}
        self._slots.update({slot: self._entry[name] for name, slot in _ATTRIBUTE_SLOTS.items()
                            if name in self._entry})
        self.P_ENTRIES = p_entries_by_value(self._entry_of, self._names, _P_PLACES)

    # The frame calls the type's background_fill, which is the plain fill.
    background_fill = staticmethod(background_fill)

    def _operands(self, place):
        """Returns a function that gives the operand of an entry, by what it
        gives."""
        def entry(value: str) -> bytes:
            return entry_operand(place.first_entry + self._entry_of[value])
        return entry

    def _border_width(self, page_object) -> int:
        """Returns its border's width, as its setbrush ends with it: its
        borderw at a style of 1, 1 for a 3D border, and 0 for none."""
        if self.style == BORDERED:
            return attribute_number(page_object, "borderw")
        return 1 if self.style in (_SUNKEN, _RAISED) else 0

    def border_blocks(self, page_object, project, place) -> list:
        """Returns its border's block, after the command that draws its
        val, or none at a style of 0: a border of its borderc's and
        borderw's entries, or a 3D border, dark then light sunken, light
        then dark raised."""
        area = b"%d,%d,%d,%d," % place_and_size(page_object)
        series = project.settings.model.series
        entry = self._operands(place)
        if self.style == BORDERED:
            return [flat_border(area, entry("borderc"), entry("borderw"), series)]
        if self.style == _SUNKEN:
            return [border(area, BORDER_DARK, BORDER_LIGHT, series)]
        if self.style == _RAISED:
            return [border(area, BORDER_LIGHT, BORDER_DARK, series)]
        return []

    def drawing(self, page_object, project, place) -> list:
        """Returns the number's drawing: its setbrush (look), the command
        that draws its val, then its border."""
        entry = self._operands(place)
        return ([self.look(page_object, project, place),
                 _DRAW_NUMBER[project.settings.model.series]
                 + b",".join([entry("val"), entry("lenth"), entry("format")])]
                + self.border_blocks(page_object, project, place))

    def look(self, page_object, project, place) -> bytes:
        """Returns the setbrush of the number `page_object`, or of an
        xfloat, whose look's entries are a number's: its place and size, the
        entries of its look, its sta, and its border's width."""
        x, y, w, h = place_and_size(page_object)
        entry = self._operands(place)
        return (SETBRUSH[project.settings.model.series] + b"%d,%d,%d,%d," % (x, y, w, h)
                + b",".join([entry("font"), entry("pco"), entry("background"), entry("xcen"),
                             entry("ycen"), b"%d" % self.sta, entry("isbr"), entry("spax"),
                             entry("spay"), b"0", b"%d" % self._border_width(page_object)]))

    def data(self, page_object, project, place) -> bytes:
        """Returns the number's entries: where each of its values lies in
        memory (entry_values)."""
        entries = object_entries(page_object, place.object_id)
        entries.update(self.entry_values(place, project))
        return packed_entries(entries, self.ENTRIES, place)

    def entry_values(self, place, project) -> dict:
        """Returns the entries of a number at `place`, or of an xfloat, past
        those every object drawn has: {entry within the type: (where its
        value lies in memory, its highest, its lowest, its code)}."""
        pictures = project.resource_count("picture")
        behind = (0xFFFF if self.sta == COLOUR else pictures - 1, 0, 0x232)
        values = {
            "sta": (2, 0, 0x121), "style": (3, 0, 0x121), "borderc": (0xFFFF, 0, 0x232),
            "borderw": (255, 0, 0x131), "font": (project.resource_count("font") - 1, 0, 0x131),
            "background": behind, "pco": (0xFFFF, 0, 0x232), "xcen": (2, 0, 0x131),
            "ycen": (2, 0, 0x131), "val": (0x7FFFFFFF, -0x80000000, 0x439),
            "lenth": (15, 0, 0x131), "format": (2, 0, 0x131), "isbr": (1, 0, 0x131),
            "spax": (255, 0, 0x131), "spay": (255, 0, 0x131),
        }
        return {entry: (place.base + _PLACES[value],) + values[value]
                for value, entry in self._entry_of.items() if value in values}

    def memory(self, page_object, project) -> bytes:
        """Returns the number's starting values (memory_of), with its lenth
        and format."""
        return self.memory_of(page_object, (attribute_number(page_object, "lenth"),
                                            attribute_number(page_object, "format")))

    def memory_of(self, page_object, digits: tuple) -> bytes:
        """Returns the starting values of the number `page_object`, or of an
        xfloat, whose memory is a number's: its sta and style, its borderc,
        2 bytes, and borderw, zeros but at a style of 1, its font, what lies
        behind it, its bco, pic, or picc, its pco, xcen, ycen, and val, then
        the two bytes of `digits`, a number's lenth and format or an
        xfloat's vvs0 and vvs1, two zeros, its isbr, spax, and spay, and a
        zero. Its style is the variant's: 0 with a picture or a crop behind
        it, as the Nextion Editor writes it there."""
        val = int.from_bytes(page_object.attribute("val") or b"\x00", "little", signed=True)
        values = {name: attribute_number(page_object, self._names.get(name, name))
                  for name in ("font", "background", "pco", "xcen", "ycen", "isbr", "spax",
                               "spay")}
        for name in ("borderc", "borderw"):
            values[name] = attribute_number(page_object, name) if self.border_entries else 0
        values.update({"sta": self.sta, "style": self.style, "val": val,
                       "lenth": digits[0], "format": digits[1]})
        return struct.pack(MEMORY_FORMAT, *(values[name] for name in MEMORY_VALUES))

    def record_slots(self) -> dict:
        """Returns the number's slots in its record: {slot: entry within the
        type}."""
        return dict(self._slots)

    def attribute_place(self, name: str) -> int:
        """Returns the entry, within the type, of the attribute `name`, any
        the type writes. Raises KeyError for another."""
        return self._entry[name]


@lru_cache(maxsize=None)
def _of(sta: int, style: int, border_entries: bool) -> _Number:
    """Returns the variant of a number of the sta `sta` and the style
    `style`, with its border's entries or not, made once."""
    return _Number(sta, style, border_entries)


def variant(page_object) -> _Number:
    """Returns what describes the number `page_object`: the variant of its
    sta and its style. A sta or a style its rules refuse is described as
    one of a colour, or of no border; a style draws at a sta of 1 alone,
    but a style of 1 gives its border's entries, and their values in memory,
    at any sta. A sta of 3, nothing behind it, which its rules take on P and
    E alone, is described as one of nothing behind it on every series."""
    sta, style = (attribute_number(page_object, name) for name in ("sta", "style"))
    sta = sta if sta in _BACKGROUNDS or sta == _NOTHING else COLOUR
    border_entries = style == BORDERED
    style = style if sta == COLOUR and style in (_FLAT, BORDERED, _SUNKEN, _RAISED) else _FLAT
    return _of(sta, style, border_entries)


# The series this module's probes matched (matching.py): T, K in k_probes.py,
# P in p_probes.py, E in e_probes.py, and F in f_probes.py.
SERIES = ("T", "K", "P", "E", "F")

# What the number has matched with probes (matching.py): a number at its
# defaults, on each screen model of T, K, P, E, and F at each rotation, but for
# these.
MATCHED = [
    Rule("type", "number", "a number, its attributes at their defaults but for those below"),
    Rule("attribute", "number.objname", "any name nxwright's build takes"),
    Rule("attribute", "number.x", PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT),
    Rule("attribute", "number.y", PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT),
    Rule("attribute", "number.w", PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT),
    Rule("attribute", "number.h", PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT),
    # A val is 4 bytes, so every val a page file can give is covered.
    Rule("attribute", "number.val", "any value, from -2147483648 to 2147483647"),
    Rule("attribute", "number.font", "any font of the project"),
] + [Rule("attribute", "number." + name, *value_rule(name))
     for name in ("bco", "pco", "xcen", "ycen", "isbr", "spax", "spay", "lenth", "format")] + [
    Rule("attribute", "number." + name, words, covers, reason)
    for name, words, covers, reason in border_and_background_rules()]
