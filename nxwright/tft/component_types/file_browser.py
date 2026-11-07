"""The file browser component, a type the P and E series have and T and K
have not, as the Nextion Editor 1.68.2 writes it on P, where its values lie
in its memory as P_ENTRIES gives them
(ResearchNotes/tft/file-browser-component.md).

As nxwright's descriptions of its attributes give it, a file browser lists
the files of a folder of the screen's SD card, its dir, that its filter
takes, and gives the one chosen as its txt.

On P, a file browser has no drawing blocks: the screen draws it from its
memory. Its memory, 160 bytes, starts with what its record's head holds.
Then it gives its values, its autoleft, which no entry gives, each of its
four texts' room and place, its dir, filter, txt, and vvs2, then its
buffsize and where its buffer lies. Its texts lie after its page's
components' memory, in that order, and its buffer, its buffsize rounded up
to 4, at the end of its page's memory. Its buff and its fwarning change
nothing in the file.

At a psta of 0, without folders listed, its pic1, a folder's icon, has no
entry, each later entry one less; and a style of 1, a border of one colour,
gives its borderc and borderw entries after its style's, each later entry
two on. So each file browser is written by the variant of its psta and its
style (variant). Its pic1's and pic2's entries give the project's last
picture as their highest (P_LAST_RESOURCE).
"""
from functools import lru_cache
import struct

from nxwright.tft.component_types import (P_DRAWN_ENTRIES, PLACE_WORDS, attribute_number, from_to,
                                   p_border_and_background_rules, place_fits_its_record,
                                   room_covered, text_in_room, value_rule, with_p_background)
from nxwright.tft.instructions.undocumented_commands import init_block
from nxwright.tft.matching import Rule
from nxwright.tft.reasons import DOES_NOT_FIT, INVALID_VALUE
from nxwright.tft.statements import method_call_covered

EVENTS = ("down", "up")
# The highest value of an entry of 4 bytes.
_LARGEST = 0x7FFFFFFF
# Its entries on P, by number within the type: (name, place from its base,
# highest, lowest, code), its font's highest and its texts' codes set by
# component_types.p_table. 16 to 18 stay empty, where an effect's first and
# time go (component_types.with_p_effect), and so do 27, 31, 33, 36, 47, and
# 49. pic1's and pic2's highest is the project's last picture, set by
# component_types.p_table (P_LAST_RESOURCE).
P_ENTRIES = {
    **P_DRAWN_ENTRIES, 19: ("sta", 56, 3, 0, 0x121), 20: ("style", 57, 3, 0, 0x121),
    21: ("font", 61, 0, 0, 0x131), 22: ("bco", 62, 0xFFFF, 0, 0x232),
    23: ("pco", 64, 0xFFFF, 0, 0x232), 24: ("pco2", 66, 0xFFFF, 0, 0x232),
    25: ("bco2", 68, 0xFFFF, 0, 0x232), 26: ("xcen", 70, 2, 0, 0x131),
    28: ("left", 72, 2, 0, 0x131), 29: ("ch", 73, 32, 0, 0x131), 30: ("dir", 0, 0, 0, 0x3F),
    32: ("filter", 0, 0, 0, 0x3F), 34: ("val", 88, _LARGEST, -_LARGEST - 1, 0x439),
    35: ("txt", 0, 0, 0, 0x2F), 37: ("qty", 100, _LARGEST, 0, 0x429),
    38: ("dis", 104, 255, 0, 0x131), 39: ("spax", 106, 255, 0, 0x131),
    40: ("spay", 107, 255, 0, 0x131), 41: ("maxval_y", 108, _LARGEST, -_LARGEST - 1, 0x429),
    42: ("val_y", 112, _LARGEST, -_LARGEST - 1, 0x439), 43: ("psta", 117, 1, 0, 0x121),
    44: ("pic1", 118, 0, 0, 0x232), 45: ("pic2", 120, 0, 0, 0x232),
    46: ("vvs2", 0, 0, 0, 0x3F), 48: ("buffsize", 128, _LARGEST, 0, 0x429),
    50: ("up", 136, _LARGEST, -_LARGEST - 1, 0x439)}
# How many entries it has, with folders listed and without a border of one
# colour, the last ones empty.
ENTRIES = 60
# With folders listed, its psta 1, its default, its pic1, a folder's icon,
# has an entry; at 0 it has none, and each later entry is one less.
_PIC1 = 44
# Its style of a border of one colour, which gives its borderc's and
# borderw's entries after its style's, each later entry two on.
_BORDERED = 1
_STYLE = 20
_BORDER_ENTRIES = {21: ("borderc", 58, 0xFFFF, 0, 0x232), 22: ("borderw", 60, 255, 0, 0x131)}
# The top byte of the owner field of these attributes' entries
# (component_types.p_component_entries); every other entry gives 0 there.
P_OWNER_TOPS = {"dir": 0x01, "val": 0x02, "dis": 0x03, "spax": 0x04, "spay": 0x05,
                "filter": 0x06, "vvs2": 0x06, "pic1": 0x07, "pic2": 0x07, "up": 0x9C}
# Its pictures' highest: the project's last picture (component_types.p_table).
P_LAST_RESOURCE = {"pic1": "picture", "pic2": "picture"}
# Its memory on P, and its texts (P_TEXTS): where in its memory the place of
# each lies, which no entry gives, and the attribute that gives its room,
# which none gives either, in the order they lie.
P_MEMORY_SIZE = 160
P_TEXTS = {76: ("dir", "dir_m", 74), 84: ("filter", "filter_m", 82),
           96: ("txt", "txt_m", 94), 124: ("vvs2", "vvs2_m", 122)}
# The values of its memory on P that no entry gives, by attribute: where
# each lies, 1 byte. Where its buffer lies, after its buffsize, which no
# entry gives either.
P_UNENTERED = {"autoleft": 71}
_BUFFER_PLACE_AT = 132


class _FileBrowser:
    """A file browser with folders listed or not (`folders`), and with a
    border of one colour or not (`bordered`), with the members a type's
    module gives (component_types/__init__.py) but MATCHED."""
    EVENTS = EVENTS
    # On P, the frame reads these of the variant.
    P_MEMORY_SIZE, P_TEXTS, P_OWNER_TOPS = P_MEMORY_SIZE, P_TEXTS, P_OWNER_TOPS
    P_LAST_RESOURCE = P_LAST_RESOURCE

    def __init__(self, folders: bool, bordered: bool):
        entries, self.ENTRIES = dict(P_ENTRIES), ENTRIES
        if not folders:
            entries = {entry - (entry > _PIC1): value
                       for entry, value in entries.items() if entry != _PIC1}
            self.ENTRIES -= 1
        if bordered:
            entries = {entry + 2 * (entry > _STYLE): value for entry, value in entries.items()}
            entries.update(_BORDER_ENTRIES)
            self.ENTRIES += 2
        self.P_ENTRIES = entries
        self._entry_of = {name: entry for entry, (name, *_) in entries.items()}

    def attribute_place(self, name: str) -> int:
        """Returns the entry, within the type, of the attribute `name`, any
        the variant writes (P_ENTRIES), its up among them, which code names,
        as in `fbrowser0.val`. Raises KeyError for another, such as pic1
        without folders listed."""
        return self._entry_of[name]

    @staticmethod
    def load_start(page_object, project, place, places: dict) -> list:
        """Returns the block the file browser adds to its page's load
        section, before the page's own load code: `init`, then its ID as
        text."""
        return [init_block(place.object_id)]

    @staticmethod
    def buffer_size(page_object, project) -> int:
        """Returns the size of the file browser's buffer, at the end of its
        page's memory: its buffsize, rounded up to a multiple of 4."""
        size = attribute_number(page_object, "buffsize")
        return size + -size % 4

    @staticmethod
    def p_memory_extras(page_object, project, place) -> dict:
        """Returns the bytes of the file browser's memory on P that no entry
        gives: its autoleft, and where its buffer lies, place.buffer_place.
        At a buffsize of 0 it has no buffer, and the place is 0."""
        buffer_place = place.buffer_place if attribute_number(page_object, "buffsize") else 0
        extras = {at: bytes([attribute_number(page_object, name)])
                  for name, at in P_UNENTERED.items()}
        extras[_BUFFER_PLACE_AT] = struct.pack("<I", buffer_place)
        return extras


@lru_cache(maxsize=None)
def _of(folders: bool, bordered: bool) -> _FileBrowser:
    """Returns the variant of a file browser with folders listed or not and
    with a border of one colour or not, made once."""
    return _FileBrowser(folders, bordered)


def variant(page_object):
    """Returns what describes the file browser `page_object`: the variant of
    its psta, folders listed at 1, its default, and of its style, a border
    of one colour at 1, its entries as its sta changes them
    (component_types.with_p_background)."""
    return with_p_background(_of(attribute_number(page_object, "psta") == 1,
                                 attribute_number(page_object, "style") == _BORDERED),
                             page_object)


# Each of its texts, and the attribute that gives its room. Each is written
# as its bytes, whatever its characters (component_types.text_in_room).
_TEXTS = (("dir", "dir_m"), ("filter", "filter_m"), ("txt", "txt_m"), ("vvs2", "vvs2_m"))


# The series this module's probes matched (matching.py): P in p_probes.py,
# and E in e_probes.py. T and K have no file browser.
SERIES = ("P", "E")

# What the file browser has matched with probes (matching.py): a file
# browser at its defaults, on P and E, but for these.
MATCHED = [
    Rule("type", "file-browser",
         "a file browser, its attributes at their defaults but for those below"),
    Rule("attribute", "file-browser.objname", "any name nxwright's build takes"),
    *[Rule("attribute", "file-browser." + name,
           PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT)
      for name in ("x", "y", "w", "h")],
    # Its border and what lies behind it, as its probes on P and E showed.
    *[Rule("attribute", "file-browser." + name, words, covers, reason)
      for name, words, covers, reason in p_border_and_background_rules()],
    Rule("attribute", "file-browser.font", "any font of the project"),
    *[Rule("attribute", "file-browser." + text, "any characters, no more than its " + room,
           text_in_room(room))
      for text, room in _TEXTS],
    *[Rule("attribute", "file-browser." + room, "from 0 to 65534, the most the Nextion Editor "
           "takes (\"Out of range\" past it), its %s fitting it" % text,
           room_covered(text, 0xFFFE, low=0))
      for text, room in _TEXTS],
    Rule("attribute", "file-browser.left", "any value, written as it is"),
    Rule("attribute", "file-browser.ch", "any value, written as it is"),
    Rule("attribute", "file-browser.dis", "from 0 to 255", from_to(0, 255)),
    Rule("attribute", "file-browser.style", "0, 1, 2, or 3", from_to(0, 3), INVALID_VALUE),
    *[Rule("attribute", "file-browser." + name, "from -2147483648 to 2147483647, its entry's "
           "limits", from_to(-_LARGEST - 1, _LARGEST))
      for name in ("val", "maxval_y", "val_y")],
    Rule("attribute", "file-browser.qty", "any value, written as it is"),
    # A file browser's buffer size is written in 4 bytes without a sign, so a
    # negative size does not fit there.
    Rule("attribute", "file-browser.buffsize", "from 0 to 2147483647, its buffer that many "
         "bytes, rounded up to 4", from_to(0, _LARGEST), DOES_NOT_FIT),
    *[Rule("attribute", "file-browser." + name, "0 or 1", from_to(0, 1))
      for name in ("autoleft", "buff", "fwarning")],
    # Its psta picks whether nxwright writes it with folders listed.
    Rule("attribute", "file-browser.psta", "0, or 1, folders listed", from_to(0, 1),
         INVALID_VALUE),
    *[Rule("attribute", "file-browser." + name, "from 0 to 65535, written as it is: one of the "
           "project's pictures, or another", from_to(0, 0xFFFF))
      for name in ("pic1", "pic2")],
    Rule("code", None, "a call of the up of a file browser of the line's page, `up()`, in an "
         "event, on P and E", lambda need: method_call_covered(need, "file-browser", {"up": ""})),
] + [Rule("attribute", "file-browser." + name, *value_rule(name))
     for name in ("bco", "pco", "pco2", "bco2", "xcen", "spax", "spay", "borderc", "borderw")]
