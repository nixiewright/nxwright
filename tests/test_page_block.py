"""Page block parsing and encoding, on small hand-built blocks."""
import struct
import unittest

from nxwright import NxwrightError
from nxwright.project.page_block import (Attribute, Event, Marker, RawRecord, encode_page,
                                         parse_page)


def record(body: bytes) -> bytes:
    """Returns `body` as a record: its length as a u32, then its bytes."""
    return struct.pack("<I", len(body)) + body


def attribute(name: str, value: bytes) -> bytes:
    """Returns an attribute record: `name` NUL-padded to 16 bytes, then `value`."""
    return record(name.encode("ascii").ljust(16, b"\0") + value)


def object_body(*records: bytes) -> bytes:
    """Returns an object body: `records`, then the zero length that ends them."""
    return b"".join(records) + struct.pack("<I", 0)


def page_block(name: str, *bodies: bytes, stamp: int = 0x12345678,
               header_16: bytes = bytes.fromhex("00000000004f2101"),
               header_40: bytes = bytes(range(16))) -> bytes:
    """Returns a page block named `name` that holds the object `bodies`.

    The header's fields at +16 and +40 are `header_16` and `header_40`, and
    `stamp` is stored as given, not computed.
    """
    table = bytearray()
    offset = 12 * len(bodies)
    for body in bodies:
        table += struct.pack("<III", offset, len(body), 0)
        offset += len(body)
    total = 56 + len(table) + sum(len(body) for body in bodies)
    header = (struct.pack("<IIII", stamp, total, 56, len(bodies)) + header_16
              + name.encode("ascii").ljust(16, b"\0") + header_40)
    return header + bytes(table) + b"".join(bodies)


# Object 0 is the page: a class marker, four attributes, a load event of two
# lines, and a down event with none. Object 1 has a txt attribute and a record
# the parser does not recognise.
SAMPLE_PAGE = page_block(
    "main",
    object_body(record(b"att-28"), attribute("type", b"y"), attribute("w", b"\x20\x03"),
                attribute("val", b"\x01\x00\x00\x00"), attribute("objname", b"main"),
                record(b"codesload-2"), record(b"if(a!=0)"), record(b"{"),
                record(b"codesdown-0")),
    object_body(record(b"att-39"), attribute("txt", b""),
                record(b"\xff" * 16 + b"odd")))


class ParsePageTest(unittest.TestCase):

    def test_parses_header_fields(self):
        page = parse_page(SAMPLE_PAGE)
        self.assertEqual(page.name, "main")
        self.assertEqual(page.stamp, 0x12345678)
        self.assertEqual(page.unknown_16, bytes.fromhex("00000000004f2101"))
        self.assertEqual(page.unknown_40, bytes(range(16)))

    def test_parses_records_in_order(self):
        items = parse_page(SAMPLE_PAGE).objects[0].items
        self.assertEqual(items[0], Marker(b"att-28"))
        self.assertEqual(items[2], Attribute("w", b"\x20\x03"))
        self.assertEqual(items[5], Event("load", [b"if(a!=0)", b"{"]))
        self.assertEqual(items[6], Event("down", []))

    def test_short_event_lines_are_lines_not_markers(self):
        event = parse_page(SAMPLE_PAGE).objects[0].items[5]
        self.assertIn(b"{", event.lines)

    def test_unrecognised_record_is_kept_raw(self):
        items = parse_page(SAMPLE_PAGE).objects[1].items
        self.assertEqual(items[2], RawRecord(b"\xff" * 16 + b"odd"))

    def test_encode_reproduces_the_block(self):
        self.assertEqual(encode_page(parse_page(SAMPLE_PAGE)), SAMPLE_PAGE)

    def test_rejects_wrong_size_field(self):
        broken = bytearray(SAMPLE_PAGE)
        struct.pack_into("<I", broken, 4, len(SAMPLE_PAGE) + 1)
        with self.assertRaises(NxwrightError):
            parse_page(bytes(broken))

    def test_rejects_event_longer_than_its_object(self):
        # The event announces three lines, but only one record follows.
        block = page_block("p", object_body(record(b"codesup-3"), record(b"x")))
        with self.assertRaises(NxwrightError):
            parse_page(block)

    def test_rejects_object_without_terminator(self):
        block = page_block("p", record(b"att-28"))
        with self.assertRaises(NxwrightError):
            parse_page(block)


if __name__ == "__main__":
    unittest.main()
