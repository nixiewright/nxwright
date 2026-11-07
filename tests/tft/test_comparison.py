"""Comparing two TFT files (tft/comparison.py), on files the tests make."""
import struct
import unittest

from nxwright.tft.comparison import differences, part_of, pieces, report
from nxwright.tft.tft_file import read_tft
from tests.tft.made_tft import made_tft, made_user_code


def read(data: bytes, where: str):
    return read_tft(data, where, check=False)


class ComparisonTest(unittest.TestCase):

    def test_the_same_file(self):
        a = read(made_tft("T"), "a")
        self.assertEqual(differences(a, read(made_tft("T"), "b")), [])
        self.assertEqual(report(a, a), "a and a are the same, byte for byte")

    def test_a_block_added_to_a_page(self):
        code = made_user_code()
        longer = made_user_code()
        # A line of code in the page's Touch Release event, after its name.
        at = longer.blocks.index(b"up") + 1
        longer.blocks.insert(at, b"t0.txt=1")
        entry = bytearray(longer.page_index)
        for place, grown in ((4, 12), (8, 12)):
            value = int.from_bytes(entry[place:place + 4], "little") + grown
            entry[place:place + 4] = value.to_bytes(4, "little")
        longer.page_index = bytes(entry)
        found = differences(read(made_tft("T", code), "a"), read(made_tft("T", longer), "b"))
        user_code = next(found for found in found if part_of(found.a or found.b) == "user code")
        self.assertEqual(user_code.a.name, "user code, page 0, block 6")
        self.assertEqual(user_code.b.data[4:], b"t0.txt=1")
        self.assertEqual(user_code.offset, 0)

    def test_pages_are_named_by_their_place(self):
        # The second page's entry counting 2 objects before it.
        code = made_user_code(pages=2)
        index = bytearray(code.page_index)
        struct.pack_into("<H", index, 16, 2)
        code.page_index = bytes(index)
        names = [piece.name for piece in pieces(read(made_tft("T", code), "a"))]
        self.assertIn("user code, page 1, block 0", names)
        self.assertIn("user code, page 1's data", names)
        self.assertNotIn("user code, page 2's data", names)

    def test_a_header_field(self):
        found = differences(read(made_tft("T"), "a"), read(made_tft("T", fonts=b"other"), "b"))
        self.assertEqual(found[0].a.name, "header 1, 0x44 (that section's checksum)")

    def test_a_piece_one_file_lacks(self):
        found = differences(read(made_tft("T"), "a"),
                            read(made_tft("T", pictures=b"a picture"), "b"))
        section = next(found for found in found if part_of(found.a or found.b) == "the section")
        self.assertIsNone(section.a)
        self.assertEqual(section.b.name, "the section, the pictures")

    def test_report(self):
        text = report(read(made_tft("T"), "a.tft"), read(made_tft("T", fonts=b"other"), "b.tft"))
        self.assertIn("a.tft and b.tft differ:\n- header 1:", text)
        self.assertIn("a.tft: the section, the fonts, at 0x", text)
        # The byte that differs, in brackets: "a font" against "other".
        self.assertIn("[61]", text)
        self.assertIn("[6f]", text)


if __name__ == "__main__":
    unittest.main()
