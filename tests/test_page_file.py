"""Page files (.page), one page as the Editor exports it, with its fonts: font
embedding and renumbering, and writing one from a dump."""
from pathlib import Path
import struct
import tempfile
import unittest
from unittest import mock

from nxwright.project.dumper import ProjectDumper
from nxwright.project.page_file import write_page_file
from nxwright import NxwrightError
from nxwright.project.page_block import parse_page
from nxwright.project.page_file import build_page_file
from nxwright.project.page_text import page_from_text
from nxwright.project.stamp import block_stamp
from tests.test_page_block import attribute, object_body, page_block, record
from tests.test_project_writer import write_small_project


def table_entries(block: bytes) -> list:
    """Returns the object table of a page block or page file, as (offset,
    length, kind) tuples. Kind 1 is an embedded font."""
    count = struct.unpack_from("<I", block, 12)[0]
    return [struct.unpack_from("<III", block, 56 + 12 * index) for index in range(count)]


class BuildPageFileTest(unittest.TestCase):

    def setUp(self):
        # Fonts used in the order 5, 2, 5: they embed as 5 then 2.
        page = page_block("p", object_body(record(b"att-28")),
                          object_body(attribute("font", b"\x05")),
                          object_body(attribute("font", b"\x02")),
                          object_body(attribute("font", b"\x05")))
        self.fonts = {2: b"font two", 5: b"font five", 7: b"unused"}
        self.page = parse_page(page)
        self.result = build_page_file(self.page, self.fonts, "iso-8859-1")

    def test_fonts_are_embedded_in_first_use_order(self):
        entries = table_entries(self.result)
        self.assertEqual([kind for _, _, kind in entries], [0, 0, 0, 0, 1, 1])
        bodies = [self.result[56 + offset:56 + offset + length]
                  for offset, length, kind in entries if kind == 1]
        self.assertEqual(bodies, [b"font five", b"font two"])

    def test_font_attributes_are_renumbered(self):
        fonts = [self.result.find(b"font\0" + bytes(11) + bytes([value]))
                 for value in (0, 1)]
        self.assertTrue(all(position > 0 for position in fonts))
        self.assertEqual(self.result.count(b"font\0" + bytes(11) + b"\x05"), 0)

    def test_header_and_stamp(self):
        # As in the page files the Editor exported from an iso-8859-1 project.
        self.assertEqual(self.result[40:56], bytes.fromhex("01440203") + bytes(12))
        self.assertEqual(block_stamp(self.result), int.from_bytes(self.result[:4], "little"))

    def test_input_page_is_not_changed(self):
        self.assertEqual(self.page.objects[1].attribute("font"), b"\x05")

    def test_refuses_missing_font(self):
        with self.assertRaises(NxwrightError):
            build_page_file(self.page, {2: b"font two"}, "iso-8859-1")


class PageFileCommandTest(unittest.TestCase):
    """`nxwright page`: a page of a dump, as a page file."""

    def test_writes_page_file_from_a_dump(self):
        with tempfile.TemporaryDirectory() as folder:
            dump = Path(folder) / "dump"
            ProjectDumper(write_small_project(Path(folder)), dump).dump()
            output = Path(folder) / "page.page"
            write_page_file(dump, 1, output)
            # The command must pick the page by its ID.
            page_text = (dump / "pages" / "01-second.txt").read_text(encoding="utf-8")
            fonts = {int(path.stem): path.read_bytes() for path in (dump / "fonts").glob("*.zi")}
            self.assertEqual(output.read_bytes(),
                             build_page_file(page_from_text(page_text), fonts, "iso-8859-1"))

    def test_refuses_dump_in_old_format(self):
        # Older dumps name fonts by block number, so their font IDs would be wrong.
        with tempfile.TemporaryDirectory() as folder:
            dump = Path(folder)
            (dump / "project.txt").write_text("file               old.HMI\n")
            (dump / "pages").mkdir()
            (dump / "pages" / "00-main.txt").write_text("page main\n")
            with self.assertRaises(NxwrightError):
                write_page_file(dump, 0, dump / "out.page")
            self.assertFalse((dump / "out.page").exists())

    def test_refuses_an_existing_file_that_is_no_page_file(self):
        # As a mistyped output, such as a file of the dump.
        with tempfile.TemporaryDirectory() as folder:
            existing = Path(folder) / "out.page"
            existing.write_bytes(b"keep")
            with self.assertRaisesRegex(NxwrightError, "not a page file"):
                write_page_file(Path(folder), 0, existing)
            self.assertEqual(existing.read_bytes(), b"keep")

    def test_replaces_an_existing_page_file(self):
        # Written beside it first, as <name>.<random>.partial, then replacing it.
        with tempfile.TemporaryDirectory() as folder:
            dump = Path(folder) / "dump"
            ProjectDumper(write_small_project(Path(folder)), dump).dump()
            output = Path(folder) / "page.page"
            write_page_file(dump, 1, output)
            first = output.read_bytes()
            write_page_file(dump, 0, output)
            self.assertNotEqual(output.read_bytes(), first)
            self.assertEqual(list(Path(folder).glob("*.partial")), [])

    def test_a_write_that_fails_midway_leaves_the_existing_page_file(self):
        with tempfile.TemporaryDirectory() as folder:
            dump = Path(folder) / "dump"
            ProjectDumper(write_small_project(Path(folder)), dump).dump()
            output = Path(folder) / "page.page"
            write_page_file(dump, 1, output)
            first = output.read_bytes()
            with mock.patch.object(Path, "write_bytes", side_effect=OSError("the disk is full")), \
                    self.assertRaisesRegex(NxwrightError, "the disk is full"):
                write_page_file(dump, 0, output)
            self.assertEqual(output.read_bytes(), first)
            self.assertEqual(list(Path(folder).glob("*.partial")), [])


if __name__ == "__main__":
    unittest.main()
