"""The picture component, as the Nextion Editor 1.68.2 writes it on T
(ResearchNotes/tft/picture-component.md gives each value, and how it was found).

So far it writes a picture at its defaults but for its place, its size, and
its pic, the project's picture it shows, or 65535 for none. Its drawing is
the drawing command pic, at its place, with its pic's entry. Its memory is
its pic, 2 bytes, then two 0 bytes.

On P, it has no drawing blocks. Its memory is 60 bytes: what its record's
head holds and its effect's values, 56 bytes, as every drawn component's
there, then its memory on T, its pic at 56. Its entries keep T's numbers
(P_ENTRIES).
"""
import struct

from nxwright.project.attribute_values import number_from_bytes

from nxwright.tft.component_types import (P_DRAWN_ENTRIES, PIC, PLACE_WORDS, entry_operand,
                                   object_entries, packed_entries, place_and_size,
                                   place_fits_its_record)
# The frame calls the type's background_fill, which is the plain fill.
from nxwright.tft.component_types import background_fill  # noqa: F401
from nxwright.tft.matching import Rule
from nxwright.tft.reasons import DOES_NOT_FIT

ENTRIES = 28
EVENTS = ("down", "up")
# The series this module's probes matched (matching.py): T, K in k_probes.py,
# P in p_probes.py, E in e_probes.py, and F in f_probes.py.
SERIES = ("T", "K", "P", "E", "F")

# Each attribute's entry, within the type.
_ENTRY = {"type": 0, "id": 1, "vscope": 3, "x": 9, "y": 10, "w": 11, "h": 12, "endx": 13,
          "endy": 14, "pic": 19}
# The record's slots that give an entry, and which entry.
_SLOTS = {1: "vscope", 6: "pic", 42: "x", 43: "y", 44: "endx", 45: "endy", 46: "w", 47: "h",
          49: "id", 62: "type"}
# The pic of a picture that shows none, its default.
_NO_PICTURE = 65535
# Its memory on T: its pic, 2 bytes, then two 0 bytes.
MEMORY_FORMAT = "<H2x"
# Its entries on P, by number within the type, as on T: (name, place from
# its base, highest, lowest, code). Its pic's highest is the project's last
# picture (P_LAST_RESOURCE, component_types.p_table).
P_ENTRIES = {**P_DRAWN_ENTRIES, 19: ("pic", 56, 0, 0, 0x232)}
P_LAST_RESOURCE = {"pic": "picture"}
P_MEMORY_SIZE = 60


def drawing(page_object, project, place) -> list:
    """Returns the picture's drawing: the drawing command pic, at its place,
    with its pic's entry."""
    x, y, _, _ = place_and_size(page_object)
    return [PIC + b"%d,%d," % (x, y)
            + entry_operand(place.first_entry + _ENTRY["pic"])]


def data(page_object, project, place) -> bytes:
    """Returns the picture's entries: its type, its ID, its vscope, its
    place and size, and where its pic lies in memory, from 0 to the
    project's last picture."""
    pictures = project.resource_count("picture")
    entries = object_entries(page_object, place.object_id)
    entries[_ENTRY["pic"]] = (place.base, pictures - 1, 0, 0x232)
    return packed_entries(entries, ENTRIES, place)


def memory(page_object, project) -> bytes:
    """Returns the picture's starting values: its pic, 2 bytes, then two 0
    bytes."""
    pic = page_object.attribute("pic")
    return struct.pack(MEMORY_FORMAT, _NO_PICTURE if pic is None else number_from_bytes(pic))


def record_slots() -> dict:
    """Returns the picture's slots in its record: {slot: entry within the type}."""
    return {slot: _ENTRY[name] for slot, name in _SLOTS.items()}


def attribute_place(name: str) -> int:
    """Returns the entry, within the type, of the attribute `name`, any the
    type writes. Raises KeyError for another."""
    return _ENTRY[name]


# What the picture has matched with probes (matching.py): a picture at its
# defaults, on each screen model of T and K at each rotation, and on P, E, and
# F, but for these.
MATCHED = [
    Rule("type", "picture", "a picture, its attributes at their defaults but for those below"),
    Rule("attribute", "picture.objname", "any name nxwright's build takes"),
    Rule("attribute", "picture.x", PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT),
    Rule("attribute", "picture.y", PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT),
    Rule("attribute", "picture.w", PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT),
    Rule("attribute", "picture.h", PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT),
    # A pic is 2 bytes in memory, written as it is, whichever picture it is.
    Rule("attribute", "picture.pic", "any value from 0 to 65535, written as it is: a "
         "picture of the project, or 65535 for none"),
]
