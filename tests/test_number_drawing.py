"""Numbers and xfloats written out as the Editor's simulator writes them,
each case as it showed one (tests/fixtures/value-widgets/)."""
import unittest

from nxwright.drawing.number_drawing import number_text, xfloat_text

DECIMAL, THOUSANDS, HEX = 0, 1, 2


class NumberTextTest(unittest.TestCase):

    def test_as_the_editor_writes_them(self):
        cases = [
            (12345, DECIMAL, 0, "12345"), (-42, DECIMAL, 0, "-42"), (0, DECIMAL, 0, "0"),
            (2147483647, DECIMAL, 0, "2147483647"), (-2147483648, DECIMAL, 0, "-2147483648"),
            (1234567, THOUSANDS, 0, "1,234,567"), (-1234567, THOUSANDS, 0, "-1,234,567"),
            (1000, THOUSANDS, 0, "1,000"), (-1234, THOUSANDS, 0, "-1,234"),
            (255, HEX, 0, "FF"), (-1, HEX, 0, "FFFFFFFF"), (-255, HEX, 0, "FFFFFF01"),
            (0, HEX, 0, "00"),
            # `lenth` pads with zeros, or keeps the first characters, the sign aside.
            (42, DECIMAL, 5, "00042"), (-42, DECIMAL, 5, "-00042"), (0, DECIMAL, 3, "000"),
            (5, DECIMAL, 15, "000000000000005"), (1234567, DECIMAL, 3, "123"),
            (-1234567, DECIMAL, 3, "-123"), (255, HEX, 4, "00FF"), (255, HEX, 1, "F"),
            (1234567, THOUSANDS, 5, "1,234"), (1234567, THOUSANDS, 3, "1,2"),
            (1234, THOUSANDS, 6, "01,234"),
        ]
        for value, form, length, written in cases:
            with self.subTest(value=value, format=form, lenth=length):
                self.assertEqual(number_text({"val": value, "format": form, "lenth": length}),
                                 written)

    def test_the_stored_bits_read_signed(self):
        # As a page file's Component holds them: unsigned.
        self.assertEqual(number_text({"val": 2 ** 32 - 42}), "-42")


class XfloatTextTest(unittest.TestCase):

    def test_as_the_editor_writes_them(self):
        cases = [
            (12345, 2, 2, "12.45"), (12345, 0, 2, "123.45"), (5, 3, 3, "000.005"),
            (-12345, 2, 2, "-12.45"), (12345, 2, 0, "12"), (12345, 0, 0, "12345"),
            (1234567, 3, 1, "123.7"), (-5, 1, 2, "-0.05"), (0, 0, 2, "0.00"), (5, 0, 2, "0.05"),
            (-5, 0, 2, "-0.05"), (12345, 3, 4, "001.2345"), (7, 0, 0, "7"), (100, 0, 3, "0.100"),
            (-12345, 1, 2, "-1.45"), (2147483647, 0, 5, "21474.83647"), (5, 2, 0, "05"),
            (123, 0, 5, "0.00123"), (-123, 4, 1, "-0012.3"),
            # In 32 bits, -2147483648 stays negative once its sign is taken off.
            (-2147483648, 0, 3, "--2147483.-648"),
        ]
        for value, before, after, written in cases:
            with self.subTest(value=value, vvs0=before, vvs1=after):
                self.assertEqual(xfloat_text({"val": value, "vvs0": before, "vvs1": after}),
                                 written)


if __name__ == "__main__":
    unittest.main()
