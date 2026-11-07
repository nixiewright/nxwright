"""The timer component (tft/component_types/timer.py): its memory, its
entries, the blocks the Nextion Editor writes of its own for each timer,
what its list matched, which of its attributes code may use, and its memory,
entries, and load section on P.

Each test gives the function it checks that function's own input: a page
object of a probe's components (tools/tft/probing/timer_probes.py), made by
nxwright's page reader, a Project of the facts it reads, and the object's
place, read from the probe's table (tests/tft/unit_inputs.py). It compares the
result with one piece of the probe's fixtures, which the probe runner wrote
once the probe matched the Nextion Editor's file. Each probe that keeps
fixtures is compared so, on T and on P (tests/tft/t_components.py,
tests/tft/p_components.py). What the frame writes across objects, such as a
timer's record, the head of its memory on P, and, on T, the place in its
load section of its timer event's code, is left to the frame's tests, and
compared until then by the sample of whole files (tests/tft/test_whole_files.py).
"""
import unittest

from nxwright.tft.compile_context import CompileContext
from nxwright.tft.component_types import timer
from nxwright.tft.matching import Need, matched_rules, project_needs, unmatched
from tools.tft.probing import p_probes, timer_probes
from tools.tft.probing.statement_probes import touch_release_code
from nxwright.tft.statements import CodePlace, StatementError, encode_line
from tests.tft.p_components import PTypePieces
from tests.tft.t_components import CodePieces, EventStartPieces, LoadSectionPieces, TypePieces
from tests.tft.unit_inputs import page, page_of, place, project_of

# The probes of a timer that keep fixtures on P.
_P_PROBES = [probe for probe in p_probes.PROBES if probe.name.startswith("p-timer-")]


def value(number: int, size: int = 2) -> bytes:
    return number.to_bytes(size, "little", signed=True)


def _probe(name: str):
    return next(probe for probe in timer_probes.PROBES if probe.name == name)


class PiecesTest(TypePieces, CodePieces, EventStartPieces, unittest.TestCase):
    """Each timer of each probe that keeps its whole user code, at its type's
    functions, its timer event's "S " block among them, and its probe of
    code, at the statement encoder, against the probe's pieces: two timers
    on a page, one among a text, a number, a button, and a variable, timers
    on two pages, whose "S " numbers count the first page's, and timers with
    code in their timer events. A timer's drawing is a 0 word alone."""

    TYPE = "timer"
    PROBES = timer_probes.PROBES
    COUNT = 8
    CODE_COUNT = 1
    EVENTS = ("timer",)


class PPiecesTest(PTypePieces, CodePieces, LoadSectionPieces, unittest.TestCase):
    """Each timer of each of its probes on P that keeps its whole user code,
    at its type's functions on P, against the probe's pieces: its values
    after the 28 bytes of its record's head its memory starts with
    (P_HEAD_SIZE), its tim, its en, and a 0 byte; its entries, its tim's
    giving its place and the top byte 1, its en's its place and 2; and its
    block in its page's load section, `init` and its ID."""

    TYPE = "timer"
    PROBES = _P_PROBES
    COUNT = 8
    CODE_COUNT = 1


class MemoryTest(unittest.TestCase):
    """A timer's starting memory: its tim, 2 bytes, its en, then a 0 byte."""

    def test_its_tim_and_en(self):
        for component, memory in ((timer_probes.timer_component(), b"\x90\x01\x01\x00"),
                                  (timer_probes.timer_component(tim=1000, en=0),
                                   b"\xe8\x03\x00\x00")):
            with self.subTest(memory.hex(" ")):
                self.assertEqual(timer.memory(page(component).objects[1], None), memory)


class LoadSectionTest(unittest.TestCase):
    """The blocks a timer adds to its page's load section on T and K: timerset
    with its en, its ID, and its tim, then the "L " block with the place of
    its timer event's code. That place is the frame's, so the test states
    one, 234, as the frame gives it to the type (its record's places)."""

    def test_its_load_section_s_blocks(self):
        # tm0 is page0's first component: its first entry is 33, so its tim's
        # is 40 and its en's 41. Its code follows its 11-byte "S " block. K
        # numbers timerset 0x23 in table 8, where T has 0x22; its operands
        # and the "L " block are T's.
        probe = _probe("timer-two")
        tm0_place = place(probe, "page0-1")
        for series, command in (("T", 0x22), ("K", 0x23)):
            with self.subTest(series):
                made = page_of(probe, series=series)
                blocks = timer.load_start(made.objects[1], project_of(made, series=series),
                                          tm0_place, {"timer": 234})
                self.assertEqual(blocks, [bytes([0x09, command, 0x08])
                                          + b"\x01\x29\x00\x00\x00,1,\x01\x28\x00\x00\x00,0",
                                          b"L \x03" + value(245, 4)])


class MatchedTest(unittest.TestCase):
    """The needs timer.MATCHED covers (matching.py)."""

    def test_what_it_covers(self):
        covered = [Need("type", "timer"), Need("attribute", "timer.objname", b"tm0"),
                   Need("attribute", "timer.tim", value(50)),
                   Need("attribute", "timer.tim", (65534).to_bytes(2, "little")),
                   Need("attribute", "timer.en", value(0, 1)),
                   Need("attribute", "timer.en", value(1, 1))]
        self.assertEqual(unmatched(covered, timer.MATCHED), [])

    def test_it_is_matched_on_k(self):
        # Its probes matched on K too (k_probes.py): the needs of a page of a
        # timer on K.
        project = project_of(page(timer_probes.timer_component(), series="K"), series="K",
                             fonts=0)
        self.assertEqual(unmatched(project_needs(project), matched_rules()), [])

    def test_what_it_leaves_out(self):
        # Any tim and any en that fit in their bytes are taken, so only a
        # vscope is left out.
        left = [Need("attribute", "timer.vscope", value(1, 1))]
        self.assertEqual(unmatched(left, timer.MATCHED), left)


class CodeTest(unittest.TestCase):
    """Code may use a timer's tim and en, and any other attribute it writes.
    The encoder reads the page's components."""

    @classmethod
    def setUpClass(cls):
        cls.project = project_of(page(timer_probes.timer_component()))

    def test_its_tim_and_en(self):
        place_of_line = CodePlace(0, "page0", "up")
        self.assertEqual(encode_line("tm0.tim=100", place_of_line, CompileContext(self.project)),
                         b"\x01\x28\x00\x00\x00=100")
        self.assertEqual(encode_line("tm0.en=0", place_of_line, CompileContext(self.project)),
                         b"\x01\x29\x00\x00\x00=0")

    def test_its_other_attributes(self):
        # Any attribute it writes, such as its vscope, entry 3 within the type,
        # after tm0's first entry, 33; but not one it does not write.
        place_of_line = CodePlace(0, "page0", "up")
        self.assertEqual(encode_line("sys0=tm0.vscope", place_of_line,
                                     CompileContext(self.project)),
                         b"\x05\x00\x00\x00\x00=\x01" + (33 + 3).to_bytes(4, "little"))
        with self.assertRaisesRegex(StatementError, "tm0's x is not encoded"):
            encode_line("sys0=tm0.x", place_of_line, CompileContext(self.project))

    def test_the_check_lets_them_through(self):
        # The needs of a page of a timer, its tim and en in code.
        made = page(timer_probes.timer_component(), strict=True, code=touch_release_code(
            ["tm0.en=0", "sys0=tm0.tim", "if(tm0.en==1)", "{", "}", "vis tm0,0"]))
        self.assertEqual(unmatched(project_needs(project_of(made, strict=True, fonts=0)),
                                   matched_rules()), [])


class OnPTest(unittest.TestCase):
    """What the check matches on P and E."""

    def test_it_is_matched_on_p_and_e(self):
        for series in ("P", "E"):
            with self.subTest(series):
                self.assertEqual(unmatched([Need("type", "timer", series=series)],
                                           matched_rules()), [])


if __name__ == "__main__":
    unittest.main()
