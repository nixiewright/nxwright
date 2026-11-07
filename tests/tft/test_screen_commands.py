"""The commands of components and of the screen
(tft/instructions/screen_commands.py): their blocks, as the probes of
screen_command_probes.py kept them once they matched the Nextion Editor's
file, and the lines refused.

Each test gives the encoder its own input: a probe's page and program.s,
made in memory from what the probe adds, or the base folder's facts, in a
Project of the facts the encoder reads (tests/tft/unit_inputs.py).
"""
import unittest

from nxwright.project.object_types import TYPE_NAMES

from nxwright.tft.compile_context import CompileContext
from tools.tft.probing import p_probes, screen_command_probes
from tools.tft.probing.attribute_probes import with_attributes
from nxwright.tft.instructions import screen_commands
from nxwright.tft.matching import Need, matched_rules, project_needs, unmatched
from nxwright.tft.statements import CodePlace, StatementError, encodable, encode_line
from tools.tft.probing.statement_probes import kept_blocks
from tests.tft.unit_inputs import page, piece, piece_names, probe_project, project_of


def built_with_a_text_and_two_numbers():
    """Returns the Project of facts of the T base folder with the text t0 and
    the numbers n0 and n1 on page0, as attribute_probes.with_attributes puts
    them there, in strict Nextion syntax."""
    change = with_attributes([])
    return project_of(page(*change.components, strict=True), strict=True)


class FixtureTest(unittest.TestCase):
    """The encoder's blocks for each probe that keeps fixtures, on its page
    and program.s made in memory, against the probe's pieces: on T, and on
    P, which keeps the blocks of the same lines."""

    def test_each_probe_s_fixtures(self):
        probes = [probe for probe in screen_command_probes.PROBES if probe.fixtures] + [
            probe for probe in p_probes.PROBES
            if probe.fixtures and probe.name.startswith("p-screen-")]
        self.assertEqual(len(probes), 5)
        for probe in probes:
            with self.subTest(probe.name):
                self.assertEqual(kept_blocks(probe, probe_project(probe)),
                                 {each: piece(probe, each) for each in piece_names(probe)})


class LineTest(unittest.TestCase):

    def test_lines_refused(self):
        # An argument to a command that takes none, which the Nextion Editor
        # refused ("Invalid number of arguments"); a component without its
        # operand, and a second argument to ref, which nxwright's build
        # refuses; a txt for a component, which the Nextion Editor refused
        # ("Invalid Component ID"); and two spaces after a comma, which
        # nxwright's build drops before the encoder sees the line.
        for line in ("doevents 1", "vis t0", "ref t0,1", "vis t0.txt,0",
                     "tsw t0,  1", "randset 0"):
            with self.subTest(line):
                self.assertFalse(encodable(line))

    def test_ids_and_the_page_s_name(self):
        # As the Nextion Editor wrote them on T: an ID as any number, as
        # written up to 3 characters and as 03 and its value past them, and
        # the page's own name as written.
        project = built_with_a_text_and_two_numbers()
        place = CodePlace(0, "page0", "up")
        for line, block in (("vis 256,0", "09 05 04 32 35 36 2c 30"),
                            ("vis 1000,0", "09 05 04 03 e8 03 00 00 2c 30"),
                            ("vis 007,0", "09 05 04 30 30 37 2c 30"),
                            ("vis -1,0", "09 05 04 2d 31 2c 30"),
                            ("vis page0,0", "09 05 04 70 61 67 65 30 2c 30"),
                            ("click page0,1", "09 00 08 70 61 67 65 30 2c 31"),
                            ("ref 0007", "09 03 04 03 07 00 00 00"),
                            ("ref -100", "09 03 04 03 9c ff ff ff")):
            with self.subTest(line):
                self.assertEqual(encode_line(line, place,
                                             CompileContext(project)), bytes.fromhex(block))

    def test_a_page_s_name_in_program_s(self):
        # The Nextion Editor refused one on T and K: "Invalid Component ID".
        project = built_with_a_text_and_two_numbers()
        for line in ("vis page0,0", "ref page0"):
            with self.subTest(line), self.assertRaisesRegex(
                    StatementError, "page0 is neither a component of program.s nor a variable"):
                encode_line(line, CodePlace(), CompileContext(project))

    def test_a_variable_as_the_component_in_program_s(self):
        # program.s has no page, so a name there is a variable's, written as
        # its operand, as the Nextion Editor wrote these on T. It refused a
        # name that is neither: "Invalid Component ID".
        project = project_of(page(strict=True), strict=True, declarations=("int a=1",))
        for line, block in (("vis sys0,0", "09 05 04 05 00 00 00 00 2c 30"),
                            ("tsw a,1", "09 09 04 05 0c 00 00 00 2c 31"),
                            ("ref dim", "09 03 04 04 04 03 00 00"),
                            ("vis RED,0", "09 05 04 04 04 01 00 00 2c 30")):
            with self.subTest(line):
                self.assertEqual(encode_line(line, CodePlace(),
                                             CompileContext(project)), bytes.fromhex(block))
        with self.assertRaisesRegex(StatementError,
                                    "zz is neither a component of program.s nor a variable"):
            encode_line("vis zz,0", CodePlace(), CompileContext(project))


class MatchedTest(unittest.TestCase):

    def test_the_rule(self):
        rule, = screen_commands.MATCHED
        types = {name: number for number, name in TYPE_NAMES.items()}
        # An event's line, on a page with the texts t0 and t1.
        page = {"components": {"t0": types["text"], "t1": types["text"]}, "page": "page0"}
        for subject, line in (("event", "vis t0,0"), ("event", "ref t1"), ("event", "doevents"),
                              ("event", "vis 255,1"), ("program.s", "ref 0"),
                              ("program.s", "randset 0,100"), ("event", "vis page0,0"),
                              ("event", "ref 1000"), ("event", "vis -1,0"),
                              ("program.s", "ref 007")):
            with self.subTest(line):
                context = page if subject == "event" else {}
                self.assertTrue(rule.matches(Need("code", subject, line, context=context)))
        # A component not on the line's page, another page's name, and any
        # name in program.s.
        for subject, line in (("event", "vis t9,0"), ("event", "vis page1,0"),
                              ("program.s", "vis t0,0"), ("program.s", "vis page0,0")):
            with self.subTest(line):
                context = page if subject == "event" else {}
                self.assertFalse(rule.matches(Need("code", subject, line, context=context)))
        self.assertFalse(rule.matches(Need("code", "event", "sys0=1", context=page)))
        # A variable as the component in program.s, of the series' or of
        # program.s's int variables, but no other name.
        variables = {"variables": ("sys0", "sys1", "sys2", "a")}
        for line in ("vis sys0,0", "tsw a,1", "ref dim", "vis RED,0"):
            with self.subTest(line):
                self.assertTrue(rule.matches(Need("code", "program.s", line, context=variables,
                                                  series="T")))
        self.assertFalse(rule.matches(Need("code", "program.s", "vis zz,0", context=variables,
                                           series="T")))

    def test_the_check_gives_program_s_s_int_variables(self):
        project = project_of(page(strict=True), strict=True, fonts=0, program=("tsw a,1",),
                             declarations=("int a=1",))
        self.assertEqual(unmatched(project_needs(project), matched_rules()), [])

    def test_each_probe_s_project(self):
        # Every need of each probe's project is matched, as a compile checks
        # them.
        for probe in screen_command_probes.PROBES:
            with self.subTest(probe.name):
                project = probe_project(probe)
                self.assertEqual(unmatched(project_needs(project), matched_rules()), [])


if __name__ == "__main__":
    unittest.main()
