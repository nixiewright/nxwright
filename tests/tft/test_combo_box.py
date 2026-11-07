"""The combo-box (tft/component_types/combo_box.py), a type P and E have
and T and K have not: its memory and its two texts' rooms on P, its
entries and their owner fields, its page's load section, the blocks of its
attributes in code, and what its rules cover.

Each test gives the function it checks that function's own input: a page
object of a probe's components, and a Project of the facts it reads
(tests/tft/unit_inputs.py). On P, a combo-box's memory starts with its record's
head, which the frame writes, so its tests compare the values its type
writes after the head (tests/tft/p_components.py). The probes of a combo-box's
whole user code are compared in tests/tft/test_whole_files.py.
"""
import unittest

from nxwright.tft.compile_context import CompileContext
from nxwright.tft import component_types
from nxwright.tft.matching import Need, matched_rules, unmatched
from tools.tft.probing import combo_box_probes, p_probes
from nxwright.tft.statements import CodePlace, encode_line
from tests.tft.p_components import PTypePieces, p_entries, p_memory, p_probe
from tests.tft.t_components import LoadSectionPieces
from tests.tft.unit_inputs import page, place, project_of

_PAGE_ENTRIES = 33
# A place for a combo-box of no probe: that of the combo-box at its
# defaults, from its probe's table.
_PLACE = place(p_probe("p-combo-box-at-its-defaults"), "page0-1")


def _combo_box(**attributes):
    """Returns the page object of a combo-box of `attributes` on P."""
    return page(combo_box_probes.combo_box_component(**attributes), series="P").objects[1]


class PieceTest(PTypePieces, LoadSectionPieces, unittest.TestCase):
    """A combo-box's memory, entries, and load section, against the pieces of
    the probes of one combo-box at its defaults and of two beside a text.

    Its memory, at places counted from its start: from 70 its txt_maxl, 32,
    and the place of its txt; from 86 its path_m, 256, and the place of its
    path. Its entries: ten give a top byte of their own in their owner field,
    and its texts' give where they lie.

    In its page's load section, a combo-box adds `init` with its ID."""

    TYPE = "combo-box"
    PROBES = [probe for probe in p_probes.PROBES if probe.name.startswith("p-combo-box-")]
    COUNT = 18


class RoomTest(unittest.TestCase):

    def test_at_its_defaults(self):
        # Its txt's room, "40V" in 36 bytes, then its path's, its six items
        # in 260 bytes.
        box_object = _combo_box()
        module = component_types.object_module(box_object)
        self.assertEqual(component_types.p_text(module, box_object, "txt", "txt_maxl"),
                         b"40V".ljust(36, b"\x00"))
        items = b"40V\r\n60V\r\n80V\r\n100V\r\n120V\r\n140V"
        self.assertEqual(component_types.p_text(module, box_object, "path", "path_m"),
                         items.ljust(260, b"\x00"))


class EntryTest(unittest.TestCase):

    def test_with_an_effect(self):
        # An effect moves its entries from 19 on two on, and their owner
        # fields' top bytes with them: its val's to 41, and its qty's to 39.
        entries = p_entries(_combo_box(effect=2), _PLACE)
        self.assertEqual((entries[24 * 41 + 19], entries[24 * 39 + 19]), (0x80, 0x03))

    def test_in_code(self):
        # Its val is the 40th of its own entries, after the page's 33.
        project = project_of(page(combo_box_probes.combo_box_component(), series="P"),
                             series="P")
        self.assertEqual(encode_line("sys0=cb0.val", CodePlace(0, "page0", "up"),
                                     CompileContext(project)),
                         b"\x05\x00\x00\x00\x00=\x01" + (_PAGE_ENTRIES + 39).to_bytes(4, "little"))


class DrastateTest(unittest.TestCase):

    def test_its_drastate_lies_in_its_memory(self):
        # At 106, after its ch, and nowhere else, though it has no entry.
        plain, drawn = (p_memory(_combo_box(**attributes), _PLACE)
                        for attributes in ({}, {"drastate": 1}))
        self.assertEqual([at for at, (a, b) in enumerate(zip(plain, drawn)) if a != b], [106])
        self.assertEqual(drawn[106], 1)


class RuleTest(unittest.TestCase):

    def test_on_p_and_e_alone(self):
        rules = matched_rules()
        for series in ("P", "E"):
            with self.subTest(series):
                need = Need("type", "combo-box", series=series)
                self.assertEqual(unmatched([need], rules), [])
        for series in ("T", "K"):
            with self.subTest(series):
                need = Need("type", "combo-box", series=series)
                self.assertEqual(unmatched([need], rules), [need])

    def test_its_values(self):
        rules = matched_rules()

        def need(name: str, value: int) -> Need:
            return Need("attribute", "combo-box." + name, value.to_bytes(4, "little"),
                        series="P")
        taken = (("qty", 0), ("qty", 1), ("qty", 254), ("qty", 255), ("hig", 15), ("hig", 16),
                 ("wid", 7), ("wid", 8), ("wid", 255), ("dir", 255),
                 ("mode", 2), ("mode", 3), ("dis", 100), ("dis", 101), ("val", 255), ("vvs0", 255),
                 ("vvs1", 255), ("ch", 32), ("ch", 33), ("path_m", 65534))
        for name, value in taken:
            with self.subTest((name, value)):
                self.assertEqual(unmatched([need(name, value)], rules), [])
        refused = (("dir", 256), ("val", 256), ("vvs0", 256), ("path_m", 65535))
        for name, value in refused:
            with self.subTest((name, value)):
                self.assertEqual(unmatched([need(name, value)], rules), [need(name, value)])


if __name__ == "__main__":
    unittest.main()
