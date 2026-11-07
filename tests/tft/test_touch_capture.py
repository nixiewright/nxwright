"""The touch capture component (tft/component_types/touch_capture.py): its
drawing and the block it adds to its page's load section, its memory, its
entries, what its list matched, and that code may read its val but not set
it, on T, K, and P.

Each test gives the function it checks a probe's page, made in memory from
the probe's components (tools/tft/probing/touch_capture_probes.py), in a Project
of the facts it reads, and its place, read from the probe's table
(tests/tft/unit_inputs.py). Each touch capture of each probe that keeps
fixtures is compared with the probe's pieces (tests/tft/t_components.py), and
one probe on each series is compared whole in tests/tft/test_whole_files.py, as
is its record, which the frame writes.
"""
import struct
import unittest

from nxwright.tft.compile_context import CompileContext
from nxwright.tft.component_types import touch_capture
from nxwright.tft.matching import Need, matched_rules, project_needs, unmatched
from tools.tft.probing import p_probes, touch_capture_probes
from nxwright.tft.statements import CodePlace, StatementError, encode_line
from tests.tft.line_context import line_context
from tests.tft.p_components import PTypePieces, p_entries, p_values
from tests.tft.t_components import CodePieces, TypePieces
from tests.tft.unit_inputs import page, place, probe_facts, probe_project


def probe_named(name: str):
    return next(probe for probe in touch_capture_probes.PROBES if probe.name == name)


def p_probe_named(name: str):
    return next(probe for probe in p_probes.PROBES if probe.name == name)


class TouchCaptureTest(unittest.TestCase):
    """A touch capture's drawing, load block, memory, and entries."""

    @classmethod
    def setUpClass(cls):
        probe = probe_named("touch-capture-two")
        cls.project = probe_facts(probe)
        cls.tc0, cls.place = cls.project.pages[0].objects[1], place(probe, "page0-1")

    def test_its_drawing_and_load_block(self):
        # It is not drawn. It adds to its page's load section the slider's
        # command, 09 16 04, and its ID as text.
        self.assertEqual(touch_capture.drawing(self.tc0, self.project, self.place), [])
        self.assertEqual(touch_capture.load_start(self.tc0, self.project, self.place, {}),
                         [b"\x09\x16\x041"])

    def test_its_load_block_on_k(self):
        # K numbers the command 0x18 in table 4, as it does a slider's, where
        # T has 0x16. Its ID is written as on T.
        project = probe_facts(probe_named("touch-capture-two"), "K")
        self.assertEqual(touch_capture.load_start(project.pages[0].objects[1], project,
                                                  self.place, {}), [b"\x09\x18\x041"])

    def test_its_memory(self):
        # Its val, 1 byte, then three 0 bytes: 0 at its default, and 5 for
        # tc1, as the Nextion Editor wrote them.
        tc1 = self.project.pages[0].objects[2]
        self.assertEqual(touch_capture.memory(self.tc0, self.project), bytes(4))
        self.assertEqual(touch_capture.memory(tc1, self.project), b"\x05\x00\x00\x00")

    def test_its_entries(self):
        # Its val, entry 7, at its base, highest 65535, of code 0x121. Of its
        # 10 entries, only its type, ID, vscope, and val are filled: it has
        # no place or size.
        data = touch_capture.data(self.tc0, self.project, self.place)
        self.assertEqual(len(data), 24 * 10)
        self.assertEqual(struct.unpack_from("<IiiiII", data, 24 * 7)[1:], (28, 0xFFFF, 0, 0x100,
                                                                           0x121))
        filled = [number for number in range(10) if any(data[24 * number:24 * number + 24])]
        self.assertEqual(filled, [0, 1, 3, 7])


class PiecesTest(TypePieces, CodePieces, unittest.TestCase):
    """Each touch capture of each probe that keeps its whole user code, at
    its type's functions, and each probe of code, at the statement encoder,
    against the probe's pieces (tests/tft/t_components.py)."""

    TYPE = "touch-capture"
    PROBES = touch_capture_probes.PROBES
    COUNT = 4
    CODE_COUNT = 1


class PPiecesTest(PTypePieces, CodePieces, unittest.TestCase):
    """Each touch capture of each of its probes on P that keeps its whole user
    code, at its type's functions on P, and each probe of code, against the
    probe's pieces (tests/tft/p_components.py)."""

    TYPE = "touch-capture"
    PROBES = [probe for probe in p_probes.PROBES if probe.name.startswith("p-touch-capture-")]
    COUNT = 4
    CODE_COUNT = 1


class MatchedTest(unittest.TestCase):
    """The needs touch_capture.MATCHED covers (matching.py)."""

    def test_what_it_covers(self):
        covered = [Need("type", "touch-capture"),
                   Need("attribute", "touch-capture.objname", b"tc0"),
                   Need("attribute", "touch-capture.val", b"\xff")]
        self.assertEqual(unmatched(covered, touch_capture.MATCHED), [])

    def test_what_it_leaves_out(self):
        left = [Need("attribute", "touch-capture.vscope", b"\x01")]
        self.assertEqual(unmatched(left, touch_capture.MATCHED), left)

    def test_it_is_matched_on_k(self):
        # Its probes matched on K too (k_probes.py).
        project = probe_project(probe_named("touch-capture-two"), series="K")
        self.assertEqual(unmatched(project_needs(project), matched_rules()), [])


class CodeTest(unittest.TestCase):
    """Code may read a touch capture's val, but not set it, and any other
    attribute it writes."""

    @classmethod
    def setUpClass(cls):
        cls.project = probe_facts(probe_named("touch-capture-two"))

    def test_its_val(self):
        # tc0's first entry is 33, and its val's entry 7 within the type.
        self.assertEqual(encode_line("sys0=tc0.val", CodePlace(0, "page0", "up"),
                                     CompileContext(self.project)),
                         b"\x05\x00\x00\x00\x00=\x01" + struct.pack("<I", 40))

    def test_its_other_attributes(self):
        # Any attribute it writes, such as its vscope, entry 3 within the type,
        # after tc0's first entry, 33; but not one it does not write.
        place_in_code = CodePlace(0, "page0", "up")
        self.assertEqual(encode_line("sys0=tc0.vscope", place_in_code,
                                     CompileContext(self.project)),
                         b"\x05\x00\x00\x00\x00=\x01" + (33 + 3).to_bytes(4, "little"))
        with self.assertRaisesRegex(StatementError, "tc0's x is not encoded"):
            encode_line("sys0=tc0.x", place_in_code, CompileContext(self.project))

    def test_the_check_lets_its_val_through(self):
        project = probe_project(probe_named("touch-capture-val-in-code"))
        self.assertEqual(unmatched(project_needs(project), matched_rules()), [])

    def test_the_check_refuses_setting_its_val(self):
        # Code cannot change a touch capture's val: the Nextion Editor
        # refuses a line that sets it, as nxwright's build does.
        page = line_context(touch_capture_probes.touch_capture_component())
        rules = matched_rules()
        for line in ("tc0.val=3", "tc0.val++", "for(tc0.val=0;sys0<1;sys0++)"):
            with self.subTest(line):
                need = Need("code", "event", line, context=page)
                self.assertEqual(unmatched([need], rules), [need])


class OnPTest(unittest.TestCase):
    """On P: its memory's values, after the 28 bytes of its record's head it
    holds, which the frame writes, its val's entry, and its load section's
    block."""

    def test_its_memory_and_val_s_entry(self):
        # A touch capture of val 255, at p-touch-capture-two's first one's
        # place: its val, 255, and three 0 bytes. Its val's entry, its entry
        # 7, gives the place 28 past its base, and the highest 65535.
        tc0 = page(touch_capture_probes.touch_capture_component(val=255),
                   series="P").objects[1]
        place_of_tc0 = place(p_probe_named("p-touch-capture-two"), "page0-1")
        self.assertEqual(p_values(tc0, place_of_tc0), b"\xff\x00\x00\x00")
        self.assertEqual(struct.unpack_from("<iii", p_entries(tc0, place_of_tc0), 7 * 24 + 4),
                         (place_of_tc0.base + 28, 0xFFFF, 0))

    def test_its_load_block(self):
        # `init` and its ID, in place of the slider's command.
        probe = p_probe_named("p-touch-capture-two")
        project = probe_facts(probe)
        self.assertEqual(touch_capture.load_start(project.pages[0].objects[1], project,
                                                  place(probe, "page0-1"), {}),
                         [b"\x09\x1f\x04" + b"1"])

    def test_it_is_matched_on_p_and_e(self):
        for series in ("P", "E"):
            with self.subTest(series):
                self.assertEqual(unmatched([Need("type", "touch-capture", series=series)],
                                           matched_rules()), [])


if __name__ == "__main__":
    unittest.main()
