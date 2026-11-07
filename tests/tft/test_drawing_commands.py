"""The drawing commands (tft/instructions/drawing_commands.py): their
blocks, as the probes of drawing_probes.py kept them once they matched the
Nextion Editor's file, the lines refused, and the copies of their first
bytes that component_types keeps.

The encoder's blocks of each probe are given its page and program.s made in
memory (tests/tft/unit_inputs.py)."""
import unittest

from nxwright.tft import component_types, frame
from tools.tft.probing import drawing_probes, p_probes
from nxwright.tft.instructions import drawing_commands, screen_commands
from nxwright.tft.matching import Need, unmatched
from tools.tft.probing.number_probes import number_component
from tools.tft.probing.statement_probes import kept_blocks
from nxwright.tft.statements import StatementError, encodable
from tools.tft.probing.text_probes import text_component
from tools.tft.probing.timer_probes import timer_component
from tests.tft.line_context import line_context
from tests.tft.unit_inputs import piece, piece_names, probe_project


class FixtureTest(unittest.TestCase):
    """The encoder still writes the blocks the probes checked, against each
    probe's piece, on its page and program.s made in memory."""

    def test_each_probe_s_blocks(self):
        # On T, and on P, which keeps the blocks of the same lines.
        probes = [probe for probe in drawing_probes.PROBES if probe.fixtures] + [
            probe for probe in p_probes.PROBES
            if probe.fixtures and probe.name.startswith("p-drawing-")]
        self.assertTrue(probes)
        for probe in probes:
            with self.subTest(probe.name):
                self.assertEqual(kept_blocks(probe, probe_project(probe)),
                                 {each: piece(probe, each) for each in piece_names(probe)})


class CopiedCommandTest(unittest.TestCase):

    def test_the_commands_component_types_keeps(self):
        # component_types keeps the first bytes of fill, pic, xpic, and ref,
        # as it cannot import the encoder's tables. They must be the
        # encoder's, on each series its types take.
        for series in ("T", "K", "F"):
            with self.subTest(series):
                drawing = drawing_commands.COMMANDS[series]
                self.assertEqual(
                    [component_types.FILL, component_types.PIC, component_types.XPIC,
                     component_types.REF],
                    [drawing["fill"].block_start(), drawing["pic"].block_start(),
                     drawing["xpic"].block_start(),
                     screen_commands.COMMANDS[series]["ref"].block_start()])


class LineTest(unittest.TestCase):

    def test_lines_refused(self):
        # Too few operands and too many, which nxwright's build refuses, and
        # two spaces after a comma, which it drops before the encoder sees
        # the line. Then operands the Nextion Editor refused: an operator
        # right after another, but a minus before a number, and operands it
        # does not read as one ("Invalid Variables"), and a txt ("Invalid
        # variable operation").
        for line in ("cls RED+*1", "fill 0,0,1", "line 0,0,1,1,2,3", "cir 50,  50,20,RED",
                     "cls 5a", "cls 1_000", "cls -a", "cls t0.txt"):
            with self.subTest(line):
                self.assertFalse(encodable(line))

    def test_texts_refused(self):
        # A text that is not xstr's last operand, an escape the screen does
        # not read, texts or a txt and a text joined, which the Nextion
        # Editor refused ("Invalid Variables"), a missing text, and a text to
        # pic.
        head = "xstr 0,0,10,10,0,RED,WHITE,0,0,"
        for line in (head + '"a",0', head + '0,"a\\b"', head + '0,"a"+"b"',
                     head + '0,t0.txt+"a"', head + "0", 'pic 0,0,"a"'):
            with self.subTest(line):
                self.assertFalse(encodable(line))
        # A line of 767 characters, the most T takes, and one past it, as
        # nxwright's build refuses a line longer than its series takes.
        for size in (732, 733):
            self.assertTrue(encodable(head + '0,"%s"' % ("a" * size)))
        # A letter past U+00FF is refused in iso-8859-1, which cannot write
        # it, by the rule of a line past ASCII (frame.py).
        line = head + '0,"Ā"'
        self.assertEqual(unmatched([Need("text in code", "iso-8859-1", line)], frame.MATCHED),
                         [Need("text in code", "iso-8859-1", line)])


class MatchedTest(unittest.TestCase):

    def test_the_rule(self):
        rule, = drawing_commands.MATCHED
        self.assertTrue(rule.matches(Need("code", "event", "cls RED")))
        self.assertTrue(rule.matches(Need("code", "program.s", "fill 0,0,10,10,BLUE")))
        for line in ("pic 0,0,1", "picq 0,0,8,4,0", "xpic 0,0,4,4,2,1,1",
                     'xstr 0,0,100,30,0,RED,WHITE,1,1,1,"hi"'):
            with self.subTest(line):
                self.assertTrue(rule.matches(Need("code", "event", line)))
        self.assertFalse(rule.matches(Need("code", "event", "cls RED+*1")))
        self.assertFalse(rule.matches(Need("code", "event", "sys0=1")))

    def test_xstr_s_text_as_one_operand(self):
        # As the probe drawing-xstr-text-operands showed: a txt, a val, a
        # tim, or a variable, on a page of the text t0, the number n0, and
        # the timer tm0; and any other attribute a type writes. A txt is a
        # number nowhere else, and an attribute the type does not write is
        # refused.
        rule, = drawing_commands.MATCHED
        context = line_context(text_component(), number_component(y=60), timer_component())
        head = "xstr 0,0,100,30,0,RED,WHITE,0,0,1,"
        for text, covered in (("t0.txt", True), (" t0.txt", True), ("n0.val", True),
                              ("tm0.en", True), ("sys0", True), ("0x41", True),
                              ("t0.bco", True), ("t0.val", False)):
            with self.subTest(text):
                self.assertEqual(rule.matches(Need("code", "event", head + text, context=context)),
                                 covered)
        self.assertFalse(rule.matches(Need("code", "event", "cls t0.txt", context=context)))
        # program.s has no page, so no attribute.
        self.assertFalse(rule.matches(Need("code", "program.s", head + "t0.txt")))


if __name__ == "__main__":
    unittest.main()
