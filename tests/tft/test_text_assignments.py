"""Texts in code (tft/statements.py): the encoder's blocks for the probes
that keep fixtures, and the lines setting a txt that the rule covers and
leaves out.

The fixtures are the blocks of page0's Touch Release event, as the statement
encoder gave them once each probe matched the Nextion Editor's file
(tools/tft/probing/text_assignment_probes.py).

Each test gives the encoder its own input: a probe's page and program.s,
made in memory from what the probe adds, in a Project of the facts the
encoder reads (tests/tft/unit_inputs.py).
"""
import unittest

from nxwright.tft.compile_context import CompileContext
from tools.tft.probing import text_assignment_probes
from nxwright.tft.matching import Need, matched_rules, project_needs, unmatched
from tools.tft.probing.number_probes import number_component
from tools.tft.probing.statement_probes import kept_blocks
from nxwright.tft.statements import MATCHED, CodePlace, encode_line
from tools.tft.probing.text_probes import text_component
from tests.tft.line_context import line_context
from tests.tft.unit_inputs import piece, piece_names, probe_project


class FixtureTest(unittest.TestCase):
    """The encoder's blocks for each probe that keeps fixtures, on its page
    and program.s made in memory, against the probe's pieces."""

    def test_each_part(self):
        probes = [probe for probe in text_assignment_probes.PROBES if probe.fixtures is not None]
        self.assertEqual(len(probes), 5)
        for probe in probes:
            with self.subTest(probe.name):
                self.assertEqual(kept_blocks(probe, probe_project(probe)),
                                 {each: piece(probe, each) for each in piece_names(probe)})

    def test_a_join(self):
        # t0 and t1 are page0's first two texts, their txt's entries 61 and
        # 102: each operand as the encoder gives it, the `+` and the text as
        # written.
        project = probe_project(next(probe for probe in text_assignment_probes.PROBES
                                     if probe.name == "text-joined"))
        self.assertEqual(encode_line('t0.txt=t1.txt+"a"', CodePlace(0, "page0", "up"),
                                     CompileContext(project)),
                         b"\x01\x3d\x00\x00\x00=\x01\x66\x00\x00\x00+\"a\"")


class MatchedTest(unittest.TestCase):
    """The lines setting a txt that MATCHED covers, on a page of the texts t0
    and t1 and the number n0."""

    @classmethod
    def setUpClass(cls):
        cls.context = line_context(text_component(), text_component("t1", y=60),
                                   number_component(y=110))

    def needs(self, lines) -> list:
        return [Need("code", "event", line, context=self.context) for line in lines]

    def test_what_it_covers(self):
        covered = self.needs([
            "t0.txt=t1.txt", 't0.txt=t1.txt+"a"', 't0.txt="a"+t1.txt+"b"', 't0.txt+="a"',
            "t0.txt+=t1.txt", "t0.txt-=1", 't0.txt = t1.txt + "a b"',
            't0.txt="Hello, world!"', 't0.txt="%s"' % ("a" * 100)])
        self.assertEqual(unmatched(covered, MATCHED), [])

    def test_joins_added_and_operands_cut(self):
        # As the probe text-added-to-joined-and-cut-by-operands showed: += with
        # texts and txts joined, and -= by a variable, a system variable, a
        # val, a hexadecimal number, and a colour's name.
        covered = self.needs([
            't0.txt+="a"+"b"', 't0.txt+="a"+t1.txt+"c"', "t0.txt-=sys0", "t0.txt-=dim",
            "t0.txt-=n0.val", "t0.txt-=0x01", "t1.txt-=RED", "t0.txt-=-1"])
        self.assertEqual(unmatched(covered, MATCHED), [])

    def test_what_it_leaves_out(self):
        # A number's val in a txt, a txt in a number, += with a number
        # joined, -= with a txt or an expression, or with a negative number,
        # which makes no sense as a count of characters to remove, an
        # operator other than +, a txt of no component of the page, and an
        # escape the screen does not read.
        left = self.needs([
            "t0.txt=n0.val", "n0.val=t0.txt", 't0.txt+="a"+n0.val', "t0.txt-=t1.txt",
            "t0.txt-=sys0+1", 't0.txt=t1.txt-"a"', "t0.txt=t9.txt",
            't0.txt="a\\nb"'])
        self.assertEqual(unmatched(left, MATCHED), left)

    def test_the_check_takes_every_probe(self):
        for probe in text_assignment_probes.PROBES:
            with self.subTest(probe=probe.name):
                project = probe_project(probe)
                self.assertEqual(unmatched(project_needs(project), matched_rules()), [])


if __name__ == "__main__":
    unittest.main()
