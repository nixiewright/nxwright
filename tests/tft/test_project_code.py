"""The code a Project keeps (tft/project.py): program.s, each event's, and
each macro's, cleaned once, as the Project is made, so that no reader of it
sees a comment after code, an indentation, or a blank line. A line of a
comment alone stays.

Each test makes its Project in memory (tests/tft/unit_inputs.py), as nxwright's
build gives its code, in strict Nextion syntax, which keeps each line as
written.
"""
from dataclasses import replace
import unittest

from nxwright.project.page_block import Event

from tools.tft.probing.macro_probes import macros_text
from tools.tft.probing.statement_probes import touch_release_code
from tests.tft.unit_inputs import page, project_of

# Lines with a comment after their code, as the Nextion Editor stores
# them, of which the first has commas in its comment, as a new project's
# first line of program.s does; then a comment alone and a blank line.
_LINES = ("  sys0=1 // a, b, c", "// a comment alone", "", "sys1=2\t//x")
_CLEAN = ["sys0=1", "// a comment alone", "sys1=2"]


class ProjectCodeTest(unittest.TestCase):

    @staticmethod
    def _program_lines(project) -> list:
        return project.codec.decode_keeping_bytes(project.program).split("\n")

    def test_program_s_is_kept_clean(self):
        lines = self._program_lines(project_of(program=_LINES, strict=True))
        at = lines.index(_CLEAN[0])
        self.assertEqual(lines[at:at + len(_CLEAN)], _CLEAN)
        self.assertFalse([line for line in lines if line != line.strip(" \t\r")])

    def test_each_event_is_kept_clean(self):
        project = project_of(page(code=touch_release_code(list(_LINES)), strict=True),
                             strict=True)
        events = [item for item in project.pages[0].objects[0].items
                  if isinstance(item, Event) and item.lines]
        self.assertEqual(len(events), 1)
        text = [project.codec.decode_keeping_bytes(line) for line in events[0].lines]
        self.assertEqual(text, _CLEAN)

    def test_an_event_of_blank_lines_alone_keeps_none(self):
        made = page(code=touch_release_code(["sys0=1"]), strict=True)
        named = [item.name for item in made.objects[0].items
                 if isinstance(item, Event) and item.lines]
        self.assertEqual(len(named), 1)
        made = replace(made, objects=[replace(page_object, items=[
            replace(item, lines=[b"  ", b"\t", b""]) if isinstance(item, Event) and item.lines
            else item for item in page_object.items]) for page_object in made.objects])
        project = project_of(made, strict=True)
        self.assertEqual([item.lines for item in project.pages[0].objects[0].items
                          if isinstance(item, Event) and item.name == named[0]], [[]])

    def test_each_macro_is_kept_clean(self):
        project = project_of(macros=macros_text([("m0", list(_LINES) + ["return"])]),
                             strict=True)
        self.assertEqual(project.macros, [("m0", _CLEAN + ["return"])])

    def test_a_text_is_not_split_at_a_character_splitlines_splits_at(self):
        # U+0085, byte 0x85 in iso-8859-1, the base folder's encoding, which
        # str.splitlines would take for a line's end.
        project = project_of(program=('t0.txt="\x85" // y',), strict=True)
        self.assertEqual(project.settings.encoding, "iso-8859-1")
        self.assertIn('t0.txt="\x85"', self._program_lines(project))


if __name__ == "__main__":
    unittest.main()
