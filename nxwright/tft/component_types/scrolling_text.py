"""The scrolling text component, as the Nextion Editor 1.68.2 writes it on T
and K (ResearchNotes/tft/scrolling-text-component.md gives each value, and how
it was found).

So far it writes a scrolling text at its defaults but for its place, its
size, its txt, its txt_maxl, its font, the attributes its memory alone
gives: its dir, dis, tim, en, bco, pco, xcen, ycen, isbr, spax, spay, and
vvs0 to vvs3, what lies behind it, its sta, pic, and picc, and its border,
its style, borderc, and borderw. A scrolling text draws its txt at a
position that moves on its own, as a timer runs: its dir gives which way,
its dis how far each time, and its tim how often. Its en starts and stops
it. The Nextion Editor writes the code that moves it. That code is the same
for every scrolling text but for its place and size, its entries, its ID,
its border's width, and the numbers of its "S " blocks:

  - its drawing: setbrush, with its place, its size, and its look's
    entries; zstr at the txt's position, its vvs0 and vvs1, and its size,
    its vvs2 and vvs3; its border, unless its style is 0; the command
    timerset, which starts its timer; then an "L " block into its timer's
    code (load_start);
  - in its page's load section: code that measures its txt and sets where
    the scrolling starts, by its dir; an "L " block past the rest; then its
    timer's code, between two "S " blocks. While its en is 1, that code
    measures the txt, moves it by dis in its dir, brings it back to the
    other side of its area once it leaves it, and refreshes it. Else it
    stops the timer.

Its memory, 36 bytes, gives its sta, style, borderc, borderw, font, bco,
pco, xcen, ycen, dir, dis, tim, en, txt_maxl, where its txt lies, isbr,
spax, spay, and vvs0 to vvs3: the txt's position as it moves, and its
measured size. Its txt lies after its page's components' memory
(page_text, component_types/__init__.py), as a QR code's does: txt_maxl +
1 bytes, rounded up to 4.

Its sta sets what lies behind it: a crop of a picture, its picc (0), its
bco (1), or a picture, its pic (2). The picture's ID takes its bco's place
in memory and its entry. On P and E, a sta of 3 puts nothing behind it: it
has no entry for what lies behind it, and its memory keeps 0 there. Its
style, its border, has an entry at a sta of 1 alone: none (0), a border of
its borderc and borderw (1), or a 3D border, sunken (2) or raised (3). A
style of 1 gives its borderc and borderw entries too. Each changes the
number of every later entry, which its timer's code gives too, so each
scrolling text is written by the variant of its sta and its style
(variant).

On P, the Nextion Editor writes none of that code: a scrolling text has no
drawing blocks, its page's load section gets `init` and its ID alone, and
it takes no "S " block numbers. Its memory is 92 bytes: what its record's
head holds and its effect's values, 56 bytes, then its memory on T. Its
entries keep T's numbers (P_ENTRIES).
"""
from functools import lru_cache
import struct

from nxwright.project.attribute_values import number_from_bytes

from nxwright.tft.component_types import (BORDER_DARK, BORDER_LIGHT, P_DRAWN_ENTRIES, PLACE_WORDS, REF,
                                   SETBRUSH, SERIES_WRITTEN_AS_P, STA_WORDS, TXT_WORDS,
                                   TXT_MAXL_WORDS, background_fill, border, entry_operand,
                                   flat_border, from_to, object_entries, packed_entries,
                                   place_and_size, place_fits_its_record, sta_covered, text_fits,
                                   txt_maxl_covered, value_operand, value_rule, with_txt, zstr)
from nxwright.tft.component_types.timer import CODE_PLACE, TIMER_EVENT_START, TIMERSET
from nxwright.tft.control_statements import (COMPARISONS, comparison_block, jump_block, size_of,
                                      threaded)
from nxwright.tft.instructions.undocumented_commands import init_block
from nxwright.tft.matching import Rule
from nxwright.tft.reasons import DOES_NOT_FIT, INVALID_VALUE
from nxwright.tft.statements import system_variable_operand

EVENTS = ("down", "up")
# The numbers a scrolling text takes in the first pass that numbers its
# page's "S " blocks (label_numbers.py): one unused, then the
# start and the end of its timer's code.
FIRST_PASS_NUMBERS = 3

# What lies behind a scrolling text, by its sta: a crop of a picture, a
# colour, or a picture; and the attribute that gives it. A sta of 3 puts
# nothing behind it, on P and E alone.
_CROP, COLOUR, _PICTURE, _NOTHING = 0, 1, 2, 3
_BACKGROUNDS = {_CROP: "picc", COLOUR: "bco", _PICTURE: "pic"}
# Its styles: no border, a border of one colour, and a 3D border, sunken or
# raised.
_FLAT, BORDERED, _SUNKEN, _RAISED = 0, 1, 2, 3
# The entries every object drawn has, and its sta's, each by its attribute.
_ENTRY = {"type": 0, "id": 1, "vscope": 3, "x": 9, "y": 10, "w": 11, "h": 12, "endx": 13,
          "endy": 14, "sta": 19}
# The entries after its sta's, in order, by what each gives. First come
# its style's entry, at a sta of 1 alone, one left empty, and its border's
# two, at a style of 1 alone, which _ScrollingText adds. Then come these,
# what lies behind it among them, and _EMPTY_AFTER empty entries.
_FOLLOWING = ("font", "background", "pco", "xcen", "ycen", "dir", "dis", "tim", "en", "txt",
              "txt_maxl", "isbr", "spax", "spay", "vvs0", "vvs1", "vvs2", "vvs3")
_EMPTY_AFTER = 8
# The record's slots that give an entry, and what each gives, but those of
# what lies behind it, its style, and its border (_ATTRIBUTE_SLOTS).
_SLOTS = {1: "vscope", 2: "sta", 16: "pco", 25: "font", 26: "xcen", 27: "ycen", 28: "txt",
          29: "txt_maxl", 33: "tim", 34: "en", 42: "x", 43: "y", 44: "endx", 45: "endy",
          46: "w", 47: "h", 48: "dir", 49: "id", 50: "vvs0", 51: "vvs1", 52: "vvs2",
          53: "vvs3", 54: "isbr", 55: "dis", 56: "spax", 57: "spay", 62: "type"}
_ATTRIBUTE_SLOTS = {"bco": 4, "picc": 5, "pic": 6, "style": 59, "borderc": 60, "borderw": 61}
# Where each value lies in a scrolling text's memory, from its base, by what
# it gives.
_PLACES = {"sta": 0, "style": 1, "borderc": 2, "borderw": 4, "font": 5, "background": 6,
           "pco": 8, "xcen": 10, "ycen": 11, "dir": 12, "dis": 13, "tim": 14, "en": 16,
           "txt_maxl": 18, "isbr": 24, "spax": 25, "spay": 26, "vvs0": 28, "vvs1": 30,
           "vvs2": 32, "vvs3": 34}
# Each entry's highest value, lowest value, and code, by the attribute it
# gives; a font's highest is the project's last font, and a picture's ID's
# the project's last picture.
_VALUES = {"sta": (2, 0, 0x121), "style": (3, 0, 0x121), "borderc": (0xFFFF, 0, 0x232),
           "borderw": (255, 0, 0x131), "bco": (0xFFFF, 0, 0x232),
           "pco": (0xFFFF, 0, 0x232), "xcen": (2, 0, 0x131), "ycen": (2, 0, 0x131),
           "dir": (3, 0, 0x131), "dis": (50, 2, 0x131), "tim": (65534, 80, 0x232),
           "en": (1, 0, 0x131), "txt_maxl": (65534, 0, 0x222), "isbr": (1, 0, 0x131),
           "spax": (255, 0, 0x131), "spay": (255, 0, 0x131),
           **{name: (2 ** 31 - 1, -2 ** 31, 0x238) for name in ("vvs0", "vvs1", "vvs2", "vvs3")}}
# Where its values start in its memory on P: after its record's head and its
# effect's values.
_P_VALUES_AT = 56
# The highest values, lowest values, and codes on P that are not T's
# (_VALUES): its sta's, and those whose highest p_table sets, the project's
# last font or picture (P_LAST_RESOURCE).
_P_VALUES = {"sta": (3, 0, 0x121), "font": (None, 0, 0x131), "pic": (None, 0, 0x232),
             "picc": (None, 0, 0x232)}
# Where the place of its txt lies in its memory, from its base.
_TXT_PLACE = 20
# Its starting values on T, K, and F, in their order in memory, and their
# form there (memory_at): its txt_place is where its txt lies.
MEMORY_VALUES = ("sta", "style", "borderc", "borderw", "font", "background", "pco", "xcen",
                 "ycen", "dir", "dis", "tim", "en", "txt_maxl", "txt_place", "isbr", "spax",
                 "spay", "vvs0", "vvs1", "vvs2", "vvs3")
MEMORY_FORMAT = "<BBHBBHHBBBBHBxHIBBBx4H"
# The command that measures a text, by series, into a width and a height.
_MEASURE = {"T": b"\x09\x12\x08", "K": b"\x09\x13\x08", "F": b"\x09\x13\x08"}
# A scrolling text's attributes at their defaults, as a new one's.
_DEFAULTS = {"sta": 1, "style": 0, "borderc": 0, "borderw": 0, "font": 0, "bco": 0xFFFF,
             "pic": 0xFFFF, "picc": 0xFFFF, "pco": 0, "xcen": 1, "ycen": 1, "dir": 1, "dis": 4,
             "tim": 150, "en": 1, "isbr": 0, "spax": 0, "spay": 0, "vvs0": 0, "vvs1": 0,
             "vvs2": 0, "vvs3": 0}
# What the scrolling's code gives where a position is not used: the most a
# position takes.
_UNUSED = 0x7FFF
# The block the Nextion Editor writes after the refresh, a capital E alone.
_AFTER_REF = b"E"


def _value(page_object, name: str) -> int:
    """Returns the scrolling text's attribute `name`, or its default."""
    value = page_object.attribute(name)
    return _DEFAULTS[name] if value is None else number_from_bytes(value)


def _code_place(place: int) -> bytes:
    """Returns the "L " block of the place `place` in the user code."""
    return CODE_PLACE + value_operand(place)


def _event_start(first: int) -> bytes:
    """Returns the "S " block that starts the scrolling text's timer code,
    one past `first`, where its numbers start in the first pass that
    numbers its page's "S " blocks (ObjectPlace.timer_numbers)."""
    return TIMER_EVENT_START + value_operand(first + 1)


def _chain(cases: list) -> list:
    """Returns an if and its else ifs, as the Nextion Editor writes them:
    `cases` are (left, comparison, right, blocks). Each comparison jumps past
    its blocks when it fails, and each case but the last ends with a jump
    block past the chain."""
    blocks, ends = [], []
    for number, (left, comparison, right, body) in enumerate(cases):
        last = number == len(cases) - 1
        guarded = size_of(body) + (0 if last else size_of([jump_block(0)]))
        blocks.append(comparison_block(left, comparison, right, guarded))
        blocks += body
        if not last:
            ends.append(len(blocks))
            blocks.append(jump_block(0))
    for at in ends:
        blocks[at] = jump_block(size_of(blocks[at + 1:]))
    return blocks


class _ScrollingText:
    """A scrolling text of the sta `sta` and the style `style`, with the
    members a type's module gives (component_types/__init__.py) but
    MATCHED."""
    EVENTS = EVENTS
    FIRST_PASS_NUMBERS = FIRST_PASS_NUMBERS
    # The frame builds the page twice: the drawing jumps into the scrolling
    # text's code in the load section, which comes later (frame.py).
    DRAWING_JUMPS_TO_LOAD = True

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
        # On P, its values lie in its memory as on T, from _P_VALUES_AT, and
        # its entries keep T's numbers. Its txt's entry gives where its txt
        # lies (P_TEXTS).
        self.P_ENTRIES = dict(P_DRAWN_ENTRIES)
        for value, entry in self._entry_of.items():
            name = self._names.get(value, value)
            if value == "txt":
                self.P_ENTRIES[entry] = ("txt", 0, 0, 0, 0x3F)
            elif value in _PLACES:
                highest, lowest, code = _P_VALUES.get(name) or _VALUES[name]
                self.P_ENTRIES[entry] = (name, _P_VALUES_AT + _PLACES[value], highest, lowest,
                                         code)

    # Its memory on P: what its record's head holds and its effect's values,
    # then its memory on T; its txt lies after its page's components' memory.
    P_MEMORY_SIZE = 92
    P_TEXTS = {_P_VALUES_AT + _TXT_PLACE: ("txt", "txt_maxl", _P_VALUES_AT + _PLACES["txt_maxl"])}
    P_LAST_RESOURCE = {"pic": "picture", "picc": "picture"}

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
            return _value(page_object, "borderw")
        return 1 if self.style in (_SUNKEN, _RAISED) else 0

    def _border(self, page_object, project, place) -> list:
        """Returns its border's block, after its zstr, or none at a style of
        0: a border of its borderc and borderw, or a 3D border, dark then light
        sunken, light then dark raised."""
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
        """Returns the scrolling text's drawing: setbrush, with its place and
        size, its look's entries, its sta, and its border's width; zstr at
        the txt's position; its border; timerset, which starts its timer;
        then the "L " block into its timer's code, past the "S " block that
        starts it (load_start)."""
        x, y, w, h = place_and_size(page_object)
        series = project.settings.model.series
        entry = self._operands(place)
        setbrush = (SETBRUSH[series] + b"%d,%d,%d,%d," % (x, y, w, h)
                    + b",".join([entry("font"), entry("pco"), entry("background"),
                                 entry("xcen"), entry("ycen"), b"%d" % self.sta, entry("isbr"),
                                 entry("spax"), entry("spay"), b"0",
                                 b"%d" % self._border_width(page_object)]))
        area = [entry("vvs0"), entry("vvs1"), entry("vvs2"), entry("vvs3")]
        before_code = (self._starting_blocks(page_object, series, place)
                       + [_code_place(0), _event_start(place.timer_numbers[0])])
        code = (place.load_place or 0) + size_of(before_code)
        return ([setbrush, zstr(entry("txt"), series, area)]
                + self._border(page_object, project, place)
                + [TIMERSET[series] + entry("en") + b",%d," % place.object_id + entry("tim")
                   + b",0", _code_place(code)])

    def load_start(self, page_object, project, place, places: dict) -> list:
        """Returns the blocks the scrolling text adds to its page's load
        section, from place.load_place: the code that sets where the
        scrolling starts, an "L " block past the rest, then its timer's code
        between two "S " blocks. While its en is 1, that code moves the txt
        by dis in its dir, brings it back once it leaves the area, and
        refreshes the scrolling text. Else it stops the timer. On P, it is
        `init` and the scrolling text's ID alone."""
        series = project.settings.model.series
        if series in SERIES_WRITTEN_AS_P:
            return [init_block(place.object_id)]
        return self.load_blocks(page_object, series, place, place.timer_numbers[0])

    def load_blocks(self, page_object, series: str, place, first: int) -> list:
        """Returns the blocks the scrolling text `page_object` at `place`
        adds to its page's load section on `series`, T, K, or F
        (load_start), where `first` is where its numbers start in the first
        pass that numbers its page's "S " blocks (label_numbers.py). They
        need only these, so that the decoder can write them again from what
        a TFT file keeps."""
        starting = self._starting_blocks(page_object, series, place)
        rest = ([_event_start(first)]
                + self._timer_code(page_object, series, place)
                + [TIMER_EVENT_START + value_operand(first + 2)])
        # The "L " block jumps past the rest, to the block after these.
        after = (place.load_place or 0) + size_of(starting + [_code_place(0)] + rest)
        return starting + [_code_place(after)] + rest

    def data(self, page_object, project, place) -> bytes:
        """Returns the scrolling text's entries: where each of its values
        lies in memory."""
        maxl = number_from_bytes(page_object.attribute("txt_maxl"))
        fonts = project.resource_count("font")
        pictures = project.resource_count("picture")
        values = dict(_VALUES, font=(fonts - 1, 0, 0x131), pic=(pictures - 1, 0, 0x232),
                      picc=(pictures - 1, 0, 0x232))
        entries = object_entries(page_object, place.object_id)
        entries.update({self._entry_of[value]: (place.base + at,)
                        + values[self._names.get(value, value)]
                        for value, at in _PLACES.items() if value in self._entry_of})
        # Its txt lies after the page's components' memory (page_text). The
        # txt's code gives its size there, txt_maxl + 1, in its second byte.
        entries[self._entry_of["txt"]] = (place.text_place, 0, 0, (maxl + 1) << 8 | 0x3F)
        return packed_entries(entries, self.ENTRIES, place)

    def memory_at(self, page_object, project, place) -> bytes:
        """Returns the scrolling text's starting values: its sta; its style,
        which is 0 unless its sta is 1; its borderc, 2 bytes, and borderw,
        zeros but at a style of 1, whatever its sta; its font, what lies
        behind it, its bco, pic, or picc, its pco, xcen, ycen, dir, dis, tim,
        en, a 0 byte, its txt_maxl, where its txt lies in memory,
        place.text_place, or 0 before the frame places it, 4 bytes, its isbr,
        spax, and spay, a 0 byte, then its vvs0 to vvs3, 2 bytes each."""
        values = {value: _value(page_object, self._names.get(value, value))
                  for value in MEMORY_VALUES
                  if value not in ("style", "txt_maxl", "txt_place")}
        if not self.border_entries:
            values["borderc"] = values["borderw"] = 0
        values.update(style=self.style, txt_maxl=number_from_bytes(
            page_object.attribute("txt_maxl")), txt_place=place.text_place or 0)
        return struct.pack(MEMORY_FORMAT, *(values[value] for value in MEMORY_VALUES))

    def page_text(self, page_object, project) -> bytes:
        """Returns what the scrolling text keeps after its page's components'
        memory: its txt, padded with zeros to txt_maxl + 1 bytes, the whole
        padded with zeros to a multiple of 4."""
        return with_txt(b"", page_object)

    def record_slots(self) -> dict:
        """Returns the scrolling text's slots in its record: {slot: entry
        within the type}."""
        return dict(self._slots)

    def attribute_place(self, name: str) -> int:
        """Returns the entry, within the type, of the attribute `name`, any
        the type writes. Raises KeyError for another."""
        return self._entry[name]

    def _setbrush_for_measuring(self, page_object, series: str, place) -> bytes:
        """Returns the setbrush before the txt is measured: its place and
        size, its font, then zeros but for its isbr, spax, and spay, and its
        border's width."""
        x, y, w, h = place_and_size(page_object)
        entry = self._operands(place)
        return (SETBRUSH[series] + b"%d,%d,%d,%d," % (x, y, w, h)
                + b",".join([entry("font"), b"0", b"0", b"0", b"0", b"0", entry("isbr"),
                             entry("spax"), entry("spay"), b"0",
                             b"%d" % self._border_width(page_object)]))

    def _measuring(self, page_object, series: str, place) -> list:
        """Returns the blocks that measure the txt into the scrolling's width
        and height entries."""
        entry = self._operands(place)
        return [self._setbrush_for_measuring(page_object, series, place),
                _MEASURE[series] + entry("txt") + b"," + entry("vvs2")
                + b"," + entry("vvs3")]

    def _starting_blocks(self, page_object, series: str, place) -> list:
        """Returns the code that measures the txt and sets where the
        scrolling starts, by its dir: past its area's left, right, top, or
        bottom edge, the other position unused."""
        x, y, w, h = place_and_size(page_object)
        entry = self._operands(place)
        unused = value_operand(_UNUSED)
        tx, ty, tw, th = (entry(name) for name in ("vvs0", "vvs1", "vvs2", "vvs3"))
        equal = COMPARISONS[series]["=="]
        cases = [
            (b"0", [tx + b"=%d-" % x + tw + b"-1", ty + b"=" + unused]),
            (b"1", [tx + b"=%d+1" % (x + w - 1), ty + b"=" + unused]),
            (b"2", [ty + b"=%d-" % y + th + b"-1", tx + b"=" + unused]),
            (b"3", [ty + b"=%d+1" % (y + h - 1), tx + b"=" + unused]),
        ]
        return self._measuring(page_object, series, place) + _chain(
            [(entry("dir"), equal, value, body) for value, body in cases])

    def _timer_code(self, page_object, series: str, place) -> list:
        """Returns the scrolling text's timer code, after the "S " block that
        starts it: while its en is 1, it measures the txt, moves it by dis in
        its dir, brings it back to the other side once it leaves the area,
        then refreshes the scrolling text. Else it stops the timer."""
        x, y, w, h = place_and_size(page_object)
        right, bottom = x + w - 1, y + h - 1
        entry = self._operands(place)
        unused = value_operand(_UNUSED)
        tx, ty, tw, th = (entry(name) for name in ("vvs0", "vvs1", "vvs2", "vvs3"))
        comparisons = COMPARISONS[series]
        edge = system_variable_operand("sya0", series)

        def moving(position, other, near, size, far, forward: bool):
            """The blocks of one dir. The other position is unused. The
            position moves by dis, forward or back. sya0 keeps the near end,
            where the txt lies just past the area's near edge. Moving
            forward, the txt comes back to the near end once past the far
            edge. Moving back, it comes back to the far edge once past the
            near end."""
            near_end, far_edge = b"%d-" % near + size, b"%d" % far
            if forward:
                back = [(position, comparisons[">"], far_edge, [position + b"=" + near_end]),
                        (position, comparisons["<"], edge, [position + b"=" + edge])]
            else:
                back = [(position, comparisons["<"], edge, [position + b"=" + far_edge]),
                        (position, comparisons[">"], far_edge, [position + b"=" + far_edge])]
            return [other + b"=" + unused,
                    position + b"=" + position + (b"+" if forward else b"-") + entry("dis"),
                    edge + b"=" + near_end] + _chain(back)

        cases = [(b"0", moving(tx, ty, x, tw, right, forward=True)),
                 (b"1", moving(tx, ty, x, tw, right, forward=False)),
                 (b"2", moving(ty, tx, y, th, bottom, forward=True)),
                 (b"3", moving(ty, tx, y, th, bottom, forward=False))]
        moved = (self._measuring(page_object, series, place)
                 + _chain([(entry("dir"), comparisons["=="], value, body)
                           for value, body in cases])
                 + [REF + b"%d" % place.object_id, _AFTER_REF])
        stopping = [TIMERSET[series] + b"0,%d,0,1" % place.object_id]
        blocks = ([comparison_block(entry("en"), comparisons["=="], b"1",
                                    size_of(moved) + size_of([jump_block(0)]))]
                  + moved + [jump_block(size_of(stopping))] + stopping)
        return threaded(blocks)


@lru_cache(maxsize=None)
def _of(sta: int, style: int, border_entries: bool) -> _ScrollingText:
    """Returns the variant of a scrolling text of the sta `sta` and the
    style `style`, with its border's entries or not, made once."""
    return _ScrollingText(sta, style, border_entries)


def variant(page_object) -> _ScrollingText:
    """Returns what describes the scrolling text `page_object`: the variant
    of its sta and its style. A sta or a style its rules refuse is described
    as one of a colour, or of no border; a style draws at a sta of 1 alone,
    but a style of 1 gives its border's entries, and their values in memory,
    at any sta. A sta of 3, nothing behind it, which its rules take on P and
    E alone, is described as one of nothing behind it on every series."""
    sta, style = _value(page_object, "sta"), _value(page_object, "style")
    sta = sta if sta in _BACKGROUNDS or sta == _NOTHING else COLOUR
    border_entries = style == BORDERED
    style = style if sta == COLOUR and style in (_FLAT, BORDERED, _SUNKEN, _RAISED) else _FLAT
    return _of(sta, style, border_entries)


def _style_covered(need) -> bool:
    """Whether the style of `need` is one of 0 to 3, at any sta. With a
    picture or a crop behind it, the Nextion Editor writes a style of 0, and
    draws no border, but a style of 1 gives its border's entries all the
    same (variant)."""
    return 0 <= number_from_bytes(need.value) <= 3


# The series this module's probes matched (matching.py): T, K in k_probes.py,
# P in p_probes.py, E in e_probes.py, and F in f_probes.py.
SERIES = ("T", "K", "P", "E", "F")

# What the scrolling text has matched with probes (matching.py): a scrolling
# text at its defaults, on each screen model of T and K at each rotation, and
# on P, E, and F, but for these.
MATCHED = [
    Rule("type", "scrolling-text", "a scrolling text, its attributes at their defaults but "
         "for those below"),
    Rule("attribute", "scrolling-text.objname", "any name nxwright's build takes"),
    Rule("attribute", "scrolling-text.x", PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT),
    Rule("attribute", "scrolling-text.y", PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT),
    Rule("attribute", "scrolling-text.w", PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT),
    Rule("attribute", "scrolling-text.h", PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT),
    Rule("attribute", "scrolling-text.txt", TXT_WORDS, text_fits),
    Rule("attribute", "scrolling-text.txt_maxl", TXT_MAXL_WORDS, txt_maxl_covered, DOES_NOT_FIT),
    Rule("attribute", "scrolling-text.font", "any font of the project"),
    Rule("attribute", "scrolling-text.sta", STA_WORDS, sta_covered, INVALID_VALUE),
    Rule("attribute", "scrolling-text.style", "0, no border, 1, a border of its borderc and "
         "borderw, or 2 or 3, a 3D border, sunken or raised, at a sta of 1; at another sta, "
         "none draws a border, and 1 gives its border's entries all the same", _style_covered,
         INVALID_VALUE),
    Rule("attribute", "scrolling-text.borderc", *value_rule("borderc")),
    Rule("attribute", "scrolling-text.borderw", *value_rule("borderw")),
] + [
    # Its code compares its dir and en with each value it plays, as the
    # screen runs, so any other value is written as it is too.
    Rule("attribute", "scrolling-text.dir", "0 to 3, left to right, right to left, top to "
         "bottom, or bottom to top, or any other value that fits in its byte, written as it is"),
    Rule("attribute", "scrolling-text.en", "0, 1, or any other value that fits in its byte, "
         "written as it is"),
] + [Rule("attribute", "scrolling-text." + name, "any value, written as it is")
     for name in ("dis", "tim")
] + [Rule("attribute", "scrolling-text." + name, "from 0 to 65535, the most its 2 bytes hold "
          "in the page file and in memory, where its entry gives more", from_to(0, 0xFFFF))
     for name in ("vvs0", "vvs1", "vvs2", "vvs3")
] + [Rule("attribute", "scrolling-text." + name, *value_rule(name))
     for name in ("bco", "pco", "xcen", "ycen", "isbr", "spax", "spay")] + [
    # A picture's ID is 2 bytes in memory, written as it is, whichever
    # picture it is, and only at the sta that shows it.
    Rule("attribute", "scrolling-text." + name, "any value from 0 to 65535, written as it is: a "
         "picture of the project, or 65535 for none") for name in ("pic", "picc")]
