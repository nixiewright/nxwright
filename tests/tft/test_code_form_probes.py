"""The forms of code the Nextion Editor writes as plainer ones
(tools/tft/probing/code_form_probes.py): the blocks the encoder gives each probe
of an event's code, and the check's taking every probe's project on each
series that runs them.

Each test gives the function it checks a Project of the facts of a probe's
page, program.s, and macros, made in memory as nxwright's build makes them
(tests/tft/unit_inputs.py), and compares the encoder's blocks with the probe's
pieces. The probes that compare the whole file are sampled in
tests/tft/test_whole_files.py.
"""
import unittest

from tools.tft.probing import code_form_probes, f_probes, k_probes, p_probes
from nxwright.tft.matching import matched_rules, project_needs, unmatched
from tools.tft.probing.statement_probes import kept_blocks
from tests.tft.unit_inputs import piece, piece_names, probe_project


class PiecesTest(unittest.TestCase):
    """The blocks the encoder gives page0's Touch Release event of each probe
    that keeps them, in strict Nextion syntax, against the probe's pieces:
    comments after code, and a negative number after each arithmetic
    operator, in assignments and in commands' operands."""

    def test_each_probe(self):
        probes = [probe for probe in code_form_probes.PROBES if probe.fixtures]
        self.assertEqual(len(probes), 3)
        for probe in probes:
            with self.subTest(probe.name):
                self.assertEqual(kept_blocks(probe, probe_project(probe)),
                                 {each: piece(probe, each) for each in piece_names(probe)})


class MatchedTest(unittest.TestCase):

    def test_each_probe_s_project(self):
        # On T, and as K, P, and F run them; E runs P's.
        rules = matched_rules()
        probes = code_form_probes.PROBES + [
            probe for module in (k_probes, p_probes, f_probes) for probe in module.PROBES
            if "code-forms-" in probe.name]
        self.assertEqual(len(probes), 24)
        for probe in probes:
            with self.subTest(probe.name):
                self.assertEqual(unmatched(project_needs(probe_project(probe)), rules), [])


if __name__ == "__main__":
    unittest.main()
