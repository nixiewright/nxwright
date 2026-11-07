"""The numbers an older Nextion Editor gives commands, system variables, and
colours (tft/decompiling/numbers.py), in each range of releases from 1.60.1
to 1.68.1.

The probes of the Nextion Editor 1.65.1 on F (tools/tft/probing/editor_1_65_1_probes.py)
keep that Editor's user code. Each is decoded by 1.65.1's numbers, and each of
its pages and program.s come back as the same source as the user code the
compile writes for the same project, by 1.68.2's numbers. The probes of the
Nextion Editor 1.63.3's code (tools/tft/probing/editor_1_63_3_code_probes.py), and
those of program.s of each release where a change begins
(tools/tft/probing/release_probes.py), do the same with program.s alone. The
numbers the probes showed (ResearchNotes/tft/older-editors.md) are checked one by
one too.
"""
from dataclasses import replace
import unittest

from nxwright.tft import frame
from nxwright.tft.decompiling import numbers
from nxwright.tft.decompiling.code import decoded_lines
from nxwright.tft.decompiling.decoded_file import CodeRun, decoded_user_code
from nxwright.tft.decompiling.page_files import page_files
from tools.tft.probing import (editor_1_60_1_probes, editor_1_61_1_probes, editor_1_63_1_probes,
                           editor_1_63_3_code_probes, editor_1_65_0_probes,
                           editor_1_65_1_probes, editor_1_67_1_probes, editor_1_68_1_probes)
from tools.tft.probing.statement_probes import program_blocks
from nxwright.tft.tft_file import layout_of, split_blocks
from tests.tft.test_decompiling_page_files import _names
from tests.tft.unit_inputs import decoded_file_of, piece, probe_facts, probe_project, user_code_of

_V1633, _V1651, _V1682 = (1, 63, 3), (1, 65, 1), (1, 68, 2)
# The modules of the probes of each release where a change begins
# (tools/tft/probing/release_probes.py).
_RELEASE_MODULES = (editor_1_60_1_probes, editor_1_61_1_probes, editor_1_63_1_probes,
                    editor_1_65_0_probes, editor_1_67_1_probes, editor_1_68_1_probes)


class NumbersTest(unittest.TestCase):
    """The numbers the probes showed, against 1.68.2's."""

    def assert_commands(self, series: str, version: tuple, lacked: set, numbered: dict):
        """Checks that a file of `series` and `version` lacks the commands
        `lacked`, and numbers those of `numbered` as it gives them."""
        older = numbers.commands(series, version)
        self.assertEqual(lacked & set(older), set())
        for name, number in numbered.items():
            with self.subTest(series=series, command=name):
                self.assertEqual(older[name], number)

    def test_commands_of_f_of_1_65_1(self):
        # Below the command it lacks, a table's numbers are 1.68.2's; above
        # it, one less.
        self.assert_commands("F", _V1651, {"beep", "cfgpio"}, {
            "xnum": (0x0e, 4), "wepo": (0x10, 4), "pa_q": (0x11, 4), "init": (0x1c, 4),
            "covx": (0x22, 4), "strlen": (0x0c, 8), "showqq": (0x0d, 8), "piccolor": (0x21, 8),
            "doevents": (0x22, 8), "timerset": (0x23, 8), "setbaudz": (0x26, 8)})
        newest = numbers.commands("F", _V1682)
        self.assertEqual((newest["beep"], newest["doevents"]), ((0x11, 4), (0x23, 8)))

    def test_commands_of_1_63_3(self):
        self.assert_commands("T", _V1633, {"getv"}, {
            "rest": (0x19, 4), "draw": (0x1a, 4), "covx": (0x1b, 4), "doevents": (0x21, 8)})
        self.assert_commands("K", _V1633, {"getv"}, {
            "rest": (0x1d, 4), "draw": (0x1e, 4), "covx": (0x1f, 4)})
        # P lacks two commands nxwright has no name for too, below page and
        # crcputs.
        self.assert_commands("P", _V1633, {"beep", "meup", "gets", "sets", "getv", "beepset"}, {
            "xpic": (0x0a, 4), "page": (0x0b, 4), "fill": (0x0e, 4), "wepo": (0x11, 4),
            "cirs": (0x17, 4), "addt": (0x19, 4), "init": (0x1a, 4), "rest": (0x1f, 4),
            "draw": (0x20, 4), "covx": (0x21, 4), "finddir": (0x1e, 8), "crcputs": (0x1f, 8),
            "randset": (0x20, 8), "crcrest": (0x22, 8), "com_star": (0x2c, 8),
            "doevents": (0x2e, 8)})
        # From 1.65 on, as 1.68.2.
        self.assertEqual(numbers.commands("P", _V1651), numbers.commands("P", _V1682))

    def test_commands_of_each_release_where_a_change_begins(self):
        # The numbers the probes of each such release gave, and the last
        # release before it, in the ranges of the table.
        self.assert_commands("T", (1, 60, 1), {"getv", "spstr"}, {
            "print": (0x03, 8), "printh": (0x0a, 8), "doevents": (0x20, 8),
            "setbaudz": (0x24, 8), "draw": (0x1a, 4), "covx": (0x1b, 4)})
        self.assert_commands("T", (1, 61, 1), {"getv"}, {
            "spstr": (0x03, 8), "print": (0x04, 8), "draw": (0x1a, 4)})
        self.assert_commands("K", (1, 60, 1), {"getv", "spstr"}, {
            "print": (0x03, 8), "printh": (0x0a, 8), "doevents": (0x21, 8),
            "setbaudz": (0x25, 8), "draw": (0x1e, 4), "covx": (0x1f, 4)})
        p_before_1_63 = {"getv", "beep", "meup", "gets", "sets", "beepset", "xnum", "cuts",
                         "cfguart"}
        self.assert_commands("P", (1, 60, 1), p_before_1_63 | {"spstr"}, {
            "page": (0x0b, 4), "repo": (0x0f, 4), "pa_q": (0x11, 4), "addt": (0x17, 4),
            "draw": (0x1e, 4), "print": (0x04, 8), "printh": (0x0e, 8), "crcputs": (0x1e, 8),
            "crcrest": (0x20, 8), "doevents": (0x2c, 8), "setbaudz": (0x30, 8)})
        self.assert_commands("P", (1, 61, 2), p_before_1_63, {
            "pa_q": (0x11, 4), "addt": (0x17, 4), "draw": (0x1e, 4), "crcputs": (0x1f, 8),
            "crcrest": (0x21, 8), "doevents": (0x2d, 8), "setbaudz": (0x31, 8)})
        self.assert_commands("P", (1, 63, 1), {"getv", "beep", "meup", "gets", "sets", "beepset"},
                             {"xnum": (0x0f, 4), "cuts": (0x18, 4), "cfguart": (0x21, 8),
                              "setbaudz": (0x32, 8)})
        self.assert_commands("F", (1, 63, 1), {"beep", "cfgpio", "xnum", "cuts", "gets", "sets"}, {
            "repo": (0x0e, 4), "wepo": (0x0f, 4), "pa_q": (0x10, 4), "getv": (0x1c, 4),
            "draw": (0x1d, 4), "showqq": (0x0d, 8), "piccolor": (0x21, 8),
            "doevents": (0x22, 8), "setbaudz": (0x26, 8)})
        self.assert_commands("F", (1, 65, 0), {"beep", "cfgpio"}, {
            "pa_q": (0x11, 4), "gets": (0x18, 4), "sets": (0x19, 4), "cuts": (0x1a, 4),
            "getv": (0x20, 4), "draw": (0x21, 4)})
        self.assert_commands("F", (1, 67, 1), {"cfgpio"}, {
            "beep": (0x11, 4), "pa_q": (0x12, 4), "showqq": (0x0d, 8), "piccolor": (0x21, 8),
            "doevents": (0x22, 8), "setbaudz": (0x26, 8)})
        # F and E of 1.68.1 number their code as 1.68.2 does.
        for series in ("F", "E"):
            self.assertEqual(numbers.commands(series, (1, 68, 1)),
                             numbers.commands(series, _V1682))
            self.assertEqual(numbers.operands(series, (1, 68, 1)),
                             numbers.operands(series, _V1682))

    def test_system_variables_of_each_release_where_a_change_begins(self):
        # P before 1.63.1 lacks scache, and those above it in table 8 are one
        # less; F before 1.68.1 takes T's numbers but lowpower's and portbusy's.
        for version in ((1, 60, 1), (1, 61, 2)):
            older = numbers.operands("P", version)
            self.assertNotIn("scache", older)
            self.assertEqual((older["volume"], older["portbusy"]), ((8, 0x11), (8, 0x14)))
        self.assertEqual(numbers.operands("P", (1, 63, 1)), numbers.operands("P", _V1682))
        older = numbers.operands("F", (1, 67, 1))
        self.assertEqual((older["baud"], older["BLUE"], older["portbusy"]),
                         ((4, 0x0e), (4, 0x0b), (8, 0x12)))
        self.assertNotIn("pio0", older)

    def test_system_variables_and_colours(self):
        older = numbers.operands("F", _V1651)
        self.assertNotIn("pio0", older)
        self.assertNotIn("pwmf", older)
        for name, key in (("baud", (4, 0x0e)), ("addr", (4, 0x13)), ("BLUE", (4, 0x0b)),
                          ("GRAY", (4, 0x0c)), ("lowpower", (8, 0x11)), ("portbusy", (8, 0x12))):
            with self.subTest(name):
                self.assertEqual(older[name], key)
        self.assertEqual(numbers.operands("F", _V1682)["baud"], (4, 0x1a))
        # 1.63.3 numbers them as 1.68.2 does.
        for series in ("T", "K", "P"):
            self.assertEqual(numbers.operands(series, _V1633), numbers.operands(series, _V1682))

    def test_blocks_as_written(self):
        # doevents's block, a block of no command, and a file of 1.68.2.
        self.assertEqual(numbers.as_written(frame.DOEVENTS["F"], "F", _V1651), b"\x09\x22\x08")
        self.assertEqual(numbers.as_written(frame.DOEVENTS["P"], "P", _V1633), b"\x09\x2e\x08")
        self.assertEqual(numbers.as_written(b"sys0=1", "F", _V1651), b"sys0=1")
        self.assertEqual(numbers.as_written(frame.DOEVENTS["F"], "F", _V1682),
                         frame.DOEVENTS["F"])

    def test_labels_counted(self):
        # 1.65.1 numbers its "S " blocks its own way, on T as on F.
        self.assertFalse(numbers.counts_labels(_V1651))
        self.assertTrue(numbers.counts_labels(_V1682))


class OlderProbesTest(unittest.TestCase):
    """Each probe of an older Nextion Editor, decoded by its numbers."""

    def test_each_probe_of_1_65_1_comes_back_as_the_compile_s(self):
        for probe in editor_1_65_1_probes.PROBES:
            project = probe_facts(probe)
            model, encoding = project.settings.model.name, project.settings.encoding
            theirs = decoded_user_code(user_code_of(probe), "F", model, 0, encoding, _V1651)
            ours = decoded_user_code(frame.user_code(project), "F", model, 0, encoding)
            names = _names(project)
            with self.subTest(probe.name):
                self.assertEqual(decoded_lines(theirs.program, None, theirs),
                                 decoded_lines(ours.program, None, ours))
                self.assertEqual(len(theirs.pages), len(ours.pages))
                for page_theirs, page_ours in zip(theirs.pages, ours.pages):
                    self.assertEqual(page_files(page_theirs, theirs, names),
                                     page_files(page_ours, ours, names))
        self.assertEqual(len(editor_1_65_1_probes.PROBES), 15)

    def test_each_probe_of_1_63_3_comes_back_as_the_compile_s(self):
        # program.s's blocks follow the first blocks, those but the first,
        # which is a piece of its own; the Nextion Editor's page 0 and 0 word
        # end them.
        skipped = layout_of(_V1633).first_blocks - 1
        for probe in editor_1_63_3_code_probes.PROBES:
            project = probe_project(probe)
            decoded, attribute_of_entry = decoded_file_of(project)
            blocks = split_blocks(piece(probe, "program-s"))[skipped:]
            appended = numbers.as_written(frame.APPENDED_PAGE_0[probe.base], probe.base, _V1633)
            ours = split_blocks(program_blocks(project)["program-s"])
            with self.subTest(probe.name):
                self.assertEqual(blocks[-2:], [appended, b""])
                self.assertEqual(
                    decoded_lines(CodeRun(0, blocks[:-2]), None, replace(decoded, version=_V1633),
                                  attribute_of_entry),
                    decoded_lines(CodeRun(0, ours), None, decoded, attribute_of_entry))
        self.assertEqual(len(editor_1_63_3_code_probes.PROBES), 26)

    def test_each_release_s_probe_of_program_s_comes_back_as_the_compile_s(self):
        # The probe of program.s of each release where a change begins, on
        # each series it has, decoded by that release's numbers.
        checked = 0
        for module in _RELEASE_MODULES:
            skipped = layout_of(module.VERSION).first_blocks - 1
            for probe in module.PROBES:
                if not probe.name.endswith("-program"):
                    continue
                project = probe_project(probe)
                decoded, attribute_of_entry = decoded_file_of(project)
                blocks = split_blocks(piece(probe, "program-s"))[skipped:]
                appended = numbers.as_written(frame.APPENDED_PAGE_0[probe.base], probe.base,
                                              module.VERSION)
                ours = split_blocks(program_blocks(project)["program-s"])
                with self.subTest(probe.name):
                    self.assertEqual(blocks[-2:], [appended, b""])
                    self.assertEqual(
                        decoded_lines(CodeRun(0, blocks[:-2]), None,
                                      replace(decoded, version=module.VERSION),
                                      attribute_of_entry),
                        decoded_lines(CodeRun(0, ours), None, decoded, attribute_of_entry))
                checked += 1
        # T, K, and P on 1.60.1 and 1.61.1; those and F on 1.63.1 and
        # 1.65.0; F on 1.67.1; F and E on 1.68.1.
        self.assertEqual(checked, 3 + 3 + 4 + 4 + 1 + 2)


if __name__ == "__main__":
    unittest.main()
