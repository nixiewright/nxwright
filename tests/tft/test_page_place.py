"""A page's place and size away from its screen's (tools/tft/probing/page_place_probes.py,
frame.py): the probes' components at their types' functions, the check's
taking every probe's project, and the frame writing such a page at its
screen's place and size.

Each test gives the function it checks its own input: a probe's page made
in memory, its place and size as the probe gives them, in a Project of the
facts it reads, and each component's place, read from the probe's table
(tests/tft/unit_inputs.py). The probes that keep fixtures are compared whole in
tests/tft/test_whole_files.py.
"""
import unittest

from nxwright.tft import frame
from nxwright.tft.component_types import number_from_bytes
from tools.tft.probing import page_place_probes
from nxwright.tft.matching import matched_rules, project_needs, unmatched
from tools.tft.probing.text_probes import text_component
from tests.tft.p_components import PTypePieces
from tests.tft.t_components import TypePieces
from tests.tft.unit_inputs import page, probe_facts, probe_project, project_of


class PiecesTest(TypePieces, unittest.TestCase):
    """The text of the probe on T of a page of another size that keeps its
    whole user code, at its type's functions, against the probe's pieces
    (tests/tft/t_components.py)."""

    PROBES = [probe for probe in page_place_probes.PROBES if probe.base == "T"]
    COUNT = 1


class PPiecesTest(PTypePieces, unittest.TestCase):
    """The text of the probe on P of a page of another size that keeps its
    whole user code, at its type's functions on P, against the probe's
    pieces (tests/tft/p_components.py)."""

    PROBES = [probe for probe in page_place_probes.PROBES if probe.base == "P"]
    COUNT = 1


class PlaceTest(unittest.TestCase):

    def test_each_probe_s_project_is_taken(self):
        rules = matched_rules()
        for probe in page_place_probes.PROBES:
            with self.subTest(probe.name):
                self.assertEqual(unmatched(project_needs(probe_project(probe)), rules), [])

    def test_each_page_in_memory_has_its_place_and_size(self):
        # So that the test below compares a page away from its screen's.
        for probe in page_place_probes.PROBES:
            page0 = probe_facts(probe).pages[0].objects[0]
            with self.subTest(probe.name):
                self.assertEqual({name: number_from_bytes(page0.attribute(name))
                                  for name, _ in probe.change.page_values},
                                 dict(probe.change.page_values))

    def test_a_page_is_written_at_its_screen_s_place_and_size(self):
        # As a page at the screen's own, with the same text, on each series.
        for probe in page_place_probes.PROBES:
            with self.subTest(probe.name):
                at_the_screen = project_of(page(text_component(), series=probe.base),
                                           series=probe.base)
                self.assertEqual(frame.user_code(probe_facts(probe)),
                                 frame.user_code(at_the_screen))


if __name__ == "__main__":
    unittest.main()
