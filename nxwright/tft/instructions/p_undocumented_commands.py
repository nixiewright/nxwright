"""The undocumented commands that P and E have and T and K have not: beepset,
cfguart, cuts, gets, meup, sets, and xnum, as the Nextion Editor 1.68.2
writes them on P and E (ResearchNotes/tft/p-series.md), and cuts, gets, sets,
and xnum on F, under numbers of its own (ResearchNotes/tft/f-series.md). The vendor's
instruction set does not give them, and what they do on the screen is not
known. nxwright's build refuses each written alone.

Each is a command of table 4 or 8, then its arguments between commas, each
encoded by the statement encoder (statements.py) as in any line:
`cuts n0.val,sys0,1,2,3,4,5` is 09 1d 04, n0.val's operand, a comma,
sys0's operand, then `,1,2,3,4,5`.

beepset, cfguart, cuts, meup, and xnum take numbers: operands joined by the
arithmetic operators, but no text or txt ("Invalid variable operation").
gets takes two operands of any kind, a text or a txt among them, but no
operator. sets takes from 1 to 12: its first three of any kind, each later
one of a number's kind, neither with an operator. The Nextion Editor
refused an operator where either takes one operand, as `gets
n0.val,sys0+1`. i, which P numbers as T
does, is with T's and K's commands, in undocumented_commands.py.
"""
from dataclasses import replace
import re

from nxwright.tft.component_types import SERIES_WRITTEN_AS_P
from nxwright.tft.matching import Rule
from nxwright.tft.statements import (TEXT, Command, attributes_are_encoded, command_name, encodable,
                              expression, f_takes, operand_pattern, operands)

# Where a command takes a number: operands joined by the arithmetic
# operators, each a hexadecimal number, a number, a name, or an attribute
# other than a txt.
_NUMBER = expression(operand_pattern(("number",)))
# One operand of a number's kind, without an operator.
_ONE_NUMBER = operand_pattern(("number",))
# One operand of any kind, a txt or a text among them, without an operator.
_ANY = r"(?:%s|%s)" % (operand_pattern(("number", "text")), TEXT)
# sets' arguments: up to three of any kind, or three of any kind, then up to
# nine of a number's kind.
_SETS = r"(?:%s(?:, ?%s){0,2}|%s(?:, ?%s){1,9})" % (_ANY, _ANY, operands(_ANY, 3), _ONE_NUMBER)

# Each command's number, its table, and its arguments, on P.
COMMANDS = {"P": {
    "beepset": Command(0x22, 8, operands(_NUMBER, 2)),
    "cfguart": Command(0x23, 8, operands(_NUMBER, 4)),
    "cuts": Command(0x1D, 4, operands(_NUMBER, 7)),
    "gets": Command(0x1B, 4, operands(_ANY, 2)),
    "meup": Command(0x14, 4, operands(_NUMBER, 2)),
    "sets": Command(0x1C, 4, _SETS),
    "xnum": Command(0x10, 4, operands(_NUMBER, 10)),
}}
# F has cuts, gets, sets, and xnum, of these, numbered its own way in the
# same table. It lacks beepset, cfguart, and meup, which nxwright's build
# refuses there.
COMMANDS["F"] = {name: replace(COMMANDS["P"][name], number=number)
                 for name, number in (("cuts", 0x1B), ("gets", 0x19), ("sets", 0x1A),
                                      ("xnum", 0x0E))}


def _covered(need) -> bool:
    """Whether the line of code `need` is one of these commands that the
    encoder encodes, on the line's series, P's table on E. Each attribute
    the line refers to outside its texts must be one the encoder encodes
    (statements.attributes_are_encoded), so program.s, which has no page,
    takes none of a page's own."""
    line = need.value.strip(" \t")
    # On F, the line may name only what F's tables hold.
    if need.series == "F" and not f_takes(line):
        return False
    series = "P" if need.series in SERIES_WRITTEN_AS_P else need.series
    if command_name(line) not in COMMANDS.get(series, {}) or not encodable(line, series):
        return False
    return attributes_are_encoded(need, re.sub(TEXT, "", line))


# The series this module's probes matched (matching.py): P in p_probes.py,
# E in e_probes.py, and F in f_probes.py.
SERIES = ("P", "E", "F")

MATCHED = [Rule("code", None, "beepset, cfguart, cuts, meup, and xnum of numbers, each one "
                "operand or several joined by the arithmetic operators; gets of two operands of "
                "any kind; sets of 1 to 12 operands, its first three of any kind and each "
                "later one of a number's kind; an operand a "
                "number, a hexadecimal number of 1 to 4 bytes, program.s's int variables, "
                "system variables, colours' names, or, in an event, an attribute of a "
                "component on its page, a txt or a text of any characters"
                ", with the escapes \\\\, \\\", and \\r, where any kind is taken; in "
                "an event, and in program.s; on P and E, and cuts, gets, sets, and xnum on F, "
                "naming only what its tables hold (statements.f_takes)",
                _covered)]
