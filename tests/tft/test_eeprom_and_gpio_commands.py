"""The commands of the EEPROM and the GPIO pins that K has and T has not
(tft/instructions/eeprom_and_gpio_commands.py): the encoder's blocks for
the probes that keep fixtures, each command's block on K, and what the rule
covers.

The fixtures are the blocks of page0's Touch Release event, or of program.s,
as the statement encoder gave them once each probe matched the Nextion
Editor's file (tools/tft/probing/eeprom_and_gpio_probes.py).

Each test gives the encoder its own input: a probe's page and program.s,
made in memory from what the probe adds, or the base folder's facts, in a
Project of the facts the encoder reads (tests/tft/unit_inputs.py).
"""
import unittest

from nxwright.tft.compile_context import CompileContext
from tools.tft.probing import eeprom_and_gpio_probes, p_probes
from nxwright.tft.instructions import eeprom_and_gpio_commands
from nxwright.tft.matching import Need
from tools.tft.probing.number_probes import number_component
from nxwright.tft.statements import CodePlace, StatementError, encode_line
from tools.tft.probing.text_probes import text_component
from tools.tft.probing.statement_probes import kept_blocks
from tests.tft.line_context import line_context
from tests.tft.unit_inputs import piece, piece_names, probe_project, project_of


def facts(probe_name: str):
    """Returns the Project of facts of the probe `probe_name`'s page and
    program.s, made in memory."""
    return probe_project(next(probe for probe in eeprom_and_gpio_probes.PROBES
                              if probe.name == probe_name))


class FixtureTest(unittest.TestCase):
    """The encoder's blocks for each probe that keeps fixtures, on its page
    and program.s made in memory, against the probe's pieces: on T, and on
    P, which keeps the blocks of the same lines."""

    def test_each_part(self):
        probes = [probe for probe in eeprom_and_gpio_probes.PROBES if probe.fixtures] + [
            probe for probe in p_probes.PROBES
            if probe.fixtures and probe.name.startswith("p-eeprom-")]
        self.assertEqual(len(probes), 5)
        for probe in probes:
            with self.subTest(probe.name):
                self.assertEqual(kept_blocks(probe, probe_project(probe)),
                                 {each: piece(probe, each) for each in piece_names(probe)})


class EncodeTest(unittest.TestCase):
    """Each command's block on K, as the Nextion Editor wrote it, in page0's
    Touch Release event beside t0, n0, and n1."""

    @classmethod
    def setUpClass(cls):
        cls.project = facts("eeprom-and-gpio-each")

    def encoded(self, line: str) -> bytes:
        return encode_line(line, CodePlace(0, "page0", "up"), CompileContext(self.project))

    def test_each_command(self):
        for line, block in (("wepo n0.val,20", "09 0f 04 01 65 00 00 00 2c 32 30"),
                            ('wepo "abc",40', "09 0f 04 22 61 62 63 22 2c 34 30"),
                            ("repo t0.txt,20", "09 0e 04 01 3d 00 00 00 2c 32 30"),
                            ("wept sys0,sys1", "09 1a 04 05 00 00 00 00 2c 05 04 00 00 00"),
                            ("rept 0,10", "09 19 04 30 2c 31 30"),
                            ("cfgpio 4,3,0", "09 0d 08 34 2c 33 2c 30")):
            with self.subTest(line):
                self.assertEqual(self.encoded(line), bytes.fromhex(block))

    def test_cfgpio_s_component(self):
        # Its third argument, a component of the line's page, kept as written.
        self.assertEqual(self.encoded("cfgpio 2,1,n0"),
                         bytes.fromhex("09 0d 08 32 2c 31 2c 6e 30"))
        # A variable, written as its operand, as the Nextion Editor wrote it.
        self.assertEqual(self.encoded("cfgpio 1,1,sys0"),
                         bytes.fromhex("09 0d 08 31 2c 31 2c 05 00 00 00 00"))
        # The Nextion Editor refuses another name: "Invalid Component ID".
        with self.assertRaisesRegex(StatementError, "zz is neither a component"):
            self.encoded("cfgpio 0,0,zz")

    def test_t_has_none_of_them(self):
        project, place = project_of(), CodePlace()
        for line in ("wepo 5,0", "repo sys0,0", "wept 0,10", "rept 0,10", "cfgpio 0,0,0"):
            with self.subTest(line):
                with self.assertRaises(StatementError):
                    encode_line(line, place, CompileContext(project))


class MatchedTest(unittest.TestCase):
    """The lines eeprom_and_gpio_commands.MATCHED covers (matching.py)."""

    def setUp(self):
        self.rule, = eeprom_and_gpio_commands.MATCHED
        # On a page with the text t0 and the number n0.
        self.page = line_context(text_component(), number_component(y=60))

    def test_what_it_covers(self):
        for line in ("wepo 5,0", "wepo sys0,10", "wepo n0.val,20", "wepo t0.txt,30",
                     'wepo "abc",40', "repo n0.val,10", "repo t0.txt,20", "repo 5,0",
                     "wept 0,10", "rept sys0,sys1", "cfgpio 4,3,0", "cfgpio 2,1,n0",
                     "cfgpio 1,1,sys0"):
            with self.subTest(line):
                self.assertTrue(self.rule.matches(Need("code", "event", line,
                                                       context=self.page)))

    def test_what_it_leaves_out(self):
        # What the Nextion Editor refuses: a text or a txt where a number
        # goes, a name that is no component, and an expression; and a val of
        # a text, a txt of a number, and a component in program.s.
        for line in ('wepo 5,"a"', "wepo 5,t0.txt", 'rept "a",1', "cfgpio 0,0,zz",
                     "cfgpio t0.txt,0,0", "wept 0,t0.txt", "wepo 5+1,0", "repo t0.val,0",
                     "wepo n0.txt,0"):
            with self.subTest(line):
                self.assertFalse(self.rule.matches(Need("code", "event", line,
                                                        context=self.page)))
        self.assertFalse(self.rule.matches(Need("code", "program.s", "cfgpio 2,1,n0")))


if __name__ == "__main__":
    unittest.main()
