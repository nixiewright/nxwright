"""The switch (tft/component_types/switch.py), a type P and E have and T
and K have not: its memory and its txt's room on P, its entries, the blocks
of its attributes in code, and what its rules cover.

Each test gives the function it checks that function's own input: a page
object of a probe's components, and a Project of the facts it reads
(tests/tft/unit_inputs.py). On P, a switch's memory starts with its record's
head, which the frame writes, so its tests compare the values its type
writes after the head (tests/tft/p_components.py). The probes of a switch's
whole user code are compared in tests/tft/test_whole_files.py.
"""
import unittest

from nxwright.tft.compile_context import CompileContext
from nxwright.tft import component_types
from nxwright.tft.matching import Need, matched_rules, unmatched
from tools.tft.probing import p_probes, switch_probes
from nxwright.tft.statements import CodePlace, encode_line
from tests.tft.p_components import PTypePieces
from tests.tft.unit_inputs import page, project_of


class PieceTest(PTypePieces, unittest.TestCase):
    """A switch's memory and entries, against the pieces of the probes of one
    switch at its defaults, of two beside a text, and of one between two
    external pictures.

    Its memory, at places counted from its start: from 52 its effect, first,
    and time, zeros, its dez and val, 0, its bco, 50712, pco, bco2, 1024,
    pco2, and pco1, its font, 0, its dis, 100, its txt_maxl, 24, and the place
    of its txt."""

    TYPE = "switch"
    # The probe of two external pictures puts a switch between them.
    PROBES = [probe for probe in p_probes.PROBES if probe.name.startswith("p-switch-")
              or probe.name == "p-external-picture-two-beside-a-switch"]
    COUNT = 4


class RoomTest(unittest.TestCase):

    def test_at_its_defaults(self):
        # Its txt's room starts with its txt, "False/True".
        switch_object = page(switch_probes.switch_component(), series="P").objects[1]
        module = component_types.object_module(switch_object)
        self.assertEqual(component_types.p_text(module, switch_object, "txt", "txt_maxl")[:10],
                         b"False/True")


class CodeTest(unittest.TestCase):

    def test_its_entries(self):
        # Its val's entry is the 21st of its own, after the page's 33.
        project = project_of(page(switch_probes.switch_component(), series="P"), series="P")
        place = CodePlace(0, "page0", "up")
        self.assertEqual(encode_line("sys0=sw0.val", place, CompileContext(project)),
                         b"\x05\x00\x00\x00\x00=\x01" + (33 + 20).to_bytes(4, "little"))


class RuleTest(unittest.TestCase):

    def test_on_p_and_e_alone(self):
        rules = matched_rules()
        for series in ("P", "E"):
            with self.subTest(series):
                need = Need("type", "switch", series=series)
                self.assertEqual(unmatched([need], rules), [])
        for series in ("T", "K"):
            with self.subTest(series):
                need = Need("type", "switch", series=series)
                self.assertEqual(unmatched([need], rules), [need])

    def test_its_values(self):
        # A switch takes any dis, val, and dez that fits in their bytes.
        rules = matched_rules()

        def need(name: str, value: int) -> Need:
            return Need("attribute", "switch." + name, value.to_bytes(4, "little"), series="P")
        for name, value in (("dis", 100), ("dis", 101), ("val", 1), ("val", 2), ("dez", 1)):
            with self.subTest((name, value)):
                self.assertEqual(unmatched([need(name, value)], rules), [])


if __name__ == "__main__":
    unittest.main()
