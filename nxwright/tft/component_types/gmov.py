"""The gmov component, which plays an animation, a type the P and E series
have and T and K have not, as the Nextion Editor 1.68.2 writes it on P,
where its values lie in its memory as P_ENTRIES gives them
(ResearchNotes/tft/gmov-component.md).

On P, a gmov, as every component, has no drawing blocks: the screen draws
it from its memory. Its memory starts with what its record's head holds.
Then it gives its vid, en, loop, dis, tim, stim, qty, and from, its path_m
at 82 and the place of its path at 84, then the size of its buffer at 88
and where that buffer lies at 92. Its path lies after its page's
components' memory, as a text's txt does. Its buffer, 12000 bytes whatever
its molloc and molloc_s, lies at the end of its page's memory, after the
texts, as a file stream's does (file_stream.py). Its page's load section
starts with init and its ID, as a select's does.

Its from sets where it plays from. At a from of 1, it has no vid entry, so
each later entry is numbered one less, and its memory gives 0 for its vid.
So each gmov is written by the variant of its from (variant).

Its vid names one of the project's animations, by its ID, or none at
65535, its default. Its vid's entry gives the project's last animation as
its highest, as a font's gives the last font (P_LAST_RESOURCE).
"""
from functools import lru_cache
import struct

from nxwright.project.attribute_values import number_from_bytes

from nxwright.tft.component_types import (P_DRAWN_ENTRIES, PLACE_WORDS, attribute_number, from_to,
                                   place_fits_its_record, room_covered)
from nxwright.tft.component_types.external_picture import path_fits
from nxwright.tft.instructions.undocumented_commands import init_block
from nxwright.tft.matching import Rule
from nxwright.tft.reasons import DOES_NOT_FIT, INVALID_VALUE

EVENTS = ("down", "up", "playend")
# The highest value of an entry of 4 bytes.
_LARGEST = 0x7FFFFFFF
# Its entries on P at a from of 0, by number within the type: (name, place
# from its base, highest, lowest, code), its path's code set by
# component_types.p_table. 16 to 18 stay empty, where an effect's first and
# time go (component_types.with_p_effect), and so does 22. Its vid's highest
# is set by p_table too (P_LAST_RESOURCE).
P_ENTRIES = {
    **P_DRAWN_ENTRIES, 19: ("from", 80, 1, 0, 0x121), 20: ("vid", 56, 0, 0, 0x232),
    21: ("path", 0, 0, 0, 0x3F), 23: ("en", 58, 2, 0, 0x131), 24: ("loop", 59, 1, 0, 0x131),
    25: ("dis", 62, 1000, 10, 0x232), 26: ("tim", 64, _LARGEST, -_LARGEST - 1, 0x439),
    27: ("stim", 68, _LARGEST, -_LARGEST - 1, 0x429),
    28: ("qty", 76, _LARGEST, -_LARGEST - 1, 0x429)}
# How many entries it has at a from of 0, the last ones empty.
ENTRIES = 39
# The entry of its vid.
_VID = 20
# The top byte of the owner field of these attributes' entries
# (component_types.p_component_entries); every other entry gives 0 there.
P_OWNER_TOPS = {"vid": 0x01, "en": 0x02, "tim": 0x04, "dis": 0x05}
# Its vid's highest: the project's last animation (component_types.p_table).
P_LAST_RESOURCE = {"vid": "animation"}
# Its memory on P, and its path (P_TEXTS): where in its memory the place of
# its path lies, which no entry gives, and its path_m, which none gives
# either. Its path lies after its page's components' memory.
P_MEMORY_SIZE = 104
P_TEXTS = {84: ("path", "path_m", 82)}
# Its buffer: its size, the same whatever its molloc and molloc_s, and
# where in its memory that size and its place lie.
_BUFFER_SIZE = 12000
_BUFFER_SIZE_AT, _BUFFER_PLACE_AT = 88, 92


class _Gmov:
    """A gmov with its vid or without (`vid`), at a from of 0 or 1, with
    the members a type's module gives (component_types/__init__.py) but
    MATCHED."""
    EVENTS = EVENTS
    # On P, the frame reads these of the variant. Without its vid, its
    # vid's top byte has no entry to go to (p_component_entries).
    P_MEMORY_SIZE, P_TEXTS, P_OWNER_TOPS = P_MEMORY_SIZE, P_TEXTS, P_OWNER_TOPS
    P_LAST_RESOURCE = P_LAST_RESOURCE

    def __init__(self, vid: bool):
        if vid:
            self.P_ENTRIES, self.ENTRIES = P_ENTRIES, ENTRIES
        else:
            self.P_ENTRIES = {entry - (entry > _VID): value
                              for entry, value in P_ENTRIES.items() if entry != _VID}
            self.ENTRIES = ENTRIES - 1
        self._entry_of = {name: entry for entry, (name, *_) in self.P_ENTRIES.items()}

    @staticmethod
    def buffer_size(page_object, project) -> int:
        """Returns the size of the gmov's buffer, at the end of its page's
        memory."""
        return _BUFFER_SIZE

    @staticmethod
    def p_memory_extras(page_object, project, place) -> dict:
        """Returns the bytes of the gmov's memory on P that no entry gives:
        its buffer's size, and where its buffer lies, place.buffer_place."""
        return {_BUFFER_SIZE_AT: struct.pack("<I", _BUFFER_SIZE),
                _BUFFER_PLACE_AT: struct.pack("<I", place.buffer_place)}

    @staticmethod
    def load_start(page_object, project, place, places: dict) -> list:
        """Returns the blocks the gmov adds to its page's load section,
        before the page's own load code: the command init with its ID, as
        `init 1`."""
        return [init_block(place.object_id)]

    def attribute_place(self, name: str) -> int:
        """Returns the entry, within the type, of the attribute `name`, any
        the variant writes (P_ENTRIES), which code names, as in `gm0.tim`.
        Raises KeyError for another, such as vid at a from of 1."""
        return self._entry_of[name]


@lru_cache(maxsize=None)
def _of(vid: bool) -> _Gmov:
    """Returns the variant of a gmov with its vid or without, made once."""
    return _Gmov(vid)


def variant(page_object) -> _Gmov:
    """Returns what describes the gmov `page_object`: the variant of its
    from, with its vid at a from of 0, its default, and without at 1."""
    return _of(attribute_number(page_object, "from") == 0)


def vid_covered(need) -> bool:
    """Whether the vid of the attribute `need`, of a gmov, a video, or an
    audio (video.py, audio.py), is from 0 to 65535. At a from of 0, the
    Nextion Editor writes any such vid as it is, one past its project's last
    animation among them. At a from of 1, it writes none: no entry, and 0
    in memory."""
    return 0 <= number_from_bytes(need.value) <= 0xFFFF


# The series this module's probes matched (matching.py): P in p_probes.py,
# and E in e_probes.py. T and K have no gmov.
SERIES = ("P", "E")

# What the gmov has matched with probes (matching.py): a gmov at its
# defaults, on P and E, but for these.
MATCHED = [
    Rule("type", "gmov", "a gmov, its attributes at their defaults but for those below"),
    Rule("attribute", "gmov.objname", "any name nxwright's build takes"),
    *[Rule("attribute", "gmov." + name, PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT)
      for name in ("x", "y", "w", "h")],
    Rule("attribute", "gmov.from", "0, or 1, without its vid", from_to(0, 1), INVALID_VALUE),
    Rule("attribute", "gmov.vid", "any value from 0 to 65535, written as it is at a from of "
         "0: one of the project's animations, or another; at a from of 1, not written",
         vid_covered),
    Rule("attribute", "gmov.en", "0, 1, 2, or any other value that fits in its byte, written as "
         "it is"),
    Rule("attribute", "gmov.loop", "0, 1, or any other value that fits in its byte, written as "
         "it is"),
    Rule("attribute", "gmov.dis", "any value, written as it is"),
    *[Rule("attribute", "gmov." + name, "from -2147483648 to 2147483647, its entry's limits",
           from_to(-_LARGEST - 1, _LARGEST)) for name in ("tim", "stim", "qty")],
    Rule("attribute", "gmov.path", "any characters, no more than its path_m, at a from of "
         "0 or 1", path_fits),
    Rule("attribute", "gmov.path_m", "from 0 to 65534, the most the Nextion Editor takes "
         "(\"Out of range\" past it), its path fitting it", room_covered("path", 0xFFFE, low=0)),
    Rule("attribute", "gmov.molloc", "any value, which changes nothing in the file"),
    Rule("attribute", "gmov.molloc_s", "any value, which changes nothing in the file"),
]
