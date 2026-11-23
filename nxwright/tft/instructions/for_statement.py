"""The `for` statement, as the Nextion Editor 1.68.2 writes it on the T
series (ResearchNotes/tft/for-statement.md).

A `for` spans several lines of a run: `for(<start>;<condition>;<step>)`,
then `{`, its body, then `}`. The braces give no block. The start and the
step are assignments, such as `sys0=0` and `sys0++`, each encoded as a line
of its own. The Nextion Editor rejects an empty start or step. Conditions,
bodies, and jumps are as control_statements.py gives them.

If the start contains a method call, the Nextion Editor writes the start
only up to the first call's parentheses, so the screen does not run the
call (_start_as_written). In the step, the Nextion Editor rejects a call
("Invalid Variables").

The statement's blocks, in order:

  - its start's block;
  - a loop, as a while's: the condition; the body, then the step's block;
    and a jump block back to the condition's first comparison. So the start
    runs once, and the step after each run of the body.
"""
from dataclasses import replace
import re

from nxwright.tft.component_types import SERIES_WRITTEN_AS_P
from nxwright.tft.control_statements import (CLOSING, OPENING, braced_body,
                                      covers_condition, loop_blocks, threaded)
from nxwright.tft.matching import Rule
from nxwright.tft.statements import (INDIRECT, StatementError, attributes_are_numbers, covers_line,
                              encodable, encode_line, f_takes, holds_a_call, indirect_covered,
                              refers_through_arrays, p_takes, sets_only_changeable_attributes)

# The statement's first line, with its parts between semicolons.
_FOR = re.compile(r"[ \t]*for[ \t]*\((?P<parts>.*)\)[ \t]*")
# A start or a step: an assignment to a name or a component's attribute,
# directly or through the screen's arrays (statements.INDIRECT).
_ASSIGNMENT = re.compile(r"[ \t]*(?:%s|[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*){0,2})"
                         r"[ \t]*(?:<<=|>>=|[-+*/%%&|^]=|\+\+|--|=(?!=)).*" % INDIRECT,
                         re.ASCII)


def starts_statement(line: str) -> bool:
    """Whether `line` starts a `for`."""
    return _FOR.fullmatch(line) is not None


def encode_statement(lines: list, start: int, place, context, encode_run) -> tuple:
    """Returns the blocks of the `for` that starts at lines[start], and the
    index of the line after its `}` (instructions/__init__.py). Raises
    StatementError for a statement it does not encode."""
    series = context.project.settings.model.series
    if series not in SERIES:
        raise StatementError("the %s series' for is not encoded yet" % series)
    head = lines[start]
    first, condition, step = _parts(head)
    body, closing, end = braced_body(lines, start + 1)
    if not CLOSING.fullmatch(closing):
        raise StatementError("%r: a for's body ends with } alone" % closing)
    blocks = encode_run(body, place, context) + [_assignment(step, head, place, context)]
    return threaded([_assignment(_start_as_written(first), head, place, context)]
                    + loop_blocks(condition, blocks, place, context, series)), end


def covers(line: str, need=None) -> bool:
    """Whether MATCHED covers `line`, one of a `for`'s own lines. `need` is
    the line's need, which gives the attributes that the line may refer to.

    The condition is checked by control_statements.covers_condition. The
    start and the step are each checked by their kind:

      - A step that contains a method call is not covered, because the
        Nextion Editor rejects it ("Invalid Variables").
      - A start or a step that contains a text, and a start that contains a
        method call, are each checked as a line of their own
        (statements.covers_line).
      - Any other start or step must refer to attributes as numbers
        (statements.attributes_are_numbers), and set only the attributes
        that code can change (statements.sets_only_changeable_attributes).
        If it refers to an attribute through the screen's arrays,
        statements.indirect_covered must cover it.
    """
    if OPENING.fullmatch(line) or CLOSING.fullmatch(line):
        return True
    # On P and on F, the line holds only what that series' probes of code
    # showed.
    if need is not None and need.series in SERIES_WRITTEN_AS_P and not p_takes(line):
        return False
    if need is not None and need.series == "F" and not f_takes(line):
        return False
    try:
        first, condition, step = _parts(line)
    except StatementError:
        return False
    if holds_a_call(step):
        return False
    return covers_condition(condition, need) and all(
        _ASSIGNMENT.fullmatch(part) is not None and encodable(part) and _part_covered(part, need)
        for part in (first, step))


def _part_covered(part: str, need) -> bool:
    """Whether the start or step `part` of the line of `need` is one the
    encoder writes. One that holds a text, as `t0.txt=""`, is a line of
    its own to the encoder, so the statement encoder's rule of a line takes
    it (statements.covers_line). A start that contains a method call is
    checked by that rule too, in full, so that every call in it is checked.
    The encoder then writes the start only up to its first call's
    parentheses (_start_as_written). Any other refers to attributes as
    numbers, sets only those code can change, and refers through the
    screen's arrays as the encoder's rule of them takes it."""
    if '"' in part or holds_a_call(part):
        return need is not None and covers_line(replace(need, value=part))
    return (attributes_are_numbers(need, part) and sets_only_changeable_attributes(need, part)
            and (not refers_through_arrays(part)
                 or (need is not None and indirect_covered(replace(need, value=part)))))


# The series this module's probes matched (matching.py): T, K in k_probes.py,
# P in p_probes.py, E in e_probes.py, and F in f_probes.py.
SERIES = ("T", "K", "P", "E", "F")

MATCHED = [Rule("code", None, "for: braces on lines of their own; a start and a step, each an "
                "assignment of the statement encoder's: one with a text as a line of its own, "
                "any other with its attributes encoded as numbers, and one through the screen's "
                "arrays as the encoder's rule of them takes it; the if's conditions; on T and "
                "K, on P and E with what P's probes of code showed alone (statements.p_takes), "
                "and on F with what F's showed alone (statements.f_takes)",
                lambda need: covers(need.value, need))]


def _parts(line: str) -> tuple:
    """Returns the start, the condition, and the step of the `for` that
    `line` starts. Raises StatementError for a line of another shape, and
    for an empty start or step."""
    found = _FOR.fullmatch(line)
    parts = found.group("parts").split(";") if found else []
    if len(parts) != 3:
        raise StatementError("%r is no for of a start, a condition, and a step" % line)
    if not parts[0].strip(" \t") or not parts[2].strip(" \t"):
        raise StatementError("%r: the Nextion Editor refuses a for whose start or step is empty"
                             % line)
    return tuple(parts)


def _start_as_written(start: str) -> str:
    """Returns the part of `start`, a for's start, that the Nextion Editor
    writes. If the start contains a method call, that part ends before the
    first call's parentheses: `sys0=fs0.close` for `sys0=fs0.close()`, and
    `sys0=fs0.open` for `sys0=fs0.open(t0.txt)+1`. So the screen reads the
    method as an attribute, and does not call it."""
    return start[:start.index("(")] if holds_a_call(start) else start


def _assignment(text: str, line: str, place, context) -> bytes:
    """Returns the block of `text`, the start or the step of the `for`
    `line`. Raises StatementError for one that is no assignment."""
    if not _ASSIGNMENT.fullmatch(text):
        raise StatementError("%r: %r is no assignment, as a for's start or step must be"
                             % (line, text))
    return encode_line(text, place, context)
