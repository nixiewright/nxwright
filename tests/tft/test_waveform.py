"""The waveform component (tft/component_types/waveform.py): its drawing
and the block it adds to its page's load section, its buffer's size, its
memory, its entries, what its list matched, and which of its attributes
code may use, on T and on P.

Each test gives the function it checks that function's own input: a page
object of a probe's components, a Project of the facts it reads, and its
place, from the probe's table (tests/tft/unit_inputs.py). The tests of its
pieces compare each waveform of each probe that keeps fixtures with the
probe's pieces (tests/tft/t_components.py, tests/tft/p_components.py), its block in
its page's load section among them. Its sample of whole files is in
tests/tft/test_whole_files.py.
"""
import struct
import unittest

from nxwright.tft.compile_context import CompileContext
from tools.tft.probing import p_probes, waveform_probes
from nxwright.tft.component_types import waveform
from nxwright.tft.matching import Need, matched_rules, project_needs, unmatched
from nxwright.tft.statements import CodePlace, StatementError, encode_line
from tests.tft.line_context import line_context
from tests.tft.p_components import PTypePieces, p_memory, p_probe
from tests.tft.t_components import CodePieces, LoadSectionPieces, TypePieces
from tests.tft.unit_inputs import page, page_of, place, probe_facts, probe_project, project_of


def probe_named(name: str):
    return next(probe for probe in waveform_probes.PROBES if probe.name == name)


def first_waveform(probe_name: str, series: str = "T"):
    """Returns page0's first component of the probe `probe_name`, made on
    `series`, a Project of its facts, and the place of the first waveform of
    the probe of two, from its table, whose first entry, 33, is the page's
    first component's."""
    made = page_of(probe_named(probe_name), series=series)
    return (made.objects[1], project_of(made, series=series),
            place(probe_named("waveform-two"), "page0-1"))


class PiecesTest(LoadSectionPieces, TypePieces, CodePieces, unittest.TestCase):
    """Each waveform's memory, drawing, entries, and load block in each probe
    of a waveform on T that keeps its user code, against the probe's pieces;
    and each probe of code, at the statement encoder."""

    TYPE = "waveform"
    PROBES = waveform_probes.PROBES
    COUNT = 15
    CODE_COUNT = 2


class PPiecesTest(LoadSectionPieces, PTypePieces, CodePieces, unittest.TestCase):
    """The same on P: each waveform's values in its memory after its head,
    its entries, and its load block; and each probe of code."""

    TYPE = "waveform"
    # The probe of the waveform's commands is their family's
    # (tests/tft/test_waveform_commands.py).
    PROBES = [probe for probe in p_probes.PROBES if probe.name.startswith("p-waveform-")
              and not probe.name.startswith("p-waveform-commands-")]
    COUNT = 16
    CODE_COUNT = 2


class WaveformTest(unittest.TestCase):
    """A waveform's drawing, load block, buffer, and entries."""

    @classmethod
    def setUpClass(cls):
        cls.s0, cls.project, cls.place = first_waveform("waveform-one")
        cls.one = waveform.variant(cls.s0)

    def test_its_drawing_and_load_block(self):
        # No drawing of its own: the screen draws it from the block it adds
        # to its page's load section, a slider's 09 16 04 and its ID as text.
        self.assertEqual(self.one.drawing(self.s0, self.project, self.place), [])
        self.assertEqual(self.one.load_start(self.s0, self.project, self.place, {}),
                         [b"\x09\x16\x041"])

    def test_its_load_block_on_k(self):
        # K numbers the command 0x18 in table 4, as it does a slider's, where
        # T has 0x16. Its ID is written as on T.
        s0, project, s0_place = first_waveform("waveform-one", "K")
        self.assertEqual(waveform.variant(s0).load_start(s0, project, s0_place, {}),
                         [b"\x09\x18\x041"])

    def test_its_buffer_s_size(self):
        # As the Nextion Editor gave it for these widths, whatever the
        # height: 16 plus 13/10 of the width, rounded down, then up to a
        # multiple of 4.
        for w, size in ((2, 20), (3, 20), (4, 24), (10, 32), (13, 32), (14, 36), (44, 76),
                        (100, 148), (200, 276), (320, 432)):
            with self.subTest(w=w):
                made = page(waveform_probes.waveform_component(x=0, w=w, h=20))
                s0 = made.objects[1]
                self.assertEqual(waveform.variant(s0).buffer_size(s0, project_of(made)), size)

    def test_its_entries(self):
        # Its ch, entry 21, at base + 2, from 1 to 4, and its dis, entry 30,
        # at base + 24, from 10 to 1000.
        data = self.one.data(self.s0, self.project, self.place)
        self.assertEqual(struct.unpack_from("<Iiii", data, 24 * 21)[1:],
                         (self.place.base + 2, 4, 1))
        self.assertEqual(struct.unpack_from("<Iiii", data, 24 * 30)[1:],
                         (self.place.base + 24, 1000, 10))


class ChannelsTest(unittest.TestCase):
    """A waveform's channels, as the Nextion Editor wrote them for waveforms
    of 100 by 60."""

    @classmethod
    def setUpClass(cls):
        cls.probe = probe_named("waveform-channels")
        cls.project = probe_facts(cls.probe)

    def test_its_entries_and_slots_by_channels(self):
        # Of ch channels, it has 40 + ch entries: channel i's colour is entry
        # 28 + i, then one entry is empty, then dis is entry 29 + ch. Its
        # record gives channel i's colour in slot 10 + i, and dis in slot 55.
        for number, page_object in enumerate(self.project.pages[0].objects[1:]):
            channels = number + 1
            one = waveform.variant(page_object)
            with self.subTest(ch=channels):
                self.assertEqual(one.ENTRIES, 40 + channels)
                slots = one.record_slots()
                self.assertEqual({slot: slots[slot] for slot in range(10, 14) if slot in slots},
                                 {10 + colour: 28 + colour for colour in range(channels)})
                self.assertEqual(slots[55], 29 + channels)

    def test_its_buffer_s_size_by_channels(self):
        # Each channel takes as much as the first: 148 for a width of 100.
        sizes = [waveform.variant(page_object).buffer_size(page_object, self.project)
                 for page_object in self.project.pages[0].objects[1:]]
        self.assertEqual(sizes, [148, 296, 444, 592])

    def test_its_memory_leaves_out_colours_past_its_channels(self):
        # Of 2 channels, with a pco2 of 1 and a pco3 of 4660: both are 0.
        made = page_of(probe_named("waveform-colours-past-its-channels"))
        s0 = made.objects[1]
        memory = waveform.variant(s0).memory_at(s0, project_of(made),
                                                place(self.probe, "page0-2"))
        self.assertEqual(memory[14:22], bytes.fromhex("ef fb ef ff 00 00 00 00"))


class BackgroundTest(unittest.TestCase):
    """What lies behind a waveform, by its sta, and the values the Nextion
    Editor's panel never shows, as the Nextion Editor wrote them for
    waveforms of 100 by 60."""

    @classmethod
    def setUpClass(cls):
        cls.probe = probe_named("waveform-of-a-picture-and-a-crop")
        cls.project = probe_facts(cls.probe)
        cls.s0, cls.s1 = cls.project.pages[0].objects[1:3]

    def test_its_entries_and_slots(self):
        # With a picture behind it, its pic is entry 22 and slot 6; with a
        # crop, its picc is entry 22 and slot 5. Its bco and its grid have no
        # entry and no slot, and its colours and its dis are numbered three
        # down: of ch channels, 37 + ch entries, channel i's colour entry
        # 25 + i, and dis entry 26 + ch.
        picture, crop = waveform.variant(self.s0), waveform.variant(self.s1)
        self.assertEqual((picture.ENTRIES, crop.ENTRIES), (38, 41))
        self.assertEqual([picture.attribute_place(name) for name in ("pic", "pco0", "dis")],
                         [22, 25, 27])
        self.assertEqual([crop.attribute_place(name) for name in ("picc", "pco0", "pco3", "dis")],
                         [22, 25, 28, 30])
        for name in ("bco", "gdc", "gdw", "gdh", "picc"):
            with self.subTest(name), self.assertRaises(KeyError):
                picture.attribute_place(name)
        self.assertEqual(picture.record_slots(), {
            1: 3, 2: 19, 3: 21, 6: 22, 10: 25, 42: 9, 43: 10, 44: 13, 45: 14, 46: 11, 47: 12,
            48: 20, 49: 1, 55: 27, 62: 0})
        slots = crop.record_slots()
        self.assertEqual((slots[5], slots.get(4), slots.get(6), slots[13], slots[55]),
                         (22, None, None, 28, 30))

    def test_no_picture_and_a_colour_with_pictures(self):
        # A picture behind it but none given gives 65535 where its bco lies.
        # A colour behind it keeps its bco and its grid, whatever pic and
        # picc the page file gives.
        made = page_of(probe_named("waveform-of-no-picture-and-of-a-colour-with-pictures"))
        project = project_of(made)
        for object_id, values in ((1, "ff ff 00 00 00 00"), (2, "00 00 00 04 28 28")):
            page_object = made.objects[object_id]
            memory = waveform.variant(page_object).memory_at(
                page_object, project, place(self.probe, "page0-%d" % object_id))
            with self.subTest(object_id=object_id):
                self.assertEqual(memory[4:10], bytes.fromhex(values))
        self.assertEqual(waveform.variant(made.objects[2]).attribute_place("bco"), 22)

    def test_its_hidden_values(self):
        # Its objWid and objHig after its grid, 2 bytes each, and its
        # inittrue before its dis, written as the page file gives them.
        probe = probe_named("waveform-of-hidden-values")
        project = probe_facts(probe)
        for object_id, sizes, inittrue in ((1, "ff ff 00 80", "ff 00"),
                                           (2, "05 00 07 00", "01 00")):
            page_object = project.pages[0].objects[object_id]
            memory = waveform.variant(page_object).memory_at(
                page_object, project, place(probe, "page0-%d" % object_id))
            with self.subTest(object_id=object_id):
                self.assertEqual(memory[10:14], bytes.fromhex(sizes))
                self.assertEqual(memory[22:24], bytes.fromhex(inittrue))


class MatchedTest(unittest.TestCase):
    """The needs waveform.MATCHED covers (matching.py)."""

    def test_what_it_covers(self):
        covered = [Need("type", "waveform"), Need("attribute", "waveform.objname", b"s0"),
                   Need("attribute", "waveform.ch", b"\x04"),
                   Need("attribute", "waveform.dir", b"\x02"),
                   Need("attribute", "waveform.dis", (10).to_bytes(2, "little")),
                   Need("attribute", "waveform.dis", (1000).to_bytes(2, "little")),
                   Need("attribute", "waveform.gdw", b"\x00"),
                   Need("attribute", "waveform.pco3", (0xFFFF).to_bytes(2, "little")),
                   Need("attribute", "waveform.sta", b"\x00"),
                   Need("attribute", "waveform.sta", b"\x02"),
                   Need("attribute", "waveform.pic", (0xFFFF).to_bytes(2, "little")),
                   Need("attribute", "waveform.picc", (1).to_bytes(2, "little")),
                   Need("attribute", "waveform.objWid", (0xFFFF).to_bytes(2, "little")),
                   Need("attribute", "waveform.objHig", (0x8000).to_bytes(2, "little")),
                   Need("attribute", "waveform.inittrue", b"\xff"),
                   Need("attribute", "waveform.molloc", (1000).to_bytes(4, "little")),
                   Need("attribute", "waveform.molloc_s", (2000).to_bytes(4, "little"))]
        self.assertEqual(unmatched(covered, waveform.MATCHED), [])

    def test_what_it_leaves_out(self):
        left = [Need("attribute", "waveform.ch", b"\x05"),
                Need("attribute", "waveform.ch", b"\x00"),
                Need("attribute", "waveform.sta", b"\x03"),
                Need("attribute", "waveform.sta", b"\x04", series="P")]
        self.assertEqual(unmatched(left, waveform.MATCHED), left)

    def test_nothing_behind_it_on_p_and_e(self):
        # A sta of 3, nothing behind it, which nxwright's build refuses on T,
        # K, and F (waveform-of-nothing-behind).
        taken = [Need("attribute", "waveform.sta", b"\x03", series=series) for series in "PE"]
        self.assertEqual(unmatched(taken, waveform.MATCHED), [])

    def test_it_is_matched_on_k(self):
        # Its probes matched on K too (k_probes.py): its page made on K.
        made = page_of(probe_named("waveform-one"), series="K")
        self.assertEqual(unmatched(project_needs(project_of(made, series="K", fonts=0)),
                                   matched_rules()), [])


class CodeTest(unittest.TestCase):
    """Code may use a waveform's id, and any other attribute it writes."""

    @classmethod
    def setUpClass(cls):
        cls.project = probe_facts(probe_named("waveform-one"))

    def test_its_id(self):
        # s0's first entry is 33, and its id's entry 1 within the type.
        self.assertEqual(encode_line("sys0=s0.id", CodePlace(0, "page0", "up"),
                                     CompileContext(self.project)),
                         b"\x05\x00\x00\x00\x00=\x01" + struct.pack("<I", 34))

    def test_its_other_attributes(self):
        # Any attribute it writes, such as its dis, entry 30 within the type,
        # after s0's first entry, 33; but not one it does not write.
        code_place = CodePlace(0, "page0", "up")
        self.assertEqual(encode_line("s0.dis=1", code_place, CompileContext(self.project)),
                         b"\x01" + (33 + 30).to_bytes(4, "little") + b"=1")
        with self.assertRaisesRegex(StatementError, "s0's txt is not encoded"):
            encode_line("s0.txt=1", code_place, CompileContext(self.project))

    def test_the_check_lets_its_id_through(self):
        project = probe_project(probe_named("waveform-id-in-code"))
        self.assertEqual(unmatched(project_needs(project), matched_rules()), [])

    def test_the_check_refuses_setting_its_id(self):
        # Code cannot change a waveform's id: the Nextion Editor refuses a
        # line that sets it ("Assignment operation failed"). The check
        # leaves out each such line, in an assignment and as a for's start
        # or step, while it takes one that reads the id.
        context = line_context(waveform_probes.waveform_component())
        rules = matched_rules()
        for line in ("s0.id=5", "s0.id++", "s0.id+=1", "s0.id = 5",
                     "for(s0.id=0;sys0<1;sys0++)", "for(sys0=0;sys0<1;s0.id++)"):
            with self.subTest(line):
                need = Need("code", "event", line, context=context)
                self.assertEqual(unmatched([need], rules), [need])
        self.assertEqual(unmatched([Need("code", "event", "sys0=s0.id", context=context)],
                                   rules), [])


class OnPTest(unittest.TestCase):
    """On P: its memory after its record's head, its entries by its
    channels, and its load section's block."""

    def test_its_memory(self):
        # From 56, at its defaults: its sta, dir, and ch, a zero, its bco,
        # gdc, gdw, gdh, objWid, objHig, pco0, three colours of channels it
        # does not have, inittrue, dis, two zeros, then the size of its
        # buffer, 276 bytes, and where its buffer lies.
        s0 = page(waveform_probes.waveform_component(), series="P").objects[1]
        values = p_memory(s0, place(p_probe("p-waveform-two"), "page0-1"))[56:]
        self.assertEqual(values[:32].hex(" "),
                         "01 00 01 00 00 00 00 04 28 28 00 00 00 00 ef fb "
                         "00 00 00 00 00 00 00 00 64 00 00 00 14 01 00 00")
        self.assertEqual(len(values), 36)

    def test_its_entries_by_its_channels(self):
        # As on T: a colour for each channel from 28, one entry left empty,
        # then its dis. Its sta's highest is 3.
        for channels, colours in ((1, {28: "pco0"}), (2, {28: "pco0", 29: "pco1"})):
            with self.subTest(channels=channels):
                names = {entry: name for entry, (name, *_) in
                         waveform._of(channels, 1).P_ENTRIES.items() if entry >= 19}
                self.assertEqual(names, {19: "sta", 20: "dir", 21: "ch", 22: "bco", 23: "gdc",
                                         24: "gdw", 25: "gdh", **colours,
                                         29 + channels: "dis"})
        self.assertEqual(waveform._of(1, 1).P_ENTRIES[19][2], 3)

    def test_its_load_block(self):
        # `init` and its ID, in place of the slider's command.
        made = page(waveform_probes.waveform_component(), series="P")
        s0 = made.objects[1]
        self.assertEqual(waveform.variant(s0).load_start(
            s0, project_of(made, series="P"), place(p_probe("p-waveform-two"), "page0-1"), {}),
            [b"\x09\x1f\x04" + b"1"])

    def test_it_is_matched_on_p_and_e(self):
        for series in ("P", "E"):
            with self.subTest(series):
                self.assertEqual(unmatched([Need("type", "waveform", series=series)],
                                           matched_rules()), [])


if __name__ == "__main__":
    unittest.main()
