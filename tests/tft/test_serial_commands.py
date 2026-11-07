"""The serial commands (tft/instructions/serial_commands.py): their blocks,
as the probes of serial_command_probes.py kept them once they matched the
Nextion Editor's file, and the lines refused.

Each test gives the encoder its own input: a probe's page and program.s,
made in memory from what the probe adds, or the base folder's facts, in a
Project of the facts the encoder reads (tests/tft/unit_inputs.py).
"""
import unittest


from tools.tft.probing import p_probes, serial_command_probes
from nxwright.tft.instructions import serial_commands
from nxwright.tft.matching import Need, matched_rules, project_needs, unmatched
from tools.tft.probing.number_probes import number_component
from nxwright.tft.statements import encodable
from tools.tft.probing.text_probes import text_component
from tools.tft.probing.timer_probes import timer_component
from tools.tft.probing.statement_probes import kept_blocks
from tests.tft.line_context import line_context
from tests.tft.unit_inputs import piece, piece_names, probe_project


class FixtureTest(unittest.TestCase):
    """The encoder's blocks for each probe that keeps fixtures, on its page
    and program.s made in memory, against the probe's pieces: on T, and on
    P, which keeps the blocks of the same lines."""

    def test_each_probe_s_fixtures(self):
        probes = [probe for probe in serial_command_probes.PROBES if probe.fixtures] + [
            probe for probe in p_probes.PROBES
            if probe.fixtures and probe.name.startswith("p-serial-")]
        self.assertEqual(len(probes), 5)
        for probe in probes:
            with self.subTest(probe.name):
                self.assertEqual(kept_blocks(probe, probe_project(probe)),
                                 {each: piece(probe, each) for each in piece_names(probe)})


class LineTest(unittest.TestCase):

    def test_lines_refused(self):
        # An expression, which the Nextion Editor refuses, and texts joined;
        # an argument to sendme; too many or too few arguments; and two
        # spaces after a comma.
        for line in ("get n0.val+1", 'print "a"+t0.txt', "sendme 1",
                     "get 1,2", "prints t0.txt", "prints t0.txt,  1", "print",
                     # A text as prints' length, which the Nextion Editor
                     # refused: "Invalid variable operation".
                     "prints n0.val,t0.txt", 'prints "hi","x"', 'prints t0.txt,"2"'):
            with self.subTest(line):
                self.assertFalse(encodable(line))


class MatchedTest(unittest.TestCase):

    def test_the_rule(self):
        rule, = serial_commands.MATCHED
        # An event's line, on a page with the text t0 and the number n0.
        page = line_context(text_component(), number_component(y=60))
        for subject, line in (("event", "get t0.txt"), ("event", "print n0.val"),
                              ("event", "prints n0.val,4"), ("event", "sendme"),
                              ("program.s", 'print "t0.txt"'), ("program.s", "get sys0")):
            with self.subTest(line):
                context = page if subject == "event" else {}
                self.assertTrue(rule.matches(Need("code", subject, line, context=context)))
        # A txt on a number, a val on a text, an attribute of no component
        # of the page, and a page's own attribute in program.s.
        for subject, line in (("event", "get n0.txt"), ("event", "get t0.val"),
                              ("event", "get t9.txt"), ("program.s", "get n0.val")):
            with self.subTest(line):
                context = page if subject == "event" else {}
                self.assertFalse(rule.matches(Need("code", subject, line, context=context)))

    def test_vals_and_a_timer_s_attributes(self):
        rule, = serial_commands.MATCHED
        # On a page with the text t0, the numbers n0 and n1, and the timer
        # tm0: a val as prints' length, and a timer's tim and en as each
        # command's operand, as the Nextion Editor compiled them.
        page = line_context(text_component(), number_component(y=60),
                            number_component("n1", y=110), timer_component())
        for line in ("prints t0.txt,n0.val", "prints n0.val,n1.val", "get tm0.tim",
                     "get tm0.en", "print tm0.tim", "prints tm0.tim,2",
                     "prints t0.txt,tm0.tim", "get tm0.vscope", "get t0.pco"):
            with self.subTest(line):
                self.assertTrue(rule.matches(Need("code", "event", line, context=page)))
        # A txt as prints' length, which the Nextion Editor refuses, a val of
        # a text, and an attribute a timer does not write.
        for line in ("prints t0.txt,t0.txt", "prints t0.txt,t0.val", "get tm0.x"):
            with self.subTest(line):
                self.assertFalse(rule.matches(Need("code", "event", line, context=page)))

    def test_each_probe_s_project(self):
        # Every need of each probe's project is matched, as a compile checks
        # them.
        for probe in serial_command_probes.PROBES:
            with self.subTest(probe.name):
                project = probe_project(probe)
                self.assertEqual(unmatched(project_needs(project), matched_rules()), [])


if __name__ == "__main__":
    unittest.main()
