"""The xfloat component (tft/component_types/xfloat.py): its drawing, its
memory, its entries, its record's slots, what its list matched, which of
its attributes code may use, and its memory and entries on P.

Each test gives the function it checks that function's own input: a page
object of a probe's components (tools/tft/probing/xfloat_probes.py), made by
nxwright's page reader, a Project of the facts it reads, and the object's
place, read from the probe's table (tests/tft/unit_inputs.py). It compares the
result with one piece of the probe's fixtures, which the probe runner wrote
once the probe matched the Nextion Editor's file. Each probe that keeps
fixtures is compared so, on T and on P (tests/tft/t_components.py,
tests/tft/p_components.py). What the frame writes across objects, such as an
xfloat's record and the head of its memory on P, is left to the frame's
tests, and compared until then by the sample of whole files
(tests/tft/test_whole_files.py), as is its font in a second font, which a page
made in memory cannot hold.
"""
from dataclasses import replace
import struct
import unittest

from nxwright.tft.compile_context import CompileContext
from nxwright.tft.component_types import number, xfloat
from nxwright.tft.matching import Need, matched_rules, project_needs, unmatched
from tools.tft.probing import p_probes, xfloat_probes
from nxwright.tft.statements import CodePlace, StatementError, encode_line
from tests.tft.p_components import PTypePieces
from tests.tft.t_components import CodePieces, TypePieces
from tests.tft.unit_inputs import page, page_of, place, probe_facts, probe_project, project_of


def entry(number_: int) -> bytes:
    return b"\x01" + struct.pack("<I", number_)


def probe_named(name: str):
    return next(probe for probe in xfloat_probes.PROBES if probe.name == name)


class PiecesTest(TypePieces, CodePieces, unittest.TestCase):
    """Each xfloat of each probe that keeps its whole user code, at its type's
    functions, and each probe of code, at the statement encoder, against the
    probe's pieces (tests/tft/t_components.py): its memory, a number's with its
    vvs0 and vvs1 in bytes 16 and 17; its drawing; and its entries."""

    TYPE = "xfloat"
    PROBES = xfloat_probes.PROBES
    COUNT = 15
    CODE_COUNT = 2


class PPiecesTest(PTypePieces, CodePieces, unittest.TestCase):
    """Each xfloat of each of its probes on P that keeps its whole user code,
    at its type's functions on P, against the probe's pieces: written as a
    number is there, its vvs0 and vvs1 in the places of a number's lenth and
    format."""

    TYPE = "xfloat"
    PROBES = [probe for probe in p_probes.PROBES if probe.name.startswith("p-xfloat-")]
    COUNT = 16
    CODE_COUNT = 2


class AsANumberTest(unittest.TestCase):
    """An xfloat's drawing, entries, and record: a number's, but for its vvs0
    and vvs1, on x1 of xfloat-two, at 10, 60, its val 1234, its vvs0 and
    vvs1 2."""

    @classmethod
    def setUpClass(cls):
        cls.probe = probe_named("xfloat-two")
        cls.project = probe_facts(cls.probe)
        cls.x1 = cls.project.pages[0].objects[2]
        cls.place = place(cls.probe, "page0-2")

    def test_its_drawing(self):
        # A number's setbrush, then 09 10 04 and the entries of its val,
        # vvs0, and vvs1, after x1's first entry, 74.
        self.assertEqual(xfloat.variant(self.x1).drawing(self.x1, self.project, self.place),
                         [number.variant(self.x1).look(self.x1, self.project, self.place),
                          b"\x09\x10\x04" + entry(101) + b"," + entry(102) + b"," + entry(103)])

    def test_its_drawing_on_k_and_f(self):
        # K numbers the command that draws an xfloat's val 0x12 in table 4,
        # and F 0x14, where T has 0x10. Its operands are T's.
        for series, command in (("K", 0x12), ("F", 0x14)):
            with self.subTest(series):
                made = page_of(self.probe, series=series)
                x1 = made.objects[2]
                self.assertEqual(
                    xfloat.variant(x1).drawing(x1, project_of(made, series=series),
                                               self.place)[1],
                    bytes([0x09, command, 0x04]) + entry(101) + b"," + entry(102) + b","
                    + entry(103))

    def test_its_entries(self):
        # A number's, but entries 28 and 29, its vvs0 and vvs1, at its base
        # plus 16 and 17, with the highest values 10 and 8.
        one = xfloat.variant(self.x1)
        ours = one.data(self.x1, self.project, self.place)
        theirs = number.variant(self.x1).data(self.x1, self.project, self.place)
        for at in range(one.ENTRIES):
            with self.subTest(entry=at):
                if at in (28, 29):
                    self.assertEqual(struct.unpack_from("<Iii", ours, 24 * at)[1:],
                                     ({28: (self.place.base + 16, 10),
                                       29: (self.place.base + 17, 8)}[at]))
                else:
                    self.assertEqual(ours[24 * at:24 * at + 24], theirs[24 * at:24 * at + 24])

    def test_its_record(self):
        # A number's slots, but slots 50 and 51 give its vvs0 and vvs1, where
        # a number's 41 and 64 give its lenth and format.
        slots = number.variant(self.x1).record_slots()
        del slots[41], slots[64]
        slots.update({50: 28, 51: 29})
        self.assertEqual(xfloat.variant(self.x1).record_slots(), slots)


class VariantTest(unittest.TestCase):
    """An xfloat with a border, and with a picture behind it, as the Nextion
    Editor wrote them: a number's variant (number.variant), with its vvs0
    and vvs1 in the places of the number's lenth and format, wherever those
    move."""

    @classmethod
    def setUpClass(cls):
        styles, pictures = probe_named("xfloat-of-each-style"), probe_named(
            "xfloat-of-a-picture-and-a-crop")
        cls.styles = probe_facts(styles)
        cls.bordered = cls.styles.pages[0].objects[1]
        cls.picture = probe_facts(pictures).pages[0].objects[1]
        cls.place = place(styles, "page0-1")

    def test_its_entries_and_slots(self):
        # Its val, vvs0, and vvs1 are 29 to 31 at a style of 1, two on, and
        # 26 to 28 behind a picture, one back; their slots, 20, 50, and 51,
        # follow them.
        for page_object, entries in ((self.bordered, [29, 30, 31]),
                                     (self.picture, [26, 27, 28])):
            one = xfloat.variant(page_object)
            with self.subTest(entries):
                self.assertEqual([one.attribute_place(name) for name in ("val", "vvs0", "vvs1")],
                                 entries)
                slots = one.record_slots()
                self.assertEqual([slots[slot] for slot in (20, 50, 51)], entries)
                self.assertNotIn(41, slots)
                with self.assertRaises(KeyError):
                    one.attribute_place("lenth")

    def test_its_drawing(self):
        # The number's setbrush, the command that draws its val with the
        # entries of its val, vvs0, and vvs1, then the number's border, at a
        # style of 1.
        drawing = xfloat.variant(self.bordered).drawing(self.bordered, self.styles, self.place)
        as_number = number.variant(self.bordered)
        first = self.place.first_entry
        self.assertEqual(drawing[0], as_number.look(self.bordered, self.styles, self.place))
        self.assertEqual(drawing[1], b"\x09\x10\x04" + entry(first + 29) + b","
                         + entry(first + 30) + b"," + entry(first + 31))
        self.assertEqual(drawing[2:],
                         as_number.border_blocks(self.bordered, self.styles, self.place))


class MatchedTest(unittest.TestCase):
    """The needs xfloat.MATCHED covers (matching.py)."""

    def test_what_it_covers(self):
        covered = [Need("type", "xfloat"), Need("attribute", "xfloat.objname", b"x0"),
                   Need("attribute", "xfloat.val", (-2147483648).to_bytes(4, "little",
                                                                         signed=True)),
                   Need("attribute", "xfloat.vvs0", b"\x0a"),
                   Need("attribute", "xfloat.vvs1", b"\x08"),
                   Need("attribute", "xfloat.font", b"\x01")]
        # The values its memory alone gives, as a number's, at their ends.
        for name, ends in (("bco", (0, 0xFFFF)), ("pco", (0, 0xFFFF)), ("xcen", (0, 2)),
                           ("ycen", (0, 2)), ("isbr", (0, 1)), ("spax", (0, 255)),
                           ("spay", (0, 255))):
            covered += [Need("attribute", "xfloat." + name, end.to_bytes(2, "little"))
                        for end in ends]
        # What lies behind it, its border, and its pictures, as a number's,
        # on T and K: each style at each sta.
        looks = [Need("attribute", "xfloat.sta", bytes([sta])) for sta in (0, 2)]
        looks += [Need("attribute", "xfloat.style", bytes([style])) for style in (1, 2, 3)]
        looks += [Need("attribute", "xfloat.style", bytes([style]), context={"sta": bytes([sta])})
                  for sta in (0, 2) for style in (0, 1, 2, 3)]
        looks += [Need("attribute", "xfloat." + name, end.to_bytes(2, "little"))
                  for name, ends in (("borderc", (0, 0xFFFF)), ("borderw", (0, 255)),
                                     ("pic", (0, 0xFFFF)), ("picc", (0, 0xFFFF)))
                  for end in ends]
        covered += looks + [replace(need, series="K") for need in looks]
        self.assertEqual(unmatched(covered, xfloat.MATCHED), [])

    def test_what_it_leaves_out(self):
        left = [Need("attribute", "xfloat.spax", (256).to_bytes(2, "little")),
                Need("attribute", "xfloat.spay", (256).to_bytes(2, "little"))]
        # Past what the probes showed: a sta past 2, a style past 3, and a
        # keyboard, which no case tried.
        left += [Need("attribute", "xfloat." + name, value) for name, value in (
            ("sta", b"\x03"), ("style", b"\x04"), ("borderw", (256).to_bytes(2, "little")),
            ("key", b"\x01"))]
        self.assertEqual(unmatched(left, xfloat.MATCHED), left)

    def test_it_is_matched_on_k(self):
        # Its probes matched on K too (k_probes.py): the needs of a page of an
        # xfloat on K.
        project = project_of(page(xfloat_probes.xfloat_component(), series="K"), series="K",
                             fonts=0)
        self.assertEqual(unmatched(project_needs(project), matched_rules()), [])


class CodeTest(unittest.TestCase):
    """Code may use an xfloat's val, and any other attribute it writes. The
    encoder reads the page's components."""

    @classmethod
    def setUpClass(cls):
        cls.project = project_of(page_of(probe_named("xfloat-one")))

    def test_its_val(self):
        # x0's first entry is 33, and its val's entry 27 within the type.
        self.assertEqual(encode_line("x0.val=5", CodePlace(0, "page0", "up"),
                                     CompileContext(self.project)),
                         entry(60) + b"=5")

    def test_its_other_attributes(self):
        # Its vvs0, entry 28 within the type, and a number's, such as its bco,
        # entry 23, after x0's first entry, 33; but not a number's lenth,
        # whose entry is its vvs0's.
        place_of_line = CodePlace(0, "page0", "up")
        for attribute, entry in (("vvs0", 28), ("bco", 23)):
            with self.subTest(attribute=attribute):
                self.assertEqual(encode_line("x0.%s=1" % attribute, place_of_line,
                                             CompileContext(self.project)),
                                 b"\x01" + (33 + entry).to_bytes(4, "little") + b"=1")
        with self.assertRaisesRegex(StatementError, "x0's lenth is not encoded"):
            encode_line("x0.lenth=1", place_of_line, CompileContext(self.project))

    def test_the_check_lets_its_val_through(self):
        # The needs of xfloat-val-in-code's page, its val in code.
        self.assertEqual(unmatched(project_needs(probe_project(probe_named(
            "xfloat-val-in-code"))), matched_rules()), [])


class PTest(unittest.TestCase):
    """On P, an xfloat is written as a number is there, its vvs0 and vvs1 in
    the places of a number's lenth and format (p_probes.py)."""

    def test_its_entries(self):
        # A number's, but its vvs0 and vvs1, 28 and 29, with their own
        # highest values.
        made = page(xfloat_probes.xfloat_component(), series="P").objects[1]
        one, as_number = xfloat.variant(made), number.variant(made)
        self.assertEqual({entry: one.P_ENTRIES[entry] for entry in (28, 29)},
                         {28: ("vvs0", 72, 10, 0, 0x131), 29: ("vvs1", 73, 8, 0, 0x131)})
        self.assertEqual({entry: value for entry, value in one.P_ENTRIES.items()
                          if entry not in (28, 29)},
                         {entry: value for entry, value in as_number.P_ENTRIES.items()
                          if entry not in (28, 29)})
        self.assertEqual((one.P_MEMORY_SIZE, one.P_LAST_RESOURCE),
                         (as_number.P_MEMORY_SIZE, as_number.P_LAST_RESOURCE))

    def test_it_is_matched_on_p_and_e_with_its_border(self):
        # Its border and what lies behind it too, as a number's.
        for series in ("P", "E"):
            with self.subTest(series):
                need = Need("type", "xfloat", series=series)
                self.assertEqual(unmatched([need], matched_rules()), [])
                style = Need("attribute", "xfloat.style", b"\x01", series=series)
                self.assertEqual(unmatched([style], matched_rules()), [])


if __name__ == "__main__":
    unittest.main()
