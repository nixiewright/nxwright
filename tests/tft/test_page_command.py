"""The `page` command (tft/statements.py): the encoder's blocks for the
probes that keep fixtures, the block of each form of its argument, and what
its rule covers.

The fixtures are the blocks of page0's Touch Release event, or of program.s,
as the statement encoder gave them once each probe matched the Nextion
Editor's file (tools/tft/probing/page_command_probes.py).

Each test gives the encoder its own input: a probe's page and program.s,
made in memory from what the probe adds, or the base folder's facts, in a
Project of the facts the encoder reads (tests/tft/unit_inputs.py).
"""
import unittest

from nxwright.tft.compile_context import CompileContext
from tools.tft.probing import p_probes, page_command_probes
from nxwright.tft.matching import Need, matched_rules, project_needs, unmatched
from tools.tft.probing.number_probes import number_component
from nxwright.tft.statements import MATCHED, CodePlace, StatementError, encode_line
from tools.tft.probing.text_probes import text_component
from tools.tft.probing.statement_probes import kept_blocks
from tests.tft.line_context import line_context
from tests.tft.unit_inputs import piece, piece_names, probe_project

_PAGE = b"\x09\x0b\x04"


def facts(probe_name: str):
    """Returns the Project of facts of the probe `probe_name`'s page and
    program.s, made in memory."""
    return probe_project(next(probe for probe in page_command_probes.PROBES
                              if probe.name == probe_name))


class FixtureTest(unittest.TestCase):
    """The encoder's blocks for each probe that keeps fixtures, on its page
    and program.s made in memory, against the probe's pieces: on T, and on
    P, which keeps the blocks of the same lines."""

    def test_each_part(self):
        probes = [probe for probe in page_command_probes.PROBES if probe.fixtures] + [
            probe for probe in p_probes.PROBES
            if probe.fixtures
            and probe.name in {"p-" + each.name for each in page_command_probes.PROBES}]
        self.assertEqual(len(probes), 6)
        for probe in probes:
            with self.subTest(probe.name):
                self.assertEqual(kept_blocks(probe, probe_project(probe)),
                                 {each: piece(probe, each) for each in piece_names(probe)})


class EncodeTest(unittest.TestCase):
    """The block of `page` with each form of its argument, in page0's Touch
    Release event of a project of the pages page0, page1, and settings."""

    @classmethod
    def setUpClass(cls):
        cls.project = facts("page-by-name")

    def encoded(self, line: str) -> bytes:
        return encode_line(line, CodePlace(0, "page0", "up"), CompileContext(self.project))

    def test_a_page_s_number_as_text(self):
        self.assertEqual(self.encoded("page 1"), _PAGE + b"1")
        self.assertEqual(self.encoded("page 255"), _PAGE + b"255")

    def test_a_page_s_name_as_written(self):
        self.assertEqual(self.encoded("page settings"), _PAGE + b"settings")
        self.assertEqual(self.encoded("page page0"), _PAGE + b"page0")

    def test_a_variable_as_its_operand(self):
        # sys0 is program.s's first int variable; dp the system variable.
        self.assertEqual(self.encoded("page sys0"), _PAGE + b"\x05\x00\x00\x00\x00")
        self.assertEqual(self.encoded("page dp"), _PAGE + b"\x04\x04\x00\x00\x00")

    def test_a_name_neither_a_page_nor_a_variable_is_refused(self):
        # The Nextion Editor refuses it too: "Invalid Page ID".
        with self.assertRaisesRegex(StatementError, "nosuch is no variable"):
            self.encoded("page nosuch")

    def test_other_numbers_as_any_number(self):
        # As the Nextion Editor wrote them on T and K: as typed up to 3
        # characters, and as 03 and the value past them, a hexadecimal
        # number however small.
        for line, block in (("page 256", "32 35 36"), ("page 1000", "03 e8 03 00 00"),
                            ("page 007", "30 30 37"), ("page 0007", "03 07 00 00 00"),
                            ("page -1", "2d 31"), ("page -1000", "03 18 fc ff ff"),
                            ("page 0x01", "03 01 00 00 00")):
            with self.subTest(line):
                self.assertEqual(self.encoded(line), _PAGE + bytes.fromhex(block))

    def test_a_value_as_an_assignment_s(self):
        # Operands joined by operators, spaces dropped, and a colour's name,
        # as the Nextion Editor wrote them on T and K.
        for line, block in (("page sys0 + 1", "05 00 00 00 00 2b 31"),
                            ("page 2*sys1-3", "32 2a 05 04 00 00 00 2d 33"),
                            ("page 0x0A+1", "03 0a 00 00 00 2b 31"),
                            ("page RED", "04 04 01 00 00")):
            with self.subTest(line):
                self.assertEqual(self.encoded(line), _PAGE + bytes.fromhex(block))

    def test_a_number_s_val(self):
        # In page-values, n0's val is entry 101 and n1's 142.
        project = facts("page-values")
        self.assertEqual(encode_line("page n0.val*n1.val", CodePlace(0, "page0", "up"),
                                     CompileContext(project)),
                         _PAGE + bytes.fromhex("01 65 00 00 00 2a 01 8e 00 00 00"))

    def test_a_txt_through_the_screen_s_arrays(self):
        # Written as any reference is, as `page b[2].val`: 09 0b 04, then the
        # reference as written (ResearchNotes/tft/statements.md).
        self.assertEqual(self.encoded("page b[1].txt"), _PAGE + b"b[1].txt")

    def test_what_is_no_value(self):
        # A text, which the Nextion Editor refused ("Invalid Page ID"), a
        # second argument ("Invalid number of arguments"), no argument, and
        # an operator without its operand.
        for line in ('page "a"', "page 1,2", "page", "page 1+"):
            with self.subTest(line), self.assertRaises(StatementError):
                self.encoded(line)


class MatchedTest(unittest.TestCase):
    """The `page` lines MATCHED covers (matching.py)."""

    def need(self, line: str) -> Need:
        return Need("code", "event", line)

    def test_what_it_covers(self):
        # A name may be a page's or a variable's, as the line does not tell.
        covered = [self.need(line) for line in
                   ("page 0", "page 7", "page 255", "page page1", "page sys0", "page dp",
                    "page 256", "page 007", "page -1000", "page 0x01", "page RED",
                    "page sys0 + 1", "page 2*sys1-3")]
        self.assertEqual(unmatched(covered, MATCHED), [])

    def test_a_number_s_val_in_an_event(self):
        page = line_context(text_component(), number_component(y=60))
        for line in ("page n0.val", "page n0.val+1"):
            with self.subTest(line):
                need = Need("code", "event", line, context=page)
                self.assertEqual(unmatched([need], MATCHED), [])

    def test_what_it_leaves_out(self):
        # A txt and a text, which the Nextion Editor refused ("Invalid Page
        # ID"); a second argument ("Invalid number of arguments"); and an
        # attribute in program.s without its page ("Invalid Page ID").
        page = line_context(text_component(), number_component(y=60))
        left = [Need("code", "event", "page t0.txt", context=page),
                self.need('page "a"'), self.need("page 1,2"),
                Need("code", "program.s", "page n0.val")]
        self.assertEqual(unmatched(left, MATCHED), left)

    def test_the_check_takes_every_probe(self):
        for probe in page_command_probes.PROBES:
            with self.subTest(probe=probe.name):
                project = probe_project(probe)
                self.assertEqual(unmatched(project_needs(project), matched_rules()), [])


if __name__ == "__main__":
    unittest.main()
