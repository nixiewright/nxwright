"""The attributes every component with a place has, and the page too
(tft/frame.py): each component of the probes of
tools/tft/probing/shared_attribute_probes.py at its type's functions; an
object's aph and sendkey in its record's head; an effect's two more
entries (component_types.EFFECT_ENTRIES); a global object's memory,
before every page's, and on P a global component of each type; and what
the frame's rules of them cover.

Each test gives the function it checks that function's own input: a
probe's pages made in memory, in a Project of the facts it reads, and each
component's place, read from the probe's table (tests/tft/unit_inputs.py). The
sample of whole files is in tests/tft/test_whole_files.py.
"""
from dataclasses import replace
import struct
import unittest

from nxwright.tft import component_types, frame
from tools.tft.probing import frame_probes, p_probes, shared_attribute_probes
from nxwright.tft.matching import Need, unmatched
from nxwright.tft.component_types import object_module, type_name
from tools.tft.probing.waveform_probes import waveform_component
from nxwright.tft.tft_file import encode_blocks
from tests.tft.p_components import PTypePieces, p_probe
from tests.tft.t_components import LoadSectionPieces, t_drawing, t_entries, t_memory
from tests.tft.test_p_series import without_p
from tests.tft.unit_inputs import page, piece, piece_names, place, probe_facts, project_of

# A record's size on T: its head and its 88 slots of 2 bytes.
_RECORD = 232


def _probe(name: str):
    return next(probe for probe in shared_attribute_probes.PROBES if probe.name == name)


def _user_code(name: str):
    """Returns the user code the frame writes for the pages of the probe
    `name`, made in memory, through frame_probes.stand_in_code."""
    return frame.user_code(probe_facts(_probe(name)), frame_probes.stand_in_code)


class PieceTest(unittest.TestCase):
    """Each component of each probe that keeps fixtures, whatever its type,
    at its type's functions, against the probe's pieces. An effect's two
    more entries are among its entries, and a global object's memory is its
    piece among the int variables. A drawn component's background fill
    names the page's bco entry, which the page's effect moves.

    The page's own pieces, and the code in each event, which the probes
    kept through frame_probes.stand_in_code, are the frame's. So is a
    timer's block in its page's load section, which gives a place in its
    record. The tests of the frame take them; until then the sample of
    whole files compares them in one of these probes."""

    PROBES = [probe for probe in shared_attribute_probes.PROBES if probe.fixtures]

    @classmethod
    def setUpClass(cls):
        # (the probe, the names of its pieces, its Project of facts, and,
        # of each component, its key such as "page0-1", its page object,
        # and its place), each probe's pages made once.
        cls.components = []
        for probe in cls.PROBES:
            project, names = probe_facts(probe), piece_names(probe)
            cls.components += [
                (probe, names, project, "page%d-%d" % (number, object_id), page_object,
                 place(probe, "page%d-%d" % (number, object_id)))
                for number, made in enumerate(project.pages)
                for object_id, page_object in enumerate(made.objects[1:], 1)]

    def test_its_probes(self):
        self.assertEqual(len(self.PROBES), 4)

    def test_each_component_s_memory_drawing_and_entries(self):
        # A hotspot writes no memory, and has no piece of it.
        compared = 0
        for probe, names, project, key, page_object, its_place in self.components:
            for kind, function in (("memory", t_memory), ("drawing", t_drawing),
                                   ("entries", t_entries)):
                name = "%s-%s" % (key, kind)
                with self.subTest(probe.name, component=key, kind=kind):
                    self.assertEqual(function(page_object, project, its_place),
                                     piece(probe, name) if name in names else b"")
                compared += 1
        self.assertEqual(compared, 243)

    def test_each_background_fill(self):
        # Each drawn component's, a run ended by a 0 word. The components
        # lie apart, so no run holds a ref to another.
        compared = 0
        for probe, names, project, key, page_object, its_place in self.components:
            if key + "-background-fill" not in names:
                continue
            with self.subTest(probe.name, component=key):
                self.assertEqual(encode_blocks(object_module(page_object).background_fill(
                    page_object, project, its_place) + [b""]),
                    piece(probe, key + "-background-fill"))
            compared += 1
        self.assertEqual(compared, 69)

    def test_each_event_s_start(self):
        # Of each type that writes blocks at its events' start, as a button
        # sets its val, after the event's name.
        compared = 0
        for probe, names, project, key, page_object, its_place in self.components:
            module = object_module(page_object)
            if not hasattr(module, "event_start"):
                continue
            for event in module.EVENTS:
                with self.subTest(probe.name, component=key, event=event):
                    start = module.event_start(page_object, project, its_place, event)
                    self.assertTrue(piece(probe, "%s-event-%s" % (key, event)).startswith(
                        encode_blocks([event.encode("ascii")] + start)))
                compared += 1
        self.assertEqual(compared, 36)

    def test_each_load_section_s_blocks(self):
        # Of each type that writes blocks in its page's load section, but the
        # timer's.
        compared = 0
        for probe, names, project, key, page_object, its_place in self.components:
            if key + "-load" not in names or type_name(page_object) == "timer":
                continue
            with self.subTest(probe.name, component=key):
                self.assertEqual(encode_blocks(object_module(page_object).load_start(
                    page_object, project, its_place, {})), piece(probe, key + "-load"))
            compared += 1
        self.assertEqual(compared, 17)


class RecordHeadTest(unittest.TestCase):
    """An object's record gives its sendkey in its head's byte 33 and its aph
    in byte 34, as the Nextion Editor wrote them."""

    def test_each_object_s(self):
        # The page, sendkey 3 and aph 50; the text, 0 and 127; the number, 1
        # and 119; the scrolling text, the last drawn, 3 and 0; then the
        # variable, the timer, and the touch capture, which have neither: 0
        # and 127.
        name = "shared-attributes-aph-and-sendkey-of-each-type"
        records, objects = _user_code(name).records, probe_facts(_probe(name)).pages[0].objects
        for number, head in ((0, "03 32"), (1, "00 7f"), (2, "01 77"), (16, "03 00"),
                             (17, "00 7f"), (18, "00 7f"), (19, "00 7f")):
            start = _RECORD * number
            with self.subTest(objects[number].attribute("objname")):
                self.assertEqual(records[start + 33:start + 35], bytes.fromhex(head))


class EffectTest(unittest.TestCase):
    """An effect gives an object two more entries, empty: a component's at
    its entry 19, and a page's at its entry 23, each later entry two on, as
    the Nextion Editor wrote them. The entries themselves are compared in
    PieceTest."""

    @classmethod
    def setUpClass(cls):
        cls.probe = _probe("shared-attributes-effects-of-each-type")
        cls.project = probe_facts(cls.probe)
        cls.page, cls.t0 = cls.project.pages[0].objects[:2]

    def test_a_component_s_entries(self):
        # The text's x and y keep entries 9 and 10, and its sta and txt, 19
        # and 28 without an effect, are 21 and 30; its record follows.
        text = component_types.object_module(self.t0)
        self.assertEqual(text.ENTRIES, 41 + 2)
        self.assertEqual([text.attribute_place(name) for name in ("x", "y", "sta", "txt")],
                         [9, 10, 21, 30])
        slots = text.record_slots()
        self.assertEqual([slots[slot] for slot in (42, 43, 2, 28)], [9, 10, 21, 30])

    def test_a_page_s_entries(self):
        # The page's sta and bco, 23 and 24 without an effect, are 25 and 26,
        # and it has 35 entries; a component's background fill names 26.
        self.assertEqual(component_types.page_entries(self.page), 35)
        self.assertEqual([component_types.page_entry(self.page, number) for number in (9, 23, 24)],
                         [9, 25, 26])
        fill = component_types.background_fill(self.t0, self.project,
                                               place(self.probe, "page0-1"))
        self.assertTrue(fill[0].endswith(component_types.entry_operand(26)))

    def test_a_page_of_no_background_s_entries(self):
        # One entry fewer without a background, two more with an effect.
        self.assertEqual(component_types.page_entries(self.project.pages[1].objects[0]), 34)


class GlobalTest(unittest.TestCase):
    """A global object's memory, of vscope 1, lies before every page's, after
    the int variables, and every page's memory follows it, as the Nextion
    Editor wrote it."""

    def bases(self, code, objects: int) -> list:
        return [struct.unpack_from("<I", code.records, _RECORD * number + 28)[0]
                for number in range(objects)]

    def int_area(self, code) -> bytes:
        # The first block's second region (_first_block).
        place_in_block, size = struct.unpack_from("<II", code.blocks[0], 12)
        return code.blocks[0][place_in_block:place_in_block + size]

    def test_every_object_global(self):
        # After the three ints' 12 bytes: the page's memory, then each
        # component's in ID order, the hotspot's empty. Each record gives 1
        # as its vscope, and the page's entry 3 gives 1 too.
        code = _user_code("shared-attributes-every-type-global")
        self.assertEqual(self.bases(code, 20), [12, 20, 40, 64, 88, 96, 100, 108, 120, 128, 152,
                                                152, 176, 204, 228, 244, 280, 316, 320, 324])
        self.assertEqual({code.records[_RECORD * number + 2] for number in range(20)}, {1})
        self.assertEqual(struct.unpack_from("<i", code.data, 24 * 3 + 4)[0], 1)
        # From 328, the QR code's txt and the scrolling text's, then the
        # word of the waveform's buffer, 108 bytes, ending the int area.
        area = self.int_area(code)
        self.assertEqual(len(area), 376)
        self.assertEqual(area[328:352], b"https://nextion.itead.cc")
        self.assertEqual(area[360:366], b"newtxt")
        self.assertEqual(area[372:], struct.pack("<I", 108))
        # The page's memory is its run of 0xFF bytes alone, one for each of
        # its 20 objects, global or not.
        self.assertEqual(struct.unpack_from("<I", code.page_index, 12)[0], 20)

    def test_globals_on_two_pages(self):
        # page0's local objects follow the int area, 260 bytes, and the
        # buffer of page1's global waveform, 276, and then its run of 20
        # bytes. page1's global text and waveform follow page0's last
        # global, its touch capture, at 152.
        code = _user_code("shared-attributes-globals-on-two-pages")
        self.assertEqual(self.bases(code, 25), [
            556, 564, 20, 584, 44, 608, 52, 612, 60, 624, 68, 648, 68, 672, 96, 696, 112, 148,
            732, 152, 544, 156, 176, 552, 568])
        self.assertEqual(self.int_area(code)[-4:], struct.pack("<I", 276))
        self.assertEqual([struct.unpack_from("<I", code.page_index, at)[0] for at in (12, 28)],
                         [200, 52])

    def test_a_global_object_on_p_of_a_type_it_does_not_write(self):
        # The frame refuses a global object of a type it does not write on
        # P, here a stand-in in a global waveform's place
        # (test_p_series.without_p).
        made = page(waveform_component(vscope=1), series="P")
        with without_p("waveform"), self.assertRaisesRegex(frame.FrameError,
                                                           "does not write a waveform"):
            frame.user_code(project_of(made, series="P"))


class GlobalOnPTest(PTypePieces, LoadSectionPieces, unittest.TestCase):
    """On P, a global component of each type P has but the text, the
    number, the button, the data record, and the file stream, beside a
    local text (p_probes.GLOBAL_TYPES): each component at its type's
    functions on P, against the probe's pieces: its values after its
    record's head, its entries (tests/tft/p_components.py), and its blocks in
    its page's load section. A global component's memory lies in the first
    block's int area, where the probe's table gives it its pieces, as a
    local component's in its page's memory. Its head and its record are the
    frame's (tests/tft/test_frame.py)."""

    PROBES = [p_probe("p-globals-" + name) for name in p_probes.GLOBAL_TYPES]
    # The global component and the text of each of the 25 probes.
    COUNT = 50


class MatchedTest(unittest.TestCase):
    """The needs of the frame's rules of these attributes, on T and K, and on
    P and E."""

    def need(self, subject: str, value: int, size: int = 1, series: str = "T") -> Need:
        return Need("attribute", subject, value.to_bytes(size, "little"), series=series)

    def test_what_they_cover(self):
        covered = [self.need("text.aph", 0), self.need("button.aph", 127),
                   self.need("page.aph", 50), self.need("slider.sendkey", 3),
                   self.need("text.drag", 1), self.need("page.lockobj", 1),
                   self.need("timer.groupid0", 0xFFFFFFFF, 4),
                   self.need("variable.groupid1", 1, 4), self.need("gauge.movex", 0xFFFF, 2),
                   self.need("qr-code.movey", 0x8000, 2), self.need("text.effect", 8),
                   self.need("page.effect", 1), self.need("slider.first", 100),
                   self.need("button.time", 150, 2), self.need("gauge.time", 0xFFFF, 2),
                   self.need("text.vscope", 1), self.need("page.vscope", 1),
                   self.need("timer.vscope", 1), self.need("waveform.vscope", 0)]
        covered += [replace(need, series=series) for need in covered for series in "KF"]
        covered += [self.need("page.effect", effect) for effect in (9, 10)]
        self.assertEqual(unmatched(covered, frame.MATCHED), [])

    def test_what_they_cover_on_p(self):
        # Of the types the frame writes on P, as P's probes showed them.
        covered = [self.need("page.aph", 90, series="P"), self.need("text.sendkey", 3, series="P"),
                   self.need("number.drag", 1, series="P"),
                   self.need("button.lockobj", 1, series="P"),
                   self.need("page.movex", 0xFFFF, 2, series="P"),
                   self.need("text.movey", 0x8000, 2, series="P"),
                   self.need("number.groupid0", 3, 4, series="P"),
                   self.need("button.groupid1", 9, 4, series="P"),
                   self.need("text.effect", 3, series="P"), self.need("page.first", 9, series="P"),
                   self.need("button.time", 1150, 2, series="P"),
                   self.need("hotspot.aph", 50, series="P"),
                   self.need("hotspot.drag", 1, series="P"),
                   self.need("hotspot.effect", 2, series="P")]
        covered += [self.need(subject, value, series=series) for series in "PE"
                    for subject, value in (("switch.aph", 50), ("switch.drag", 1),
                                           ("switch.effect", 2), ("external-picture.aph", 50),
                                           ("external-picture.drag", 1),
                                           ("external-picture.effect", 2))]
        # A component of each type P has global, as P's probes of each
        # showed (p_probes.py), and the data record, global whatever its
        # vscope.
        covered += [self.need(name + ".vscope", value, series=series) for series in "PE"
                    for name in ("checkbox", "waveform", "timer", "picture", "select", "gmov",
                                 "file-browser")
                    for value in (0, 1)]
        covered += [self.need("data-record.vscope", 1, series=series) for series in "PE"]
        self.assertEqual(unmatched(covered, frame.MATCHED), [])

    def test_what_they_leave_out(self):
        # Left out: a vscope past 1, and on P, a global file stream, which the
        # Nextion Editor refuses there, and a data record of its page. The
        # other shared attributes take any value that fits in their bytes.
        left = [self.need("text.vscope", 2),
                self.need("file-stream.vscope", 1, series="P"),
                self.need("data-record.vscope", 0, series="P")]
        self.assertEqual(unmatched(left, frame.MATCHED), left)
        taken = [self.need("text.aph", 255), self.need("text.sendkey", 255),
                 self.need("text.drag", 255), self.need("text.lockobj", 255),
                 self.need("text.effect", 255), self.need("text.first", 255),
                 self.need("text.time", 0, 2), self.need("text.effect", 255, series="P")]
        self.assertEqual(unmatched(taken, frame.MATCHED), [])


if __name__ == "__main__":
    unittest.main()
