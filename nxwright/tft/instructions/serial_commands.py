"""The serial commands: get, print, prints, and sendme, on the T, K, P, E,
and F series, as the Nextion Editor 1.68.2 writes them
(ResearchNotes/tft/serial-commands.md).

Each is a command of table 4 or 8, then its arguments between commas. get
and print take one operand, prints an operand and a length, and sendme
none. Each operand is a number, a hexadecimal number, an int variable of
program.s, a system variable, a colour's name, a text between double
quotes, or, in an event, an attribute of a component of the line's page
(statements.attribute_kind), as the statement encoder (statements.py)
encodes it: `get n0.val` is 09 07 04, then n0.val's operand. prints' length
is a number: it may be an attribute, such as `t0.bco`, but not a text or a
txt. It
may also be operands joined by the arithmetic operators, as an
assignment's value is. The Nextion Editor refuses an expression as the
first operand, as in `get n0.val+1`, and so does nxwright.tft.
"""
import re

from nxwright.tft.matching import Rule
from nxwright.tft.statements import (REFERENCE_WORDS, TEXT, Command, arrays_fit, attribute_kind,
                              command_name, encodable, expression, f_takes, named_attributes,
                              operand_pattern, renumbered)

# An operand: a component's attribute, a txt among them; a hexadecimal
# number; a number, its sign included; a name; or a text, as the encoder
# reads them.
_OPERAND = r"(?:%s|%s)" % (operand_pattern(("number", "text")), TEXT)
# prints' length: operands joined by the arithmetic operators, each a
# hexadecimal number, a number, its sign included, a name, or an attribute
# other than a txt. The Nextion Editor refuses a text or a txt there
# ("Invalid variable operation").
_NUMBER = expression(operand_pattern(("number",)))

# Each command's number, its table, and its arguments: get and print what
# they send; prints what it sends and how many bytes of it; sendme none.
COMMANDS = {"T": {
    "get": Command(0x07, 4, _OPERAND),
    "print": Command(0x04, 8, _OPERAND),
    "prints": Command(0x0F, 8, _OPERAND + ", ?" + _NUMBER),
    "sendme": Command(0x09, 8, ""),
}}
# K numbers prints its own way, the others as T does.
COMMANDS["K"] = renumbered(COMMANDS["T"], {"prints": 0x10})
# P numbers these its own way, in the same tables (ResearchNotes/tft/p-series.md).
COMMANDS["P"] = renumbered(COMMANDS["T"], {"print": 0x05, "sendme": 0x0d, "prints": 0x16})
# F numbers these its own way, in the same tables (ResearchNotes/tft/f-series.md).
COMMANDS["F"] = renumbered(COMMANDS["T"], {"prints": 0x10})


def _covered(need) -> bool:
    """Whether the line of code `need` is one of these commands that the
    encoder encodes, on T. Each attribute the line refers to must be one
    the encoder encodes (statements.attribute_kind), so program.s, which has
    no page, takes none but another page's global's, and each reference
    through the screen's arrays one the line may hold
    (statements.arrays_fit)."""
    line = need.value.strip(" \t")
    # On F, the line may name only what F's tables hold.
    if need.series == "F" and not f_takes(line):
        return False
    if command_name(line) not in COMMANDS["T"] or not encodable(line):
        return False
    # Outside the texts between double quotes.
    return arrays_fit(need, line) and all(
        attribute_kind(need, attribute) is not None
        for attribute in named_attributes(re.sub(TEXT, "", line)))


# The series this module's probes matched (matching.py): T, K in k_probes.py,
# P in p_probes.py, E in e_probes.py, and F in f_probes.py.
SERIES = ("T", "K", "P", "E", "F")

MATCHED = [Rule("code", None, "get, print, prints, and sendme, their operands numbers, "
                "hexadecimal numbers of 1 to 4 bytes, program.s's int variables, system "
                "variables, colours' names, texts of any characters"
                ", with the escapes \\\\, \\\", and \\r, or, in an event, "
                "an attribute of a component on its page, its txt among them; "
                "prints' length no text or txt, but one operand or several joined by "
                "the arithmetic operators; " + REFERENCE_WORDS + "; on T, K, P, E, and F, on "
                "F naming only what its tables hold (statements.f_takes)",
                _covered)]
