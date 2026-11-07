"""The probes of the Nextion Editor 1.63.3 (tools/tft/probing/older_editor_probes.py),
which keep its files' user code as their fixtures: each puts back
together into user code laid out as 1.63.3 lays it out
(ResearchNotes/tft/older-editors.md).
"""
import unittest

from tools.tft.probing import older_editor_probes
from tests.tft.unit_inputs import user_code_of

# The size of a record on T and K, and on P, where 1.63.3 gives each of its
# 108 slots: its head of 56 bytes, then 2 bytes a slot.
_RECORDS = {"T": 232, "K": 232, "P": 56 + 2 * 108}
# What pads the records, after the last, up to a multiple of 4 bytes from
# the user code's start.
_RECORDS_PADDING = 0xFF
# The size of the int area: 24 bytes for the project of pages, ints, and
# code, which declares two ints, and 16 for every other, which declares
# none. A data record is always global, so its memory lies in the int area
# after the ints, which makes the area larger (ResearchNotes/tft/p-series.md).
_INT_AREA, _INT_AREA_WITH_INTS = 16, 24


class OlderEditorProbesTest(unittest.TestCase):

    def test_each_probe_s_user_code(self):
        for probe in older_editor_probes.PROBES:
            code = user_code_of(probe)
            objects = sum(entry.objects for entry in code.index_entries())
            with self.subTest(probe.name):
                # A 0 word, the int area, then the page list, 6 bytes a page.
                self.assertEqual(code.blocks[0], bytes(4))
                if "-data-record-" in probe.name:
                    self.assertGreater(len(code.blocks[1]), _INT_AREA)
                else:
                    self.assertEqual(len(code.blocks[1]),
                                     _INT_AREA_WITH_INTS if probe.name.endswith("pages-ints-code")
                                     else _INT_AREA)
                self.assertEqual(len(code.blocks[2]), 6 * len(code.index_entries()))
                size = _RECORDS[probe.base] * objects
                end = code.places()["records"][0] + size
                self.assertEqual(code.records[size:], bytes([_RECORDS_PADDING]) * (-end % 4))
        self.assertEqual(sorted({probe.base for probe in older_editor_probes.PROBES}),
                         ["K", "P", "T"])


if __name__ == "__main__":
    unittest.main()
