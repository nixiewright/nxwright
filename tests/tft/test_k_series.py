"""The K series (tools/tft/probing/k_probes.py): the blocks of its probe of its
own system variables, as it kept them once it matched the Nextion Editor's
file, what the check matches on K, and K's tables beside T's.

Each test gives the function it checks its own input: a probe's program.s
made in memory, or the base folder's facts, in a Project of the facts it
reads (tests/tft/unit_inputs.py). The whole compile of a blank project on K is
compared whole in tests/tft/test_whole_files.py.
"""
import unittest

from nxwright.tft.compile_context import CompileContext
from nxwright.tft import control_statements, statements
from tools.tft.probing import k_probes
from nxwright.tft.matching import Need, matched_rules
from tools.tft.probing.statement_probes import kept_blocks
from tests.tft.unit_inputs import piece, piece_names, probe_project, project_of

# The commands K has and T has not (instructions/eeprom_and_gpio_commands.py).
_OWN_COMMANDS = {"wepo", "repo", "wept", "rept", "cfgpio"}
# The system variables K has and T has not.
_OWN_SYSTEM_VARIABLES = ({"pio%d" % pin for pin in range(8)}
                         | {"pwm%d" % pin for pin in range(4, 8)} | {"pwmf"}
                         | {"rtc%d" % part for part in range(7)})


class FixtureTest(unittest.TestCase):
    """The probes of K that keep fixtures: the whole compile of a blank
    project, compared whole as K's sample, and the probe of K's own system
    variables, whose blocks the encoder gives on its program.s made in
    memory."""

    def test_the_probes_that_keep_fixtures(self):
        self.assertEqual({probe.name for probe in k_probes.PROBES if probe.fixtures}, {
            "k-compile-T-blank",
            "k-statements-own-system-variables",
        })

    def test_its_own_system_variables_blocks(self):
        probe = next(probe for probe in k_probes.PROBES
                     if probe.name == "k-statements-own-system-variables")
        self.assertEqual(kept_blocks(probe, probe_project(probe)),
                         {name: piece(probe, name) for name in piece_names(probe)})


class MatchedTest(unittest.TestCase):

    def test_the_series_and_its_model(self):
        rules = matched_rules()
        for need in (Need("series", "K"), Need("model", "NX4832K035")):
            with self.subTest(need.subject):
                self.assertTrue(any(rule.matches(need) for rule in rules))
        # A model nxwright does not know is refused.
        self.assertFalse(any(rule.matches(Need("model", "NX0000F000", series="F"))
                             for rule in rules))


class TableTest(unittest.TestCase):
    """K has every command, system variable, and colour T has, numbered its
    own way only where the probes showed it, and commands and system
    variables of its own."""

    def test_the_same_names(self):
        for table in (statements.COLOURS, statements.COMMANDS, control_statements.COMPARISONS):
            self.assertEqual(set(table["K"]), set(table["T"]))
        # K's system variables are T's and its own.
        self.assertEqual(set(statements.SYSTEM_VARIABLES["K"]),
                         set(statements.SYSTEM_VARIABLES["T"]) | _OWN_SYSTEM_VARIABLES)
        # Each module of commands gives K T's, but one that gives K's own,
        # and one of P's own alone, which gives K none.
        own = set()
        for module in statements._instruction_modules():
            if "K" in getattr(module, "COMMANDS", {}):
                with self.subTest(module.__name__):
                    if "T" in module.COMMANDS:
                        self.assertEqual(set(module.COMMANDS["K"]), set(module.COMMANDS["T"]))
                    else:
                        own |= set(module.COMMANDS["K"])
        self.assertEqual(own, _OWN_COMMANDS)

    def test_the_same_but_for_the_number(self):
        # A command differs between T and K by its number alone: its table,
        # its arguments, and how they are kept stay T's. K's own have none
        # on T.
        for module in statements._instruction_modules():
            if "T" not in getattr(module, "COMMANDS", {}):
                continue
            for name, command in module.COMMANDS["K"].items():
                with self.subTest(name):
                    t_command = module.COMMANDS["T"][name]
                    self.assertEqual(command.table, t_command.table)
                    self.assertEqual((command.arguments, command.raw, command.component),
                                     (t_command.arguments, t_command.raw, t_command.component))

    def test_its_own_system_variables(self):
        # Read and set in program.s on K, as the Nextion Editor wrote them:
        # pio0 is 0x08 in table 4, rtc0 0x06, and pwmf 0x22. T has none of
        # them, so its encoder refuses them as names it does not know.
        k_project, t_project = project_of(series="K"), project_of()
        place = statements.CodePlace()
        self.assertEqual(statements.encode_line("pio0=sys0", place, CompileContext(k_project)),
                         b"\x04\x04\x08\x00\x00=\x05\x00\x00\x00\x00")
        self.assertEqual(statements.encode_line("sys0=rtc0", place, CompileContext(k_project)),
                         b"\x05\x00\x00\x00\x00=\x04\x04\x06\x00\x00")
        self.assertEqual(statements.encode_line("sys0=pwmf", place, CompileContext(k_project)),
                         b"\x05\x00\x00\x00\x00=\x04\x04\x22\x00\x00")
        with self.assertRaisesRegex(statements.StatementError, "pio0 is no variable"):
            statements.encode_line("pio0=sys0", place, CompileContext(t_project))


if __name__ == "__main__":
    unittest.main()
