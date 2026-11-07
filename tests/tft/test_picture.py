"""The picture component (tft/component_types/picture.py): its drawing, its
memory, its pic's entry, what its list matched, and which of its
attributes code may use, on T and on P.

Each test gives the function it checks a probe's page, made in memory from
the probe's components (tools/tft/probing/picture_probes.py), in a Project of
the facts it reads, and its place, read from the probe's table
(tests/tft/unit_inputs.py). Each picture of each probe that keeps fixtures is
compared with the probe's pieces (tests/tft/t_components.py), and one probe on
each series is compared whole in tests/tft/test_whole_files.py.
"""
import struct
import unittest

from nxwright.tft.compile_context import CompileContext
from nxwright.tft.component_types import picture
from nxwright.tft.matching import Need, matched_rules, project_needs, unmatched
from tools.tft.probing import p_probes, picture_probes
from nxwright.tft.statements import CodePlace, StatementError, encode_line
from tests.tft.p_components import PTypePieces, p_entries, p_values
from tests.tft.t_components import CodePieces, TypePieces
from tests.tft.unit_inputs import page, place, probe_facts, probe_project, project_of


def value(number: int, size: int = 2) -> bytes:
    return number.to_bytes(size, "little", signed=True)


def probe_named(name: str):
    return next(probe for probe in picture_probes.PROBES if probe.name == name)


def place_of(name: str, object_id: int = 1):
    """Returns where the component `object_id` of page0 of the probe `name`
    lies, as its table gives it. A probe that keeps no fixtures has no
    table, and its component takes the place of picture-two's first, the
    first component of a page."""
    probe = probe_named(name)
    if probe.fixtures is None:
        return place(probe_named("picture-two"), "page0-1")
    return place(probe, "page0-%d" % object_id)


class DrawingTest(unittest.TestCase):
    """A picture's drawing, its memory, and its pic's entry."""

    @classmethod
    def setUpClass(cls):
        cls.project = probe_facts(probe_named("picture-two"))

    def test_its_drawing(self):
        # pic, at its place, with its pic's entry: p0's first entry is 33, so
        # its pic's is 52.
        p0 = self.project.pages[0].objects[1]
        self.assertEqual(picture.drawing(p0, self.project, place_of("picture-two")),
                         [b"\x09\x01\x0410,10,\x01" + struct.pack("<I", 52)])

    def test_its_memory(self):
        # Its pic, 2 bytes, then two zeros: none is 65535.
        p0, p1 = self.project.pages[0].objects[1:3]
        self.assertEqual(picture.memory(p0, self.project), b"\x00\x00\x00\x00")
        self.assertEqual(picture.memory(p1, self.project), b"\x01\x00\x00\x00")
        none = probe_facts(probe_named("picture-of-none"))
        self.assertEqual(picture.memory(none.pages[0].objects[1], none), b"\xff\xff\x00\x00")
        # A pic past the project's pictures is written as it is, as the
        # Nextion Editor wrote it.
        past = probe_facts(probe_named("picture-of-a-number-past-the-last"))
        self.assertEqual(picture.memory(past.pages[0].objects[1], past), b"\x05\x00\x00\x00")

    def test_its_pic_s_highest_is_the_last_picture(self):
        # Entry 19, its pic's: 24 bytes, the highest value after the base and
        # the value. Two pictures give 1; none gives -1.
        p0 = self.project.pages[0].objects[1]
        entry = picture.data(p0, self.project, place_of("picture-two"))[24 * 19:24 * 20]
        self.assertEqual(struct.unpack_from("<i", entry, 8)[0], 1)
        none = probe_facts(probe_named("picture-of-none"))
        entry = picture.data(none.pages[0].objects[1], none,
                             place_of("picture-of-none"))[24 * 19:24 * 20]
        self.assertEqual(struct.unpack_from("<i", entry, 8)[0], -1)


class PiecesTest(TypePieces, CodePieces, unittest.TestCase):
    """Each picture of each probe that keeps its whole user code, at its
    type's functions, and each probe of code whose page is made in memory,
    at the statement encoder, against the probe's pieces
    (tests/tft/t_components.py)."""

    TYPE = "picture"
    PROBES = picture_probes.PROBES
    COUNT = 4
    CODE_COUNT = 1


class PPiecesTest(PTypePieces, CodePieces, unittest.TestCase):
    """Each picture of each of its probes on P that keeps its whole user
    code, at its type's functions on P, and each probe of code whose page is
    made in memory, against the probe's pieces (tests/tft/p_components.py)."""

    TYPE = "picture"
    PROBES = [probe for probe in p_probes.PROBES if probe.name.startswith("p-picture-")]
    COUNT = 4
    CODE_COUNT = 1


class MatchedTest(unittest.TestCase):
    """The needs picture.MATCHED covers (matching.py)."""

    def place(self, x: int, y: int, w: int, h: int) -> dict:
        return {name: value(number) for name, number in zip("xywh", (x, y, w, h))}

    def test_what_it_covers(self):
        covered = [Need("type", "picture"), Need("attribute", "picture.objname", b"p0"),
                   Need("attribute", "picture.pic", value(0)),
                   Need("attribute", "picture.pic", (65535).to_bytes(2, "little")),
                   Need("attribute", "picture.x", value(312), context=self.place(312, 476, 8, 4))]
        self.assertEqual(unmatched(covered, picture.MATCHED), [])

    def test_what_it_leaves_out(self):
        left = [Need("attribute", "picture.aph", value(64, 1))]
        self.assertEqual(unmatched(left, picture.MATCHED), left)

    def test_it_is_matched_on_k(self):
        # Its probes matched on K too (k_probes.py).
        project = probe_project(probe_named("picture-one"), series="K")
        self.assertEqual(unmatched(project_needs(project), matched_rules()), [])


class CodeTest(unittest.TestCase):
    """Code may use a picture's pic, and any other attribute it writes, which
    an aph is not."""

    @classmethod
    def setUpClass(cls):
        cls.project = probe_facts(probe_named("picture-one"))

    def test_its_pic(self):
        self.assertEqual(encode_line("p0.pic=1", CodePlace(0, "page0", "up"),
                                     CompileContext(self.project)),
                         b"\x01\x34\x00\x00\x00=1")

    def test_another_attribute_is_refused(self):
        with self.assertRaisesRegex(StatementError, "p0's aph is not encoded"):
            encode_line("p0.aph=64", CodePlace(0, "page0", "up"), CompileContext(self.project))

    def test_the_check_lets_its_pic_through(self):
        project = probe_project(probe_named("picture-pic-in-code"))
        self.assertEqual(unmatched(project_needs(project), matched_rules()), [])


class OnPTest(unittest.TestCase):
    """On P: its memory's values, after its record's head and its effect's
    values, and its pic's entry, after the page's 33."""

    def test_its_memory_and_its_pic_s_entry(self):
        # Its values after its effect's 4 bytes: its pic, the second of two
        # pictures, and two 0 bytes. Its pic's entry, its entry 19, gives the
        # place of its pic, 56 past its base, and the highest 1, the
        # project's last picture. At p-picture-two's first picture's place.
        p0 = page(picture_probes.picture_component(pic="blue", w=4, h=8), series="P",
                  pictures=("red", "blue")).objects[1]
        kept = next(probe for probe in p_probes.PROBES if probe.name == "p-picture-two")
        place_of_p0 = place(kept, "page0-1")
        project = project_of(series="P", pictures=2)
        self.assertEqual(p_values(p0, place_of_p0, project)[4:8], b"\x01\x00\x00\x00")
        self.assertEqual(struct.unpack_from("<ii", p_entries(p0, place_of_p0, project), 19 * 24 + 4),
                         (place_of_p0.base + 56, 1))

    def test_it_is_matched_on_p_and_e(self):
        for series in ("P", "E"):
            with self.subTest(series):
                self.assertEqual(unmatched([Need("type", "picture", series=series)],
                                           matched_rules()), [])


if __name__ == "__main__":
    unittest.main()
