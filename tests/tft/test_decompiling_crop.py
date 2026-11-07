"""The crop's decoder (tft/decompiling/component_types/crop.py): a crop's
attributes read back from its record, its entries, and its memory, on T.

Each test decodes a crop probe's own user code, kept in its fixtures
(tests/tft/unit_inputs.py, user_code_of), and compares the values read back
with the probe's page, as nxwright's build gives it (unit_inputs.page_of).
"""
from types import SimpleNamespace
import unittest

from nxwright.project.attribute_values import number_from_bytes
from nxwright.project.object_types import TYPES_BY_NAME

from nxwright.tft.component_types import object_module
from nxwright.tft.decompiling.decoded_file import (CodeRun, DecodedObject, DecodedPage, Name,
                                            decoded_user_code)
from nxwright.tft.decompiling.objects import decoded_values
from tools.tft.probing import crop_probes
from tools.tft.probing.crop_probes import crop_component
from tools.tft.probing.probe_runner import FIXTURES
from tests.tft.unit_inputs import (page, page_of, piece, place, probe_change, project_of,
                               user_code_of)

# A decoded file of T, of which the decoder reads only the series, for an
# object decoded alone.
_T_FILE = SimpleNamespace(series="T")
# What a crop's decoder gives: the attributes its file keeps.
_KEPT = ("x", "y", "w", "h", "vscope", "aph", "sendkey", "effect", "picc")
_STARTS = ("vvs0", "vvs1")


def _crops(probe) -> list:
    """Returns (the ObjectValues of each crop of `probe`'s page, that crop's
    page object), in ID order."""
    decoded = decoded_user_code(user_code_of(probe), "T", "NX4832T035", 0, "iso-8859-1")
    name = probe_change(probe).page
    [decoded_page] = [each for each in decoded.pages if each.objects[0].name.text == name]
    expected = page_of(probe).objects
    return [(decoded_values(each, decoded_page, decoded), expected[each.object_id])
            for each in decoded_page.objects if each.type_name == "crop"]


class CropTest(unittest.TestCase):

    def test_each_probe(self):
        # Each crop of each probe that keeps its user code: its place and
        # size, its vscope, aph, sendkey, and effect, its picc, the
        # project's picture it shows a part of or 65535 for none, and where
        # its part starts, as its page gives them.
        compared = 0
        for probe in crop_probes.PROBES:
            # A probe of code keeps its event's blocks alone.
            if probe.fixtures is None or not (
                    FIXTURES / probe.fixtures / probe.name / "records.bin").exists():
                continue
            for values, page_object in _crops(probe):
                with self.subTest(probe.name, crop=values.attributes.get("x")):
                    # These probes start each crop at 0, 0, which the screen
                    # reads as it is (test_its_starts).
                    expected = {name: number_from_bytes(page_object.attribute(name))
                                for name in _KEPT + _STARTS}
                    self.assertEqual(values.attributes, expected)
                    self.assertEqual(values.added, {})
                    compared += 1
        self.assertGreaterEqual(compared, 4)

    def test_its_starts(self):
        # The probes that keep their user code start every crop at 0, 0, and
        # give none an effect. So the compile writes a crop's entries and
        # memory here, at each start the other crop probes tried, without an
        # effect and with one, which moves its own entries two on, in
        # crop-two's first crop's place. The decoder reads each start back
        # as the page file keeps it, 2 bytes, unsigned, though the screen
        # reads 65437 as -99, and 40000 as -25536.
        probe = next(probe for probe in crop_probes.PROBES if probe.name == "crop-two")
        where = place(probe, "page0-1")
        project = project_of(page(), pictures=1)
        for effect in (0, 1):
            for vvs0, vvs1 in ((5, 7), (300, 500), (1000, 32767), (65437, 64537),
                               (40000, 65535)):
                with self.subTest(effect=effect, vvs0=vvs0, vvs1=vvs1):
                    page_object = page(crop_component(vvs0=vvs0, vvs1=vvs1, effect=effect),
                                       pictures=("bg",)).objects[1]
                    module = object_module(page_object)
                    entries = module.data(page_object, project, where)
                    decoded_object = DecodedObject(
                        1, TYPES_BY_NAME["crop"], "crop", Name("q0", 0, True), False,
                        where.first_entry,
                        [entries[at:at + 24] for at in range(0, len(entries), 24)],
                        piece(probe, "page0-1-record"), where.base, [], [], {})
                    decoded_page = DecodedPage(0, [], where.base,
                                               module.memory(page_object, project),
                                               CodeRun(0, []))
                    values = decoded_values(decoded_object, decoded_page, _T_FILE).attributes
                    self.assertEqual(
                        (values["effect"], values["picc"], values["vvs0"], values["vvs1"]),
                        (effect, 0, vvs0, vvs1))


if __name__ == "__main__":
    unittest.main()
