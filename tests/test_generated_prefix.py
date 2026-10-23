"""nxlang's generated names start with "__", so a project's own names may
start with one "_". A probe of the Editor bore it out: it compiled names
starting with "__" as globals, number and text variables, and hotspots."""
import unittest

from nxwright.source.lint import ERROR
from nxwright.source.project_files import build
from nxwright.source.source_folder import switch_to_nxlang
from nxwright.testing import SourceFolderRunner
from nxwright.testing.looks import value_group
from nxwright.testing.simulation import Simulation
from tests.test_folder_check import FolderTestCase


def variable(name: str, value: int) -> str:
    """A page file's table of a number variable `name` holding `value`."""
    return '\n[[component]]\nname = "%s"\ntype = "variable"\nval = %d\n' % (name, value)


class OwnNamesTest(FolderTestCase):
    """A project's own names starting with one "_", in a folder in the
    Editor's own language, then in nxlang."""
    language = "nextion"

    def test_they_switch_to_nxlang_and_build(self):
        self.write("program.nx", "int sys0=0,sys1=0,sys2=0\nint _tmp=0\npage 0\n")
        self.write("pages/page0.page.toml", self.text("pages/page0.page.toml") +
                   variable("_x", 5))
        self.write("pages/page0.nx", "on page0.load:\n  _tmp=_x.val\n")
        switch_to_nxlang(self.root)
        build(self.root, self.root.parent / "switched.HMI")
        self.assertIn('language = "nxlang"', self.text("app.toml"))

    def test_the_simulator_starts_a_double_underscore_name_from_its_page_file(self):
        # In the Editor's own language nothing is generated, not even __v0.
        self.write("pages/page0.page.toml", self.text("pages/page0.page.toml") +
                   variable("__v0", 5))
        self.write("pages/page0.nx", "on page0.load:\n  sys0=__v0.val\n")
        self.assertEqual(Simulation(self.root).values()["sys0"], 5)


class GeneratedNamesTest(FolderTestCase):
    """In nxlang (FolderTestCase's language)."""

    def test_nxlang_refuses_a_name_starting_with_its_prefix(self):
        for file, text, line in [
                ("program.nx", "int sys0=0,sys1=0,sys2=0\nint __x=0\npage 0\n", 2),
                ("pages/page0.nx", "on page0.load:\n  var __n = 1\n", 2)]:
            with self.subTest(text=text):
                self.write(file, text)
                [finding] = self.findings()
                self.assertEqual((finding.file, finding.line, finding.severity),
                                 (file, line, ERROR))
                self.assertIn("'__'", finding.message)
                self.write("program.nx", "int sys0=0,sys1=0,sys2=0\npage 0\n")
                self.write("pages/page0.nx", "")

    def test_nxlang_takes_one_underscore(self):
        self.write("program.nx", "int sys0=0,sys1=0,sys2=0\nint _tmp=0\npage 0\n")
        self.write("pages/page0.page.toml", self.text("pages/page0.page.toml") +
                   variable("_a1", 5))
        self.write("pages/page0.nx", 'on page0.load:\n  var _n = _a1.val\n  _tmp = _n\n'
                   '  title.txt = "x" + title.txt\n')
        self.assertEqual(self.findings(), [])
        # The simulator starts the project's own `_a1` from its page file.
        self.assertEqual(Simulation(self.root).values()["_tmp"], 5)

    def test_the_generated_names_start_with_double_underscore(self):
        # A local and a text temporary: a program.s global and a component.
        self.write("pages/page0.nx", 'on page0.load:\n  var n = 1\n'
                   '  title.txt = "a" + title.txt + "b"\n  sys0 = n\n')
        code, start = SourceFolderRunner(self.root).compile("page0")
        names = [name for name in start if name.startswith("_")]
        self.assertTrue(names)
        self.assertTrue(all(name.startswith("__") for name in names), names)


class DebuggerGroupsTest(unittest.TestCase):

    def test_generated_names_are_grouped_apart_in_nxlang_alone(self):
        self.assertEqual([value_group(name, True) for name in
                          ("__g0_0", "__v0.txt", "_tmp", "_x.val", "sys0")],
                         ["Generated", "Generated", "Program", "Page", "Program"])
        # In the Editor's own language, nothing is generated.
        self.assertEqual([value_group(name, False) for name in ("__g0_0", "__v0.txt")],
                         ["Program", "Page"])


if __name__ == "__main__":
    unittest.main()
