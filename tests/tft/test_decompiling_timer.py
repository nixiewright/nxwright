"""The timer's decoder (tft/decompiling/component_types/timer.py): a
timer's attributes read back from its record and its memory, on T, and the
code the Nextion Editor writes of its own for it, which the source folder
leaves out: the "S " block that starts its timer event, and the two blocks
it adds to its page's load section.

Each test decodes a timer probe's own user code, kept in its fixtures
(tests/tft/unit_inputs.py, user_code_of), and compares the values read back
with the probe's page, as nxwright's build gives it (unit_inputs.page_of).
"""
from dataclasses import replace
import unittest

from nxwright.project.attribute_values import number_from_bytes

from nxwright.tft.decompiling import DecodeError
from nxwright.tft.decompiling.decoded_file import decoded_user_code
from nxwright.tft.decompiling.objects import decoded_values
from tools.tft.probing import timer_probes
from tools.tft.probing.probe_runner import FIXTURES
from tests.tft.unit_inputs import page_of, probe_change, user_code_of

# What a timer's decoder gives: the attributes its file keeps.
_KEPT = ("vscope", "tim", "en")
# What the Nextion Editor adds for a timer: an "S " block at the start of
# its timer event, and timerset and an "L " block at the start of its
# page's load section.
_ADDED = {"timer": (1, 0), "load": (2, 0)}


def _probes() -> list:
    """Returns the timer probes that keep their user code, of one page of
    components."""
    return [probe for probe in timer_probes.PROBES if probe.fixtures is not None
            and (FIXTURES / probe.fixtures / probe.name / "records.bin").exists()
            and hasattr(probe_change(probe), "page")]


def _timers(probe) -> tuple:
    """Returns (the decoded file of `probe`, its page of components, and
    (each timer's DecodedObject, its page object), in ID order)."""
    decoded = decoded_user_code(user_code_of(probe), "T", "NX4832T035", 0, "iso-8859-1")
    name = probe_change(probe).page
    [decoded_page] = [each for each in decoded.pages if each.objects[0].name.text == name]
    expected = page_of(probe).objects
    return decoded, decoded_page, [(each, expected[each.object_id])
                                   for each in decoded_page.objects
                                   if each.type_name == "timer"]


class TimerTest(unittest.TestCase):

    def test_each_probe(self):
        # Each timer of each probe that keeps its user code: its vscope,
        # tim, and en, as its page gives them, and the blocks the Nextion
        # Editor added for it.
        compared = 0
        for probe in _probes():
            decoded, decoded_page, timers = _timers(probe)
            for each, page_object in timers:
                with self.subTest(probe.name, timer=each.object_id):
                    values = decoded_values(each, decoded_page, decoded)
                    self.assertEqual(values.attributes, {
                        name: number_from_bytes(page_object.attribute(name)) for name in _KEPT})
                    self.assertEqual(values.added, _ADDED)
                    compared += 1
        self.assertGreaterEqual(compared, 4)

    def test_load_blocks_of_another_timer(self):
        # A timer whose code's place no "L " block of its page's load section
        # gives is not laid out as the compile writes one.
        decoded, decoded_page, timers = _timers(_probes()[0])
        each, _ = timers[0]
        moved = replace(each, events={"timer": replace(
            each.events["timer"], place=each.events["timer"].place + 4)})
        self.assertRaises(DecodeError, decoded_values, moved, decoded_page, decoded)


if __name__ == "__main__":
    unittest.main()
