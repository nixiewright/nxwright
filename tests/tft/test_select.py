"""The select (tft/component_types/select.py), a type P and E have and T
and K have not: its memory and its two texts' rooms on P, its entries, its
page's load section, the blocks of its attributes in code, and what its
rules cover.

Each test gives the function it checks that function's own input: a page
object of a probe's components, and a Project of the facts it reads
(tests/tft/unit_inputs.py). On P, a select's memory starts with its record's
head, which the frame writes, so its tests compare the values its type
writes after the head (tests/tft/p_components.py). The probes of a select's
whole user code are compared in tests/tft/test_whole_files.py.
"""
import struct
import unittest

from nxwright.tft.compile_context import CompileContext
from nxwright.tft import component_types
from nxwright.tft.component_types import select
from nxwright.tft.matching import Need, matched_rules, unmatched
from tools.tft.probing import p_probes, select_probes
from nxwright.tft.statements import CodePlace, encode_line
from tests.tft.p_components import PTypePieces, p_entries, p_memory, p_probe
from tests.tft.t_components import LoadSectionPieces
from tests.tft.unit_inputs import page, place, project_of

_PAGE_ENTRIES = 33
# A place for a select of no probe, whose memory and entries are compared
# with each other's: that of the select at its defaults, from its probe's
# table.
_PLACE = place(p_probe("p-select-at-its-defaults"), "page0-1")


def _select(**attributes):
    """Returns the page object of a select of `attributes` on P."""
    return page(select_probes.select_component(**attributes), series="P").objects[1]


class PieceTest(PTypePieces, LoadSectionPieces, unittest.TestCase):
    """A select's memory, entries, and load section, against the pieces of
    the probes of one select at its defaults and of two beside a text.

    Its memory, at places counted from its start: its txt_maxl at 74 and the
    place of its txt at 76, and its path_m at 86 and the place of its path at
    88; the second of two selects has a val of 1. Its entries: its val's with
    0x80 in its owner field's top byte, and its texts' giving where they lie.

    In its page's load section, a select adds `init` with its ID."""

    TYPE = "select"
    PROBES = [probe for probe in p_probes.PROBES if probe.name.startswith("p-select-")]
    COUNT = 10


class RoomTest(unittest.TestCase):

    def test_at_its_defaults(self):
        # Its txt's room, 256 bytes of zeros, then its path's, its twelve
        # items in 1028 bytes.
        select_object = _select()
        module = component_types.object_module(select_object)
        self.assertEqual(component_types.p_text(module, select_object, "txt", "txt_maxl"),
                         bytes(256))
        items = b"\r\n".join(b"%02d" % number for number in range(1, 13))
        self.assertEqual(component_types.p_text(module, select_object, "path", "path_m"),
                         items.ljust(1028, b"\x00"))


class MemoryTest(unittest.TestCase):

    def test_without_its_line(self):
        # A dis of 0 writes no pco1, which lies at 72.
        self.assertEqual(p_memory(_select(dis=0, pco1=4567), _PLACE)[70:74], bytes(4))
        self.assertEqual(p_memory(_select(pco1=4567), _PLACE)[72:74], struct.pack("<H", 4567))


class EntryTest(unittest.TestCase):

    def test_with_an_effect(self):
        # An effect moves its val's entry two on, and its owner's top byte
        # with it: its txt's entry takes 31, without that byte.
        entries = p_entries(_select(effect=2), _PLACE)
        self.assertEqual(entries[24 * 33:][16:20].hex(" "), "00 01 00 80")
        self.assertEqual(entries[24 * 31:][16:20].hex(" "), "00 01 00 00")

    def test_in_code(self):
        # Its val is the 32nd of its own entries, after the page's 33; the
        # 31st without its line, which has no pco1.
        place = CodePlace(0, "page0", "up")
        for attributes, entry in (({}, 31), ({"dis": 0}, 30)):
            with self.subTest(attributes):
                project = project_of(page(select_probes.select_component(**attributes),
                                          series="P"), series="P")
                self.assertEqual(encode_line("sys0=select0.val", place, CompileContext(project)),
                                 b"\x05\x00\x00\x00\x00=\x01"
                                 + (_PAGE_ENTRIES + entry).to_bytes(4, "little"))
        self.assertRaises(KeyError, select._of(False).attribute_place, "pco1")


class RuleTest(unittest.TestCase):

    def test_on_p_and_e_alone(self):
        rules = matched_rules()
        for series in ("P", "E"):
            with self.subTest(series):
                need = Need("type", "select", series=series)
                self.assertEqual(unmatched([need], rules), [])
        for series in ("T", "K"):
            with self.subTest(series):
                need = Need("type", "select", series=series)
                self.assertEqual(unmatched([need], rules), [need])

    def test_its_path(self):
        # Items of any characters between "\r\n", or none, no
        # longer than its path_m.
        rules = matched_rules()

        def need(path: bytes, path_m: int) -> Need:
            return Need("attribute", "select.path", path, series="P",
                        context={"path_m": path_m.to_bytes(2, "little")})
        for path, path_m in ((b"Ab\r\n9z\r\nc", 9), (b"a", 1), (b"a\nb", 255), (b"a_b", 255),
                             (b"a\r\n", 255), (b"", 255)):
            with self.subTest(path):
                self.assertEqual(unmatched([need(path, path_m)], rules), [])
        for path, path_m in ((b"Ab\r\n9z\r\nc", 8),):
            with self.subTest(path):
                self.assertEqual(unmatched([need(path, path_m)], rules), [need(path, path_m)])

    def test_its_txt(self):
        # Any characters, no longer than its txt_maxl.
        rules = matched_rules()

        def need(txt: bytes, txt_maxl: int) -> Need:
            return Need("attribute", "select.txt", txt, series="P",
                        context={"txt_maxl": txt_maxl.to_bytes(2, "little")})
        for txt, txt_maxl in ((b"Ab9z", 4), (b"a" * 1000, 1000), (b"a b, \xe9!", 255),
                              (b"a\tb", 255), (b"a\r\nb", 255)):
            with self.subTest(txt):
                self.assertEqual(unmatched([need(txt, txt_maxl)], rules), [])
        for txt, txt_maxl in ((b"Ab9z", 3),):
            with self.subTest(txt):
                self.assertEqual(unmatched([need(txt, txt_maxl)], rules), [need(txt, txt_maxl)])

    def test_its_values(self):
        rules = matched_rules()

        def need(name: str, value: int) -> Need:
            return Need("attribute", "select." + name, value.to_bytes(4, "little"),
                        series="P")
        for name, value in (("hig", 15), ("hig", 16), ("hig", 255), ("hig", 256), ("ch", 32),
                            ("ch", 33), ("dis", 0), ("val", 0xFFFF), ("val", 0x10000),
                            ("path_m", 0), ("path_m", 8192)):
            with self.subTest((name, value)):
                self.assertEqual(unmatched([need(name, value)], rules), [])
        for name, value in (("dis", 2), ("path_m", 8193)):
            with self.subTest((name, value)):
                self.assertEqual(unmatched([need(name, value)], rules), [need(name, value)])


if __name__ == "__main__":
    unittest.main()
