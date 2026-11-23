"""The slider component, as the Nextion Editor 1.68.2 writes it on T
(ResearchNotes/tft/slider-component.md gives each value, and how it was found),
and on P, where its memory gives its values as on T, from 56 (P_ENTRIES),
and its load section's block is `init` and its ID.

So far it writes a slider at its defaults but for its place, its size, its
val, its minval, and its maxval, the val inside its bounds or not, its
mode, across or upright, its colours, bco, bco1, and pco, its cursor's
size, wid and hig, its dis, its ch, what lies behind its track, its sta,
pic, pic1, picc, and picc1, and its cursor, its psta and pic2. A slider is
a bar whose cursor a touch drags along it. Its drawing has no blocks, but
it is written as a drawn object, as a hotspot is: its run after the drawing
is the plain fill of its area, and its record has its place and size, but
no first block's place (frame.py). The screen draws it from the command a slider adds
to its page's load section, `09 16 04` on T and `09 18 04` on K, and its
ID. It has three events: down, up, and slide, as a touch drags its cursor.
Its memory gives its mode, sta, psta, wid, hig, dis, bco, pco, val, maxval,
minval, ch, and bco1, 28 bytes.

Its sta sets what lies behind its track: a crop of a picture (0), a colour
(1), or a picture (2). Its bco and bco1 give the colours of the whole track
and of its part up to the cursor; a picture's ID, pic and pic1, or a crop's,
picc and picc1, takes their places in memory and their entries. With a
picture or a crop, its ch and its dis are zeros in memory, and its ch has no
entry. Its psta sets what its cursor is: round, of its pco's colour (0), a
picture, its pic2 (1), which takes its pco's place and entry, or, on P and
E, square, of its pco's colour (2). So each slider is written by the variant
of its sta and psta (variant).
"""
from functools import lru_cache
import struct

from nxwright.project.attribute_values import number_from_bytes

from nxwright.tft.component_types import (P_DRAWN_ENTRIES, PLACE_WORDS, SERIES_WRITTEN_AS_P,
                                   background_fill, from_to, object_entries, packed_entries,
                                   place_fits_its_record, value_rule)
from nxwright.tft.instructions.undocumented_commands import init_block
from nxwright.tft.matching import Rule
from nxwright.tft.reasons import DOES_NOT_FIT, INVALID_VALUE

EVENTS = ("down", "up", "slide")

# What lies behind a slider's track, by its sta: a crop of a picture, a
# colour, or a picture.
_CROP, _COLOUR, _PICTURE = 0, 1, 2
# The attributes that give what lies behind its track, by its sta: behind
# the whole track, then behind its part up to the cursor.
TRACKS = {_CROP: ("picc", "picc1"), _COLOUR: ("bco", "bco1"), _PICTURE: ("pic", "pic1")}
# The attribute that gives its cursor, by its psta: a round one of a colour,
# a picture, or a square one of a colour, SQUARE. The Nextion Editor refuses
# a square on T and K, and nxwright's build on T, K, and F.
SQUARE = 2
CURSORS = {0: "pco", 1: "pic2", SQUARE: "pco"}
# The entries a slider with a colour behind it has. One with a picture or a
# crop behind it has two fewer.
_ENTRIES = 40
# Where each value lies in a slider's memory, from its base, by what it
# gives: what lies behind the whole track, and behind its part up to the
# cursor, and its cursor, whichever attribute gives each.
_PLACES = {"mode": 0, "sta": 1, "psta": 2, "wid": 3, "hig": 4, "dis": 5, "track": 6,
           "cursor": 8, "val": 10, "maxval": 12, "minval": 14, "ch": 16, "track1": 22}
# Each attribute's entry, within the type, but those from what lies behind
# its track on.
_ENTRY = {"type": 0, "id": 1, "vscope": 3, "x": 9, "y": 10, "w": 11, "h": 12, "endx": 13,
          "endy": 14, "mode": 19, "sta": 20, "psta": 21, "wid": 22, "hig": 23}
# The entries from what lies behind its track on, in order: from entry 25
# with a colour behind it, which gives its ch an entry too, or from entry 24
# with a picture or a crop behind it.
_FOLLOWING = ("track", "track1", "cursor", "val", "maxval", "minval")
# Each entry's highest value and code, by the attribute it gives. That of a
# picture's ID is from 0 to the project's last picture (_PICTURE_NAMES).
_VALUES = {"mode": (1, 0x121), "sta": (2, 0x121), "psta": (1, 0x121), "wid": (255, 0x131),
           "hig": (255, 0x131), "bco": (0xFFFF, 0x232), "bco1": (0xFFFF, 0x232),
           "pco": (0xFFFF, 0x232), "val": (0xFFFF, 0x232), "maxval": (0xFFFF, 0x232),
           "minval": (0xFFFF, 0x232), "ch": (255, 0x131)}
# The attributes that give a picture's ID.
_PICTURE_NAMES = ("pic", "pic1", "pic2", "picc", "picc1")
# The top byte of the owner field of some entries, as a timer's tim and en
# give one (component_types.packed_entries).
_OWNER_TOPS = {"wid": 1, "hig": 2, "maxval": 3, "minval": 4, "val": 5}
# The record's slots that give an entry, and what each gives, but those of
# what lies behind its track and of its cursor (_ATTRIBUTE_SLOTS).
_SLOTS = {1: "vscope", 2: "sta", 14: "mode", 15: "psta", 18: "wid", 19: "hig", 20: "val",
          21: "maxval", 22: "minval", 42: "x", 43: "y", 44: "endx", 45: "endy", 46: "w",
          47: "h", 49: "id", 62: "type"}
# The slot of each attribute that gives what lies behind its track or its
# cursor, and of its ch, which a colour behind it alone has.
_ATTRIBUTE_SLOTS = {"bco": 4, "bco1": 38, "ch": 3, "picc": 5, "picc1": 36, "pic": 6,
                    "pic1": 40, "pco": 16, "pic2": 17}
# A slider's attributes at their defaults, as a new one's.
_DEFAULTS = {"mode": 0, "sta": 1, "psta": 0, "wid": 255, "hig": 255, "dis": 100, "bco": 1024,
             "pco": 0x4000, "val": 50, "maxval": 100, "minval": 0, "ch": 25, "bco1": 0xFAEB,
             "pic": 0xFFFF, "pic1": 0xFFFF, "pic2": 0xFFFF, "picc": 0xFFFF, "picc1": 0xFFFF}
# The command a slider adds to its page's load section, by series: K and F
# number it their own ways.
_LOAD = {"T": b"\x09\x16\x04", "K": b"\x09\x18\x04", "F": b"\x09\x1d\x04"}
# Its memory on T, K, and F, by what each value gives, in order, and its
# form: its mode, sta, psta, wid, hig, and dis, what lies behind its track,
# its cursor, its val, maxval, minval, and ch, five 0 bytes, what lies
# behind its track's part up to the cursor, then four 0 bytes.
MEMORY_VALUES = ("mode", "sta", "psta", "wid", "hig", "dis", "track", "cursor", "val", "maxval",
                 "minval", "ch", "track1")
MEMORY_FORMAT = "<BBBBBBHHHHHB5xH4x"
# Where its values start in its memory on P: after its record's head and its
# effect's values.
_P_VALUES_AT = 56
# The highest values and codes on P that are not T's (_VALUES): those of its
# psta and ch, and of its dis, which has an entry on P, entry 24, with a
# colour behind its track. A picture's highest is the project's last picture
# (P_LAST_RESOURCE).
_P_VALUES = {"psta": (2, 0x121), "ch": (100, 0x131), "dis": (100, 0x131),
             **{name: (None, 0x232) for name in _PICTURE_NAMES}}
_P_DIS_ENTRY = 24


def _value(page_object, name: str) -> int:
    value = page_object.attribute(name)
    return _DEFAULTS[name] if value is None else number_from_bytes(value)


class _Slider:
    """A slider of the sta `sta` and the psta `psta`, with the members a
    type's module gives (component_types/__init__.py) but MATCHED. `names`
    gives the attribute each of its values comes from: what lies behind its
    track, "track" and "track1", its cursor, "cursor", and the others by
    their own names."""
    EVENTS = EVENTS

    def __init__(self, sta: int, psta: int):
        self.coloured = sta == _COLOUR
        track, track1 = TRACKS[sta]
        self.names = {name: name for name in _PLACES}
        self.names.update(track=track, track1=track1, cursor=CURSORS[psta])
        following = _FOLLOWING + (("ch",) if self.coloured else ())
        first = 25 if self.coloured else 24
        self.ENTRIES = _ENTRIES if self.coloured else _ENTRIES - 2
        # By what each entry gives, then by the attribute that gives it.
        self._entry_of = dict(_ENTRY)
        self._entry_of.update({value: first + number for number, value in enumerate(following)})
        self._entry = {self.names.get(value, value): entry
                       for value, entry in self._entry_of.items()}
        slots = {slot: self._entry[name] for slot, name in _SLOTS.items()}
        slots.update({_ATTRIBUTE_SLOTS[name]: self._entry[name]
                      for name in (track, track1, CURSORS[psta], "ch") if name in self._entry})
        self._slots = slots
        # On P, its values lie in its memory as on T, from _P_VALUES_AT, and
        # its entries keep T's numbers, with its dis's too when it has one.
        entry_of = dict(self._entry_of, **({"dis": _P_DIS_ENTRY} if self.coloured else {}))
        self.P_ENTRIES = dict(P_DRAWN_ENTRIES)
        for value, at in _PLACES.items():
            if value in entry_of:
                name = self.names[value]
                highest, code = _P_VALUES.get(name) or _VALUES[name]
                self.P_ENTRIES[entry_of[value]] = (name, _P_VALUES_AT + at, highest, 0, code)

    # Its memory on P: what its record's head holds and its effect's values,
    # then its values, as on T (memory). Its entries' owner fields take the
    # top bytes they take on T, and a picture's highest is the project's last
    # picture.
    P_MEMORY_SIZE = 84
    P_OWNER_TOPS = _OWNER_TOPS
    P_LAST_RESOURCE = {name: "picture" for name in _PICTURE_NAMES}

    # The frame calls the type's background_fill, which is the plain fill.
    background_fill = staticmethod(background_fill)

    def drawing(self, page_object, project, place) -> list:
        """Returns no blocks: the screen draws a slider from its load
        section's command (load_start)."""
        return []

    def data(self, page_object, project, place) -> bytes:
        """Returns the slider's entries: where each of its values lies in
        memory, five of them with a top byte in their owner field. A
        picture's ID, behind its track or as its cursor, is from 0 to the
        project's last picture."""
        pictures = project.resource_count("picture")
        values = dict(_VALUES, **{name: (pictures - 1, 0x232) for name in _PICTURE_NAMES})
        entries = object_entries(page_object, place.object_id)
        for value, at in _PLACES.items():
            if value in self._entry_of:
                highest, code = values[self.names[value]]
                entries[self._entry_of[value]] = (place.base + at, highest, 0, code)
        owner_tops = {self._entry[name]: top for name, top in _OWNER_TOPS.items()}
        return packed_entries(entries, self.ENTRIES, place, owner_tops=owner_tops)

    def memory(self, page_object, project) -> bytes:
        """Returns the slider's starting values: its mode, sta, psta, wid,
        hig, and dis, what lies behind its track, its cursor, its val,
        maxval, minval, and ch, five 0 bytes, what lies behind its track's
        part up to the cursor, then four 0 bytes. With a picture or a crop
        behind its track, its dis and ch are zeros."""
        values = {value: _value(page_object, self.names[value]) for value in MEMORY_VALUES}
        if not self.coloured:
            values.update(dis=0, ch=0)
        return struct.pack(MEMORY_FORMAT, *(values[value] for value in MEMORY_VALUES))

    def record_slots(self) -> dict:
        """Returns the slider's slots in its record: {slot: entry within the
        type}."""
        return dict(self._slots)

    def attribute_place(self, name: str) -> int:
        """Returns the entry, within the type, of the attribute `name`, any
        the type writes. Raises KeyError for another."""
        return self._entry[name]

    def load_start(self, page_object, project, place, places: dict) -> list:
        """Returns the block the slider adds to its page's load section,
        before the page's own load code: the slider's command, then its ID
        as text. On P, it is `init` and its ID."""
        series = project.settings.model.series
        if series in SERIES_WRITTEN_AS_P:
            return [init_block(place.object_id)]
        return [load_block(series, place.object_id)]


def load_block(series: str, object_id: int) -> bytes:
    """Returns the block a slider of the ID `object_id` adds to its page's
    load section on `series`, T, K, or F: the slider's command, then its ID
    as text."""
    return _LOAD[series] + b"%d" % object_id


@lru_cache(maxsize=None)
def _of(sta: int, psta: int) -> _Slider:
    """Returns the variant of a slider of the sta `sta` and the psta
    `psta`, made once."""
    return _Slider(sta, psta)


def variant(page_object) -> _Slider:
    """Returns what describes the slider `page_object`: the variant of its
    sta and its psta. A sta or a psta its rules refuse, as nxwright's build
    does, is described as one of a colour and of a round cursor."""
    sta, psta = _value(page_object, "sta"), _value(page_object, "psta")
    return _of(sta if sta in TRACKS else _COLOUR, psta if psta in CURSORS else 0)


# The series this module's probes matched (matching.py): T, K in k_probes.py,
# P in p_probes.py, E in e_probes.py, and F in f_probes.py.
SERIES = ("T", "K", "P", "E", "F")

# What the slider has matched with probes (matching.py): a slider at its
# defaults, on each screen model of T and K at each rotation, and on P and E,
# but for these.
MATCHED = [
    Rule("type", "slider", "a slider, its attributes at their defaults but for those below"),
    Rule("attribute", "slider.objname", "any name nxwright's build takes"),
    Rule("attribute", "slider.x", PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT),
    Rule("attribute", "slider.y", PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT),
    Rule("attribute", "slider.w", PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT),
    Rule("attribute", "slider.h", PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT),
    # The Nextion Editor writes each as it is, the val outside the minval
    # and the maxval too, and a minval above the maxval.
    *[Rule("attribute", "slider." + name, "from 0 to 65535, whatever the other two",
           from_to(0, 0xFFFF)) for name in ("val", "minval", "maxval")],
    Rule("attribute", "slider.mode", "0, across, 1, upright, or any other value that fits in its "
         "byte, written as it is"),
    Rule("attribute", "slider.wid", "from 0 to 255, 255 sizing the cursor itself",
         from_to(0, 255)),
    Rule("attribute", "slider.hig", "from 0 to 255, 255 sizing the cursor itself",
         from_to(0, 255)),
    Rule("attribute", "slider.dis", "any value, written as it is"),
    Rule("attribute", "slider.ch", "any value, written as it is"),
    Rule("attribute", "slider.sta", "0, a crop of a picture, 1, a colour, or 2, a picture",
         from_to(0, 2), INVALID_VALUE),
    Rule("attribute", "slider.psta", "0, a round cursor, or 1, a picture; and on P and E 2 "
         "too, a square cursor, its entry's highest there, which nxwright's build refuses on "
         "T, K, and F",
         lambda need: from_to(0, 2 if need.series in SERIES_WRITTEN_AS_P else 1)(need),
         INVALID_VALUE),
] + [Rule("attribute", "slider." + name, *value_rule(name)) for name in ("bco", "bco1", "pco")
] + [
    # A picture's ID is 2 bytes in memory, written as it is, whichever
    # picture it is, and only at the sta or the psta that shows it.
    Rule("attribute", "slider." + name, "any value from 0 to 65535, written as it is: a "
         "picture of the project, or 65535 for none") for name in _PICTURE_NAMES]
