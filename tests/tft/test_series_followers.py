"""The follower series, F and K beside T and E beside P
(tft/series_differences.py): each gets its leader's coverage, the same
unit tests on its own series, with the leader's pieces, as the table of
differences changes them, as their expected bytes.

A follower's probe makes the same change as its leader's
(tests/tft/series_probe_pairs.py). Each test gives the function it checks the
follower's own input: the probe's pages made in memory on the follower's
series, in a Project of the facts it reads, and each component's place,
read from the leader's table, as the differences move no place
(tests/tft/unit_inputs.py). The pieces it covers are those the leader's own
unit tests compare: each component of a probe that keeps the whole user
code, at its type's functions; the blocks of each probe of code, at the
statement encoder; and the runs of code of each probe of labels and goto,
as the goto statement's test compares them (tests/tft/goto_pieces.py). The
probes a leader compares only whole, such as its whole compiles, are its
follower's samples too. Each difference row is exercised but the page's size,
which the frame writes in a page's record and memory; each follower's
sample of whole files compares its whole user code with its leader's
(tests/tft/test_whole_files.py).
"""
import unittest

from nxwright.tft.compile_context import CompileContext
from nxwright.tft import overlaps
from nxwright.tft.component_types import object_module, place_and_size, type_name
from tools.tft.probing.statement_probes import kept_blocks, ours_in_event, ours_in_program
from nxwright.tft.series_differences import DIFFERENCES
from nxwright.tft.tft_file import UserCode, encode_blocks
from tests.tft import goto_pieces
from tests.tft.p_components import p_entries, p_values
from tests.tft.series_comparison import (compare_user_code, difference_rows, entries_piece,
                                     instruction_piece)
from tests.tft.series_probe_pairs import paired_probes
from tests.tft.t_components import (keeps_its_user_code, made_in_memory, t_drawing, t_entries,
                                t_memory, t_scratch_tail)
from tests.tft.unit_inputs import piece, piece_names, place, probe_facts, probe_project


def _background_fill(page_object, project, its_place) -> bytes:
    """Returns the component's background fill, then the refs of the drawn
    components over it (overlaps.ref_blocks), then the run's 0 word, as the
    piece page0-N-background-fill holds them."""
    page = project.pages[its_place.page]
    areas = {number: place_and_size(item) for number, item in enumerate(page.objects)
             if number and getattr(object_module(item), "DRAWN", True)}
    return encode_blocks(object_module(page_object).background_fill(page_object, project,
                                                                    its_place)
                         + overlaps.ref_blocks(CompileContext(project), areas,
                                               its_place.object_id) + [b""])


def _load(page_object, project, its_place) -> bytes:
    """Returns the blocks the component's type writes in its page's load
    section, as the piece page0-N-load holds them."""
    return encode_blocks(object_module(page_object).load_start(page_object, project, its_place,
                                                               {}))


# Each kind of a component's piece the leaders' unit tests compare, the
# type's function that writes it, and whether it is blocks, whose
# instruction tokens the differences change. On P and E, a component's
# drawing is its 0 word alone, and its memory's head is the frame's.
_KINDS = {
    "T": (("memory", t_memory, False), ("drawing", t_drawing, True),
          ("entries", t_entries, False), ("background-fill", _background_fill, True),
          ("load", _load, True)),
    "P": (("memory", lambda page_object, project, its_place: p_values(page_object, its_place,
                                                                      project), False),
          ("entries", lambda page_object, project, its_place: p_entries(page_object, its_place,
                                                                        project), False),
          ("load", _load, True)),
}


# The names of the probes of labels and goto that keep fixtures, as the goto
# statement's test takes them (tests/tft/test_goto_statement.py).
_GOTO_PREFIXES = ("goto-", "p-goto-")


def _of_code(probe) -> bool:
    """Whether `probe` is a probe of code a leader's unit tests compare at
    the statement encoder: its fixture the blocks of page0's Touch Release
    event or of program.s, its pages made in memory."""
    return (probe.fixtures is not None and (probe.kept or probe.ours) in (ours_in_event,
                                                                          ours_in_program)
            and made_in_memory(probe))


class FollowerTest(unittest.TestCase):
    """Each follower's components and probes of code, against its leader's
    pieces, as the follower's table of differences changes them."""

    # The pieces each follower compares, (components' pieces, probes of
    # code, pieces of the probes of labels and goto), as its leader's unit
    # tests compare them.
    COUNTS = {"F": (2710, 158, 73), "K": (2190, 157, 73), "E": (1666, 53, 7)}

    def assert_components(self, leader, follower, differences: dict, used: set) -> int:
        """Checks each component of `follower`'s pages at its type's
        functions on its series against `leader`'s pieces, and returns how
        many pieces it compared. On T's followers, each event's piece starts
        with the event's name and the blocks its type writes at its start, as
        a button sets its val, which the leader's tests compare
        (t_components.EventStartPieces); the code after them is the
        encoder's. A timer's blocks in its page's load section on T give a
        place in its record, which the frame writes, so they are left to the
        frame's tests and the samples."""
        project = probe_facts(follower)
        kept = piece_names(leader)
        compared = 0
        for number, made in enumerate(project.pages):
            for object_id, page_object in enumerate(made.objects[1:], 1):
                name = "page%d-%d" % (number, object_id)
                its_place = place(leader, name)
                for kind, function, blocks in _KINDS[leader.base]:
                    wanted = "%s-%s" % (name, kind)
                    if wanted not in kept or (kind == "load" and leader.base == "T"
                                              and type_name(page_object) == "timer"):
                        continue
                    with self.subTest(follower.name, piece=wanted):
                        expected = piece(leader, wanted)
                        if blocks:
                            expected = instruction_piece(expected, differences, used)
                        if kind == "entries":
                            expected = entries_piece(expected, page_object, differences, used)
                        found = function(page_object, project, its_place)
                        # The bytes that round a txt's room up to 4 are the
                        # frame's scratch image's, so both sides leave them
                        # out, as P's memory leaves out its head.
                        if kind == "memory" and leader.base == "T":
                            tail = t_scratch_tail(page_object)
                            found, expected = (found[:len(found) - tail],
                                               expected[:len(expected) - tail])
                        self.assertEqual(found, expected)
                    compared += 1
                module = object_module(page_object)
                if leader.base != "T" or not hasattr(module, "event_start"):
                    continue
                for event in module.EVENTS:
                    wanted = "%s-event-%s" % (name, event)
                    with self.subTest(follower.name, piece=wanted):
                        start = module.event_start(page_object, project, its_place, event)
                        self.assertTrue(instruction_piece(piece(leader, wanted), differences,
                                                          used).startswith(
                            encode_blocks([event.encode("ascii")] + start)))
                    compared += 1
        return compared

    def assert_code(self, leader, follower, differences: dict, used: set):
        """Checks the encoder's blocks of `follower`'s lines, on its pages and
        program.s made in memory, against `leader`'s pieces, each of whose
        blocks as the differences change it. The leader's kind gives which
        lines: page0's Touch Release event's, or program.s's."""
        with self.subTest(follower.name):
            self.assertEqual(kept_blocks(leader, probe_project(follower)),
                             {name: instruction_piece(piece(leader, name), differences, used)
                              for name in piece_names(leader)})

    def assert_goto(self, leader, follower, differences: dict, used: set) -> int:
        """Checks the runs of code of `follower`, a probe of labels and goto,
        on its pages and program.s made in memory, against `leader`'s pieces,
        as the goto statement's own test does (tests/tft/goto_pieces.py), and
        returns how many pieces it compared. Each run starts where the
        leader's table gives it."""
        project = probe_facts(follower)
        with self.subTest(follower.name, piece="program-s"):
            self.assertTrue(instruction_piece(piece(leader, "program-s"), differences, used)
                            .startswith(goto_pieces.program_s(leader, project)))
        compared = 1
        for name, data in {**goto_pieces.event_pieces(leader, project),
                           **goto_pieces.load_pieces(leader, project)}.items():
            with self.subTest(follower.name, piece=name):
                self.assertEqual(instruction_piece(piece(leader, name), differences, used), data)
            compared += 1
        return compared

    def test_each_follower(self):
        for series, (components, code, goto) in self.COUNTS.items():
            differences = DIFFERENCES[series]
            used = set()
            counted = [0, 0, 0]
            for leader, follower in paired_probes(series):
                if keeps_its_user_code(leader):
                    counted[0] += self.assert_components(leader, follower, differences, used)
                elif _of_code(leader):
                    self.assert_code(leader, follower, differences, used)
                    counted[1] += 1
                elif leader.name.startswith(_GOTO_PREFIXES):
                    counted[2] += self.assert_goto(leader, follower, differences, used)
            with self.subTest(series=series, coverage="pieces"):
                self.assertEqual(tuple(counted), (components, code, goto))
            with self.subTest(series=series, coverage="difference rows"):
                left = {row for row in difference_rows(differences) - used
                        if row[0] != "page_size"}
                self.assertEqual(left, set())


class PieceTest(unittest.TestCase):
    """The pieces of a leader as a follower writes them
    (series_comparison.instruction_piece, entries_piece)."""

    def test_a_command_s_number(self):
        # K numbers zstr 0x15 where T has 0x13, in table 4; the rest of its
        # block stays.
        row = next(row for row in DIFFERENCES["K"]["commands"] if row[0] == "zstr")
        _, table, before, after = row
        used = set()
        piece_of_t = encode_blocks([bytes((9, before, table)) + b"10,10", b""])
        self.assertEqual(instruction_piece(piece_of_t, DIFFERENCES["K"], used),
                         encode_blocks([bytes((9, after, table)) + b"10,10", b""]))
        self.assertEqual(used, {("commands", row)})

    def test_tokens_inside_a_number_or_text_are_not_translated(self):
        # The payload resembles baud's operand but is not an operand token.
        for block in (b'\x05\x00\x00\x00\x00="\x04\x04\x0e\x00\x00"',
                      b'\x05\x00\x00\x00\x00=\x03\x04\x04\x0e\x00'):
            with self.subTest(block=block):
                used = set()
                self.assertEqual(instruction_piece(encode_blocks([block]), DIFFERENCES["K"],
                                                   used), encode_blocks([block]))
                self.assertEqual(used, set())
                compare_user_code(UserCode([b"", block], b"", b"", b"", b"", b""),
                                  UserCode([b"", block], b"", b"", b"", b"", b""), "K")

    def test_a_piece_that_is_not_blocks_is_refused(self):
        with self.assertRaisesRegex(AssertionError, "not blocks"):
            instruction_piece(b"\x09\x00\x00\x00ab", DIFFERENCES["K"], set())


if __name__ == "__main__":
    unittest.main()
