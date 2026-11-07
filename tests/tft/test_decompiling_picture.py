"""The picture's decoder (tft/decompiling/component_types/picture.py): a
picture's attributes read back from its record, its entries, and its
memory, on T.

Each test decodes a picture probe's own user code, kept in its fixtures
(tests/tft/unit_inputs.py, user_code_of), and compares the values read back
with the probe's page, as nxwright's build gives it (unit_inputs.page_of).
"""
import unittest

from nxwright.project.attribute_values import number_from_bytes

from nxwright.tft.decompiling.decoded_file import decoded_user_code
from nxwright.tft.decompiling.objects import decoded_values
from tools.tft.probing import picture_probes
from tools.tft.probing.probe_runner import FIXTURES
from tests.tft.unit_inputs import page_of, probe_change, user_code_of

# What a picture's decoder gives: the attributes its file keeps.
_KEPT = ("x", "y", "w", "h", "vscope", "aph", "sendkey", "effect", "pic")


def _pictures(probe) -> list:
    """Returns (the ObjectValues of each picture of `probe`'s page, that
    picture's page object), in ID order."""
    decoded = decoded_user_code(user_code_of(probe), "T", "NX4832T035", 0, "iso-8859-1")
    name = probe_change(probe).page
    [page] = [page for page in decoded.pages if page.objects[0].name.text == name]
    expected = page_of(probe).objects
    return [(decoded_values(each, page, decoded), expected[each.object_id])
            for each in page.objects if each.type_name == "picture"]


class PictureTest(unittest.TestCase):

    def test_each_probe(self):
        # Each picture of each probe that keeps its user code: its place
        # and size, its vscope, aph, sendkey, and effect, and its pic, the
        # project's picture it shows or 65535 for none, as its page gives
        # them.
        compared = 0
        for probe in picture_probes.PROBES:
            # A probe of code keeps its event's blocks alone.
            if probe.fixtures is None or not (
                    FIXTURES / probe.fixtures / probe.name / "records.bin").exists():
                continue
            for values, page_object in _pictures(probe):
                with self.subTest(probe.name, picture=values.attributes.get("x")):
                    self.assertEqual(sorted(values.attributes), sorted(_KEPT))
                    self.assertEqual(values.attributes, {
                        name: number_from_bytes(page_object.attribute(name)) for name in _KEPT})
                    self.assertEqual(values.added, {})
                    compared += 1
        self.assertGreaterEqual(compared, 4)


if __name__ == "__main__":
    unittest.main()
