"""The int declarations of program.nx that the Nextion Editor 1.68.2 refused
as it compiled, on an NX4832T035, and those it compiled. The build refuses
them on their line, with the Nextion Editor's words, in either language,
but where nxlang writes a form the Nextion Editor compiles: it moves a late
int above program.nx's other code, and keeps the low 32 bits of a decimal
starting value past 32 bits. The test runner and the simulator start each
int at the value the build writes."""
import unittest

from nxwright import NxwrightError
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

    def test_a_starting_value_that_is_not_a_number(self):
        # Another variable, arithmetic, a number with a fraction, a text, and
        # nothing after the "=". The simulator stops at the same line as the
        # build.
        for value in ("first", "1+2", "1.5", '"x"', ""):
            with self.subTest(value=value):
                self.declare("int first=1", "int a=%s" % value)
                [finding] = self.findings()
                self.assertEqual((finding.file, finding.line, finding.severity),
                                 ("program.nx", 5, ERROR))
                self.assertIn("starting value", finding.message)
                with self.assertRaises(NxwrightError) as refusal:
                    Simulation(self.root)
                self.assertEqual((refusal.exception.file, refusal.exception.line),
                                 ("program.nx", 5))
        # The forms of a decimal number that the Nextion Editor compiled.
        self.declare("int a=+5,b=-0,c=007, d = 7 ,e")
        self.assertEqual(self.findings(), [])
        globals_ = Simulation(self.root).globals
        self.assertEqual([globals_[name] for name in "abcde"], [5, 0, 7, 7, 0])

    def test_the_message_for_a_starting_value_that_is_not_a_number(self):
        self.declare("int first=1", "int a=first")
        self.assert_refused("program.nx", 5,
                            "Initial value for a global variable must be a constant")
        self.assertIn("int a=first: the starting value of a must be a whole number, written in "
                      "decimal", self.findings()[0].message)

    def test_a_sign_apart_from_its_number(self):
        for value in ("- 5", "+ 5"):
            with self.subTest(value=value):
                self.declare("int a=%s" % value)
                self.assert_refused("program.nx", 4,
                                    "Initial value for a global variable must be a constant")
                self.assertIn("int a=%s: the starting value of a has a space after its sign"
                              % value, self.findings()[0].message)

    def test_a_malformed_int_line(self):
        # Text after a name, a number in place of a name, a comma with no
        # variable beside it, and `int` alone. The simulator stops at the
        # same line as the build.
        missing = "a variable is missing"
        for line, said in (("int a b", '"a b" is not a variable'),
                           ("int a b=5", '"a b=5" is not a variable'),
                           ("int 5", '"5" is not a variable'),
                           ("int a,", missing), ("int ,a", missing), ("int a,,b", missing),
                           ("int", missing)):
            with self.subTest(line=line):
                self.declare(line)
                [finding] = self.findings()
                self.assertEqual((finding.file, finding.line, finding.severity),
                                 ("program.nx", 4, ERROR))
                self.assertIn("%s: %s. An int line lists variables separated by commas, as in "
                              "int a=1,b" % (line, said), finding.message)
                with self.assertRaises(NxwrightError) as refusal:
                    Simulation(self.root)
                self.assertEqual((refusal.exception.file, refusal.exception.line),
                                 ("program.nx", 4))

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
        # nxlang's message adds how to write a local.
        super().test_an_int_in_an_event()
        self.assertIn("For a local, write var.", self.findings()[0].message)

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

    def test_a_constant_as_a_starting_value(self):
        # The build writes the constant's value. The test runner and the
        # simulator start the int at that value, and do not take the constant's
        # name for a variable.
        self.write("app.toml", self.text("app.toml") + "\n[defines]\nSIZE = 40\n")
        self.declare("const LIMIT = 5", "int count=LIMIT,back=-LIMIT,size=SIZE,ticks=0")
        self.assertEqual(self.findings(), [])
        program = read_folder_source(folder_reader(self.root)).build_program().decode("latin-1")
        self.assertIn("\r\nint count=5,back=-5,size=40,ticks=0\r\n", program)
        names = ("count", "back", "size", "ticks")
        values = self.run_load()
        self.assertEqual([values[name] for name in names], [5, -5, 40, 0])
        self.assertFalse("LIMIT" in values or "SIZE" in values)
        globals_ = Simulation(self.root).globals
        self.assertEqual([globals_[name] for name in names], [5, -5, 40, 0])
        self.assertFalse("LIMIT" in globals_ or "SIZE" in globals_)

    def test_the_message_for_a_starting_value_that_is_not_a_number(self):
        # nxlang has its own messages, because it also accepts a constant as a
        # starting value.
        for value, words in (("first", "first is not a constant"),
                             ("LIMT", "LIMT is not a constant"),
                             ("1+2", "the starting value of a must be a whole number or a "
                                     "constant")):
            with self.subTest(value=value):
                self.declare("int first=1", "int a=%s" % value)
                [finding] = self.findings()
                self.assertEqual((finding.file, finding.line), ("program.nx", 5))
                self.assertIn("int a=%s: %s" % (value, words), finding.message)

    def test_a_sign_apart_from_its_number(self):
        # nxlang writes the number without the space, so the Nextion Editor
        # compiles the line.
        self.declare("int a=- 5,b=+ 5")
        self.assertEqual(self.findings(), [])
        program = read_folder_source(folder_reader(self.root)).build_program().decode("latin-1")
        self.assertIn("\r\nint a=-5,b=5\r\n", program)
        values = self.run_load()
        self.assertEqual((values["a"], values["b"]), (-5, 5))
        globals_ = Simulation(self.root).globals
        self.assertEqual((globals_["a"], globals_["b"]), (-5, 5))

    def test_a_text_constant_as_a_starting_value(self):
        # An int cannot start at a text. The build, the test runner, and the
        # simulator all stop at the declaration's line.
        self.declare('const UNIT = "mm"', "int count=UNIT")
        [finding] = self.findings()
        self.assertEqual((finding.file, finding.line, finding.severity), ("program.nx", 5, ERROR))
        self.assertIn("the constant UNIT is a text. An int's starting value must be a number",
                      finding.message)
        for start in (self.run_load, lambda: Simulation(self.root)):
            with self.assertRaises(NxwrightError) as refusal:
                start()
            self.assertEqual((refusal.exception.file, refusal.exception.line), ("program.nx", 5))

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
