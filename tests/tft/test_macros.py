"""Macros, call, and return (tft/instructions/call_statement.py,
frame._macros, and label_numbers.py): the macros' blocks and table, the
counter's numbers, the blocks of call and return, the reader's parts, what
the frame refuses, and what the rules cover.

Each test gives the function it checks that function's own input: a
Project of the facts of a probe's page, program.s, and macros
(tools/tft/probing/macro_probes.py), made in memory as nxwright's build makes
them (tests/tft/unit_inputs.py). The probes that keep the whole user code are
compared with their pieces of the macros. What the packaging writes in
header 1 of the macros, and what the frame writes across objects, are
compared by the sample of whole files (tests/tft/test_whole_files.py).
"""
from dataclasses import replace
import struct
import unittest

from nxwright.tft.compile_context import CompileContext
from nxwright.tft import frame, label_numbers
from tools.tft.probing import code_form_probes, macro_probes
from nxwright.tft.component_types import value_operand
from nxwright.tft.frame import FrameError
from nxwright.tft.label_numbers import CallBlock
from nxwright.tft.matching import Need, matched_rules, project_needs, unmatched
from nxwright.tft.statements import CodePlace, StatementError, encode_code
from tools.tft.probing.frame_probes import stand_in_code
from nxwright.tft.tft_file import byte_form_crc, encode_blocks
from tests.tft.unit_inputs import blocks_place, piece, probe_facts, probe_project, project_of


def facts(probe_name: str, series: str = None):
    """Returns the Project of facts of the probe `probe_name`, on its series
    or on `series`."""
    return probe_facts(next(probe for probe in macro_probes.PROBES if probe.name == probe_name),
                        series)


def with_macros_block(project, block: bytes):
    """Returns `project` with the comcode.sn block `block` in place of its
    macros."""
    return replace(project, blocks={**project.blocks, "comcode.sn": block})


class PiecesTest(unittest.TestCase):
    """The macros and their table in each probe that keeps the whole user
    code, at the frame's function that writes them (frame._macros), against
    the probe's pieces: each macro, its "S " block, its lines' blocks, and
    its 0 word; and the table, each macro's name's CRC and the place of its
    "S " block, sorted by the CRC. The macros start where the probe's table
    gives the first one (unit_inputs.blocks_place). Their lines are written
    by the encoder the probes kept them with, which gives a made-up block
    for each line (frame_probes.stand_in_code), so the blocks of a call are
    compared at the statement encoder in EncodingTest. The probes' other
    pieces are their types' and the frame's, compared by the sample of whole
    files."""

    PROBES = [probe for probe in macro_probes.PROBES if probe.fixtures]

    def test_its_probes(self):
        self.assertEqual(len(self.PROBES), 3)

    def test_the_macros_and_their_table(self):
        compared = 0
        for probe in self.PROBES:
            project = probe_facts(probe)
            start = blocks_place(probe, "macro-0")
            blocks, _, table, spans = frame._macros(CompileContext(project), start,
                                                    stand_in_code)
            written = encode_blocks(blocks)
            for number, (name, first, end) in enumerate(spans):
                with self.subTest(probe.name, macro=name):
                    self.assertEqual(written[first - start:end - start],
                                     piece(probe, "macro-%d" % number))
                compared += 1
            with self.subTest(probe.name, piece="macros-table"):
                self.assertEqual(table, piece(probe, "macros-table"))
        # The four macros of one, the three of another, and the one of the
        # third.
        self.assertEqual(compared, 8)


class TableTest(unittest.TestCase):
    """The macros' table in nxwright's user code."""

    def test_the_table(self):
        # Sorted by the CRC of each name, each entry the place of its macro's
        # "S " block, which holds the macro's number in the tab's order.
        code = frame.user_code(facts("macros-sorted-by-crc"))
        crcs = [struct.unpack_from("<I", code.macros, at)[0]
                for at in range(0, len(code.macros), 8)]
        self.assertEqual(crcs, sorted(byte_form_crc(name.encode("ascii"))
                                      for name in ("delta", "alpha", "beta", "gamma")))
        self.assertEqual(crcs[0], byte_form_crc(b"gamma"))
        starts = {place: number for number, place in enumerate(code.block_places())}
        self.assertEqual([code.blocks[starts[place]] for place in code.macro_places()],
                         [b"S " + value_operand(number) for number in (3, 2, 1, 0)])

    def test_without_macros(self):
        self.assertEqual(frame.user_code(project_of()).macros, b"")


class NumbersTest(unittest.TestCase):

    def test_the_counter(self):
        # program.s's label and call take 0 and 1, then each macro its "S "
        # block's number and its labels' and gotos', then the event's call,
        # label, and goto.
        numbers = label_numbers.numbers(facts("macros-labels"))
        self.assertEqual(numbers.macros, {"m0": 2, "m1": 3, "m2": 6})
        self.assertEqual(numbers.events[0, "page0", "up"], 7)

    def test_the_counter_past_comments_and_indentation(self):
        # The macro m's "S " block takes 0, then its label and its indented
        # goto, each with a comment after it, take 1 and 2, so the event's
        # call takes 3.
        probe = next(probe for probe in code_form_probes.PROBES
                     if probe.name == "code-forms-in-a-macro")
        numbers = label_numbers.numbers(probe_facts(probe))
        self.assertEqual(numbers.macros, {"m": 0})
        self.assertEqual(numbers.events[0, "page0", "up"], 3)

    def test_a_call_s_line(self):
        self.assertEqual(label_numbers.call_of("call my name "), "my name")
        self.assertIsNone(label_numbers.call_of("call"))
        self.assertIsNone(label_numbers.call_of("sys0=1"))


class EncodingTest(unittest.TestCase):

    def test_call_and_return(self):
        # A call unwritten, then its macro's place once laid out; return a 0
        # word.
        project = facts("macros-called")
        blocks = encode_code(["call first", "return"], CodePlace(), CompileContext(project))
        self.assertIsInstance(blocks[0], CallBlock)
        self.assertEqual(blocks[1], b"")
        self.assertEqual(label_numbers.resolved(blocks, 0, 0, {"first": 0xa8}),
                         [b"J " + value_operand(0xa8), b""])
        with self.assertRaises(StatementError):
            label_numbers.resolved([CallBlock("none")], 0, 0, {"first": 0xa8})

    def test_on_p(self):
        # P writes the macros and their table as T does.
        self.assertEqual(len(frame.user_code(facts("macros-sorted-by-crc", "P")).macros), 32)

    def test_what_the_frame_refuses(self):
        # An int declaration in a macro.
        project = with_macros_block(project_of(), b"m0\r\n1\r\nint x=1\r\n")
        with self.assertRaisesRegex(FrameError, "int declaration"):
            frame.user_code(project)


class ReaderTest(unittest.TestCase):
    """The parts of nxwright's user code of macros, as the reader names them."""

    def test_the_parts(self):
        # program.s ends before the first macro, and the macros before page
        # 0, though a macro holds a 0 word for its return.
        code = frame.user_code(facts("macros-called"))
        parts = code.block_parts()
        starts = {place: number for number, place in enumerate(code.block_places())}
        first = min(starts[place] for place in code.macro_places())
        self.assertEqual(parts[first - 1], "program.s")
        self.assertEqual(set(parts[first:parts.index("page 0")]), {"macros"})


class MatchedTest(unittest.TestCase):

    def test_each_probe_s_project(self):
        # Every need of each probe's project is matched, as a compile checks
        # them.
        for probe in macro_probes.PROBES:
            with self.subTest(probe.name):
                self.assertEqual(unmatched(project_needs(probe_project(probe)), matched_rules()),
                                 [])

    def test_a_macro_s_lines(self):
        # A macro has no page, as program.s: a reference through the screen's
        # arrays must be p[i].b[j], and it declares no int.
        rules = matched_rules()

        def need(line: str) -> Need:
            return Need("code", "macro", line, context={"pages": ("page0",)}, series="T")
        for line in ('p[0].b[1].txt="a"', "call m0", "return", "sys0=0x10"):
            with self.subTest(line):
                self.assertEqual(unmatched([need(line)], rules), [])
        left = [need('b[1].txt="a"'), need("int x=1")]
        self.assertEqual(unmatched(left, rules), left)

    def test_on_f(self):
        # F takes a macro, a call, and a return, as T does.
        needs = [Need("macro", "m0", series="F"), Need("macro", "my name", series="F"),
                 Need("code", "macro", "return", context={}, series="F"),
                 Need("code", "event", "call m0", context={}, series="F")]
        self.assertEqual(unmatched(needs, matched_rules()), [])


if __name__ == "__main__":
    unittest.main()
