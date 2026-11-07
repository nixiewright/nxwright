"""The CRC commands (tft/instructions/crc_commands.py): their blocks, as
the probes of crc_command_probes.py kept them once they matched the Nextion
Editor's file, the blocks on T and K, hexadecimal numbers, and the lines
refused.

Each test gives the encoder its own input: a line, where it lies, and a
Project of the facts the encoder reads, a probe's page and program.s made
in memory (tests/tft/unit_inputs.py)."""
import unittest


from nxwright.tft.compile_context import CompileContext
from tools.tft.probing import crc_command_probes, p_probes
from nxwright.tft.instructions import crc_commands
from nxwright.tft.matching import Need, matched_rules, project_needs, unmatched
from tools.tft.probing.number_probes import number_component
from tools.tft.probing.statement_probes import kept_blocks
from nxwright.tft.statements import CodePlace, encodable, encode_line
from tools.tft.probing.text_probes import text_component
from tests.tft.line_context import line_context
from tests.tft.unit_inputs import piece, piece_names, probe_project, project_of


class FixtureTest(unittest.TestCase):
    """The encoder still writes the blocks the probes checked, against each
    probe's piece, on its page and program.s made in memory."""

    def test_each_probe_s_blocks(self):
        # On T, and on P, which keeps the blocks of the same lines.
        probes = [probe for probe in crc_command_probes.PROBES if probe.fixtures] + [
            probe for probe in p_probes.PROBES
            if probe.fixtures and probe.name.startswith("p-crc-commands-")]
        self.assertTrue(probes)
        for probe in probes:
            with self.subTest(probe.name):
                self.assertEqual(kept_blocks(probe, probe_project(probe)),
                                 {each: piece(probe, each) for each in piece_names(probe)})


class LineTest(unittest.TestCase):

    def test_blocks(self):
        # In program.s, as the Nextion Editor wrote them: each a command of
        # table 8, crcputh's bytes as written. K numbers each one past T.
        place = CodePlace()
        for series, first in (("T", 0x13), ("K", 0x14)):
            project = project_of(series=series)
            with self.subTest(series):
                self.assertEqual(encode_line("crcputh 31 32", place, CompileContext(project)),
                                 bytes([0x09, first, 0x08]) + b"31 32")
                self.assertEqual(encode_line('crcputs "abc",0', place, CompileContext(project)),
                                 bytes([0x09, first + 2, 0x08]) + b'"abc",0')
                self.assertEqual(encode_line("crcrest sys0,1", place, CompileContext(project)),
                                 bytes([0x09, first + 4, 0x08]) + b"\x05\x00\x00\x00\x00,1")
                self.assertEqual(encode_line("crcputu 0,3", place, CompileContext(project)),
                                 bytes([0x09, first + 5, 0x08]) + b"0,3")

    def test_system_variables(self):
        # A system variable is its operand, as in any line: 04, its table,
        # and its number, which K gives rand its own way. As the Nextion
        # Editor wrote them, on T and on K.
        place = CodePlace()
        for series, first, rand in (("T", 0x13, 0x0d), ("K", 0x14, 0x20)):
            project = project_of(series=series)
            with self.subTest(series):
                self.assertEqual(encode_line("crcrest 1,dim", place, CompileContext(project)),
                                 bytes([0x09, first + 4, 0x08]) + b"1,\x04\x04\x03\x00\x00")
                self.assertEqual(encode_line("crcputu rand,sendxy", place, CompileContext(project)),
                                 bytes([0x09, first + 5, 0x08, 0x04, 0x04, rand, 0, 0])
                                 + b",\x04\x08\x10\x00\x00")

    def test_hexadecimal_numbers(self):
        # A hexadecimal number, its digits in pairs, is 03 and its value, 4
        # bytes, however small, as the Nextion Editor wrote it.
        place, project = CodePlace(), project_of()
        for number, value in (("0x00", b"\x00\x00\x00\x00"), ("0x12", b"\x12\x00\x00\x00"),
                              ("0X12", b"\x12\x00\x00\x00"), ("0xfFfF", b"\xff\xff\x00\x00"),
                              ("0x010000", b"\x00\x00\x01\x00"),
                              ("0xFFFFFFFF", b"\xff\xff\xff\xff")):
            with self.subTest(number):
                self.assertEqual(encode_line("crcrest 1," + number, place, CompileContext(project)),
                                 b"\x09\x17\x081,\x03" + value)

    def test_lines_refused(self):
        # A text or a txt where a number goes, which the Nextion Editor
        # refused ("Invalid variable operation"); a hexadecimal number past
        # 4 bytes, which 4 bytes cannot hold; an expression as crcputs'
        # value, which the Nextion Editor refused ("Invalid Variables"); and
        # an operator right after another, but a minus before a number.
        for line in ('crcrest 1,"a"', "crcrest 1,t0.txt", "crcputs t0.txt,t0.txt",
                     "crcputu t0.txt,1", "crcrest 1,0x0100000000",
                     "crcputs 0x01+1,4", "crcrest 1,sys0+*1", "crcputs t0.txt"):
            with self.subTest(line):
                self.assertFalse(encodable(line))
        # crcputh's argument of any length, as nxwright's build holds a line
        # to its series' limit.
        self.assertTrue(encodable("crcputh " + " ".join(["00"] * 254)))


class MatchedTest(unittest.TestCase):

    def test_the_rule(self):
        rule, = crc_commands.MATCHED
        # An event's line, on a page with the text t0 and the number n0.
        page = line_context(text_component(), number_component(y=60))
        for subject, line in (("event", "crcputs t0.txt,n0.val"), ("event", "crcrest 1,n0.val"),
                              ("event", "crcputu n0.val,1"), ("program.s", "crcrest 1,0xFFFF"),
                              ("program.s", "crcputh 0d 0a")):
            with self.subTest(line):
                self.assertTrue(rule.matches(Need("code", subject, line,
                                                  context=page if subject == "event" else {})))
        # A val in program.s, which has no page; a txt of a number; a val of
        # a text; and an attribute a number does not write.
        self.assertFalse(rule.matches(Need("code", "program.s", "crcrest 1,n0.val")))
        for line in ("crcputs n0.txt,0", "crcrest 1,t0.val", "crcputs n0.pw,0"):
            with self.subTest(line):
                self.assertFalse(rule.matches(Need("code", "event", line, context=page)))

    def test_each_probe_s_project(self):
        # Every need of each probe's pages and program.s is matched, the
        # components' and the lines' alike, as a compile checks them.
        for probe in crc_command_probes.PROBES:
            with self.subTest(probe.name):
                self.assertEqual(unmatched(project_needs(probe_project(probe)),
                                           matched_rules()), [])


if __name__ == "__main__":
    unittest.main()
