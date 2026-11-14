"""The gmov (tft/component_types/gmov.py), a type P and E have and T and K
have not: its memory, its path's room, and its buffer on P, its entries by
its from, its page's load section, and what its rules cover.

Each test gives the function it checks that function's own input: a page
object of a probe's components, and a Project of the facts it reads
(tests/tft/unit_inputs.py). On P, a gmov's memory starts with its record's head,
which the frame writes, so its tests compare the values its type writes
after the head (tests/tft/p_components.py). The probes of a gmov's whole user
code, and its record's place of its playend event's code, are compared in
tests/tft/test_whole_files.py.
"""
from dataclasses import replace
import unittest

from nxwright.tft import component_types
from nxwright.tft.component_types import gmov
from nxwright.tft.matching import Need, matched_rules, unmatched
from tools.tft.probing import gmov_probes, p_probes
from tests.tft.p_components import PTypePieces, p_entries, p_memory, p_probe, p_values
from tests.tft.t_components import LoadSectionPieces
from tests.tft.unit_inputs import page, piece, place, project_of, without_attribute

_PROBE_AT_ITS_DEFAULTS = "p-gmov-at-its-defaults"
# A place for a gmov of no probe: that of the gmov at its defaults, from
# its probe's table.
_PLACE = place(p_probe(_PROBE_AT_ITS_DEFAULTS), "page0-1")


def _gmov(**attributes):
    """Returns the page object of a gmov of `attributes` on P."""
    return page(gmov_probes.gmov_component(**attributes), series="P").objects[1]


class PieceTest(PTypePieces, LoadSectionPieces, unittest.TestCase):
    """A gmov's memory, entries, and load section, against the pieces of the
    probes of one gmov at its defaults and of two beside a text, the second
    at a from of 1.

    Its memory, at places counted from its start: its vid, 65535, from 56; its
    path_m, 255, at 82 and the place of its path at 84; its buffer's size,
    12000, at 88 and its place at 92. Its entries: at a from of 0, its vid's
    is 20, with 1 in its owner field's top byte, and its path's 21; at a from
    of 1, it has no vid entry.

    In its page's load section, a gmov adds `init` with its ID."""

    TYPE = "gmov"
    PROBES = [probe for probe in p_probes.PROBES if probe.name.startswith("p-gmov-")]
    COUNT = 3


class RoomTest(unittest.TestCase):

    def test_at_its_defaults(self):
        # Its path's room, 256 bytes of zeros, and its buffer, 12000 bytes.
        gmov_object = _gmov()
        module = component_types.object_module(gmov_object)
        self.assertEqual(component_types.p_text(module, gmov_object, "path", "path_m"),
                         bytes(256))
        self.assertEqual(module.buffer_size(gmov_object, project_of(series="P")), 12000)


class MemoryTest(unittest.TestCase):

    def test_molloc_changes_nothing(self):
        # Its values with a molloc and a molloc_s are those of the probe at
        # its defaults.
        self.assertEqual(p_values(_gmov(molloc=20000, molloc_s=30000), _PLACE),
                         piece(p_probe(_PROBE_AT_ITS_DEFAULTS), "page0-1-memory"))


class EntryTest(unittest.TestCase):

    def test_at_a_from_of_1(self):
        # It has no vid entry: its path's is 20, and its memory gives 0 for
        # its vid.
        gmov_object = _gmov(**{"from": 1})
        entries = p_entries(gmov_object, _PLACE)
        self.assertEqual(entries[24 * 20:][20:24].hex(" "), "3f 00 01 00")
        self.assertEqual(entries[24 * 21:][:24], bytes(24))
        self.assertEqual(p_memory(gmov_object, _PLACE)[56:58], bytes(2))
        self.assertRaises(KeyError, gmov._of(False).attribute_place, "vid")

    def test_without_its_from(self):
        # A gmov that has no from is written with a from of 0, the default.
        # Its values and its entries are those of the probe at its defaults.
        made = page(gmov_probes.gmov_component(), series="P")
        made = replace(made, objects=[made.objects[0],
                                      without_attribute(made.objects[1], "from")])
        gmov_object = project_of(made, series="P").pages[0].objects[1]
        probe = p_probe(_PROBE_AT_ITS_DEFAULTS)
        self.assertEqual(p_values(gmov_object, _PLACE), piece(probe, "page0-1-memory"))
        self.assertEqual(p_entries(gmov_object, _PLACE), piece(probe, "page0-1-entries"))


class RuleTest(unittest.TestCase):

    def test_on_p_and_e_alone(self):
        rules = matched_rules()
        for series in ("P", "E"):
            with self.subTest(series):
                need = Need("type", "gmov", series=series)
                self.assertEqual(unmatched([need], rules), [])
        for series in ("T", "K"):
            with self.subTest(series):
                need = Need("type", "gmov", series=series)
                self.assertEqual(unmatched([need], rules), [need])

    def test_its_times_at_their_entries_limits(self):
        rules = matched_rules()
        for name in ("tim", "stim", "qty"):
            for value in (-2 ** 31, 2 ** 31 - 1):
                with self.subTest(name, value=value):
                    need = Need("attribute", "gmov." + name,
                                value.to_bytes(4, "little", signed=True), series="P")
                    self.assertEqual(unmatched([need], rules), [])

    def test_its_values(self):
        # Its vid, any value at a from of 0, written as it is.
        rules = matched_rules()

        def need(name: str, value: int, **context) -> Need:
            return Need("attribute", "gmov." + name, value.to_bytes(4, "little"),
                        context=context, series="P")
        for name, value in (("from", 1), ("en", 2), ("en", 3), ("dis", 9), ("dis", 10),
                            ("dis", 1000), ("dis", 1001),
                            ("tim", 0x7FFFFFFF), ("path_m", 0), ("path_m", 65534),
                            ("molloc", 1), ("vid", 0), ("vid", 0xFFFF)):
            with self.subTest((name, value)):
                self.assertEqual(unmatched([need(name, value)], rules), [])
        for name, value in (("from", 2), ("path_m", 65535), ("vid", 0x10000)):
            with self.subTest((name, value)):
                self.assertEqual(unmatched([need(name, value)], rules), [need(name, value)])
        # At a from of 1, any vid too, which it does not write.
        self.assertEqual(unmatched([need("vid", 3, **{"from": b"\x01"})], rules), [])
        # A path_m its path does not fit.
        short = need("path_m", 2, path=b"abc")
        self.assertEqual(unmatched([short], rules), [short])

    def test_its_path(self):
        # Any characters, no longer than its path_m.
        rules = matched_rules()

        def need(path: bytes, path_m: int) -> Need:
            return Need("attribute", "gmov.path", path, series="P",
                        context={"path_m": path_m.to_bytes(2, "little")})
        for path, path_m in ((b"sd0/Mov_1.gmov", 14), (b"a" * 1000, 1000), (b"a b", 255),
                             (b"a\\b", 255)):
            with self.subTest(path):
                self.assertEqual(unmatched([need(path, path_m)], rules), [])
        for path, path_m in ((b"sd0/Mov_1.gmov", 13),):
            with self.subTest(path):
                self.assertEqual(unmatched([need(path, path_m)], rules), [need(path, path_m)])


if __name__ == "__main__":
    unittest.main()
