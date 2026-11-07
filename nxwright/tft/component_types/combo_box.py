"""The combo-box component, a type the P and E series have and T and K have
not, as the Nextion Editor 1.68.2 writes it on P, where its values lie in
its memory as P_ENTRIES gives them (ResearchNotes/tft/combo-box-component.md).

On P, a combo-box, as every component, has no drawing blocks: the screen
draws it from its memory. Its memory starts with what its record's head
holds. Then it gives its values, with its txt_maxl at 70 and the place of
its txt at 72, and its path_m at 86 and the place of its path at 88. Both
its txt and its path lie after its page's components' memory, in that
order, as a select's do (select.py). Its path gives its items, one a line,
each line ending in "\\r\\n" but the last. Its drastate, which has no
entry, lies in its memory alone, at 106 (p_memory_extras). Its page's load
section starts with init and its ID, as a select's does.
"""
import sys

from nxwright.tft.component_types import (P_DRAWN_ENTRIES, PLACE_WORDS, TXT_MAXL_WORDS, TXT_WORDS,
                                   attribute_number, from_to, p_border_and_background_rules,
                                   place_fits_its_record, room_covered, text_fits,
                                   txt_maxl_covered, value_rule, with_p_background, with_p_border)
from nxwright.tft.component_types.select import items_fit
from nxwright.tft.instructions.undocumented_commands import init_block
from nxwright.tft.matching import Rule
from nxwright.tft.reasons import DOES_NOT_FIT

EVENTS = ("down", "up")
# Its entries on P, by number within the type: (name, place from its base,
# highest, lowest, code), its font's highest and its texts' codes set by
# component_types.p_table. 16 to 18 stay empty, where an effect's first and
# time go (component_types.with_p_effect), and so does 35.
P_ENTRIES = {
    **P_DRAWN_ENTRIES, 19: ("sta", 56, 3, 0, 0x121), 20: ("style", 57, 3, 0, 0x121),
    21: ("font", 61, 0, 0, 0x131), 22: ("bco", 62, 0xFFFF, 0, 0x232),
    23: ("pco", 64, 0xFFFF, 0, 0x232), 24: ("xcen", 66, 2, 0, 0x131),
    25: ("ycen", 67, 2, 0, 0x131), 26: ("spax", 68, 255, 0, 0x131),
    27: ("dis", 69, 100, 0, 0x131), 28: ("txt", 0, 0, 0, 0x3F),
    29: ("txt_maxl", 70, 0xFFFE, 0, 0x222), 30: ("up", 76, 1, 0, 0x131),
    31: ("pco3", 78, 0xFFFF, 0, 0x232), 32: ("bco1", 82, 0xFFFF, 0, 0x232),
    33: ("pco1", 84, 0xFFFF, 0, 0x232), 34: ("path", 0, 0, 0, 0x3F),
    36: ("dir", 92, 255, 0, 0x131), 37: ("qty", 93, 254, 1, 0x131),
    38: ("vvs0", 94, 255, 0, 0x131), 39: ("val", 95, 255, 0, 0x131),
    40: ("bco2", 96, 0xFFFF, 0, 0x232), 41: ("pco2", 98, 0xFFFF, 0, 0x232),
    42: ("hig", 100, 255, 16, 0x131), 43: ("down", 101, 1, 0, 0x131),
    44: ("mode", 102, 2, 0, 0x131), 45: ("wid", 103, 255, 8, 0x131),
    46: ("vvs1", 104, 255, 0, 0x131), 47: ("ch", 105, 32, 0, 0x131)}
# How many entries it has, the last ones empty.
ENTRIES = 57
# The top byte of the owner field of these attributes' entries
# (component_types.p_component_entries); every other entry gives 0 there.
P_OWNER_TOPS = {"dir": 0x01, "vvs1": 0x02, "qty": 0x03, "hig": 0x04, "path": 0x05,
                "down": 0x06, "vvs0": 0x07, "mode": 0x08, "wid": 0x09, "val": 0x80}
# The entry of each attribute it writes, by name.
_ENTRY_OF = {name: entry for entry, (name, *_) in P_ENTRIES.items()}
# Its memory on P, and its texts (P_TEXTS): where in its memory the place of
# each lies, which no entry gives, and its txt_maxl and its path_m. Its
# texts lie after its page's components' memory.
P_MEMORY_SIZE = 140
P_TEXTS = {72: ("txt", "txt_maxl", 70), 88: ("path", "path_m", 86)}
# The values of its memory on P that no entry gives, by attribute: where
# each lies, 1 byte. Its drastate lies after its ch.
P_UNENTERED = {"drastate": 106}


def load_start(page_object, project, place, places: dict) -> list:
    """Returns the blocks the combo-box adds to its page's load section,
    before the page's own load code: the command init with its ID, as
    `init 1`."""
    return [init_block(place.object_id)]


def p_memory_extras(page_object, project, place) -> dict:
    """Returns the bytes of the combo box's memory on P that no entry gives,
    beside its texts' (component_types.p_memory_extras): its drastate."""
    return {at: bytes([attribute_number(page_object, name)]) for name, at in P_UNENTERED.items()}


def attribute_place(name: str) -> int:
    """Returns the entry, within the type, of the attribute `name`, any the
    type writes (P_ENTRIES), which code names, as in `cb0.val`. Raises
    KeyError for another."""
    return _ENTRY_OF[name]


def variant(page_object):
    """Returns what describes the combo box `page_object`: its module, its
    entries as its style and its sta change them
    (component_types.with_p_border, with_p_background)."""
    return with_p_background(with_p_border(sys.modules[__name__], page_object), page_object)


# The series this module's probes matched (matching.py): P in p_probes.py,
# and E in e_probes.py. T and K have no combo-box.
SERIES = ("P", "E")

# What the combo-box has matched with probes (matching.py): a combo-box at
# its defaults, on P and E, but for these.
MATCHED = [
    Rule("type", "combo-box",
         "a combo-box, its attributes at their defaults but for those below"),
    Rule("attribute", "combo-box.objname", "any name nxwright's build takes"),
    *[Rule("attribute", "combo-box." + name,
           PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT)
      for name in ("x", "y", "w", "h")],
    # Its border and what lies behind it, as its probes on P and E showed.
    *[Rule("attribute", "combo-box." + name, words, covers, reason)
      for name, words, covers, reason in p_border_and_background_rules(3)],
    Rule("attribute", "combo-box.font", "any font of the project"),
    Rule("attribute", "combo-box.txt", TXT_WORDS, text_fits),
    Rule("attribute", "combo-box.txt_maxl", TXT_MAXL_WORDS, txt_maxl_covered, DOES_NOT_FIT),
    Rule("attribute", "combo-box.path", "items of any characters, the items between "
         "\"\\r\\n\", or none, no more than its path_m", items_fit),
    Rule("attribute", "combo-box.path_m", "from 0 to 65534, the most the Nextion Editor takes "
         "(\"Out of range\" past it), its path fitting it", room_covered("path", 0xFFFE, low=0)),
    Rule("attribute", "combo-box.dis", "any value, written as it is"),
    Rule("attribute", "combo-box.up", "any value, written as it is"),
    Rule("attribute", "combo-box.dir", "from 0 to 255, its entry's limits: 0, 1, 2, or 3, the "
         "ways its list opens, and past them as given", from_to(0, 255)),
    Rule("attribute", "combo-box.qty", "any value, written as it is"),
    Rule("attribute", "combo-box.val", "from 0 to 255", from_to(0, 255)),
    Rule("attribute", "combo-box.hig", "any value, written as it is"),
    Rule("attribute", "combo-box.down", "any value, written as it is"),
    Rule("attribute", "combo-box.mode", "0, 1, 2, or any other value that fits in its byte, "
         "written as it is"),
    Rule("attribute", "combo-box.wid", "any value, written as it is"),
    Rule("attribute", "combo-box.ch", "any value, written as it is"),
    Rule("attribute", "combo-box.drastate", "any value of its byte, written in its memory "
         "alone, as it has no entry", from_to(0, 255)),
    *[Rule("attribute", "combo-box." + name, "from 0 to 255", from_to(0, 255))
      for name in ("vvs0", "vvs1")],
] + [Rule("attribute", "combo-box." + name, *value_rule(name))
     for name in ("bco", "pco", "pco1", "pco2", "pco3", "bco1", "bco2", "xcen", "ycen", "spax")]
