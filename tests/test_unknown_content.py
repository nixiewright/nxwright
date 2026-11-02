"""The finder of the things in a project that nxwright does not know, and how it
sorts each: kept exactly, may be lost, or cannot be kept
(source/unknown_content.py)."""
from types import SimpleNamespace
import unittest

from nxwright.project.device_settings import DeviceSettings, manifest_header
from nxwright.project.page_block import Attribute, Marker, PageObject
from nxwright.project.resources import ImageSource, encode_image_source, parse_manifest
from nxwright.project.screen_models import model_named
from nxwright.source.unknown_content import (CANNOT_BE_KEPT, KEPT, MAY_BE_LOST,
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
                  "0.is": b"", "0.gmovs": b"", "2.ib": b"?"}
        self.assertEqual(sorts(unknown_in_blocks(blocks)), [("block 2.ib", MAY_BE_LOST)])


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


def page(*objects) -> SimpleNamespace:
    """Returns a stand-in page holding `objects`, each a list of
    (name, bytes) attributes."""
    return SimpleNamespace(objects=[
        PageObject([Marker(b"att-%d" % len(attributes))]
                   + [Attribute(name, value) for name, value in attributes])
        for attributes in objects])


class PagesTest(unittest.TestCase):

    def test_known_types_and_attributes_are_not_found(self):
        text = [("type", bytes([116])), ("id", b"\1"), ("objname", b"t0"), ("aph", b"\x7f")]
        self.assertEqual(unknown_in_pages({"block 0.pa": page(text)}), [])

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
