"""Labels and goto, on the T, K, P, E, and F series, as the Nextion Editor
1.68.2 writes them (ResearchNotes/tft/goto-statement.md). A label is a line of its
name and a colon, such as `loop:`. `goto loop` jumps to the line after it,
in the same run of code: program.s, or one event.

A label is an "S " block of its number, and a goto a "G " block of the
place of the block after its label's (label_numbers.py): `loop:` is
53 20 03 01 00 00 00 when it takes number 1. The statement encoder gives
both unwritten (label_numbers.LabelBlock and GotoBlock), and the frame
writes them once it lays out their run of code. A label may lie in the
body of an if, a while, or a for, and at the end of its run, where its goto
jumps to the run's closing 0 word.

nxwright's build refuses a goto whose label is not in its run, and a label
twice in one run, as the Nextion Editor refuses them ("nofind mark",
"repeated mark").
"""
import re

from nxwright.tft.label_numbers import GotoBlock, LabelBlock, goto_of, label_of
from nxwright.tft.matching import Rule
from nxwright.tft.statements import StatementError

# The series whose labels and gotos the encoder writes.
_SERIES = ("T", "K", "P", "E", "F")
# A label's name, as the probes gave them: ASCII letters, digits, and _,
# not starting with a digit, of any length.
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def starts_statement(line: str) -> bool:
    """Whether `line` is a label or a goto, each a statement of one line."""
    return label_of(line) is not None or goto_of(line) is not None


def encode_statement(lines: list, start: int, place, context, encode_run) -> tuple:
    """Returns the block of the label or the goto at lines[start], unwritten,
    and the index of the next line (instructions/__init__.py). Raises
    StatementError on a series whose labels the encoder does not write."""
    series = context.project.settings.model.series
    if series not in _SERIES:
        raise StatementError("the %s series' labels and goto are not encoded yet" % series)
    label = label_of(lines[start])
    if label is not None:
        return [LabelBlock(label)], start + 1
    return [GotoBlock(goto_of(lines[start]))], start + 1


def _covered(need) -> bool:
    """Whether the line of code `need` is a label, or a goto, whose name the
    probes showed (_NAME)."""
    name = label_of(need.value)
    if name is None:
        name = goto_of(need.value)
    return name is not None and _NAME.fullmatch(name) is not None


# The series this module's probes matched (matching.py): T, K in k_probes.py,
# P in p_probes.py, E in e_probes.py, and F in f_probes.py.
SERIES = _SERIES

MATCHED = [Rule("code", None, "labels and goto, in program.s or an event: a label's name of "
                "ASCII letters, digits, and _, not starting with a digit; on T, K, P, E, and F",
                _covered)]
