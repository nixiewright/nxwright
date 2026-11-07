"""The hotspot component, as the Nextion Editor 1.68.2 writes it on T and on K
(ResearchNotes/tft/hotspot-component.md gives each value, and how it was found).

So far it writes a hotspot at its defaults but for its place and its size.
A hotspot is an area that takes touches. Its drawing has no blocks, but it
is written as a drawn object: its run after the drawing is the plain fill
of its area, and its record has its place and size. Its record has no first
block's place, as a timer's (frame.py). It has no memory. Code may read
its attributes, such as its x, and the screen's commands take it by its
name.

On P, it has no drawing blocks. Its memory is 56 bytes, what its record's
head holds and its effect's values, as every drawn component's there, but
for a 0 where theirs keeps their drag, and another where they keep their
aph. Its entries are a drawn component's there, but its drag's, its aph's,
and its effect's give their values themselves, not places in its memory:
0, 127, and 0 at their defaults (P_ENTRIES).
"""
from nxwright.tft.component_types import (P_DRAWN_ENTRIES, PLACE_WORDS, FixedValue, object_entries,
                                   packed_entries, place_fits_its_record)
# The frame calls the type's background_fill, which is the plain fill.
from nxwright.tft.component_types import background_fill  # noqa: F401
from nxwright.tft.matching import Rule
from nxwright.tft.reasons import DOES_NOT_FIT

ENTRIES = 27
EVENTS = ("down", "up")
# The series this module's probes matched (matching.py): T, K in k_probes.py,
# P in p_probes.py, E in e_probes.py, and F in f_probes.py.
SERIES = ("T", "K", "P", "E", "F")

# Each attribute's entry, within the type.
_ENTRY = {"type": 0, "id": 1, "vscope": 3, "x": 9, "y": 10, "w": 11, "h": 12, "endx": 13,
          "endy": 14}
# The record's slots that give an entry, and which entry.
_SLOTS = {1: "vscope", 42: "x", 43: "y", 44: "endx", 45: "endy", 46: "w", 47: "h",
          49: "id", 62: "type"}
# Its entries on P, by number within the type: (name, place from its base,
# highest, lowest, code). Its memory on T has no bytes, so its memory on P
# ends after its effect's values.
P_ENTRIES = {**P_DRAWN_ENTRIES, 4: ("drag", FixedValue(0), 1, 0, 0x111),
             6: ("aph", FixedValue(127), 127, 0, 0x111),
             15: ("effect", FixedValue(0), 8, 0, 0x111)}
P_MEMORY_SIZE = 56
# Where a drawn component's memory on P keeps its drag and its aph, which a
# hotspot's keeps at 0, whatever they are.
_P_DRAG = P_DRAWN_ENTRIES[4][1]
_P_APH = P_DRAWN_ENTRIES[6][1]


def drawing(page_object, project, place) -> list:
    """Returns no blocks: a hotspot draws nothing of its own."""
    return []


def data(page_object, project, place) -> bytes:
    """Returns the hotspot's entries: a drawn object's alone, its type, its
    ID, its vscope, and its place, size, and edges."""
    return packed_entries(object_entries(page_object, place.object_id), ENTRIES, place)


def memory(page_object, project) -> bytes:
    """Returns no starting values: a hotspot has no memory."""
    return b""


def p_memory_extras(page_object, project, place) -> dict:
    """Returns the bytes of the hotspot's memory on P that its record's head
    would give otherwise: a 0 where a drawn component's memory keeps its
    drag, and another where it keeps its aph, as their entries give their
    values themselves."""
    return {_P_DRAG: bytes(1), _P_APH: bytes(1)}


def record_slots() -> dict:
    """Returns the hotspot's slots in its record: {slot: entry within the type}."""
    return {slot: _ENTRY[name] for slot, name in _SLOTS.items()}


def attribute_place(name: str) -> int:
    """Returns the entry, within the type, of the attribute `name`, any the
    type writes. Raises KeyError for another."""
    return _ENTRY[name]


# What the hotspot has matched with probes (matching.py): a hotspot at its
# defaults, on each screen model of T and K at each rotation, and on P, E, and
# F, but for these.
MATCHED = [
    Rule("type", "hotspot", "a hotspot, its attributes at their defaults but for those below"),
    Rule("attribute", "hotspot.objname", "any name nxwright's build takes"),
    Rule("attribute", "hotspot.x", PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT),
    Rule("attribute", "hotspot.y", PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT),
    Rule("attribute", "hotspot.w", PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT),
    Rule("attribute", "hotspot.h", PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT),
]
