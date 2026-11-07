"""Components' attributes in code other than those each type's probes
showed (tools/tft/probing/other_attribute_probes.py): the blocks the probes kept once
they matched the Nextion Editor's file, the check taking each probe's
project, and what it leaves out: an attribute set that code cannot change
on the line's series, and an attribute a type does not write.

The probes' blocks, and the check, are on each probe's page and program.s
made in memory (tests/tft/unit_inputs.py). One probe on T and one on P are
compared whole, as the family's samples, in tests/tft/test_whole_files.py.
"""
import re
import unittest

from tools.tft.probing import other_attribute_probes, p_probes
from nxwright.tft.matching import Need, matched_rules, project_needs, unmatched
from tools.tft.probing.number_probes import number_component
from tools.tft.probing.statement_probes import kept_blocks
from nxwright.tft.statements import operand_pattern
from tools.tft.probing.text_probes import text_component
from tools.tft.probing.xfloat_probes import xfloat_component
from tests.tft.line_context import line_context
from tests.tft.unit_inputs import piece, piece_names, probe_project


class PiecesTest(unittest.TestCase):
    """The blocks the encoder gives each probe's lines, on its page and
    program.s made in memory, in strict Nextion syntax, against the probe's
    pieces: page0's Touch Release event's, or program.s's for a probe that
    keeps those (statement_probes.kept_blocks). On T, every attribute of
    each type read and set, those of the variants read, attributes in
    conditions and in commands, and on K in its own commands; and on P,
    P's own probes of every attribute of a text, a number, and a button,
    read and set."""

    PROBES = (other_attribute_probes.PROBES
              + [probe for probe in p_probes.PROBES
                 if probe.name in ("p-attributes-read", "p-attributes-set")])

    def test_each_probe(self):
        self.assertEqual(len(self.PROBES), 8)
        for probe in self.PROBES:
            with self.subTest(probe.name):
                self.assertEqual(kept_blocks(probe, probe_project(probe)),
                                 {name: piece(probe, name) for name in piece_names(probe)})


class CheckTest(unittest.TestCase):
    """The check takes every line of the probes, and leaves out a line that
    sets what code cannot change, or names what a type does not write."""

    def test_each_probe_s_project(self):
        rules = matched_rules()
        for probe in other_attribute_probes.PROBES:
            with self.subTest(probe.name):
                self.assertEqual(unmatched(project_needs(probe_project(probe)), rules), [])

    def test_what_it_leaves_out(self):
        # On T and K, an attribute code cannot change on every series, as an
        # id, and one it cannot change on those series, as an x or a y, set;
        # an attribute a type does not write, as a number's pw; and an
        # xfloat's lenth, whose entry is its vvs0's.
        page = line_context(text_component(), number_component(y=60),
                            xfloat_component(y=110))
        rules = matched_rules()
        for series in ("T", "K"):
            for line in ("t0.id=1", "t0.x=1", "n0.y++", "for(n0.y=0;sys0<1;sys0++)",
                         "sys0=n0.pw", "cls n0.pw", "covx n0.pw,t0.txt,0,0", "sys0=x0.lenth"):
                with self.subTest(series=series, line=line):
                    need = Need("code", "event", line, context=page, series=series)
                    self.assertEqual(unmatched([need], rules), [need])
            # Read, an x, an id, and an xfloat's vvs0 are taken.
            need = Need("code", "event", "sys0=t0.x+n0.id+x0.vvs0", context=page, series=series)
            self.assertEqual(unmatched([need], rules), [])


class OperandPatternTest(unittest.TestCase):
    """A command's operand of the kind "number" is any attribute but a txt;
    one of the kind "text" is a txt."""

    def test_kinds(self):
        number = operand_pattern(("number",))
        either = operand_pattern(("number", "text"))
        for operand, as_number, as_either in (
                ("t0.bco", True, True), ("t0.txt_maxl", True, True), ("t0.txt", False, True),
                ("sys0", True, True), ("0x12", True, True), ("t0.", False, False)):
            with self.subTest(operand):
                self.assertEqual(re.fullmatch(number, operand) is not None, as_number)
                self.assertEqual(re.fullmatch(either, operand) is not None, as_either)


if __name__ == "__main__":
    unittest.main()
