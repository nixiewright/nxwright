"""The text component, as the Nextion Editor 1.68.2 writes it on T and K
(ResearchNotes/tft/text-component.md gives each value, and how it was found),
and on P, where its values lie in its memory as P_ENTRIES gives them
(ResearchNotes/tft/p-series.md).

So far it writes a text at its defaults but for its place, its size, its
text, its txt_maxl, and the values below. On T and K, its memory gives its
font, isbr, pco, what lies behind it, xcen, ycen, and pw, then its text:
txt_maxl + 1 bytes, the whole rounded up to 4. Its drawing and its entries
give its spax and spay.

Its sta sets what lies behind it: a crop of a picture, its picc (0), its
bco (1), or a picture, its pic (2). The picture's ID takes its bco's place
in memory and its entry. On P and E, a sta of 3 puts nothing behind it: it
has no entry for what lies behind it, and its memory keeps 0 there. Its
style, its border, has an entry at a sta of 1 alone: none (0), a border of
its borderc and borderw (1), or a 3D border, sunken (2) or raised (3). A
style of 1 gives its borderc and borderw entries too, which give their
values. Each changes the number of every later entry, so each text is
written by the variant of its sta and its style (variant).
"""
from functools import lru_cache
import struct

from nxwright.tft.component_types import (BORDER_DARK, BORDER_LIGHT, PLACE_WORDS, SETBRUSH, TXT_WORDS,
                                   TXT_MAXL_WORDS, attribute_number, background_fill, border,
                                   border_and_background_rules, entry_operand, flat_border,
                                   object_entries, packed_entries, p_entries_by_value,
                                   place_and_size, place_fits_its_record, text_fits,
                                   txt_maxl_covered, value_rule, with_txt, zstr)
from nxwright.tft.matching import Rule
from nxwright.tft.reasons import DOES_NOT_FIT
from nxwright.tft.statements import drawing_operand

EVENTS = ("down", "up")

# What lies behind a text, by its sta: a crop of a picture, a colour, or a
# picture; and the attribute that gives it. A sta of 3 puts nothing behind
# it, on P and E alone.
_CROP, COLOUR, _PICTURE, _NOTHING = 0, 1, 2, 3
_BACKGROUNDS = {_CROP: "picc", COLOUR: "bco", _PICTURE: "pic"}
# Its styles: no border, a border of one colour, and a 3D border, sunken or
# raised.
_FLAT, BORDERED, _SUNKEN, _RAISED = 0, 1, 2, 3
# Where each value lies in a text's memory, from its base, by what it gives.
_PLACES = {"font": 0, "isbr": 1, "pco": 2, "background": 4, "xcen": 6, "ycen": 7, "pw": 8,
           "txt": 9}
# Its starting values on T, K, and F, before its txt, by what each gives,
# and their form in memory.
MEMORY_VALUES = ("font", "isbr", "pco", "background", "xcen", "ycen", "pw")
MEMORY_FORMAT = "<BBHHBBB"
# The entries every object drawn has, and its sta's, each by its attribute.
_ENTRY = {"type": 0, "id": 1, "vscope": 3, "x": 9, "y": 10, "w": 11, "h": 12, "endx": 13,
          "endy": 14, "sta": 19}
# The entries after its sta's, in order, by what each gives. First come its
# style's entry, at a sta of 1 alone, one left empty, and its border's two,
# at a style of 1 alone, which _Text adds. Then come these, what lies behind
# it among them, and _EMPTY_AFTER empty entries.
_FOLLOWING = ("font", "background", "pco", "xcen", "ycen", "pw", "txt", "txt_maxl", "isbr",
              "spax", "spay")
_EMPTY_AFTER = 8
# The record's slots that give an entry, and what each gives, but those of
# what lies behind it, its style, and its border (_ATTRIBUTE_SLOTS).
_SLOTS = {1: "vscope", 2: "sta", 16: "pco", 25: "font", 26: "xcen", 27: "ycen", 28: "txt",
          29: "txt_maxl", 42: "x", 43: "y", 44: "endx", 45: "endy", 46: "w", 47: "h", 49: "id",
          54: "isbr", 56: "spax", 57: "spay", 58: "pw", 62: "type"}
_ATTRIBUTE_SLOTS = {"bco": 4, "picc": 5, "pic": 6, "style": 59, "borderc": 60, "borderw": 61}

# On P, a text keeps every value in its memory, which starts with what its
# record's head holds (ResearchNotes/tft/p-series.md). Its entries keep T's
# numbers, by its sta and style, but its values lie in one layout for every
# variant: by what each gives, (place from its base, highest, lowest, code),
# its font's highest and its txt's code set by component_types.p_table.
_P_PLACES = {"sta": (56, 3, 0, 0x121), "style": (57, 3, 0, 0x121),
             "borderc": (58, 0xFFFF, 0, 0x232), "borderw": (60, 255, 0, 0x131),
             "font": (61, 0, 0, 0x131), "background": (62, 0xFFFF, 0, 0x232),
             "pco": (64, 0xFFFF, 0, 0x232), "xcen": (66, 2, 0, 0x131),
             "ycen": (67, 2, 0, 0x131), "pw": (68, 1, 0, 0x131), "txt": (0, 0, 0, 0x3F),
             "txt_maxl": (70, 0xFFFE, 0, 0x222), "isbr": (76, 1, 0, 0x131),
             "spax": (77, 255, 0, 0x131), "spay": (78, 255, 0, 0x131)}
# Its memory on P, and its txt (P_TEXTS): where in its memory the place of
# its txt lies, which no entry gives, and its txt_maxl. Its txt lies after
# its page's components' memory.
P_MEMORY_SIZE = 84
P_TEXTS = {72: ("txt", "txt_maxl", 70)}


class _Text:
    """A text of the sta `sta` and the style `style`, with the members a
    type's module gives (component_types/__init__.py) but MATCHED. With
    `border_entries`, it has its borderc's and borderw's entries, as a style
    of 1 gives them at any sta, though behind a picture or a crop it draws
    as a style of 0."""
    EVENTS = EVENTS
    # On P, the frame reads these of the variant, and its P_ENTRIES. A
    # picture's highest is the project's last picture.
    P_MEMORY_SIZE, P_TEXTS = P_MEMORY_SIZE, P_TEXTS
    P_LAST_RESOURCE = {"pic": "picture", "picc": "picture"}
    # On T, K, and F, where its txt lies in its memory, for the frame's
    # scratch image (frame._t_rooms).
    TXT_PLACE = _PLACES["txt"]

    def __init__(self, sta: int, style: int, border_entries: bool):
        self.sta, self.style = sta, style
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

    def _border(self, page_object, project) -> list:
        """Returns its border's block, after its zstr, or none at a style of
        0: a border of its borderc and borderw, each written as a number, or
        a 3D border, dark then light sunken, light then dark raised."""
        area = b"%d,%d,%d,%d," % place_and_size(page_object)
        series = project.settings.model.series
        if self.style == BORDERED:
            colour, width = (drawing_operand(str(attribute_number(page_object, name)), project)
                             for name in ("borderc", "borderw"))
            return [flat_border(area, colour, width, series)]
        if self.style == _SUNKEN:
            return [border(area, BORDER_DARK, BORDER_LIGHT, series)]
        if self.style == _RAISED:
            return [border(area, BORDER_LIGHT, BORDER_DARK, series)]
        return []

    def drawing(self, page_object, project, place) -> list:
        """Returns the text's drawing: setbrush, with its place and size, its
        look's entries, its sta, and its border's width; zstr, which draws
        its text; then its border."""
        x, y, w, h = place_and_size(page_object)
        entry = self._operands(place)
        series = project.settings.model.series
        # Its spax and spay are given as numbers, not as their entries.
        setbrush = (SETBRUSH[series] + b"%d,%d,%d,%d," % (x, y, w, h)
                    + b",".join([entry("font"), entry("pco"), entry("background"),
                                 entry("xcen"), entry("ycen"), b"%d" % self.sta, entry("isbr"),
                                 b"%d" % attribute_number(page_object, "spax"),
                                 b"%d" % attribute_number(page_object, "spay"), entry("pw"),
                                 b"%d" % self._border_width(page_object)]))
        return [setbrush, zstr(entry("txt"), series)] + self._border(page_object, project)

    def data(self, page_object, project, place) -> bytes:
        """Returns the text's entries: its values, or where they lie in
        memory."""
        maxl = attribute_number(page_object, "txt_maxl")
        base = place.base
        pictures = project.resource_count("picture")
        behind = (0xFFFF if self.sta == COLOUR else pictures - 1, 0, 0x232)
        values = {
            "sta": (self.sta, 2, 0, 0x101), "style": (self.style, 3, 0, 0x101),
            "borderc": (attribute_number(page_object, "borderc"), 0xFFFF, 0, 0x202),
            "borderw": (attribute_number(page_object, "borderw"), 255, 0, 0x101),
            "font": (base + _PLACES["font"], project.resource_count("font") - 1, 0, 0x131),
            "background": (base + _PLACES["background"],) + behind,
            "pco": (base + _PLACES["pco"], 0xFFFF, 0, 0x232),
            "xcen": (base + _PLACES["xcen"], 2, 0, 0x131),
            "ycen": (base + _PLACES["ycen"], 2, 0, 0x131),
            "isbr": (base + _PLACES["isbr"], 1, 0, 0x131),
            # The text's code gives its size in memory, txt_maxl + 1, in its
            # second byte.
            "txt": (base + _PLACES["txt"], 0, 0, (maxl + 1) << 8 | 0x3F),
            "txt_maxl": (maxl, 0xFFFE, 0, 0x202),
            "pw": (base + _PLACES["pw"], 1, 0, 0x131),
            "spax": (attribute_number(page_object, "spax"), 255, 0, 0x101),
            "spay": (attribute_number(page_object, "spay"), 255, 0, 0x101),
        }
        entries = object_entries(page_object, place.object_id)
        entries.update({entry: values[value] for value, entry in self._entry_of.items()
                        if value in values})
        return packed_entries(entries, self.ENTRIES, place)

    def memory(self, page_object, project) -> bytes:
        """Returns the text's starting values: its font, isbr, pco, what lies
        behind it, its bco, pic, or picc, its xcen, ycen, and pw, then its
        text, padded with zeros."""
        return with_txt(struct.pack(MEMORY_FORMAT, *(
            attribute_number(page_object, self._names.get(value, value))
            for value in MEMORY_VALUES)), page_object)

    def record_slots(self) -> dict:
        """Returns the text's slots in its record: {slot: entry within the
        type}."""
        return dict(self._slots)

    def attribute_place(self, name: str) -> int:
        """Returns the entry, within the type, of the attribute `name`, any
        the type writes. Raises KeyError for another."""
        return self._entry[name]


@lru_cache(maxsize=None)
def _of(sta: int, style: int, border_entries: bool) -> _Text:
    """Returns the variant of a text of the sta `sta` and the style
    `style`, with its border's entries or not, made once."""
    return _Text(sta, style, border_entries)


def variant(page_object) -> _Text:
    """Returns what describes the text `page_object`: the variant of its
    sta and its style. A sta or a style its rules refuse is described as
    one of a colour, or of no border; a style draws at a sta of 1 alone,
    but a style of 1 gives its border's entries at any sta. A sta of 3,
    nothing behind it, which its rules take on P and E alone, is described
    as one of nothing behind it on every series."""
    sta, style = (attribute_number(page_object, name) for name in ("sta", "style"))
    sta = sta if sta in _BACKGROUNDS or sta == _NOTHING else COLOUR
    border_entries = style == BORDERED
    style = style if sta == COLOUR and style in (_FLAT, BORDERED, _SUNKEN, _RAISED) else _FLAT
    return _of(sta, style, border_entries)


# The series this module's probes matched (matching.py): T, K in k_probes.py,
# P in p_probes.py, E in e_probes.py, and F in f_probes.py.
SERIES = ("T", "K", "P", "E", "F")

# What the text has matched with probes (matching.py): a text at its
# defaults, on each screen model of T, K, P, E, and F at each rotation, but for
# these.
MATCHED = [
    Rule("type", "text", "a text, its attributes at their defaults but for those below"),
    Rule("attribute", "text.objname", "any name nxwright's build takes"),
    Rule("attribute", "text.x", PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT),
    Rule("attribute", "text.y", PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT),
    Rule("attribute", "text.w", PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT),
    Rule("attribute", "text.h", PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT),
    Rule("attribute", "text.txt", TXT_WORDS, text_fits),
    Rule("attribute", "text.txt_maxl", TXT_MAXL_WORDS, txt_maxl_covered, DOES_NOT_FIT),
    Rule("attribute", "text.font", "any font of the project"),
] + [Rule("attribute", "text." + name, *value_rule(name))
     for name in ("bco", "pco", "xcen", "ycen", "isbr", "pw", "spax", "spay")] + [
    Rule("attribute", "text." + name, words, covers, reason)
    for name, words, covers, reason in border_and_background_rules()]
