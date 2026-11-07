"""The text commands (tft/instructions/text_commands.py): their blocks, as
the probes of text_command_probes.py kept them once they matched the
Nextion Editor's file, and the lines refused.

Each test gives the encoder its own input: a probe's page and program.s,
made in memory from what the probe adds, in a Project of the facts the
encoder reads (tests/tft/unit_inputs.py).
"""
import unittest


from tools.tft.probing import p_probes, text_command_probes
from tools.tft.probing.crop_probes import crop_component
from nxwright.tft.instructions import text_commands
from nxwright.tft.matching import Need, matched_rules, project_needs, unmatched
from tools.tft.probing.number_probes import number_component
from tools.tft.probing.picture_probes import picture_component
from tools.tft.probing.statement_probes import kept_blocks
from nxwright.tft.statements import encodable
from tools.tft.probing.text_probes import text_component
from tools.tft.probing.timer_probes import timer_component
from tools.tft.probing.waveform_probes import waveform_component
from tests.tft.line_context import line_context
from tests.tft.unit_inputs import piece, piece_names, probe_project


class FixtureTest(unittest.TestCase):
    """The encoder's blocks for each probe that keeps fixtures, on its page
    and program.s made in memory, against the probe's pieces."""

    def test_each_probe_s_fixtures(self):
        # On T, and on P, which keeps the blocks of the same lines.
        probes = [probe for probe in text_command_probes.PROBES if probe.fixtures is not None] + [
            probe for probe in p_probes.PROBES
            if probe.fixtures and probe.name.startswith("p-text-commands-")]
        self.assertEqual(len(probes), 8)
        for probe in probes:
            with self.subTest(probe.name):
                self.assertEqual(kept_blocks(probe, probe_project(probe)),
                                 {each: piece(probe, each) for each in piece_names(probe)})


class LineTest(unittest.TestCase):

    def test_lines_refused(self):
        # An expression, too few operands, too many, two spaces after a
        # comma, a txt where a number goes, and a backslash in a text, none
        # of which a probe showed.
        for line in ("covx sys0+1,t0.txt,0,0", "covx sys0,t0.txt,0", "strlen t0.txt,sys0,1",
                     "btlen t0.txt,  sys0", "covx sys0,t0.pco,t0.txt,0", 'strlen "a\\b",sys0',
                     "substr t0.txt,t1.txt,0,1,2", "spstr t0.txt,t1.txt,0"):
            with self.subTest(line):
                self.assertFalse(encodable(line))

    def test_a_text_where_a_number_goes(self):
        # The Nextion Editor refused each: "Invalid variable operation".
        for line in ("covx sys0,t0.txt,t0.txt,0", "covx sys0,t0.txt,0,t0.txt",
                     'covx sys0,t0.txt,"1",0', "cov sys0,t0.txt,t0.txt",
                     "substr t0.txt,t0.txt,t0.txt,1", 'substr t0.txt,t0.txt,0,"1"',
                     'spstr t0.txt,t0.txt,",",t0.txt'):
            with self.subTest(line):
                self.assertFalse(encodable(line))
        # It took a text as strlen's and btlen's destination.
        for line in ("strlen t0.txt,t0.txt", 'btlen t0.txt,"x"'):
            with self.subTest(line):
                self.assertTrue(encodable(line))


class MatchedTest(unittest.TestCase):

    def test_the_rule(self):
        rule, = text_commands.MATCHED
        # An event's line, on a page with the texts t0 and t1 and a number n0.
        page = line_context(text_component(), text_component("t1", y=60),
                            number_component(y=110))
        for subject, line in (("event", "covx t0.txt,sys0,0,0"), ("event", "strlen t1.txt,sys1"),
                              ("program.s", "covx sys0,sys1,0,0"),
                              ("program.s", 'strlen "t0.txt",sys0')):
            with self.subTest(line):
                self.assertTrue(rule.matches(Need("code", subject, line,
                                                  context=page if subject == "event" else {})))
        # A text's txt in program.s, which has no page to find the text on.
        self.assertFalse(rule.matches(Need("code", "program.s", "covx t0.txt,sys0,0,0")))
        # A txt on no text of the page: a number's, or one not on it.
        for line in ("strlen n0.txt,sys0", "covx sys0,t9.txt,0,0"):
            with self.subTest(line):
                self.assertFalse(rule.matches(Need("code", "event", line, context=page)))
        self.assertFalse(rule.matches(Need("code", "event", "covx sys0+1,t0.txt,0,0",
                                           context=page)))
        self.assertFalse(rule.matches(Need("code", "event", "sys0=1", context=page)))

    def test_vals(self):
        rule, = text_commands.MATCHED
        # On a page with the text t0 and the number n0.
        page = line_context(text_component(), number_component(y=60))
        for line in ("covx n0.val,t0.txt,0,0", "covx t0.txt,n0.val,0,0", "cov n0.val,t0.txt,0",
                     "covx n0.val,t0.txt,n0.val,0", "strlen t0.txt,n0.val",
                     "substr t0.txt,t0.txt,n0.val,1", 'spstr t0.txt,t0.txt,",",n0.val'):
            with self.subTest(line):
                self.assertTrue(rule.matches(Need("code", "event", line, context=page)))
        # A val of a text, a txt of a number, a txt where a number goes, and
        # an attribute a number does not write.
        for line in ("covx t0.val,t0.txt,0,0", "covx n0.txt,t0.txt,0,0",
                     "covx n0.val,t0.txt,t0.txt,0", "covx n0.pw,t0.txt,0,0"):
            with self.subTest(line):
                self.assertFalse(rule.matches(Need("code", "event", line, context=page)))

    def test_other_attributes(self):
        rule, = text_commands.MATCHED
        # On a page with the text t0, the picture p0, the crop q0, the
        # waveform s0, and the timer tm0: their pic, picc, id, tim, and en,
        # as an operand, as a destination, and where a number goes, as the
        # Nextion Editor compiled them. It took a waveform's id as a
        # destination too, though nxwright refuses an assignment that sets one.
        # Then any other attribute a type writes, such as a timer's vscope.
        page = line_context(text_component(), picture_component(x=160, pic=None),
                            crop_component(x=160, y=60, picc=None), waveform_component(y=150),
                            timer_component())
        for line in ("covx tm0.tim,t0.txt,0,0", "cov p0.pic,t0.txt,0", "covx q0.picc,t0.txt,0,0",
                     "covx s0.id,t0.txt,0,0", "covx t0.txt,tm0.en,0,0", "strlen t0.txt,q0.picc",
                     "btlen t0.txt,p0.pic", "strlen t0.txt,s0.id",
                     "covx sys0,t0.txt,tm0.tim,tm0.en", "substr t0.txt,t0.txt,q0.picc,s0.id",
                     'spstr t0.txt,t0.txt,",",p0.pic', "covx tm0.tim, t0.txt, 0, 0",
                     "covx tm0.vscope,t0.txt,0,0", "covx s0.dis,t0.txt,0,0"):
            with self.subTest(line):
                self.assertTrue(rule.matches(Need("code", "event", line, context=page)))
        # One type's attribute on another type, an attribute its type does
        # not write, and a timer's tim in program.s, which has no page.
        for line in ("covx p0.picc,t0.txt,0,0", "covx tm0.pic,t0.txt,0,0",
                     "covx tm0.x,t0.txt,0,0"):
            with self.subTest(line):
                self.assertFalse(rule.matches(Need("code", "event", line, context=page)))
        self.assertFalse(rule.matches(Need("code", "program.s", "covx sys0,tm0.tim,0,0")))

    def test_each_probe_s_project(self):
        # Every need of each probe's project is matched, the texts' and the
        # lines' alike, as a compile checks them.
        for probe in text_command_probes.PROBES:
            with self.subTest(probe.name):
                project = probe_project(probe)
                self.assertEqual(unmatched(project_needs(project), matched_rules()), [])


if __name__ == "__main__":
    unittest.main()
