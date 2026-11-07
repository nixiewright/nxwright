"""The checkbox component (tft/component_types/checkbox.py): its drawing,
the start of its down event, its memory, its entries, what its list
matched, and which of its attributes code may use, on T, and on F and P.

Each test gives the function it checks a probe's page, made in memory from
the probe's components (tools/tft/probing/checkbox_probes.py), in a Project of
the facts it reads, and its place, read from the probe's table
(tests/tft/unit_inputs.py). Each checkbox of each probe that keeps fixtures is
compared with the probe's pieces (tests/tft/t_components.py), and one probe on
each series is compared whole in tests/tft/test_whole_files.py.
"""
import struct
import unittest

from nxwright.tft.compile_context import CompileContext
from nxwright.tft.component_types import checkbox
from nxwright.tft.matching import Need, matched_rules, project_needs, unmatched
from tools.tft.probing import checkbox_probes, p_probes
from tools.tft.probing.checkbox_probes import checkbox_component
from nxwright.tft.statements import CodePlace, StatementError, encode_line
from tests.tft.p_components import PTypePieces, p_values
from tests.tft.t_components import CodePieces, EventStartPieces, TypePieces
from tests.tft.unit_inputs import page, place, probe_facts, probe_project

# The system variables sya0 and sya1, as operands, and c0's entries of its
# bco, pco, and val: its first entry is 33.
SYA0, SYA1 = b"\x04\x04\x05\x00\x00", b"\x04\x04\x07\x00\x00"
BCO, PCO, VAL = (b"\x01" + struct.pack("<I", number) for number in (53, 54, 55))


def probe_named(name: str):
    return next(probe for probe in checkbox_probes.PROBES if probe.name == name)


def place_of(name: str, object_id: int = 1):
    """Returns where the component `object_id` of page0 of the probe `name`
    lies, as its table gives it. A probe that keeps no fixtures has no
    table, and its component takes the place of checkbox-two's first, the
    first component of a page."""
    probe = probe_named(name)
    if probe.fixtures is None:
        return place(probe_named("checkbox-two"), "page0-1")
    return place(probe, "page0-%d" % object_id)


def first_checkbox(name: str, series: str = None) -> tuple:
    """Returns page0's first component of the probe `name`, on its own
    series or on `series`, the Project of facts of its pages, and its place
    (place_of)."""
    project = probe_facts(probe_named(name), series)
    return project.pages[0].objects[1], project, place_of(name)


class DrawingTest(unittest.TestCase):
    """A checkbox's drawing, the start of its down event, its memory, and its
    entries."""

    def test_its_drawing(self):
        # As the Nextion Editor wrote it for a checkbox at 10, 10, 40 by 20.
        # The comparison jumps 42 bytes, past the square's fill, when its val
        # is not 1. The border's colours are 16936 then 59164.
        c0, project, place_of_c0 = first_checkbox("checkbox-wider-than-tall")
        self.assertEqual(checkbox.variant(c0).drawing(c0, project, place_of_c0), [
            SYA0 + b"=40/4", SYA1 + b"=40-" + SYA0 + b"-" + SYA0,
            b"\x09\x0d\x0410,10,40,20," + BCO,
            b"\x09\x00\x04" + VAL + b",1,1,\x03\x2a\x00\x00\x00",
            b"\x09\x0d\x0410+" + SYA0 + b",10+" + SYA0 + b"," + SYA1 + b"," + SYA1 + b"," + PCO,
            b"\x09\x07\x0810,10,40,20,\x03\x28\x42\x00\x00,\x03\x1c\xe7\x00\x00,1"])

    def test_its_down_event_starts_with_the_switch(self):
        # If its val is 1, it is set to 0, and a jump of 11 bytes skips
        # setting it to 1. Else the comparison jumps those 22 bytes.
        c0, project, place_of_c0 = first_checkbox("checkbox-one")
        self.assertEqual(checkbox.variant(c0).event_start(c0, project, place_of_c0, "down"), [
            b"\x09\x00\x04" + VAL + b",1,1,\x03\x16\x00\x00\x00", VAL + b"=0",
            b"T \x03\x0b\x00\x00\x00", VAL + b"=1"])
        self.assertEqual(checkbox.variant(c0).event_start(c0, project, place_of_c0, "up"), [])

    def test_its_memory(self):
        # Its style, 2, three zeros, its bco and pco, its val, three zeros.
        for name, colours, val in (("checkbox-one", (0xFFFF, 0), 1),
                                   ("checkbox-unchecked", (0xFFFF, 0), 0),
                                   ("checkbox-in-other-colours", (1024, 63488), 1)):
            with self.subTest(probe=name):
                c0, project, _ = first_checkbox(name)
                self.assertEqual(checkbox.variant(c0).memory(c0, project),
                                 b"\x02\x00\x00\x00" + struct.pack("<HH", *colours)
                                 + bytes([val, 0, 0, 0]))

    def test_its_entries(self):
        # Entries 19 to 22 give where its style, bco, pco, and val lie, from
        # its base, 28, and their highest values.
        c0, project, place_of_c0 = first_checkbox("checkbox-one")
        data = checkbox.variant(c0).data(c0, project, place_of_c0)
        self.assertEqual([struct.unpack_from("<IiiiII", data, 24 * number)[1:3]
                          for number in (19, 20, 21, 22)],
                         [(28, 3), (32, 0xFFFF), (34, 0xFFFF), (36, 1)])


class StyleTest(unittest.TestCase):
    """A checkbox's border by its style, as the Nextion Editor wrote it for
    checkboxes at 10, 10, 10, 60, 10, 110, and 10, 160, each of 40 by 30,
    each at its place in its probe (place_of)."""

    NAME = "checkbox-of-each-style"

    @classmethod
    def setUpClass(cls):
        cls.project = probe_facts(probe_named(cls.NAME))
        cls.checkboxes = cls.project.pages[0].objects[1:5]

    @staticmethod
    def entry(number: int) -> bytes:
        return b"\x01" + struct.pack("<I", number)

    def place(self, page_object):
        return place_of(self.NAME, self.project.pages[0].objects.index(page_object))

    def drawing(self, page_object) -> list:
        return checkbox.variant(page_object).drawing(page_object, self.project,
                                                     self.place(page_object))

    def test_its_border(self):
        # None at a style of 0; at 1, the border command with its borderc's
        # entry, 21 within the type, twice, then its borderw's, 20; at 2,
        # dark then light; and at 3, light then dark.
        flat, bordered, sunken, raised = self.checkboxes
        first_entry = self.place(bordered).first_entry
        self.assertEqual(len(self.drawing(flat)), 5)
        self.assertEqual(self.drawing(bordered)[-1],
                         b"\x09\x07\x0810,60,40,30," + self.entry(first_entry + 21) + b","
                         + self.entry(first_entry + 21) + b"," + self.entry(first_entry + 20))
        self.assertEqual(self.drawing(sunken)[-1],
                         b"\x09\x07\x0810,110,40,30,\x03\x28\x42\x00\x00,\x03\x1c\xe7\x00\x00,1")
        self.assertEqual(self.drawing(raised)[-1],
                         b"\x09\x07\x0810,160,40,30,\x03\x1c\xe7\x00\x00,\x03\x28\x42\x00\x00,1")

    def test_its_memory(self):
        # Its style, then its borderw and borderc at a style of 1 alone,
        # though the third checkbox's page file gives them too.
        for page_object, memory in zip(self.checkboxes, (
                "00 00 00 00 1f 00 e0 07 01 00 00 00", "01 03 00 f8 1f 00 00 00 01 00 00 00",
                "02 00 00 00 ff ff 00 00 01 00 00 00", "03 00 00 00 ff ff 00 00 00 00 00 00")):
            with self.subTest(page_object.attribute("objname")):
                self.assertEqual(checkbox.variant(page_object).memory(page_object, self.project),
                                 bytes.fromhex(memory))

    def test_its_entries_and_slots_at_style_1(self):
        # 33 entries: its borderw and borderc 20 and 21, then its bco, pco,
        # and val, two on; its borderc in slot 60 and its borderw in 61; and
        # its down event's switch by its val's entry, 24 within the type.
        bordered = self.checkboxes[1]
        one = checkbox.variant(bordered)
        self.assertEqual(one.ENTRIES, 33)
        self.assertEqual([one.attribute_place(name)
                          for name in ("borderw", "borderc", "bco", "pco", "val")],
                         [20, 21, 22, 23, 24])
        self.assertEqual(one.record_slots(), {
            1: 3, 4: 22, 16: 23, 20: 24, 42: 9, 43: 10, 44: 13, 45: 14, 46: 11, 47: 12, 49: 1,
            59: 19, 60: 21, 61: 20, 62: 0})
        place_of_bordered = self.place(bordered)
        switch = one.event_start(bordered, self.project, place_of_bordered, "down")
        self.assertTrue(switch[0].startswith(
            b"\x09\x00\x04" + self.entry(place_of_bordered.first_entry + 24)))
        for page_object in self.checkboxes[:1] + self.checkboxes[2:]:
            with self.subTest(page_object.attribute("objname")), self.assertRaises(KeyError):
                checkbox.variant(page_object).attribute_place("borderw")


class PiecesTest(TypePieces, CodePieces, EventStartPieces, unittest.TestCase):
    """Each checkbox of each probe that keeps its whole user code, at its
    type's functions, its events' start among them, and each probe of code,
    at the statement encoder, against the probe's pieces
    (tests/tft/t_components.py)."""

    TYPE = "checkbox"
    PROBES = checkbox_probes.PROBES
    COUNT = 8
    CODE_COUNT = 2


class PPiecesTest(PTypePieces, CodePieces, unittest.TestCase):
    """Each checkbox of each of its probes on P that keeps its whole user
    code, at its type's functions on P, and each probe of code, against the
    probe's pieces (tests/tft/p_components.py)."""

    TYPE = "checkbox"
    PROBES = [probe for probe in p_probes.PROBES if probe.name.startswith("p-checkbox-")]
    COUNT = 8
    CODE_COUNT = 2


class MatchedTest(unittest.TestCase):
    """The needs checkbox.MATCHED covers (matching.py)."""

    def test_what_it_covers(self):
        covered = [Need("type", "checkbox"), Need("attribute", "checkbox.objname", b"c0"),
                   Need("attribute", "checkbox.val", b"\x00"),
                   Need("attribute", "checkbox.bco", (1024).to_bytes(2, "little")),
                   Need("attribute", "checkbox.pco", (63488).to_bytes(2, "little")),
                   Need("attribute", "checkbox.style", b"\x00"),
                   Need("attribute", "checkbox.style", b"\x01"),
                   Need("attribute", "checkbox.style", b"\x03"),
                   Need("attribute", "checkbox.borderc", (63488).to_bytes(2, "little")),
                   Need("attribute", "checkbox.borderw", b"\x00"),
                   Need("attribute", "checkbox.borderw", b"\xff")]
        self.assertEqual(unmatched(covered, checkbox.MATCHED), [])

    def test_what_it_leaves_out(self):
        left = [Need("attribute", "checkbox.style", b"\x04")]
        self.assertEqual(unmatched(left, checkbox.MATCHED), left)

    def test_its_val_is_written_as_it_is_whatever_its_width(self):
        # A val is written as it is, whatever its value, as long as it fits
        # in the bytes that store it. A val of 1 or -1 in 4 bytes, and of 2
        # in 1 byte, is taken.
        taken = [Need("attribute", "checkbox.val", (1).to_bytes(4, "little")),
                 Need("attribute", "checkbox.val", (0xFFFFFFFF).to_bytes(4, "little")),
                 Need("attribute", "checkbox.val", b"\x02")]
        self.assertEqual(unmatched(taken, checkbox.MATCHED), [])

    def test_it_is_matched_on_k(self):
        # Its probes matched on K too (k_probes.py).
        project = probe_project(probe_named("checkbox-one"), series="K")
        self.assertEqual(unmatched(project_needs(project), matched_rules()), [])


class PTest(unittest.TestCase):
    """On P, a checkbox's memory gives its values as on T, after its
    record's head and its effect's values (p_probes.py)."""

    @staticmethod
    def values(**attributes) -> bytes:
        """Returns the values a checkbox of `attributes` gives in its memory
        on P, after its effect's 4 bytes: at p-checkbox-two's first
        checkbox's place."""
        c0 = page(checkbox_component(**attributes), series="P").objects[1]
        kept = next(probe for probe in p_probes.PROBES if probe.name == "p-checkbox-two")
        return p_values(c0, place(kept, "page0-1"))[4:16]

    def test_its_memory(self):
        # Sunken, its default: no borderw or borderc, then its bco, pco, and
        # val. A style of 1 gives its borderw and borderc too.
        self.assertEqual(self.values().hex(" "), "02 00 00 00 ff ff 00 00 01 00 00 00")
        self.assertEqual(self.values(style=1, borderw=3, borderc=63488).hex(" "),
                         "01 03 00 f8 ff ff 00 00 01 00 00 00")

    def test_its_entries(self):
        # As on T: its style 19, then its bco, pco, and val, or at a style
        # of 1 its borderw and borderc first.
        variant = checkbox._of(1)
        self.assertEqual({name: (entry, at) for entry, (name, at, *_) in variant.P_ENTRIES.items()
                          if entry >= 19},
                         {"style": (19, 56), "borderw": (20, 57), "borderc": (21, 58),
                          "bco": (22, 60), "pco": (23, 62), "val": (24, 64)})
        self.assertEqual(variant.ENTRIES, 33)

    def test_it_is_matched_on_p_and_e(self):
        for series in ("P", "E"):
            with self.subTest(series):
                need = Need("type", "checkbox", series=series)
                self.assertEqual(unmatched([need], matched_rules()), [])


class FTest(unittest.TestCase):
    """On F, a checkbox is written as on T, but for F's number of sya1 in its
    drawing (statements.SYSTEM_VARIABLES, f_probes.py)."""

    def test_its_drawing(self):
        drawings = {}
        for series in ("T", "F"):
            c0, project, place_of_c0 = first_checkbox("checkbox-one", series)
            drawings[series] = checkbox.variant(c0).drawing(c0, project, place_of_c0)
        f_sya1 = b"\x04\x04\x08\x00\x00"
        self.assertTrue(any(SYA1 in block for block in drawings["T"]))
        self.assertEqual(drawings["F"], [block.replace(SYA1, f_sya1) for block in drawings["T"]])

    def test_it_is_matched_on_f(self):
        self.assertEqual(unmatched([Need("type", "checkbox", series="F")], matched_rules()), [])


class CodeTest(unittest.TestCase):
    """Code may use a checkbox's val, and any other attribute it writes."""

    @classmethod
    def setUpClass(cls):
        cls.project = probe_facts(probe_named("checkbox-one"))

    def test_its_val(self):
        self.assertEqual(encode_line("c0.val=0", CodePlace(0, "page0", "up"),
                                     CompileContext(self.project)),
                         VAL + b"=0")

    def test_its_other_attributes(self):
        # Any attribute it writes, such as its bco, entry 20 within the type,
        # after c0's first entry, 33; but not one it does not write.
        place_in_code = CodePlace(0, "page0", "up")
        self.assertEqual(encode_line("c0.bco=1", place_in_code, CompileContext(self.project)),
                         b"\x01" + (33 + 20).to_bytes(4, "little") + b"=1")
        with self.assertRaisesRegex(StatementError, "c0's txt is not encoded"):
            encode_line("c0.txt=1", place_in_code, CompileContext(self.project))

    def test_the_check_lets_its_val_through(self):
        project = probe_project(probe_named("checkbox-val-in-code"))
        self.assertEqual(unmatched(project_needs(project), matched_rules()), [])


if __name__ == "__main__":
    unittest.main()
