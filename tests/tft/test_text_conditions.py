"""Conditions that compare texts (tft/control_statements.py): the
encoder's blocks for the probes that keep fixtures, the comparisons the
encoder refuses, and the conditions the rules cover and leave out.

The fixtures are the blocks of page0's Touch Release event, as the statement
encoder gave them once each probe matched the Nextion Editor's file
(tools/tft/probing/text_condition_probes.py).

Each test gives the encoder its own input: a probe's page and program.s,
made in memory from what the probe adds, in a Project of the facts the
encoder reads (tests/tft/unit_inputs.py).
"""
import unittest

from nxwright.tft.compile_context import CompileContext
from tools.tft.probing import text_condition_probes
from nxwright.tft.control_statements import condition_blocks, covers_condition
from nxwright.tft.matching import Need, matched_rules, project_needs, unmatched
from tools.tft.probing.number_probes import number_component
from tools.tft.probing.statement_probes import kept_blocks
from nxwright.tft.statements import CodePlace, StatementError
from tools.tft.probing.text_probes import text_component
from tests.tft.line_context import line_context
from tests.tft.unit_inputs import piece, piece_names, probe_project


class FixtureTest(unittest.TestCase):
    """The encoder's blocks for each probe that keeps fixtures, on its page
    and program.s made in memory, against the probe's pieces."""

    def test_each_part(self):
        probes = [probe for probe in text_condition_probes.PROBES if probe.fixtures is not None]
        self.assertEqual(len(probes), 8)
        for probe in probes:
            with self.subTest(probe.name):
                self.assertEqual(kept_blocks(probe, probe_project(probe)),
                                 {each: piece(probe, each) for each in piece_names(probe)})


class EncodeTest(unittest.TestCase):
    """A comparison of texts, and those the encoder refuses."""

    @classmethod
    def setUpClass(cls):
        cls.project = probe_project(next(probe for probe in text_condition_probes.PROBES
                                         if probe.name == "text-conditions-in-if"))

    def test_a_txt_beside_a_text(self):
        # A number's comparison block: t0's txt, entry 61, the text as
        # written, == (1), then a jump past 11 bytes.
        block, = condition_blocks('t0.txt=="ab"', 11, CodePlace(0, "page0", "up"),
                                  CompileContext(self.project),
                                  "T")
        self.assertEqual(block, b"\x09\x00\x04\x01\x3d\x00\x00\x00,\"ab\",1,\x03\x0b\x00\x00\x00")

    def test_a_text_beside_a_number_is_refused(self):
        # The Nextion Editor refuses each: "Variable type does not match".
        for condition in ('sys0=="a"', '"a"!=5', '"a"<dim'):
            with self.subTest(condition=condition):
                with self.assertRaisesRegex(StatementError, "of one kind"):
                    condition_blocks(condition, 0, CodePlace(0, "page0", "up"),
                                     CompileContext(self.project),
                                     "T")


class CoveredTest(unittest.TestCase):
    """The conditions covers_condition takes, on a page of the texts t0 and
    t1 and the number n0."""

    @classmethod
    def setUpClass(cls):
        context = line_context(text_component(), text_component("t1", y=60),
                               number_component(y=110))
        cls.need = Need("code", "event", "", context=context)

    def test_what_it_covers(self):
        for condition in ('t0.txt=="ab"', "t0.txt!=t1.txt", '"a"<t1.txt', '"a"=="b"',
                          't0.txt==")"', 't0.txt==""', 't0.txt=="%s"' % ("a" * 300),
                          't0.txt=="a"&&n0.val==1', 't0.txt=="a"||t1.txt=="b"', "n0.val==1"):
            with self.subTest(condition=condition):
                self.assertTrue(covers_condition(condition, self.need))

    def test_what_it_leaves_out(self):
        # A txt beside a number or a val, a txt of no text of the page, a
        # text with an escape the screen does not read, and a txt in
        # program.s, which has no page.
        for condition in ("t0.txt==n0.val", "t0.txt==1", 't9.txt=="a"', 't0.txt=="a"&&',
                          't0.txt=="a\\b"'):
            with self.subTest(condition=condition):
                self.assertFalse(covers_condition(condition, self.need))
        self.assertFalse(covers_condition('t0.txt=="a"', None))

    def test_the_check_takes_every_probe(self):
        for probe in text_condition_probes.PROBES:
            with self.subTest(probe=probe.name):
                project = probe_project(probe)
                self.assertEqual(unmatched(project_needs(project), matched_rules()), [])


if __name__ == "__main__":
    unittest.main()
