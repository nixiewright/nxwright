"""The forms of code the Nextion Editor accepts, in the match check and the
frame.

docs/source-folder.md gives the forms of code the Nextion
Editor accepts, which nxwright's build leaves as written, and
ResearchNotes/build-rules.md records two more the Nextion Editor
compiled: an int declaration without a value, and a negative number after
an arithmetic operator. A label's name past 30 characters is one more, as
the Nextion Editor compiled one of 762. For each, in an event, in
program.s, or in a macro, on T, K, P, E, and F, the
check must take a project that holds it, and the frame, with the statement
encoder, must write the project's user code.

What fails today is listed below, each case by the line of the plan's
Checklist that takes it up. A case that no longer fails must be taken off
the list, so that the test checks it from then on.

Each case is a Project of the facts of the base folder's page0, program.s,
and macros, holding the form, made in memory as nxwright's build makes them
(tests/tft/unit_inputs.py).
"""
import unittest


from nxwright.tft import frame
from nxwright.tft.matching import matched_rules, project_needs, unmatched
from tools.tft.probing.macro_probes import macros_text
from tools.tft.probing.statement_probes import touch_release_code
from tools.tft.probing.text_probes import text_component
from tests.tft.unit_inputs import page, project_of

# The forms of a page's event, each by its words in the table or the note,
# with the lines that hold it. The page holds a text, msg, which the table's
# command names.
_IN_AN_EVENT = {
    "an assignment": ["sys0=1"],
    "if and else if": ["if(sys0==1)", "{", "sys0=2", "}else if(sys0==2)", "{", "sys0=3", "}"],
    "a command": ["covx sys0,msg.txt,0,0"],
    "indentation with spaces": ["  sys0=1"],
    "indentation with tabs": ["\tsys0=1"],
    "a comment after code": ["sys0=1 // note"],
    "spaces between a command's own arguments": ["printh 00 00 00"],
    "a negative number after an arithmetic operator": ["sys0=2*-16"],
    "a label's name past 30 characters": ["a" * 40 + ":", "goto " + "a" * 40],
}
# And those of program.s's int declarations, which follow the base folder's
# own: spaces after commas, which the table gives there; indentation and a
# comment after code, which it gives for any line; and a declaration
# without a value, which the note records.
_IN_PROGRAM_S = {
    "spaces after commas in a declaration": ["int a=0, b=1"],
    "an indented declaration": ["  int a=0"],
    "a comment after a declaration": ["int a=0 // note"],
    "a declaration without a value": ["int a"],
}
# And those of a macro, which page0's Touch Release event calls: the table
# gives indentation and a comment after code for any line.
_IN_A_MACRO = {
    "a comment after code in a macro": ["sys0=1 // note"],
    "indentation in a macro": ["  sys0=1", "\tsys1=2"],
}
_SERIES = "TKPEF"

# What fails today, by the line of the plan's Checklist that takes it up.
_KNOWN_FAILURES = {}


def _projects(series: str, form: str) -> tuple:
    """Returns the Projects of facts of the base folder of `series` that
    holds `form`, with the text msg on page0: one as the match check reads
    it, without resources, and one as the frame reads it, with the base
    folder's fonts. A declaration's form makes the code strict Nextion
    syntax, as statement_probes.program_lines does."""
    declarations = tuple(_IN_PROGRAM_S.get(form, ()))
    strict = bool(declarations)
    lines = _IN_AN_EVENT.get(form, [])
    macros = None
    if form in _IN_A_MACRO:
        macros = macros_text([("m", _IN_A_MACRO[form])])
        lines = ["call m"]
    code = touch_release_code(lines) if lines else ""
    made = page(text_component("msg"), series=series, code=code, strict=strict,
                declarations=declarations, macros=macros)
    options = dict(series=series, strict=strict, declarations=declarations, macros=macros)
    return project_of(made, fonts=0, **options), project_of(made, **options)


def _failure(checked, written) -> str:
    """Returns why the form fails, the needs the check refuses in `checked`
    or the error the frame raises writing `written`, or None when it
    passes."""
    refused = unmatched(project_needs(checked), matched_rules())
    if refused:
        return "refused: %s" % [need.described() for need in refused]
    try:
        frame.user_code(written)
    except Exception as error:
        return "not written: %s" % error
    return None


class FormsTest(unittest.TestCase):

    def test_each_form_the_nextion_editor_accepts(self):
        failing = {}
        for series in _SERIES:
            for form in list(_IN_AN_EVENT) + list(_IN_PROGRAM_S) + list(_IN_A_MACRO):
                failure = _failure(*_projects(series, form))
                if failure is not None:
                    failing[(form, series)] = failure
        self.assertEqual({key: failing[key] for key in failing.keys() - _KNOWN_FAILURES.keys()},
                         {})
        self.assertEqual(_KNOWN_FAILURES.keys() - failing.keys(), set(),
                         "these pass now, so take them off _KNOWN_FAILURES")


if __name__ == "__main__":
    unittest.main()
