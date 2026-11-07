"""The hotspot component (tft/component_types/hotspot.py): its drawing,
its background fill, its memory, and its entries, what its list matched,
the attributes code may use, and its memory and entries on P.

Each test gives the function it checks that function's own input: a page
object of a probe's components (tools/tft/probing/hotspot_probes.py), made by
nxwright's page reader, a Project of the facts it reads, and the object's
place, read from the probe's table (tests/tft/unit_inputs.py). It compares the
result with one piece of the probe's fixtures, which the probe runner wrote
once the probe matched the Nextion Editor's file. Each probe that keeps
fixtures is compared so, on T and on P. What the frame writes across
objects, such as a hotspot's record and the head of its memory on P, is
left to the frame's tests, and compared until then by the sample of whole
files (tests/tft/test_whole_files.py).
"""
import struct
import unittest

from nxwright.tft.compile_context import CompileContext
from nxwright.tft import component_types, frame
from nxwright.tft.component_types import hotspot
from nxwright.tft.matching import Need, matched_rules, project_needs, unmatched
from tools.tft.probing import hotspot_probes, p_probes
from tools.tft.probing.hotspot_probes import hotspot_component
from nxwright.tft.statements import CodePlace, StatementError, encode_line
from nxwright.tft.tft_file import encode_blocks
from tests.tft.p_components import PTypePieces, p_probe
from tests.tft.t_components import CodePieces, TypePieces
from tests.tft.unit_inputs import page, piece_names, place, probe_project, project_of


def value(number: int) -> bytes:
    return number.to_bytes(2, "little", signed=True)


class PiecesTest(TypePieces, CodePieces, unittest.TestCase):
    """Each hotspot of each probe that keeps its whole user code, at its
    type's functions, and its probe of code, at the statement encoder,
    against the probe's pieces (tests/tft/t_components.py): two hotspots on a
    page, one among the types matched, and one on a second page, numbered on
    from the first's. Its drawing is a 0 word alone; its entries are a drawn
    object's alone: its type, ID, vscope, place, size, and edges. Its probe
    of code takes m0 and m1 by their IDs in vis, tsw, click, and ref."""

    TYPE = "hotspot"
    PROBES = hotspot_probes.PROBES
    COUNT = 4
    CODE_COUNT = 1

    def test_its_memory(self):
        # It keeps no memory, so its probes give no piece of it.
        for probe, page_object, its_place, project in self.components:
            with self.subTest(probe.name, object_id=its_place.object_id):
                self.assertEqual(hotspot.memory(page_object, project), b"")
                self.assertNotIn("page%d-%d-memory" % (its_place.page, its_place.object_id),
                                 piece_names(probe))

    def test_its_background_fill(self):
        # The plain fill of its area, then a 0 word.
        self.assert_each(lambda page_object, project, its_place: encode_blocks(
            hotspot.background_fill(page_object, project, its_place) + [b""]),
            "background-fill")


class PPiecesTest(PTypePieces, CodePieces, unittest.TestCase):
    """Each hotspot of each of its probes on P that keeps its whole user
    code, at its type's functions on P, and its probe of code, against the
    probe's pieces (tests/tft/p_components.py). Its values after its record's
    head are its effect's slot, its first, and its time, at their defaults.
    Its entries give its drag's, aph's, and effect's defaults, 0, 127, and
    0, and the others their places, from its base."""

    TYPE = "hotspot"
    PROBES = [probe for probe in p_probes.PROBES if probe.name.startswith("p-hotspot-")]
    COUNT = 4
    CODE_COUNT = 1


class MatchedTest(unittest.TestCase):
    """The needs hotspot.MATCHED covers (matching.py)."""

    def need(self, attribute: str, number: int, **context) -> Need:
        attributes = {"x": value(10), "y": value(10), "w": value(100), "h": value(50)}
        attributes.update({name: value(other) for name, other in context.items()})
        return Need("attribute", "hotspot." + attribute, value(number), context=attributes)

    def test_what_it_covers(self):
        covered = [Need("type", "hotspot"), Need("attribute", "hotspot.objname", b"m0"),
                   self.need("x", 220, x=220, y=430), self.need("w", 2, x=0, y=0, w=2, h=2),
                   self.need("h", 480, x=0, y=0, w=320, h=480)]
        self.assertEqual(unmatched(covered, hotspot.MATCHED), [])

    def test_what_it_leaves_out(self):
        left = [self.need("drag", 1)]
        self.assertEqual(unmatched(left, hotspot.MATCHED), left)


class CodeTest(unittest.TestCase):
    """Code may read the attributes a hotspot writes, and takes a hotspot in
    the screen's commands. The encoder reads the page's components."""

    def test_its_attributes(self):
        # Its x and w, entries 9 and 11 within the type, after m0's first
        # entry, 33; but not one it does not write.
        project = project_of(page(hotspot_component()))
        place = CodePlace(0, "page0", "up")
        for attribute, entry in (("x", 9), ("w", 11)):
            with self.subTest(attribute=attribute):
                self.assertEqual(encode_line("sys0=m0.%s" % attribute, place,
                                             CompileContext(project)),
                                 b"\x05\x00\x00\x00\x00=\x01" + (33 + entry).to_bytes(4, "little"))
        with self.assertRaisesRegex(StatementError, "m0's pco is not encoded"):
            encode_line("sys0=m0.pco", place, CompileContext(project))

    def test_the_check_takes_every_probe(self):
        # Each probe's page matched the Nextion Editor's, so the check,
        # through the hotspot's rules and those of the statements and the
        # commands, lets it through.
        for probe in hotspot_probes.PROBES:
            with self.subTest(probe=probe.name):
                self.assertEqual(unmatched(project_needs(probe_project(probe)),
                                           matched_rules()), [])


class OnPTest(unittest.TestCase):
    """On P, the bytes it writes in its head, and its values and entries at
    attributes no probe of its pieces sets, at the type's functions. Its
    memory is 56 bytes: the 52 of a whole head, then its effect's values.
    Its entries are a drawn component's, but its drag's, aph's, and
    effect's, 4, 6, and 15, which give their values themselves (P_ENTRIES).
    Each probe's values and entries are compared in PPiecesTest."""

    # The size of the head its memory starts with, by the frame's rule: a
    # whole head's, 52 bytes.
    HEAD = frame._p_head_size(hotspot)

    @classmethod
    def setUpClass(cls):
        cls.project = project_of(series="P")
        # The place of p-hotspot-two's first hotspot, from its table, for a
        # hotspot of a page made in memory.
        cls.place = place(p_probe("p-hotspot-two"), "page0-1")

    def table(self, page_object, project=None) -> dict:
        return component_types.p_table(hotspot, page_object, project or self.project)

    def test_what_it_writes_in_its_head(self):
        # A 0 at 32 and at 34, where a drawn component's memory keeps its
        # drag and its aph, whatever they are, as their entries give their
        # values themselves: at their defaults, and at a drag of 1 and an
        # aph of 50.
        for page_object in (page(hotspot_component(), series="P").objects[1],
                            page(hotspot_component(drag=1, aph=50), series="P").objects[1]):
            with self.subTest(page_object.attribute("drag")):
                self.assertEqual(hotspot.p_memory_extras(page_object, self.project, self.place),
                                 {32: b"\x00", 34: b"\x00"})

    def test_its_values_and_entries_with_the_attributes_every_component_has(self):
        # As the Nextion Editor wrote them (p-hotspot-shared-attributes): its
        # effect as 0 at 52, then its first, 10, and its time, 500; its drag's,
        # aph's, and effect's entries give its own values, 1, 50, and 2.
        page_object = page(hotspot_component(
            aph=50, sendkey=3, drag=1, lockobj=1, movex=5, movey=6, groupid0=1, groupid1=2,
            effect=2, first=10, time=500), series="P").objects[1]
        table = self.table(page_object)
        memory = component_types.p_component_memory(page_object, bytes(self.HEAD), table,
                                                    hotspot.P_MEMORY_SIZE)
        self.assertEqual(memory[self.HEAD:].hex(" "), "00 0a f4 01")
        # Its drag's, aph's, and effect's entries give their values
        # themselves, whatever its place: here, a probe's first hotspot's.
        entries = component_types.p_component_entries(table, hotspot.ENTRIES, self.place)
        self.assertEqual({number: struct.unpack_from("<IiiiII", entries, number * 24)[1]
                          for number in (4, 6, 15)}, {4: 1, 6: 50, 15: 2})

    def test_it_is_matched_on_p_and_e(self):
        for series in ("P", "E"):
            with self.subTest(series):
                self.assertEqual(unmatched([Need("type", "hotspot", series=series)],
                                           matched_rules()), [])


if __name__ == "__main__":
    unittest.main()
