"""The text form of a page: what it shows, and that it rebuilds the block exactly."""
import unittest

from nxwright import NxwrightError
from nxwright.project.page_block import encode_page, parse_page
from nxwright.project.page_text import (escape_string, page_from_text, page_to_text,
                                        unescape_string)
from tests.test_page_block import SAMPLE_PAGE, attribute, object_body, page_block, record


def round_trip(block: bytes) -> bytes:
    """Returns `block` written as text, read back, and encoded again. Its 4-byte
    stamp is left out, as the text does not hold it."""
    return encode_page(page_from_text(page_to_text(parse_page(block))))[4:]


class PageToTextTest(unittest.TestCase):

    def setUp(self):
        self.text = page_to_text(parse_page(SAMPLE_PAGE))

    def test_numbers_with_expected_width_are_plain(self):
        self.assertIn("\n  w = 800\n", self.text)
        self.assertIn("\n  type = 121\n", self.text)

    def test_event_code_is_readable(self):
        self.assertIn("  event load\n    | if(a!=0)\n    | {\n  event down\n", self.text)

    def test_object_line_labels_index_and_name(self):
        self.assertIn("\nobject 0 main\n", self.text)
        self.assertIn("\nobject 1\n", self.text)

    def test_unrecognised_record_is_hex(self):
        self.assertIn("  raw " + (b"\xff" * 16 + b"odd").hex() + "\n", self.text)


class RoundTripTest(unittest.TestCase):

    def test_sample_page(self):
        self.assertEqual(round_trip(SAMPLE_PAGE), SAMPLE_PAGE[4:])

    def test_unexpected_width_is_written_explicitly(self):
        # "val" is 4 bytes by default; a 1-byte val must say so.
        block = page_block("p", object_body(attribute("val", b"\x07")))
        self.assertIn("  val:u8 = 7\n", page_to_text(parse_page(block)))
        self.assertEqual(round_trip(block), block[4:])

    def test_width_depends_on_component_type(self):
        # Type 98 has a 1-byte "val", so no explicit width is needed.
        block = page_block("p", object_body(attribute("type", b"\x62"), attribute("val", b"\x01")))
        self.assertIn("  val = 1\n", page_to_text(parse_page(block)))
        self.assertEqual(round_trip(block), block[4:])

    def test_unknown_attribute_round_trips(self):
        block = page_block("p", object_body(attribute("newthing", b"\x01\x02"),
                                            attribute("blob", b"abc")))
        text = page_to_text(parse_page(block))
        self.assertIn("  newthing:u16 = 513\n", text)
        self.assertIn('  blob = "abc"\n', text)
        self.assertEqual(round_trip(block), block[4:])

    def test_awkward_code_lines_become_raw(self):
        block = page_block("p", object_body(record(b"codesup-3"), record(b"a=1 "),
                                            record(b"t.txt=\"\xe9\""), record(b"  b=2")))
        text = page_to_text(parse_page(block))
        self.assertIn("    raw " + b"a=1 ".hex() + "\n", text)
        self.assertIn("    |   b=2\n", text)
        self.assertEqual(round_trip(block), block[4:])

    def test_objname_with_space_or_empty_round_trips(self):
        block = page_block("p", object_body(attribute("objname", b"two words")),
                           object_body(attribute("objname", b"")))
        text = page_to_text(parse_page(block))
        self.assertIn("\nobject 0\n", text)
        self.assertIn("\nobject 1\n", text)
        self.assertEqual(round_trip(block), block[4:])

    def test_escaped_strings(self):
        block = page_block("p", object_body(attribute("txt", b'say "hi"\\\r\n\x00')))
        self.assertEqual(round_trip(block), block[4:])


class StringEscapeTest(unittest.TestCase):

    def test_escape(self):
        self.assertEqual(escape_string(b'a"b\\c\xe9'), '"a\\"b\\\\c\\xe9"')

    def test_unescape_reverses_escape(self):
        value = bytes(range(256))
        self.assertEqual(unescape_string(escape_string(value)), value)

    def test_unescape_rejects_unknown_escape(self):
        with self.assertRaises(NxwrightError):
            unescape_string('"\\n"')


class PageFromTextErrorTest(unittest.TestCase):

    def setUp(self):
        self.text = page_to_text(parse_page(SAMPLE_PAGE))

    def assert_rejected(self, text: str):
        with self.assertRaises(NxwrightError):
            page_from_text(text)

    def test_rejects_mismatched_object_label(self):
        self.assert_rejected(self.text.replace("object 0 main", "object 0 other"))

    def test_rejects_unknown_width(self):
        self.assert_rejected(self.text.replace("  w = 800", "  newthing = 800"))

    def test_rejects_number_too_big_for_its_width(self):
        self.assert_rejected(self.text.replace("  w = 800", "  w = 70000"))

    def test_rejects_code_line_without_prefix(self):
        self.assert_rejected(self.text.replace("    | {", "    {"))

    def test_rejects_non_ascii_text(self):
        self.assert_rejected(self.text.replace("    | {", "    | é"))

    def test_rejects_missing_header_line(self):
        self.assert_rejected(self.text.replace("header_40", "header_41"))


if __name__ == "__main__":
    unittest.main()
