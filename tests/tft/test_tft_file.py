"""Reading a TFT file (tft/tft_file.py), on files the tests make (made_tft)
and on the checksums seen in the Nextion Editor's own."""
import os
import struct
import unittest

from nxwright.project.stamp import CRC_START, word_crc

from nxwright.tft.tft_file import (IndexEntry, TftFileError, UserCode, byte_form_crc,
                            file_checksum_from_crc, header_2_key, layout_of, read_tft,
                            split_blocks)
from tests.tft.made_tft import made_tft, made_user_code


def changed(data: bytes, place: int, value: bytes) -> bytes:
    """Returns `data` with `value` written at `place`."""
    return data[:place] + value + data[place + len(value):]


class ChecksumTest(unittest.TestCase):

    def test_byte_form_is_nxwright_s_stamp_crc(self):
        data = os.urandom(301)
        self.assertEqual(byte_form_crc(data), word_crc(CRC_START, data))

    def test_header_2_key_from_the_device_id(self):
        # The key the research note gives for an NX4832T035.
        self.assertEqual(header_2_key(bytes.fromhex("18c03bb2"), "T"), 0xEBAB2932)
        self.assertIsNone(header_2_key(bytes.fromhex("0376e41c"), "F"))

    def test_file_checksum_low_byte(self):
        # As seen in the Nextion Editor's files: the CRC of every byte before
        # the checksum, the file's size, the device ID, and the checksum.
        for crc, size, device_id, checksum in (
                (0x14461698, 0x50544, "18c03bb2", 0x1446168A),   # NX4832T035
                (0x20210C22, 0x50ACC, "18c03bb2", 0x20210CB8),   # the same, larger
                (0x75751E38, 0x40544, "be24d31b", 0x75751E8C),   # NX4832K035
                (0x84A6D347, 0xC054C, "883d9555", 0x84A6D3CD),   # NX8048P050
                (0x14C94DE9, 0x8054C, "65afb221", 0x14C94D8E),   # NX4848E040
                (0xEA771BD4, 0x60544, "0376e41c", 0xEA771BDD)):  # NX4832F035
            with self.subTest(device_id=device_id, size=size):
                self.assertEqual(file_checksum_from_crc(crc, size, bytes.fromhex(device_id)),
                                 checksum)


class ReadTest(unittest.TestCase):

    def test_every_series_reads_without_problems(self):
        for series in "TKPEF":
            with self.subTest(series):
                tft = read_tft(made_tft(series), series)
                self.assertEqual((tft.series, tft.version, tft.problems), (series, (1, 68, 2), []))

    def test_the_user_code_s_parts(self):
        code = made_user_code(pages=2, variables=4)
        tft = read_tft(made_tft("T", code), "two pages")
        self.assertEqual(tft.user_code, code)
        self.assertEqual(tft.user_code.to_bytes(), tft.user_code_bytes)
        parts = tft.user_code.block_parts()
        self.assertEqual(parts, ["first block"] + ["program.s"] * 3 + ["page 0"] * 13
                         + ["page 1"] * 13)
        self.assertEqual(tft.user_code.page_data(), [bytes(24), b"\x01" * 24])
        self.assertEqual([entry.objects_before for entry in tft.user_code.index_entries()], [0, 1])

    def test_header_2_s_words_from_0x114_are_not_keyed(self):
        # The key covers words 0 to 18. Words 19 to 48 hold 0xFFFFFFFF as
        # they are stored, as in every T, K, P, and E file seen.
        for series in "TKPE":
            with self.subTest(series):
                tft = read_tft(made_tft(series), series)
                self.assertEqual(tft.data[0x114:0x18C], b"\xff" * 0x78)
                self.assertEqual(tft.header_2_words[19:], [0xFFFFFFFF] * 30)
                self.assertEqual(tft.header_2_value(0x110), 3)

    def test_pages_are_named_by_their_place_in_the_page_index(self):
        # An entry's first number counts the objects on the pages before:
        # 2 for a second page, when the first holds a component.
        code = made_user_code(pages=2)
        index = bytearray(code.page_index)
        struct.pack_into("<H", index, 16, 2)
        code.page_index = bytes(index)
        tft = read_tft(made_tft("T", code), "after a component")
        self.assertEqual([entry.objects_before for entry in tft.user_code.index_entries()],
                         [0, 2])
        self.assertEqual(tft.user_code.block_parts()[-13:], ["page 1"] * 13)

    def test_the_section_s_table(self):
        tft = read_tft(made_tft("P", pictures=b"a picture"), "P")
        self.assertEqual([row.name for row in tft.table][:3], ["input.bin", "3.cc", "cdx.dll"])
        self.assertEqual(tft.table_part(tft.table[7]), b"a picture")
        self.assertEqual(tft.table_part(tft.table[8]), b"a font")

    def test_f_s_header_2_is_unscrambled(self):
        code = made_user_code(pages=2)
        tft = read_tft(made_tft("F", code), "F")
        self.assertEqual(tft.header_2_value(0x100), 2 | (2 << 16))
        self.assertEqual(tft.header_2_words[19:], [0xFFFFFFFF] * 30)
        self.assertEqual(tft.user_code, code)
        self.assertEqual(tft.problems, [])


class ProblemTest(unittest.TestCase):
    """Each checksum, size, or place a file states that does not hold is
    named, and read_tft raises with every one unless asked not to."""

    def problems(self, data: bytes) -> list:
        return read_tft(data, "changed", check=False).problems

    def test_a_byte_of_the_user_code_changed(self):
        data = made_tft("T")
        problems = self.problems(changed(data, len(data) - 6, b"X"))
        self.assertEqual(len(problems), 1)
        self.assertIn("the file's checksum", problems[0])

    def test_a_byte_of_the_section_changed(self):
        data = made_tft("T")
        problems = self.problems(changed(data, 0x10000 + 0x90, b"X"))
        self.assertIn("header 1's section checksum", problems[0])

    def test_header_1_changed(self):
        data = made_tft("T")
        # A byte of its 0xFF fill.
        problems = self.problems(changed(data, 0x4C, b"\x00"))
        self.assertIn("header 1's checksum", problems[0])

    def test_header_2_changed(self):
        data = made_tft("T")
        problems = self.problems(changed(data, 0x104, b"\x01"))
        self.assertIn("header 2's checksum", problems[0])

    def test_header_1_s_macros_place_changed(self):
        # Without macros, header 1's 0x58 gives the page index's place: there,
        # it then lies before the pages' data.
        data = made_tft("T")
        problems = self.problems(changed(data, 0x58, b"\x00"))
        self.assertTrue(any(problem.startswith("header 1's 0x58, the macros' table's place")
                            for problem in problems), problems)

    def test_header_2_s_unkeyed_words_changed(self):
        problems = self.problems(changed(made_tft("T"), 0x120, b"\x00"))
        self.assertIn("header 2's checksum", problems[0])
        self.assertIn("header 2's words from 0x114 are not all 0xFFFFFFFF", problems)

    def test_a_page_s_entry_that_misses_its_objects_table(self):
        code = made_user_code(pages=2)
        entry = struct.unpack("<HHIII", code.page_index[16:32])
        code.page_index = code.page_index[:16] + struct.pack("<HHIII", entry[0], entry[1],
                                                             entry[2] + 1, *entry[3:])
        tft = read_tft(made_tft("T", code), "moved", check=False)
        self.assertEqual(tft.user_code.block_parts()[-13:], ["pages"] * 13)
        self.assertIn("does not place the user code's blocks from block 17 on", tft.problems[0])

    def test_check_raises_naming_every_problem(self):
        data = made_tft("T")
        data = changed(changed(data, 0x4C, b"\x00"), len(data) - 6, b"X")
        with self.assertRaises(TftFileError) as raised:
            read_tft(data, "changed")
        self.assertIn("header 1's checksum", str(raised.exception))
        self.assertIn("the file's checksum", str(raised.exception))
        self.assertTrue(str(raised.exception).startswith("changed: "))

    def test_files_that_cannot_be_split(self):
        data = made_tft("T")
        for name, broken, message in (
                ("too short", data[:0x100], "too few for a TFT file's headers"),
                ("unknown series", changed(data, 0x15, b"\x09"), "series code 9"),
                ("section past the end", changed(data, 0x40, struct.pack("<I", 0x900000)),
                 "header 1 puts the section")):
            with self.subTest(name):
                with self.assertRaisesRegex(TftFileError, message):
                    read_tft(broken, name, check=False)


class BlocksTest(unittest.TestCase):

    def test_split_blocks(self):
        self.assertEqual(split_blocks(b"\x02\x00\x00\x00ab\x00\x00\x00\x00"), [b"ab", b""])
        self.assertIsNone(split_blocks(b"\x05\x00\x00\x00ab"))
        self.assertIsNone(split_blocks(b"\x02\x00"))

    def test_places(self):
        code = UserCode([b"ab", b""], b"", b"v" * 12, b"data", b"i" * 16, b"r")
        self.assertEqual(code.places(), {"blocks": (0, 10), "after the blocks": (10, 10),
                                         "variables": (10, 22), "data": (22, 26),
                                         "macros": (26, 26), "page index": (26, 42),
                                         "records": (42, 43)})
        # The macros' table lies between the data and the page index.
        code = UserCode([b"ab", b""], b"", b"v" * 12, b"data", b"i" * 16, b"r", b"m" * 8)
        self.assertEqual((code.places()["macros"], code.places()["page index"]),
                         ((26, 34), (34, 50)))
        self.assertEqual(code.to_bytes()[26:34], b"m" * 8)


class OlderEditorTest(unittest.TestCase):
    """The headers that the Nextion Editors 1.61.2 to 1.65.1 write otherwise
    than 1.68.2 (ResearchNotes/tft/older-editors.md), each taken from a file of
    such a version, and named as a problem in a file of 1.68.2."""

    def problems(self, data: bytes) -> list:
        return read_tft(data, "older", check=False).problems

    def test_no_macros(self):
        # The macros' table's place as 0xffffffff, and their number as 0xffff,
        # in a file of each version, of the first blocks it writes.
        for version, first_blocks in (((1, 65, 1), [b"first block"]),
                                      ((1, 63, 3), [bytes(4), bytes(16), b"page 0"]),
                                      ((1, 61, 2), [bytes(16), b"page 0"])):
            code = made_user_code(first_blocks=first_blocks,
                                  index_entry=layout_of(version).page_index_entry)
            with self.subTest(version):
                self.assertEqual(self.problems(made_tft(
                    "T", code, version=version, macros_unset=True,
                    first_blocks=len(first_blocks))), [])
        problems = self.problems(made_tft("T", macros_unset=True))
        self.assertTrue(any(problem.startswith("header 1's 0x58") for problem in problems))
        self.assertTrue(any(problem.startswith("header 1's 0x6E") for problem in problems))

    def test_the_first_blocks_of_1_63_3_and_1_61_2(self):
        # Header 2's 0xFC gives the size of the first blocks: 1.63.3's three,
        # a 0 word, the int area, and the page list; 1.61.2's two, the int
        # area and the page list.
        for version, first_blocks in (((1, 63, 3), [bytes(4), bytes(16), b"page 0"]),
                                      ((1, 61, 2), [bytes(16), b"page 0"])):
            code = made_user_code(first_blocks=first_blocks,
                                  index_entry=layout_of(version).page_index_entry)
            with self.subTest(version):
                self.assertEqual(self.problems(made_tft(
                    "K", code, version=version, macros_unset=True,
                    first_blocks=len(first_blocks))), [])
                problems = self.problems(made_tft("K", code, first_blocks=len(first_blocks)))
                self.assertTrue(any(problem.startswith("header 2's 0xFC") for problem in problems),
                                problems)

    def test_the_page_index_before_1_63(self):
        # Before 1.63, a page's entry in the page index is 12 bytes, without
        # the page's memory. A file of 1.61.2 of such entries reads without a
        # problem; one of 1.63.3 refuses them.
        code = made_user_code(pages=2, first_blocks=[bytes(16), b"page 0"], index_entry=12)
        tft = read_tft(made_tft("K", code, version=(1, 61, 2), macros_unset=True,
                                first_blocks=2), "older", check=False)
        self.assertEqual(tft.problems, [])
        entries = tft.user_code.index_entries()
        self.assertEqual([(entry.objects_before, entry.objects, entry.memory)
                          for entry in entries], [(0, 1, None), (1, 1, None)])
        self.assertEqual(entries, [IndexEntry.from_bytes(code.page_index[at:at + 12])
                                   for at in (0, 12)])
        code = made_user_code(pages=2, first_blocks=[bytes(4), bytes(16), b"page 0"],
                              index_entry=12)
        problems = self.problems(made_tft("K", code, version=(1, 63, 3), macros_unset=True,
                                          first_blocks=3))
        self.assertIn("the page index takes 24 bytes, not a multiple of 16", problems)

    def test_no_second_firmware_file_on_p(self):
        code = made_user_code(first_blocks=[bytes(4), bytes(16), b"page 0"])
        self.assertEqual(self.problems(made_tft("P", code, version=(1, 63, 3), macros_unset=True,
                                                first_blocks=3, second_firmware=False)), [])
        problems = self.problems(made_tft("P", second_firmware=False))
        self.assertTrue(any(problem.startswith("header 1's 0x18") for problem in problems),
                        problems)

    def test_no_second_firmware_file_on_p_before_1_68_1(self):
        # The releases before 1.68.1 have no cdx.dll, P's second firmware
        # file, whatever their layout.
        for version in ((1, 65, 0), (1, 67, 1)):
            with self.subTest(version=version):
                self.assertEqual(self.problems(made_tft("P", version=version, macros_unset=True,
                                                        second_firmware=False)), [])
        code = made_user_code(first_blocks=[bytes(16), b"page 0"], index_entry=12)
        self.assertEqual(self.problems(made_tft("P", code, version=(1, 61, 2), macros_unset=True,
                                                first_blocks=2, second_firmware=False)), [])
        problems = self.problems(made_tft("P", version=(1, 68, 1), macros_unset=True,
                                          second_firmware=False))
        self.assertTrue(any(problem.startswith("header 1's 0x18") for problem in problems),
                        problems)
        # A P file of 1.68.1 with its second firmware file reads as one of
        # 1.68.2 with no macros does.
        self.assertEqual(self.problems(made_tft("P", version=(1, 68, 1), macros_unset=True)), [])
        # Only P and E may hold none.
        problems = self.problems(made_tft("T", version=(1, 65, 0), macros_unset=True,
                                          second_firmware=False))
        self.assertTrue(any(problem.startswith("header 1's 0x18") for problem in problems),
                        problems)

    def test_a_file_older_than_1_60_1_is_refused(self):
        # Each file is laid out as 1.61.2 lays out its files, so the reader
        # can refuse it only by its version.
        code = made_user_code(first_blocks=[bytes(16), b"page 0"], index_entry=12)
        for version in ((1, 60, 0), (1, 59, 9), (0, 53, 0)):
            with self.subTest(version=version):
                with self.assertRaises(TftFileError) as raised:
                    read_tft(made_tft("T", code, version=version, macros_unset=True,
                                      first_blocks=2), "old.tft", check=False)
                self.assertEqual(str(raised.exception),
                                 "old.tft was made by a Nextion Editor older than 1.60.1. nxwright "
                                 "reads only files made by the Nextion Editor 1.60.1 or later")
        self.assertEqual(self.problems(made_tft("T", code, version=(1, 60, 1), macros_unset=True,
                                                first_blocks=2)), [])


if __name__ == "__main__":
    unittest.main()
