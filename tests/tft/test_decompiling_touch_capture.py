"""The touch capture's decoder (tft/decompiling/component_types/
touch_capture.py): a touch capture's vscope and val read back from its
record and its memory, on T, and the block the Nextion Editor adds to its
page's load section for it.

Each test decodes a touch capture probe's own user code, kept in its
fixtures (tests/tft/unit_inputs.py, user_code_of), and compares the values read
back with the probe's page, as nxwright's build gives it
(unit_inputs.page_of).
"""
from dataclasses import replace
import unittest

from nxwright.project.attribute_values import number_from_bytes

from nxwright.tft.decompiling import DecodeError
from nxwright.tft.decompiling.decoded_file import decoded_user_code
from nxwright.tft.decompiling.objects import decoded_values
from tools.tft.probing import touch_capture_probes
from tools.tft.probing.probe_runner import FIXTURES
from tests.tft.unit_inputs import page_of, probe_change, user_code_of


def _probes() -> list:
    """Returns the touch capture probes that keep their user code."""
    return [probe for probe in touch_capture_probes.PROBES if probe.fixtures is not None
            and (FIXTURES / probe.fixtures / probe.name / "records.bin").exists()]


def _captures(probe) -> tuple:
    """Returns (the decoded file of `probe`, its page of components, and
    (each touch capture's DecodedObject, its page object), in ID order)."""
    decoded = decoded_user_code(user_code_of(probe), "T", "NX4832T035", 0, "iso-8859-1")
    name = probe_change(probe).page
    [decoded_page] = [each for each in decoded.pages if each.objects[0].name.text == name]
    expected = page_of(probe).objects
    return decoded, decoded_page, [(each, expected[each.object_id])
                                   for each in decoded_page.objects
                                   if each.type_name == "touch-capture"]


class TouchCaptureTest(unittest.TestCase):

    def test_each_probe(self):
        # Each touch capture of each probe that keeps its user code: its
        # vscope and val, as its page gives them, and its load section's
        # block.
        compared = 0
        for probe in _probes():
            decoded, decoded_page, captures = _captures(probe)
            for each, page_object in captures:
                with self.subTest(probe.name, capture=each.object_id):
                    values = decoded_values(each, decoded_page, decoded)
                    self.assertEqual(values.attributes, {
                        name: number_from_bytes(page_object.attribute(name))
                        for name in ("vscope", "val")})
                    self.assertEqual(values.added, {"load": (1, 0)})
                    compared += 1
        self.assertGreaterEqual(compared, 3)

    def test_without_its_load_block(self):
        # A touch capture whose page's load section has no block for it is
        # not laid out as the compile writes one.
        decoded, decoded_page, captures = _captures(_probes()[0])
        each, _ = captures[0]
        emptied = replace(decoded_page, load_section=replace(decoded_page.load_section,
                                                             blocks=[]))
        self.assertRaises(DecodeError, decoded_values, each, emptied, decoded)


if __name__ == "__main__":
    unittest.main()
