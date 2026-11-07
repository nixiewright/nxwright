"""Components' attributes in code: their blocks, against the fixtures the
probes kept (tools/tft/probing/attribute_probes.py); which attributes the check of what
nxwright matched lets through (statements.attribute_kind), in lines and in
control statements; and what the check refuses up front.

Each test gives the function it checks a Project of the facts of a page and
program.s made in memory, as the probes' changes make them
(tests/tft/unit_inputs.py). One probe is compared whole, as the family's sample,
in tests/tft/test_whole_files.py.
"""
import unittest

from nxwright.tft.compile_context import CompileContext
from tools.tft.probing import attribute_probes
from nxwright.tft.instructions import for_statement, if_statement, while_statement
from nxwright.tft.matching import Need, matched_rules, project_needs, unmatched
from tools.tft.probing.probe_runner import Probe
from tools.tft.probing.statement_probes import kept_blocks
from nxwright.tft.statements import MATCHED, CodePlace, attribute_kind, encode_code, encode_line
from tests.tft.unit_inputs import piece, piece_names, probe_project


def facts(change):
    """Returns a Project of the facts of the T base folder's page0 and
    program.s, with `change`, an attribute_probes.AttributesChange, made in
    memory, as the match check reads it (unit_inputs.probe_project)."""
    return probe_project(Probe("test", "T", change, None, None))


class PiecesTest(unittest.TestCase):
    """The blocks the encoder gives each probe's lines, on its page and
    program.s made in memory, in strict Nextion syntax, against the probe's
    pieces: page0's Touch Release event's, or program.s's for a probe that
    keeps those (statement_probes.kept_blocks). Attributes in lines and in
    control statements."""

    PROBES = attribute_probes.PROBES

    def test_each_probe(self):
        self.assertEqual(len(self.PROBES), 6)
        for probe in self.PROBES:
            with self.subTest(probe.name):
                self.assertEqual(kept_blocks(probe, probe_project(probe)),
                                 {name: piece(probe, name) for name in piece_names(probe)})


class CheckTest(unittest.TestCase):
    """The check's needs of a page with a text t0 and numbers n0 and n1, and
    the lines of code its rules cover there."""

    @classmethod
    def setUpClass(cls):
        cls.project = facts(attribute_probes.with_attributes(["n0.val=5"]))
        needs = project_needs(cls.project)
        cls.event = next(need for need in needs
                         if need.kind == "code" and need.subject == "event")
        cls.program = next(need for need in needs
                           if need.kind == "code" and need.subject == "program.s")

    def need(self, line: str, subject: str = "event") -> Need:
        """A need of `line`, in page0's event, or in program.s."""
        found = self.event if subject == "event" else self.program
        return Need("code", subject, line, found.where, found.context, series=found.series)

    def test_the_kind_of_an_attribute(self):
        # Any attribute a type writes, a txt as a text and the others as
        # numbers; none it does not write, as a number's pw; and a page's own
        # attribute whose entry nxwright knows, as a number, its effect among
        # them, but none it has no entry of, as a txt.
        for attribute, kind in (("n0.val", "number"), ("n1.val", "number"), ("t0.txt", "text"),
                                ("t0.bco", "number"), ("n0.x", "number"),
                                ("t0.txt_maxl", "number"), ("n0.txt", None), ("n0.pw", None),
                                ("n9.val", None), ("page0.bco", "number"),
                                ("page0.effect", "number"), ("page0.txt", None)):
            with self.subTest(attribute=attribute):
                self.assertEqual(attribute_kind(self.event, attribute), kind)
        self.assertIsNone(attribute_kind(self.program, "n0.val"))

    def test_lines(self):
        rule, = MATCHED
        for line in ("n0.val=5", "sys0=n0.val+1", "n0.val++", "n1.val+=n0.val", 't0.txt="Yo"',
                     "n0.bco=5", "sys0=n0.x+t0.pco", "t0.bco++"):
            with self.subTest(line=line):
                self.assertTrue(rule.matches(self.need(line)))
        # An attribute code cannot change, on any series or on T, set; and
        # one the type does not write.
        for line in ('n0.txt="Yo"', 'page0.txt="Yo"', "sys0=t0.txt", "t0.txt=n0.val",
                     "n0.id=1", "n0.x=5", "t0.aph++", "n0.pw=1", "sys0=n0.pw", "n9.val=1",
                     'n0.val="a"'):
            with self.subTest(line=line):
                self.assertFalse(rule.matches(self.need(line)))
        self.assertFalse(rule.matches(self.need("n0.val=1", "program.s")))

    def test_control_statements(self):
        for module, line in ((if_statement, "if(n0.val==1)"),
                             (if_statement, "}else if(sys0<n1.val&&n0.val!=3)"),
                             (while_statement, "while(n0.val<3)"),
                             (while_statement, "while(n0.bco<t0.pco)"),
                             (for_statement, "for(n1.val=0;n1.val<n0.val;n1.val++)"),
                             (for_statement, "for(n0.font=0;n0.font<n0.x;n0.font++)"),
                             (for_statement, 'for(t0.txt="";sys0<3;sys0++)')):
            with self.subTest(line=line):
                self.assertTrue(module.covers(line, self.need(line)))
                # Without the line's need, no attribute is known.
                self.assertFalse(module.covers(line))
        for module, line in ((if_statement, "if(t0.txt==1)"), (if_statement, "if(n9.val==1)"),
                             (while_statement, "while(n0.pw<3)"),
                             (for_statement, "for(t0.txt=0;sys0<3;sys0++)"),
                             (for_statement, "for(n0.x=0;sys0<3;sys0++)"),
                             (for_statement, "for(sys0=0;sys0<3;n0.y++)"),
                             (for_statement, "for(sys0=0;sys0<3;n0.txt++)"),
                             (for_statement, 'for(sys0="a";sys0<3;sys0++)')):
            with self.subTest(line=line):
                self.assertFalse(module.covers(line, self.need(line)))

    def test_a_for_whose_start_sets_a_txt(self):
        # Its start is written as the same line alone.
        place = CodePlace(0, "page0", "up")
        blocks = encode_code(['for(t0.txt="";sys0<3;sys0++)', "{", "}"], place,
                             CompileContext(self.project))
        self.assertEqual(blocks[0], encode_line('t0.txt=""', place, CompileContext(self.project)))

    def test_projects(self):
        for probe in attribute_probes.PROBES:
            with self.subTest(probe=probe.name):
                self.assertEqual(unmatched(project_needs(probe_project(probe)), matched_rules()),
                                 [])

    def test_a_txt_on_another_type_is_listed(self):
        # nxwright's build refuses these lines, as the Nextion Editor refuses
        # to compile them, so they are put in after it, as a project file
        # nxwright did not write may hold them. The encoder refuses them too,
        # but the check now lists them first.
        from nxwright.project.page_block import Event
        project = facts(attribute_probes.with_attributes(["n0.val=5"]))
        event = next(item for item in project.pages[0].objects[0].items
                     if isinstance(item, Event) and item.name == "up")
        event.lines = [b'n0.txt="Yo"', b'page0.txt="Yo"']
        left = unmatched(project_needs(project), matched_rules())
        self.assertEqual([need.value for need in left], ['n0.txt="Yo"', 'page0.txt="Yo"'])


if __name__ == "__main__":
    unittest.main()
