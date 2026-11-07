"""The device and serial buffer commands (tft/instructions/
device_and_buffer_commands.py): their blocks, as the probes of
device_and_buffer_command_probes.py kept them once they matched the Nextion
Editor's file, the blocks on T and K, and the lines refused.

Each test gives the encoder its own input: a probe's page and program.s,
made in memory from what the probe adds, or the base folder's facts, in a
Project of the facts the encoder reads (tests/tft/unit_inputs.py).
"""
import unittest


from nxwright.tft.compile_context import CompileContext
from tools.tft.probing import device_and_buffer_command_probes, p_probes
from nxwright.tft.instructions import device_and_buffer_commands
from nxwright.tft.matching import Need, matched_rules, project_needs, unmatched
from tools.tft.probing.number_probes import number_component
from nxwright.tft.statements import CodePlace, encodable, encode_line
from tools.tft.probing.text_probes import text_component
from tools.tft.probing.touch_capture_probes import touch_capture_component
from tools.tft.probing.statement_probes import kept_blocks
from tests.tft.line_context import line_context
from tests.tft.unit_inputs import piece, piece_names, probe_project, project_of


class FixtureTest(unittest.TestCase):
    """The encoder's blocks for each probe that keeps fixtures, on its page
    and program.s made in memory, against the probe's pieces: on T, and on
    P, which keeps the blocks of the same lines."""

    def test_each_probe_s_fixtures(self):
        probes = [probe for probe in device_and_buffer_command_probes.PROBES if probe.fixtures] + [
            probe for probe in p_probes.PROBES
            if probe.fixtures and probe.name.startswith("p-device-")]
        self.assertEqual(len(probes), 7)
        for probe in probes:
            with self.subTest(probe.name):
                self.assertEqual(kept_blocks(probe, probe_project(probe)),
                                 {each: piece(probe, each) for each in piece_names(probe)})


class LineTest(unittest.TestCase):

    def test_blocks(self):
        # In program.s, as the Nextion Editor wrote them: rest a command of
        # table 4, the others of table 8. K numbers rest, touch_j, and
        # udelete its own way.
        place = CodePlace()
        for series, rest, touch_j, udelete in (("T", 0x19, 0x14, 0x11), ("K", 0x1d, 0x15, 0x12)):
            project = project_of(series=series)
            with self.subTest(series):
                self.assertEqual(encode_line("rest", place,
                                             CompileContext(project)), bytes([0x09, rest, 0x04]))
                self.assertEqual(encode_line("touch_j", place, CompileContext(project)),
                                 bytes([0x09, touch_j, 0x08]))
                self.assertEqual(encode_line("code_c", place,
                                             CompileContext(project)), b"\x09\x06\x08")
                self.assertEqual(encode_line("ucopy sys0,0,2,0", place, CompileContext(project)),
                                 b"\x09\x05\x08\x05\x00\x00\x00\x00,0,2,0")
                self.assertEqual(encode_line("udelete 1", place, CompileContext(project)),
                                 bytes([0x09, udelete, 0x08]) + b"1")

    def test_operands(self):
        # A hexadecimal number is 03 and its value, 4 bytes, and so is a
        # number of 4 characters or more. A shorter number, a negative one
        # too, is kept as written. A system variable is 04, its table, and
        # its number. A space after a comma is dropped. Operands joined by
        # the arithmetic operators are written as an assignment's value.
        place, project = CodePlace(), project_of()
        for line, block in (("udelete 0x02", b"\x09\x11\x08\x03\x02\x00\x00\x00"),
                            ("udelete 0xFFFFFFFF", b"\x09\x11\x08\x03\xff\xff\xff\xff"),
                            ("udelete 1000", b"\x09\x11\x08\x03\xe8\x03\x00\x00"),
                            ("udelete -1", b"\x09\x11\x08-1"),
                            ("ucopy dim,0,2,0", b"\x09\x05\x08\x04\x04\x03\x00\x00,0,2,0"),
                            ("ucopy sys0, 0x01, 2, 0",
                             b"\x09\x05\x08\x05\x00\x00\x00\x00,\x03\x01\x00\x00\x00,2,0"),
                            ("udelete sys0+1", b"\x09\x11\x08\x05\x00\x00\x00\x00+1"),
                            ("ucopy sys0,1+1,2,sys1*2",
                             b"\x09\x05\x08\x05\x00\x00\x00\x00,1+1,2,\x05\x04\x00\x00\x00*2")):
            with self.subTest(line):
                self.assertEqual(encode_line(line, place, CompileContext(project)), block)

    def test_lines_refused(self):
        # A text or a txt where a number goes, which the Nextion Editor
        # refused ("Invalid variable operation"). An argument of rest, three
        # arguments of ucopy, and two of udelete, which it refused ("Invalid
        # number of arguments", the last two in nxwright's
        # ResearchNotes/serial-line.md). Its simulator refused five of
        # ucopy's and udelete alone. An argument of touch_j or code_c, which
        # nxwright's build refuses, saying the Nextion Editor does. An expression
        # as ucopy's destination, which the Nextion Editor refused ("Invalid
        # Variables").
        for line in ("ucopy n0.val,t0.txt,2,0", 'ucopy n0.val,0,2,"a"', "udelete t0.txt",
                     'udelete "a"', "rest 1", "touch_j 1", "code_c 0", "ucopy n0.val,0,2",
                     "ucopy n0.val,0,2,0,1", "udelete", "udelete 1,2", "ucopy sys0+1,0,2,0"):
            with self.subTest(line):
                self.assertFalse(encodable(line))


class MatchedTest(unittest.TestCase):

    def test_the_rule(self):
        rule, = device_and_buffer_commands.MATCHED
        # An event's line, on a page with the text t0 and the number n0.
        page = line_context(text_component(), number_component(y=60))
        for subject, line in (("event", "ucopy t0.txt,0,4,0"),
                              ("event", "ucopy n0.val,0,n0.val,0"), ("event", "udelete n0.val"),
                              ("event", "udelete n0.val*2"),
                              ("event", "ucopy n0.val,n0.val+1,2,0"),
                              ("event", "ucopy t0.bco,0,2,0"),
                              ("program.s", "ucopy sys0,1+1,2,sys1*2"),
                              ("program.s", "rest"), ("program.s", "touch_j"),
                              ("program.s", "code_c"), ("program.s", "ucopy sys0,0x01,2,0"),
                              ("program.s", "ucopy dim,0,2,0"), ("program.s", "udelete 1")):
            with self.subTest(line):
                self.assertTrue(rule.matches(Need("code", subject, line,
                                                  context=page if subject == "event" else {})))
        # A touch capture's val as ucopy's destination, which an assignment
        # may not set.
        capture = line_context(number_component(y=60), touch_capture_component(val=5))
        self.assertTrue(rule.matches(Need("code", "event", "ucopy tc0.val,0,2,0",
                                          context=capture)))
        # A val in program.s, which has no page; a txt of a number; and a
        # val of a text.
        self.assertFalse(rule.matches(Need("code", "program.s", "udelete n0.val")))
        for line in ("ucopy n0.txt,0,2,0", "ucopy t0.val,0,2,0", "udelete t0.val"):
            with self.subTest(line):
                self.assertFalse(rule.matches(Need("code", "event", line, context=page)))

    def test_each_probe_s_project(self):
        # Every need of each probe's project is matched, the components' and
        # the lines' alike, as a compile checks them.
        for probe in device_and_buffer_command_probes.PROBES:
            with self.subTest(probe.name):
                project = probe_project(probe)
                self.assertEqual(unmatched(project_needs(project), matched_rules()), [])


if __name__ == "__main__":
    unittest.main()
