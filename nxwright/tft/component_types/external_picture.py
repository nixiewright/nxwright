"""The external picture component, a type the P and E series have and T
and K have not, as the Nextion Editor 1.68.2 writes it on P, where its
values lie in its memory as P_ENTRIES gives them
(ResearchNotes/tft/external-picture-component.md).

On P, an external picture, as every component, has no drawing blocks: the
screen draws it from its memory. Its memory starts with what its record's
head holds. At 58 it gives its path_m, 2 bytes, and at 60 the place of its
path, which lies after its page's components' memory, as a text's txt
does. Its path names the picture's file, as "sd0/a.jpg"; its path_m is its
room, 255 at its default.
"""
from nxwright.tft.component_types import (P_DRAWN_ENTRIES, PLACE_WORDS, from_to, place_fits_its_record,
                                   text_in_room)
from nxwright.tft.matching import Rule
from nxwright.tft.reasons import DOES_NOT_FIT

EVENTS = ("down", "up")
# Its entries on P, by number within the type: (name, place from its base,
# highest, lowest, code), its path's code set by component_types.p_table.
# 16 to 18 stay empty, where an effect's first and time go
# (component_types.with_p_effect).
P_ENTRIES = {**P_DRAWN_ENTRIES, 19: ("path", 0, 0, 0, 0x3F)}
# How many entries it has, the last ones empty.
ENTRIES = 29
# The entry of each attribute it writes, by name.
_ENTRY_OF = {name: entry for entry, (name, *_) in P_ENTRIES.items()}
# Its memory on P, and its path (P_TEXTS): where in its memory the place of
# its path lies, which no entry gives, and its path_m, which none gives
# either. Its path lies after its page's components' memory.
P_MEMORY_SIZE = 64
P_TEXTS = {60: ("path", "path_m", 58)}
# The check of a path, its own and a gmov's, a video's, and an audio's
# (gmov.py, video.py, audio.py): a path is written as its bytes, whatever
# its characters, so it holds no more bytes than its path_m.
path_fits = text_in_room("path_m")


def attribute_place(name: str) -> int:
    """Returns the entry, within the type, of the attribute `name`, any the
    type writes (P_ENTRIES), which code names, as in `xp0.path`. Raises
    KeyError for another."""
    return _ENTRY_OF[name]


# The series this module's probes matched (matching.py): P in p_probes.py,
# and E in e_probes.py. T and K have no external picture.
SERIES = ("P", "E")

# What the external picture has matched with probes (matching.py): one at
# its defaults, on P and E, but for these.
MATCHED = [
    Rule("type", "external-picture",
         "an external picture, its attributes at their defaults but for those below"),
    Rule("attribute", "external-picture.objname", "any name nxwright's build takes"),
    *[Rule("attribute", "external-picture." + name,
           PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT)
      for name in ("x", "y", "w", "h")],
    Rule("attribute", "external-picture.path", "any characters, no more than its path_m",
         path_fits),
    Rule("attribute", "external-picture.path_m", "from 0 to 65534, the most the Nextion Editor "
         "takes (\"Out of range\" past it)", from_to(0, 0xFFFE)),
]
