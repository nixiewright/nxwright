"""What the control statements share (tft/control_statements.py), where
the statements' own tests do not reach: the comparison's block, which a
component type's drawing may hold too."""
import unittest

from nxwright.tft import control_statements


class ComparisonBlockTest(unittest.TestCase):

    def test_a_comparison_s_block(self):
        # `if(sys0==1)` before a body and a jump past an else, as the
        # Nextion Editor wrote it (ResearchNotes/tft/if-statement.md).
        block = control_statements.comparison_block(b"\x05\x00\x00\x00\x00", 1, b"1", 22)
        self.assertEqual(block.hex(" "), "09 00 04 05 00 00 00 00 2c 31 2c 31 2c 03 16 00 00 00")
        self.assertIsInstance(block, control_statements.JumpBlock)
        self.assertEqual(block.jump, 22)


if __name__ == "__main__":
    unittest.main()
