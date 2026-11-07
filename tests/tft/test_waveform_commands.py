"""The waveform commands (tft/instructions/waveform_commands.py): their
blocks, as the probes of waveform_command_probes.py kept them once they
matched the Nextion Editor's file, add's block on T and K, and the lines
refused.

Each test gives the encoder its own input: a line, where it lies, and a
Project of the facts the encoder reads, a probe's page and program.s made
in memory (tests/tft/unit_inputs.py)."""
import struct
import unittest


from nxwright.tft.compile_context import CompileContext
from tools.tft.probing import p_probes, waveform_command_probes
from nxwright.tft.instructions import waveform_commands
from nxwright.tft.matching import Need, matched_rules, project_needs, unmatched
from tools.tft.probing.number_probes import number_component
from tools.tft.probing.statement_probes import kept_blocks
from nxwright.tft.statements import CodePlace, encodable, encode_line
from tools.tft.probing.text_probes import text_component
from tools.tft.probing.waveform_probes import waveform_component
from tests.tft.line_context import line_context
from tests.tft.unit_inputs import piece, piece_names, probe_project, project_of


def entry(number: int) -> bytes:
    return b"\x01" + struct.pack("<I", number)


class FixtureTest(unittest.TestCase):
    """The encoder still writes the blocks the probes checked, against each
    probe's piece, on its page and program.s made in memory."""

    def test_each_probe_s_blocks(self):
        # On T, and on P, which keeps the blocks of the same lines.
        probes = [probe for probe in waveform_command_probes.PROBES if probe.fixtures] + [
            probe for probe in p_probes.PROBES
            if probe.fixtures and probe.name.startswith("p-waveform-commands-")]
        self.assertTrue(probes)
        for probe in probes:
            with self.subTest(probe.name):
                self.assertEqual(kept_blocks(probe, probe_project(probe)),
                                 {each: piece(probe, each) for each in piece_names(probe)})


class LineTest(unittest.TestCase):

    def test_blocks(self):
        # In program.s, as the Nextion Editor wrote them: add by its name and
        # a space, addt 0x15 and cle 0x02 in table 4 on T. K numbers addt
        # 0x17, P and E 0x1E, and each writes add and cle as T does.
        place = CodePlace()
        for series, addt in (("T", 0x15), ("K", 0x17), ("P", 0x1E), ("E", 0x1E)):
            project = project_of(series=series)
            with self.subTest(series):
                self.assertEqual(encode_line("add 1,0,10", place,
                                             CompileContext(project)), b"add 1,0,10")
                self.assertEqual(encode_line("addt 1,0,100", place, CompileContext(project)),
                                 bytes([0x09, addt, 0x04]) + b"1,0,100")
                self.assertEqual(encode_line("cle 1,255", place,
                                             CompileContext(project)), b"\x09\x02\x041,255")

    def test_a_waveform_s_id(self):
        # In an event, s0.id is the operand of the waveform's entry 1: page0's
        # entries are 33, so s0's id is entry 34.
        project = probe_project(waveform_command_probes.PROBES[0])
        place = CodePlace(0, "page0", "up")
        self.assertEqual(encode_line("cle s0.id,0", place, CompileContext(project)),
                         b"\x09\x02\x04" + entry(34) + b",0")
        self.assertEqual(encode_line("sys0=s0.id", place, CompileContext(project)),
                         b"\x05\x00\x00\x00\x00=" + entry(34))

    def test_lines_refused(self):
        # Too few arguments and too many, which nxwright's build refuses, and
        # two spaces after a comma, which it drops before the encoder sees
        # the line. Then what the Nextion Editor refused: an operator right
        # after another, but a minus before a number ("Invalid Variables"),
        # and a text and a txt where a number goes ("Invalid variable
        # operation").
        for line in ("add s0.id,0,sys0+*1", "add s0.id,0", "cle s0.id,0,1", "cle s0.id,  0",
                     'add s0.id,0,"a"', "add s0.id,0,t0.txt"):
            with self.subTest(line):
                self.assertFalse(encodable(line))

    def test_a_text_or_a_txt_in_each_place(self):
        # The Nextion Editor refused each on T ("Invalid variable operation"),
        # which nxwright's build lets through.
        places = {"add": 3, "addt": 3, "cle": 2}
        for command, count in places.items():
            for place in range(count):
                for value in ('"a"', "t0.txt"):
                    line = "%s %s" % (command, ",".join(
                        value if each == place else "1" for each in range(count)))
                    with self.subTest(line):
                        self.assertFalse(encodable(line))
                        self.assertTrue(encodable(line.replace(value, "1")))


class MatchedTest(unittest.TestCase):

    def test_the_rule(self):
        rule, = waveform_commands.MATCHED
        # An event's line, on a page with the waveform s0, the number n0, and
        # the text t0.
        page = line_context(waveform_component(), number_component(y=150),
                            text_component(y=200))
        for subject, line in (("event", "add s0.id,0,n0.val"), ("event", "cle s0.id,255"),
                              ("program.s", "add 1,0,10"), ("program.s", "addt sys0,0,100")):
            with self.subTest(line):
                self.assertTrue(rule.matches(Need("code", subject, line,
                                                  context=page if subject == "event" else {})))
        # A waveform's id in program.s, which has no page to find it on.
        self.assertFalse(rule.matches(Need("code", "program.s", "cle s0.id,0")))
        # Another attribute of a type that writes it, such as a text's id or
        # a number's pco.
        for line in ("add t0.id,0,10", "add s0.id,0,n0.pco"):
            with self.subTest(line):
                self.assertTrue(rule.matches(Need("code", "event", line, context=page)))
        # A txt, which the Nextion Editor refused ("Invalid variable
        # operation"); an attribute a type does not write, such as a
        # number's pw; and the id of a component not on the page.
        for line in ("add s0.id,0,t0.txt", "add s0.id,0,n0.pw", "cle s9.id,0"):
            with self.subTest(line):
                self.assertFalse(rule.matches(Need("code", "event", line, context=page)))

    def test_each_probe_s_project(self):
        # Every need of each probe's pages and program.s is matched, the
        # components' and the lines' alike, as a compile checks them.
        for probe in waveform_command_probes.PROBES:
            with self.subTest(probe.name):
                self.assertEqual(unmatched(project_needs(probe_project(probe)),
                                           matched_rules()), [])


if __name__ == "__main__":
    unittest.main()
