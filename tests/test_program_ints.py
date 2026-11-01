"""The int declarations of program.nx that the Nextion Editor 1.68.2 refused
as it compiled, on an NX4832T035, and those it compiled. The build refuses
them on their line, with the Nextion Editor's words, in either language,
but where nxlang writes a form the Nextion Editor compiles: it moves a late
int above program.nx's other code, and keeps the low 32 bits of a decimal
starting value past 32 bits. The test runner and the simulator start each
int at the value the build writes."""
import unittest

from nxwright.project.editor_language import EDITOR_COLOURS, EDITOR_PROGRAM_DECLARATION
from nxwright.source.lint import ERROR
from nxwright.source.source_folder import folder_reader, read_folder_source
from nxwright.testing import SourceFolderRunner
from nxwright.testing.simulation import Simulation
from tests.test_folder_check import FolderTestCase


class ProgramIntTest(FolderTestCase):
    """In strict Nextion syntax; the class below runs the same tests in
    nxlang."""
    language = "nextion"

    def setUp(self):
        super().setUp()
        self.program = self.text("program.nx")

    def declare(self, *lines: str):
        """Writes program.nx as a new folder has it, with `lines` right after
        its declaration of sys0 to sys2, so that they start on line 4,
        before its other code."""
        self.write("program.nx", self.program.replace(
            EDITOR_PROGRAM_DECLARATION, "\n".join((EDITOR_PROGRAM_DECLARATION,) + lines), 1))

    def assert_refused(self, file: str, line: int, words: str):
        [finding] = self.findings()
        self.assertEqual((finding.file, finding.line, finding.severity), (file, line, ERROR))
        self.assertIn('("%s")' % words, finding.message)

    def test_a_name_declared_twice(self):
        for lines, line in ((("int a=1,a=2",), 4), (("int a=1", "int a=2"), 5),
                            (("int sys1=4",), 4)):
            with self.subTest(lines=lines):
                self.declare(*lines)
                self.assert_refused("program.nx", line, "Repeated definition global variable name")
        # Letter case tells names apart, as the Nextion Editor compiled.
        self.declare("int a=1,A=2")
        self.assertEqual(self.findings(), [])

    def test_a_colour_s_name(self):
        for colour in EDITOR_COLOURS:
            with self.subTest(colour=colour):
                self.declare("int %s=1" % colour)
                self.assert_refused("program.nx", 4, "Illegal name")
        self.declare("int Red=1")
        self.assertEqual(self.findings(), [])

    def test_a_name_past_32_characters(self):
        self.declare("int %s=1" % ("a" * 33))
        self.assert_refused("program.nx", 4, "Illegal global variable name length")
        self.declare("int %s=1" % ("a" * 32))
        self.assertEqual(self.findings(), [])

    def test_an_int_in_an_event(self):
        self.write("pages/page0.nx", "on page0.load:\n  int i=5\n")
        self.assert_refused("pages/page0.nx", 2,
                            "Global variable definitions must precede all code in the program.c")

    def test_an_int_in_a_macro(self):
        self.write("macros.nx", "macro m0:\n  int x=3\n  sys0=1\n")
        self.write("program.nx", self.text("program.nx").replace("page 0", "call m0\npage 0"))
        self.assert_refused("macros.nx", 2,
                            "Global variable definitions must precede all code in the program")

    def test_a_decimal_starting_value_past_32_bits(self):
        for value in ("2147483648", "-2147483649", "4294967295"):
            with self.subTest(value=value):
                self.declare("int a=%s" % value)
                self.assert_refused("program.nx", 4,
                                    "Initial value for a global variable must be a constant")
        self.declare("int a=2147483647,b=-2147483648")
        self.assertEqual(self.findings(), [])

    def test_an_indented_int(self):
        # The build keeps its indentation. The simulator still reads it as a
        # declaration, not as code to run.
        self.declare("  int a=5")
        self.assertEqual(self.findings(), [])
        self.assertEqual(Simulation(self.root).globals["a"], 5)

    def test_an_int_after_other_code(self):
        self.write("program.nx", self.text("program.nx").replace("page 0", "int late=1\npage 0"))
        self.assert_refused("program.nx", 8,
                            "Global variable definitions must precede all code in the program")


class NxlangProgramIntTest(ProgramIntTest):
    language = "nxlang"

    def run_load(self) -> dict:
        """Returns the values after page0's load event, which sets sys0, as
        the test runner runs it."""
        self.write("pages/page0.nx", "on page0.load:\n  sys0 = 1\n")
        return SourceFolderRunner(self.root).run("page0", [("page0", "load")])

    def test_an_int_in_an_event(self):
        # nxlang's message adds what declares a local.
        super().test_an_int_in_an_event()
        self.assertIn("var declares a local", self.findings()[0].message)

    def test_an_int_in_a_function(self):
        self.write("pages/page0.nx", "function f():\n  int i=5\n\non page0.load:\n  f()\n")
        self.assert_refused("pages/page0.nx", 2,
                            "Global variable definitions must precede all code in the program.c")

    def test_a_decimal_starting_value_past_32_bits(self):
        # nxlang keeps its low 32 bits, as C does. The test runner and the
        # simulator start it there, as the screen does.
        self.declare("int a=4294967295,b=-2147483649,c=2147483647,d=-2147483648")
        program = read_folder_source(folder_reader(self.root)).build_program().decode("latin-1")
        self.assertIn("\r\nint a=-1,b=2147483647,c=2147483647,d=-2147483648\r\n", program)
        values = self.run_load()
        self.assertEqual([values[name] for name in "abcd"],
                         [-1, 2147483647, 2147483647, -2147483648])
        self.assertEqual([Simulation(self.root).globals[name] for name in "abcd"],
                         [-1, 2147483647, 2147483647, -2147483648])

    def test_a_hexadecimal_starting_value(self):
        # Written in decimal, which the test runner reads.
        self.declare("int mask=0x10,all=0xFFFFFFFF")
        values = self.run_load()
        self.assertEqual((values["mask"], values["all"], "x10" in values), (16, -1, False))

    def test_an_int_after_other_code(self):
        # nxlang moves it above program.nx's other code, unindented, out of
        # its block too, and an error still names the line as written.
        self.write("program.nx", self.text("program.nx").replace(
            "page 0", "int late=1\nif (dim == 100) {\n  int inner=2\n}\npage 0"))
        self.assertEqual(self.findings(), [])
        program = read_folder_source(folder_reader(self.root)).build_program().decode("latin-1")
        self.assertIn("%s\r\nint late=1\r\nint inner=2\r\nbaud=9600\r\n"
                      % EDITOR_PROGRAM_DECLARATION, program)
        values = self.run_load()
        self.assertEqual((values["late"], values["inner"]), (1, 2))
        globals_ = Simulation(self.root).globals
        self.assertEqual((globals_["late"], globals_["inner"]), (1, 2))
        self.write("program.nx", self.text("program.nx").replace("int inner=2", "int RED=2"))
        self.assert_refused("program.nx", 10, "Illegal name")


if __name__ == "__main__":
    unittest.main()
