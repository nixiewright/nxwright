"""The select component, a type the P and E series have and T and K have
not, as the Nextion Editor 1.68.2 writes it on P, where its values lie in
its memory as P_ENTRIES gives them (ResearchNotes/tft/select-component.md).

On P, a select, as every component, has no drawing blocks: the screen draws
it from its memory. Its memory starts with what its record's head holds.
Then it gives its values, with its txt_maxl at 74 and the place of its txt
at 76, and its path_m at 86 and the place of its path at 88. Both its txt
and its path lie after its page's components' memory, in that order, as a
text's txt does. Its path gives its items, one a line, each line ending in
"\\r\\n" but the last.

Its dis sets whether a line, of its pco1, marks the item chosen. At a dis
of 0, without the line, it has no pco1 entry, so each later entry is
numbered one less, and its memory gives 0 for its pco1. So each select is
written by the variant of its dis (variant).
"""
from functools import lru_cache

from nxwright.tft.component_types import (P_DRAWN_ENTRIES, PLACE_WORDS, TXT_MAXL_WORDS, TXT_WORDS,
                                   attribute_number, from_to, p_border_and_background_rules,
                                   place_fits_its_record, room_covered, text_fits, text_in_room,
                                   txt_maxl_covered, value_rule, with_p_background,
                                   with_p_border)
from nxwright.tft.instructions.undocumented_commands import init_block
from nxwright.tft.matching import Rule
from nxwright.tft.reasons import DOES_NOT_FIT, INVALID_VALUE

EVENTS = ("down", "up")
# Its entries on P with its line, by number within the type: (name, place
# from its base, highest, lowest, code), its font's highest and its texts'
# codes set by component_types.p_table. 16 to 18 stay empty, where an
# effect's first and time go (component_types.with_p_effect), and so does
# 30.
P_ENTRIES = {
    **P_DRAWN_ENTRIES, 19: ("sta", 56, 3, 0, 0x121), 20: ("style", 57, 1, 0, 0x121),
    21: ("font", 61, 0, 0, 0x131), 22: ("bco", 62, 0xFFFF, 0, 0x232),
    23: ("pco", 64, 0xFFFF, 0, 0x232), 24: ("pco2", 66, 0xFFFF, 0, 0x232),
    25: ("spax", 68, 255, 0, 0x131), 26: ("hig", 69, 255, 16, 0x131),
    27: ("dis", 70, 1, 0, 0x131), 28: ("pco1", 72, 0xFFFF, 0, 0x232),
    29: ("txt", 0, 0, 0, 0x2F), 31: ("val", 80, 0xFFFF, 0, 0x439),
    32: ("ch", 84, 32, 0, 0x131), 33: ("path", 0, 0, 0, 0x3F)}
# How many entries it has with its line, the last ones empty.
ENTRIES = 43
# The entry of its line's colour.
_LINE = 28
# The top byte of the owner field of its val's entry
# (component_types.p_component_entries).
P_OWNER_TOPS = {"val": 0x80}
# Its memory on P, and its texts (P_TEXTS): where in its memory the place of
# each lies, which no entry gives, and its txt_maxl and its path_m, which
# none gives either. Its texts lie after its page's components' memory.
P_MEMORY_SIZE = 108
P_TEXTS = {76: ("txt", "txt_maxl", 74), 88: ("path", "path_m", 86)}
# The check of a path, of a select or of a combo-box (combo_box.py): its
# items, between "\r\n", are written as its bytes, whatever their
# characters, so it holds no more bytes than its path_m.
items_fit = text_in_room("path_m")
# The most path_m a select takes: the Nextion Editor refuses 8193 ("Out of
# range"), where a combo box takes up to 65534.
_MOST_PATH_M = 8192


class _Select:
    """A select with its line or without (`line`), with the members a type's
    module gives (component_types/__init__.py) but MATCHED."""
    EVENTS = EVENTS
    # On P, the frame reads these of the variant.
    P_MEMORY_SIZE, P_TEXTS, P_OWNER_TOPS = P_MEMORY_SIZE, P_TEXTS, P_OWNER_TOPS

    def __init__(self, line: bool):
        if line:
            self.P_ENTRIES, self.ENTRIES = P_ENTRIES, ENTRIES
        else:
            self.P_ENTRIES = {entry - (entry > _LINE): value
                              for entry, value in P_ENTRIES.items() if entry != _LINE}
            self.ENTRIES = ENTRIES - 1
        self._entry_of = {name: entry for entry, (name, *_) in self.P_ENTRIES.items()}

    @staticmethod
    def load_start(page_object, project, place, places: dict) -> list:
        """Returns the blocks the select adds to its page's load section,
        before the page's own load code: the command init with its ID, as
        `init 1`."""
        return [init_block(place.object_id)]

    def attribute_place(self, name: str) -> int:
        """Returns the entry, within the type, of the attribute `name`, any
        the variant writes (P_ENTRIES), which code names, as in
        `select0.val`. Raises KeyError for another, such as pco1 without
        its line."""
        return self._entry_of[name]


@lru_cache(maxsize=None)
def _of(line: bool) -> _Select:
    """Returns the variant of a select with its line or without, made
    once."""
    return _Select(line)


def variant(page_object):
    """Returns what describes the select `page_object`: the variant of its
    dis, with its line at a dis of 1, its default, and without at 0, its
    entries as its style and its sta change them (component_types.with_p_border,
    with_p_background)."""
    described = with_p_border(_of(attribute_number(page_object, "dis") != 0), page_object)
    return with_p_background(described, page_object)


# The series this module's probes matched (matching.py): P in p_probes.py,
# and E in e_probes.py. T and K have no select.
SERIES = ("P", "E")

# What the select has matched with probes (matching.py): a select at its
# defaults, on P and E, but for these.
MATCHED = [
    Rule("type", "select", "a select, its attributes at their defaults but for those below"),
    Rule("attribute", "select.objname", "any name nxwright's build takes"),
    *[Rule("attribute", "select." + name,
           PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT)
      for name in ("x", "y", "w", "h")],
    # Its border and what lies behind it, as its probes on P and E showed.
    *[Rule("attribute", "select." + name, words, covers, reason)
      for name, words, covers, reason in p_border_and_background_rules(1)],
    Rule("attribute", "select.font", "any font of the project"),
    Rule("attribute", "select.path", "items of any characters, the items between "
         "\"\\r\\n\", or none, no more than its path_m", items_fit),
    Rule("attribute", "select.path_m", "from 0 to 8192, the most the Nextion Editor takes, its "
         "path fitting it", room_covered("path", _MOST_PATH_M, low=0)),
    # Its txt is written as it is, not as the item its val chooses.
    Rule("attribute", "select.txt", TXT_WORDS, text_fits),
    Rule("attribute", "select.txt_maxl", TXT_MAXL_WORDS, txt_maxl_covered, DOES_NOT_FIT),
    Rule("attribute", "select.val", "any value, written as it is"),
    Rule("attribute", "select.spax", "from 0 to 255", from_to(0, 255)),
    Rule("attribute", "select.hig", "any value, written as it is"),
    # The compile writes one form for a dis of 0 and another for 1. The
    # build refuses any other value.
    Rule("attribute", "select.dis", "0, without the line that marks the item chosen, or 1",
         from_to(0, 1), INVALID_VALUE),
    Rule("attribute", "select.ch", "any value, written as it is"),
] + [Rule("attribute", "select." + name, *value_rule(name))
     for name in ("bco", "pco", "pco2", "pco1")]
