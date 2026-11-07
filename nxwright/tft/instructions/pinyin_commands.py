"""The pinyin commands, pa_q and pa_txt, which look Chinese characters up by
their pinyin syllable in the screen's own table, on the T, K, P, E,
and F series, as the Nextion Editor 1.68.2 writes them
(ResearchNotes/tft/pinyin-commands.md).
nxwright's Chinese keyboard runs them.

  - `pa_q "mei",n0.val` gives n0.val the number of characters of the
    syllable "mei";
  - `pa_txt "mei",t0.txt,0,6` gives t0.txt six of them, from the first.

Each is a command of table 4 or 8, its operands between commas, each
encoded by the statement encoder (statements.py) as in any line:
`pa_q t0.txt,n0.val` is 09 0e 04, t0.txt's operand, a comma, then n0.val's.
The syllable, where pa_txt gives its characters, and where pa_q gives its
count each take one operand of any kind, a text or a txt among them: the
Nextion Editor does not check an operand's kind there. It refused an
expression there ("Invalid Variables"), which nxwright's build lets
through. Where a command takes a number, pa_txt's start and count, it
takes operands joined by the arithmetic operators, each a number, a
hexadecimal number, a variable, or an attribute other than a txt:
`pa_txt "mei",t0.txt,sys0+1,6` gives sys0's operand, then `+1`. It refused
a text or a txt there ("Invalid variable operation").
"""
import re

from nxwright.tft.matching import Rule
from nxwright.tft.statements import (REFERENCE_WORDS, TEXT, Command,
                              attributes_are_encoded, command_name, encodable, expression,
                              f_takes, operand_pattern, renumbered)

# A syllable, where pa_txt's characters go, and where pa_q's count goes: one
# operand of any kind, a text or a txt among them, as the Nextion Editor
# does not check an operand's kind there. It compiled `pa_q 5,sys0`,
# `pa_q "a",b[1].txt`, and `pa_txt "a",sys0,0,1`, and refused an
# expression ("Invalid Variables").
_ANY = r"(?:%s|%s)" % (operand_pattern(("number", "text")), TEXT)
# Where a command takes a number: operands joined by the arithmetic
# operators, each a hexadecimal number, a number, a variable, or an
# attribute other than a txt.
_NUMBER = expression(operand_pattern(("number",)))

# Each command's number, its table, and its operands: pa_q a syllable and
# where its count goes; pa_txt a syllable, where its characters go, the
# first to give, from 0, and how many.
COMMANDS = {"T": {
    "pa_q": Command(0x0E, 4, ", ?".join([_ANY, _ANY])),
    "pa_txt": Command(0x10, 8, ", ?".join([_ANY, _ANY, _NUMBER, _NUMBER])),
}}
# K numbers both its own way.
COMMANDS["K"] = renumbered(COMMANDS["T"], {"pa_q": 0x10, "pa_txt": 0x11})
# P numbers these its own way, in the same tables (ResearchNotes/tft/p-series.md).
COMMANDS["P"] = renumbered(COMMANDS["T"], {"pa_q": 0x15, "pa_txt": 0x17})
# F numbers these its own way, in the same tables (ResearchNotes/tft/f-series.md).
COMMANDS["F"] = renumbered(COMMANDS["T"], {"pa_q": 0x12, "pa_txt": 0x11})


def _covered(need) -> bool:
    """Whether the line of code `need` is one of these commands that the
    encoder encodes, on T. Each attribute the line refers to must be that
    of a component of the line's page whose type has it
    (statements.attributes_are_encoded), so program.s, which has no page,
    takes none."""
    line = need.value.strip(" \t")
    # On F, the line may name only what F's tables hold.
    if need.series == "F" and not f_takes(line):
        return False
    if command_name(line) not in COMMANDS["T"] or not encodable(line):
        return False
    # Outside the texts between double quotes.
    return attributes_are_encoded(need, re.sub(TEXT, "", line))


# The series this module's probes matched (matching.py): T, K in k_probes.py,
# P in p_probes.py, E in e_probes.py, and F in f_probes.py.
SERIES = ("T", "K", "P", "E", "F")

MATCHED = [Rule("code", None, "pa_q and pa_txt, their syllable, pa_q's count's destination, "
                "and pa_txt's characters' each one operand of any kind, a number, a "
                "hexadecimal number, a variable, an attribute, a txt, or a text, but no "
                "expression, which the Nextion Editor refuses; pa_txt's start and count each "
                "operands joined by the arithmetic operators, a number, a hexadecimal number, "
                "a variable, or an attribute other than a txt; in an event, "
                "and in program.s; " + REFERENCE_WORDS + "; on T, K, P, E, and F, on F naming "
                "only what its tables hold (statements.f_takes)", _covered)]
