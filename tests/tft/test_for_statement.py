"""The for statement (tft/instructions/for_statement.py): its blocks,
against the fixtures its probes kept (tools/tft/probing/for_probes.py), its jumps, what
it refuses, and the lines its rule covers.

Each test gives the encoder its own input: lines, where they lie, and a
Project of the facts the encoder reads, a probe's page and program.s made
in memory (tests/tft/unit_inputs.py).
"""
import struct
import unittest

from nxwright.tft.compile_context import CompileContext
from tools.tft.probing import for_probes
from nxwright.tft.instructions import for_statement
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
        probes = [probe for probe in for_probes.PROBES if probe.fixtures]
        self.assertEqual(len(probes), 5)
        for probe in probes:
            with self.subTest(probe=probe.name):
                self.assertEqual(kept_blocks(probe, probe_project(probe)),
                                 {name: piece(probe, name) for name in piece_names(probe)})


class JumpTest(unittest.TestCase):
    """The start before the loop, the step at the end of its body, and the
    jump back to the condition."""

    @classmethod
    def setUpClass(cls):
        cls.project = project_of(strict=True)

    def encoded(self, lines: list) -> list:
        return encode_code(lines, CodePlace(), CompileContext(self.project))

    def test_the_jump_back_goes_to_the_condition(self):
        # sys0=0, then the comparison, which skips sys1++, sys0++, and the
        # jump back, 11 bytes each with their size words. The jump back goes
        # over all but sys0=0.
        blocks = self.encoded(["for(sys0=0;sys0<3;sys0++)", "{", "sys1++", "}"])
        self.assertEqual(blocks[0], self.encoded(["sys0=0"])[0])
        self.assertEqual(jump(blocks[1]), 33)
        self.assertEqual(blocks[3], self.encoded(["sys0++"])[0])
        self.assertEqual(blocks[4], b"T \x03" + struct.pack("<i", -55))

    def test_an_if_ending_the_body_lands_on_the_step(self):
        # The step follows the body, not a jump block, so the if's comparison
        # skips sys1=3 alone.
        blocks = self.encoded(["for(sys0=0;sys0<5;sys0++)", "{", "if(sys1==2)", "{", "sys1=3",
                               "}", "}"])
        self.assertEqual(jump(blocks[2]), 11)

    def test_a_for_ending_a_body_before_an_else(self):
        # The for's comparison would land on the if's jump past the else. It
        # jumps past the else itself: past sys2++, sys1++, the jump back, the
        # if's jump, and sys2=1, 11 bytes each.
        blocks = self.encoded(["if(sys0==1)", "{", "for(sys1=0;sys1<3;sys1++)", "{", "sys2++",
                               "}", "}else", "{", "sys2=1", "}"])
        self.assertEqual(jump(blocks[2]), 55)


class RefusedTest(unittest.TestCase):
    """The statements the encoder refuses, each with a StatementError."""

    @classmethod
    def setUpClass(cls):
        cls.project = project_of()

    def assertRefused(self, head: str, message: str, rest=("{", "}")):
        with self.assertRaisesRegex(StatementError, message):
            encode_code([head, *rest], CodePlace(), CompileContext(self.project))

    def test_an_empty_start_or_step(self):
        # The Nextion Editor says "SYNTAX ERROR" for both.
        for head in ("for(;sys0<3;sys0++)", "for(sys0=0;sys0<3;)", "for( ;sys0<3;sys0++)"):
            with self.subTest(head=head):
                self.assertRefused(head, "empty")

    def test_a_head_of_another_shape(self):
        for head in ("for(sys0=0;sys0<3)", "for(sys0=0;sys0<3;sys0++;sys1++)"):
            with self.subTest(head=head):
                self.assertRefused(head, "no for of a start, a condition, and a step")

    def test_a_start_or_step_that_is_no_assignment(self):
        # A start that sets a number to a text is an assignment to the
        # encoder, which the rule refuses (tests/tft/test_attributes_in_code.py).
        for head in ("for(cls RED;sys0<3;sys0++)", "for(int a=1;sys0<3;sys0++)",
                     "for(sys0=0;sys0<3;sys0==1)"):
            with self.subTest(head=head):
                self.assertRefused(head, "no assignment")

    def test_an_attribute_in_program_s(self):
        self.assertRefused("for(sys0=0;sys0<3;t0.val++)", "attribute in program.s")

    def test_a_brace_not_on_its_own_line(self):
        self.assertRefused("for(sys0=0;sys0<3;sys0++)", "no {", rest=())
        self.assertRefused("for(sys0=0;sys0<3;sys0++)", "no } to close it", rest=("{",))

    def test_a_branch_after_its_body(self):
        self.assertRefused("for(sys0=0;sys0<3;sys0++)", "a for's body ends with }",
                           rest=("{", "}else", "{", "}"))

    def test_a_condition_it_does_not_encode(self):
        self.assertRefused("for(sys0=0;sys0<1&&sys1<2||sys2<3;sys0++)", "both && and \\|\\|")
        self.assertRefused("for(sys0=0;sys0;sys0++)", "no comparison")


class SeriesTest(unittest.TestCase):

    def test_on_f_as_on_t(self):
        # F writes a for as T does (ResearchNotes/tft/f-series.md).
        lines = ["for(sys0=0;sys0<3;sys0++)", "{", "sys1+=sys0", "}"]
        project = project_of()
        self.assertEqual(encode_code(lines, CodePlace(), CompileContext(project_of(series="F"))),
                         encode_code(lines, CodePlace(), CompileContext(project)))


class RuleTest(unittest.TestCase):
    """The lines for_statement.MATCHED covers, and a project whose code
    holds for statements, which the check of what nxwright matched lets
    through."""

    def test_covered(self):
        for line in ("for(sys0=0;sys0<3;sys0++)", "for ( sys0 = 0 ; sys0 < 3 ; sys0 ++ )", "{",
                     " } ", "for(sys0=sys1+1;sys0<=1000;sys0+=sys1)", "for(a=-1000;a!=RED;a-=1)",
                     "for(dim=0;dim<1||sys1>2||sys2<=3;dim--)"):
            with self.subTest(line=line):
                self.assertTrue(for_statement.covers(line))

    def test_left(self):
        for line in ("for(;sys0<3;sys0++)", "for(sys0=0;sys0<3;)", "for(sys0=0;sys0<3)",
                     "for(cls RED;sys0<3;sys0++)", "for(sys0=t0.val;sys0<3;sys0++)",
                     'for(sys0="a";sys0<3;sys0++)', "for(sys0=0;sys0<3;sys0++){",
                     "}else"):
            with self.subTest(line=line):
                self.assertFalse(for_statement.covers(line))

    def test_a_long_start(self):
        # A start of 767 characters, the most T takes, and one past it.
        # nxwright's build refuses a start longer than its series takes.
        self.assertEqual(len(for_probes.LONGEST_START), 767)
        for start in (for_probes.LONGEST_START, for_probes.LONGEST_START + "1"):
            with self.subTest(size=len(start)):
                self.assertTrue(for_statement.covers("for(%s;sys0<10;sys0++)" % start))

    def test_starts(self):
        for line, starts in (("for(sys0=0;sys0<3;sys0++)", True),
                             (" for ( sys0 = 0 ; sys0 < 3 ; sys0 ++ ) ", True),
                             ("for(sys0=0;sys0<3)", True), ("fors=1", False),
                             ("// for(sys0=0;sys0<3;sys0++)", False)):
            with self.subTest(line=line):
                self.assertEqual(for_statement.starts_statement(line), starts)

    def test_a_project_with_for_statements(self):
        for probe in (probe for probe in for_probes.PROBES
                      if probe.name in ("for-nested", "for-event")):
            with self.subTest(probe=probe.name):
                project = probe_project(probe)
                self.assertEqual(unmatched(project_needs(project), matched_rules()), [])


if __name__ == "__main__":
    unittest.main()
