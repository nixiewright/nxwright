"""The gauge's decoder (tft/decompiling/component_types/gauge.py): a
gauge's attributes read back from its record, its entries, and its memory,
on T.

Each test decodes a gauge probe's own user code, kept in its fixtures
(tests/tft/unit_inputs.py, user_code_of), and compares the values read back
with the probe's page, as nxwright's build gives it (unit_inputs.page_of).
"""
from dataclasses import replace
import unittest

from nxwright.project.attribute_values import number_from_bytes

from nxwright.tft.decompiling import DecodeError
from nxwright.tft.decompiling.decoded_file import decoded_user_code
from nxwright.tft.decompiling.objects import AN_EFFECT, decoded_values
from tools.tft.probing import gauge_probes
from tools.tft.probing.probe_runner import FIXTURES
from tests.tft.unit_inputs import page_of, probe_change, user_code_of

# The attributes a gauge's file keeps, but the one that gives what lies
# behind it, which its sta picks.
_KEPT = ("x", "y", "w", "h", "vscope", "aph", "sendkey", "sta", "val", "format", "up", "down",
         "left", "pco", "pco2", "hig", "wid", "vvs0", "vvs1", "vvs2")
# What lies behind a gauge, by its sta: a crop of a picture, a colour, or a
# picture.
_BEHIND = {0: "picc", 1: "bco", 2: "pic"}


def _gauges(probe) -> list:
    """Returns (the ObjectValues of each gauge of `probe`'s page, that
    gauge's page object), in ID order."""
    decoded = decoded_user_code(user_code_of(probe), "T", "NX4832T035", 0, "iso-8859-1")
    name = probe_change(probe).page
    [decoded_page] = [each for each in decoded.pages if each.objects[0].name.text == name]
    expected = page_of(probe).objects
    return [(decoded_values(each, decoded_page, decoded), expected[each.object_id])
            for each in decoded_page.objects if each.type_name == "gauge"]


class GaugeTest(unittest.TestCase):

    def test_each_probe(self):
        # Each gauge of each probe that keeps its user code: what every
        # drawn component keeps, its sta and what lies behind it, by its
        # sta, and its needle's and its colours' values, as its page gives
        # them.
        compared, stas = 0, set()
        for probe in gauge_probes.PROBES:
            # A probe of code keeps its event's blocks alone.
            if probe.fixtures is None or not (
                    FIXTURES / probe.fixtures / probe.name / "records.bin").exists():
                continue
            for values, page_object in _gauges(probe):
                with self.subTest(probe.name, gauge=values.attributes.get("x")):
                    expected = {name: number_from_bytes(page_object.attribute(name))
                                for name in _KEPT}
                    behind = _BEHIND[expected["sta"]]
                    expected[behind] = number_from_bytes(page_object.attribute(behind))
                    expected["effect"] = (
                        AN_EFFECT if number_from_bytes(page_object.attribute("effect")) else 0)
                    self.assertEqual(values.attributes, expected)
                    self.assertEqual(values.added, {})
                    compared += 1
                    stas.add(expected["sta"])
        # Gauges of each of the three stas T takes.
        self.assertEqual((compared >= 6, stas), (True, {0, 1, 2}))

    def test_a_sta_t_does_not_take(self):
        # A gauge's memory giving a sta of 3, nothing behind it, which T,
        # K, and F do not take, or of 5, which no gauge has, is refused.
        probe = next(probe for probe in gauge_probes.PROBES if probe.name == "gauge-two")
        decoded = decoded_user_code(user_code_of(probe), "T", "NX4832T035", 0, "iso-8859-1")
        page = decoded.pages[0]
        gauge = next(each for each in page.objects if each.type_name == "gauge")
        for sta in (3, 5):
            with self.subTest(sta=sta):
                memory = bytearray(page.memory)
                memory[gauge.base - page.memory_start] = sta
                changed = replace(page, memory=bytes(memory))
                self.assertRaises(DecodeError, decoded_values, gauge, changed, decoded)


if __name__ == "__main__":
    unittest.main()
