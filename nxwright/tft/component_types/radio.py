"""The radio component, as the Nextion Editor 1.68.2 writes it on T
(ResearchNotes/tft/radio-component.md gives each value, and how it was found),
and on P, where it has no drawing blocks, no switch of its val in its down
event, and its memory gives its values as on T, from 56 (P_ENTRIES).

So far it writes a radio at its defaults but for its place, its size, its
bco, its pco, and its val, 1 when it is chosen. Its memory gives its bco,
pco, and val, 8 bytes.

Its drawing is code of the Nextion Editor's own. It sets the system variable
sya0 to its radius: half its width, less 1 when its width is even. It draws
a filled circle of that radius in its bco, its centre sya0 right of and
below its top left, then the circle's edge. When its val is 1, it draws a
filled circle of half that radius on the same centre, in its pco. Its down
event starts with a checkbox's code that switches its val.
"""
import struct

from nxwright.project.attribute_values import number_from_bytes

from nxwright.tft.component_types import (BORDER_DARK, P_DRAWN_ENTRIES, PLACE_WORDS, entry_operand,
                                   object_entries, packed_entries, place_and_size,
                                   place_fits_its_record, value_operand, value_rule)
# The frame calls the type's background_fill, which is the plain fill.
from nxwright.tft.component_types import background_fill  # noqa: F401
from nxwright.tft.component_types.checkbox import val_switch
from nxwright.tft.control_statements import COMPARISONS, comparison_block, jump_block, size_of
from nxwright.tft.instructions import drawing_commands
from nxwright.tft.matching import Rule
from nxwright.tft.reasons import DOES_NOT_FIT
from nxwright.tft.statements import drawing_operand

ENTRIES = 30
EVENTS = ("down", "up")

# Where each value lies in a radio's memory, from its base.
_BCO, _PCO, _VAL = 0, 2, 4
# Its starting values on T, K, and F, in their order in memory, and their
# form there (memory).
MEMORY_VALUES = ("bco", "pco", "val")
MEMORY_FORMAT = "<HHB3x"
# Each attribute's entry, within the type.
_ENTRY = {"type": 0, "id": 1, "vscope": 3, "x": 9, "y": 10, "w": 11, "h": 12, "endx": 13,
          "endy": 14, "bco": 19, "pco": 20, "val": 21}
# The record's slots that give an entry, and which entry.
_SLOTS = {1: "vscope", 4: "bco", 16: "pco", 20: "val", 42: "x", 43: "y", 44: "endx",
          45: "endy", 46: "w", 47: "h", 49: "id", 62: "type"}
# The defaults of its bco, pco, and val.
_DEFAULTS = {"bco": 0xFFFF, "pco": 0, "val": 1}
# Its entries on P, by number within the type, as on T: (name, place from
# its base, highest, lowest, code). Its values lie in its memory as on T,
# from 56, after its record's head and its effect's values.
P_ENTRIES = {**P_DRAWN_ENTRIES, 19: ("bco", 56 + _BCO, 0xFFFF, 0, 0x232),
             20: ("pco", 56 + _PCO, 0xFFFF, 0, 0x232), 21: ("val", 56 + _VAL, 1, 0, 0x131)}
# Its memory on P: what its record's head holds and its effect's values,
# then its values, as on T (memory).
P_MEMORY_SIZE = 64
# The system variable the drawing works the radius out in.
_RADIUS = "sya0"


def drawing(page_object, project, place) -> list:
    """Returns the radio's drawing: sya0 set to its width's last bit; a
    comparison of sya0 with 0, which jumps past the next two blocks when it
    fails; sya0 set to its width over 2, less 1; a jump past the next block;
    sya0 set to its width over 2; cirs, a filled circle at its top left plus
    sya0, of radius sya0, in its bco; cir, the circle's edge, in the
    border's dark colour; a comparison of its val with 1, which jumps past
    the next block when it fails; then cirs of radius sya0 over 2, in its
    pco."""
    x, y, w, _ = place_and_size(page_object)
    series = project.settings.model.series
    commands, comparisons = drawing_commands.COMMANDS[series], COMPARISONS[series]
    radius = drawing_operand(_RADIUS, project)

    def entry(name: str) -> bytes:
        return entry_operand(place.first_entry + _ENTRY[name])

    def circle(name: str, size: bytes, colour: bytes) -> bytes:
        return (commands[name].block_start() + b"%d+" % x + radius
                + b",%d+" % y + radius + b"," + size + b"," + colour)

    odd = radius + b"=%d/2" % w
    even = [radius + b"=%d/2-1" % w, jump_block(size_of([odd]))]
    dot = circle("cirs", radius + b"/2", entry("pco"))
    return ([radius + b"=%d&1" % w,
             comparison_block(radius, comparisons["=="], b"0", size_of(even))]
            + even + [odd, circle("cirs", radius, entry("bco")),
                      circle("cir", radius, value_operand(BORDER_DARK)),
                      comparison_block(entry("val"), comparisons["=="], b"1", size_of([dot])),
                      dot])


def data(page_object, project, place) -> bytes:
    """Returns the radio's entries: where each of its values lies in
    memory."""
    base = place.base
    values = {
        "bco": (base + _BCO, 0xFFFF, 0, 0x232), "pco": (base + _PCO, 0xFFFF, 0, 0x232),
        "val": (base + _VAL, 1, 0, 0x131),
    }
    entries = object_entries(page_object, place.object_id)
    entries.update({_ENTRY[name]: value for name, value in values.items()})
    return packed_entries(entries, ENTRIES, place)


def memory(page_object, project) -> bytes:
    """Returns the radio's starting values: its bco and pco, 2 bytes each,
    its val, then three 0 bytes."""
    values = {name: number_from_bytes(page_object.attribute(name))
              if page_object.attribute(name) is not None else default
              for name, default in _DEFAULTS.items()}
    return struct.pack(MEMORY_FORMAT, *(values[name] for name in MEMORY_VALUES))


def record_slots() -> dict:
    """Returns the radio's slots in its record: {slot: entry within the
    type}."""
    return {slot: _ENTRY[name] for slot, name in _SLOTS.items()}


def attribute_place(name: str) -> int:
    """Returns the entry, within the type, of the attribute `name`, any the
    type writes. Raises KeyError for another."""
    return _ENTRY[name]


def event_start(page_object, project, place, event: str) -> list:
    """Returns the blocks the Nextion Editor writes at the start of the
    radio's down event, a checkbox's, which switch its val. Its up event
    has none."""
    if event != "down":
        return []
    return val_switch(entry_operand(place.first_entry + _ENTRY["val"]),
                      project.settings.model.series)


# The series this module's probes matched (matching.py): T, K in k_probes.py,
# P in p_probes.py, E in e_probes.py, and F in f_probes.py.
SERIES = ("T", "K", "P", "E", "F")

# What the radio has matched with probes (matching.py): a radio at its
# defaults, on each screen model of T and K at each rotation, and on P and E,
# but for these.
MATCHED = [
    Rule("type", "radio", "a radio, its attributes at their defaults but for those below"),
    Rule("attribute", "radio.objname", "any name nxwright's build takes"),
    Rule("attribute", "radio.x", PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT),
    Rule("attribute", "radio.y", PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT),
    Rule("attribute", "radio.w", PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT),
    Rule("attribute", "radio.h", PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT),
    Rule("attribute", "radio.bco", *value_rule("bco")),
    Rule("attribute", "radio.pco", *value_rule("pco")),
    Rule("attribute", "radio.val", "any value, written as it is"),
]
