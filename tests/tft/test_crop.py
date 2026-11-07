"""The crop component (tft/component_types/crop.py): its drawing, its
memory, its entries, what its list matched, and which of its attributes
code may use, on T and on P.

Each test gives the function it checks a probe's page, made in memory from
the probe's components (tools/tft/probing/crop_probes.py), in a Project of the
facts it reads, and its place, read from the probe's table
(tests/tft/unit_inputs.py). Each crop of each probe that keeps fixtures is
compared with the probe's pieces (tests/tft/t_components.py), and one probe on
each series is compared whole in tests/tft/test_whole_files.py.
"""
import struct
import unittest

from nxwright.tft.compile_context import CompileContext
from nxwright.tft.component_types import crop
from nxwright.tft.matching import Need, matched_rules, project_needs, unmatched
from tools.tft.probing import crop_probes, p_probes
from nxwright.tft.statements import CodePlace, StatementError, encode_line
from tests.tft.line_context import line_context
from tests.tft.p_components import PTypePieces, p_entries, p_values
from tests.tft.t_components import CodePieces, TypePieces
from tests.tft.unit_inputs import place, probe_facts, probe_project


def value(number: int, size: int = 2) -> bytes:
    return number.to_bytes(size, "little", signed=True)


def probe_named(name: str):
    return next(probe for probe in crop_probes.PROBES if probe.name == name)


def first_crop(name: str) -> tuple:
    """Returns page0's first component of the probe `name`, the Project of
    facts of its pages, and its place, as its table gives it. A probe that
    keeps no fixtures has no table, and its crop takes the place of
    crop-two's first, the first component of a page as it is too."""
    probe = probe_named(name)
    project = probe_facts(probe)
    kept = probe if probe.fixtures is not None else probe_named("crop-two")
    return project.pages[0].objects[1], project, place(kept, "page0-1")


class DrawingTest(unittest.TestCase):
    """A crop's drawing, its memory, and its entries."""

    def test_its_drawing(self):
        # xpic: its place and size, where its part starts as text, and its
        # picc's entry. q0's first entry is 33, so its picc's is 52.
        q0, project, place_of_q0 = first_crop("crop-starting-elsewhere")
        self.assertEqual(crop.drawing(q0, project, place_of_q0),
                         [b"\x09\x0a\x0410,20,50,30,10+5,20+7,\x01" + struct.pack("<I", 52)])

    def test_a_start_past_32767(self):
        # The screen reads a vvs0 or vvs1 as signed 16 bits: 40000 is -25536
        # and 65535 is -1. In the drawing, each is a number as code gives
        # one: -1 as text, -25536 as 03 and its value.
        q0, project, place_of_q0 = first_crop("crop-starting-past-32767")
        self.assertEqual(crop.drawing(q0, project, place_of_q0),
                         [b"\x09\x0a\x0410,20,50,30,10+\x03" + struct.pack("<i", -25536)
                          + b",20+-1,\x01" + struct.pack("<I", 52)])
        data = crop.data(q0, project, place_of_q0)
        self.assertEqual([struct.unpack_from("<i", data, 24 * number + 4)[0]
                          for number in (20, 21)], [-25536, -1])

    def test_its_memory(self):
        # Its picc, 2 bytes, then six zeros: none is 65535, and a picc past
        # the project's pictures is written as it is.
        for name, memory in (("crop-one", b"\x00\x00"), ("crop-of-none", b"\xff\xff"),
                             ("crop-of-a-number-past-the-last", b"\x05\x00")):
            with self.subTest(probe=name):
                q0, project, _ = first_crop(name)
                self.assertEqual(crop.memory(q0, project), memory + bytes(6))

    def test_its_entries(self):
        # Entry 19, its picc's, gives the project's pictures less 1 as its
        # highest; entries 20 and 21 give its vvs0 and vvs1 as their values.
        q0, project, place_of_q0 = first_crop("crop-starting-elsewhere")
        data = crop.data(q0, project, place_of_q0)

        def entry(number: int) -> tuple:
            return struct.unpack_from("<IiiiII", data, 24 * number)
        self.assertEqual(entry(19)[2], 0)
        self.assertEqual(entry(20)[1:4], (5, 0x7FFFFFFF, -0x80000000))
        self.assertEqual(entry(21)[1], 7)


class PiecesTest(TypePieces, CodePieces, unittest.TestCase):
    """Each crop of each probe that keeps its whole user code, at its type's
    functions, and each probe of code, at the statement encoder, against
    the probe's pieces (tests/tft/t_components.py)."""

    TYPE = "crop"
    PROBES = crop_probes.PROBES
    COUNT = 4
    CODE_COUNT = 1


class PPiecesTest(PTypePieces, CodePieces, unittest.TestCase):
    """Each crop of each of its probes on P that keeps its whole user code,
    at its type's functions on P, and each probe of code, against the
    probe's pieces (tests/tft/p_components.py)."""

    TYPE = "crop"
    PROBES = [probe for probe in p_probes.PROBES if probe.name.startswith("p-crop-")]
    COUNT = 4
    CODE_COUNT = 1


class MatchedTest(unittest.TestCase):
    """The needs crop.MATCHED covers (matching.py)."""

    def test_what_it_covers(self):
        covered = [Need("type", "crop"), Need("attribute", "crop.objname", b"q0"),
                   Need("attribute", "crop.picc", value(0)),
                   Need("attribute", "crop.picc", (65535).to_bytes(2, "little")),
                   Need("attribute", "crop.vvs0", value(300)),
                   Need("attribute", "crop.vvs1", value(500))]
        self.assertEqual(unmatched(covered, crop.MATCHED), [])

    def test_what_it_leaves_out(self):
        left = [Need("attribute", "crop.aph", value(64, 1))]
        self.assertEqual(unmatched(left, crop.MATCHED), left)

    def test_it_is_matched_on_k(self):
        # Its probes matched on K too (k_probes.py).
        project = probe_project(probe_named("crop-one"), series="K")
        self.assertEqual(unmatched(project_needs(project), matched_rules()), [])


class CodeTest(unittest.TestCase):
    """Code may use a crop's picc, and any other attribute it writes."""

    @classmethod
    def setUpClass(cls):
        cls.project = probe_facts(probe_named("crop-one"))

    def test_its_picc(self):
        self.assertEqual(encode_line("q0.picc=1", CodePlace(0, "page0", "up"),
                                     CompileContext(self.project)),
                         b"\x01\x34\x00\x00\x00=1")

    def test_its_other_attributes(self):
        # Any attribute it writes, such as its vvs0, entry 20 within the type,
        # after q0's first entry, 33; but not one it does not write.
        place_in_code = CodePlace(0, "page0", "up")
        self.assertEqual(encode_line("sys0=q0.vvs0", place_in_code, CompileContext(self.project)),
                         b"\x05\x00\x00\x00\x00=\x01" + (33 + 20).to_bytes(4, "little"))
        with self.assertRaisesRegex(StatementError, "q0's pic is not encoded"):
            encode_line("sys0=q0.pic", place_in_code, CompileContext(self.project))

    def test_the_check_refuses_setting_its_vvs0_and_vvs1_on_t(self):
        # nxwright's tables say the T series refuses code that sets them, and
        # a component's x, while it takes code that reads them.
        page = line_context(crop_probes.crop_component(picc=None))
        rules = matched_rules()
        for line in ("q0.vvs0=1", "q0.vvs1++", "q0.x=1"):
            with self.subTest(line):
                need = Need("code", "event", line, context=page, series="T")
                self.assertEqual(unmatched([need], rules), [need])
        self.assertEqual(unmatched([Need("code", "event", "sys0=q0.vvs0+q0.x", context=page,
                                         series="T")], rules), [])

    def test_the_check_lets_its_picc_through(self):
        project = probe_project(probe_named("crop-picc-in-code"))
        self.assertEqual(unmatched(project_needs(project), matched_rules()), [])


class OnPTest(unittest.TestCase):
    """On P: its memory's values, after its record's head and its effect's
    values, and its entries."""

    def test_its_memory_and_entries(self):
        # crop-starting-elsewhere's page on P, its crop at p-crop-two's
        # first crop's place. After its effect's 4 bytes: its picc, the first
        # picture, its vvs0, 5, and its vvs1, 7, 2 bytes each, and two 0
        # bytes. Its entries 19, 20, and 21 give their places, 56, 58, and 60
        # past its base, where T's vvs entries give their values.
        project = probe_facts(probe_named("crop-starting-elsewhere"), "P")
        q0 = project.pages[0].objects[1]
        kept = next(probe for probe in p_probes.PROBES if probe.name == "p-crop-two")
        place_of_q0 = place(kept, "page0-1")
        base = place_of_q0.base
        self.assertEqual(p_values(q0, place_of_q0, project)[4:12].hex(" "),
                         "00 00 05 00 07 00 00 00")
        entries = p_entries(q0, place_of_q0, project)
        self.assertEqual([struct.unpack_from("<iiiiII", entries, number * 24)[1:]
                          for number in (19, 20, 21)],
                         [(base + 56, 0, 0, 0x100, 0x232),
                          (base + 58, 0x7FFFFFFF, -0x80000000, 0x100, 0x238),
                          (base + 60, 0x7FFFFFFF, -0x80000000, 0x100, 0x238)])

    def test_it_is_matched_on_p_and_e(self):
        for series in ("P", "E"):
            with self.subTest(series):
                self.assertEqual(unmatched([Need("type", "crop", series=series)],
                                           matched_rules()), [])

    def test_the_check_takes_setting_its_vvs0_and_vvs1_on_p(self):
        # They lie in its memory there, and p_probes.py's crop-vvs-in-code
        # matched the Nextion Editor's file.
        page = line_context(crop_probes.crop_component(picc=None))
        for line in ("q0.vvs0=5", "q0.vvs1++", "sys0=q0.vvs0+q0.vvs1"):
            with self.subTest(line):
                need = Need("code", "event", line, context=page, series="P")
                self.assertEqual(unmatched([need], matched_rules()), [])


if __name__ == "__main__":
    unittest.main()
