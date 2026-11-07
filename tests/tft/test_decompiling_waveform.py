"""The waveform's decoder (tft/decompiling/component_types/waveform.py): a
waveform's attributes read back from its record, its entries, and its
memory, on T, and the block the Nextion Editor adds to its page's load
section, which draws it.

Each test decodes a waveform probe's own user code, kept in its fixtures
(tests/tft/unit_inputs.py, user_code_of), and compares the values read back
with the probe's page, as nxwright's build gives it (unit_inputs.page_of).
"""
from dataclasses import replace
import unittest

from nxwright.project.attribute_values import number_from_bytes

from nxwright.tft.decompiling import DecodeError
from nxwright.tft.decompiling.decoded_file import decoded_user_code
from nxwright.tft.decompiling.objects import AN_EFFECT, decoded_values
from tools.tft.probing import waveform_probes
from tools.tft.probing.probe_runner import FIXTURES
from tests.tft.unit_inputs import page_of, probe_change, user_code_of

# The attributes every waveform's file keeps.
_KEPT = ("x", "y", "w", "h", "vscope", "aph", "sendkey", "sta", "dir", "ch", "objWid",
         "objHig", "inittrue", "dis")
# What lies behind it, by its sta, and its grid, which a colour behind it
# alone keeps.
_BEHIND = {0: "picc", 1: "bco", 2: "pic"}
_GRID = ("gdc", "gdw", "gdh")


def _probes() -> list:
    """Returns the waveform probes that keep their user code."""
    return [probe for probe in waveform_probes.PROBES if probe.fixtures is not None
            and (FIXTURES / probe.fixtures / probe.name / "records.bin").exists()]


def _waveforms(probe) -> tuple:
    """Returns (the decoded file of `probe`, its page of components, and
    (each waveform's DecodedObject, its page object), in ID order)."""
    decoded = decoded_user_code(user_code_of(probe), "T", "NX4832T035", 0, "iso-8859-1")
    name = probe_change(probe).page
    [decoded_page] = [each for each in decoded.pages if each.objects[0].name.text == name]
    expected = page_of(probe).objects
    return decoded, decoded_page, [(each, expected[each.object_id])
                                   for each in decoded_page.objects
                                   if each.type_name == "waveform"]


class WaveformTest(unittest.TestCase):

    def test_each_probe(self):
        # Each waveform of each probe that keeps its user code: what every
        # drawn component keeps, its values, what lies behind it by its sta,
        # its grid behind a colour alone, a colour for each of its channels,
        # as its page gives them, and its load section's block.
        compared, stas, channels = 0, set(), set()
        for probe in _probes():
            decoded, decoded_page, waveforms = _waveforms(probe)
            for each, page_object in waveforms:
                with self.subTest(probe.name, waveform=each.object_id):
                    def number(name: str) -> int:
                        return number_from_bytes(page_object.attribute(name))
                    expected = {name: number(name) for name in _KEPT}
                    sta, ch = expected["sta"], expected["ch"]
                    names = ((_BEHIND[sta],) + (_GRID if sta == 1 else ())
                             + tuple("pco%d" % channel for channel in range(ch)))
                    expected.update({name: number(name) for name in names})
                    expected["effect"] = AN_EFFECT if number("effect") else 0
                    values = decoded_values(each, decoded_page, decoded)
                    self.assertEqual(values.attributes, expected)
                    self.assertEqual(values.added, {"load": (1, 0)})
                    compared += 1
                    stas.add(sta)
                    channels.add(ch)
        self.assertEqual((compared >= 8, stas, channels), (True, {0, 1, 2}, {1, 2, 3, 4}))

    def test_without_its_load_block(self):
        # A waveform whose page's load section does not draw it is not laid
        # out as the compile writes one.
        decoded, decoded_page, waveforms = _waveforms(_probes()[0])
        each, _ = waveforms[0]
        emptied = replace(decoded_page, load_section=replace(decoded_page.load_section,
                                                             blocks=[]))
        self.assertRaises(DecodeError, decoded_values, each, emptied, decoded)

    def test_a_sta_or_a_ch_t_does_not_take(self):
        # A waveform's memory giving a sta of 3, nothing behind it, which T,
        # K, and F do not take, or a ch of 0 or 5, which no waveform has, is
        # refused.
        decoded, decoded_page, waveforms = _waveforms(_probes()[0])
        each, _ = waveforms[0]
        for at, value in ((0, 3), (2, 0), (2, 5)):
            with self.subTest(at=at, value=value):
                memory = bytearray(decoded_page.memory)
                memory[each.base - decoded_page.memory_start + at] = value
                changed = replace(decoded_page, memory=bytes(memory))
                self.assertRaises(DecodeError, decoded_values, each, changed, decoded)


if __name__ == "__main__":
    unittest.main()
