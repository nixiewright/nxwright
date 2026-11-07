"""The xfloat component, as the Nextion Editor 1.68.2 writes it on T and K
(ResearchNotes/tft/xfloat-component.md gives each value, and how it was found),
and on P, where it is written as a number is there, its vvs0 and vvs1 in
the places of a number's lenth and format.

So far it writes an xfloat at its defaults but for its place, its size, its
val, its vvs0 and vvs1, the digits it shows before and after its point, the
values its memory alone gives, as a number's: its font, bco, pco, xcen,
ycen, isbr, spax, and spay, and its border and what lies behind it, as a
number's: its sta, style, borderc, borderw, pic, and picc. It is written as
the number of its sta and style is (number.variant), but for these. Its
drawing draws its val with the command that draws an xfloat's, from its
val, vvs0, and vvs1. Its vvs0 and vvs1 take the places of a number's lenth
and format, in its entries and its memory, with highest values of their
own. Its record gives them in slots of their own.
"""
from functools import lru_cache

from nxwright.project.attribute_values import number_from_bytes

from nxwright.tft.component_types import (PLACE_WORDS, border_and_background_rules, entry_operand,
                                   object_entries, packed_entries, place_fits_its_record,
                                   value_rule)
from nxwright.tft.component_types import number
from nxwright.tft.matching import Rule
from nxwright.tft.reasons import DOES_NOT_FIT

EVENTS = ("down", "up")

# Its vvs0 and vvs1, by the number's attribute whose place each takes, and
# their highest values.
DIGITS = {"vvs0": ("lenth", 10), "vvs1": ("format", 8)}
# Its record's slots of vvs0 and vvs1, and a number's of lenth and format,
# which it has not.
_SLOTS = {50: "vvs0", 51: "vvs1"}
_NUMBER_SLOTS = (41, 64)
# The command that draws an xfloat's val, as its vvs0 and vvs1 give it, by
# series: K and F number it their own ways.
_DRAW_XFLOAT = {"T": b"\x09\x10\x04", "K": b"\x09\x12\x04", "F": b"\x09\x14\x04"}


class _Xfloat:
    """An xfloat written as the number variant `as_number` is
    (number.variant), with the members a type's module gives
    (component_types/__init__.py) but MATCHED."""
    EVENTS = EVENTS

    def __init__(self, as_number):
        self._number = as_number
        self.ENTRIES = as_number.ENTRIES
        self.background_fill = as_number.background_fill
        # Its vvs0 and vvs1 take the entries of the number's lenth and
        # format.
        self._entry = {name: as_number.attribute_place(of)
                       for name, (of, _) in DIGITS.items()}
        # On P, its memory and entries are the number's there, its vvs0 and
        # vvs1 in the places of the number's lenth and format, with their own
        # highest values.
        in_place_of = {of: (name, highest) for name, (of, highest) in DIGITS.items()}
        self.P_ENTRIES = dict(as_number.P_ENTRIES)
        for entry, (name, at, _, lowest, code) in as_number.P_ENTRIES.items():
            if name in in_place_of:
                own, highest = in_place_of[name]
                self.P_ENTRIES[entry] = (own, at, highest, lowest, code)
        self.P_MEMORY_SIZE = as_number.P_MEMORY_SIZE
        self.P_LAST_RESOURCE = as_number.P_LAST_RESOURCE

    def drawing(self, page_object, project, place) -> list:
        """Returns the xfloat's drawing: the number's setbrush (look), the
        command that draws its val, with the entries of its val, vvs0, and
        vvs1, then the number's border."""
        val = self._number.attribute_place("val")
        operands = [entry_operand(place.first_entry + entry)
                    for entry in (val, self._entry["vvs0"], self._entry["vvs1"])]
        return ([self._number.look(page_object, project, place),
                 _DRAW_XFLOAT[project.settings.model.series] + b",".join(operands)]
                + self._number.border_blocks(page_object, project, place))

    def data(self, page_object, project, place) -> bytes:
        """Returns the xfloat's entries: the number's (entry_values), but
        for its vvs0's and vvs1's highest values."""
        entries = object_entries(page_object, place.object_id)
        entries.update(self._number.entry_values(place, project))
        for name, (_, highest) in DIGITS.items():
            at, _, lowest, code = entries[self._entry[name]]
            entries[self._entry[name]] = (at, highest, lowest, code)
        return packed_entries(entries, self.ENTRIES, place)

    def memory(self, page_object, project) -> bytes:
        """Returns the xfloat's starting values: the number's (memory_of),
        its vvs0 and vvs1 in the places of a number's lenth and format."""
        return self._number.memory_of(page_object, tuple(
            0 if page_object.attribute(name) is None
            else number_from_bytes(page_object.attribute(name)) for name in DIGITS))

    def record_slots(self) -> dict:
        """Returns the xfloat's slots in its record: the number's, but for
        its lenth's and format's, then its vvs0's and vvs1's."""
        slots = {slot: entry for slot, entry in self._number.record_slots().items()
                 if slot not in _NUMBER_SLOTS}
        slots.update({slot: self._entry[name] for slot, name in _SLOTS.items()})
        return slots

    def attribute_place(self, name: str) -> int:
        """Returns the entry, within the type, of the attribute `name`, any
        the type writes: its vvs0's or vvs1's, or the number's, as its
        entries are a number's. Raises KeyError for another, a lenth or a
        format among them."""
        if name in self._entry:
            return self._entry[name]
        if name in (of for of, _ in DIGITS.values()):
            raise KeyError(name)
        return self._number.attribute_place(name)


@lru_cache(maxsize=None)
def _of(as_number) -> _Xfloat:
    """Returns the xfloat written as the number variant `as_number`, made
    once."""
    return _Xfloat(as_number)


def variant(page_object) -> _Xfloat:
    """Returns what describes the xfloat `page_object`: an xfloat written as
    the number of its sta and its style (number.variant)."""
    return _of(number.variant(page_object))


# The series this module's probes matched (matching.py): T, K in k_probes.py,
# P in p_probes.py, E in e_probes.py, and F in f_probes.py.
SERIES = ("T", "K", "P", "E", "F")

# What the xfloat has matched with probes (matching.py): an xfloat at its
# defaults, on each screen model of T and K at each rotation, and on P and E,
# but for these.
MATCHED = [
    Rule("type", "xfloat", "an xfloat, its attributes at their defaults but for those below"),
    Rule("attribute", "xfloat.objname", "any name nxwright's build takes"),
    Rule("attribute", "xfloat.x", PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT),
    Rule("attribute", "xfloat.y", PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT),
    Rule("attribute", "xfloat.w", PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT),
    Rule("attribute", "xfloat.h", PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT),
    # A val is 4 bytes, so every val a page file can give is covered.
    Rule("attribute", "xfloat.val", "any value, from -2147483648 to 2147483647"),
    Rule("attribute", "xfloat.vvs0", "any value, written as it is"),
    Rule("attribute", "xfloat.vvs1", "any value, written as it is"),
    Rule("attribute", "xfloat.font", "any font of the project"),
] + [Rule("attribute", "xfloat." + name, *value_rule(name))
     for name in ("bco", "pco", "xcen", "ycen", "isbr", "spax", "spay")] + [
    Rule("attribute", "xfloat." + name, words, covers, reason)
    for name, words, covers, reason in border_and_background_rules()]
