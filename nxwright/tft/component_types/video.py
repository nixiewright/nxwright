"""The video component, a type the P and E series have and T and K have
not, as the Nextion Editor 1.68.2 writes it on P, where its values lie in
its memory as P_ENTRIES gives them (ResearchNotes/tft/video-component.md).

As nxwright's descriptions of its attributes give it, a video plays one of
the project's videos, its vid, when its from is 0, or a file on the screen,
its path, when its from is 1.

On P, a video, as every component, has no drawing blocks: the screen draws
it from its memory. Its memory starts with what its record's head holds.
Then it gives its vid, en, loop, fps, dis, tim, stim, qty, and from, and,
from a file, its path_m and where its path lies. Last come the size of its
buffer, 64000 bytes whatever its molloc and molloc_s, and where that buffer
lies, at the end of its page's memory, after the texts, as for a file stream
(file_stream.py). Its page's load section starts with init and its ID, as a
select's does.

Code cannot change its from, so each video is written by the variant of its
from (variant), as an audio is. From a file, its path has an entry in vid's
place, an empty entry follows it, and each later entry is numbered one
more. Its path lies after its page's components' memory, in a room of its
path_m + 1 bytes. From the project, its path is written nowhere.

Its vid names one of the project's videos, by its ID, or none at 65535,
its default. Its vid's entry gives the project's last video as its
highest, as a gmov's gives the last animation (P_LAST_RESOURCE).
"""
from functools import lru_cache
import struct

from nxwright.tft.component_types import (P_DRAWN_ENTRIES, PLACE_WORDS, attribute_number, from_to,
                                   place_fits_its_record)
from nxwright.tft.component_types.external_picture import path_fits
from nxwright.tft.component_types.gmov import vid_covered
from nxwright.tft.instructions.undocumented_commands import init_block
from nxwright.tft.matching import Rule
from nxwright.tft.reasons import DOES_NOT_FIT, INVALID_VALUE

EVENTS = ("down", "up", "playend")
# The highest value of an entry of 4 bytes.
_LARGEST = 0x7FFFFFFF
# Its entries on P from the project, by number within the type: (name, place
# from its base, highest, lowest, code), its vid's highest set by
# component_types.p_table (P_LAST_RESOURCE). 16 to 18 stay empty, where an
# effect's first and time go (component_types.with_p_effect).
P_ENTRIES = {
    **P_DRAWN_ENTRIES, 19: ("from", 80, 1, 0, 0x121), 20: ("vid", 56, 0, 0, 0x232),
    21: ("en", 58, 2, 0, 0x131), 22: ("loop", 59, 1, 0, 0x131), 23: ("fps", 60, 50, 0, 0x121),
    24: ("dis", 62, 1000, 10, 0x232), 25: ("tim", 64, _LARGEST, -_LARGEST - 1, 0x439),
    26: ("stim", 68, _LARGEST, -_LARGEST - 1, 0x429),
    27: ("qty", 76, _LARGEST, -_LARGEST - 1, 0x429)}
# How many entries it has from the project, the last ones empty.
ENTRIES = 38
# The entry of vid, which a path's takes from a file.
_VID = 20
# The top byte of the owner field of these attributes' entries
# (component_types.p_component_entries); every other entry gives 0 there.
_OWNER_TOPS = {"vid": 0x01, "path": 0x80, "en": 0x02, "tim": 0x04, "dis": 0x05}
# Its vid's highest: the project's last video (component_types.p_table).
P_LAST_RESOURCE = {"vid": "video"}
# Its memory on P.
P_MEMORY_SIZE = 104
# From a file, its path (P_TEXTS): where in its memory the place of its path
# lies, which no entry gives, and its path_m, which none gives either.
_PATH_TEXTS = {84: ("path", "path_m", 82)}
# Its buffer: its size, the same whatever its molloc and molloc_s, and
# where in its memory that size and its place lie.
_BUFFER_SIZE = 64000
_BUFFER_SIZE_AT, _BUFFER_PLACE_AT = 88, 92


class _Video:
    """A video from the project or from a file (`from_a_file`), with the
    members a type's module gives (component_types/__init__.py) but
    MATCHED."""
    EVENTS = EVENTS
    # On P, the frame reads these of the variant.
    P_MEMORY_SIZE, P_OWNER_TOPS = P_MEMORY_SIZE, _OWNER_TOPS
    P_LAST_RESOURCE = P_LAST_RESOURCE

    def __init__(self, from_a_file: bool):
        if from_a_file:
            self.P_ENTRIES = {entry + (entry > _VID): value
                              for entry, value in P_ENTRIES.items() if entry != _VID}
            self.P_ENTRIES[_VID] = ("path", 0, 0, 0, 0x3F)
            self.ENTRIES, self.P_TEXTS = ENTRIES + 1, _PATH_TEXTS
        else:
            self.P_ENTRIES, self.ENTRIES, self.P_TEXTS = P_ENTRIES, ENTRIES, {}
        self._entry_of = {name: entry for entry, (name, *_) in self.P_ENTRIES.items()}

    @staticmethod
    def buffer_size(page_object, project) -> int:
        """Returns the size of the video's buffer, at the end of its page's
        memory."""
        return _BUFFER_SIZE

    @staticmethod
    def p_memory_extras(page_object, project, place) -> dict:
        """Returns the bytes of the video's memory on P that no entry gives:
        its buffer's size, and where its buffer lies, place.buffer_place."""
        return {_BUFFER_SIZE_AT: struct.pack("<I", _BUFFER_SIZE),
                _BUFFER_PLACE_AT: struct.pack("<I", place.buffer_place)}

    @staticmethod
    def load_start(page_object, project, place, places: dict) -> list:
        """Returns the block the video adds to its page's load section:
        `init`, then its ID as text."""
        return [init_block(place.object_id)]

    def attribute_place(self, name: str) -> int:
        """Returns the entry, within the type, of the attribute `name`, any
        the variant writes (P_ENTRIES), which code names, as in `vd0.en`.
        Raises KeyError for another, such as path from the project."""
        return self._entry_of[name]


@lru_cache(maxsize=None)
def _of(from_a_file: bool) -> _Video:
    """Returns the variant of a video from the project or from a file, made
    once."""
    return _Video(from_a_file)


def variant(page_object) -> _Video:
    """Returns what describes the video `page_object`: the variant of its
    from, from the project at 0, its default, and from a file at 1."""
    return _of(attribute_number(page_object, "from") == 1)


# The series this module's probes matched (matching.py): P in p_probes.py,
# and E in e_probes.py. T and K have no video.
SERIES = ("P", "E")

# What the video has matched with probes (matching.py): a video at its
# defaults, on P and E, but for these.
MATCHED = [
    Rule("type", "video", "a video, its attributes at their defaults but for those below"),
    Rule("attribute", "video.objname", "any name nxwright's build takes"),
    *[Rule("attribute", "video." + name, PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT)
      for name in ("x", "y", "w", "h")],
    Rule("attribute", "video.from", "0, from the project, or 1, from a file", from_to(0, 1),
         INVALID_VALUE),
    Rule("attribute", "video.vid", "any value from 0 to 65535, written as it is from the "
         "project: one of the project's videos, or another; from a file, not written",
         vid_covered),
    # From the project, its path and path_m are written nowhere, but the
    # probes tried them only as from a file.
    Rule("attribute", "video.path", "any characters, no more than its path_m", path_fits),
    Rule("attribute", "video.path_m", "from 0 to 65534, the most the Nextion Editor takes "
         "(\"Out of range\" past it, from a file)", from_to(0, 0xFFFE)),
    Rule("attribute", "video.en", "0, 1, 2, or any other value that fits in its byte, written as "
         "it is"),
    Rule("attribute", "video.loop", "0, 1, or any other value that fits in its byte, written as "
         "it is"),
    Rule("attribute", "video.fps", "any value, written as it is"),
    Rule("attribute", "video.dis", "any value, written as it is"),
    *[Rule("attribute", "video." + name, "from -2147483648 to 2147483647, its entry's limits",
           from_to(-_LARGEST - 1, _LARGEST)) for name in ("tim", "stim", "qty")],
    Rule("attribute", "video.molloc", "any value, which changes nothing in the file"),
    Rule("attribute", "video.molloc_s", "any value, which changes nothing in the file"),
]
