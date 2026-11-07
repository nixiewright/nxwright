"""The button component, as the Nextion Editor 1.68.2 writes it on T and K
(ResearchNotes/tft/button-component.md gives each value, and how it was found),
and on P, where its values lie in its memory as P_ENTRIES gives them
(ResearchNotes/tft/p-series.md).

So far it writes a button at its defaults but for its place, its size, its
text, its txt_maxl, and the values below. On T and K, its memory gives its
font, val, what lies behind it, released and pressed, its pco, pco2, xcen,
ycen, and isbr, then its text: txt_maxl + 1 bytes, the whole rounded up to
4. Its drawing and its entries give its spax and spay. Its val is 1 while
it is pressed: its drawing draws it pressed then, and its down and up
events set it.

Its sta sets what lies behind it: a crop of a picture, its picc and picc2
(0), its bco and bco2 (1), or a picture, its pic and pic2 (2), the second
of each while it is pressed. The pictures' IDs take its bco's and bco2's
places in memory and their entries. On P and E, a sta of 3 puts nothing
behind it: it has no entries for what lies behind it, and its memory keeps
0 there. Its style, its border, has an entry at a sta of 1 alone: none (0),
a border of its borderc and borderw (1), a 3D border, sunken (2) or raised
(3), or, its default, a 3D border that is raised, and sunken while it is
pressed (4). A style of 1 gives its borderc and borderw entries too, which
give their values. Each changes the number of every later entry, so each
button is written by the variant of its sta and its style (variant), and so
is a dual-state button (dual_state_button.py).
"""
from functools import lru_cache
import struct

from nxwright.tft.component_types import (BORDER_DARK, BORDER_LIGHT, PLACE_WORDS, REF, SETBRUSH,
                                   TXT_WORDS, TXT_MAXL_WORDS, attribute_number, background_fill,
                                   border, border_and_background_rules, entry_operand, flat_border,
                                   object_entries, p_entries_by_value, packed_entries,
                                   place_and_size, place_fits_its_record, text_fits,
                                   txt_maxl_covered, value_operand, value_rule, with_txt, zstr)
from nxwright.tft.control_statements import COMPARISONS, comparison_block, jump_block, size_of
from nxwright.tft.matching import Rule
from nxwright.tft.reasons import DOES_NOT_FIT
from nxwright.tft.statements import drawing_operand

EVENTS = ("down", "up")

# What lies behind a button, by its sta: a crop of a picture, a colour, or a
# picture; and the attributes that give it, released and pressed. A sta of 3
# puts nothing behind it, on P and E alone.
_CROP, COLOUR, _PICTURE, _NOTHING = 0, 1, 2, 3
BACKGROUNDS = {_CROP: ("picc", "picc2"), COLOUR: ("bco", "bco2"), _PICTURE: ("pic", "pic2")}
# Its styles: no border, a border of one colour, a 3D border, sunken or
# raised, and its default, a 3D border, raised, and sunken while it is
# pressed.
_FLAT, BORDERED, _SUNKEN, _RAISED, _PRESSED_IN = 0, 1, 2, 3, 4
# Where each value lies in a button's memory, from its base, by what it
# gives.
_PLACES = {"font": 0, "val": 1, "background": 2, "background2": 4, "pco": 6, "pco2": 8,
           "xcen": 10, "ycen": 11, "isbr": 12, "txt": 13}
# Its starting values on T, K, and F, before its txt, by what each gives, in
# their order in memory, and their form there (memory_of).
MEMORY_VALUES = ("font", "val", "background", "background2", "pco", "pco2", "xcen", "ycen",
                 "isbr")
MEMORY_FORMAT = "<BBHHHHBBB"
# The entries every object drawn has, and its sta's, each by its attribute.
_ENTRY = {"type": 0, "id": 1, "vscope": 3, "x": 9, "y": 10, "w": 11, "h": 12, "endx": 13,
          "endy": 14, "sta": 19}
# The entries after its sta's, in order, by what each gives. First come its
# style's entry, at a sta of 1 alone, and its border's two, at a style of 1
# alone, which _Button adds. Then come these, what lies behind it, released
# and pressed, among them, and _EMPTY_AFTER empty entries.
_FOLLOWING = ("font", "background", "background2", "pco", "pco2", "xcen", "ycen", "val", "txt",
              "txt_maxl", "isbr", "spax", "spay")
_EMPTY_AFTER = 8
# The record's slots that give an entry, and what each gives, but those of
# what lies behind it, its style, and its border (_ATTRIBUTE_SLOTS).
_SLOTS = {1: "vscope", 2: "sta", 12: "pco2", 16: "pco", 20: "val", 25: "font", 26: "xcen",
          27: "ycen", 28: "txt", 29: "txt_maxl", 42: "x", 43: "y", 44: "endx", 45: "endy",
          46: "w", 47: "h", 49: "id", 54: "isbr", 56: "spax", 57: "spay", 62: "type"}
_ATTRIBUTE_SLOTS = {"bco": 4, "picc": 5, "pic": 6, "pic2": 17, "picc2": 23, "bco2": 24,
                    "style": 59, "borderc": 60, "borderw": 61}

# The operand the Nextion Editor gives ref in the button's events: the
# button's ID and `+`, then the number 65535.
_REF_NUMBER = 0xFFFF
# What the events set the val to: 1 when pressed, 0 when released.
_PRESSED = {"down": b"1", "up": b"0"}

# On P, a button keeps every value in its memory, which starts with what its
# record's head holds (ResearchNotes/tft/p-series.md). Its entries keep T's
# numbers, by its sta and style, but its values lie in one layout for every
# variant: by what each gives, (place from its base, highest, lowest, code),
# its font's highest and its txt's code set by component_types.p_table.
_P_PLACES = {"sta": (56, 3, 0, 0x121), "style": (57, 4, 0, 0x121),
             "borderc": (58, 0xFFFF, 0, 0x232), "borderw": (60, 255, 0, 0x131),
             "font": (61, 0, 0, 0x131), "background": (62, 0xFFFF, 0, 0x232),
             "background2": (64, 0xFFFF, 0, 0x232), "pco": (66, 0xFFFF, 0, 0x232),
             "pco2": (68, 0xFFFF, 0, 0x232), "xcen": (70, 2, 0, 0x131),
             "ycen": (71, 2, 0, 0x131), "val": (72, 1, 0, 0x131), "txt": (0, 0, 0, 0x3F),
             "txt_maxl": (74, 0xFFFE, 0, 0x222), "isbr": (80, 1, 0, 0x131),
             "spax": (81, 255, 0, 0x131), "spay": (82, 255, 0, 0x131)}
# Its memory on P, and its txt (P_TEXTS): where in its memory the place of
# its txt lies, which no entry gives, and its txt_maxl. Its txt lies after
# its page's components' memory.
P_MEMORY_SIZE = 84
P_TEXTS = {76: ("txt", "txt_maxl", 74)}


class _Button:
    """A button of the sta `sta` and the style `style`, with the members a
    type's module gives (component_types/__init__.py) but MATCHED, and the
    one a dual-state button takes of it: memory_of."""
    EVENTS = EVENTS
    # On P, the frame reads these of the variant, and its P_ENTRIES. A
    # picture's highest is the project's last picture.
    P_MEMORY_SIZE, P_TEXTS = P_MEMORY_SIZE, P_TEXTS
    P_LAST_RESOURCE = {name: "picture" for name in ("pic", "pic2", "picc", "picc2")}
    # On T, K, and F, where its txt lies in its memory, for the frame's
    # scratch image (frame._t_rooms).
    TXT_PLACE = _PLACES["txt"]

    def __init__(self, sta: int, style: int, border_entries: bool):
        self.sta, self.style, self.border_entries = sta, style, border_entries
        # With nothing behind it, it has no entries for what lies behind it,
        # released and pressed, so each later entry is two down. On P, its
        # memory keeps 0 there, as no entry gives a value.
        if sta == _NOTHING:
            self._names = {}
        else:
            released, pressed = BACKGROUNDS[sta]
            self._names = {"background": released, "background2": pressed}
        order = (["style"] if sta == COLOUR else [])
        order += (["borderc", "borderw"] if border_entries else [])
        order += [value for value in _FOLLOWING
                  if value not in ("background", "background2") or sta != _NOTHING]
        self.ENTRIES = _ENTRY["sta"] + 1 + len(order) + _EMPTY_AFTER
        # By what each entry gives, then by the attribute that gives it.
        self._entry_of = dict(_ENTRY)
        self._entry_of.update({value: _ENTRY["sta"] + 1 + number
                               for number, value in enumerate(order)})
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
        """Returns its border's width, as its setbrushes end with it: its
        borderw at a style of 1, 1 for a 3D border, and 0 for none."""
        if self.style == BORDERED:
            return attribute_number(page_object, "borderw")
        return 0 if self.style == _FLAT else 1

    def _border(self, page_object, project) -> list:
        """Returns the border's block that follows both its looks, at a style
        of 0 to 3: none at 0, a border of its borderc and borderw, each
        written as a number, at 1, or a 3D border, dark then light sunken at
        2, light then dark raised at 3."""
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
        """Returns the button's drawing: a comparison of its val with 1, then
        its look pressed and a jump past the other look, then its look
        released, which the comparison jumps to when its val is not 1. Each
        look is setbrush, with its place and size, the entries of its
        colours, its sta, and its border's width. With a colour behind it,
        each look then draws its text with zstr. At its default style, each
        look ends with its own border, sunken while pressed and raised else;
        at another, one border follows both. With a picture or a crop behind
        it, one zstr follows both, and no style draws a border."""
        area = b"%d,%d,%d,%d," % place_and_size(page_object)
        series = project.settings.model.series
        entry = self._operands(place)
        # Its spax and spay are given as numbers, not as their entries.
        spacing = b"%d,%d" % (attribute_number(page_object, "spax"),
                              attribute_number(page_object, "spay"))
        width = b"%d" % self._border_width(page_object)

        def look(pco: str, background: str) -> list:
            setbrush = SETBRUSH[series] + area + b",".join(
                [entry("font"), entry(pco), entry(background), entry("xcen"), entry("ycen"),
                 b"%d" % self.sta, entry("isbr"), spacing, b"0", width])
            return [setbrush] + ([zstr(entry("txt"), series)] if self.sta == COLOUR else [])

        released, pressed = look("pco", "background"), look("pco2", "background2")
        after = ([zstr(entry("txt"), series)] if self.sta != COLOUR
                 else self._border(page_object, project))
        if self.sta == COLOUR and self.style == _PRESSED_IN:
            released.append(border(area, BORDER_LIGHT, BORDER_DARK, series))
            pressed.append(border(area, BORDER_DARK, BORDER_LIGHT, series))
        pressed.append(jump_block(size_of(released)))
        is_pressed = comparison_block(entry("val"), COMPARISONS[series]["=="], b"1",
                                      size_of(pressed))
        return [is_pressed] + pressed + released + after

    def data(self, page_object, project, place) -> bytes:
        """Returns the button's entries: its values, or where they lie in
        memory."""
        maxl = attribute_number(page_object, "txt_maxl")
        base = place.base
        pictures = project.resource_count("picture")
        behind = (0xFFFF if self.sta == COLOUR else pictures - 1, 0, 0x232)
        values = {
            "sta": (self.sta, 2, 0, 0x101), "style": (self.style, 4, 0, 0x101),
            "borderc": (attribute_number(page_object, "borderc"), 0xFFFF, 0, 0x202),
            "borderw": (attribute_number(page_object, "borderw"), 255, 0, 0x101),
            "font": (base + _PLACES["font"], project.resource_count("font") - 1, 0, 0x131),
            "background": (base + _PLACES["background"],) + behind,
            "background2": (base + _PLACES["background2"],) + behind,
            "pco": (base + _PLACES["pco"], 0xFFFF, 0, 0x232),
            "pco2": (base + _PLACES["pco2"], 0xFFFF, 0, 0x232),
            "xcen": (base + _PLACES["xcen"], 2, 0, 0x131),
            "ycen": (base + _PLACES["ycen"], 2, 0, 0x131),
            "val": (base + _PLACES["val"], 1, 0, 0x131),
            # The text's code gives its size in memory, txt_maxl + 1, in its
            # second byte.
            "txt": (base + _PLACES["txt"], 0, 0, (maxl + 1) << 8 | 0x3F),
            "txt_maxl": (maxl, 0xFFFE, 0, 0x202),
            "isbr": (base + _PLACES["isbr"], 1, 0, 0x131),
            "spax": (attribute_number(page_object, "spax"), 255, 0, 0x101),
            "spay": (attribute_number(page_object, "spay"), 255, 0, 0x101),
        }
        entries = object_entries(page_object, place.object_id)
        entries.update({entry: values[value] for value, entry in self._entry_of.items()
                        if value in values})
        return packed_entries(entries, self.ENTRIES, place)

    def memory(self, page_object, project) -> bytes:
        """Returns the button's starting values (memory_of), with its val."""
        return self.memory_of(page_object, attribute_number(page_object, "val"))

    def memory_of(self, page_object, val: int) -> bytes:
        """Returns the starting values of the button `page_object`, or of a
        dual-state button, whose memory is a button's: its font, `val`, what
        lies behind it, released and pressed, its pco, pco2, xcen, ycen, and
        isbr, then its text, padded with zeros."""
        values = {value: val if value == "val"
                  else attribute_number(page_object, self._names.get(value, value))
                  for value in MEMORY_VALUES}
        return with_txt(struct.pack(MEMORY_FORMAT, *(values[value] for value in MEMORY_VALUES)),
                        page_object)

    def record_slots(self) -> dict:
        """Returns the button's slots in its record: {slot: entry within the
        type}."""
        return dict(self._slots)

    def attribute_place(self, name: str) -> int:
        """Returns the entry, within the type, of the attribute `name`, any
        the type writes. Raises KeyError for another."""
        return self._entry[name]

    def event_start(self, page_object, project, place, event: str) -> list:
        """Returns the blocks the Nextion Editor writes at the start of the
        button's down and up events (event_blocks)."""
        return self.event_blocks(place, event)

    def event_blocks(self, place, event: str) -> list:
        """Returns the blocks the Nextion Editor writes at the start of the
        event `event` of the button at `place`, alike on every series: its
        val set to 1 or to 0, then its ref of itself (self_ref). They need
        only these, so that the decoder can write them again from what a TFT
        file keeps."""
        return [entry_operand(place.first_entry + self._entry["val"]) + b"=" + _PRESSED[event],
                self_ref(place)]


@lru_cache(maxsize=None)
def _of(sta: int, style: int, border_entries: bool) -> _Button:
    """Returns the variant of a button of the sta `sta` and the style
    `style`, with its border's entries or not, made once."""
    return _Button(sta, style, border_entries)


def variant(page_object) -> _Button:
    """Returns what describes the button `page_object`, or a dual-state
    button: the variant of its sta and its style. A sta or a style its
    rules refuse is described as one of a colour, or of its default style;
    a style draws at a sta of 1 alone, but a style of 1 gives its border's
    entries at any sta. A sta of 3, nothing behind it, which its rules take
    on P and E alone, is described as one of nothing behind it on every
    series."""
    sta, style = (attribute_number(page_object, name) for name in ("sta", "style"))
    sta = sta if sta in BACKGROUNDS or sta == _NOTHING else COLOUR
    border_entries = style == BORDERED
    if sta != COLOUR:
        style = _FLAT
    elif style not in (_FLAT, BORDERED, _SUNKEN, _RAISED, _PRESSED_IN):
        style = _PRESSED_IN
    return _of(sta, style, border_entries)


def self_ref(place) -> bytes:
    """Returns the ref the Nextion Editor writes in a button's events, and
    in a dual-state button's down event, of the component at `place`: ref,
    its operand the component's ID, `+`, and the number 65535."""
    return REF + b"%d+" % place.object_id + value_operand(_REF_NUMBER)


# The series this module's probes matched (matching.py): T, K in k_probes.py,
# P in p_probes.py, E in e_probes.py, and F in f_probes.py.
SERIES = ("T", "K", "P", "E", "F")

# What the button has matched with probes (matching.py): a button at its
# defaults, on each screen model of T, K, P, E, and F at each rotation, but for
# these.
MATCHED = [
    Rule("type", "button", "a button, its attributes at their defaults but for those below"),
    Rule("attribute", "button.objname", "any name nxwright's build takes"),
    Rule("attribute", "button.x", PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT),
    Rule("attribute", "button.y", PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT),
    Rule("attribute", "button.w", PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT),
    Rule("attribute", "button.h", PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT),
    Rule("attribute", "button.txt", TXT_WORDS, text_fits),
    Rule("attribute", "button.txt_maxl", TXT_MAXL_WORDS, txt_maxl_covered, DOES_NOT_FIT),
    Rule("attribute", "button.font", "any font of the project"),
    # Its val is 1 while it is pressed, so 1 draws it pressed from the start.
    Rule("attribute", "button.val", "any value, written as it is"),
] + [Rule("attribute", "button." + name, *value_rule(name))
     for name in ("bco", "bco2", "pco", "pco2", "xcen", "ycen", "isbr", "spax", "spay")] + [
    Rule("attribute", "button." + name, words, covers, reason)
    for name, words, covers, reason in border_and_background_rules(button=True)]
