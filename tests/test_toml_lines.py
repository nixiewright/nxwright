"""The line of a TOML file that an error is about (project/toml_lines.py)."""
import tomllib
import unittest

from nxwright.project.toml_lines import error_line, key_line, table_line

TEXT = """format = 1
name = "demo"
rotation = 0

[mcu]  # the emulator
emulator = "../mcu/main.py"
rotation = 5

[defines]
LIMIT = 3
"""

PAGE = """[page]
name = "home"

[[component]]
name = "b0"

[[component]]
name = "b1"
"""


class KeyLineTest(unittest.TestCase):

    def test_a_key_at_the_top_level(self):
        self.assertEqual(key_line(TEXT, "name"), 2)
        # The key of the same name in a table is another key.
        self.assertEqual(key_line(TEXT, "rotation"), 3)

    def test_a_key_of_a_table(self):
        self.assertEqual(key_line(TEXT, "rotation", "mcu"), 7)
        self.assertEqual(key_line(TEXT, "LIMIT", "defines"), 10)
        self.assertEqual(key_line(PAGE, "name", "page"), 2)

    def test_a_key_that_no_line_gives(self):
        self.assertEqual(key_line(TEXT, "colour"), 0)
        self.assertEqual(key_line(TEXT, "emulator"), 0)
        self.assertEqual(key_line(TEXT, "LIMIT", "mcu"), 0)
        self.assertEqual(key_line(TEXT, "wait", "nothing"), 0)

    def test_a_key_with_spaces_around_it(self):
        self.assertEqual(key_line("a = 1\n  colour   = 2\n", "colour"), 2)


class TableLineTest(unittest.TestCase):

    def test_the_header_of_a_table(self):
        self.assertEqual([table_line(PAGE, table) for table in range(3)], [1, 4, 7])

    def test_a_table_the_text_does_not_have(self):
        self.assertEqual(table_line(PAGE, 3), 0)


class ErrorLineTest(unittest.TestCase):

    def error_of(self, text: str) -> tomllib.TOMLDecodeError:
        with self.assertRaises(tomllib.TOMLDecodeError) as raised:
            tomllib.loads(text)
        return raised.exception

    def test_the_line_the_reader_stopped_at(self):
        self.assertEqual(error_line(self.error_of("a = 1\nb = = 2\n")), 2)

    def test_an_error_at_the_end_of_the_text_has_no_line(self):
        self.assertIsNone(error_line(self.error_of('a = "unclosed')))
