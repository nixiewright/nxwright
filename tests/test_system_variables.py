"""The Editor's system variables are listed once, in
editor_language.EDITOR_SYSTEM_VARIABLES, which nxlang, the build's names
check, and the editing help read. The extension's grammar, which cannot
read it, colours the same names: this test keeps the two alike. So are
the Editor's commands, in editor_language.EDITOR_COMMANDS, which the
grammar colours, and among which every command the build, the series'
checks, and the test machine know must be."""
import json
from pathlib import Path
import re
import unittest

from nxwright.language.code_checks import COMMAND_PARAMETERS
from nxwright.project.editor_language import (EDITOR_COMMANDS, EDITOR_SYSTEM_VARIABLES,
                                              SERIES_LACKED_COMMANDS)
from nxwright.testing.editor_machine import RECORDED_ONLY

GRAMMAR = (Path(__file__).resolve().parents[1] / "editors" / "vscode" / "syntaxes"
           / "nxwright.tmLanguage.json")
# Names close to the system variables that are none of them, as the probe of
# the names the Editor refuses found: another case, another number, sys0 to
# sys2, and eqlb, which nxwright once listed.
_NEAR_MISSES = ("DIM", "dim1", "rtc7", "pio8", "pwm3", "tch4", "eq10", "sya2", "audio2",
                "sys0", "sys1", "sys2", "eqlb")


class GrammarTest(unittest.TestCase):

    def test_the_grammar_colours_the_editors_system_variables(self):
        rule = json.loads(GRAMMAR.read_text(encoding="utf-8"))["repository"]["system-variable"]
        pattern = re.compile(rule["match"])
        coloured = {name for name in EDITOR_SYSTEM_VARIABLES | set(_NEAR_MISSES)
                    if pattern.fullmatch(name)}
        self.assertEqual(coloured, EDITOR_SYSTEM_VARIABLES)

    def test_the_grammar_colours_the_editors_commands(self):
        # The rule's words are read from its text. call, return, and goto are
        # coloured by the grammar's other rules.
        match = json.loads(GRAMMAR.read_text(encoding="utf-8"))["repository"]["command"]["match"]
        words = set(re.search(r"\((page\|[^)]*)\)", match)[1].split("|"))
        self.assertEqual(words, EDITOR_COMMANDS - {"call", "return", "goto"})

    def test_a_command_is_coloured_where_command_word_reads_one(self):
        # At the start of a statement, and not assigned to: `i 1,2` is the
        # command, and `i = 5` or `x=i+1` name a variable i. The rule is one
        # Python's patterns take.
        match = json.loads(GRAMMAR.read_text(encoding="utf-8"))["repository"]["command"]["match"]
        pattern = re.compile(match)
        for line, coloured in (("i 1,2", True), ("  cls 1", True), ("cls", True), ("cls(1)", True),
                               ("{cls 1", True), ("i = 5", False), ("i  = 5", False),
                               ("i += 1", False), ("i ++", False), ("x = i + 1", False),
                               ("sys0=i", False), ("if(i 1)", False),
                               ("for(i=0; i < 3; i++)", False)):
            with self.subTest(line=line):
                self.assertEqual(bool(pattern.search(line)), coloured)

    def test_only_a_conditionals_colon_is_coloured_as_an_operator(self):
        # The formatter writes a space on each side of a conditional's ":".
        # The other colons end a heading, a case, or a label, or give a
        # parameter's kind.
        match = json.loads(GRAMMAR.read_text(encoding="utf-8"))["repository"]["operator"]["match"]
        pattern = re.compile(match)
        for line, coloured in (("x = a ? 1 : 2", ["?", ":"]), ("case 1:", []), ("default:", []),
                               ("up:", []), ("on n0.down:", []),
                               ("function f(a: number) -> text:", [])):
            with self.subTest(line=line):
                self.assertEqual([found[0] for found in pattern.finditer(line)
                                  if found[0] in ("?", ":")], coloured)

    def test_the_commands_nxwright_knows_are_the_editors(self):
        lacked = set().union(*SERIES_LACKED_COMMANDS.values())
        for known in (set(COMMAND_PARAMETERS), lacked, RECORDED_ONLY):
            self.assertEqual(known - EDITOR_COMMANDS, set())


if __name__ == "__main__":
    unittest.main()
