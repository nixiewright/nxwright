"""The hotspot's decoder (tft/decompiling/component_types/hotspot.py): a
hotspot's attributes read back from its record and its entries, on T.

Each test decodes a probe's own user code, kept in its fixtures
(tests/tft/unit_inputs.py, user_code_of), and compares the values read back
with the probe's page, as nxwright's build gives it (unit_inputs.page_of):
the hotspot's probes, and those of the attributes every component with a
place has, among them hotspots with an effect and global ones.
"""
from types import SimpleNamespace
import unittest

from nxwright.project.attribute_values import number_from_bytes
from nxwright.project.object_types import TYPES_BY_NAME

from nxwright.tft.component_types import object_module
from nxwright.tft.decompiling import DecodeError
from nxwright.tft.decompiling.decoded_file import DecodedObject, Name, decoded_user_code
from nxwright.tft.decompiling.objects import AN_EFFECT, decoded_values
from tools.tft.probing import hotspot_probes, shared_attribute_probes
from tools.tft.probing.hotspot_probes import hotspot_component
from tools.tft.probing.probe_runner import FIXTURES
from tests.tft.unit_inputs import (page, page_of, piece, place, probe_change, project_of,
                               user_code_of)

# A decoded file of T, of which the decoder reads only the series, for an
# object decoded alone.
_T_FILE = SimpleNamespace(series="T")
# What a hotspot's decoder gives: the attributes its file keeps. The file
# keeps only whether it has an effect.
_KEPT = ("x", "y", "w", "h", "vscope", "aph", "sendkey")


def _hotspots(probe) -> list:
    """Returns (the ObjectValues of each hotspot of `probe`'s page, that
    hotspot's page object), in ID order."""
    decoded = decoded_user_code(user_code_of(probe), "T", "NX4832T035", 0, "iso-8859-1")
    name = probe_change(probe).page
    [decoded_page] = [each for each in decoded.pages if each.objects[0].name.text == name]
    expected = page_of(probe).objects
    return [(decoded_values(each, decoded_page, decoded), expected[each.object_id])
            for each in decoded_page.objects if each.type_name == "hotspot"]


class HotspotTest(unittest.TestCase):

    def test_each_probe(self):
        # Each hotspot of each probe that keeps its user code: its place and
        # size, its vscope, aph, and sendkey, and whether it has an effect,
        # as its page gives them.
        compared, effects, global_ones = 0, 0, 0
        for probe in hotspot_probes.PROBES + shared_attribute_probes.PROBES:
            # A probe of code keeps its event's blocks alone, and page_of
            # gives the page of a probe of one page of components alone.
            if probe.fixtures is None or not (
                    FIXTURES / probe.fixtures / probe.name / "records.bin").exists() or not (
                    hasattr(probe_change(probe), "page")):
                continue
            for values, page_object in _hotspots(probe):
                with self.subTest(probe.name, hotspot=values.attributes.get("x")):
                    expected = {name: number_from_bytes(page_object.attribute(name))
                                for name in _KEPT}
                    expected["effect"] = (
                        AN_EFFECT if number_from_bytes(page_object.attribute("effect")) else 0)
                    self.assertEqual(values.attributes, expected)
                    self.assertEqual(values.added, {})
                    compared += 1
                    effects += bool(expected["effect"])
                    global_ones += expected["vscope"]
        # A global one among them. The probe of effects lays out pages of
        # its own, which page_of does not give (test_with_an_effect).
        self.assertEqual((compared >= 4, effects, global_ones > 0), (True, 0, True))

    def test_with_an_effect(self):
        # An effect gives a hotspot two more entries, which are empty, as
        # its first entry after a drawn object's is without one. So the
        # compile writes a hotspot's entries here, without an effect and
        # with one, in hotspot-two's first hotspot's place, and the decoder
        # tells them apart by their number. One entry more is no hotspot's.
        probe = next(probe for probe in hotspot_probes.PROBES if probe.name == "hotspot-two")
        where = place(probe, "page0-1")
        for effect in (0, 3):
            with self.subTest(effect=effect):
                page_object = page(hotspot_component(effect=effect)).objects[1]
                entries = object_module(page_object).data(page_object, project_of(page()),
                                                          where)
                decoded_object = _hotspot_of(probe, where, entries)
                values = decoded_values(decoded_object, None, _T_FILE)
                self.assertEqual(values.attributes["effect"], AN_EFFECT if effect else 0)
        decoded_object = _hotspot_of(probe, where, entries + bytes(24))
        self.assertRaises(DecodeError, decoded_values, decoded_object, None, _T_FILE)


def _hotspot_of(probe, where, entries: bytes) -> DecodedObject:
    """Returns a hotspot of the entries `entries`, at the place `where`,
    with the record of `probe`'s first hotspot."""
    return DecodedObject(1, TYPES_BY_NAME["hotspot"], "hotspot", Name("m0", 0, True), False,
                         where.first_entry,
                         [entries[at:at + 24] for at in range(0, len(entries), 24)],
                         piece(probe, "page0-1-record"), where.base, [], [], {})


if __name__ == "__main__":
    unittest.main()
