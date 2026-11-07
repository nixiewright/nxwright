"""The while statement (tft/instructions/while_statement.py): its blocks,
against the fixtures its probes kept (tools/tft/probing/while_probes.py), its jumps,
what it refuses, and the lines its rule covers.

Each test gives the encoder its own input: lines, where they lie, and a
Project of the facts the encoder reads, a probe's page and program.s made
in memory (tests/tft/unit_inputs.py).
"""
import struct
import unittest

from nxwright.tft.compile_context import CompileContext
from tools.tft.probing import while_probes
from nxwright.tft.instructions import while_statement
from nxwright.tft.matching import matched_rules, project_needs, unmatched
from tools.tft.probing.statement_probes import kept_blocks
from nxwright.tft.statements import CodePlace, StatementError, encode_code
from tests.tft.unit_inputs import piece, piece_names, probe_project, project_of


def jump(block: bytes) -> int:
    return struct.unpack("<i", block[-4:])[0]


class FixturesTest(unittest.TestCase):
    """Each probe's blocks, as the encoder gives them now on its page and
    program.s made in memory, are the pieces the probe kept once they
    matched the Nextion Editor's."""

    def test_each_probe(self):
        probes = [probe for probe in while_probes.PROBES if probe.fixtures]
        self.assertEqual(len(probes), 5)
        for probe in probes:
            with self.subTest(probe=probe.name):
                self.assertEqual(kept_blocks(probe, probe_project(probe)),
                                 {name: piece(probe, name) for name in piece_names(probe)})


class JumpTest(unittest.TestCase):
    """The jump back to the condition, and jumps that land on it."""

    @classmethod
    def setUpClass(cls):
        cls.project = project_of(strict=True)

    def encoded(self, lines: list) -> list:
        return encode_code(lines, CodePlace(), CompileContext(self.project))

    def test_the_body_ends_with_a_jump_back(self):
        # The comparison, 22 bytes with its size word, then sys0++ and the
        # jump, 11 each.
        blocks = self.encoded(["while(sys0<3)", "{", "sys0++", "}"])
        self.assertEqual(jump(blocks[0]), 22)
        self.assertEqual(blocks[2], b"T \x03" + struct.pack("<i", -44))

    def test_an_if_ending_the_body_jumps_back_to_the_condition(self):
        # The if's comparison would land on the jump back. It jumps back
        # itself, to the while's comparison, 44 bytes before its own end.
        blocks = self.encoded(["while(sys0<5)", "{", "if(sys1==2)", "{", "sys1=3", "}", "}"])
        self.assertEqual(jump(blocks[1]), -44)
        self.assertEqual(jump(blocks[3]), -66)

    def test_a_while_ending_a_body_before_an_else(self):
        # The while's comparison would land on the if's jump past the else.
        # It jumps past the else itself: past sys1++, the jump back, the
        # if's jump, and sys2=1, 11 bytes each.
        blocks = self.encoded(["if(sys0==1)", "{", "while(sys1<3)", "{", "sys1++", "}", "}else",
                               "{", "sys2=1", "}"])
        self.assertEqual(jump(blocks[1]), 44)


class RefusedTest(unittest.TestCase):
    """The statements the encoder refuses, each with a StatementError."""

    @classmethod
    def setUpClass(cls):
        cls.project = project_of()

    def assertRefused(self, lines: list, message: str):
        with self.assertRaisesRegex(StatementError, message):
            encode_code(lines, CodePlace(), CompileContext(self.project))

    def test_a_brace_not_on_its_own_line(self):
        self.assertRefused(["while(sys0<1)"], "no {")
        self.assertRefused(["while(sys0<1)", "sys0++"], "no {")
        self.assertRefused(["while(sys0<1)", "{", "sys0++"], "no } to close it")

    def test_a_branch_after_its_body(self):
        for closing in ("}else", "}else if(sys0==2)"):
            with self.subTest(closing=closing):
                self.assertRefused(["while(sys0<1)", "{", closing, "{", "}"],
                                   "a while's body ends with }")

    def test_a_condition_it_does_not_encode(self):
        self.assertRefused(["while(sys0<1&&sys1<2||sys2<3)", "{", "}"], "both && and \\|\\|")
        for condition in ("sys0", "sys0=1", "sys 0<1"):
            with self.subTest(condition=condition):
                self.assertRefused(["while(%s)" % condition, "{", "}"], "no comparison")
        self.assertRefused(["while(nothing<1)", "{", "}"], "no variable")
        self.assertRefused(["while(t0.val<1)", "{", "}"], "attribute in program.s")


class SeriesTest(unittest.TestCase):

    def test_on_f_as_on_t(self):
        # F writes a while as T does (ResearchNotes/tft/f-series.md).
        lines = ["while(sys0<1)", "{", "sys0++", "}"]
        project = project_of()
        self.assertEqual(encode_code(lines, CodePlace(), CompileContext(project_of(series="F"))),
                         encode_code(lines, CodePlace(), CompileContext(project)))


class RuleTest(unittest.TestCase):
    """The lines while_statement.MATCHED covers, and a project whose code
    holds while statements, which the check of what nxwright matched lets
    through."""

    def test_covered(self):
        for line in ("while(sys0<3)", "while ( sys0 < 3 )", "{", " } ",
                     "while(sys0<1||sys1>2||sys2<=3)", "while(-5<sys0&&a!=RED)"):
            with self.subTest(line=line):
                self.assertTrue(while_statement.covers(line))

    def test_left(self):
        for line in ("while(sys0<1&&sys1<2||sys2<3)",
                     "while(t0.val<1)", "while(sys0<1){", "while(sys0)", "while sys0<1",
                     "}else"):
            with self.subTest(line=line):
                self.assertFalse(while_statement.covers(line))

    def test_starts(self):
        for line, starts in (("while(sys0<1)", True), (" while ( sys0 < 1 ) ", True),
                             ("whiles=1", False), ("// while(sys0<1)", False)):
            with self.subTest(line=line):
                self.assertEqual(while_statement.starts_statement(line), starts)

    def test_a_project_with_while_statements(self):
        for probe in (probe for probe in while_probes.PROBES
                      if probe.name in ("while-nested", "while-event")):
            with self.subTest(probe=probe.name):
                project = probe_project(probe)
                self.assertEqual(unmatched(project_needs(project), matched_rules()), [])


if __name__ == "__main__":
    unittest.main()
