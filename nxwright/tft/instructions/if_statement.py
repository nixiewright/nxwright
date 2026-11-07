"""The `if` statement, with its `else if` and `else` branches, as the
Nextion Editor 1.68.2 writes it on the T series
(ResearchNotes/tft/if-statement.md).

An `if` spans several lines of a run: `if(<condition>)`, then `{`, its
body, then `}`. In place of that `}`, `}else if(<condition>)` or `}else`
starts another branch, followed by `{`, its body, and so on, the last
branch ending with `}`. The braces give no block. Conditions, bodies, and
jumps are as control_statements.py gives them.

The statement's blocks, in order, branch after branch:

  - the branch's condition, which guards the rest of the branch: its body,
    and the jump block that may follow the body;
  - the branch's body: its lines' blocks, other statements among them;
  - when another branch follows, a jump block past the rest of the
    statement.
"""
import re

from nxwright.tft.component_types import SERIES_WRITTEN_AS_P
from nxwright.tft.control_statements import (CLOSING, OPENING, braced_body,
                                      condition_blocks, covers_condition, jump_block, size_of,
                                      threaded)
from nxwright.tft.matching import Rule
from nxwright.tft.statements import StatementError, f_takes, p_takes

# The lines of the statement, but its braces.
_IF = re.compile(r"[ \t]*if[ \t]*\((?P<condition>.+)\)[ \t]*")
_ELSE_IF = re.compile(r"[ \t]*\}[ \t]*else[ \t]+if[ \t]*\((?P<condition>.+)\)[ \t]*")
_ELSE = re.compile(r"[ \t]*\}[ \t]*else[ \t]*")


def starts_statement(line: str) -> bool:
    """Whether `line` starts an `if`."""
    return _IF.fullmatch(line) is not None


def encode_statement(lines: list, start: int, place, context, encode_run) -> tuple:
    """Returns the blocks of the `if` that starts at lines[start], and the
    index of the line after its last `}` (instructions/__init__.py). Raises
    StatementError for a statement it does not encode."""
    series = context.project.settings.model.series
    if series not in SERIES:
        raise StatementError("the %s series' if is not encoded yet" % series)
    branches, otherwise, end = _branches(lines, start)
    rest = [] if otherwise is None else encode_run(otherwise, place, context)
    for number in range(len(branches) - 1, -1, -1):
        condition, body = branches[number]
        blocks = encode_run(body, place, context)
        if number < len(branches) - 1 or otherwise is not None:
            blocks.append(jump_block(size_of(rest)))
        rest = condition_blocks(condition, size_of(blocks), place, context, series) + blocks + rest
    return threaded(rest), end


def covers(line: str, need=None) -> bool:
    """Whether MATCHED covers `line`: one of an `if`'s own lines, as the
    encoder writes them. `need` is the line's, which tells the attributes
    its condition may refer to (control_statements.covers_condition)."""
    if any(shape.fullmatch(line) for shape in (OPENING, CLOSING, _ELSE)):
        return True
    # On P and on F, the line holds only what that series' probes of code
    # showed.
    if need is not None and need.series in SERIES_WRITTEN_AS_P and not p_takes(line):
        return False
    if need is not None and need.series == "F" and not f_takes(line):
        return False
    found = _IF.fullmatch(line) or _ELSE_IF.fullmatch(line)
    return found is not None and covers_condition(found.group("condition"), need)


# The series this module's probes matched (matching.py): T, K in k_probes.py,
# P in p_probes.py, E in e_probes.py, and F in f_probes.py.
SERIES = ("T", "K", "P", "E", "F")

MATCHED = [Rule("code", None, "if, else if, and else: braces on lines of their own; a "
                "condition of comparisons joined by && alone or || alone outside its texts, "
                "each of two numbers, hexadecimal numbers, int variables, system variables, "
                "colours' names, or attributes encoded as numbers, or of two texts or txts, the "
                "texts of any characters and any length, with the escapes \\\\, \\\", and \\r; "
                "on T and K, "
                "on P and E with what P's probes of code showed alone (statements.p_takes), "
                "and on F with what F's showed alone (statements.f_takes)",
                lambda need: covers(need.value, need))]


def _branches(lines: list, start: int) -> tuple:
    """Returns the statement's branches, [(condition, body's lines)], its
    else's body's lines, or None, and the index of the line after it."""
    branches, otherwise = [], None
    condition = _IF.fullmatch(lines[start]).group("condition")
    at = start + 1
    while True:
        body, closing, at = braced_body(lines, at)
        if condition is None:
            otherwise = body
        else:
            branches.append((condition, body))
        if CLOSING.fullmatch(closing):
            return branches, otherwise, at
        if otherwise is not None:
            raise StatementError("%r: no branch may follow an else" % closing)
        if _ELSE.fullmatch(closing):
            condition = None
            continue
        found = _ELSE_IF.fullmatch(closing)
        if found is None:
            raise StatementError("%r is not a line of an if" % closing)
        condition = found.group("condition")
