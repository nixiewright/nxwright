"""The refs the frame writes for drawn components that overlap
(tft/overlaps.py): each drawn component's background fill and refs in the
probes that keep fixtures; each component's refs in each probe, as the
Nextion Editor wrote them; where they go; and what the rule covers.

Each test gives the function it checks its own input: a probe's pages made
in memory, in a Project of the facts it reads, and each component's place,
read from the probe's table (tests/tft/unit_inputs.py). The probes
(tools/tft/probing/overlap_probes.py) kept their fixtures through
frame_probes.stand_in_code. Their sample of whole files is in
tests/tft/test_whole_files.py.
"""
import unittest

from nxwright.tft.compile_context import CompileContext
from nxwright.tft import component_types, frame, overlaps
from tools.tft.probing import overlap_probes
from nxwright.tft.component_types import FILL, place_and_size
from nxwright.tft.matching import Need, matched_rules, project_needs, unmatched
from nxwright.tft.tft_file import encode_blocks
from tests.tft.unit_inputs import piece, place, probe_facts, probe_project

# Each component's refs in each probe, as the Nextion Editor wrote them:
# {probe: {page: {ID: refs}}}. A component of a page not given has none.
_CHAIN_OF_SIX = {1: [2, 3, 4, 5, 6], 2: [1, 3, 4, 5, 6], 3: [2, 1, 2, 4, 5, 6],
                 4: [3, 2, 1, 2, 3, 5, 6], 5: [4, 3, 2, 1, 2, 3, 4, 6],
                 6: [5, 4, 3, 2, 1, 2, 3, 4, 5]}
SEEN = {
    "overlap-two": {0: {1: [2], 2: [1]}},
    "overlap-by-one-pixel": {0: {1: [2], 2: [1]}},
    "overlap-two-beside-one-apart": {0: {1: [2], 2: [1]}},
    "overlap-one-inside-another": {0: {1: [2], 2: [1]}},
    "overlap-one-under-four": {0: {1: [2, 3, 4, 5], 2: [1, 3, 4, 5], 3: [1, 2, 4, 5],
                                   4: [1, 2, 3, 5], 5: [1, 2, 3, 4]}},
    "overlap-one-over-four": {0: {1: [2, 3, 4, 5], 2: [5, 1, 3, 4, 5], 3: [5, 1, 2, 4, 5],
                                  4: [5, 1, 2, 3, 5], 5: [1, 2, 3, 4]}},
    "overlap-chain-1-3-2": {0: {1: [2, 3], 2: [3, 1, 3], 3: [1, 2]}},
    "overlap-chain-1-2-3-4": {0: {1: [2, 3, 4], 2: [1, 3, 4], 3: [2, 1, 2, 4],
                                  4: [3, 2, 1, 2, 3]}},
    "overlap-chain-1-4-2-3": {0: {1: [2, 3, 4], 2: [3, 4, 1, 3, 4], 3: [2, 4, 1, 2, 4],
                                  4: [1, 2, 3]}},
    "overlap-chain-1-2-5-4-3": {0: {1: [2, 3, 4, 5], 2: [1, 3, 4, 5], 3: [4, 5, 2, 1, 2, 4, 5],
                                    4: [3, 5, 2, 1, 2, 3, 5], 5: [2, 1, 2, 3, 4]}},
    "overlap-chain-3-5-1-4-2": {0: {1: [2, 3, 4, 5], 2: [4, 1, 3, 4, 5], 3: [5, 1, 2, 4, 5],
                                    4: [1, 2, 3, 5], 5: [1, 2, 3, 4]}},
    "overlap-chain-1-4-5-3-6-beside-2": {0: {1: [3, 4, 5, 6], 3: [4, 5, 1, 4, 5, 6],
                                             4: [1, 3, 5, 6], 5: [3, 4, 1, 3, 4, 6],
                                             6: [3, 4, 5, 1, 3, 4, 5]}},
    "overlap-ids-past-9": {0: {11: [12, 13], 12: [11, 13], 13: [12, 11, 12]}},
    "overlap-on-second-page": {1: {1: [2], 2: [1]}},
    "overlap-event-code": {0: {1: [2], 2: [1]}},
    # The variable and the timer, 6 and 7, are not drawn.
    "overlap-types-under-a-picture": {0: {1: [2, 3, 4, 5, 8], 2: [8, 1, 3, 4, 5, 8],
                                          3: [8, 1, 2, 4, 5, 8], 4: [8, 1, 2, 3, 5, 8],
                                          5: [8, 1, 2, 3, 4, 8], 8: [1, 2, 3, 4, 5]}},
    "overlap-types-in-a-chain": {0: _CHAIN_OF_SIX},
    "overlap-more-types-under-a-picture": {0: {1: [2, 3, 4, 5], 2: [5, 1, 3, 4, 5],
                                               3: [5, 1, 2, 4, 5], 4: [5, 1, 2, 3, 5],
                                               5: [1, 2, 3, 4]}},
    "overlap-more-types-in-a-chain": {0: _CHAIN_OF_SIX},
    "overlap-hotspot-and-xfloat-under-a-picture": {0: {1: [2, 3, 4], 2: [4, 1, 3, 4],
                                                       3: [4, 1, 2, 4], 4: [1, 2, 3]}},
    "overlap-hotspot-and-xfloat-in-a-chain": {0: {1: [2, 3, 4], 2: [1, 3, 4],
                                                  3: [2, 1, 2, 4], 4: [3, 2, 1, 2, 3]}},
    "overlap-slider-gauge-qr-code-and-waveform-under-a-picture": {0: {
        1: [2, 3, 4, 5, 6], 2: [6, 1, 3, 4, 5, 6], 3: [6, 1, 2, 4, 5, 6], 4: [6, 1, 2, 3, 5, 6],
        5: [6, 1, 2, 3, 4, 6], 6: [1, 2, 3, 4, 5]}},
    "overlap-slider-gauge-qr-code-and-waveform-in-a-chain": {0: {
        1: [2, 3, 4, 5], 2: [1, 3, 4, 5], 3: [2, 1, 2, 4, 5], 4: [3, 2, 1, 2, 3, 5],
        5: [4, 3, 2, 1, 2, 3, 4]}},
    "overlap-scrolling-text-under-a-picture": {0: {
        1: [2, 3, 4, 5, 6, 7], 2: [1, 3, 4, 5, 6, 7], 3: [4, 7, 1, 2, 4, 5, 6, 7],
        4: [3, 7, 1, 2, 3, 5, 6, 7], 5: [6, 7, 1, 2, 3, 4, 6, 7], 6: [5, 7, 1, 2, 3, 4, 5, 7],
        7: [1, 2, 3, 4, 5, 6]}},
    "overlap-scrolling-text-in-a-chain": {0: {
        1: [2, 3, 4, 5], 2: [1, 3, 4, 5], 3: [2, 1, 2, 4, 5], 4: [3, 2, 1, 2, 3, 5],
        5: [4, 3, 2, 1, 2, 3, 4]}},
}


def probe_named(name: str):
    return next(probe for probe in overlap_probes.PROBES if probe.name == name)


def drawn_areas(page) -> dict:
    """Returns the area of each drawn component of `page`, by ID, as the
    frame gives them to overlaps.py."""
    return {number: place_and_size(item) for number, item in enumerate(page.objects)
            if number and getattr(component_types.object_module(item), "DRAWN", True)}


class PiecesTest(unittest.TestCase):
    """Each drawn component's background fill in each probe that keeps
    fixtures, then the refs of the components it overlaps (ref_blocks), and
    the run's 0 word, against its piece: its type's fill at its place from
    the probe's table, and the refs of the drawn components' areas on its
    page. The probes' other pieces are their types' and the frame's."""

    PROBES = [probe for probe in overlap_probes.PROBES if probe.fixtures is not None]

    def test_each_background_fill_and_its_refs(self):
        self.assertEqual(len(self.PROBES), 8)
        compared = refs = 0
        for probe in self.PROBES:
            project = probe_facts(probe)
            for number, page in enumerate(project.pages):
                areas = drawn_areas(page)
                for object_id in areas:
                    name = "page%d-%d-background-fill" % (number, object_id)
                    page_object = page.objects[object_id]
                    its_place = place(probe, "page%d-%d" % (number, object_id))
                    with self.subTest(probe.name, piece=name):
                        run = (component_types.object_module(page_object).background_fill(
                            page_object, project, its_place)
                            + overlaps.ref_blocks(CompileContext(project), areas, object_id))
                        self.assertEqual(encode_blocks(run + [b""]), piece(probe, name))
                    compared += 1
                    refs += len(overlaps.refreshed(areas, object_id))
        # 49 runs, which hold 191 refs in all.
        self.assertEqual((compared, refs), (49, 191))


class RefreshedTest(unittest.TestCase):
    """Which refs each component gets, and in which order (overlaps.refreshed)."""

    def test_each_probe_as_the_editor_wrote(self):
        self.assertEqual(sorted(SEEN), sorted(probe.name for probe in overlap_probes.PROBES))
        for probe in overlap_probes.PROBES:
            project = probe_facts(probe)
            for number, page in enumerate(project.pages):
                areas = drawn_areas(page)
                for object_id in areas:
                    with self.subTest(probe=probe.name, page=number, object_id=object_id):
                        self.assertEqual(overlaps.refreshed(areas, object_id),
                                         SEEN[probe.name].get(number, {}).get(object_id, []))

    def test_components_that_touch_get_none(self):
        # As the probe text-touching showed.
        areas = {1: (10, 10, 100, 30), 2: (110, 10, 100, 30), 3: (10, 40, 100, 30),
                 4: (110, 40, 100, 30)}
        self.assertEqual([overlaps.refreshed(areas, object_id) for object_id in areas],
                         [[], [], [], []])


class BlocksTest(unittest.TestCase):
    """The refs' blocks, and where the frame puts them."""

    def test_a_ref_block(self):
        # ref and the ID as text, as the statement encoder gives `ref 12`.
        project = probe_facts(probe_named("overlap-ids-past-9"))
        self.assertEqual(overlaps.ref_blocks(CompileContext(project),
                                             drawn_areas(project.pages[0]), 11),
                         [b"\x09\x03\x0412", b"\x09\x03\x0413"])

    def test_a_ref_block_on_k_and_f(self):
        # K and F number ref as T does, so the refs' blocks are T's.
        for series in ("K", "F"):
            with self.subTest(series):
                project = probe_facts(probe_named("overlap-ids-past-9"), series=series)
                self.assertEqual(
                    overlaps.ref_blocks(CompileContext(project), drawn_areas(project.pages[0]), 11),
                    [b"\x09\x03\x0412", b"\x09\x03\x0413"])

    def test_after_the_background_fill(self):
        # t0's background fill, then its ref of t1, then the run's 0 word.
        blocks = frame.user_code(probe_facts(probe_named("overlap-two"))).blocks
        fill = [number for number, block in enumerate(blocks)
                if block.startswith(FILL + b"10,10,100,30,")]
        self.assertEqual(len(fill), 1)
        self.assertEqual(blocks[fill[0] + 1:fill[0] + 3], [b"\x09\x03\x042", b""])


class MatchedTest(unittest.TestCase):
    """The overlaps overlaps.MATCHED covers (matching.py)."""

    def test_what_it_covers(self):
        covered = [Need("overlap", "text and picture", context={"types": ("text", "picture")}),
                   Need("overlap", "crop and progress-bar",
                        context={"types": ("crop", "progress-bar")}),
                   Need("overlap", "number and button", context={"types": ("number", "button")}),
                   Need("overlap", "checkbox and radio", context={"types": ("checkbox", "radio")}),
                   Need("overlap", "dual-state-button and text",
                        context={"types": ("dual-state-button", "text")}),
                   Need("overlap", "hotspot and xfloat", context={"types": ("hotspot", "xfloat")}),
                   Need("overlap", "slider and gauge", context={"types": ("slider", "gauge")}),
                   Need("overlap", "qr-code and waveform",
                        context={"types": ("qr-code", "waveform")}),
                   Need("overlap", "text and scrolling-text",
                        context={"types": ("text", "scrolling-text")})]
        self.assertEqual(unmatched(covered, overlaps.MATCHED), [])

    def test_what_it_leaves_out(self):
        # A type of P and E alone, on T, and an overlap without its types.
        left = [Need("overlap", "text and combo-box",
                     context={"types": ("text", "combo-box")}, series="T"),
                Need("overlap", "text and text")]
        self.assertEqual(unmatched(left, overlaps.MATCHED), left)

    def test_the_types_of_p_and_e_there_alone(self):
        # Each placed type of P and E alone, beside a text, and two of them
        # together, on P and E.
        pairs = [("text", name) for name in ("switch", "external-picture", "select", "combo-box",
                                             "sliding-text", "gmov", "video", "data-record",
                                             "file-browser")]
        pairs.append(("select", "gmov"))
        for series in ("P", "E"):
            for pair in pairs:
                with self.subTest(series=series, types=pair):
                    need = Need("overlap", "%s and %s" % pair, context={"types": pair},
                                series=series)
                    self.assertEqual(unmatched([need], overlaps.MATCHED), [])

    def test_the_check_lets_overlaps_through(self):
        for name in ("overlap-two", "overlap-types-under-a-picture",
                     "overlap-more-types-under-a-picture",
                     "overlap-hotspot-and-xfloat-under-a-picture",
                     "overlap-slider-gauge-qr-code-and-waveform-under-a-picture",
                     "overlap-scrolling-text-under-a-picture"):
            with self.subTest(probe=name):
                project = probe_project(probe_named(name))
                self.assertEqual(unmatched(project_needs(project), matched_rules()), [])

    def test_it_is_matched_on_every_series(self):
        # Its probes matched on K, F, P, and E too (k_probes.py, f_probes.py,
        # p_probes.py, e_probes.py).
        for series in ("K", "F", "P", "E"):
            with self.subTest(series):
                project = probe_project(probe_named("overlap-two"), series=series)
                self.assertEqual(unmatched(project_needs(project), matched_rules()), [])


if __name__ == "__main__":
    unittest.main()
