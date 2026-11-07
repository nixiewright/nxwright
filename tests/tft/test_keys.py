"""A component's key (tft/component_types.key_lines, and its rule in
tft/frame.py): the probe beside nxwright's keypad's components at their
types' functions, the lines a key adds and their blocks as the Nextion
Editor wrote them, a key whose keyboard page is missing, and what the rule
covers.

Each test gives the function it checks its own input: a probe's pages made
in memory, nxwright's keyboard page among them, in a Project of the facts
it reads, and each component's place, read from the probe's table
(tests/tft/unit_inputs.py). The probe is compared whole in
tests/tft/test_whole_files.py.
"""
from dataclasses import replace
import unittest

from nxwright.tft.compile_context import CompileContext
from nxwright.tft import frame, label_numbers
from tools.tft.probing import key_probes
from tools.tft.probing.frame_probes import stand_in_code
from nxwright.tft.component_types import key_lines
from nxwright.tft.matching import Need, code_lines, unmatched
from nxwright.tft.statements import CodePlace, StatementError, encode_code
from tools.tft.probing.text_probes import text_component
from nxwright.tft.tft_file import encode_blocks
from tests.tft.t_components import FillStartAndLoadPieces, TypePieces
from tests.tft.unit_inputs import page, piece, probe_facts, project_of

# A text with key 2, global as a key needs: the keypad's.
_KEYED_TEXT = text_component() + "vscope = 1\nkey = 2\n"


class PiecesTest(TypePieces, FillStartAndLoadPieces, unittest.TestCase):
    """Each component of the probe that keeps its whole user code, a keyed
    text beside nxwright's keypad, of every type, the keypad's among them,
    at its type's functions, against the probe's pieces: its memory, its
    drawing, its entries, its background fill, its events' start, and its
    blocks in the load section, on its pages made in memory
    (tests/tft/t_components.py)."""

    PROBES = key_probes.PROBES
    COUNT = 40
    FILL_COUNT = 20
    START_COUNT = 30
    LOAD_COUNT = 0


class LinesTest(unittest.TestCase):
    """The lines a key adds at the end of its component's Touch Release
    code, and their blocks."""

    def test_its_lines(self):
        made = page(_KEYED_TEXT)
        self.assertEqual(key_lines(made.objects[1], 1), ["keybdB.loadpageid.val=dp",
                                                         "keybdB.loadcmpid.val=1",
                                                         "page keybdB"])
        self.assertEqual(key_lines(made.objects[0], 0), [])

    def test_their_blocks_after_the_component_s_code(self):
        # The text's `sys0=7`, then loadpageid's val, entry 0x72, given dp,
        # then loadcmpid's, entry 0x7d, given 1, then `page keybdB`, as the
        # Nextion Editor wrote them beside nxwright's keypad. The probe kept
        # its user code through the stand-in encoder, so the text's piece of
        # its Touch Release event holds a stand-in block for each, after the
        # event's name, then a 0 word.
        probe = next(probe for probe in key_probes.PROBES
                     if probe.name == "key-text-on-the-keypad")
        project = probe_facts(probe)
        t0 = project.pages[0].objects[1]
        place = CodePlace(0, "t0", "up")
        blocks = (encode_code(code_lines(project, label_numbers.event_code(t0, "up")), place,
                              CompileContext(project))
                  + encode_code(key_lines(t0, 1), place, CompileContext(project)))
        self.assertEqual([block.hex(" ") for block in blocks],
                         ["05 00 00 00 00 3d 37", "01 72 00 00 00 3d 04 04 00 00 00",
                          "01 7d 00 00 00 3d 31", "09 0b 04 6b 65 79 62 64 42"])
        lines = code_lines(project, label_numbers.event_code(t0, "up")) + key_lines(t0, 1)
        self.assertEqual(piece(probe, "page0-1-event-up"),
                         encode_blocks([b"up"] + stand_in_code(lines, place, project) + [b""]))

    def test_a_missing_keyboard_page(self):
        # The key's lines name the page, which the project lacks.
        with self.assertRaisesRegex(StatementError, "no page keybdB"):
            frame.user_code(project_of(page(_KEYED_TEXT)))


class MatchedTest(unittest.TestCase):
    """The needs of the key's rule."""

    def need(self, subject: str, value: int, series: str = "T") -> Need:
        return Need("attribute", subject, bytes([value]), series=series)

    def test_what_it_covers(self):
        covered = [self.need("text.key", 0), self.need("number.key", 5),
                   self.need("text.key", 2), self.need("number.key", 1),
                   self.need("xfloat.key", 3), self.need("scrolling-text.key", 2),
                   self.need("text.key", 4), self.need("number.key", 4),
                   self.need("xfloat.key", 4), self.need("scrolling-text.key", 4)]
        covered += [replace(need, series=series) for need in covered for series in "KPEF"]
        self.assertEqual(unmatched(covered, frame.MATCHED), [])

    def test_what_it_leaves_out(self):
        # A type whose key no probe gave.
        left = [self.need("button.key", 2)]
        self.assertEqual(unmatched(left, frame.MATCHED), left)


if __name__ == "__main__":
    unittest.main()
