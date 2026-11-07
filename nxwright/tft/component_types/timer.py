"""The timer component, as the Nextion Editor 1.68.2 writes it on T
(ResearchNotes/tft/timer-component.md gives each value, and how it was found).

So far it writes a timer at its defaults but for its tim and en, with the
code of its timer event. A timer is not drawn: its blocks are one empty run,
then its timer event. Its memory is its tim, 2 bytes, its en, 1 byte, and a
0 byte.

The Nextion Editor writes code of its own for each timer:

  - at the start of its timer event, an "S " block: 53 20, then 03 and its
    number among the project's timer events (event_start);
  - in its page's load section, before the page's own load code, the
    command timerset (09 22 08 on T, 09 23 08 on K, 09 24 08 on F) with
    its en, its ID, and its tim, then an "L " block: 4c 20, then 03 and the
    place, in the user code, of its timer event's code after the "S " block
    (load_start).

On P, its memory is 32 bytes, which start with its record's first 28 bytes
(P_HEAD_SIZE), as an audio's do, then give its tim and its en at 28 and
30. Its timer event has no "S " block there, and its page's load section
gets `init` and its ID in place of timerset and the "L " block.
"""
import struct

from nxwright.project.attribute_values import number_from_bytes

from nxwright.tft.component_types import (P_DRAWN_ENTRIES, SERIES_WRITTEN_AS_P, entry_operand,
                                   packed_entries, value_operand, vscope_entry)
from nxwright.tft.instructions.undocumented_commands import init_block
from nxwright.tft.label_numbers import S_BLOCK_START
from nxwright.tft.matching import Rule
from nxwright.tft.tft_file import encode_blocks

ENTRIES = 11
EVENTS = ("timer",)
DRAWN = False
# The numbers a timer takes in the first pass that numbers its page's "S "
# blocks, on T and K (label_numbers.py).
FIRST_PASS_NUMBERS = 1
# The series this module's probes matched (matching.py): T, K in k_probes.py,
# P in p_probes.py, E in e_probes.py, and F in f_probes.py.
SERIES = ("T", "K", "P", "E", "F")

# Each attribute's entry, within the type.
_ENTRY = {"type": 0, "id": 1, "vscope": 3, "tim": 7, "en": 8}
# The record's slots that give an entry, and which entry.
_SLOTS = {1: "vscope", 33: "tim", 34: "en", 49: "id", 62: "type"}
# What the top byte of the owner field of tim's and en's entries gives, the
# same for every timer seen; every other entry seen gives 0 there.
_OWNER_TOPS = {_ENTRY["tim"]: 1, _ENTRY["en"]: 2}
# A timer at its defaults.
_DEFAULTS = {"tim": 400, "en": 1}
# Where the en lies in a timer's memory, after its tim's 2 bytes, and the
# memory's form on T: its tim, 2 bytes, its en, 1 byte, and a 0 byte.
_EN = 2
MEMORY_FORMAT = "<HBx"
# On P: its memory, which starts with its record's first 28 bytes; its
# entries, by number within the type: (name, place from its base, highest,
# lowest, code); and the top byte of tim's and en's owner field, as on T.
P_MEMORY_SIZE, P_HEAD_SIZE = 32, 28
P_ENTRIES = {0: P_DRAWN_ENTRIES[0], 1: P_DRAWN_ENTRIES[1], 3: P_DRAWN_ENTRIES[3],
             7: ("tim", 28, 65534, 50, 0x232), 8: ("en", 30, 1, 0, 0x131)}
P_OWNER_TOPS = {"tim": 1, "en": 2}

# The blocks the Nextion Editor writes of its own for a timer, and for a
# scrolling text (scrolling_text.py). The command timerset is by series: K
# and F number it their own ways.
TIMER_EVENT_START = S_BLOCK_START
TIMERSET = {"T": b"\x09\x22\x08", "K": b"\x09\x23\x08", "F": b"\x09\x24\x08"}
CODE_PLACE = b"L "


def drawing(page_object, project, place) -> list:
    """Returns no blocks: a timer is not drawn."""
    return []


def data(page_object, project, place) -> bytes:
    """Returns the timer's entries: its type, its ID, its vscope, and
    where its tim and its en lie in memory."""
    values = {
        "type": (page_object.attribute("type")[0], 255, 0, 0x101),
        "id": (place.object_id, 255, 0, 0x101),
        "vscope": vscope_entry(page_object),
        "tim": (place.base, 65534, 50, 0x232),
        "en": (place.base + _EN, 1, 0, 0x131),
    }
    return packed_entries({_ENTRY[name]: value for name, value in values.items()}, ENTRIES,
                          place, owner_tops=_OWNER_TOPS)


def memory(page_object, project) -> bytes:
    """Returns the timer's starting values: its tim, 2 bytes, its en, 1
    byte, and a 0 byte."""
    return struct.pack(MEMORY_FORMAT, _value(page_object, "tim"), _value(page_object, "en"))


def record_slots() -> dict:
    """Returns the timer's slots in its record: {slot: entry within the type}."""
    return {slot: _ENTRY[name] for slot, name in _SLOTS.items()}


def attribute_place(name: str) -> int:
    """Returns the entry, within the type, of the attribute `name`, any the
    type writes. Raises KeyError for another."""
    return _ENTRY[name]


def event_start(page_object, project, place, event: str) -> list:
    """Returns the "S " block that starts the timer's timer event, of its
    second number (ObjectPlace.timer_numbers). With timers alone, and no
    labels, that is twice the timers on the pages before the timer's, plus
    the timers on its page, plus the timer's place among them, counted from
    0, as seen with up to twelve timers on a page and timers on three
    pages."""
    return [TIMER_EVENT_START + value_operand(place.timer_numbers[1])]


def load_start(page_object, project, place, places: dict) -> list:
    """Returns the blocks the timer adds to its page's load section, before
    the page's own load code: the command timerset with its en, its ID,
    and its tim, and the "L " block with the place, in the user code, of its
    timer event's code after its "S " block. `places` are the places of the
    timer's record (frame.py). On P, it is `init` and the timer's ID alone."""
    if project.settings.model.series in SERIES_WRITTEN_AS_P:
        return [init_block(place.object_id)]
    start = event_start(page_object, project, place, "timer")
    return load_blocks(project.settings.model.series, place,
                       places["timer"] + len(encode_blocks(start)))


def load_blocks(series: str, place, code: int) -> list:
    """Returns the blocks a timer at `place` adds to its page's load section
    on `series`, T, K, or F: the command timerset with its en's entry, its
    ID, and its tim's entry, then the "L " block with `code`, the place in
    the user code of its timer event's code after its "S " block."""
    def entry(name: str) -> bytes:
        return entry_operand(place.first_entry + _ENTRY[name])

    return [TIMERSET[series] + entry("en") + b",%d," % place.object_id + entry("tim") + b",0",
            CODE_PLACE + value_operand(code)]


def _value(page_object, name: str) -> int:
    value = page_object.attribute(name)
    return _DEFAULTS[name] if value is None else number_from_bytes(value)


# What the timer has matched with probes (matching.py): a timer at its
# defaults, on each screen model of T and K at each rotation, and on P, E, and
# F, but for these.
MATCHED = [
    Rule("type", "timer", "a timer, its attributes at their defaults but for those below"),
    Rule("attribute", "timer.objname", "any name nxwright's build takes"),
    Rule("attribute", "timer.tim", "any value, written as it is"),
    Rule("attribute", "timer.en", "0, 1, or any other value that fits in its byte, written as it "
         "is"),
]
