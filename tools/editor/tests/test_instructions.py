"""The lines `simulate --send` types (tools/editor/instructions.py), checked as
the tool does before the simulator starts. They need neither the Editor nor
pywinauto."""
import unittest

from tools.editor.instructions import DONE_MARKER, InstructionError, typed_lines


class TypedLinesTest(unittest.TestCase):

    def test_string_lines_then_the_marker(self):
        self.assertEqual(typed_lines("bkcmd=3\nget n0.val"), ["bkcmd=3", "get n0.val", DONE_MARKER])
        self.assertEqual(typed_lines(""), [DONE_MARKER])

    def test_hex_lines_are_spaced_in_pairs_and_the_marker_ends_with_ff(self):
        # "get 1", then FF FF FF, which a String line would get from the box.
        self.assertEqual(typed_lines("68656c6c6f\n0A 0d", hex_mode=True),
                         ["68 65 6C 6C 6F", "0A 0D", "67 65 74 20 31 FF FF FF"])

    def test_a_line_that_is_not_hex_is_refused(self):
        for line in ("hello", "6", "68 6G", ""):
            with self.subTest(line=line), self.assertRaisesRegex(InstructionError,
                                                                 "is not hexadecimal bytes"):
                typed_lines("68\n%s\n69" % line, hex_mode=True)


if __name__ == "__main__":
    unittest.main()
