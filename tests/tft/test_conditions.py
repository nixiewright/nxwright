"""Conditions past the first probes of if, while, and for
(tft/control_statements.py): their blocks, as the probes of
condition_probes.py kept them once they matched the Nextion Editor's file,
how a condition is split into comparisons, and what the check covers.

The probes' blocks are the encoder's for a probe's page and program.s made
in memory (tests/tft/unit_inputs.py).
"""
import unittest

from tools.tft.probing import condition_probes
from nxwright.tft.control_statements import _comparisons, covers_condition
from nxwright.tft.instructions import for_statement
from nxwright.tft.matching import Need
from tools.tft.probing.statement_probes import kept_blocks
from nxwright.tft.statements import StatementError
from tools.tft.probing.text_probes import text_component
from tests.tft.line_context import line_context
from tests.tft.unit_inputs import piece, piece_names, probe_project


class FixtureTest(unittest.TestCase):
    """The encoder still writes the blocks the probes checked, against each
    probe's pieces, on its page and program.s made in memory."""

    def test_each_probe_s_fixtures(self):
        probes = [probe for probe in condition_probes.PROBES if probe.fixtures]
        self.assertEqual(len(probes), 5)
        for probe in probes:
            with self.subTest(probe.name):
                self.assertEqual(kept_blocks(probe, probe_project(probe)),
                                 {name: piece(probe, name) for name in piece_names(probe)})


class SplitTest(unittest.TestCase):
    """The Nextion Editor joins comparisons at && and || outside the texts."""

    def test_joins_in_a_text_are_left_in_it(self):
        self.assertEqual(_comparisons('t0.txt=="a&&b"'), ([("t0.txt", "==", '"a&&b"')], None))
        self.assertEqual(_comparisons('t0.txt=="a||b"&&sys0==1'),
                         ([("t0.txt", "==", '"a||b"'), ("sys0", "==", "1")], "&&"))
        self.assertEqual(_comparisons(r't0.txt=="a\"&&b"||sys0==4'),
                         ([("t0.txt", "==", r'"a\"&&b"'), ("sys0", "==", "4")], "||"))

    def test_both_joins_outside_texts_are_refused(self):
        # Both in texts are no join, so the condition is one comparison.
        self.assertEqual(len(_comparisons('t0.txt=="&&||"')[0]), 1)
        with self.assertRaisesRegex(StatementError, "both && and \\|\\|"):
            _comparisons('t0.txt=="a"&&sys0==1||sys1==2')


class CoveredTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.need = Need("code", "event", "", context=line_context(text_component()))

    def test_what_it_covers(self):
        # Up to 80 comparisons in up to 788 characters, as the probes
        # showed, texts holding && or ||, and texts of up to 740 characters
        # together.
        eighty = "||".join("sys0==%d" % number for number in range(80))
        self.assertEqual(len(eighty), 788)
        for condition in (eighty, "&&".join("sys0!=%d" % number for number in range(12)),
                          't0.txt=="a&&b"', 't0.txt=="&&"||t0.txt=="||"',
                          't0.txt=="%s"' % ("a" * 740),
                          't0.txt=="%s"||t0.txt=="%s"' % ("b" * 450, "c" * 290)):
            with self.subTest(condition=condition[:40]):
                self.assertTrue(covers_condition(condition, self.need))

    def test_past_what_the_probes_tried(self):
        # These are encoded like shorter ones: 81 comparisons, a condition of
        # 789 characters, a comparison whose line is 767 bytes, and texts of
        # 741 characters together.
        for condition in ("||".join("a==%d" % number for number in range(81)),
                          "||".join("sys0==%d" % number for number in range(80)) + "0",
                          't0.txt=="%s"' % ("a" * 752),
                          't0.txt=="%s"||t0.txt=="%s"' % ("b" * 450, "c" * 291),
                          't0.txt=="%s"||t0.txt=="%s"' % ("b" * 600, "c" * 600)):
            with self.subTest(condition=condition[:40]):
                self.assertTrue(covers_condition(condition, self.need))

    def test_a_comparison_of_any_length(self):
        # The Nextion Editor refuses a comparison whose line is too long, but
        # nxwright's build refuses it first, so the encoder does not check
        # the length. On P, the Nextion Editor takes lines up to 4095 bytes.
        for condition in ('t0.txt=="%s"' % ("a" * 753), 't0.txt=="%s"' % ("中" * 376),
                          '"%s"=="%s"' % ("a" * 378, "b" * 379),
                          't0.txt=="%s"' % ("a" * 4080)):
            with self.subTest(condition=condition[:40]):
                self.assertTrue(covers_condition(condition, self.need))

    def test_a_for_whose_text_holds_a_semicolon(self):
        # The Nextion Editor refused it ("SYNTAX ERROR:for"), though it took
        # the same text in an if.
        need = Need("code", "event", "", context=self.need.context)
        self.assertFalse(for_statement.covers('for(sys0=0;t0.txt!="a;b";sys0++)', need))
        self.assertTrue(covers_condition('t0.txt!="a;b"', self.need))


if __name__ == "__main__":
    unittest.main()
