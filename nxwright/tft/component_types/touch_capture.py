"""The touch capture component, as the Nextion Editor 1.68.2 writes it on T
and K, and on P and E (ResearchNotes/tft/touch-capture-component.md gives each
value, and how it was found).

So far it writes a touch capture at its defaults but for its val. A touch
capture has no place or size, and is not drawn: its blocks are one empty
run, then its down and up events. It adds the slider's command to its
page's load section, `09 16 04` on T, `09 18 04` on K, and `09 1d 04` on
F, and its ID, as a slider and a waveform do. Its memory is its val, 1
byte, and three 0 bytes.

Code may read its attributes, its val among them. An assignment may not
set its val: the Nextion Editor
refuses that (statements.sets_only_changeable_attributes). A text
command's destination may set it, as the Nextion Editor compiles that
(instructions/text_commands.py).

On P, its memory is 32 bytes, which start with its record's first 28 bytes
(P_HEAD_SIZE), as a timer's do, then give its val at 28. Its page's load
section gets `init` and its ID in place of the slider's command.
"""
import struct

from nxwright.project.attribute_values import number_from_bytes

from nxwright.tft.component_types import (P_DRAWN_ENTRIES, SERIES_WRITTEN_AS_P,
                                   packed_entries, vscope_entry)
from nxwright.tft.component_types.slider import load_block
from nxwright.tft.instructions.undocumented_commands import init_block
from nxwright.tft.matching import Rule

ENTRIES = 10
EVENTS = ("down", "up")
DRAWN = False

# Each attribute's entry, within the type.
_ENTRY = {"type": 0, "id": 1, "vscope": 3, "val": 7}
# The record's slots that give an entry, and which entry.
_SLOTS = {1: "vscope", 20: "val", 49: "id", 62: "type"}
# The most val a page file keeps, in its 1 byte.
_MOST_VAL = 255
# Its memory on T, K, and F: its val, 1 byte, and three 0 bytes.
MEMORY_FORMAT = "<B3x"
# On P: its memory, which starts with its record's first 28 bytes, then its
# memory on T; and its entries, by number within the type: (name, place from
# its base, highest, lowest, code), its val's as on T.
P_MEMORY_SIZE, P_HEAD_SIZE = 32, 28
P_ENTRIES = {0: P_DRAWN_ENTRIES[0], 1: P_DRAWN_ENTRIES[1], 3: P_DRAWN_ENTRIES[3],
             7: ("val", 28, 0xFFFF, 0, 0x121)}


def drawing(page_object, project, place) -> list:
    """Returns no blocks: a touch capture is not drawn."""
    return []


def data(page_object, project, place) -> bytes:
    """Returns the touch capture's entries: its type, its ID, its vscope,
    and where its val lies in memory, its base. Its val's entry gives
    65535 as its highest, though a page file keeps a val in 1 byte."""
    values = {
        "type": (page_object.attribute("type")[0], 255, 0, 0x101),
        "id": (place.object_id, 255, 0, 0x101),
        "vscope": vscope_entry(page_object),
        "val": (place.base, 0xFFFF, 0, 0x121),
    }
    return packed_entries({_ENTRY[name]: value for name, value in values.items()}, ENTRIES,
                          place)


def memory(page_object, project) -> bytes:
    """Returns the touch capture's starting values: its val, 1 byte, and
    three 0 bytes."""
    val = page_object.attribute("val")
    return struct.pack(MEMORY_FORMAT, 0 if val is None else number_from_bytes(val))


def record_slots() -> dict:
    """Returns the touch capture's slots in its record: {slot: entry within
    the type}."""
    return {slot: _ENTRY[name] for slot, name in _SLOTS.items()}


def attribute_place(name: str) -> int:
    """Returns the entry, within the type, of the attribute `name`, any the
    type writes. Raises KeyError for another."""
    return _ENTRY[name]


def load_start(page_object, project, place, places: dict) -> list:
    """Returns the block the touch capture adds to its page's load section,
    before the page's own load code: a slider's command, then its ID as
    text (slider.load_block). On P, the command is `init`."""
    series = project.settings.model.series
    if series in SERIES_WRITTEN_AS_P:
        return [init_block(place.object_id)]
    return [load_block(series, place.object_id)]


# The series this module's probes matched (matching.py): T, K in k_probes.py,
# P in p_probes.py, E in e_probes.py, and F in f_probes.py.
SERIES = ("T", "K", "P", "E", "F")

# What the touch capture has matched with probes (matching.py): a touch
# capture at its defaults, on each screen model of T and K at each rotation,
# and on P, E, and F, but for these.
MATCHED = [
    Rule("type", "touch-capture", "a touch capture, its attributes at their defaults but for "
         "those below"),
    Rule("attribute", "touch-capture.objname", "any name nxwright's build takes"),
    Rule("attribute", "touch-capture.val", "from 0 to 255, as a page file keeps it",
         lambda need: 0 <= number_from_bytes(need.value) <= _MOST_VAL),
]
