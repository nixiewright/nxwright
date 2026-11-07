"""The switch component, a type the P and E series have and T and K have
not, as the Nextion Editor 1.68.2 writes it on P, where its values lie in
its memory as P_ENTRIES gives them (ResearchNotes/tft/switch-component.md).

On P, a switch, as every component, has no drawing blocks: the screen draws
it from its memory. Its memory starts with what its record's head holds,
then gives its dez and its val, 1 byte each, its bco, pco, bco2, pco2, and
pco1, 2 bytes each, its font and its dis, 1 byte each, its txt_maxl, 2
bytes, and the place of its txt, which lies after its page's components'
memory, as a text's does. Its txt's default is "False/True".
"""
from nxwright.tft.component_types import (P_DRAWN_ENTRIES, PLACE_WORDS, TXT_WORDS, TXT_MAXL_WORDS,
                                   place_fits_its_record, text_fits, txt_maxl_covered, value_rule)
from nxwright.tft.matching import Rule
from nxwright.tft.reasons import DOES_NOT_FIT

EVENTS = ("down", "up")
# Its entries on P, by number within the type: (name, place from its base,
# highest, lowest, code), its font's highest and its txt's code set by
# component_types.p_table. 16 to 18 stay empty, where an effect's first and
# time go (component_types.with_p_effect).
P_ENTRIES = {
    **P_DRAWN_ENTRIES, 19: ("dez", 56, 1, 0, 0x121), 20: ("val", 57, 1, 0, 0x131),
    21: ("bco", 58, 0xFFFF, 0, 0x232), 22: ("pco", 60, 0xFFFF, 0, 0x232),
    23: ("bco2", 62, 0xFFFF, 0, 0x232), 24: ("pco2", 64, 0xFFFF, 0, 0x232),
    25: ("pco1", 66, 0xFFFF, 0, 0x232), 26: ("font", 68, 0, 0, 0x131),
    27: ("dis", 69, 100, 0, 0x131), 28: ("txt", 0, 0, 0, 0x3F),
    29: ("txt_maxl", 70, 0xFFFE, 0, 0x222)}
# How many entries it has, the last ones empty.
ENTRIES = 38
# The entry of each attribute it writes, by name.
_ENTRY_OF = {name: entry for entry, (name, *_) in P_ENTRIES.items()}
# Its memory on P, and its txt (P_TEXTS): where in its memory the place of
# its txt lies, which no entry gives, and its txt_maxl. Its txt lies after
# its page's components' memory.
P_MEMORY_SIZE = 76
P_TEXTS = {72: ("txt", "txt_maxl", 70)}


def attribute_place(name: str) -> int:
    """Returns the entry, within the type, of the attribute `name`, any the
    type writes (P_ENTRIES), which code names, as in `sw0.val`. Raises
    KeyError for another."""
    return _ENTRY_OF[name]


# The series this module's probes matched (matching.py): P in p_probes.py,
# and E in e_probes.py. T and K have no switch.
SERIES = ("P", "E")

# What the switch has matched with probes (matching.py): a switch at its
# defaults, on P and E, but for these.
MATCHED = [
    Rule("type", "switch", "a switch, its attributes at their defaults but for those below"),
    Rule("attribute", "switch.objname", "any name nxwright's build takes"),
    Rule("attribute", "switch.x", PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT),
    Rule("attribute", "switch.y", PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT),
    Rule("attribute", "switch.w", PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT),
    Rule("attribute", "switch.h", PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT),
    Rule("attribute", "switch.txt", TXT_WORDS, text_fits),
    Rule("attribute", "switch.txt_maxl", TXT_MAXL_WORDS, txt_maxl_covered, DOES_NOT_FIT),
    Rule("attribute", "switch.font", "any font of the project"),
    Rule("attribute", "switch.val", "any value, written as it is"),
    Rule("attribute", "switch.dez", "any value, written as it is"),
    Rule("attribute", "switch.dis", "any value, written as it is"),
] + [Rule("attribute", "switch." + name, *value_rule(name))
     for name in ("bco", "pco", "bco2", "pco2", "pco1")]
