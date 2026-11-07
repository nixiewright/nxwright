"""The if statement (tft/instructions/if_statement.py): its blocks,
against the fixtures its probes kept (tools/tft/probing/if_probes.py), what it refuses,
and the lines its rule covers.

Each test gives the encoder its own input: lines, where they lie, and a
Project of the facts the encoder reads, a probe's page and program.s made
in memory (tests/tft/unit_inputs.py).
"""
import struct
import unittest

from nxwright.tft.compile_context import CompileContext
from tools.tft.probing import if_probes
from nxwright.tft.instructions import if_statement
from nxwright.tft.matching import Need, matched_rules, project_needs, unmatched
from tools.tft.probing.statement_probes import kept_blocks
from nxwright.tft.statements import CodePlace, StatementError, encode_code
from tests.tft.unit_inputs import piece, piece_names, probe_project, project_of


class FixturesTest(unittest.TestCase):
    """Each probe's blocks, as the encoder gives them now on its page and
    program.s made in memory, are the pieces the probe kept once they
    matched the Nextion Editor's."""

    def test_each_probe(self):
        probes = [probe for probe in if_probes.PROBES if probe.fixtures]
        self.assertEqual(len(probes), 11)
        for probe in probes:
            with self.subTest(probe=probe.name):
                self.assertEqual(kept_blocks(probe, probe_project(probe)),
                                 {name: piece(probe, name) for name in piece_names(probe)})


class RefusedTest(unittest.TestCase):
    """The statements the encoder refuses, each with a StatementError."""

    @classmethod
    def setUpClass(cls):
        cls.project = project_of()

    def assertRefused(self, lines: list, message: str, place=CodePlace()):
        with self.assertRaisesRegex(StatementError, message):
            encode_code(lines, place, CompileContext(self.project))

    def test_a_condition_with_both_and_and_or(self):
        self.assertRefused(["if(sys0==1&&sys1==2||sys2==3)", "{", "}"], "both && and \\|\\|")

    def test_a_condition_that_is_no_comparison(self):
        for condition in ("sys0", "sys0=1", "sys0==", "(sys0==1)", "sys0==1&&",
                          'sys0=="a"', "sys0+1==2", "sys 0==1", "sys0==1 0",
                          "sys0= =1", "sys0==1& &sys1==2"):
            with self.subTest(condition=condition):
                self.assertRefused(["if(%s)" % condition, "{", "}"], "no comparison")

    def test_an_attribute_in_program_s(self):
        self.assertRefused(["if(t0.val==1)", "{", "}"], "attribute in program.s")

    def test_an_operand_that_is_no_variable(self):
        self.assertRefused(["if(nothing==1)", "{", "}"], "no variable")

    def test_a_brace_not_on_its_own_line(self):
        self.assertRefused(["if(sys0==1)"], "no {")
        self.assertRefused(["if(sys0==1)", "sys1=2"], "no {")
        self.assertRefused(["if(sys0==1)", "{", "sys1=2"], "no } to close it")

    def test_a_branch_after_else(self):
        self.assertRefused(["if(sys0==1)", "{", "}else", "{", "}else if(sys0==2)", "{", "}"],
                           "follow an else")

    def test_a_closing_line_of_no_branch(self):
        self.assertRefused(["if(sys0==1)", "{", "}sys1=2"], "not a line of an if")


class SeriesTest(unittest.TestCase):

    def test_on_f_as_on_t(self):
        # F writes an if as T does (ResearchNotes/tft/f-series.md).
        lines = ["if(sys0==1)", "{", "sys1=2", "}else", "{", "sys1=3", "}"]
        project = project_of()
        self.assertEqual(encode_code(lines, CodePlace(), CompileContext(project_of(series="F"))),
                         encode_code(lines, CodePlace(), CompileContext(project)))


class RuleTest(unittest.TestCase):
    """The lines if_statement.MATCHED covers, and a project whose code holds
    if statements, which the check of what nxwright matched lets through."""

    def test_covered(self):
        for line in ("if(sys0==1)", "{", "}", "}else", "}else if(sys0>=2)",
                     "if(sys0==1&&sys1<2&&sys2!=3)", "if(sys0<1||sys1>2||dim<=3)",
                     "if(1==RED)", "if(sys0<-1000)", "if (sys0 == 1)", "} else if ( sys0 > 2 )",
                     "}\telse", " } "):
            with self.subTest(line=line):
                self.assertTrue(if_statement.covers(line))

    def test_left(self):
        # Both && and ||, and other shapes.
        for line in ("if(sys0==1&&sys1==2||sys2==3)",
                     "if(t0.val==1)", 'if(sys0=="a")', "if(sys0==1){", "}else{",
                     "else", "if(sys0)", "}elseif(sys0==1)", "if(sys 0==1)"):
            with self.subTest(line=line):
                self.assertFalse(if_statement.covers(line))

    def test_a_project_with_if_statements(self):
        for probe in (probe for probe in if_probes.PROBES if probe.name in ("if-or", "if-event")):
            with self.subTest(probe=probe.name):
                project = probe_project(probe)
                self.assertEqual(unmatched(project_needs(project), matched_rules()), [])

    def test_a_rule_for_lines_of_code(self):
        rule = if_statement.MATCHED[0]
        self.assertTrue(rule.matches(Need("code", "event", "}else")))
        self.assertFalse(rule.matches(Need("attribute", "text", "}else")))


class StartsTest(unittest.TestCase):
    """The lines that start an if, which the run's encoder hands to it."""

    def test_starts(self):
        for line, starts in (("if(sys0==1)", True), (" if (sys0 == 1) ", True),
                             ("if(nothing)", True), ("}else if(sys0==1)", False),
                             ("ifs=1", False), ("// if(sys0==1)", False)):
            with self.subTest(line=line):
                self.assertEqual(if_statement.starts_statement(line), starts)

    def test_a_jump_onto_a_jump_goes_where_that_one_goes(self):
        # The inner if ends the outer's first body, so its comparison would
        # land on the jump past the else. It jumps past the else instead:
        # sys2=1, that jump, and sys2=2, 11 bytes each with their size words.
        project = project_of(strict=True)
        lines = ["if(sys0==1)", "{", "if(sys1==2)", "{", "sys2=1", "}", "}else", "{",
                 "sys2=2", "}"]
        blocks = encode_code(lines, CodePlace(), CompileContext(project))
        self.assertEqual(blocks[1][-5:], b"\x03" + struct.pack("<I", 33))
        self.assertEqual(blocks[3], b"T \x03" + struct.pack("<I", 11))

    def test_lines_around_a_statement_keep_their_order(self):
        project = project_of(strict=True)
        lines = ["sys0=1", "if(sys0==1)", "{", "sys1=2", "}", "sys2=3"]
        blocks = encode_code(lines, CodePlace(), CompileContext(project))
        self.assertEqual(len(blocks), 4)
        self.assertEqual(blocks[0], encode_code(["sys0=1"], CodePlace(),
                                                CompileContext(project))[0])
        self.assertEqual(blocks[3], encode_code(["sys2=3"], CodePlace(),
                                                CompileContext(project))[0])


if __name__ == "__main__":
    unittest.main()
