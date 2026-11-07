"""The `while` statement, as the Nextion Editor 1.68.2 writes it on the T
series (ResearchNotes/tft/while-statement.md).

A `while` spans several lines of a run: `while(<condition>)`, then `{`, its
body, then `}`. The braces give no block. Conditions, bodies, and jumps are
as control_statements.py gives them.

The statement's blocks are a loop (control_statements.loop_blocks), in
order:

  - its condition, which guards the rest of the statement: its body, and
    the jump block after it;
  - its body: its lines' blocks, other statements among them;
  - a jump block back to the condition's first comparison.
"""
import re

from nxwright.tft.component_types import SERIES_WRITTEN_AS_P
from nxwright.tft.control_statements import (CLOSING, OPENING, braced_body,
                                      covers_condition, loop_blocks, threaded)
from nxwright.tft.matching import Rule
from nxwright.tft.statements import StatementError, f_takes, p_takes

# The statement's first line.
_WHILE = re.compile(r"[ \t]*while[ \t]*\((?P<condition>.+)\)[ \t]*")


def starts_statement(line: str) -> bool:
    """Whether `line` starts a `while`."""
    return _WHILE.fullmatch(line) is not None


def encode_statement(lines: list, start: int, place, context, encode_run) -> tuple:
    """Returns the blocks of the `while` that starts at lines[start], and
    the index of the line after its `}` (instructions/__init__.py). Raises
    StatementError for a statement it does not encode."""
    series = context.project.settings.model.series
    if series not in SERIES:
        raise StatementError("the %s series' while is not encoded yet" % series)
    body, closing, end = braced_body(lines, start + 1)
    if not CLOSING.fullmatch(closing):
        raise StatementError("%r: a while's body ends with } alone" % closing)
    condition = _WHILE.fullmatch(lines[start]).group("condition")
    return threaded(loop_blocks(condition, encode_run(body, place, context), place, context,
                                series)), end


def covers(line: str, need=None) -> bool:
    """Whether MATCHED covers `line`: one of a `while`'s own lines, as the
    encoder writes them. `need` is the line's, which tells the attributes
    its condition may refer to (control_statements.covers_condition)."""
    if OPENING.fullmatch(line) or CLOSING.fullmatch(line):
        return True
    # On P and on F, the line holds only what that series' probes of code
    # showed.
    if need is not None and need.series in SERIES_WRITTEN_AS_P and not p_takes(line):
        return False
    if need is not None and need.series == "F" and not f_takes(line):
        return False
    found = _WHILE.fullmatch(line)
    return found is not None and covers_condition(found.group("condition"), need)


# The series this module's probes matched (matching.py): T, K in k_probes.py,
# P in p_probes.py, E in e_probes.py, and F in f_probes.py.
SERIES = ("T", "K", "P", "E", "F")

MATCHED = [Rule("code", None, "while: braces on lines of their own; a condition of "
                "comparisons joined by && alone or || alone outside its texts, each of two "
                "numbers, hexadecimal numbers, int variables, system variables, colours' "
                "names, or attributes encoded as numbers, or of two texts or txts, the texts of "
                "any characters and any length, with the escapes \\\\, \\\", and \\r; on T and "
                "K, on P and E with "
                "what P's probes of code showed alone (statements.p_takes), and on F with "
                "what F's showed alone (statements.f_takes)",
                lambda need: covers(need.value, need))]
