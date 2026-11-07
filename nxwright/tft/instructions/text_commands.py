"""The text commands: covx, cov, strlen, btlen, substr, and spstr, on the T,
K, P, E, and F series, as the Nextion Editor 1.68.2 writes them
(ResearchNotes/tft/text-commands.md).

Each is a command of table 4 or 8, its operands between commas. Each
operand is a number, a hexadecimal number, an int variable of program.s, a
system variable, a colour's name, a text between double quotes, or a
component's attribute, such as a txt, a val, a timer's tim, or a text's
bco. The statement encoder (statements.py) encodes each as in any line:
`strlen t1.txt,sys1` is 09 0c 08, t1.txt's operand, a comma, then sys1's.
A space after a comma is dropped, as the Nextion Editor drops it.

Where a command takes a number, a length, a form, a start, a count, or a
part, the Nextion Editor refuses a text or a txt ("Invalid variable
operation"), and so does nxwright.tft. Every other attribute is a number there:
`covx n0.val,t0.txt,n1.val,0` takes n1's val as its length. There it also
takes operands joined by the arithmetic operators, as an assignment's value
is: `covx n0.val,t0.txt,n1.val*2,0`. It refused them as each source,
destination, and separator tried ("Invalid Variables"): cov's, covx's,
strlen's, substr's, spstr's, and btlen's sources, cov's, covx's, and
strlen's destinations, and spstr's separator, and so does nxwright, as
nxwright's build lets them through. Elsewhere it does
not check an operand's kind: `strlen sys0,sys1` compiles, and so does
nxwright.tft. A destination may be an attribute that an assignment may not set:
`strlen t0.txt,s0.id` compiles, though nxwright refuses `s0.id=5`
(statements.sets_only_changeable_attributes).
"""
import re

from nxwright.tft.matching import Rule
from nxwright.tft.statements import (REFERENCE_WORDS, TEXT, Command, attributes_are_encoded, command_name,
                              encodable, expression, f_takes, operand_pattern, operands,
                              renumbered)

# A command's operand, as the encoder reads it: a component's attribute, a
# txt among them, a hexadecimal number, a number, its sign included, a
# name, or a text. Any other operand is refused, such as an expression.
_OPERAND = r"(?:%s|%s)" % (operand_pattern(("number", "text")), TEXT)
# Where a command takes a number: operands joined by the arithmetic
# operators, each a hexadecimal number, a number, its sign included, an
# attribute other than a txt, or a name. The Nextion Editor refuses a text
# or a txt there ("Invalid variable operation").
_NUMBER = expression(operand_pattern(("number",)))

# Each command's number, its table, and how many operands it takes: covx a
# source, a destination, a length, and a form; cov the same without the
# form; strlen and btlen a text and where its length goes; substr a source,
# a destination, a start, and a count; spstr a source, a destination, a
# separator, and which part to take.
COMMANDS = {"T": {
    "covx": Command(0x1C, 4, ", ?".join([_OPERAND, _OPERAND, _NUMBER, _NUMBER])),
    "cov": Command(0x08, 4, ", ?".join([_OPERAND, _OPERAND, _NUMBER])),
    "strlen": Command(0x0C, 8, operands(_OPERAND, 2)),
    "btlen": Command(0x02, 8, operands(_OPERAND, 2)),
    "substr": Command(0x0E, 8, ", ?".join([_OPERAND, _OPERAND, _NUMBER, _NUMBER])),
    "spstr": Command(0x03, 8, ", ?".join([_OPERAND, _OPERAND, _OPERAND, _NUMBER])),
}}
# K numbers covx and substr its own way, the others as T does.
COMMANDS["K"] = renumbered(COMMANDS["T"], {"covx": 0x20, "substr": 0x0f})
# P numbers these its own way, in the same tables (ResearchNotes/tft/p-series.md).
COMMANDS["P"] = renumbered(COMMANDS["T"], {
    "spstr": 0x04, "strlen": 0x10, "substr": 0x15, "covx": 0x27})
# F numbers these its own way, in the same tables (ResearchNotes/tft/f-series.md).
COMMANDS["F"] = renumbered(COMMANDS["T"], {"covx": 0x23, "substr": 0x0f})


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

MATCHED = [Rule("code", None, "covx, cov, strlen, btlen, substr, and spstr, their operands "
                "numbers, hexadecimal numbers of 1 to 4 bytes, program.s's int variables, "
                "system variables, colours' names, texts of any characters"
                ", with the escapes \\\\, \\\", and \\r, or, in an "
                "event, an attribute of a component on its page, its txt among them; "
                "where a command takes a number, no text or txt, but one operand or several "
                "joined by the arithmetic operators; " + REFERENCE_WORDS + "; on T, K, P, E, "
                "and F, on F naming only what its tables hold (statements.f_takes)",
                _covered)]
