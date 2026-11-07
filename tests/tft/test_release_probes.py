"""The probes of the Nextion Editor 1.60.1's layout
(tools/tft/probing/editor_1_60_1_probes.py), which keep its files' user code as
their fixtures: each puts back together into user code laid out as the
releases before 1.63 lay it out (ResearchNotes/tft/older-editors.md). And the
helpers of the release probes (tools/tft/probing/release_probes.py).
"""
import unittest

from tools.tft.probing import editor_1_60_1_probes, release_probes
from tests.tft.unit_inputs import user_code_of

# The size of a record on T and K, and on P, where the releases before 1.63
# give each of 98 slots: its head of 56 bytes, then 2 bytes a slot.
_RECORDS = {"T": 232, "K": 232, "P": 56 + 2 * 98}
# What pads the records, after the last, up to a multiple of 4 bytes from
# the user code's start.
_RECORDS_PADDING = 0xFF
# A page's entry in the page index, and in the page list.
_INDEX_ENTRY, _PAGE_LIST_ENTRY = 12, 6
# The int area, and the pages of each project: the project of pages, ints,
# and code declares two ints on three pages; the blank one none, on one.
_INT_AREA, _INT_AREA_WITH_INTS = 16, 24
_PAGES, _PAGES_OF_INTS_AND_CODE = 1, 3


class LayoutBefore163Test(unittest.TestCase):

    def test_each_layout_probe_s_user_code(self):
        probes = [probe for probe in editor_1_60_1_probes.PROBES
                  if probe.name.endswith(("compile-T-blank", "compile-T-pages-ints-code"))]
        for probe in probes:
            code = user_code_of(probe)
            ints = probe.name.endswith("pages-ints-code")
            pages = _PAGES_OF_INTS_AND_CODE if ints else _PAGES
            with self.subTest(probe.name):
                # The int area, then the page list, with no 0 word before
                # them.
                self.assertEqual(len(code.blocks[0]), _INT_AREA_WITH_INTS if ints else _INT_AREA)
                self.assertEqual(len(code.blocks[1]), _PAGE_LIST_ENTRY * pages)
                self.assertEqual(len(code.page_index), _INDEX_ENTRY * pages)
                # Each page is its one object, as these projects have no
                # components.
                size = _RECORDS[probe.base] * pages
                end = code.places()["records"][0] + size
                self.assertEqual(code.records[size:], bytes([_RECORDS_PADDING]) * (-end % 4))
        self.assertEqual(sorted({probe.base for probe in probes}), ["K", "P", "T"])
        self.assertEqual(len(probes), 6)


class DisupTest(unittest.TestCase):
    """disup on a page of P, which the Nextion Editor's run alone used."""

    def test_disup_after_the_page_s_drag(self):
        page = ("page page0\nheader_size = 56\n\nobject 0 page0\n  marker att-28\n"
                "  type = 121\n  drag = 0\n  sendkey = 0\n\nobject 1 t0\n  marker att-5\n"
                "  drag = 0\n")
        self.assertEqual(release_probes._page_with_disup(page),
                         "page page0\nheader_size = 56\n\nobject 0 page0\n  marker att-29\n"
                         "  type = 121\n  drag = 0\n  disup:u8 = 0\n  sendkey = 0\n\n"
                         "object 1 t0\n  marker att-5\n  drag = 0\n")
        with self.assertRaises(ValueError):
            release_probes._page_with_disup("object 0 page0\n  marker att-28\n  drag = 1\n")


if __name__ == "__main__":
    unittest.main()
