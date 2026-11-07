"""Labels and goto (tft/instructions/goto_statement.py and
tft/label_numbers.py): the blocks of each probe's runs of code, the
numbers the counter gives the "S " blocks, the blocks written once their
places are known, and what the rule covers.

Each test gives the function it checks its own input: a probe's pages and
program.s, made in memory from what its change adds
(tools/tft/probing/goto_probes.py), in a Project of the facts it reads, and
where a run of code starts, read from the probe's table
(tests/tft/unit_inputs.py). Its expected bytes are the probe's pieces, which the
probe runner wrote once each probe matched the Nextion Editor's file. One
probe on each series is compared whole in tests/tft/test_whole_files.py.
"""
import unittest

from nxwright.tft.compile_context import CompileContext
from nxwright.tft import label_numbers
from tools.tft.probing import goto_probes, p_probes
from nxwright.tft.component_types import value_operand
from nxwright.tft.instructions import goto_statement
from nxwright.tft.label_numbers import GotoBlock, LabelBlock
from nxwright.tft.matching import Need
from nxwright.tft.statements import CodePlace, StatementError, encode_code
from tests.tft import goto_pieces
from tests.tft.unit_inputs import piece, probe_facts, project_of


def facts(probe_name: str, series: str = None):
    """Returns the Project of facts of the probe `probe_name`'s pages, on
    `series`, unless given its own."""
    return probe_facts(next(probe for probe in goto_probes.PROBES if probe.name == probe_name),
                       series)


class PiecesTest(unittest.TestCase):
    """The blocks of each run of code of each probe that keeps fixtures, on T
    and on P, against the probe's pieces: program.s's lines and each event's,
    through the statement encoder, their labels and gotos written
    (label_numbers.resolved). Their numbers start where the counter gives
    them (label_numbers.numbers), and their places where the run starts,
    read from the probe's table. An event's piece also holds its name, and
    the blocks its type writes at its start (event_start), such as a
    timer's "S " block. The blocks a timer or a scrolling text writes in its
    page's load section are compared too, as the labels shift their
    numbers. The probes' other pieces are left to their types' tests and to
    the frame's, such as the blocks the frame appends to program.s, and
    compared until then by the sample."""

    PROBES = [probe for probe in goto_probes.PROBES + p_probes.PROBES
              if probe.fixtures and probe.name.startswith(("goto-", "p-goto-"))]

    def test_its_probes(self):
        self.assertEqual(len(self.PROBES), 8)

    def test_program_s(self):
        # program.s's blocks start the piece; the blocks the frame appends
        # follow them.
        for probe in self.PROBES:
            with self.subTest(probe.name):
                self.assertTrue(piece(probe, "program-s").startswith(
                    goto_pieces.program_s(probe, probe_facts(probe))))

    def test_each_event(self):
        # Each event's piece, its name, its type's blocks at its start, its
        # code's, and its 0 word (goto_pieces.event_pieces).
        compared = 0
        for probe in self.PROBES:
            for name, data in goto_pieces.event_pieces(probe, probe_facts(probe)).items():
                with self.subTest(probe.name, piece=name):
                    self.assertEqual(piece(probe, name), data)
                compared += 1
        self.assertEqual(compared, 66)

    def test_each_load_section(self):
        # The blocks a timer or a scrolling text writes in its page's load
        # section, at its type's function (goto_pieces.load_pieces).
        compared = 0
        for probe in self.PROBES:
            for name, data in goto_pieces.load_pieces(probe, probe_facts(probe)).items():
                with self.subTest(probe.name, piece=name):
                    self.assertEqual(piece(probe, name), data)
                compared += 1
        self.assertEqual(compared, 6)


class NumbersTest(unittest.TestCase):
    """The counter's numbers, as the Nextion Editor gave them in the probes."""

    def test_beside_a_timer_and_a_button(self):
        # tm0's first pass takes 0. The page's up event, of u1, starts at 1.
        # The text t0 has no code. tm0 takes its second, 2, then its timer
        # event's t1 and goto 3 and 4. b0's down event starts at 5 and its up
        # event at 7.
        numbers = label_numbers.numbers(facts("goto-beside-a-timer-and-a-button"))
        self.assertEqual(numbers.timers, {(0, 2): (0, 2)})
        self.assertEqual([numbers.events[0, name, event] for name, event in (
            ("page0", "up"), ("tm0", "timer"), ("b0", "down"), ("b0", "up"))], [1, 3, 5, 7])

    def test_load_loadend_and_a_second_page(self):
        # page0's load and loadend come before its up event, of u1 and its
        # goto; then tm0's second, 5. page1 goes on from 6: tm1's first, its
        # up event's p1, then tm1's second.
        numbers = label_numbers.numbers(facts("goto-in-load-loadend-and-a-second-page"))
        self.assertEqual(numbers.timers, {(0, 2): (0, 5), (1, 2): (6, 8)})
        self.assertEqual([numbers.events[0, "page0", event] for event in ("load", "loadend",
                                                                          "up")], [1, 2, 3])
        self.assertEqual(numbers.events[1, "page1", "up"], 7)

    def test_on_p_a_timer_takes_none(self):
        # On P, a timer's timer event has no "S " block, and the timer takes
        # no numbers. Beside a timer and a button, u1 takes 0, tm0's t1 and
        # goto 1 and 2, and b0's down event starts at 3 and its up event at
        # 5. With a timer on each of two pages, page0's load, loadend, and up
        # events start at 0, 1, and 2, and page1's up event at 4.
        numbers = label_numbers.numbers(facts("goto-beside-a-timer-and-a-button", "P"))
        self.assertEqual(numbers.timers, {})
        self.assertEqual([numbers.events[0, name, event] for name, event in (
            ("page0", "up"), ("tm0", "timer"), ("b0", "down"), ("b0", "up"))], [0, 1, 3, 5])
        numbers = label_numbers.numbers(facts("goto-in-load-loadend-and-a-second-page", "P"))
        self.assertEqual([numbers.events[0, "page0", event] for event in ("load", "loadend",
                                                                          "up")], [0, 1, 2])
        self.assertEqual(numbers.events[1, "page1", "up"], 4)

    def test_program_s_comes_first(self):
        # program.s's goto and label take 0 and 1, so page0's down starts
        # at 2, its up, after down's three, at 5, and its unload, after up's
        # four, at 9.
        numbers = label_numbers.numbers(facts("goto-across-program-and-events"))
        self.assertEqual(numbers.events[None, None, None], 0)
        self.assertEqual([numbers.events[0, "page0", event] for event in ("down", "up",
                                                                          "unload")], [2, 5, 9])


class ResolvedTest(unittest.TestCase):

    def test_labels_and_gotos_written(self):
        # A label's block is "S " and its number; a goto's "G " and the place
        # of the block after its label's, each block with its 4-byte size.
        blocks = [LabelBlock("a"), b"\x05\x00\x00\x00\x00=1", GotoBlock("a"), GotoBlock("b"),
                  LabelBlock("b")]
        self.assertEqual(label_numbers.resolved(blocks, 7, 100), [
            b"S " + value_operand(7), b"\x05\x00\x00\x00\x00=1", b"G " + value_operand(111),
            b"G " + value_operand(155), b"S " + value_operand(10)])

    def test_a_goto_without_its_label(self):
        with self.assertRaisesRegex(StatementError, "no label b"):
            label_numbers.resolved([GotoBlock("b")], 0, 0)

    def test_other_blocks_unchanged(self):
        self.assertEqual(label_numbers.resolved([b"x", b""], 3, 50), [b"x", b""])


class EncodeTest(unittest.TestCase):

    def test_labels_and_gotos_unwritten(self):
        # The encoder gives each unwritten, of the right size, in the body of
        # an if too.
        blocks = encode_code(["a:", "if(sys0==1)", "{", "goto a", "}"], CodePlace(),
                             CompileContext(project_of()))
        self.assertIsInstance(blocks[0], LabelBlock)
        self.assertEqual(blocks[0].label, "a")
        self.assertIsInstance(blocks[2], GotoBlock)
        self.assertEqual(blocks[2].label, "a")
        self.assertEqual([len(blocks[0]), len(blocks[2])], [7, 7])

    def test_on_f_as_on_t(self):
        # F writes labels and gotos as T does (ResearchNotes/tft/f-series.md).
        lines = ["a:", "if(sys0==1)", "{", "goto a", "}"]
        project = project_of()

        def written(blocks: list) -> list:
            return [(bytes(block), getattr(block, "label", None)) for block in blocks]
        self.assertEqual(written(encode_code(lines, CodePlace(),
                                             CompileContext(project_of(series="F")))),
                         written(encode_code(lines, CodePlace(), CompileContext(project))))


class MatchedTest(unittest.TestCase):

    def test_the_rule(self):
        rule, = goto_statement.MATCHED
        # A name of any length. nxwright's build refuses a line longer than
        # its series takes, 767 bytes on T and 4095 on P.
        for line in ("loop:", "goto loop", "_x9:", "  goto _x9", "a" * 31 + ":",
                     "a" * 766 + ":", "goto " + "a" * 762, "a" * 767 + ":", "goto " + "a" * 4090):
            with self.subTest(line[:40]):
                self.assertTrue(rule.matches(Need("code", "event", line)))
        # A name with other characters, and a line of another kind.
        for line in ("goto a b", "a!:", "sys0=1", "gotoloop"):
            with self.subTest(line):
                self.assertFalse(rule.matches(Need("code", "event", line)))


if __name__ == "__main__":
    unittest.main()
