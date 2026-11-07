"""The radio component (tft/component_types/radio.py): its drawing, the
start of its down event, its memory, its entries, what its list matched,
and which of its attributes code may use, on T, and on F and P.

Each test gives the function it checks a probe's page, made in memory from
the probe's components (tools/tft/probing/radio_probes.py), in a Project of the
facts it reads, and its place, read from the probe's table
(tests/tft/unit_inputs.py). Each radio of each probe that keeps fixtures is
compared with the probe's pieces (tests/tft/t_components.py), and one probe on
each series is compared whole in tests/tft/test_whole_files.py.
"""
import struct
import unittest

from nxwright.tft.compile_context import CompileContext
from nxwright.tft.component_types import radio
from nxwright.tft.matching import Need, matched_rules, project_needs, unmatched
from tools.tft.probing import p_probes, radio_probes
from nxwright.tft.statements import CodePlace, StatementError, encode_line
from tests.tft.p_components import PTypePieces, p_values
from tests.tft.t_components import CodePieces, EventStartPieces, TypePieces
from tests.tft.unit_inputs import page, place, probe_facts, probe_project

# The system variable sya0, as an operand, and r0's entries of its bco,
# pco, and val: its first entry is 33.
SYA0 = b"\x04\x04\x05\x00\x00"
BCO, PCO, VAL = (b"\x01" + struct.pack("<I", number) for number in (52, 53, 54))


def probe_named(name: str):
    return next(probe for probe in radio_probes.PROBES if probe.name == name)


def first_radio(name: str, series: str = None) -> tuple:
    """Returns page0's first component of the probe `name`, on its own
    series or on `series`, the Project of facts of its pages, and its place.
    Its place is its probe's table's; a probe that keeps no fixtures has no
    table, and its first radio takes the place of radio-two's, the first
    component of a page as it is too."""
    probe = probe_named(name)
    project = probe_facts(probe, series)
    kept = probe if probe.fixtures is not None else probe_named("radio-two")
    return project.pages[0].objects[1], project, place(kept, "page0-1")


class DrawingTest(unittest.TestCase):
    """A radio's drawing, the start of its down event, its memory, and its
    entries."""

    def test_its_drawing(self):
        # As the Nextion Editor wrote it for a radio at 10, 10, 40 by 21. The
        # first comparison jumps 27 bytes, past the even width's radius and
        # its jump, when its width is odd; the jump skips the odd width's 14.
        # The second jumps the dot's 38 when its val is not 1.
        r0, project, place_of_r0 = first_radio("radio-wider-than-tall")
        centre = b"10+" + SYA0 + b",10+" + SYA0 + b","
        self.assertEqual(radio.drawing(r0, project, place_of_r0), [
            SYA0 + b"=40&1", b"\x09\x00\x04" + SYA0 + b",0,1,\x03\x1b\x00\x00\x00",
            SYA0 + b"=40/2-1", b"T \x03\x0e\x00\x00\x00", SYA0 + b"=40/2",
            b"\x09\x14\x04" + centre + SYA0 + b"," + BCO,
            b"\x09\x04\x04" + centre + SYA0 + b",\x03\x28\x42\x00\x00",
            b"\x09\x00\x04" + VAL + b",1,1,\x03\x26\x00\x00\x00",
            b"\x09\x14\x04" + centre + SYA0 + b"/2," + PCO])

    def test_its_down_event_starts_with_the_switch(self):
        # A checkbox's: if its val is 1, it is set to 0, else to 1.
        r0, project, place_of_r0 = first_radio("radio-one")
        self.assertEqual(radio.event_start(r0, project, place_of_r0, "down"), [
            b"\x09\x00\x04" + VAL + b",1,1,\x03\x16\x00\x00\x00", VAL + b"=0",
            b"T \x03\x0b\x00\x00\x00", VAL + b"=1"])
        self.assertEqual(radio.event_start(r0, project, place_of_r0, "up"), [])

    def test_its_memory(self):
        # Its bco and pco, its val, three zeros.
        for name, colours, val in (("radio-one", (0xFFFF, 0), 1),
                                   ("radio-not-chosen", (0xFFFF, 0), 0),
                                   ("radio-in-other-colours", (1024, 63488), 1)):
            with self.subTest(probe=name):
                r0, project, _ = first_radio(name)
                self.assertEqual(radio.memory(r0, project),
                                 struct.pack("<HH", *colours) + bytes([val, 0, 0, 0]))

    def test_its_entries(self):
        # Entries 19 to 21 give where its bco, pco, and val lie, from its
        # base, 28, and their highest values.
        r0, project, place_of_r0 = first_radio("radio-one")
        data = radio.data(r0, project, place_of_r0)
        self.assertEqual([struct.unpack_from("<IiiiII", data, 24 * number)[1:3]
                          for number in (19, 20, 21)],
                         [(28, 0xFFFF), (30, 0xFFFF), (32, 1)])


class PiecesTest(TypePieces, CodePieces, EventStartPieces, unittest.TestCase):
    """Each radio of each probe that keeps its whole user code, at its
    type's functions, its events' start among them, and each probe of code,
    at the statement encoder, against the probe's pieces
    (tests/tft/t_components.py)."""

    TYPE = "radio"
    PROBES = radio_probes.PROBES
    COUNT = 4
    CODE_COUNT = 1


class PPiecesTest(PTypePieces, CodePieces, unittest.TestCase):
    """Each radio of each of its probes on P that keeps its whole user code,
    at its type's functions on P, and each probe of code, against the
    probe's pieces (tests/tft/p_components.py)."""

    TYPE = "radio"
    PROBES = [probe for probe in p_probes.PROBES if probe.name.startswith("p-radio-")]
    COUNT = 4
    CODE_COUNT = 1


class MatchedTest(unittest.TestCase):
    """The needs radio.MATCHED covers (matching.py)."""

    def test_what_it_covers(self):
        covered = [Need("type", "radio"), Need("attribute", "radio.objname", b"r0"),
                   Need("attribute", "radio.val", b"\x00"),
                   Need("attribute", "radio.bco", (1024).to_bytes(2, "little")),
                   Need("attribute", "radio.pco", (63488).to_bytes(2, "little"))]
        self.assertEqual(unmatched(covered, radio.MATCHED), [])

    def test_what_it_leaves_out(self):
        left = [Need("attribute", "radio.aph", b"\x40")]
        self.assertEqual(unmatched(left, radio.MATCHED), left)

    def test_its_val_is_written_as_it_is_whatever_its_width(self):
        # A val is written as it is, whatever its value, as long as it fits
        # in the bytes that store it. A val of 1 or -1 in 4 bytes, and of 2
        # in 1 byte, is taken.
        taken = [Need("attribute", "radio.val", (1).to_bytes(4, "little")),
                 Need("attribute", "radio.val", (0xFFFFFFFF).to_bytes(4, "little")),
                 Need("attribute", "radio.val", b"\x02")]
        self.assertEqual(unmatched(taken, radio.MATCHED), [])

    def test_it_is_matched_on_k(self):
        # Its probes matched on K too (k_probes.py).
        project = probe_project(probe_named("radio-one"), series="K")
        self.assertEqual(unmatched(project_needs(project), matched_rules()), [])


class CodeTest(unittest.TestCase):
    """Code may use a radio's val, and any other attribute it writes."""

    @classmethod
    def setUpClass(cls):
        cls.project = probe_facts(probe_named("radio-one"))

    def test_its_val(self):
        self.assertEqual(encode_line("r0.val=0", CodePlace(0, "page0", "up"),
                                     CompileContext(self.project)),
                         VAL + b"=0")

    def test_its_other_attributes(self):
        # Any attribute it writes, such as its bco, entry 19 within the type,
        # after r0's first entry, 33; but not one it does not write.
        place_in_code = CodePlace(0, "page0", "up")
        self.assertEqual(encode_line("r0.bco=1", place_in_code, CompileContext(self.project)),
                         b"\x01" + (33 + 19).to_bytes(4, "little") + b"=1")
        with self.assertRaisesRegex(StatementError, "r0's txt is not encoded"):
            encode_line("r0.txt=1", place_in_code, CompileContext(self.project))

    def test_the_check_lets_its_val_through(self):
        project = probe_project(probe_named("radio-val-in-code"))
        self.assertEqual(unmatched(project_needs(project), matched_rules()), [])


class FTest(unittest.TestCase):
    """On F, a radio is written as on T, but for F's number of cirs, 0x18 in
    table 4 (drawing_commands.py, f_probes.py)."""

    def test_its_drawing(self):
        drawings = {}
        for series in ("T", "F"):
            r0, project, place_of_r0 = first_radio("radio-wider-than-tall", series)
            drawings[series] = radio.drawing(r0, project, place_of_r0)
        self.assertEqual(drawings["F"], [block.replace(b"\x09\x14\x04", b"\x09\x18\x04")
                                         for block in drawings["T"]])
        self.assertNotEqual(drawings["F"], drawings["T"])


class PTest(unittest.TestCase):
    """On P, a radio's memory gives its values as on T, after its record's
    head and its effect's values (p_probes.py)."""

    def test_its_memory(self):
        # Its bco and pco, and its val, then three zeros, after its effect's
        # 4 bytes. A radio of other colours, at p-radio-two's first radio's
        # place.
        r0 = page(radio_probes.radio_component(bco=1024, pco=63488), series="P").objects[1]
        values = p_values(r0, place(next(probe for probe in p_probes.PROBES
                                         if probe.name == "p-radio-two"), "page0-1"))
        self.assertEqual(values[4:12].hex(" "), "00 04 00 f8 01 00 00 00")

    def test_its_entries(self):
        # As on T: its bco 19, pco 20, and val 21.
        self.assertEqual({name: (entry, at) for entry, (name, at, *_) in radio.P_ENTRIES.items()
                          if entry >= 19},
                         {"bco": (19, 56), "pco": (20, 58), "val": (21, 60)})

    def test_it_is_matched_on_p_and_e(self):
        for series in ("P", "E"):
            with self.subTest(series):
                need = Need("type", "radio", series=series)
                self.assertEqual(unmatched([need], matched_rules()), [])


if __name__ == "__main__":
    unittest.main()
