"""Hexadecimal numbers in assignments and in the conditions of if, while,
and for (tft/statements.py and tft/control_statements.py): the blocks,
as the probes of hex_number_probes.py kept them once they matched the
Nextion Editor's file, and the lines refused.

Each test gives the function it checks a Project of the facts it reads:
a probe's page and program.s, or the base folder's, made in memory
(tests/tft/unit_inputs.py). One probe is compared whole, as the family's
sample, in tests/tft/test_whole_files.py.
"""
import unittest


from nxwright.tft.compile_context import CompileContext
from tools.tft.probing import hex_number_probes
from nxwright.tft.control_statements import condition_blocks, covers_condition
from nxwright.tft.matching import Need, matched_rules, project_needs, unmatched
from tools.tft.probing.number_probes import number_component
from tools.tft.probing.statement_probes import kept_blocks
from nxwright.tft.statements import CodePlace, encodable, encode_line
from tools.tft.probing.text_probes import text_component
from tests.tft.line_context import line_context
from tests.tft.unit_inputs import piece, piece_names, probe_project, project_of


class PiecesTest(unittest.TestCase):
    """The blocks the encoder gives each probe's lines, on its page and
    program.s made in memory, in strict Nextion syntax, against the probe's
    pieces: page0's Touch Release event's, or program.s's for a probe that
    keeps those (statement_probes.kept_blocks). In assignments, in the
    conditions of if, while, and for, and in program.s."""

    PROBES = [probe for probe in hex_number_probes.PROBES if probe.fixtures]

    def test_each_probe(self):
        self.assertEqual(len(self.PROBES), 3)
        for probe in self.PROBES:
            with self.subTest(probe.name):
                self.assertEqual(kept_blocks(probe, probe_project(probe)),
                                 {name: piece(probe, name) for name in piece_names(probe)})


class EncodeTest(unittest.TestCase):
    """A hexadecimal number is 03 and its value, 4 bytes, however small, as
    the Nextion Editor wrote it."""

    def test_in_assignments(self):
        place, project = CodePlace(), project_of()
        for line, block in (("sys0=0x12", b"\x05\x00\x00\x00\x00=\x03\x12\x00\x00\x00"),
                            ("sys0=0xFFFFFFFF", b"\x05\x00\x00\x00\x00=\x03\xff\xff\xff\xff"),
                            ("sys0+=0x10", b"\x05\x00\x00\x00\x00+=\x03\x10\x00\x00\x00"),
                            ("sys0=sys1+0x12",
                             b"\x05\x00\x00\x00\x00=\x05\x04\x00\x00\x00+\x03\x12\x00\x00\x00")):
            with self.subTest(line):
                self.assertEqual(encode_line(line, place, CompileContext(project)), block)

    def test_in_a_condition(self):
        # sys0, then 0x12, == (1), and a jump past 11 bytes.
        block, = condition_blocks("sys0==0x12", 11, CodePlace(), CompileContext(project_of()), "T")
        self.assertEqual(block, b"\x09\x00\x04\x05\x00\x00\x00\x00,\x03\x12\x00\x00\x00,1,"
                                b"\x03\x0b\x00\x00\x00")


class RefusedTest(unittest.TestCase):

    def test_lines_refused(self):
        # A sign, which nxwright's build refuses; and 5 bytes, which 4 cannot
        # hold, in an assignment and in a command (tests/tft/test_command_operands.py
        # gives the commands').
        for line in ("sys0=-0x01", "sys0=0x0100000000", "covx 0x0100000000,t0.txt,0,0"):
            with self.subTest(line):
                self.assertFalse(encodable(line))

    def test_beside_a_text(self):
        # A hexadecimal number is a number: the Nextion Editor refuses one
        # beside a txt ("Variable type does not match"), and nxwright's build
        # refuses one given to a txt. A txt cut by one is covered
        # (tests/tft/test_text_assignments.py).
        page = line_context(text_component(), number_component(y=60))
        need = Need("code", "event", "", context=page)
        self.assertFalse(covers_condition("t0.txt==0x12", need))
        line_need = Need("code", "event", "t0.txt=0x12", context=page)
        self.assertEqual(unmatched([line_need], matched_rules()), [line_need])


class MatchedTest(unittest.TestCase):

    def test_what_the_rules_cover(self):
        page = line_context(text_component(), number_component(y=60))
        rules = matched_rules()
        for line in ("sys0=0x12", "n0.val=0x12", "sys0=n0.val%0x10", "if(n0.val<0xFF)",
                     "while(sys0<0x10)", "for(sys0=0x00;sys0<0x10;sys0+=0x01)"):
            with self.subTest(line):
                self.assertEqual(unmatched([Need("code", "event", line, context=page)], rules),
                                 [])

    def test_each_probe_s_project(self):
        # Every need of each probe's project is matched, as a compile checks
        # them.
        for probe in hex_number_probes.PROBES:
            with self.subTest(probe.name):
                self.assertEqual(unmatched(project_needs(probe_project(probe)), matched_rules()),
                                 [])


if __name__ == "__main__":
    unittest.main()
