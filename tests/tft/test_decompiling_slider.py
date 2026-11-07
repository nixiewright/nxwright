"""The slider's decoder (tft/decompiling/component_types/slider.py): a
slider's attributes read back from its record, its entries, and its
memory, on T, and the block the Nextion Editor adds to its page's load
section, which draws it.

Each test decodes a slider probe's own user code, kept in its fixtures
(tests/tft/unit_inputs.py, user_code_of), and compares the values read back
with the probe's page, as nxwright's build gives it (unit_inputs.page_of).
"""
from dataclasses import replace
import unittest

from nxwright.project.attribute_values import number_from_bytes

from nxwright.tft.decompiling import DecodeError
from nxwright.tft.decompiling.decoded_file import decoded_user_code
from nxwright.tft.decompiling.objects import AN_EFFECT, decoded_values
from tools.tft.probing import slider_probes
from tools.tft.probing.probe_runner import FIXTURES
from tests.tft.unit_inputs import page_of, probe_change, user_code_of

# The attributes every slider's file keeps.
_KEPT = ("x", "y", "w", "h", "vscope", "aph", "sendkey", "mode", "sta", "psta", "wid", "hig",
         "val", "maxval", "minval")
# What lies behind its track, by its sta, and its cursor, by its psta.
_TRACKS = {0: ("picc", "picc1"), 1: ("bco", "bco1"), 2: ("pic", "pic1")}
_CURSORS = {0: "pco", 1: "pic2"}
# What a slider keeps with a colour behind its track alone.
_COLOURED = ("dis", "ch")


def _probes() -> list:
    """Returns the slider probes that keep their user code."""
    return [probe for probe in slider_probes.PROBES if probe.fixtures is not None
            and (FIXTURES / probe.fixtures / probe.name / "records.bin").exists()]


def _sliders(probe) -> tuple:
    """Returns (the decoded file of `probe`, its page of components, and
    (each slider's DecodedObject, its page object), in ID order)."""
    decoded = decoded_user_code(user_code_of(probe), "T", "NX4832T035", 0, "iso-8859-1")
    name = probe_change(probe).page
    [decoded_page] = [each for each in decoded.pages if each.objects[0].name.text == name]
    expected = page_of(probe).objects
    return decoded, decoded_page, [(each, expected[each.object_id])
                                   for each in decoded_page.objects
                                   if each.type_name == "slider"]


class SliderTest(unittest.TestCase):

    def test_each_probe(self):
        # Each slider of each probe that keeps its user code: what every
        # drawn component keeps, its values, what lies behind its track by
        # its sta, its cursor by its psta, its dis and ch behind a colour
        # alone, as its page gives them, and its load section's block.
        compared, stas, pstas = 0, set(), set()
        for probe in _probes():
            decoded, decoded_page, sliders = _sliders(probe)
            for each, page_object in sliders:
                with self.subTest(probe.name, slider=each.object_id):
                    def number(name: str) -> int:
                        return number_from_bytes(page_object.attribute(name))
                    expected = {name: number(name) for name in _KEPT}
                    sta, psta = expected["sta"], expected["psta"]
                    names = _TRACKS[sta] + (_CURSORS[psta],) + (_COLOURED if sta == 1 else ())
                    expected.update({name: number(name) for name in names})
                    expected["effect"] = AN_EFFECT if number("effect") else 0
                    values = decoded_values(each, decoded_page, decoded)
                    self.assertEqual(values.attributes, expected)
                    self.assertEqual(values.added, {"load": (1, 0)})
                    compared += 1
                    stas.add(sta)
                    pstas.add(psta)
        self.assertEqual((compared >= 8, stas, pstas), (True, {0, 1, 2}, {0, 1}))

    def test_without_its_load_block(self):
        # A slider whose page's load section does not draw it is not laid out
        # as the compile writes one.
        decoded, decoded_page, sliders = _sliders(_probes()[0])
        each, _ = sliders[0]
        emptied = replace(decoded_page, load_section=replace(decoded_page.load_section,
                                                             blocks=[]))
        self.assertRaises(DecodeError, decoded_values, each, emptied, decoded)

    def test_a_sta_or_a_psta_t_does_not_take(self):
        # A slider's memory giving a sta of 3, or a psta of 2, a square
        # cursor, which T, K, and F do not take, is refused.
        decoded, decoded_page, sliders = _sliders(_probes()[0])
        each, _ = sliders[0]
        for at, value in ((1, 3), (2, 2)):
            with self.subTest(at=at, value=value):
                memory = bytearray(decoded_page.memory)
                memory[each.base - decoded_page.memory_start + at] = value
                changed = replace(decoded_page, memory=bytes(memory))
                self.assertRaises(DecodeError, decoded_values, each, changed, decoded)


if __name__ == "__main__":
    unittest.main()
