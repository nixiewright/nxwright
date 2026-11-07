"""The listing (tft/decompiling/listing.py) of a decoded file, and the
listing command (tft/commands/listing.py) on a whole file of a probe."""
from pathlib import Path
import tempfile
import unittest

from nxwright.tft.decompiling.decoded_file import (CodeRun, DecodedFile, DecodedObject, DecodedPage,
                                            IntVariable, Macro, Name, Resource)
from nxwright.tft.decompiling.listing import listing_lines
from tools.tft.probing import k_probes
from tests.tft.test_commands import run
from tests.tft.unit_inputs import whole_file_of


def _object(object_id: int, type_name: str, name: Name, events: dict) -> DecodedObject:
    """Returns an object of `type_name` with two entries, from entry 10,
    a drawing of one block, and `events`."""
    return DecodedObject(object_id, 0, type_name, name, False, 10, [bytes(24)] * 2, b"", 20,
                         [b"\x09\x0d"], [], events)


class ListingTest(unittest.TestCase):

    def test_each_part(self):
        # A name no guess matched shows its checksum; a run without code
        # says so; each block shows its place.
        page = DecodedPage(0, [_object(0, "page", Name("page0", 1, True),
                                       {"down": CodeRun(0x40, [b"\x05\x00", b"\x01"])})],
                           16, b"\xff\xff", CodeRun(0x50, []))
        decoded = DecodedFile(
            "T", "NX4832T035", 90, "iso-8859-1",
            [IntVariable(Name("sys0", 2, True), 0), IntVariable(Name("int1", 0xAB, False), -5)],
            bytes(12), CodeRun(0x30, [b"\x09\x0b"]),
            [Macro(Name("macro0", 0xCD, False), 4, CodeRun(0x38, []))], [page],
            [Resource("font", 0, 300)])
        self.assertEqual(listing_lines(decoded), [
            "NX4832T035, series T, at 90 degrees, in iso-8859-1",
            "int variables:",
            "  sys0 = 0",
            "  int1 (no guess matched its checksum, 0x000000ab) = -5",
            "program.s:",
            "  0x30: 09 0b",
            "macro macro0 (no guess matched its checksum, 0x000000cd), labels from 4: no code",
            "page 0:",
            "  object 0, page0, a page, entries 10 to 11",
            "    drawing:",
            "      09 0d",
            "    down:",
            "      0x40: 05 00",
            "      0x46: 01",
            "  memory from 16: ff ff",
            "  load section: no code",
            "font 0: 300 bytes"])

    def test_the_attribute_names_on_p(self):
        # On P, the first block's table of attribute names, in its order,
        # follows the settings.
        decoded = DecodedFile("P", "NX8048P050", 0, "iso-8859-1", [], bytes(4), CodeRun(0x30, []),
                              [], [], attribute_names=["x", "y", "w"])
        self.assertEqual(listing_lines(decoded)[:3], [
            "NX8048P050, series P, at 0 degrees, in iso-8859-1",
            "attribute names: x, y, w",
            "int variables:"])

    def test_slots_without_a_name_on_p_of_1_63_3(self):
        # The Nextion Editor 1.63.3 writes no table of names on P, and the
        # decoded file's own table names no attribute for some slots, which
        # show by their number.
        decoded = DecodedFile("P", "NX8048P050", 0, "iso-8859-1", [], bytes(4), CodeRun(0x30, []),
                              [], [], attribute_names=[None, "vscope", None, "type"])
        self.assertEqual(listing_lines(decoded)[1],
                         "attribute names: slot 0, vscope, slot 2, type")


class ListingCommandTest(unittest.TestCase):

    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.addCleanup(self._folder.cleanup)

    def write(self, name: str, data: bytes) -> str:
        path = Path(self._folder.name) / name
        path.write_bytes(data)
        return str(path)

    def test_a_blank_project_on_k(self):
        probe = next(probe for probe in k_probes.PROBES if probe.name == "k-compile-T-blank")
        code, printed, _ = run(["tft-listing", self.write("blank.tft", whole_file_of(probe))])
        self.assertEqual(code, 0)
        lines = printed.splitlines()
        self.assertEqual(lines[0], "NX4832K035, series K, at 0 degrees, in iso-8859-1")
        self.assertIn("  object 0, page0, a page, entries 0 to 32", lines)
        self.assertRegex(lines[-1], r"^font 0: \d+ bytes$")

    def test_a_file_it_cannot_read(self):
        code, _, errors = run(["tft-listing", self.write("short.tft", b"too short")])
        self.assertEqual(code, 1)
        self.assertIn("nxwright tft-listing:", errors)


if __name__ == "__main__":
    unittest.main()
