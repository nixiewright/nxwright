"""sys0, sys1, and sys2 are program.nx's int variables, as the Editor's new
project declares them, not system variables: the Editor refuses code naming
one that program.nx does not declare ("Invalid Variables"), and so does the
build, on the line naming it, in either language. A tab after `int`, which
the Editor refused alike, the build refuses in the Editor's own language;
nxlang writes a space instead."""
import unittest

from nxwright import NxwrightError
from nxwright.project.editor_language import EDITOR_SYSTEM_VARIABLES
from nxwright.source.lint import ERROR
from nxwright.source.project_files import build, extract
from nxwright.source.source_folder import folder_reader, read_folder_source
from nxwright.testing import SourceFolderRunner
from nxwright.testing.simulation import SYSTEM_START, Simulation
from tests.test_build_checks import add_component
from tests.test_folder_check import FolderTestCase

# The declaration the Editor's new project has, which the message names.
DECLARATION = "int sys0=0,sys1=0,sys2=0"


class UndeclaredProgramVariableTest(FolderTestCase):
    """In nxlang (FolderTestCase's language); the class below, in the
    Editor's own."""

    def assert_refused(self, file: str, line: int, name: str):
        [finding] = self.findings()
        self.assertEqual((finding.file, finding.line, finding.severity), (file, line, ERROR))
        self.assertIn(name, finding.message)
        self.assertIn(DECLARATION, finding.message)

    def test_a_page_naming_one_undeclared(self):
        self.write("program.nx", "page 0\n")
        self.write("pages/page0.nx", "on page0.load:\n  sys1 = 1\n")
        self.assert_refused("pages/page0.nx", 2, "sys1")

    def test_one_declared_alone(self):
        self.write("program.nx", "int sys2=7\npage 0\n")
        self.write("pages/page0.nx", "on page0.load:\n  sys2 = 1\n  sys0 = 1\n")
        self.assert_refused("pages/page0.nx", 3, "sys0")

    def test_program_nx_naming_one_undeclared(self):
        self.write("program.nx", "sys0 = 1\npage 0\n")
        self.assert_refused("program.nx", 1, "sys0")

    def test_declared_as_a_new_folder_declares_them(self):
        self.write("pages/page0.nx", "on page0.load:\n  sys0 = sys1 + sys2\n")
        self.assertEqual(self.findings(), [])

    def test_a_component_named_sys0_is_not_refused(self):
        # The Editor took a text named sys0; `sys0.txt` names the text.
        self.write("program.nx", "page 0\n")
        add_component(self.root / "pages" / "page0.page.toml", "sys0", "x")
        self.write("pages/page0.nx", 'on page0.load:\n  sys0.txt = "a"\n')
        self.assertEqual(self.findings(), [])

    def test_a_text_or_another_name_holding_them_is_not_refused(self):
        self.write("program.nx", "int sys10=0\npage 0\n")
        self.write("pages/page0.nx", 'on page0.load:\n  title.txt = "sys0"\n  sys10 = 1\n')
        self.assertEqual(self.findings(), [])


class UndeclaredProgramVariableEditorLanguageTest(UndeclaredProgramVariableTest):
    language = "nextion"

    def test_a_tab_after_int_is_refused(self):
        # The Editor read `int<TAB>count` as one name, "Invalid Variables",
        # as it compiled. The build, and so the test runner, refuse it.
        self.write("program.nx", "int sys0=0\nint\tcount=3\npage 0\n")
        self.write("pages/page0.nx", "on page0.load:\n  count = 1\n")
        [finding] = self.findings()
        self.assertEqual((finding.file, finding.line, finding.severity), ("program.nx", 2, ERROR))
        self.assertIn("a tab after int", finding.message)
        with self.assertRaisesRegex(NxwrightError, "a tab after int"):
            Simulation(self.root)

    def test_its_program_is_read_as_the_editor_reads_it(self):
        # nxlang's rule against a name starting with "_" is not the Editor's.
        self.write("program.nx", "int _tmp=0,sys0=1\npage 0\n")
        self.write("pages/page0.nx", "on page0.load:\n  sys0 = _tmp\n")
        self.assertEqual(self.findings(), [])


class TabAfterIntTest(FolderTestCase):
    """In nxlang, a tab after `int` declares as a space does: nxlang writes a
    space, which the Editor takes."""

    PROGRAM = "int sys0=0\nint\tcount=3\npage 0\n"

    def setUp(self):
        super().setUp()
        self.write("program.nx", self.PROGRAM)
        self.write("pages/page0.nx", "on page0.load:\n  count += 1\n")

    def test_written_with_a_space(self):
        self.assertEqual(self.findings(), [])
        program = read_folder_source(folder_reader(self.root)).build_program().decode("latin-1")
        self.assertIn("\r\nint count=3\r\n", program)
        # The test runner starts it at its value, as the screen does.
        values = SourceFolderRunner(self.root).run("page0", [("page0", "load")])
        self.assertEqual(values["count"], 4)

    def test_spaces_alone_are_kept(self):
        # The Editor takes them, and the build's output is as before.
        self.write("program.nx", "int  count=3\npage 0\n")
        program = read_folder_source(folder_reader(self.root)).build_program().decode("latin-1")
        self.assertIn("int  count=3\r\n", program)

    def test_extracting_keeps_it_as_written(self):
        project = self.root.parent / "project.HMI"
        build(self.root, project)
        extract(project, self.root)
        self.assertEqual(self.text("program.nx"), self.PROGRAM)


class ProgramVariableTest(unittest.TestCase):

    def test_they_are_no_system_variables(self):
        for name in ("sys0", "sys1", "sys2"):
            with self.subTest(name=name):
                self.assertNotIn(name, EDITOR_SYSTEM_VARIABLES)
                self.assertNotIn(name, SYSTEM_START)


class ProgramVariableSimulationTest(FolderTestCase):

    def test_the_simulator_starts_them_as_declared(self):
        self.write("program.nx", "int sys0=0,sys1=5\npage 0\n")
        globals_ = Simulation(self.root).globals
        self.assertEqual((globals_["sys0"], globals_["sys1"], "sys2" in globals_), (0, 5, False))


if __name__ == "__main__":
    unittest.main()
