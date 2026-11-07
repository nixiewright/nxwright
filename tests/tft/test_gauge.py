"""The gauge component (tft/component_types/gauge.py): its drawing, its
memory, its entries, what its list matched, and which of its attributes
code may use, on T and on P.

Each test gives the function it checks that function's own input: a page
object of a probe's components, a Project of the facts it reads, and its
place, from the probe's table (tests/tft/unit_inputs.py). The tests of its
pieces compare each gauge of each probe that keeps fixtures with the
probe's pieces (tests/tft/t_components.py, tests/tft/p_components.py). Its sample
of whole files is in tests/tft/test_whole_files.py.
"""
import struct
import unittest

from nxwright.tft.compile_context import CompileContext
from tools.tft.probing import gauge_probes, p_probes
from nxwright.tft.component_types import FILL, gauge
from nxwright.tft.matching import Need, matched_rules, project_needs, unmatched
from nxwright.tft.statements import CodePlace, StatementError, encode_line
from tests.tft.p_components import PTypePieces, p_memory, p_probe
from tests.tft.t_components import CodePieces, TypePieces
from tests.tft.unit_inputs import page, page_of, place, probe_facts, probe_project, project_of


def entry(number: int) -> bytes:
    return b"\x01" + struct.pack("<I", number)


def probe_named(name: str):
    return next(probe for probe in gauge_probes.PROBES if probe.name == name)


def _first_place():
    """Returns the place of a gauge that is page0's first component, from
    the table of the probe of two gauges: its first entry, 33, after the
    page's."""
    return place(probe_named("gauge-two"), "page0-1")


def first_gauge(probe_name: str, series: str = "T"):
    """Returns page0's first component of the probe `probe_name`, made on
    `series`, a Project of its facts, and its place (_first_place)."""
    made = page_of(probe_named(probe_name), series=series)
    return made.objects[1], project_of(made, series=series), _first_place()


class PiecesTest(TypePieces, CodePieces, unittest.TestCase):
    """Each gauge's memory, drawing, and entries in each probe of a gauge on
    T that keeps its user code, against the probe's pieces; and each probe
    of code, at the statement encoder."""

    TYPE = "gauge"
    PROBES = gauge_probes.PROBES
    COUNT = 9
    CODE_COUNT = 2


class PPiecesTest(PTypePieces, CodePieces, unittest.TestCase):
    """The same on P: each gauge's values in its memory after its head, and
    its entries; and each probe of code."""

    TYPE = "gauge"
    PROBES = [probe for probe in p_probes.PROBES if probe.name.startswith("p-gauge-")]
    COUNT = 11
    CODE_COUNT = 2


class GaugeTest(unittest.TestCase):
    """A gauge's drawing, memory, and entries."""

    def test_its_drawing(self):
        # As the Nextion Editor wrote it for a gauge at 10, 10, of 100 by 100,
        # its first entry 33: a fill with its bco, then its needle from the
        # middle of its area, half its height long, with the entries of its
        # val, plus 22, its wid, its pco, 27, and 28, then five zeros.
        z0, project, z0_place = first_gauge("gauge-one")
        self.assertEqual(gauge.variant(z0).drawing(z0, project, z0_place), [
            FILL + b"10,10,100,100," + entry(53),
            b"\x09\x0a\x08100/2+10,100/2+10,100/2," + entry(54) + b"+" + entry(55) + b","
            + entry(62) + b"," + entry(59) + b"," + entry(60) + b"," + entry(61)
            + b",0,0,0,0,0"])

    def test_its_drawing_on_k(self):
        # K numbers the needle's command as T does, 09 0a 08, and the fill and
        # the operands are T's.
        drawings = {}
        for series in ("T", "K"):
            z0, project, z0_place = first_gauge("gauge-one", series)
            drawings[series] = gauge.variant(z0).drawing(z0, project, z0_place)
        self.assertEqual(drawings["K"], drawings["T"])

    def test_its_needle_is_half_its_height(self):
        # 80 wide and 120 high: 120/2.
        z0, project, z0_place = first_gauge("gauge-taller-than-wide")
        self.assertTrue(gauge.variant(z0).drawing(z0, project, z0_place)[1].startswith(
            b"\x09\x0a\x0880/2+10,120/2+10,120/2,"))

    def test_its_memory(self):
        # As the Nextion Editor wrote it at its defaults but for its sta, 1.
        z0, project, _ = first_gauge("gauge-one")
        self.assertEqual(gauge.variant(z0).memory(z0, project), bytes.fromhex(
            "01 00 ff ff 00 00 00 00 ff 7f 1e 00 00 00 00 04 00 f8 18 00 02 01 07 02"))

    def test_its_entries(self):
        # Its val's entry, 21, at its base plus 4, highest 360; its wid's, 29,
        # from 1 to 20; and the needle's entries 22, 27, and 28 empty.
        z0, project, z0_place = first_gauge("gauge-one")
        data = gauge.variant(z0).data(z0, project, z0_place)
        self.assertEqual(struct.unpack_from("<Iiii", data, 24 * 21)[1:3],
                         (z0_place.base + 4, 360))
        self.assertEqual(struct.unpack_from("<Iiii", data, 24 * 29)[2:4], (20, 1))
        for number in (22, 27, 28):
            self.assertEqual(data[24 * number:24 * number + 24], bytes(24))


class LooksTest(unittest.TestCase):
    """What lies behind a gauge, as the Nextion Editor wrote it."""

    def test_a_picture_and_a_crop(self):
        # A picture's ID where its bco lies, picture 1 or 2; the picture at
        # its place, with pic, or the part of the crop's picture where it
        # lies, with xpic, in place of its fill; and entry 20 from 0 to the
        # project's last picture, 2, in slot 6 or 5 in place of slot 4.
        probe = probe_named("gauge-of-a-picture-and-a-crop")
        project = probe_facts(probe)
        z0, z1 = project.pages[0].objects[1:3]
        for page_object, object_id, sta, background, slot, first in (
                (z0, 1, 2, 1, 6, b"\x09\x01\x0410,10,"),
                (z1, 2, 0, 2, 5, b"\x09\x0a\x0410,120,100,100,10,120,")):
            one = gauge.variant(page_object)
            object_place = place(probe, "page0-%d" % object_id)
            with self.subTest(sta=sta):
                self.assertEqual(one.memory(page_object, project)[:4],
                                 bytes([sta, 0, background, 0]))
                self.assertEqual(one.drawing(page_object, project, object_place)[0],
                                 first + entry(object_place.first_entry + 20))
                self.assertEqual(struct.unpack_from(
                    "<Iiii", one.data(page_object, project, object_place), 24 * 20)[1:3],
                    (object_place.base + 2, 2))
                self.assertEqual((one.record_slots()[slot], one.record_slots().get(4)), (20, None))
                with self.assertRaises(KeyError):
                    one.attribute_place("bco")
        self.assertEqual((gauge.variant(z0).attribute_place("pic"),
                          gauge.variant(z1).attribute_place("picc")), (20, 20))


class MatchedTest(unittest.TestCase):
    """The needs gauge.MATCHED covers (matching.py)."""

    def test_what_it_covers(self):
        covered = [Need("type", "gauge"), Need("attribute", "gauge.objname", b"z0"),
                   Need("attribute", "gauge.sta", b"\x00"), Need("attribute", "gauge.sta", b"\x02"),
                   Need("attribute", "gauge.val", (360).to_bytes(2, "little")),
                   Need("attribute", "gauge.format", (360).to_bytes(2, "little")),
                   Need("attribute", "gauge.up", (32767).to_bytes(2, "little")),
                   Need("attribute", "gauge.left", (1024).to_bytes(2, "little")),
                   Need("attribute", "gauge.hig", b"\x64"),
                   Need("attribute", "gauge.wid", b"\x01"), Need("attribute", "gauge.wid", b"\x14"),
                   Need("attribute", "gauge.vvs2", b"\x80"),
                   Need("attribute", "gauge.pco2", (0).to_bytes(2, "little")),
                   Need("attribute", "gauge.pic", (1).to_bytes(2, "little"))]
        self.assertEqual(unmatched(covered, gauge.MATCHED), [])

    def test_what_it_leaves_out(self):
        # A sta of 3 on T, nothing behind it, is left out, as nxwright's build
        # refuses it on T, K, and F.
        left = [Need("attribute", "gauge.sta", b"\x03", series="T")]
        self.assertEqual(unmatched(left, gauge.MATCHED), left)

    def test_it_is_matched_on_k(self):
        # Its probes matched on K too (k_probes.py): its page made on K.
        made = page_of(probe_named("gauge-one"), series="K")
        self.assertEqual(unmatched(project_needs(project_of(made, series="K", fonts=0)),
                                   matched_rules()), [])


class CodeTest(unittest.TestCase):
    """Code may use a gauge's val, and any other attribute it writes."""

    @classmethod
    def setUpClass(cls):
        cls.project = probe_facts(probe_named("gauge-one"))

    def test_its_val(self):
        # z0's first entry is 33, and its val's entry 21 within the type.
        self.assertEqual(encode_line("z0.val=90", CodePlace(0, "page0", "up"),
                                     CompileContext(self.project)),
                         entry(54) + b"=90")

    def test_its_other_attributes(self):
        # Any attribute it writes, such as its wid, entry 29 within the type,
        # after z0's first entry, 33; but not one it does not write.
        code_place = CodePlace(0, "page0", "up")
        self.assertEqual(encode_line("z0.wid=1", code_place, CompileContext(self.project)),
                         b"\x01" + (33 + 29).to_bytes(4, "little") + b"=1")
        with self.assertRaisesRegex(StatementError, "z0's txt is not encoded"):
            encode_line("z0.txt=1", code_place, CompileContext(self.project))

    def test_the_check_lets_its_val_through(self):
        self.assertEqual(unmatched(project_needs(probe_project(probe_named("gauge-val-in-code"))),
                                   matched_rules()), [])


class PTest(unittest.TestCase):
    """On P, a gauge's memory gives its values as on T, from 56, after its
    record's head and its effect's values; its entries are its own there
    (p_probes.py)."""

    def test_its_memory(self):
        # Its sta, a zero, its bco, val, format, up, down, left, pco, and pco2,
        # its hig, a zero, then its wid, which no entry gives, and its vvs0,
        # vvs1, and vvs2.
        z0 = page(gauge_probes.gauge_component(val=45, bco=1024, pco=63488),
                  series="P").objects[1]
        memory = p_memory(z0, place(p_probe("p-gauge-two"), "page0-1"))
        self.assertEqual(memory[56:gauge._of(1).P_MEMORY_SIZE].hex(" "),
                         "01 00 00 04 2d 00 00 00 ff 7f 1e 00 00 00 00 f8 00 f8 18 00 02 01 07 02")

    def test_its_entries(self):
        # Every value in its memory has one but its wid, whose entry on T,
        # 29, is empty.
        self.assertEqual({entry: name for entry, (name, *_) in gauge._of(1).P_ENTRIES.items()
                          if entry >= 19},
                         {19: "sta", 20: "bco", 21: "val", 22: "format", 23: "up", 24: "down",
                          25: "left", 26: "pco", 27: "pco2", 28: "hig", 30: "vvs0",
                          31: "vvs1", 32: "vvs2"})

    def test_code_names_them_by_their_numbers_on_p(self):
        # Its val keeps entry 21; its wid, entry 29 on T, has none on P,
        # so code there may not name it.
        _, project, _ = first_gauge("gauge-one", "P")
        code_place = CodePlace(0, "page0", "up")
        self.assertEqual(encode_line("z0.val=90", code_place,
                                     CompileContext(project)), entry(54) + b"=90")
        with self.assertRaisesRegex(StatementError, "z0's wid is not encoded"):
            encode_line("z0.wid=1", code_place, CompileContext(project))

    def test_it_is_matched_on_p_and_e(self):
        for series in ("P", "E"):
            with self.subTest(series):
                need = Need("type", "gauge", series=series)
                self.assertEqual(unmatched([need], matched_rules()), [])

    def test_nothing_behind_it(self):
        # At its default sta of 3, it has no entry for what lies behind it,
        # and each later entry is one down, 40 in all. Its memory keeps 0
        # there, beside its sta, 3, though its bco is set.
        nothing = gauge._of(3)
        self.assertEqual(nothing.ENTRIES, 40)
        self.assertEqual({entry: name for entry, (name, *_) in nothing.P_ENTRIES.items()
                          if entry >= 19},
                         {19: "sta", 20: "val", 21: "format", 22: "up", 23: "down",
                          24: "left", 25: "pco", 26: "pco2", 27: "hig", 29: "vvs0",
                          30: "vvs1", 31: "vvs2"})
        z0 = page(gauge_probes.gauge_component(sta=3, bco=31), series="P").objects[1]
        memory = p_memory(z0, place(p_probe("p-gauge-of-nothing-behind"), "page0-1"))
        self.assertEqual(memory[56:60].hex(" "), "03 00 00 00")

    def test_its_sta_of_3_on_p_and_e_alone(self):
        # Its entry's highest on P, which nxwright's build refuses on T, K,
        # and F.
        for series, left in (("P", []), ("E", []), ("T", True), ("K", True), ("F", True)):
            with self.subTest(series):
                need = Need("attribute", "gauge.sta", b"\x03", series=series)
                self.assertEqual(unmatched([need], gauge.MATCHED), [need] if left else [])


if __name__ == "__main__":
    unittest.main()
