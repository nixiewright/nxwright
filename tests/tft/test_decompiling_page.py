"""The page's decoder (tft/decompiling/page.py), the jumps it reads
(tft/decompiling/jumps.py), and what every object's decoder shares
(tft/decompiling/objects.py): each against the pieces of the probes that
keep their whole user code, and the probe's own input.

Each test gives the decoder a DecodedPage and its DecodedObject made from
a probe's pieces (_decoded_object), as small as the decoder
needs: its record, its entries, its memory, and its runs.
"""
import unittest

from nxwright.project.attribute_values import number_from_bytes

from nxwright.tft import frame
from nxwright.tft.component_types import REF, SERIES_WRITTEN_AS_P, has_effect, value_operand
from nxwright.tft.control_statements import COMPARISON_HEAD, JUMP_START, comparison_block, jump_block
from nxwright.tft.decompiling import DecodeError
from nxwright.tft.decompiling.decoded_file import CodeRun, DecodedFile, DecodedObject, DecodedPage, Name
from nxwright.tft.decompiling.jumps import jump_targets
from nxwright.tft.decompiling.objects import decoded_values, object_memory, record_head
from nxwright.tft.decompiling.page import decoded_page_values, overlap_refs, page_load_runs
from nxwright.tft.label_numbers import CALL_START, GOTO_START
from tools.tft.probing import (for_probes, frame_probes, goto_probes, if_probes, overlap_probes,
                           shared_attribute_probes, while_probes)
from nxwright.tft.tft_file import split_blocks
from tests.tft.test_frame import _facts, _probes_of_the_user_code
from tests.tft.test_overlap import SEEN
from tests.tft.unit_inputs import blocks_place, piece, piece_names, place

# The attributes the page's decoder gives that the record keeps as the
# Nextion Editor's defaults when the page has none: its aph and its
# sendkey.
_RECORD_DEFAULTS = {"aph": 127, "sendkey": 0}


def _blocks(probe, name: str) -> list:
    """Returns the blocks of the piece `name` of `probe`, without the 0 word
    that ends its run, as the decoded file gives them."""
    blocks = split_blocks(piece(probe, name))
    return blocks[:-1] if blocks and blocks[-1] == b"" else blocks


def _decoded_object(probe, number: int, object_id: int) -> DecodedObject:
    """Returns the object `object_id` of the page `number` of `probe`, as
    the decoded file gives it: its record, its entries, its base, and its
    background fill, from the probe's pieces and its table. Its name and
    its events are left empty."""
    name = "page%d-%d" % (number, object_id)
    record = piece(probe, name + "-record")
    entries = piece(probe, name + "-entries")
    its_place = place(probe, name)
    fill = (_blocks(probe, name + "-background-fill")
            if name + "-background-fill" in piece_names(probe) else [])
    return DecodedObject(object_id, record[0], "", Name("", 0, True), bool(record[2]),
                         its_place.first_entry,
                         [entries[at:at + 24] for at in range(0, len(entries), 24)],
                         record, its_place.base, [], fill, {})


def _decoded_file(series: str, pages: list, int_area: bytes = b"") -> DecodedFile:
    """Returns a decoded file of `pages` on `series`, with `int_area`, and
    no int variable, macro, or code."""
    return DecodedFile(series, "", 0, "iso-8859-1", [], int_area, CodeRun(0, []), [], pages)


def _page_memory_test(probe, number: int):
    """Returns (the DecodedPage of the page `number` of `probe`, holding its
    own object alone, and the DecodedFile around it), with the page's
    memory where its base places it: in its page's memory, or in the int
    area for a global page."""
    page_object = _decoded_object(probe, number, 0)
    memory = piece(probe, "page%d-0-memory" % number)
    if page_object.is_global:
        page = DecodedPage(number, [page_object], 0, b"", CodeRun(0, []))
        int_area = bytes(page_object.base) + memory
    else:
        page = DecodedPage(number, [page_object], page_object.base, memory, CodeRun(0, []))
        int_area = b""
    return page, _decoded_file(probe.base, [page], int_area)


class PageValuesTest(unittest.TestCase):
    """A page's own attributes, read back from its record, its memory, and
    its entries (decoded_page_values), against the probe's own page, at
    the screen's place and size as the frame lays it out, for each page of
    each probe of the whole user code on T, K, and F."""

    def test_each_page(self):
        compared = global_pages = effects = 0
        for probe in _probes_of_the_user_code():
            project = _facts(probe)
            if project.settings.model.series in SERIES_WRITTEN_AS_P:
                continue
            for number, made in enumerate(project.pages):
                page_object = made.objects[0]
                page, decoded_file = _page_memory_test(probe, number)
                attributes = decoded_page_values(page, decoded_file).attributes
                with self.subTest(probe.name, page=number):
                    # The file keeps only whether a page has an effect.
                    self.assertEqual(bool(attributes.pop("effect")), has_effect(page_object))
                    self.assertEqual(attributes, {
                        name: (_RECORD_DEFAULTS[name] if page_object.attribute(name) is None
                               else number_from_bytes(page_object.attribute(name)))
                        for name in attributes})
                compared += 1
                global_pages += page.objects[0].is_global
                effects += has_effect(page_object)
        # 209 pages, of which 1 is global and 5 have an effect.
        self.assertEqual((compared, global_pages, effects), (209, 1, 5))

    def test_a_page_s_sendkey(self):
        # The one probe whose page has a sendkey, 3, which its record keeps.
        probe = next(probe for probe in shared_attribute_probes.PROBES
                     if probe.name == "shared-attributes-aph-and-sendkey-of-each-type")
        page, decoded_file = _page_memory_test(probe, 0)
        self.assertEqual(decoded_page_values(page, decoded_file).attributes["sendkey"], 3)

    def test_entries_of_no_page(self):
        # A page of 30 entries is neither a page of no background nor one
        # with an effect.
        probe = next(probe for probe in frame_probes.PROBES if probe.name == "frame-page-events")
        page, decoded_file = _page_memory_test(probe, 0)
        page.objects[0].entries = page.objects[0].entries[:30]
        with self.assertRaises(DecodeError):
            decoded_page_values(page, decoded_file)


class ObjectsTest(unittest.TestCase):
    """What every object's decoder shares: its record's head, its memory,
    and the dispatch to its type's decoder (objects.py)."""

    PROBE = next(probe for probe in overlap_probes.PROBES if probe.name == "overlap-two")

    def test_a_record_head(self):
        # Component 1 of overlap-two, a text at 10, 10, of 100 by 30.
        head = record_head(_decoded_object(self.PROBE, 0, 1))
        self.assertEqual(
            (head.type_number, head.object_id, head.is_global, head.drawn, head.x, head.y,
             head.w, head.h, head.sendkey, head.aph),
            (116, 1, False, True, 10, 10, 100, 30, 0, 127))
        self.assertEqual(head.background_fill_place,
                         blocks_place(self.PROBE, "page0-1-background-fill"))
        self.assertEqual(head.drawing_place, blocks_place(self.PROBE, "page0-1-drawing"))

    def test_memory_outside_its_page(self):
        decoded_object = _decoded_object(self.PROBE, 0, 1)
        page = DecodedPage(0, [decoded_object], decoded_object.base + 1, bytes(64),
                           CodeRun(0, []))
        self.assertRaises(DecodeError, object_memory, decoded_object, page,
                          _decoded_file("T", [page]), 4)

    def test_a_global_object_s_memory_past_the_int_area(self):
        decoded_object = _decoded_object(self.PROBE, 0, 1)
        decoded_object.record = decoded_object.record[:2] + b"\x01" + decoded_object.record[3:]
        page = DecodedPage(0, [decoded_object], 0, b"", CodeRun(0, []))
        decoded_file = _decoded_file("T", [page], bytes(decoded_object.base + 3))
        self.assertRaises(DecodeError, object_memory, decoded_object, page, decoded_file, 4)
        self.assertEqual(object_memory(decoded_object, page, decoded_file, 3), bytes(3))

    def test_a_type_without_a_decoder(self):
        decoded_object = _decoded_object(self.PROBE, 0, 1)
        decoded_object.type_name = "type 99"
        page = DecodedPage(0, [decoded_object], 0, b"", CodeRun(0, []))
        with self.assertRaisesRegex(DecodeError, "cannot decode a type 99 yet"):
            decoded_values(decoded_object, page, _decoded_file("T", [page]))


class OverlapRefsTest(unittest.TestCase):
    """The refs that end each drawn component's background fill
    (overlap_refs), read from the components' records and fills, against
    the refs the Nextion Editor wrote, for each probe of overlaps that keeps
    fixtures."""

    PROBES = [probe for probe in overlap_probes.PROBES if probe.fixtures is not None]

    def _page(self, probe, number: int) -> DecodedPage:
        objects = [_decoded_object(probe, number, object_id)
                   for object_id in range(len(_facts(probe).pages[number].objects))]
        return DecodedPage(number, objects, 0, b"", CodeRun(0, []))

    def test_each_probe(self):
        compared = 0
        for probe in self.PROBES:
            for number in range(len(_facts(probe).pages)):
                page = self._page(probe, number)
                with self.subTest(probe.name, page=number):
                    self.assertEqual(overlap_refs(page, _decoded_file("T", [page])), {
                        object_id: len(refs)
                        for object_id, refs in SEEN[probe.name].get(number, {}).items()})
                compared += 1
        self.assertEqual(compared, 8)

    def test_a_fill_without_its_refs(self):
        page = self._page(self.PROBES[0], 0)
        fill = page.objects[1].background_fill
        for changed in (fill[:-1], fill[:-1] + [REF + b"9"]):
            with self.subTest(changed):
                page.objects[1].background_fill = changed
                self.assertRaises(DecodeError, overlap_refs, page, _decoded_file("T", [page]))


class PageLoadRunsTest(unittest.TestCase):
    """How a page's load section is split into its load and loadend events'
    code (page_load_runs)."""

    DOEVENTS = frame.DOEVENTS["T"]

    def test_each_probe_with_load_code(self):
        # The probes whose page's load event has code, the probe of a
        # page's events and the probe of gotos in load and loadend, its
        # first page after a component's blocks there.
        probes = {probe.name: probe for probe in frame_probes.PROBES + goto_probes.PROBES}
        for name, components in (("frame-page-events", []),
                                 ("goto-in-load-loadend-and-a-second-page", ["page0-2-load"])):
            probe = probes[name]
            pieces = components + ["page0-0-event-load", "page0-doevents",
                                   "page0-0-event-loadend"]
            section = CodeRun(blocks_place(probe, pieces[0]),
                              [block for each in pieces for block in _blocks(probe, each)])
            page = DecodedPage(0, [], 0, b"", section)
            load, loadend = page_load_runs(page, _decoded_file("T", [page]),
                                           sum(len(_blocks(probe, each)) for each in components))
            with self.subTest(name):
                self.assertEqual(load, CodeRun(blocks_place(probe, "page0-0-event-load"),
                                               _blocks(probe, "page0-0-event-load")))
                self.assertEqual(loadend, CodeRun(blocks_place(probe, "page0-0-event-loadend"),
                                                  _blocks(probe, "page0-0-event-loadend")))

    def _split(self, blocks: list, components_blocks: int = 0, series: str = "T") -> tuple:
        page = DecodedPage(0, [], 0, b"", CodeRun(100, blocks))
        return page_load_runs(page, _decoded_file(series, [page]), components_blocks)

    def test_empty_load_and_loadend(self):
        self.assertEqual(self._split([self.DOEVENTS]), (CodeRun(100, []), CodeRun(107, [])))

    def test_after_the_components_blocks(self):
        self.assertEqual(self._split([self.DOEVENTS, b"x", self.DOEVENTS], 1),
                         (CodeRun(107, [b"x"]), CodeRun(119, [])))

    def test_the_first_doevents_no_jump_crosses(self):
        # The load event's if guards a doevents of its own: its comparison
        # jumps past it, so the split is at the next doevents.
        guarded = comparison_block(b"1", 1, b"1", 4 + len(self.DOEVENTS))
        load, loadend = self._split([guarded, self.DOEVENTS, self.DOEVENTS, b"y"])
        self.assertEqual(load, CodeRun(100, [guarded, self.DOEVENTS]))
        self.assertEqual(loadend, CodeRun(100 + 4 + len(guarded) + 2 * (4 + len(self.DOEVENTS)),
                                          [b"y"]))

    def test_a_doevents_at_the_end_of_load(self):
        # Either doevents splits the same bytes, and the first is taken.
        self.assertEqual(self._split([self.DOEVENTS, self.DOEVENTS]),
                         (CodeRun(100, []), CodeRun(107, [self.DOEVENTS])))

    def test_by_series(self):
        for series in ("K", "F"):
            with self.subTest(series):
                self.assertEqual(self._split([frame.DOEVENTS[series]], series=series),
                                 (CodeRun(100, []), CodeRun(107, [])))

    def test_no_doevents_to_split_at(self):
        # No doevents at all, or one a loop crosses: a while loop around a
        # doevents, its comparison jumping past the loop, and its jump
        # block back to the comparison.
        body = 4 + len(self.DOEVENTS) + 4 + len(jump_block(0))
        comparison = comparison_block(b"1", 1, b"1", body)
        size = 4 + len(comparison) + body
        loop = [comparison, self.DOEVENTS, jump_block(-size)]
        for blocks in ([], [b"x"], loop):
            with self.subTest(blocks):
                self.assertRaises(DecodeError, self._split, blocks)


class JumpTargetsTest(unittest.TestCase):
    """The jumps of a run of code (jump_targets)."""

    def test_each_kind(self):
        # A comparison that jumps 7 bytes, a jump block back 30, a goto, and
        # a call and an `i` of a short last number, which do not jump.
        comparison = comparison_block(b"sys0", 2, b"5", 7)
        blocks = [comparison, jump_block(-30), GOTO_START + value_operand(0x1234),
                  CALL_START + value_operand(0x40), b"\x09\x00\x04sys0,5,2,7"]
        run = CodeRun(0x100, blocks)
        first, second, third = run.block_places()[:3]
        self.assertEqual(jump_targets(run), [
            (first, first + 4 + len(comparison) + 7), (second, second + 4 + 7 - 30),
            (third, 0x1234)])

    def test_each_probe_of_control_statements(self):
        # Each jump of each run of code of the probes of if, while, for, and
        # goto that keep fixtures lands on one of its run's blocks, or at its
        # end. Some probes keep program.s's blocks without the user code
        # before them. Their run is given the place 0, which is enough for
        # comparisons and jump blocks, as they count from their own block.
        # A goto there would fail the test.
        starts = (COMPARISON_HEAD, JUMP_START, GOTO_START)
        jumps = 0
        for probe in (if_probes.PROBES + while_probes.PROBES + for_probes.PROBES
                      + goto_probes.PROBES):
            if probe.fixtures is None:
                continue
            for name in piece_names(probe):
                if name != "program-s" and "-event-" not in name:
                    continue
                whole = "first-block-head" in piece_names(probe)
                run = CodeRun(blocks_place(probe, name) if whole else 0,
                              split_blocks(piece(probe, name)))
                places = run.block_places()
                landings = set(places) | {places[-1] + 4 + len(run.blocks[-1])}
                found = jump_targets(run)
                # Every comparison, jump block, and goto is found.
                self.assertEqual(len(found), sum(block.startswith(starts) for block in run.blocks))
                for source, target in found:
                    with self.subTest(probe.name, piece=name, source=source):
                        self.assertIn(target, landings)
                jumps += len(found)
        self.assertEqual(jumps, 203)


if __name__ == "__main__":
    unittest.main()
