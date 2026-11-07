"""Code that names a global component of another page by that page's name,
as `page1.va0.val` (tft/statements.py): the blocks the probes of
other_page_probes.py kept once they matched the Nextion Editor's file, the
bytes of each form as the Nextion Editor wrote them, what the encoder
refuses, and what the check covers.

Each test gives the function it checks its own input: a probe's pages and
program.s made in memory from what the probe adds, in a Project of the
facts it reads (tests/tft/unit_inputs.py).
"""
from dataclasses import replace
import unittest

from nxwright.tft.compile_context import CompileContext
from tools.tft.probing import other_page_probes
from nxwright.tft.instructions import for_statement, if_statement
from nxwright.tft.matching import matched_rules, project_needs, unmatched
from tools.tft.probing.statement_probes import kept_blocks
from nxwright.tft.statements import MATCHED, CodePlace, StatementError, encode_line
from tests.tft.unit_inputs import piece, piece_names, probe_project

_PROBE = other_page_probes.PROBES[0]
_UP = CodePlace(0, "t0", "up")


class FixtureTest(unittest.TestCase):
    """The encoder's blocks for each probe, on its pages and program.s made
    in memory, against the probe's pieces."""

    def test_each_probe_s_fixtures(self):
        self.assertEqual(len(other_page_probes.PROBES), 4)
        for probe in other_page_probes.PROBES:
            with self.subTest(probe.name):
                self.assertEqual(kept_blocks(probe, probe_project(probe)),
                                 {name: piece(probe, name) for name in piece_names(probe)})


class EncodingTest(unittest.TestCase):
    """The component's entry, counted across the project, as the Nextion
    Editor wrote it: page1's va0's val is entry 0x73, n0's val 0x91, and
    va1's txt 0xd0."""

    @classmethod
    def setUpClass(cls):
        cls.project = probe_project(_PROBE)

    def block(self, line: str, place: CodePlace = _UP) -> str:
        return encode_line(line, place, CompileContext(self.project)).hex(" ")

    def test_its_entry(self):
        self.assertEqual(self.block("page1.va0.val=5"), "01 73 00 00 00 3d 35")
        self.assertEqual(self.block("sys0=page1.n0.val"), "05 00 00 00 00 3d 01 91 00 00 00")
        self.assertEqual(self.block('page1.va1.txt="a"'), "01 d0 00 00 00 3d 22 61 22")
        # In program.s too, and the line's own page named is the same as none.
        self.assertEqual(self.block("page1.va0.val=5", CodePlace()), "01 73 00 00 00 3d 35")
        self.assertEqual(self.block('page0.t0.txt="a"'), self.block('t0.txt="a"'))
        self.assertEqual(self.block("cls page1.n0.val"), "09 06 04 01 91 00 00 00")

    def test_what_it_refuses(self):
        # A local component of another page, as the Nextion Editor refuses
        # it; a page the project has not; and a component without its page
        # in program.s.
        for line, place in (('page1.t1.txt="a"', _UP), ("page9.n0.val=1", _UP),
                            ("n0.val=1", CodePlace())):
            with self.subTest(line), self.assertRaises(StatementError):
                self.block(line, place)


class CoveredTest(unittest.TestCase):
    """What the check covers, with the probe's pages."""

    @classmethod
    def setUpClass(cls):
        cls.project = probe_project(_PROBE)
        cls.needs = {(need.subject, need.value): need for need in project_needs(cls.project)
                     if need.kind == "code"}

    def need(self, line: str, subject: str = "event"):
        template = next(need for (kind, _), need in self.needs.items() if kind == subject)
        return replace(template, value=line)

    def covered(self, need) -> bool:
        rules = MATCHED + if_statement.MATCHED + for_statement.MATCHED
        return any(rule.covers(need) for rule in rules)

    def test_the_probe_s_lines(self):
        self.assertEqual(unmatched(project_needs(self.project), matched_rules()), [])

    def test_what_it_covers(self):
        for line in ("page1.va0.val=5", 't0.txt=page1.va1.txt+"b"', "page1.n0.val*=2",
                     "if(page1.n0.val==1)", "for(page1.n0.val=0;page1.n0.val<3;page1.n0.val++)"):
            with self.subTest(line):
                self.assertTrue(self.covered(self.need(line)))
        self.assertTrue(self.covered(self.need("sys0=page1.n0.val", "program.s")))

    def test_what_it_leaves_out(self):
        # A local component of another page; a page the project has not; an
        # attribute code cannot change on T; a txt given a number; and a
        # component without its page in program.s.
        for line in ('page1.t1.txt="a"', "page9.n0.val=1", "page1.n0.x=5",
                     "page1.va1.txt=page1.n0.val"):
            with self.subTest(line):
                self.assertFalse(self.covered(self.need(line)))
        self.assertFalse(self.covered(self.need("sys0=t0.txt_maxl", "program.s")))

    def test_in_commands(self):
        # As an operand of each family's commands, in an event and in
        # program.s; but not as a command's component, which the Nextion
        # Editor refused ("Invalid Component ID").
        rules = matched_rules()
        for line, subject in (("get page1.n0.val", "event"), ("prints page1.va1.txt,0", "event"),
                              ("pa_q page1.va1.txt,page1.n0.val", "event"),
                              ("page page1.n0.val+1", "event"),
                              ("fstr page1.va1.txt,page1.n0.val,0", "event"),
                              ("cls page1.n0.val", "program.s")):
            with self.subTest(line):
                self.assertEqual(unmatched([self.need(line, subject)], rules), [])
        need = self.need("vis page1.n0,0")
        self.assertEqual(unmatched([need], rules), [need])


if __name__ == "__main__":
    unittest.main()
