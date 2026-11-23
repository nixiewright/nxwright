"""The QR code component, as the Nextion Editor 1.68.2 writes it on T and K
(ResearchNotes/tft/qr-code-component.md gives each value, and how it was found).

So far it writes a QR code at its defaults but for its place, its size, its
txt, the text the code holds, its txt_maxl, up to its entry's highest, its
colours, bco and pco, and its dis, the margin around the code. It writes
its logo too. Its sta gives whether a picture of the project shows in the
code's middle, and its pic gives which. Its drawing is one command, which
draws the code of its txt in its width, from its top left. Its memory, 16
bytes, gives its sta, dis, bco, pco, pic, and txt_maxl, then where its txt
lies. Its txt lies after its page's components' memory (page_text,
component_types/__init__.py): txt_maxl + 1 bytes, rounded up to 4.

A QR code with a logo, of sta 1, has one entry more, its pic's, before its
txt's, and its drawing gives that entry where one without a logo gives
65535. So each QR code is written by the variant of its sta (variant).

On P, it has no drawing blocks. Its memory gives its values as on T, from
56, its txt still after its page's components' memory (P_TEXTS), and its
entries keep T's numbers (P_ENTRIES).

On F, it is written as on T, but its txt_maxl's entry gives a highest of
368.
"""
import struct

from nxwright.project.attribute_values import number_from_bytes

from nxwright.tft.component_types import (P_DRAWN_ENTRIES, PLACE_WORDS, TXT_MAXL_WORDS, TXT_WORDS,
                                   background_fill, entry_operand, from_to, object_entries,
                                   packed_entries, place_and_size, place_fits_its_record,
                                   text_fits, txt_maxl_covered, value_operand, value_rule,
                                   with_txt)
from nxwright.tft.matching import Rule
from nxwright.tft.reasons import DOES_NOT_FIT, INVALID_VALUE

# Where each value lies in a QR code's memory, from its base, and where the
# place of its txt lies.
_STA, _DIS, _BCO, _PCO, _PIC, _TXT_MAXL, _TXT_PLACE = 0, 1, 2, 4, 6, 8, 12
# Its starting values on T, K, and F, in their order in memory, and their
# form there (memory_at): its txt_place is where its txt lies.
MEMORY_VALUES = ("sta", "dis", "bco", "pco", "pic", "txt_maxl", "txt_place")
MEMORY_FORMAT = "<BBHHHH2xI"
# Each attribute's entry, within the type, for a QR code without a logo.
# One with a logo has its pic's entry where this one has its txt's, and its
# txt's and txt_maxl's one later.
_ENTRY = {"type": 0, "id": 1, "vscope": 3, "x": 9, "y": 10, "w": 11, "h": 12, "endx": 13,
          "endy": 14, "sta": 19, "dis": 20, "bco": 21, "pco": 22, "txt": 23, "txt_maxl": 24}
# The record's slots that give an entry, and which entry. One with a logo
# gives its pic in slot 6 too.
_SLOTS = {1: "vscope", 2: "sta", 4: "bco", 16: "pco", 28: "txt", 29: "txt_maxl", 42: "x",
          43: "y", 44: "endx", 45: "endy", 46: "w", 47: "h", 49: "id", 55: "dis", 62: "type"}
_PIC_SLOT = 6
# The command that draws a QR code, by series. K and F number it as T does.
_DRAW_QR_CODE = {"T": b"\x09\x08\x08", "K": b"\x09\x08\x08", "F": b"\x09\x08\x08"}
# What the drawing of a QR code without a logo gives where one with a logo
# gives its pic's entry: no picture.
_NO_PICTURE = 0xFFFF
# Its attributes at their defaults, as a new one's.
_DEFAULTS = {"sta": 0, "dis": 8, "bco": 0xFFFF, "pco": 0, "pic": _NO_PICTURE}
# The most txt_maxl the Nextion Editor takes, "Out of range" past it, which
# its txt_maxl's entry gives as its highest, by series: F gives its own, and
# P and E theirs. A page may hold less: past 154, a QR code alone needs more
# temporary memory than a page of NX4832T035 leaves. nxwright's build
# refuses that, as the Nextion Editor's compile does.
_TXT_MAXL_HIGHEST = {"T": 192, "K": 192, "F": 368, "P": 630, "E": 630}
# Where its values start in its memory on P: after its record's head and its
# effect's values.
_P_VALUES_AT = 56
# Its entries on P, by name: (place from its base, highest, code). Its txt's
# place and code come from its P_TEXTS, and its pic's highest from the
# project's last picture (P_LAST_RESOURCE, component_types.p_table), and its
# txt_maxl's highest is P's own (_TXT_MAXL_HIGHEST).
_P_VALUES = {"sta": (_P_VALUES_AT + _STA, 1, 0x121), "dis": (_P_VALUES_AT + _DIS, 255, 0x131),
             "bco": (_P_VALUES_AT + _BCO, 0xFFFF, 0x232),
             "pco": (_P_VALUES_AT + _PCO, 0xFFFF, 0x232),
             "pic": (_P_VALUES_AT + _PIC, None, 0x232), "txt": (0, 0, 0x3F),
             "txt_maxl": (_P_VALUES_AT + _TXT_MAXL, _TXT_MAXL_HIGHEST["P"], 0x222)}


def _value(page_object, name: str) -> int:
    value = page_object.attribute(name)
    return _DEFAULTS[name] if value is None else number_from_bytes(value)


EVENTS = ("down", "up")


class _QrCode:
    """A QR code with or without a logo, with the members a type's module
    gives (component_types/__init__.py) but MATCHED."""
    EVENTS = EVENTS

    def __init__(self, logo: bool):
        self.logo = logo
        self.ENTRIES = 34 if logo else 33
        self._entry = dict(_ENTRY)
        self._slots = dict(_SLOTS)
        if logo:
            self._entry.update(pic=23, txt=24, txt_maxl=25)
            self._slots[_PIC_SLOT] = "pic"
        self.P_ENTRIES = {**P_DRAWN_ENTRIES, **{
            self._entry[name]: (name, at, highest, 0, code)
            for name, (at, highest, code) in _P_VALUES.items() if name in self._entry}}

    # Its memory on P: what its record's head holds and its effect's values,
    # then its values, as on T (memory_at). Its txt lies after its page's
    # components' memory.
    P_MEMORY_SIZE = 72
    P_TEXTS = {_P_VALUES_AT + _TXT_PLACE: ("txt", "txt_maxl", _P_VALUES_AT + _TXT_MAXL)}
    P_LAST_RESOURCE = {"pic": "picture"}

    # The frame calls the type's background_fill, which is the plain fill.
    background_fill = staticmethod(background_fill)

    def _operand(self, place, name: str) -> bytes:
        return entry_operand(place.first_entry + self._entry[name])

    def drawing(self, page_object, project, place) -> list:
        """Returns the QR code's drawing: the command that draws a QR code,
        with its place and width, the entries of its bco and pco, its pic's
        entry for one with a logo or 65535 for one without, then the entries
        of its dis and txt."""
        x, y, w, _ = place_and_size(page_object)
        logo = self._operand(place, "pic") if self.logo else value_operand(_NO_PICTURE)
        return [_DRAW_QR_CODE[project.settings.model.series] + b"%d,%d,%d," % (x, y, w)
                + b",".join([self._operand(place, "bco"), self._operand(place, "pco"), logo,
                             self._operand(place, "dis"), self._operand(place, "txt")])]

    def data(self, page_object, project, place) -> bytes:
        """Returns the QR code's entries: where each of its values lies in
        memory. One with a logo gives its pic's, from 0 to the project's last
        picture."""
        maxl = number_from_bytes(page_object.attribute("txt_maxl"))
        base = place.base
        values = {
            "sta": (base + _STA, 1, 0, 0x121), "dis": (base + _DIS, 255, 0, 0x131),
            "bco": (base + _BCO, 0xFFFF, 0, 0x232), "pco": (base + _PCO, 0xFFFF, 0, 0x232),
            # Its txt lies after the page's components' memory (page_text).
            # The text's code gives its size there, txt_maxl + 1, in its
            # second byte.
            "txt": (place.text_place, 0, 0, (maxl + 1) << 8 | 0x3F),
            "txt_maxl": (base + _TXT_MAXL, _TXT_MAXL_HIGHEST[project.settings.model.series], 0,
                         0x222),
        }
        if self.logo:
            pictures = project.resource_count("picture")
            values["pic"] = (base + _PIC, pictures - 1, 0, 0x232)
        entries = object_entries(page_object, place.object_id)
        entries.update({self._entry[name]: value for name, value in values.items()})
        return packed_entries(entries, self.ENTRIES, place)

    def memory_at(self, page_object, project, place) -> bytes:
        """Returns the QR code's starting values: its sta, dis, bco, and pco,
        its pic for one with a logo or two zeros for one without, its
        txt_maxl, two zeros, then where its txt lies in memory,
        place.text_place, or 0 before the frame places it, 4 bytes."""
        values = {name: _value(page_object, name) for name in ("sta", "dis", "bco", "pco")}
        values.update(pic=_value(page_object, "pic") if self.logo else 0,
                      txt_maxl=number_from_bytes(page_object.attribute("txt_maxl")),
                      txt_place=place.text_place or 0)
        return struct.pack(MEMORY_FORMAT, *(values[name] for name in MEMORY_VALUES))

    def page_text(self, page_object, project) -> bytes:
        """Returns what the QR code keeps after its page's components' memory:
        its txt, padded with zeros to txt_maxl + 1 bytes, the whole padded
        with zeros to a multiple of 4."""
        return with_txt(b"", page_object)

    def record_slots(self) -> dict:
        """Returns the QR code's slots in its record: {slot: entry within the
        type}."""
        return {slot: self._entry[name] for slot, name in self._slots.items()}

    def attribute_place(self, name: str) -> int:
        """Returns the entry, within the type, of the attribute `name`, any
        the type writes. Raises KeyError for another."""
        return self._entry[name]


_WITHOUT_A_LOGO, _WITH_A_LOGO = _QrCode(False), _QrCode(True)


def variant(page_object) -> _QrCode:
    """Returns what describes the QR code `page_object`: one with a logo when
    its sta is 1, else one without."""
    return _WITH_A_LOGO if _value(page_object, "sta") == 1 else _WITHOUT_A_LOGO


# The series this module's probes matched (matching.py): T, K in k_probes.py,
# P in p_probes.py, E in e_probes.py, and F in f_probes.py.
SERIES = ("T", "K", "P", "E", "F")

# What the QR code has matched with probes (matching.py): a QR code at its
# defaults, on each screen model of T and K at each rotation, and on P and E,
# but for these.
MATCHED = [
    Rule("type", "qr-code", "a QR code, its attributes at their defaults but for those below"),
    Rule("attribute", "qr-code.objname", "any name nxwright's build takes"),
    Rule("attribute", "qr-code.x", PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT),
    Rule("attribute", "qr-code.y", PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT),
    Rule("attribute", "qr-code.w", PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT),
    Rule("attribute", "qr-code.h", PLACE_WORDS, place_fits_its_record, DOES_NOT_FIT),
    Rule("attribute", "qr-code.txt", TXT_WORDS, text_fits),
    Rule("attribute", "qr-code.txt_maxl", TXT_MAXL_WORDS, txt_maxl_covered, DOES_NOT_FIT),
    Rule("attribute", "qr-code.bco", *value_rule("bco")),
    Rule("attribute", "qr-code.pco", *value_rule("pco")),
    Rule("attribute", "qr-code.dis", "from 0 to 255", from_to(0, 255)),
    Rule("attribute", "qr-code.sta", "0, no logo, or 1, a logo", from_to(0, 1), INVALID_VALUE),
    # A pic is 2 bytes in memory, written as it is, whichever picture it is,
    # and not written at all without a logo.
    Rule("attribute", "qr-code.pic", "any value from 0 to 65535, written as it is: a picture "
         "of the project, or 65535 for none"),
]
