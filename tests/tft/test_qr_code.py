"""The QR code component (tft/component_types/qr_code.py): its drawing, its
memory, which gives where its txt lies, its entries, what its list matched,
which of its attributes code may use, and its memory and entries on P.

Each test gives the function it checks that function's own input: a page
object of a probe's components (tools/tft/probing/qr_code_probes.py), made by
nxwright's page reader, a Project of the facts it reads, and the object's
place, read from the probe's table (tests/tft/unit_inputs.py). It compares the
result with one piece of the probe's fixtures, which the probe runner wrote
once the probe matched the Nextion Editor's file. Each probe that keeps
fixtures is compared so, on T and on P (tests/tft/t_components.py,
tests/tft/p_components.py). What the frame writes across objects, such as a QR
code's record, the head of its memory on P, and its txt in its page's
texts, is left to the frame's tests, and compared until then by the sample
of whole files (tests/tft/test_whole_files.py).
"""
import struct
import unittest

from nxwright.tft.compile_context import CompileContext
from nxwright.tft.component_types import qr_code
from nxwright.tft.matching import Need, matched_rules, project_needs, unmatched
from tools.tft.probing import p_probes, qr_code_probes
from nxwright.tft.statements import CodePlace, StatementError, encode_line
from tests.tft.p_components import PTypePieces, p_values
from tests.tft.t_components import CodePieces, TypePieces
from tests.tft.unit_inputs import page, page_of, place, probe_facts, probe_project, project_of


def entry(number: int) -> bytes:
    return b"\x01" + struct.pack("<I", number)


def probe_named(name: str):
    return next(probe for probe in qr_code_probes.PROBES + p_probes.PROBES
                if probe.name == name)


class PiecesTest(TypePieces, CodePieces, unittest.TestCase):
    """Each QR code of each probe that keeps its whole user code, at its
    type's functions, and its probe of code, at the statement encoder,
    against the probe's pieces (tests/tft/t_components.py): its memory, which
    gives where its txt lies; its drawing; and its entries."""

    TYPE = "qr-code"
    PROBES = qr_code_probes.PROBES
    COUNT = 9
    CODE_COUNT = 1


class PPiecesTest(PTypePieces, CodePieces, unittest.TestCase):
    """Each QR code of each of its probes on P that keeps its whole user code,
    at its type's functions on P, against the probe's pieces: its values as
    on T, from 56, after its record's head and its effect's values, its txt
    still after its page's components' memory."""

    TYPE = "qr-code"
    PROBES = [probe for probe in p_probes.PROBES if probe.name.startswith("p-qr-code-")]
    COUNT = 9
    CODE_COUNT = 1


class QRCodeTest(unittest.TestCase):
    """A QR code's drawing, memory, and entries."""

    @classmethod
    def setUpClass(cls):
        # qr0 at its defaults, its memory from 28; qr1 after qr0's 16 bytes,
        # its txt "Hello123" and its txt_maxl 20. Their memory ends at 60, so
        # their txts lie from 64, past 4 zeros: qr0's in 32 bytes, then
        # qr1's, as the probe's table gives their places.
        cls.probe = probe_named("qr-code-two")
        cls.project = probe_facts(cls.probe)
        cls.qr0, cls.qr1 = cls.project.pages[0].objects[1:3]
        cls.place0, cls.place1 = place(cls.probe, "page0-1"), place(cls.probe, "page0-2")
        # Both without a logo, of sta 0.
        cls.without_a_logo = qr_code.variant(cls.qr0)

    def test_its_drawing(self):
        # 09 08 08, its place and width, its bco's and pco's entries, 65535,
        # then its dis's and txt's entries. qr0's first entry is 33.
        self.assertEqual(self.without_a_logo.drawing(self.qr0, self.project, self.place0),
                         [b"\x09\x08\x0810,10,100," + entry(54) + b"," + entry(55)
                          + b",\x03\xff\xff\x00\x00," + entry(53) + b"," + entry(56)])

    def test_its_drawing_on_k(self):
        # K numbers the command as T does, 09 08 08, and its operands are T's.
        made = page_of(self.probe, series="K")
        qr0 = made.objects[1]
        self.assertEqual(qr_code.variant(qr0).drawing(qr0, project_of(made, series="K"),
                                                      self.place0),
                         self.without_a_logo.drawing(self.qr0, self.project, self.place0))

    def test_its_memory_gives_where_its_txt_lies(self):
        # sta, dis, bco, pco, two zeros, txt_maxl, two zeros, then where its
        # txt lies, after the page's components' memory.
        for item, its_place, maxl in ((self.qr0, self.place0, 30), (self.qr1, self.place1, 20)):
            with self.subTest(maxl=maxl):
                self.assertEqual(self.without_a_logo.memory_at(item, self.project, its_place),
                                 struct.pack("<BBHH2xH2xI", 0, 8, 0xFFFF, 0, maxl,
                                             its_place.text_place))

    def test_its_txt_lies_after_the_components(self):
        # Its txt, padded with zeros to txt_maxl + 1 bytes, then to a
        # multiple of 4: 31 bytes to 32, and 21 to 24.
        self.assertEqual(self.without_a_logo.page_text(self.qr0, self.project),
                         b"https://nextion.itead.cc".ljust(32, b"\x00"))
        self.assertEqual(self.without_a_logo.page_text(self.qr1, self.project),
                         b"Hello123".ljust(24, b"\x00"))

    def test_its_entries(self):
        # Its txt's entry gives where its txt lies, and txt_maxl + 1 in its
        # code's second byte; its txt_maxl's gives the place of its
        # txt_maxl in memory, its base plus 8, highest 192.
        data = self.without_a_logo.data(self.qr1, self.project, self.place1)
        self.assertEqual(struct.unpack_from("<IiiiII", data, 24 * 23)[1], 96)
        self.assertEqual(struct.unpack_from("<IiiiII", data, 24 * 23)[5], 21 << 8 | 0x3F)
        self.assertEqual(struct.unpack_from("<IiiiII", data, 24 * 24)[1:3], (52, 192))

    def test_its_entries_on_f(self):
        # As on T, but its txt_maxl's highest is 368.
        made = page_of(self.probe, series="F")
        qr1 = made.objects[2]
        data = qr_code.variant(qr1).data(qr1, project_of(made, series="F"), self.place1)
        on_t = self.without_a_logo.data(self.qr1, self.project, self.place1)
        self.assertEqual(struct.unpack_from("<IiiiII", data, 24 * 24)[1:3], (52, 368))
        self.assertEqual(data[:24 * 24] + data[24 * 25:], on_t[:24 * 24] + on_t[24 * 25:])


class LogoTest(unittest.TestCase):
    """A QR code's logo, of sta 1, and its colours and margin, as the
    Nextion Editor wrote them."""

    @classmethod
    def setUpClass(cls):
        # Two QR codes with logos, qr0 of the project's second picture and
        # qr1 of its first. qr0's memory is from 28, and its txt lies at 64.
        probe = probe_named("qr-code-logos")
        cls.project = probe_facts(probe)
        cls.qr0 = cls.project.pages[0].objects[1]
        cls.place0 = place(probe, "page0-1")
        cls.with_a_logo = qr_code.variant(cls.qr0)
        # A place for the QR codes of the probes below, which keep no
        # fixtures: qr-code-two's qr0's. Their tests check the bytes of their
        # pic and its entry's highest alone, which the place does not change.
        cls.place_of_one = place(probe_named("qr-code-two"), "page0-1")

    def test_its_entries_and_slots(self):
        # 34 entries, one more than without a logo: its pic's is entry 23, at
        # its base plus 6, from 0 to the last of the project's 2 pictures,
        # and its txt's and txt_maxl's follow, 24 and 25. Its record gives
        # its pic in slot 6.
        self.assertEqual(self.with_a_logo.ENTRIES, 34)
        data = self.with_a_logo.data(self.qr0, self.project, self.place0)
        self.assertEqual(struct.unpack_from("<IiiiII", data, 24 * 23)[1:4], (34, 1, 0))
        self.assertEqual(struct.unpack_from("<IiiiII", data, 24 * 24)[1], 64)
        slots = self.with_a_logo.record_slots()
        self.assertEqual((slots[6], slots[28], slots[29]), (23, 24, 25))

    def test_its_drawing(self):
        # Its pic's entry, 56, where one without a logo gives 65535.
        self.assertEqual(self.with_a_logo.drawing(self.qr0, self.project, self.place0),
                         [b"\x09\x08\x0810,10,100," + entry(54) + b"," + entry(55) + b","
                          + entry(56) + b"," + entry(53) + b"," + entry(57)])

    def test_its_memory(self):
        # Its sta 1, dis 8, bco 65535, pco 0, its pic 1, then its txt_maxl,
        # two zeros, and where its txt lies.
        self.assertEqual(self.with_a_logo.memory_at(self.qr0, self.project, self.place0),
                         bytes.fromhex("01 08 ff ff 00 00 01 00 1e 00 00 00 40 00 00 00"))

    def test_a_pic_without_a_logo(self):
        # Of sta 0, its pic is not kept, and it has 33 entries.
        project = probe_facts(probe_named("qr-code-pic-without-a-logo"))
        qr0 = project.pages[0].objects[1]
        without_a_logo = qr_code.variant(qr0)
        self.assertEqual(without_a_logo.ENTRIES, 33)
        self.assertEqual(without_a_logo.memory_at(qr0, project, self.place_of_one)[6:8],
                         bytes(2))

    def test_a_logo_without_a_picture(self):
        # Its pic stays 65535, and its pic's entry gives -1 as its highest,
        # the project having no picture.
        project = probe_facts(probe_named("qr-code-logo-without-a-picture"))
        qr0 = project.pages[0].objects[1]
        with_a_logo = qr_code.variant(qr0)
        self.assertEqual(with_a_logo.memory_at(qr0, project, self.place_of_one)[6:8],
                         b"\xff\xff")
        data = with_a_logo.data(qr0, project, self.place_of_one)
        self.assertEqual(struct.unpack_from("<IiiiII", data, 24 * 23)[2], -1)

    def test_its_colours_and_margin(self):
        # A bco of 31, a pco of 2016, and a dis of 20, each in its place.
        probe = probe_named("qr-code-colours-and-margin")
        project = probe_facts(probe)
        qr0 = project.pages[0].objects[1]
        self.assertEqual(qr_code.variant(qr0).memory_at(qr0, project, place(probe, "page0-1")),
                         bytes.fromhex("00 14 1f 00 e0 07 00 00 1e 00 00 00 50 00 00 00"))


class MatchedTest(unittest.TestCase):
    """The needs qr_code.MATCHED covers (matching.py)."""

    def test_what_it_covers(self):
        covered = [Need("type", "qr-code"), Need("attribute", "qr-code.objname", b"qr0"),
                   Need("attribute", "qr-code.txt", b"Hello123",
                        context={"txt_maxl": (20).to_bytes(2, "little")}),
                   Need("attribute", "qr-code.txt_maxl", (154).to_bytes(2, "little"),
                        context={"txt": b"Yo"}),
                   Need("attribute", "qr-code.sta", b"\x01"),
                   Need("attribute", "qr-code.dis", b"\xff"),
                   Need("attribute", "qr-code.bco", (31).to_bytes(2, "little")),
                   Need("attribute", "qr-code.pco", (0xFFFF).to_bytes(2, "little")),
                   Need("attribute", "qr-code.pic", (1).to_bytes(2, "little"))]
        self.assertEqual(unmatched(covered, qr_code.MATCHED), [])

    def test_its_txt_maxl_to_its_entry_s_highest(self):
        # 192 on T and K, 368 on F, and 630 on P and E. A page's memory holds
        # less on NX4832T035, which nxwright's build refuses.
        covered = [Need("attribute", "qr-code.txt_maxl", maxl.to_bytes(2, "little"),
                        context={"txt": b"Yo"}, series=series)
                   for series, maxl in (("T", 192), ("K", 192), ("F", 368), ("P", 630),
                                        ("E", 630))]
        self.assertEqual(unmatched(covered, qr_code.MATCHED), [])

    def test_what_it_leaves_out(self):
        # A txt past its txt_maxl, and a sta past 1, are left out.
        left = [Need("attribute", "qr-code.txt", b"http:\x85",
                     context={"txt_maxl": (5).to_bytes(2, "little")}),
                Need("attribute", "qr-code.sta", b"\x02")]
        self.assertEqual(unmatched(left, qr_code.MATCHED), left)

    def test_it_is_matched_on_k(self):
        # Its probes matched on K too (k_probes.py): the needs of a page of a
        # QR code on K.
        project = project_of(page(qr_code_probes.qr_code_component(), series="K"), series="K",
                             fonts=0)
        self.assertEqual(unmatched(project_needs(project), matched_rules()), [])


class CodeTest(unittest.TestCase):
    """Code may use a QR code's txt, and any other attribute it writes. The
    encoder reads the page's components."""

    @classmethod
    def setUpClass(cls):
        cls.project = project_of(page_of(probe_named("qr-code-one")))

    def test_its_txt(self):
        # qr0's first entry is 33, and its txt's entry 23 within the type.
        self.assertEqual(encode_line('qr0.txt="Hi"', CodePlace(0, "page0", "up"),
                                     CompileContext(self.project)),
                         entry(56) + b'="Hi"')

    def test_its_other_attributes(self):
        # Any attribute it writes, such as its dis, entry 20 within the type,
        # after qr0's first entry, 33; but not one it does not write.
        place_of_line = CodePlace(0, "page0", "up")
        self.assertEqual(encode_line("qr0.dis=1", place_of_line, CompileContext(self.project)),
                         b"\x01" + (33 + 20).to_bytes(4, "little") + b"=1")
        with self.assertRaisesRegex(StatementError, "qr0's val is not encoded"):
            encode_line("qr0.val=1", place_of_line, CompileContext(self.project))

    def test_the_check_lets_its_txt_through(self):
        # The needs of qr-code-txt-in-code's page, its txt in code.
        self.assertEqual(unmatched(project_needs(probe_project(probe_named(
            "qr-code-txt-in-code"))), matched_rules()), [])


class PTest(unittest.TestCase):
    """On P, a QR code's memory gives its values as on T, from 56, after its
    record's head and its effect's values, its txt still after its page's
    components' memory (p_probes.py)."""

    def test_its_values(self):
        # Its sta, dis, bco, and pco, two zeros without a logo, and its
        # txt_maxl, then two zeros, at a txt_maxl, dis, bco, and pco of no
        # probe's; the place of its txt, which follows, is the frame's. Its
        # place is p-qr-code-two's qr0's.
        made = page(qr_code_probes.qr_code_component(txt="abc", txt_maxl=20, dis=4, bco=1024,
                                                     pco=63488), series="P").objects[1]
        values = p_values(made, place(probe_named("p-qr-code-two"), "page0-1"))
        self.assertEqual(values[56 - 52:68 - 52].hex(" "), "00 04 00 04 00 f8 00 00 14 00 00 00")

    def test_its_entries_with_and_without_a_logo(self):
        # As on T: a logo adds its pic's entry, 23, and moves its txt's and
        # txt_maxl's one on.
        names = {variant.logo: {entry: name for entry, (name, *_) in variant.P_ENTRIES.items()
                                if entry >= 19}
                 for variant in (qr_code._WITHOUT_A_LOGO, qr_code._WITH_A_LOGO)}
        self.assertEqual(names[False], {19: "sta", 20: "dis", 21: "bco", 22: "pco", 23: "txt",
                                        24: "txt_maxl"})
        self.assertEqual(names[True], {19: "sta", 20: "dis", 21: "bco", 22: "pco", 23: "pic",
                                       24: "txt", 25: "txt_maxl"})

    def test_it_is_matched_on_p_and_e(self):
        for series in ("P", "E"):
            with self.subTest(series):
                need = Need("type", "qr-code", series=series)
                self.assertEqual(unmatched([need], matched_rules()), [])


if __name__ == "__main__":
    unittest.main()
