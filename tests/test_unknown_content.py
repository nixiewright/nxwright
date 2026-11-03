"""The finder of the things in a project that nxwright does not know, and how it
sorts each: kept exactly, written otherwise, may be lost, or cannot be kept
(source/unknown_content.py)."""
from pathlib import Path
from types import SimpleNamespace
import unittest

from nxwright.project.device_settings import DeviceSettings, manifest_header
from nxwright.project.page_block import Attribute, Marker, PageObject
from nxwright.project.resources import ImageSource, encode_image_source, parse_manifest
from nxwright.project.screen_models import model_named
from nxwright.source.unknown_content import (CANNOT_BE_KEPT, KEPT, MAY_BE_LOST,
                                             WRITTEN_OTHERWISE, UnknownContent, checked,
                                             unknown_in_blocks, unknown_in_manifest_entries,
                                             unknown_in_manifest_header,
                                             unknown_in_pages, unknown_in_picture_headers)
from tests.test_container import manifest

# A manifest header as the build writes it, for a model nxwright knows.
HEADER = manifest_header(DeviceSettings(model_named("NX4832T035"), 0, "iso-8859-1"))


def with_bytes(header: bytes, **places) -> bytes:
    """Returns `header` with each byte given as b<place>=value changed."""
    changed = bytearray(header)
    for name, value in places.items():
        changed[int(name[1:])] = value
    return bytes(changed)


def sorts(found: list) -> list:
    """Returns (where, sort) of each UnknownContent of `found`."""
    return [(each.where, each.sort) for each in found]


class BlocksTest(unittest.TestCase):

    def test_a_block_of_another_kind_may_be_lost(self):
        blocks = {"main.HMI": b"", "Program.s": b"", "0.pa": b"", "comcode.sn": b"",
                  "0.is": b"", "0.gmovs": b"", "2.xb": b"?"}
        self.assertEqual(sorts(unknown_in_blocks(blocks)), [("block 2.xb", MAY_BE_LOST)])


class CheckedTest(unittest.TestCase):

    def test_content_written_otherwise_is_a_warning_and_no_question(self):
        found = [UnknownContent("a page header form nxwright has not seen",
                                "block 0.pa, page header bytes 40 to 43", b"", WRITTEN_OTHERWISE)]
        notes = checked(Path("demo.HMI"), found, continue_with_unknown=False)
        self.assertIn("a page header form nxwright has not seen (block 0.pa, page header bytes 40 "
                      "to 43), which the next build writes as nxwright knows it", notes)


class ManifestTest(unittest.TestCase):

    def test_an_entry_of_another_kind_may_be_lost(self):
        listed = parse_manifest(manifest("0.pa", "0.xx", "0.i"))
        self.assertEqual(sorts(unknown_in_manifest_entries(listed)),
                         [("manifest entry 1", MAY_BE_LOST)])

    def test_the_current_and_the_older_form_are_known(self):
        older = with_bytes(HEADER, b9=0x43, b36=1, b65=2)
        for header in (HEADER, older):
            with self.subTest(header=header[:16].hex()):
                self.assertEqual(unknown_in_manifest_header(header), [])

    def test_a_constant_byte_of_another_value_may_be_lost(self):
        self.assertEqual(sorts(unknown_in_manifest_header(with_bytes(HEADER, b14=0x50))),
                         [("manifest header, byte 14", MAY_BE_LOST)])
        # One byte of the older form alone is neither form.
        self.assertEqual(sorts(unknown_in_manifest_header(with_bytes(HEADER, b9=0x43))),
                         [("manifest header, byte 9", MAY_BE_LOST)])
        self.assertEqual(sorts(unknown_in_manifest_header(with_bytes(HEADER, b70=1))),
                         [("manifest header, byte 70", MAY_BE_LOST)])

    def test_an_unknown_model_may_be_lost(self):
        header = with_bytes(HEADER, b16=0xEE, b17=0xEE)
        self.assertEqual(sorts(unknown_in_manifest_header(header)),
                         [("manifest header, bytes 16 to 19", MAY_BE_LOST)])

    def test_an_unknown_encoding_cannot_be_kept(self):
        self.assertEqual(sorts(unknown_in_manifest_header(with_bytes(HEADER, b13=0xEE))),
                         [("manifest header, byte 13", CANNOT_BE_KEPT)])

    def test_a_header_of_another_size_cannot_be_kept(self):
        self.assertEqual(sorts(unknown_in_manifest_header(HEADER + bytes(4))),
                         [("manifest header", CANNOT_BE_KEPT)])


class PictureHeadersTest(unittest.TestCase):

    def test_a_header_other_than_the_build_s_may_be_lost(self):
        block = encode_image_source(ImageSource(8, 4, b"\x89PNG data", ".png"))
        self.assertEqual(unknown_in_picture_headers({"0.is": block}), [])
        changed = block[:1] + b"\x0b" + block[2:]
        self.assertEqual(sorts(unknown_in_picture_headers({"0.is": changed})),
                         [("block 0.is", MAY_BE_LOST)])


# A page header's bytes 16 to 23 and 40 to 55, as the Nextion Editor 1.68.2
# writes them for an ordinary page of a project in iso-8859-1.
HEADER_16 = bytes.fromhex("00000000004f2100")
HEADER_40 = bytes.fromhex("01440203") + bytes(12)


def page(*objects, header_16: bytes = HEADER_16, header_40: bytes = HEADER_40) -> SimpleNamespace:
    """Returns a stand-in page holding `objects`, each a list of
    (name, bytes) attributes, its header's bytes 16 to 23 `header_16` and 40
    to 55 `header_40`."""
    return SimpleNamespace(name="page0", unknown_16=header_16, unknown_40=header_40, objects=[
        PageObject([Marker(b"att-%d" % len(attributes))]
                   + [Attribute(name, value) for name, value in attributes])
        for attributes in objects])


class PagesTest(unittest.TestCase):

    def test_known_types_and_attributes_are_not_found(self):
        text = [("type", bytes([116])), ("id", b"\1"), ("objname", b"t0"), ("aph", b"\x7f")]
        self.assertEqual(unknown_in_pages({"block 0.pa": page(text)}), [])

    def test_the_header_forms_seen_are_known(self):
        # The current form, and the older ones of pages the Nextion Editor
        # has not written since it was updated: the second was seen in 32
        # pages of a project for an NSPanel screen.
        for start in ("01440203", "01430100", "01440100"):
            with self.subTest(form=start):
                header_40 = bytes.fromhex(start) + bytes(12)
                self.assertEqual(unknown_in_pages({"block 0.pa": page(header_40=header_40)}), [])

    def test_a_header_form_not_seen_is_written_otherwise(self):
        # The build writes the current form, as the Nextion Editor does.
        header_40 = bytes.fromhex("01450100") + bytes(12)
        self.assertEqual(sorts(unknown_in_pages({"block 0.pa": page(header_40=header_40)})),
                         [("block 0.pa, page header bytes 40 to 43", WRITTEN_OTHERWISE)])

    def test_header_bytes_past_43_other_than_zero_may_be_lost(self):
        header_40 = bytes.fromhex("01440203") + bytes(11) + b"\1"
        self.assertEqual(sorts(unknown_in_pages({"block 0.pa": page(header_40=header_40)})),
                         [("block 0.pa, page header bytes 44 to 55", MAY_BE_LOST)])

    def test_a_header_value_not_seen_is_kept_in_its_own_field(self):
        for header_16, place in (("00000000024f2100", "byte 20"),
                                 ("00000000004f2200", "bytes 21 and 22"),
                                 ("00000000004f2105", "byte 23")):
            with self.subTest(header_16=header_16):
                found = unknown_in_pages({"block 0.pa": page(header_16=bytes.fromhex(header_16))})
                self.assertEqual(sorts(found), [("block 0.pa, page header " + place, KEPT)])

    def test_an_unknown_type_is_kept_exactly(self):
        found = unknown_in_pages({"block 0.pa": page([("type", bytes([200])), ("id", b"\1")])})
        self.assertEqual(sorts(found), [("block 0.pa, object 0", KEPT)])

    def test_an_unknown_attribute_is_kept_exactly(self):
        # As its stored bytes, in the page file's raw form.
        found = unknown_in_pages({"block 0.pa": page([("type", bytes([116])), ("newattr", b"\1")])})
        self.assertEqual(sorts(found), [("block 0.pa, object 0, attribute newattr", KEPT)])
        self.assertIn("does not know", found[0].what)

    def test_a_picture_attribute_s_bytes_keep_its_id(self):
        # A text's pic in 1 byte, where nxwright knows 2: its bytes give the
        # picture's ID, not its name.
        found = unknown_in_pages({"block 0.pa": page([("type", bytes([116])), ("pic", b"\1")])})
        self.assertEqual(sorts(found), [("block 0.pa, object 0, attribute pic", KEPT)])
        self.assertIn("give a resource's ID", found[0].what)

    def test_a_known_attribute_at_another_width_is_kept_exactly(self):
        found = unknown_in_pages({"block 0.pa": page([("type", bytes([116])), ("aph", b"\x7f\0")])})
        self.assertEqual(sorts(found), [("block 0.pa, object 0, attribute aph", KEPT)])
        self.assertIn("2 bytes, where nxwright knows 1", found[0].what)


if __name__ == "__main__":
    unittest.main()
