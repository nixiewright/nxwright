"""Commands' operands (tft/statements.py and tft/instructions/): an
expression where a command takes a number, an attribute in the drawing and
screen commands, a hexadecimal number in every family of commands, and texts
with the escapes the screen reads. The blocks, as the probes of
command_operand_probes.py kept them once they matched the Nextion Editor's
file, the lines refused, and what each family's rule covers.

Each test gives the encoder its own input: a line, where it lies, and a
Project of the facts the encoder reads, a page of the probes' components
made in memory and program.s (tests/tft/unit_inputs.py)."""
import unittest

from nxwright.tft.compile_context import CompileContext
from tools.tft.probing import command_operand_probes
from nxwright.tft.component_types import entry_operand
from nxwright.tft.control_statements import condition_blocks, covers_condition
from nxwright.tft.instructions import (crc_commands, drawing_commands, eeprom_and_gpio_commands,
                                if_statement, screen_commands, serial_commands, text_commands,
                                waveform_commands)
from nxwright.tft.matching import Need, matched_rules, project_needs, unmatched
from tools.tft.probing.statement_probes import event_blocks, kept_blocks, touch_release_code
from nxwright.tft.statements import CodePlace, StatementError, encodable, encode_line
from tests.tft.line_context import line_context
from tests.tft.unit_inputs import page, piece, piece_names, probe_project, project_of

# The probes' page0: t0, n0, n1, tm0, and s0. In it, t0's txt is entry 61,
# n0's val 101, n1's val 142, tm0's tim 163, and s0's id 168.
_COMPONENTS = command_operand_probes.COMPONENTS
_EVENT = CodePlace(0, "page0", "up")


def _with(lines: list):
    """Returns a Project of facts of the probes' page0, its Touch Release
    event giving `lines`, in strict Nextion syntax, as a probe of
    attribute_probes.with_attributes has it."""
    return project_of(page(*_COMPONENTS, code=touch_release_code(lines), strict=True),
                      strict=True)


class FixtureTest(unittest.TestCase):
    """The encoder still writes the blocks the probes checked, against each
    probe's piece, on its page and program.s made in memory."""

    def test_each_probe_s_blocks(self):
        probes = [probe for probe in command_operand_probes.PROBES if probe.fixtures]
        self.assertTrue(probes)
        for probe in probes:
            with self.subTest(probe.name):
                self.assertEqual(kept_blocks(probe, probe_project(probe)),
                                 {each: piece(probe, each) for each in piece_names(probe)})

    def test_the_check_takes_every_probe(self):
        # Each probe's page and program.s matched the Nextion Editor's, so
        # the check lets them through.
        for probe in command_operand_probes.PROBES:
            with self.subTest(probe.name):
                self.assertEqual(unmatched(project_needs(probe_project(probe)),
                                           matched_rules()), [])


class EncodeTest(unittest.TestCase):
    """Each argument is a value, as an assignment's: its operands, each
    operator as its text after its operand, as the Nextion Editor wrote
    them."""

    @classmethod
    def setUpClass(cls):
        cls.project = _with(["sys0=1"])

    def encoded(self, line: str) -> bytes:
        return encode_line(line, _EVENT, CompileContext(self.project))

    def test_expressions(self):
        red = b"\x04\x04\x01\x00\x00"
        self.assertEqual(self.encoded("cls RED+1"), b"\x09\x06\x04" + red + b"+1")
        self.assertEqual(self.encoded("fill 0,0,10+5*2,10,RED"),
                         b"\x09\x0d\x04" + b"0,0,10+5*2,10," + red)
        self.assertEqual(self.encoded("vis t0,1+0"), b"\x09\x05\x04t0,1+0")
        self.assertEqual(self.encoded("add s0.id+0,0,n0.val*2"),
                         b"add " + entry_operand(168) + b"+0,0," + entry_operand(101) + b"*2")
        self.assertEqual(self.encoded("cls -5+1"), b"\x09\x06\x04-5+1")

    def test_attributes_and_hexadecimal_numbers(self):
        self.assertEqual(self.encoded("fill n0.val,n1.val,tm0.tim,n0.val+1,0x0A"),
                         b"\x09\x0d\x04" + entry_operand(101) + b"," + entry_operand(142)
                         + b"," + entry_operand(163) + b"," + entry_operand(101)
                         + b"+1,\x03\x0a\x00\x00\x00")
        self.assertEqual(self.encoded("cls 0xF800"), b"\x09\x06\x04\x03\x00\xf8\x00\x00")

    def test_escapes_kept_as_written(self):
        self.assertEqual(self.encoded(r'prints "a\\b",0'), b'\x09\x0f\x08"a\\\\b",0')
        self.assertEqual(self.encoded(r't0.txt="a\"b\r"'), entry_operand(61) + b'="a\\"b\\r"')


class RefusedTest(unittest.TestCase):

    def test_expressions_refused(self):
        # An operator right after another, but a minus before a number, or at
        # the end; an expression as get's, print's, prints',
        # covx's, and cov's first operand, as crcputs' value, as a
        # destination, and as spstr's separator, each of which the Nextion
        # Editor refused ("Invalid Variables").
        for line in ("cls RED+", "cls RED*/1", "get sys0+1", "print n0.val+1",
                     "prints sys0+1,0", "covx sys0+1,t0.txt,0,0", "cov sys0+1,t0.txt,0",
                     "crcputs 0x01+1,4", "strlen t0.txt,sys0+1",
                     'spstr t0.txt,t0.txt,"a"+"b",0'):
            with self.subTest(line):
                self.assertFalse(encodable(line))
        # On K, wepo's value, which the Nextion Editor refused, and repo's
        # destination.
        for line in ("wepo 5+1,0", "repo n0.val+1,0"):
            with self.subTest(line):
                self.assertFalse(encodable(line, "K"))

    def test_texts_refused(self):
        # An escape the screen does not read, and a backslash alone before
        # the closing quote, which escapes it.
        for line in (r'prints "a\nb",0', r'prints "a\",0', r't0.txt="a\tb"'):
            with self.subTest(line):
                self.assertFalse(encodable(line))


class ConditionTest(unittest.TestCase):
    """In a condition, the Nextion Editor refused a text whose last escape is
    `\\\\`, right before its closing quote ("SYNTAX ERROR#1"). It compiled
    any other text with the escapes."""

    @classmethod
    def setUpClass(cls):
        cls.need = Need("code", "event", "", context=line_context(*_COMPONENTS))
        cls.project = _with(["sys0=1"])

    def test_texts_ending_in_an_escaped_backslash_are_refused(self):
        for condition in (r't0.txt=="\\"', r't0.txt=="a\\"', r'"\\"==t0.txt',
                          r't0.txt=="a"||t0.txt=="\\\\"'):
            with self.subTest(condition):
                self.assertFalse(covers_condition(condition, self.need))
                with self.assertRaisesRegex(StatementError, "SYNTAX ERROR"):
                    condition_blocks(condition, 0, _EVENT, CompileContext(self.project), "T")

    def test_other_escapes_are_covered(self):
        for condition in (r't0.txt=="a\\b"', r't0.txt!="\""', r'"a\"b"!=t0.txt',
                          r't0.txt=="\r"', r't0.txt=="\\\\a"'):
            with self.subTest(condition):
                self.assertTrue(covers_condition(condition, self.need))


class SpacesTest(unittest.TestCase):

    def test_spaces_by_commas_and_operators_are_dropped(self):
        # nxwright drops the spaces beside a command's commas and operators
        # as it reads a page's code, as the Nextion Editor's compile does, so
        # the encoder never sees them.
        def blocks(lines):
            return event_blocks(_with(lines))

        self.assertEqual(blocks(["fill 0,  0,10,   10,RED", "cls RED + 1"]),
                         blocks(["fill 0,0,10,10,RED", "cls RED+1"]))


class MatchedTest(unittest.TestCase):
    """What each family's rule covers, in an event whose page has the probes'
    components, and in program.s, which has no page."""

    @classmethod
    def setUpClass(cls):
        cls.context = line_context(*_COMPONENTS)

    def assert_covered(self, module, lines: list, covered: bool = True, series: str = "T"):
        rule, = module.MATCHED
        for line in lines:
            with self.subTest(line=line):
                need = Need("code", "event", line, context=self.context, series=series)
                self.assertEqual(rule.matches(need), covered)

    def test_expressions_attributes_and_hexadecimal_numbers(self):
        self.assert_covered(drawing_commands, ["cls n0.val+1", "fill n0.val,0,tm0.tim,10,0xF800",
                                               r'xstr 0,0,10,10,0,RED,WHITE,0,0,1,"a\\b"'])
        self.assert_covered(screen_commands, ["vis t0,n0.val*2", "randset tm0.tim,0x64"])
        self.assert_covered(serial_commands, ["prints t0.txt,n0.val+1", "get 0x10"])
        self.assert_covered(text_commands, ["covx 0x12,t0.txt,n1.val*2,0"])
        self.assert_covered(waveform_commands, ["add s0.id+0,0,n0.val*2"])
        self.assert_covered(crc_commands, ["crcrest 0+1,n0.val", r'crcputs "a\\b",0'])
        self.assert_covered(eeprom_and_gpio_commands, ["wept n0.val+1,0x10", "cfgpio 1+1,1,n0"],
                            series="K")
        self.assert_covered(if_statement, [r'if(t0.txt=="a\\b")'])

    def test_what_the_rules_leave_out(self):
        # A text's txt where a number goes, an attribute the type does not
        # write, and a text ending in an escaped backslash in a condition.
        self.assert_covered(drawing_commands, ["cls t0.val", "cls t0.txt"], covered=False)
        self.assert_covered(screen_commands, ["vis t0,t0.txt"], covered=False)
        self.assert_covered(if_statement, [r'if(t0.txt=="\\")'], covered=False)
        # program.s has no page, so no attribute.
        rule, = drawing_commands.MATCHED
        self.assertFalse(rule.matches(Need("code", "program.s", "cls n0.val+1")))
        self.assertTrue(rule.matches(Need("code", "program.s", "cls RED+1")))


if __name__ == "__main__":
    unittest.main()
