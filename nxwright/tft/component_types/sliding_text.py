"""The sliding text component, a type the P and E series have and T and K
have not, as the Nextion Editor 1.68.2 writes it on P, where its values lie
in its memory as P_ENTRIES gives them
(ResearchNotes/tft/sliding-text-component.md).

On P, a sliding text, as every component, has no drawing blocks: the screen
draws it from its memory. Its memory starts with what its record's head
holds. Then it gives its values, with its txt_maxl at 70 and the place of
its txt at 72, and its path_m at 82 and the place of its path at 84. Both
its txt and its path lie after its page's components' memory, in that
order, as a select's do (select.py). Its txt gives its lines, each ending
in "\\r\\n" but the last. Its path's room is its path_m + 1 bytes, rounded
up to 4, or its txt_maxl + 1 when its path_m is 0, its default
(P_ROOMS_WHEN_ZERO). Its leftshow, which has no entry, lies in its memory
alone, at 67 (p_memory_extras). Its key has no entry either: one that binds
a keyboard, 1 to 4, adds the three lines that open the keyboard's page at
the end of its Touch Release event, as a text's does
(component_types.key_lines), and any other is written nowhere. Its page's
load section starts with init and its ID, as a select's does.
"""
import sys

from nxwright.project.attribute_values import number_from_bytes

from nxwright.tft.component_types import (P_DRAWN_ENTRIES, PLACE_WORDS, TXT_MAXL_WORDS, attribute_number,
                                   from_to, p_border_and_background_rules, place_fits_its_record,
                                   room_covered, text_in_room, value_rule, with_p_background,
                                   with_p_border)
from nxwright.tft.instructions.undocumented_commands import init_block
from nxwright.tft.matching import Rule
from nxwright.tft.reasons import DOES_NOT_FIT

EVENTS = ("down", "up")
# Its entries on P, by number within the type: (name, place from its base,
# highest, lowest, code), its font's highest and its txt's code set by
# component_types.p_table. 16 to 18 stay empty, where an effect's first and
# time go (component_types.with_p_effect), and so do 21, 26, 34, and 35.
P_ENTRIES = {
    **P_DRAWN_ENTRIES, 19: ("sta", 56, 3, 0, 0x121), 20: ("style", 57, 3, 0, 0x121),
    22: ("font", 61, 0, 0, 0x131), 23: ("bco", 62, 0xFFFF, 0, 0x232),
    24: ("pco", 64, 0xFFFF, 0, 0x232), 25: ("xcen", 66, 2, 0, 0x131),
    27: ("left", 68, 2, 0, 0x131), 28: ("ch", 69, 32, 0, 0x131), 29: ("txt", 0, 0, 0, 0x3F),
    30: ("txt_maxl", 70, 0xFFFE, 0, 0x222), 31: ("isbr", 76, 1, 0, 0x131),
    32: ("spax", 77, 255, 0, 0x131), 33: ("spay", 78, 255, 0, 0x131),
    36: ("maxval_y", 92, 2 ** 31 - 1, -2 ** 31, 0x429),
    37: ("val_y", 96, 2 ** 31 - 1, -2 ** 31, 0x439)}
# How many entries it has, the last ones empty.
ENTRIES = 46
# The top byte of the owner field of these attributes' entries
# (component_types.p_component_entries); every other entry gives 0 there.
P_OWNER_TOPS = {"txt": 0x01, "left": 0x02, "xcen": 0x03, "isbr": 0x04, "spax": 0x05,
                "spay": 0x06, "font": 0x07}
# Its path has no entry in its data, but the Nextion Editor names it in code
# as entry 34 of its own (component_types.code_entry).
P_CODE_ENTRIES = {"path": 34}
# The entry of each attribute it writes, by name, and its path's.
_ENTRY_OF = {**{name: entry for entry, (name, *_) in P_ENTRIES.items()}, **P_CODE_ENTRIES}
# Its memory on P, and its texts (P_TEXTS): where in its memory the place of
# each lies, which no entry gives, and its txt_maxl and its path_m. Its
# texts lie after its page's components' memory. Its path has no entry in
# its data, but is entry 34 in code (P_CODE_ENTRIES).
P_MEMORY_SIZE = 116
P_TEXTS = {72: ("txt", "txt_maxl", 70), 84: ("path", "path_m", 82)}
# The values of its memory on P that no entry gives, by attribute: where
# each lies, 1 byte. Its leftshow lies before its left.
P_UNENTERED = {"leftshow": 67}
# At a path_m of 0, its txt_maxl gives its path's room.
P_ROOMS_WHEN_ZERO = {"path_m": "txt_maxl"}


def load_start(page_object, project, place, places: dict) -> list:
    """Returns the blocks the sliding text adds to its page's load section,
    before the page's own load code: the command init with its ID, as
    `init 1`."""
    return [init_block(place.object_id)]


def p_memory_extras(page_object, project, place) -> dict:
    """Returns the bytes of the sliding text's memory on P that no entry
    gives, beside its texts' (component_types.p_memory_extras): its
    leftshow."""
    return {at: bytes([attribute_number(page_object, name)]) for name, at in P_UNENTERED.items()}


def attribute_place(name: str) -> int:
    """Returns the entry, within the type, of the attribute `name`, any the
    type writes (P_ENTRIES) or its path, which code names, as in
    `slt0.val_y`. Raises KeyError for another."""
    return _ENTRY_OF[name]


def variant(page_object):
    """Returns what describes the sliding text `page_object`: its module, its
    entries as its style and its sta change them
    (component_types.with_p_border, with_p_background)."""
    return with_p_background(with_p_border(sys.modules[__name__], page_object), page_object)


# The series this module's probes matched (matching.py): P in p_probes.py,
# and E in e_probes.py. T and K have no sliding text.
SERIES = ("P", "E")


def _path_fits(need) -> bool:
    """Whether the path of the attribute `need` holds no more bytes than its
    room: its path_m, or its txt_maxl when its path_m is 0
    (P_ROOMS_WHEN_ZERO). It is written as its bytes, whatever its
    characters."""
    room = (number_from_bytes(need.context["path_m"])
            or number_from_bytes(need.context["txt_maxl"]))
    return len(need.value) <= room


# What the sliding text has matched with probes (matching.py): a sliding
# text at its defaults, on P and E, but for these.
MATCHED = [
    Rule("type", "sliding-text",
         "a sliding text, its attributes at their defaults but for those below"),
    Rule("attribute", "sliding-text.objname", "any name nxwright's build takes"),
    *[Rule("attribute", "sliding-text." + name,
           PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT)
      for name in ("x", "y", "w", "h")],
    # Its border and what lies behind it, as its probes on P and E showed.
    *[Rule("attribute", "sliding-text." + name, words, covers, reason)
      for name, words, covers, reason in p_border_and_background_rules(3)],
    Rule("attribute", "sliding-text.font", "any font of the project"),
    Rule("attribute", "sliding-text.txt", "lines of any characters, the lines between "
         "\"\\r\\n\", or none, no more than its txt_maxl", text_in_room("txt_maxl")),
    Rule("attribute", "sliding-text.txt_maxl", TXT_MAXL_WORDS,
         room_covered("txt", 0xFFFF, low=0), DOES_NOT_FIT),
    Rule("attribute", "sliding-text.path_m", "from 0 to 65534, the most the Nextion Editor "
         "takes (\"Out of range\" past it), its path's room its txt_maxl's at 0",
         from_to(0, 0xFFFE)),
    Rule("attribute", "sliding-text.path", "lines of any characters, the lines between "
         "\"\\r\\n\", or none, no more than its path_m, or its txt_maxl at a "
         "path_m of 0",
         _path_fits),
    Rule("attribute", "sliding-text.left", "any value, written as it is"),
    Rule("attribute", "sliding-text.leftshow", "any value of its byte, written in its "
         "memory alone, as it has no entry", from_to(0, 255)),
    Rule("attribute", "sliding-text.ch", "any value, written as it is"),
    # Where it is scrolled to, 4 bytes each, as a file browser's are.
    *[Rule("attribute", "sliding-text." + name, "from -2147483648 to 2147483647, its entry's "
           "limits", from_to(-2 ** 31, 2 ** 31 - 1))
      for name in ("maxval_y", "val_y")],
] + [Rule("attribute", "sliding-text." + name, *value_rule(name))
     for name in ("bco", "pco", "xcen", "isbr", "spax", "spay")]
