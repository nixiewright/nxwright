"""The waveform component, as the Nextion Editor 1.68.2 writes it on T and K
(ResearchNotes/tft/waveform-component.md gives each value, and how it was found).

So far it writes a waveform at its defaults but for its place, its size, its
ch, its channels from 1 to 4, its dir, its dis, its colours and grid: bco,
gdc, gdw, gdh, and pco0 to pco3, what lies behind it, its sta, pic, and
picc, and three values the Nextion Editor's panel never shows: its objWid,
objHig, and inittrue. A waveform draws the values code adds
to its channels, across its width. Its drawing has no blocks, but it is
written as a drawn object, as a slider is: its run after the drawing is the
plain fill of its area, and its record has its place and size, but no first
block's place (frame.py). The screen draws it from the command a waveform
adds to its page's load section, a slider's, `09 16 04` on T, `09 18 04`
on K, and `09 1d 04` on F, and its ID.

Its memory, 36 bytes, gives its sta, dir, ch, bco, gdc, gdw, gdh, objWid,
objHig, a colour for each of its channels, inittrue, and dis, then the size
of its buffer and where that buffer lies. The buffer is memory the screen
sets aside for the waveform, at the end of its page's memory (buffer_size,
component_types/__init__.py). Its entries and its record give each
channel's colour too, so how many entries it has, and where its dis's entry
lies, depend on its ch.

Its sta sets what lies behind it: a crop of a picture, its picc (0), its
bco (1), or a picture, its pic (2). With a picture or a crop, the picture's
ID lies in memory where its bco lies, and its grid is not drawn: its gdc,
gdw, and gdh are zeros in memory, and have no entries. Each later entry is
numbered three down. On P and E, a sta of 3 puts nothing behind it: its bco
is a zero in memory too, and has no entry either, so each later entry is
numbered four down. So each waveform is written by the variant of its ch
and its sta (variant).

On P, its memory is 92 bytes: what its record's head holds and its
effect's values, 56 bytes, as every drawn component's there, then its
memory on T. Its entries keep T's numbers (P_ENTRIES), and its page's load
section gets `init` and its ID in place of the slider's command.
"""
from functools import lru_cache
import struct

from nxwright.project.attribute_values import number_from_bytes
from nxwright.project.memory_table import memory_table

from nxwright.tft.component_types import (P_DRAWN_ENTRIES, PLACE_WORDS, SERIES_WRITTEN_AS_P, STA_WORDS,
                                   background_fill, from_to, object_entries, packed_entries,
                                   place_and_size, place_fits_its_record, sta_covered, value_rule)
from nxwright.tft.component_types.slider import load_block
from nxwright.tft.instructions.undocumented_commands import init_block
from nxwright.tft.matching import Rule
from nxwright.tft.reasons import DOES_NOT_FIT, INVALID_VALUE

# What lies behind a waveform, by its sta: a crop of a picture, its colour,
# or a picture. A sta of 3 puts nothing behind it, on P and E alone.
_CROP, _COLOUR, _PICTURE, _NOTHING = 0, 1, 2, 3
# The attribute that gives what lies behind it, by its sta.
BACKGROUND = {_CROP: "picc", _COLOUR: "bco", _PICTURE: "pic"}
# The attributes of its grid, which a colour behind it has alone.
GRID = ("gdc", "gdw", "gdh")
# The entries a waveform of a colour has, besides one for each channel's
# colour. One of a picture or a crop has fewer, by its grid's.
_ENTRIES = 40
# Where each value with an entry lies in a waveform's memory, from its base.
# A pic or a picc lies where a bco does. Channel i's colour, pco0 to pco3,
# lies 2 bytes after channel i - 1's.
_PLACES = {"sta": 0, "dir": 1, "ch": 2, "bco": 4, "pic": 4, "picc": 4, "gdc": 6, "gdw": 8,
           "gdh": 9, "pco0": 14, "pco1": 16, "pco2": 18, "pco3": 20, "dis": 24}
# Each attribute's entry, within the type, in a waveform of a colour, but
# those of the channels' colours and of dis, which depend on its ch
# (_Waveform).
_ENTRY = {"type": 0, "id": 1, "vscope": 3, "x": 9, "y": 10, "w": 11, "h": 12, "endx": 13,
          "endy": 14, "sta": 19, "dir": 20, "ch": 21, "bco": 22, "gdc": 23, "gdw": 24,
          "gdh": 25}
# The entry of channel 0's colour in a waveform of a colour; the others
# follow it. In one of a picture or a crop, it is numbered three down.
_FIRST_COLOUR_ENTRY = 28
# Each entry's highest value, lowest value, and code, by the attribute it
# gives.
_VALUES = {"sta": (2, 0, 0x121), "dir": (2, 0, 0x121), "ch": (4, 1, 0x121),
           "bco": (0xFFFF, 0, 0x232), "gdc": (0xFFFF, 0, 0x232), "gdw": (255, 0, 0x131),
           "gdh": (255, 0, 0x131), "pco0": (0xFFFF, 0, 0x232), "pco1": (0xFFFF, 0, 0x232),
           "pco2": (0xFFFF, 0, 0x232), "pco3": (0xFFFF, 0, 0x232), "dis": (1000, 10, 0x232)}
# The record's slots that give an entry, and which entry, in a waveform of a
# colour, but those of the channels' colours: channel i's is slot 10 + i.
# One of a picture or a crop has no slots of its bco and its grid, and gives
# its pic in slot 6, or its picc in slot 5.
_SLOTS = {1: "vscope", 2: "sta", 3: "ch", 4: "bco", 7: "gdc", 8: "gdw", 9: "gdh", 42: "x",
          43: "y", 44: "endx", 45: "endy", 46: "w", 47: "h", 48: "dir", 49: "id", 55: "dis",
          62: "type"}
_BACKGROUND_SLOTS = {"bco": 4, "pic": 6, "picc": 5}
_FIRST_COLOUR_SLOT = 10
# A waveform's attributes at their defaults, as a new one's.
_DEFAULTS = {"sta": 1, "dir": 0, "ch": 1, "bco": 0, "pic": 0xFFFF, "picc": 0xFFFF, "gdc": 1024,
             "gdw": 40, "gdh": 40, "objWid": 0, "objHig": 0, "pco0": 0xFBEF, "pco1": 0xFFEF,
             "pco2": 0xF800, "pco3": 0x07E0, "inittrue": 0, "dis": 100}
# The most channels a waveform has.
MOST_CHANNELS = 4
# Its memory on T, K, and F, by what each value gives, in order, and its
# form: its sta, dir, and ch, a 0 byte, what lies behind it, its gdc, gdw,
# and gdh, its objWid and objHig, a colour for each of its four channels,
# its inittrue and dis, two 0 bytes, then the size of its buffer and where
# its buffer lies.
MEMORY_VALUES = ("sta", "dir", "ch", "background", "gdc", "gdw", "gdh", "objWid", "objHig",
                 "pco0", "pco1", "pco2", "pco3", "inittrue", "dis", "buffer size",
                 "buffer place")
MEMORY_FORMAT = "<BBBxHHBBHH4HHH2xII"
# Where its values start in its memory on P: after its record's head and its
# effect's values.
P_VALUES_AT = 56
# The highest values, lowest values, and codes on P that are not T's
# (_VALUES): its sta's, and a picture's, whose highest p_table sets, the
# project's last picture (P_LAST_RESOURCE).
_P_VALUES = {"sta": (3, 0, 0x121), "pic": (None, 0, 0x232), "picc": (None, 0, 0x232)}
# Where the values no entry gives lie in its memory, from its base, 2 bytes
# each (memory_at): its objWid, objHig, and inittrue; then the size of its
# buffer and where its buffer lies, 4 bytes each.
P_UNNAMED_PLACES = {"objWid": 10, "objHig": 12, "inittrue": 22}
_BUFFER_SIZE_PLACE, _BUFFER_PLACE = 28, 32


def _value(page_object, name: str) -> int:
    value = page_object.attribute(name)
    return _DEFAULTS[name] if value is None else number_from_bytes(value)


EVENTS = ("down", "up")


class _Waveform:
    """A waveform of `channels` channels, and of what its sta `sta` puts
    behind it, with the members a type's module gives
    (component_types/__init__.py) but MATCHED. It has an entry for each
    channel's colour, then one empty entry, then its dis's entry, and a slot
    in its record for each channel's colour. One of a picture or a crop has
    its pic's or its picc's entry in place of its bco's, and none of its
    grid. One of nothing behind it has neither, on P and E alone."""
    EVENTS = EVENTS

    def __init__(self, channels: int, sta: int):
        self.channels, self.sta = channels, sta
        self.background = BACKGROUND.get(sta)
        colours = ["pco%d" % number for number in range(channels)]
        # A picture or a crop behind it takes its bco's entry and drops its
        # grid's three, so each later entry is numbered three down. With
        # nothing behind it, it has no entry for what lies behind it either,
        # so each is four down. On P, its memory keeps 0 there and for its
        # grid, as no entry gives a value.
        dropped = () if sta == _COLOUR else ("bco",) + GRID
        shift = 0 if sta == _COLOUR else len(GRID) + (sta == _NOTHING)
        first_colour = _FIRST_COLOUR_ENTRY - shift
        self.ENTRIES = _ENTRIES + channels - shift
        self._entry = {name: entry for name, entry in _ENTRY.items() if name not in dropped}
        self._slots = {slot: name for slot, name in _SLOTS.items() if name not in dropped}
        if self.background is not None:
            self._entry[self.background] = _ENTRY["bco"]
            self._slots[_BACKGROUND_SLOTS[self.background]] = self.background
        self._entry["dis"] = first_colour + channels + 1
        self._entry.update({name: first_colour + number for number, name in enumerate(colours)})
        self._slots.update({_FIRST_COLOUR_SLOT + number: name
                            for number, name in enumerate(colours)})
        # On P, its values lie in its memory as on T, from P_VALUES_AT, and
        # its entries keep T's numbers.
        self.P_ENTRIES = dict(P_DRAWN_ENTRIES)
        for name, entry in self._entry.items():
            if name in _PLACES:
                highest, lowest, code = _P_VALUES.get(name) or _VALUES[name]
                self.P_ENTRIES[entry] = (name, P_VALUES_AT + _PLACES[name], highest, lowest,
                                         code)

    # Its memory on P: what its record's head holds and its effect's values,
    # then its memory on T (memory_at).
    P_MEMORY_SIZE = 92
    P_LAST_RESOURCE = {"pic": "picture", "picc": "picture"}

    def p_memory_extras(self, page_object, project, place) -> dict:
        """Returns the bytes of the waveform's memory on P that no entry
        gives: its objWid, objHig, and inittrue, the size of its buffer, and
        where its buffer lies, place.buffer_place."""
        extras = {P_VALUES_AT + at: struct.pack("<H", _value(page_object, name))
                  for name, at in P_UNNAMED_PLACES.items()}
        extras[P_VALUES_AT + _BUFFER_SIZE_PLACE] = struct.pack(
            "<I", self.buffer_size(page_object, project))
        extras[P_VALUES_AT + _BUFFER_PLACE] = struct.pack("<I", place.buffer_place or 0)
        return extras

    # The frame calls the type's background_fill, which is the plain fill.
    background_fill = staticmethod(background_fill)

    def drawing(self, page_object, project, place) -> list:
        """Returns no blocks: the screen draws a waveform from its load
        section's command (load_start)."""
        return []

    def data(self, page_object, project, place) -> bytes:
        """Returns the waveform's entries: where each of its values lies in
        memory, a colour for each of its channels among them. A pic's or a
        picc's is from 0 to the project's last picture."""
        pictures = project.resource_count("picture")
        values = dict(_VALUES, pic=(pictures - 1, 0, 0x232), picc=(pictures - 1, 0, 0x232))
        entries = object_entries(page_object, place.object_id)
        entries.update({self._entry[name]: (place.base + _PLACES[name],) + values[name]
                        for name in _PLACES if name in self._entry})
        return packed_entries(entries, self.ENTRIES, place)

    def buffer_size(self, page_object, project) -> int:
        """Returns the size of the waveform's buffer, by nxwright's table of
        what each type takes in memory (project/memory_table.py): for
        each channel, 16 bytes plus 13/10 of its width, rounded down, then up
        to a multiple of 4."""
        parts = memory_table().series[project.settings.model.series].types["waveform"].parts
        values = {"ch": self.channels, "w": place_and_size(page_object)[2]}
        return sum(part.cost_in(values) for part in parts)

    def memory_at(self, page_object, project, place) -> bytes:
        """Returns the waveform's starting values: its sta, dir, and ch, a 0
        byte, what lies behind it, its bco, pic, or picc, then its gdc, its
        gdw and gdh, zeros without a colour behind it, its objWid and objHig,
        the colours of its channels, pco0 to pco3, 0 for each it does not
        have, its inittrue, its dis, two 0 bytes, then the size of its buffer
        and where its buffer lies, place.buffer_place, 4 bytes each."""
        values = {name: _value(page_object, name) for name in MEMORY_VALUES
                  if name in _DEFAULTS}
        values.update({"ch": self.channels, "background": _value(page_object, self.background),
                       "buffer size": self.buffer_size(page_object, project),
                       "buffer place": place.buffer_place or 0})
        values.update({"pco%d" % number: 0 for number in range(self.channels, MOST_CHANNELS)})
        if self.sta != _COLOUR:
            values.update({name: 0 for name in GRID})
        return struct.pack(MEMORY_FORMAT, *(values[name] for name in MEMORY_VALUES))

    def record_slots(self) -> dict:
        """Returns the waveform's slots in its record: {slot: entry within the
        type}."""
        return {slot: self._entry[name] for slot, name in self._slots.items()}

    def attribute_place(self, name: str) -> int:
        """Returns the entry, within the type, of the attribute `name`, any
        the type writes. Raises KeyError for another."""
        return self._entry[name]

    def load_start(self, page_object, project, place, places: dict) -> list:
        """Returns the block the waveform adds to its page's load section,
        before the page's own load code: a slider's command, then its ID as
        text (slider.load_block). On P, the command is `init`."""
        series = project.settings.model.series
        if series in SERIES_WRITTEN_AS_P:
            return [init_block(place.object_id)]
        return [load_block(series, place.object_id)]


@lru_cache(maxsize=None)
def _of(channels: int, sta: int) -> _Waveform:
    """Returns the variant of a waveform of `channels` channels and of the
    sta `sta`, made once."""
    return _Waveform(channels, sta)


def variant(page_object) -> _Waveform:
    """Returns what describes the waveform `page_object`: the variant of its
    ch and its sta. A sta its rule refuses is described as one of a
    colour. A sta of 3, nothing behind it, which its rule takes on P and E
    alone, is described as one of nothing behind it on every series."""
    sta = _value(page_object, "sta")
    return _of(_value(page_object, "ch"),
               sta if sta in BACKGROUND or sta == _NOTHING else _COLOUR)


# The series this module's probes matched (matching.py): T, K in k_probes.py,
# P in p_probes.py, E in e_probes.py, and F in f_probes.py.
SERIES = ("T", "K", "P", "E", "F")

# What the waveform has matched with probes (matching.py): a waveform at its
# defaults, on each screen model of T and K at each rotation, and on P, E, and
# F, but for these.
MATCHED = [
    Rule("type", "waveform", "a waveform, its attributes at their defaults but for those below"),
    Rule("attribute", "waveform.objname", "any name nxwright's build takes"),
    Rule("attribute", "waveform.x", PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT),
    Rule("attribute", "waveform.y", PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT),
    Rule("attribute", "waveform.w", PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT),
    Rule("attribute", "waveform.h", PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT),
    # A waveform's channels set its entries, its colours, and its buffer, for
    # 1 to 4 channels. nxwright's build refuses any other number.
    Rule("attribute", "waveform.ch", "from 1 to 4 channels", from_to(1, MOST_CHANNELS),
         INVALID_VALUE),
    Rule("attribute", "waveform.dir", "0, 1, 2, or any other value that fits in its byte, "
         "written as it is"),
    Rule("attribute", "waveform.dis", "any value, written as it is"),
    Rule("attribute", "waveform.gdw", "from 0 to 255", from_to(0, 255)),
    Rule("attribute", "waveform.gdh", "from 0 to 255", from_to(0, 255)),
    Rule("attribute", "waveform.sta", STA_WORDS, sta_covered, INVALID_VALUE),
    # A pic or a picc is 2 bytes in memory, written as it is, whichever
    # picture it is, and only at the sta that shows it.
    Rule("attribute", "waveform.pic", "any value from 0 to 65535, written as it is: a picture "
         "of the project, or 65535 for none"),
    Rule("attribute", "waveform.picc", "any value from 0 to 65535, written as it is: a picture "
         "of the project, or 65535 for none"),
    # Values the Nextion Editor's panel never shows, each written as it is in
    # memory, and in no entry.
    Rule("attribute", "waveform.objWid", "from 0 to 65535", from_to(0, 0xFFFF)),
    Rule("attribute", "waveform.objHig", "from 0 to 65535", from_to(0, 0xFFFF)),
    Rule("attribute", "waveform.inittrue", "from 0 to 255", from_to(0, 255)),
    Rule("attribute", "waveform.molloc", "any value, which changes nothing in the file"),
    Rule("attribute", "waveform.molloc_s", "any value, which changes nothing in the file"),
] + [Rule("attribute", "waveform." + name, *value_rule(name))
     for name in ("bco", "gdc", "pco0", "pco1", "pco2", "pco3")]
