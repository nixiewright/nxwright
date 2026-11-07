"""The crop component, as the Nextion Editor 1.68.2 writes it on T
(ResearchNotes/tft/crop-component.md gives each value, and how it was found).

So far it writes a crop at its defaults but for its place, its size, its
picc, the project's picture it shows a part of, or 65535 for none, and its
vvs0 and vvs1, where in that picture its part starts. Its drawing is the
drawing command xpic: its place and size, then where its part starts, its
x, a plus, and its vvs0, then its y, a plus, and its vvs1, each vvs a
number as code gives one, then its picc's entry. The screen reads a vvs as
signed 16 bits. Its memory is its picc, 2 bytes, then six 0 bytes.

On P, it has no drawing blocks. Its memory is 64 bytes: what its record's
head holds and its effect's values, 56 bytes, as every drawn component's
there, then its picc, its vvs0, and its vvs1, 2 bytes each, and two 0
bytes. Its entries keep T's numbers, but its vvs0's and its vvs1's give
their places in memory, not their values (P_ENTRIES).
"""
import struct

from nxwright.project.attribute_values import number_from_bytes

from nxwright.tft.component_types import (P_DRAWN_ENTRIES, PLACE_WORDS, XPIC, entry_operand,
                                   object_entries, packed_entries, place_and_size,
                                   place_fits_its_record)
# The frame calls the type's background_fill, which is the plain fill.
from nxwright.tft.component_types import background_fill  # noqa: F401
from nxwright.tft.matching import Rule
from nxwright.tft.reasons import DOES_NOT_FIT
from nxwright.tft.statements import drawing_operand

ENTRIES = 30
EVENTS = ("down", "up")
# The series this module's probes matched (matching.py): T, K in k_probes.py,
# P in p_probes.py, E in e_probes.py, and F in f_probes.py.
SERIES = ("T", "K", "P", "E", "F")

# Each attribute's entry, within the type.
_ENTRY = {"type": 0, "id": 1, "vscope": 3, "x": 9, "y": 10, "w": 11, "h": 12, "endx": 13,
          "endy": 14, "picc": 19, "vvs0": 20, "vvs1": 21}
# The record's slots that give an entry, and which entry.
_SLOTS = {1: "vscope", 5: "picc", 42: "x", 43: "y", 44: "endx", 45: "endy", 46: "w", 47: "h",
          49: "id", 50: "vvs0", 51: "vvs1", 62: "type"}
# The picc of a crop that shows none, its default.
_NO_PICTURE = 65535
# Its memory on T: its picc, 2 bytes, then six 0 bytes.
MEMORY_FORMAT = "<H6x"
# Its entries on P, by number within the type, as on T: (name, place from
# its base, highest, lowest, code). Its picc's highest is the project's last
# picture (P_LAST_RESOURCE, component_types.p_table).
P_ENTRIES = {**P_DRAWN_ENTRIES, 19: ("picc", 56, 0, 0, 0x232),
             20: ("vvs0", 58, 0x7FFFFFFF, -0x80000000, 0x238),
             21: ("vvs1", 60, 0x7FFFFFFF, -0x80000000, 0x238)}
P_LAST_RESOURCE = {"picc": "picture"}
P_MEMORY_SIZE = 64


def drawing(page_object, project, place) -> list:
    """Returns the crop's drawing: the drawing command xpic, with its place
    and size, where its part of its picture starts, and its picc's entry."""
    x, y, w, h = place_and_size(page_object)
    # Each vvs is a number as code gives one: 4 characters or more as 03 and
    # its value, as -25536 is.
    start = b"".join(b"%d+" % place_value + drawing_operand(str(_value(page_object, name)),
                                                           project) + b","
                     for place_value, name in ((x, "vvs0"), (y, "vvs1")))
    return [XPIC + b"%d,%d,%d,%d," % (x, y, w, h)
            + start + entry_operand(place.first_entry + _ENTRY["picc"])]


def data(page_object, project, place) -> bytes:
    """Returns the crop's entries: a drawn object's, where its picc lies in
    memory, from 0 to the project's last picture, and its vvs0 and vvs1, as
    their values, signed (_value)."""
    pictures = project.resource_count("picture")
    entries = object_entries(page_object, place.object_id)
    entries[_ENTRY["picc"]] = (place.base, pictures - 1, 0, 0x232)
    for name in ("vvs0", "vvs1"):
        entries[_ENTRY[name]] = (_value(page_object, name), 0x7FFFFFFF, -0x80000000, 0x208)
    return packed_entries(entries, ENTRIES, place)


def memory(page_object, project) -> bytes:
    """Returns the crop's starting values: its picc, 2 bytes, then six 0
    bytes."""
    picc = page_object.attribute("picc")
    return struct.pack(MEMORY_FORMAT, _NO_PICTURE if picc is None else number_from_bytes(picc))


def record_slots() -> dict:
    """Returns the crop's slots in its record: {slot: entry within the type}."""
    return {slot: _ENTRY[name] for slot, name in _SLOTS.items()}


def attribute_place(name: str) -> int:
    """Returns the entry, within the type, of the attribute `name`, any the
    type writes. Raises KeyError for another."""
    return _ENTRY[name]


def _value(page_object, name: str) -> int:
    """Returns the crop's vvs0 or vvs1, 0 by default, as the screen reads it:
    2 bytes, signed, so that 40000 is -25536 and 65535 is -1."""
    value = page_object.attribute(name)
    value = 0 if value is None else number_from_bytes(value)
    return value - 0x10000 if value >= 0x8000 else value


# What the crop has matched with probes (matching.py): a crop at its
# defaults, on each screen model of T and K at each rotation, and on P, E, and
# F, but for these.
MATCHED = [
    Rule("type", "crop", "a crop, its attributes at their defaults but for those below"),
    Rule("attribute", "crop.objname", "any name nxwright's build takes"),
    Rule("attribute", "crop.x", PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT),
    Rule("attribute", "crop.y", PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT),
    Rule("attribute", "crop.w", PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT),
    Rule("attribute", "crop.h", PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT),
    # A picc is 2 bytes in memory, written as it is, whichever picture it is.
    Rule("attribute", "crop.picc", "any value from 0 to 65535, written as it is: a picture of "
         "the project, or 65535 for none"),
    # A vvs0 or a vvs1 is 2 bytes, read as signed 16 bits, within its picture,
    # past its edge, and past 32767.
    Rule("attribute", "crop.vvs0", "any value from 0 to 65535, read as signed 16 bits"),
    Rule("attribute", "crop.vvs1", "any value from 0 to 65535, read as signed 16 bits"),
]
