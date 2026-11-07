"""The dual-state button component (tft/component_types/dual_state_button.py):
that it is written as a button is, the start of its down event, its memory,
what its list matched, and which of its attributes code may use, on T, and
on P.

Each test gives the function it checks a probe's page, made in memory from
the probe's components (tools/tft/probing/dual_state_button_probes.py), in a
Project of the facts it reads, and its place, read from the probe's table
(tests/tft/unit_inputs.py). Each dual-state button of each probe that keeps
fixtures is compared with the probe's pieces (tests/tft/t_components.py), and
one probe on each series is compared whole in tests/tft/test_whole_files.py, as
is its font in a second font, which a page made in memory cannot hold.
"""
from dataclasses import replace
import struct
import unittest

from nxwright.tft.compile_context import CompileContext
from nxwright.tft.component_types import button, dual_state_button, entry_operand
from nxwright.tft.matching import Need, matched_rules, project_needs, unmatched
from tools.tft.probing import dual_state_button_probes, p_probes
from nxwright.tft.statements import CodePlace, StatementError, encode_line
from tests.tft.p_components import PTypePieces, p_values
from tests.tft.t_components import CodePieces, EventStartPieces, TypePieces
from tests.tft.test_button import entry_values, look_ends
from tests.tft.unit_inputs import page, place, probe_facts, probe_project

# bt0's entry of its val: its first entry is 33, and its val a button's, 28.
VAL = b"\x01" + struct.pack("<I", 61)


def probe_named(name: str):
    return next(probe for probe in dual_state_button_probes.PROBES if probe.name == name)


def place_of(name: str, object_id: int = 1):
    """Returns where the component `object_id` of page0 of the probe `name`
    lies, as its table gives it. A probe that keeps no fixtures has no
    table, and its component takes the place of dual-state-button-two's
    first, the first component of a page."""
    probe = probe_named(name)
    if probe.fixtures is None:
        return place(probe_named("dual-state-button-two"), "page0-1")
    return place(probe, "page0-%d" % object_id)


def facts(name: str, series: str = None):
    """Returns a Project of facts of the pages of the probe `name`, on its
    own series or on `series` (unit_inputs.probe_facts)."""
    return probe_facts(probe_named(name), series)


class AsAButtonTest(unittest.TestCase):
    """A dual-state button's drawing, entries, record, memory, and events."""

    NAME = "dual-state-button-pressed-in"

    @classmethod
    def setUpClass(cls):
        cls.project = facts(cls.NAME)
        cls.bt0, cls.place = cls.project.pages[0].objects[1], place_of(cls.NAME)

    def test_its_drawing_is_a_button_s(self):
        # Its first block, as the Nextion Editor wrote it: the comparison of
        # its val with 1, which jumps past its look pressed in, 143 bytes.
        drawing = dual_state_button.variant(self.bt0).drawing(self.bt0, self.project, self.place)
        self.assertEqual(drawing,
                         button.variant(self.bt0).drawing(self.bt0, self.project, self.place))
        self.assertEqual(drawing[0], b"\x09\x00\x04" + VAL + b",1,1,\x03\x8f\x00\x00\x00")

    def test_its_entries_and_record_are_a_button_s(self):
        one, as_button = dual_state_button.variant(self.bt0), button.variant(self.bt0)
        self.assertEqual(one.ENTRIES, 42)
        self.assertEqual(one.data(self.bt0, self.project, self.place),
                         as_button.data(self.bt0, self.project, self.place))
        self.assertEqual(one.record_slots(), as_button.record_slots())

    def test_its_memory_gives_its_val(self):
        # A button's, its val 1 in its second byte, then its text in 11
        # bytes, txt_maxl + 1.
        self.assertEqual(dual_state_button.variant(self.bt0).memory(self.bt0, self.project),
                         b"\x00\x01\x18\xc6\x00\x04\x00\x00\xff\xff\x01\x01\x00newtxt"
                         + bytes(5))

    def test_its_down_event_starts_with_the_switch_then_its_ref(self):
        # A checkbox's switch of its val, then ref, its ID, `+`, and 65535.
        one = dual_state_button.variant(self.bt0)
        self.assertEqual(one.event_start(self.bt0, self.project, self.place, "down"), [
            b"\x09\x00\x04" + VAL + b",1,1,\x03\x16\x00\x00\x00", VAL + b"=0",
            b"T \x03\x0b\x00\x00\x00", VAL + b"=1", b"\x09\x03\x041+\x03\xff\xff\x00\x00"])
        self.assertEqual(one.event_start(self.bt0, self.project, self.place, "up"), [])


class ValuesTest(unittest.TestCase):
    """A dual-state button's attributes that its memory alone gives, as a
    button's, each pair apart, and its spax and spay, which its drawing and
    its entries give, as the Nextion Editor wrote them."""

    def memories(self, name: str) -> list:
        project = facts(name)
        return [dual_state_button.variant(page_object).memory(page_object, project)[:13]
                for page_object in project.pages[0].objects[1:]]

    def test_its_colours(self):
        # Its font, its val, its bco, bco2, pco, and pco2, then its xcen,
        # ycen, and isbr.
        self.assertEqual(self.memories("dual-state-button-of-other-colours"), [
            bytes.fromhex("00 00 01 00 02 00 03 00 04 00 01 01 00"),
            bytes.fromhex("00 00 ff ff 00 00 00 f8 1f 00 01 01 00")])

    def test_its_placing(self):
        self.assertEqual(self.memories("dual-state-button-of-other-placing"), [
            bytes.fromhex("00 00 18 c6 00 04 00 00 ff ff 00 02 01"),
            bytes.fromhex("00 00 18 c6 00 04 00 00 ff ff 02 00 00")])

    def test_its_spacing(self):
        # A button's: each look's setbrush gives spax and spay as numbers,
        # after isbr's entry, and so do entries 32 and 33.
        name = "dual-state-button-of-spacing"
        project = facts(name)
        for object_id, spacing, values in ((1, b",5,7,0,1", [5, 7]),
                                           (2, b",255,3,0,1", [255, 3])):
            place_of_it = place_of(name, object_id)
            with self.subTest(object_id):
                isbr = entry_operand(place_of_it.first_entry + 31)
                self.assertEqual(look_ends(dual_state_button, project, object_id, place_of_it),
                                 [isbr + spacing] * 2)
                self.assertEqual(entry_values(dual_state_button, project, object_id,
                                              place_of_it, (32, 33)), values)


class AsAButtonOfEachStyleTest(unittest.TestCase):
    """A dual-state button of each style, and with pictures or crops behind
    it, written as the button of its sta and style (button.variant), as the
    Nextion Editor wrote them, each at its place in its probe (place_of)."""

    def test_its_drawing_entries_and_record_are_its_button_s(self):
        for name in ("dual-state-button-of-each-style", "dual-state-button-of-pictures-and-crops"):
            project = facts(name)
            for object_id, page_object in enumerate(project.pages[0].objects[1:], 1):
                place_of_it = place_of(name, object_id)
                one, as_button = (dual_state_button.variant(page_object),
                                  button.variant(page_object))
                with self.subTest(name=name, object_id=object_id):
                    self.assertEqual(one.drawing(page_object, project, place_of_it),
                                     as_button.drawing(page_object, project, place_of_it))
                    self.assertEqual((one.ENTRIES, one.record_slots()),
                                     (as_button.ENTRIES, as_button.record_slots()))

    def test_its_memory_behind_pictures(self):
        # The pictures' IDs lie where its bco and bco2 lie, and its val, 1 for
        # the first, which starts pressed in, in its second byte.
        project = facts("dual-state-button-of-pictures-and-crops")
        picture, crop = project.pages[0].objects[1:3]
        self.assertEqual([dual_state_button.variant(page_object).memory(page_object, project)[:6]
                          for page_object in (picture, crop)],
                         [bytes.fromhex("00 01 00 00 01 00"), bytes.fromhex("00 00 01 00 00 00")])


class PiecesTest(TypePieces, CodePieces, EventStartPieces, unittest.TestCase):
    """Each dual-state button of each probe that keeps its whole user code,
    at its type's functions, its events' start among them, and each probe of
    code, at the statement encoder, against the probe's pieces
    (tests/tft/t_components.py)."""

    TYPE = "dual-state-button"
    PROBES = dual_state_button_probes.PROBES
    COUNT = 18
    CODE_COUNT = 2


class PPiecesTest(PTypePieces, CodePieces, unittest.TestCase):
    """Each dual-state button of each of its probes on P that keeps its whole
    user code, at its type's functions on P, and each probe of code, against
    the probe's pieces (tests/tft/p_components.py)."""

    TYPE = "dual-state-button"
    PROBES = [probe for probe in p_probes.PROBES
              if probe.name.startswith("p-dual-state-button-")]
    COUNT = 19
    CODE_COUNT = 2


class MatchedTest(unittest.TestCase):
    """The needs dual_state_button.MATCHED covers (matching.py)."""

    def test_what_it_covers(self):
        covered = [Need("type", "dual-state-button"),
                   Need("attribute", "dual-state-button.objname", b"bt0"),
                   Need("attribute", "dual-state-button.val", b"\x01"),
                   Need("attribute", "dual-state-button.txt", b"Go12",
                        context={"txt_maxl": (10).to_bytes(2, "little")}),
                   Need("attribute", "dual-state-button.txt_maxl", (200).to_bytes(2, "little"),
                        context={"txt": b"Yo"}),
                   Need("attribute", "dual-state-button.font", b"\x01")]
        # The values its memory alone gives, as a button's, at their ends.
        for name, ends in (("bco", (0, 0xFFFF)), ("bco2", (0, 0xFFFF)), ("pco", (0, 0xFFFF)),
                           ("pco2", (0, 0xFFFF)), ("xcen", (0, 2)), ("ycen", (0, 2)),
                           ("isbr", (0, 1)), ("spax", (0, 255)), ("spay", (0, 255))):
            covered += [Need("attribute", "dual-state-button." + name, end.to_bytes(2, "little"))
                        for end in ends]
        # What lies behind it, its border, and its pictures, as a button's, on
        # T and K: each style at a sta of 1, and 0, 2, 3, and 4 at another.
        looks = [Need("attribute", "dual-state-button.sta", bytes([sta])) for sta in (0, 2)]
        looks += [Need("attribute", "dual-state-button.style", bytes([style]))
                  for style in (0, 1, 2, 3)]
        looks += [Need("attribute", "dual-state-button.style", bytes([style]),
                       context={"sta": bytes([sta])})
                  for sta in (0, 2) for style in (0, 1, 2, 3, 4)]
        looks += [Need("attribute", "dual-state-button." + name, end.to_bytes(2, "little"))
                  for name, ends in (("borderc", (0, 0xFFFF)), ("borderw", (0, 255)),
                                     ("pic", (0, 0xFFFF)), ("pic2", (0, 0xFFFF)),
                                     ("picc", (0, 0xFFFF)), ("picc2", (0, 0xFFFF)))
                  for end in ends]
        covered += looks + [replace(need, series="K") for need in looks]
        # On P and E, a sta of 3 too, nothing behind it, at any style.
        covered += [Need("attribute", "dual-state-button.sta", b"\x03", series=series)
                    for series in "PE"]
        covered += [Need("attribute", "dual-state-button.style", bytes([style]),
                         context={"sta": b"\x03"}, series="P") for style in (0, 1, 2, 3, 4)]
        self.assertEqual(unmatched(covered, dual_state_button.MATCHED), [])

    def test_what_it_leaves_out(self):
        left = [Need("attribute", "dual-state-button.spax", (256).to_bytes(2, "little"))]
        # Past what the probes showed, as a button's, on T and on P: a sta
        # past 2 on T and past 3 on P, and a style past 4.
        for series, sta_past in ((None, 3), ("P", 4)):
            left += [Need("attribute", "dual-state-button." + name,
                          number.to_bytes(2, "little"), series=series)
                     for name, number in (("sta", sta_past), ("style", 5), ("borderw", 256))]
        self.assertEqual(unmatched(left, dual_state_button.MATCHED), left)

    def test_its_val_is_written_as_it_is_whatever_its_width(self):
        # A val is written as it is, whatever its value, as long as it fits
        # in the bytes that store it. A val of 1 or -1 in 4 bytes, and of 2
        # in 1 byte, is taken.
        val = "dual-state-button.val"
        taken = [Need("attribute", val, (1).to_bytes(4, "little")),
                 Need("attribute", val, (0xFFFFFFFF).to_bytes(4, "little")),
                 Need("attribute", val, b"\x02")]
        self.assertEqual(unmatched(taken, dual_state_button.MATCHED), [])

    def test_it_is_matched_on_k(self):
        # Its probes matched on K too (k_probes.py).
        project = probe_project(probe_named("dual-state-button-pressed-in"), series="K")
        self.assertEqual(unmatched(project_needs(project), matched_rules()), [])


class CodeTest(unittest.TestCase):
    """Code may use a dual-state button's txt, its val, and any other attribute
    it writes, as a button's."""

    @classmethod
    def setUpClass(cls):
        cls.project = facts("dual-state-button-one")

    def test_its_val(self):
        self.assertEqual(encode_line("bt0.val=1", CodePlace(0, "page0", "up"),
                                     CompileContext(self.project)),
                         VAL + b"=1")

    def test_its_other_attributes(self):
        # Any attribute it writes, such as its bco, entry 22 within the type,
        # after bt0's first entry, 33; but not one it does not write.
        place_in_code = CodePlace(0, "page0", "up")
        self.assertEqual(encode_line("bt0.bco=1", place_in_code, CompileContext(self.project)),
                         b"\x01" + (33 + 22).to_bytes(4, "little") + b"=1")
        with self.assertRaisesRegex(StatementError, "bt0's pw is not encoded"):
            encode_line("bt0.pw=1", place_in_code, CompileContext(self.project))

    def test_the_check_lets_its_txt_and_val_through(self):
        project = probe_project(probe_named("dual-state-button-txt-and-val-in-code"))
        self.assertEqual(unmatched(project_needs(project), matched_rules()), [])


class PTest(unittest.TestCase):
    """On P, a dual-state button is written as a button is there, its val its
    own (p_probes.py)."""

    def test_its_memory_gives_its_val(self):
        # A button's, after its effect's 4 bytes: its sta and style, its
        # font, its colours, its xcen and ycen, its val, 1, then its
        # txt_maxl. At p-dual-state-button-two's first one's place.
        bt0 = page(dual_state_button_probes.dual_state_button_component(val=1),
                   series="P").objects[1]
        kept = next(probe for probe in p_probes.PROBES
                    if probe.name == "p-dual-state-button-two")
        self.assertEqual(p_values(bt0, place(kept, "page0-1"))[4:24].hex(" "),
                         "01 04 00 00 00 00 18 c6 00 04 00 00 ff ff 01 01 01 00 0a 00")

    def test_its_entries_are_its_button_s(self):
        # Of each sta and style, as its button variant's on P.
        project = facts("dual-state-button-of-each-style")
        for page_object in project.pages[0].objects[1:]:
            one, as_button = (dual_state_button.variant(page_object),
                              button.variant(page_object))
            self.assertEqual((one.P_ENTRIES, one.P_MEMORY_SIZE, one.P_TEXTS,
                              one.P_LAST_RESOURCE),
                             (as_button.P_ENTRIES, as_button.P_MEMORY_SIZE,
                              as_button.P_TEXTS, as_button.P_LAST_RESOURCE))

    def test_it_is_matched_on_p_and_e_with_its_border(self):
        # Its border and what lies behind it too, as a button's.
        for series in ("P", "E"):
            with self.subTest(series):
                need = Need("type", "dual-state-button", series=series)
                self.assertEqual(unmatched([need], matched_rules()), [])
                style = Need("attribute", "dual-state-button.style", b"\x01", series=series)
                self.assertEqual(unmatched([style], matched_rules()), [])


if __name__ == "__main__":
    unittest.main()
