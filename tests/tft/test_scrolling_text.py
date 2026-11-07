"""The scrolling text component (tft/component_types/scrolling_text.py):
its drawing and its code in its page's load section; the numbers of the "S "
blocks it shares with timers (label_numbers.numbers); its memory,
its entries, its txt in its page's texts, and its record's slots; what its
list matched; its attributes in code; and its memory, entries, and load
section on P.

Each test gives the function it checks that function's own input: a page
object of a probe's components (tools/tft/probing/scrolling_text_probes.py),
made by nxwright's page reader, a Project of the facts it reads, and the
object's place, read from the probe's table (tests/tft/unit_inputs.py), where
its txt and its code in the load section lie among them. It compares the
result with one piece of the probe's fixtures, which the probe runner wrote
once the probe matched the Nextion Editor's file. Each probe that keeps
fixtures is compared so, on T and on P (tests/tft/t_components.py,
tests/tft/p_components.py). What the frame writes across objects, such as a
scrolling text's record, the head of its memory on P, and its txt among
its page's texts on P, is left to the frame's tests, and compared until then by the
sample of whole files (tests/tft/test_whole_files.py), as is the check of its
probe in a second font, which a page made in memory cannot hold.
"""
import struct
import unittest

from nxwright.tft.compile_context import CompileContext
from nxwright.tft.component_types import scrolling_text
from nxwright.tft.label_numbers import numbers
from nxwright.tft.matching import Need, matched_rules, project_needs, unmatched
from tools.tft.probing import p_probes, scrolling_text_probes
from nxwright.tft.statements import CodePlace, encode_line
from tools.tft.probing.text_probes import text_component
from tests.tft.line_context import line_context
from tests.tft.p_components import PTypePieces
from tests.tft.t_components import CodePieces, LoadSectionPieces, TypePieces, made_in_memory
from tests.tft.unit_inputs import page, page_of, place, probe_facts, probe_project, project_of


def probe_named(name: str):
    return next(probe for probe in scrolling_text_probes.PROBES if probe.name == name)


def entry(number: int) -> bytes:
    return b"\x01" + struct.pack("<I", number)


class PiecesTest(TypePieces, CodePieces, LoadSectionPieces, unittest.TestCase):
    """Each scrolling text of each probe that keeps its whole user code, at its
    type's functions, and each probe of code, at the statement encoder,
    against the probe's pieces (tests/tft/t_components.py): its memory, which
    gives where its txt lies; its drawing, setbrush, zstr, timerset, and the
    "L " block into its timer's code; its entries; and its code in the load
    section."""

    TYPE = "scrolling-text"
    PROBES = scrolling_text_probes.PROBES
    COUNT = 18
    CODE_COUNT = 2


class PPiecesTest(PTypePieces, CodePieces, LoadSectionPieces, unittest.TestCase):
    """Each scrolling text of each of its probes on P that keeps its whole user
    code, at its type's functions on P, against the probe's pieces: from 56,
    its sta, style, borderc, borderw, font, bco, pco, xcen, ycen, dir, dis,
    tim, en, a zero, and txt_maxl, then the place of its txt; its entries;
    and its load section's block, `init` and its ID."""

    TYPE = "scrolling-text"
    PROBES = [probe for probe in p_probes.PROBES if probe.name.startswith("p-scrolling-text-")]
    COUNT = 19
    CODE_COUNT = 2


class AttributesTest(unittest.TestCase):
    """A scrolling text's memory at attributes no probe of its pieces sets,
    and its txt in its page's texts, on pages made in memory, each the base
    folder's page0 with one scrolling text. Its place is the one
    scrolling-text-one's table gives, as its page is of one scrolling text
    too."""

    @classmethod
    def setUpClass(cls):
        cls.place = place(probe_named("scrolling-text-one"), "page0-1")

    def test_its_memory_with_a_border_behind_a_picture(self):
        # A style of 1 behind a picture: its sta 2, its style 0, as it draws
        # no border there, then its borderc, 63488, and borderw, 3, all the
        # same.
        made = page(scrolling_text_probes.scrolling_text_component(
            sta=2, style=1, borderc=63488, borderw=3))
        g0 = made.objects[1]
        self.assertEqual(scrolling_text.variant(g0).memory_at(g0, project_of(made),
                                                              self.place)[:5],
                         bytes.fromhex("02 00 00 f8 03"))

    def test_its_memory_with_its_attributes(self):
        # Each attribute in the place where the Nextion Editor wrote it, in
        # the probes of these attributes: bco 0, pco 63488, xcen 0, ycen 2,
        # dir 2, dis 50, tim 80, en 0, isbr 1, spax and spay 255, and vvs0
        # to vvs3 5, 6, 7, and 32767.
        made = page(scrolling_text_probes.scrolling_text_component(
            bco=0, pco=63488, xcen=0, ycen=2, dir=2, dis=50, tim=80, en=0, isbr=1,
            spax=255, spay=255, vvs0=5, vvs1=6, vvs2=7, vvs3=32767))
        g0 = made.objects[1]
        self.assertEqual(scrolling_text.variant(g0).memory_at(g0, project_of(made), self.place),
                         bytes.fromhex("01 00 00 00 00 00 00 00 00 f8 00 02 02 32 50 00 00 00 0a"
                                       " 00 44 00 00 00 01 ff ff 00 05 00 06 00 07 00 ff 7f"))

    def test_its_page_text(self):
        # Its txt, "newtxt", padded with zeros to txt_maxl + 1 bytes, 11,
        # then to a multiple of 4.
        made = page(scrolling_text_probes.scrolling_text_component())
        g0 = made.objects[1]
        self.assertEqual(scrolling_text.variant(g0).page_text(g0, project_of(made)),
                         b"newtxt" + bytes(6))


class ScrollingTextTest(unittest.TestCase):
    """A scrolling text's record's slots, and its blocks on K, on g0 of
    scrolling-text-two, page0's first component."""

    @classmethod
    def setUpClass(cls):
        probe = probe_named("scrolling-text-two")
        cls.probe = probe
        cls.project = probe_facts(probe)
        cls.g0 = cls.project.pages[0].objects[1]
        cls.place = place(probe, "page0-1")
        cls.one = scrolling_text.variant(cls.g0)

    def test_its_record_slots(self):
        # The scrolling's four entries are in slots 50 to 53.
        slots = self.one.record_slots()
        self.assertEqual(len(slots), 29)
        self.assertEqual([slots[slot] for slot in (50, 51, 52, 53)], [36, 37, 38, 39])

    def test_on_k(self):
        # K numbers setbrush 0x1D, zstr 0x15, timerset 0x23, and the
        # measuring command 0x13, and writes the rest as T does.
        made = page_of(self.probe, series="K")
        project = project_of(made, series="K")
        g0 = made.objects[1]
        setbrush, drawn, timerset, _ = self.one.drawing(g0, project, self.place)
        self.assertEqual((setbrush[:3], drawn[:3], timerset[:3]),
                         (b"\x09\x1d\x08", b"\x09\x15\x04", b"\x09\x23\x08"))
        blocks = self.one.load_start(g0, project, self.place, {})
        self.assertEqual(blocks[1][:3], b"\x09\x13\x08")


class TimerNumbersTest(unittest.TestCase):
    """The numbers of the "S " blocks of a page's timers and scrolling texts,
    as the Nextion Editor numbered them in the probes."""

    def numbers(self, probe_name: str) -> dict:
        project = probe_facts(probe_named(probe_name))
        timers = numbers(project).timers
        found = {}
        for page_number, made in enumerate(project.pages):
            for object_id, page_object in enumerate(made.objects[1:], start=1):
                name = page_object.attribute("objname").decode("ascii")
                if name.startswith(("tm", "g")):
                    found[name, page_number] = timers[page_number, object_id]
        return found

    def test_between_timers(self):
        # tm0, g0, tm1, and g1: first 1, 3, 1, and 3 numbers, then 1 each.
        # tm0's timer event is 8 and tm1's 10; g0's code is 2 to 3 and g1's
        # 6 to 7.
        self.assertEqual(self.numbers("scrolling-text-between-timers"),
                         {("tm0", 0): (0, 8), ("g0", 0): (1, 9), ("tm1", 0): (4, 10),
                          ("g1", 0): (5, 11)})

    def test_on_two_pages(self):
        # The second page's numbers start where the first's end: a timer
        # takes 2 in all, a scrolling text 4.
        self.assertEqual(self.numbers("scrolling-text-after-a-timer-on-another-page"),
                         {("tm0", 0): (0, 1), ("g0", 1): (2, 5)})
        self.assertEqual(self.numbers("scrolling-text-before-a-timer-on-another-page"),
                         {("g0", 0): (0, 3), ("tm0", 1): (4, 5)})


class VariantTest(unittest.TestCase):
    """A scrolling text of each style, and with a picture or a crop behind
    it, as the Nextion Editor wrote them, on the probes' pages made in
    memory, each one's place read from its probe's table."""

    @classmethod
    def setUpClass(cls):
        cls.styles_probe = probe_named("scrolling-text-of-each-style")
        cls.styles = probe_facts(cls.styles_probe)
        cls.pictures = probe_facts(probe_named("scrolling-text-of-a-picture-and-a-crop"))

    def test_its_entries_and_slots(self):
        # A style of 1 gives its borderc and borderw entries 22 and 23, so
        # its font is 24 and its tim 31, two on; 50 entries. A picture or a
        # crop behind it gives its style none, so its font is 21, its pic or
        # picc 22, and its tim 28, one back; 47 entries.
        bordered, sunken = (scrolling_text.variant(page_object)
                            for page_object in self.styles.pages[0].objects[1:3])
        picture, crop = (scrolling_text.variant(page_object)
                         for page_object in self.pictures.pages[0].objects[1:3])
        self.assertEqual([one.ENTRIES for one in (bordered, sunken, picture, crop)],
                         [50, 48, 47, 47])
        self.assertEqual([bordered.attribute_place(name)
                          for name in ("style", "borderc", "borderw", "font", "bco", "tim")],
                         [20, 22, 23, 24, 25, 31])
        self.assertEqual([picture.attribute_place(name) for name in ("font", "pic", "tim")],
                         [21, 22, 28])
        self.assertEqual(crop.attribute_place("picc"), 22)
        for one, name in ((picture, "style"), (picture, "bco"), (sunken, "borderc")):
            with self.subTest(name), self.assertRaises(KeyError):
                one.attribute_place(name)
        slots = bordered.record_slots()
        self.assertEqual([slots[slot] for slot in (4, 59, 60, 61)], [25, 20, 22, 23])
        slots = picture.record_slots()
        self.assertEqual((slots[6], slots.get(4), slots.get(59)), (22, None, None))
        self.assertEqual(crop.record_slots()[5], 22)

    def test_its_border(self):
        # Its setbrush ends with its border's width: its borderw, 3, at a
        # style of 1, 1 at 2 and 3, and 0 at 0. Its border's block follows
        # its zstr: of its borderc's entry, 22, twice and its borderw's, 23,
        # at 1; 3D, dark then light at 2, and light then dark at 3; none at 0,
        # where its timerset follows.
        blocks = []
        for object_id, page_object in enumerate(self.styles.pages[0].objects[1:5], 1):
            its_place = place(self.styles_probe, "page0-%d" % object_id)
            blocks.append(scrolling_text.variant(page_object).drawing(page_object, self.styles,
                                                                      its_place))
        self.assertEqual([drawing[0][-4:] for drawing in blocks],
                         [b",0,3", b",0,1", b",0,1", b",0,0"])
        self.assertEqual(blocks[0][2], b"\x09\x07\x0810,10,240,30," + entry(55) + b","
                         + entry(55) + b"," + entry(56))
        self.assertEqual(blocks[1][2], b"\x09\x07\x0810,50,240,30,"
                         b"\x03\x28\x42\x00\x00,\x03\x1c\xe7\x00\x00,1")
        self.assertEqual(blocks[2][2], b"\x09\x07\x0810,90,240,30,"
                         b"\x03\x1c\xe7\x00\x00,\x03\x28\x42\x00\x00,1")
        self.assertEqual(blocks[3][2][:3], b"\x09\x22\x08")


class MatchedTest(unittest.TestCase):

    def test_what_it_covers(self):
        # Each probe's pages are matched, made in memory; the probe of a
        # second font, which a page made in memory cannot hold, is checked
        # in tests/tft/test_whole_files.py.
        probes = [probe for probe in scrolling_text_probes.PROBES if made_in_memory(probe)]
        self.assertEqual(len(probes), len(scrolling_text_probes.PROBES) - 1)
        for probe in probes:
            with self.subTest(probe=probe.name):
                self.assertEqual(unmatched(project_needs(probe_project(probe)), matched_rules()),
                                 [])

    def test_its_attributes_within_what_the_probes_showed(self):
        rules = scrolling_text.MATCHED
        covered = [Need("attribute", "scrolling-text." + name, value)
                   for name, value in (("dir", b"\x00"), ("dir", b"\x03"), ("dis", b"\x02"),
                                       ("dis", b"\x32"), ("tim", b"\x50\x00"),
                                       ("tim", b"\xfe\xff"), ("en", b"\x00"), ("bco", b"\x00\x00"),
                                       ("pco", b"\x00\xf8"), ("xcen", b"\x00"), ("ycen", b"\x02"),
                                       ("isbr", b"\x01"), ("spax", b"\xff"), ("spay", b"\xff"),
                                       ("vvs0", b"\x05\x00"), ("vvs3", b"\xff\x7f"),
                                       ("sta", b"\x00"), ("sta", b"\x02"), ("font", b"\x01"),
                                       ("style", b"\x03"), ("borderc", b"\xff\xff"),
                                       ("borderw", b"\x00"), ("borderw", b"\xff"),
                                       ("pic", b"\x01\x00"))]
        self.assertEqual(unmatched(covered, rules), [])

    def test_what_it_leaves_out(self):
        # Values nxwright's build refuses: a sta past 2 on T and past 3 on P,
        # and a style past 3.
        rules = scrolling_text.MATCHED
        left = [Need("attribute", "scrolling-text." + name, value)
                for name, value in (("sta", b"\x03"), ("style", b"\x04"))]
        left.append(Need("attribute", "scrolling-text.sta", b"\x04", series="P"))
        self.assertEqual(unmatched(left, rules), left)


class CodeTest(unittest.TestCase):
    """Code may read and set a scrolling text's txt, tim, and en, and its other
    attributes."""

    def test_its_attributes_in_code(self):
        project = probe_facts(probe_named("scrolling-text-txt-tim-and-en-in-code"))
        place_of_line = CodePlace(0, "page0", "up")
        # g0, after t0, has its entries from 74: txt at 105, tim at 103, en
        # at 104.
        self.assertEqual(encode_line("sys1=g0.tim", place_of_line, CompileContext(project)),
                         b"\x05\x04\x00\x00\x00=" + entry(103))
        self.assertEqual(encode_line("g0.en=0", place_of_line,
                                     CompileContext(project)), entry(104) + b"=0")
        self.assertEqual(encode_line('g0.txt="hi"', place_of_line, CompileContext(project)),
                         entry(105) + b'="hi"')

    def test_other_attributes(self):
        # The check takes any other attribute it writes, read or set; but not
        # one set that code cannot change, on every series or on T, nor one
        # it does not write.
        page = line_context(text_component(), scrolling_text_probes.scrolling_text_component(y=50))
        rules = matched_rules()
        for line in ("sys0=g0.dir", "g0.dis=2"):
            with self.subTest(line):
                need = Need("code", "event", line, context=page, series="T")
                self.assertEqual(unmatched([need], rules), [])
        for line in ("g0.w=5", "g0.x=5", "sys0=g0.pw"):
            with self.subTest(line):
                need = Need("code", "event", line, context=page, series="T")
                self.assertEqual(unmatched([need], rules), [need])


class OnPTest(unittest.TestCase):
    """On P: its entries by its style."""

    def test_its_entries_by_its_style(self):
        # As on T: a style of 1 gives its borderc and borderw entries 22 and
        # 23, and every later entry moves two on. Its sta's highest is 3.
        def names(style: int) -> dict:
            return {entry: name for entry, (name, *_) in
                    scrolling_text._of(1, style, style == 1).P_ENTRIES.items() if entry >= 19}
        later = ("font", "bco", "pco", "xcen", "ycen", "dir", "dis", "tim", "en", "txt",
                 "txt_maxl", "isbr", "spax", "spay", "vvs0", "vvs1", "vvs2", "vvs3")
        self.assertEqual(names(0), {19: "sta", 20: "style",
                                    **{22 + number: name for number, name in enumerate(later)}})
        self.assertEqual(names(1), {19: "sta", 20: "style", 22: "borderc", 23: "borderw",
                                    **{24 + number: name for number, name in enumerate(later)}})
        self.assertEqual(scrolling_text._of(1, 0, False).P_ENTRIES[19][2], 3)

    def test_it_is_matched_on_p_and_e(self):
        for series in ("P", "E"):
            with self.subTest(series):
                self.assertEqual(unmatched([Need("type", "scrolling-text", series=series)],
                                           matched_rules()), [])


if __name__ == "__main__":
    unittest.main()
