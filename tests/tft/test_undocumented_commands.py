"""The undocumented commands (tft/instructions/undocumented_commands.py):
their blocks, as the probes of undocumented_command_probes.py kept them
once they matched the Nextion Editor's file, the blocks on T and K, and the
lines refused.

Each test gives the encoder its own input: a probe's page and program.s,
made in memory from what the probe adds, or the base folder's facts, in a
Project of the facts the encoder reads (tests/tft/unit_inputs.py).
"""
import unittest


from nxwright.tft.compile_context import CompileContext
from tools.tft.probing import p_probes, undocumented_command_probes
from nxwright.tft.instructions import undocumented_commands
from nxwright.tft.matching import Need, matched_rules, project_needs, unmatched
from tools.tft.probing.number_probes import number_component
from nxwright.tft.statements import CodePlace, encodable, encode_line
from tools.tft.probing.text_probes import text_component
from tools.tft.probing.statement_probes import kept_blocks
from tests.tft.line_context import line_context
from tests.tft.unit_inputs import piece, piece_names, probe_project, project_of


class FixtureTest(unittest.TestCase):
    """The encoder's blocks for each probe that keeps fixtures, on its page
    and program.s made in memory, against the probe's pieces: on T, and on
    P, which keeps the blocks of the same lines."""

    def test_each_probe_s_fixtures(self):
        probes = [probe for probe in undocumented_command_probes.PROBES if probe.fixtures] + [
            probe for probe in p_probes.PROBES
            if probe.fixtures and probe.name.startswith("p-undocumented-")]
        self.assertEqual(len(probes), 9)
        for probe in probes:
            with self.subTest(probe.name):
                self.assertEqual(kept_blocks(probe, probe_project(probe)),
                                 {each: piece(probe, each) for each in piece_names(probe)})


class LineTest(unittest.TestCase):

    def test_blocks(self):
        # In program.s, as the Nextion Editor wrote them: a command of table 4
        # or 8, then its arguments. K numbers most of them its own way, but
        # comok as T does.
        place = CodePlace()
        for series, getv, lcd_dev in (("T", 0x1A, 0x19), ("K", 0x1E, 0x1A)):
            project = project_of(series=series)
            with self.subTest(series):
                self.assertEqual(encode_line("getv sys0", place, CompileContext(project)),
                                 bytes([0x09, getv, 0x04]) + b"\x05\x00\x00\x00\x00")
                self.assertEqual(encode_line("lcd_dev 01 02", place, CompileContext(project)),
                                 bytes([0x09, lcd_dev, 0x08]) + b"01 02")
                self.assertEqual(encode_line("comok 0,0,0,0,0,0,0", place, CompileContext(project)),
                                 b"\x09\x01\x08" + b"0,0,0,0,0,0,0")

    def test_i(self):
        # 09 00 04 on T, K, P, and F alike, its two operands as any command's,
        # then its two numbers, as the Nextion Editor wrote them.
        place = CodePlace()
        for series in ("T", "K", "P", "F"):
            project = project_of(series=series)
            with self.subTest(series):
                self.assertEqual(encode_line("i sys0,sys1,1,2", place, CompileContext(project)),
                                 b"\x09\x00\x04\x05\x00\x00\x00\x00,\x05\x04\x00\x00\x00,1,2")
                self.assertEqual(encode_line('i "a","b",0,0', place, CompileContext(project)),
                                 b'\x09\x00\x04"a","b",0,0')

    def test_operands(self):
        # A text is kept between its double quotes, and operands joined by
        # the arithmetic operators are written as an assignment's value.
        # comok keeps its arguments as written, its text and its names too.
        place, project = CodePlace(), project_of()
        for line, block in (('fstr "abc",sys0+1,0', b'\x09\x10\x04"abc",\x05\x00\x00\x00\x00+1,0'),
                            ("timerset 1000,RED,0x01,-1",
                             b"\x09\x22\x08\x03\xe8\x03\x00\x00,\x04\x04\x01\x00\x00,"
                             b"\x03\x01\x00\x00\x00,-1"),
                            ('comok "a",sys0+1,0x01,RED,0,0,0',
                             b'\x09\x01\x08"a",sys0+1,0x01,RED,0,0,0')):
            with self.subTest(line):
                self.assertEqual(encode_line(line, place, CompileContext(project)), block)

    def test_lines_refused(self):
        # A text or a txt where a number goes, which the Nextion Editor
        # refused ("Invalid variable operation"); an expression where a
        # command takes one operand of any kind, which it refused ("Invalid
        # Variables"); another number of arguments, which nxwright's build
        # refuses, saying the Nextion Editor does.
        for line in ('init "a"', "init t0.txt", 'fstr 0,"a",0', 'qrcode "a",0,0,0,0,0,0,0',
                     "getv sys0+1", "fstr sys0+1,0,0", "strsize 0,0,sys0+1", "getpassw 0",
                     "getv", "fstr 0,0", "comok 0,0,0,0,0,0"):
            with self.subTest(line):
                self.assertFalse(encodable(line))


class MatchedTest(unittest.TestCase):

    def test_the_rule(self):
        rule, = undocumented_commands.MATCHED
        # An event's line, on a page with the text t0 and the number n0.
        page = line_context(text_component(), number_component(y=60))
        for subject, line in (("event", "getv t0.txt"), ("event", "fstr t0.txt,n0.val*2,0"),
                              ("event", 'strsize n0.val,"a",t0.txt'),
                              ("event", "comok t0.txt,0,0,0,0,0,0"),
                              ("program.s", "showqq"), ("program.s", "lcd_dev ff"),
                              ("program.s", 'zstr 0,0,0,sys0+1,"a"')):
            with self.subTest(line):
                self.assertTrue(rule.matches(Need("code", subject, line,
                                                  context=page if subject == "event" else {})))
        # A val in program.s, which has no page, comok's among them; a txt of
        # a number; and a component the page has not.
        for subject, line in (("program.s", "getv n0.val"),
                              ("program.s", "comok n0.val,0,0,0,0,0,0"),
                              ("event", "getv n0.txt"), ("event", "init t9.bco")):
            with self.subTest(line):
                self.assertFalse(rule.matches(Need("code", subject, line,
                                                   context=page if subject == "event" else {})))

    def test_i_s_operands_of_one_kind(self):
        # Its first two arguments, two numbers or two texts, or one reached
        # through the screen's arrays beside either, on T, K, P, and E; not
        # a text beside a number ("SYNTAX ERROR: Variable type does not
        # match"), nor an expression there ("Invalid Variables").
        page = line_context(text_component(), number_component(y=60))
        rules = matched_rules()
        for series in ("T", "K", "P", "E"):
            for line in ("i 0,0,0,0", "i n0.val,sys0,1,2", 'i "a", "b", 0, 0',
                         'i "a,b",t0.txt,0,0', "i b[1].txt,0,0,0", "i 0,0,sys0+1,n0.val*2"):
                with self.subTest(series=series, line=line):
                    self.assertEqual(unmatched([Need("code", "event", line, context=page,
                                                     series=series)], rules), [])
            for line in ("i t0.txt,0,0,0", 'i 0,"a",0,0', "i sys0+1,0,0,0", 'i 0,0,"a",0',
                         "i 0,0,0"):
                with self.subTest(series=series, line=line):
                    need = Need("code", "event", line, context=page, series=series)
                    self.assertEqual(unmatched([need], rules), [need])

    def test_on_p(self):
        # P numbers them its own way, as P's probes showed (p_probes.py), but
        # lacks fstr, which the Nextion Editor refuses there.
        self.assertEqual(unmatched([Need("code", "event", "getpassw", series="P")],
                                   matched_rules()), [])
        need = Need("code", "event", "fstr 0,0,0", series="P")
        self.assertEqual(unmatched([need], matched_rules()), [need])

    def test_piccolor_on_f(self):
        # F alone has it, as F's probes showed (f_probes.py): three numbers,
        # then one operand of any kind. Not a text or a txt among the three
        # ("Invalid variable operation"), nor an expression fourth ("Invalid
        # Variables"), nor another number of arguments ("Invalid number of
        # arguments"), which the Nextion Editor refused; and not on T, K, P,
        # or E, whose series lack it.
        page = line_context(text_component(), number_component(y=60))
        rules = matched_rules()
        for line in ("piccolor 1,2,3,4", "piccolor sys0,n0.val,n0.val+1,n0.val",
                     "piccolor 0x10,-5,799,t0.txt", 'piccolor 65535,0,0,"a"'):
            with self.subTest(line):
                self.assertEqual(unmatched([Need("code", "event", line, context=page,
                                                 series="F")], rules), [])
        for line in ("piccolor t0.txt,0,0,sys0", "piccolor 0,0,0,sys0+1", "piccolor 0,0,0",
                     "piccolor 0,0,0,0,0", 'piccolor 0,"a",0,sys0'):
            with self.subTest(line):
                need = Need("code", "event", line, context=page, series="F")
                self.assertEqual(unmatched([need], rules), [need])
        for series in ("T", "K", "P", "E"):
            with self.subTest(series):
                need = Need("code", "event", "piccolor 0,0,0,sys0", context=page, series=series)
                self.assertEqual(unmatched([need], rules), [need])

    def test_each_probe_s_project(self):
        # Every need of each probe's project is matched, the components' and
        # the lines' alike, as a compile checks them.
        for probe in undocumented_command_probes.PROBES:
            with self.subTest(probe.name):
                project = probe_project(probe)
                self.assertEqual(unmatched(project_needs(project), matched_rules()), [])


if __name__ == "__main__":
    unittest.main()
