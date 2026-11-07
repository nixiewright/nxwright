"""The waveform commands, on the T, K, P, E, and F series, as the Nextion
Editor 1.68.2 writes them (ResearchNotes/tft/waveform-commands.md): add, addt,
and cle. As the vendor's instruction set documents them, each takes a
waveform's ID and a channel first. add adds a value to the channel, addt
readies it for a count of bytes that come next on the serial line, and cle
clears it, or every channel when the channel is 255.

Each argument, the ID too, is a value, as the statement encoder
(statements.py) encodes an assignment's: an operand, or operands joined by
the arithmetic operators. An operand is a number, a hexadecimal number, an
int variable of program.s, a system variable, or a component's attribute
other than a txt, such as a waveform's id.
addt and cle are commands of table 4: `cle s0.id,0` is 09 02 04, s0.id's
operand, then `,0`. add is written by its name instead: `add s0.id,0,10` is
`add `, s0.id's operand, then `,0,10`. The Nextion Editor refuses a text or
a txt as an argument ("Invalid variable operation"), and so does nxwright.tft.
"""
from nxwright.tft.matching import Rule
from nxwright.tft.statements import (REFERENCE_WORDS, Command, attributes_are_numbers, command_name,
                              encodable, expression, f_takes, operand_pattern, operands,
                              renumbered)

# An argument, as the encoder reads it: operands joined by the arithmetic
# operators, each a hexadecimal number, a number, its sign included, a
# name, or a component's attribute other than a txt. Any other argument is
# refused, such as a text.
_OPERAND = expression(operand_pattern(("number",)))

# Each command's number, its table, and its arguments: add and addt a
# waveform's ID, a channel, and a value or a count; cle a waveform's ID and
# a channel. add has no number: its block starts with its name.
COMMANDS = {"T": {
    "add": Command(None, None, operands(_OPERAND, 3)),
    "addt": Command(0x15, 4, operands(_OPERAND, 3)),
    "cle": Command(0x02, 4, operands(_OPERAND, 2)),
}}
# K and P number addt their own ways, the others as T does. E numbers them
# as P does.
COMMANDS["K"] = renumbered(COMMANDS["T"], {"addt": 0x17})
COMMANDS["P"] = renumbered(COMMANDS["T"], {"addt": 0x1E})
# F numbers these its own way, in the same tables (ResearchNotes/tft/f-series.md).
COMMANDS["F"] = renumbered(COMMANDS["T"], {"addt": 0x1c})


def _covered(need) -> bool:
    """Whether the line of code `need` is one of these commands that the
    encoder encodes, on T. Each attribute the line refers to must be that of
    a component of the line's page whose type has it, as a number
    (statements.attribute_kind), so program.s, which has no page, takes
    none but another page's global's."""
    line = need.value.strip(" \t")
    # On F, the line may name only what F's tables hold.
    if need.series == "F" and not f_takes(line):
        return False
    return (command_name(line) in COMMANDS["T"] and encodable(line)
            and attributes_are_numbers(need, line))


# The series this module's probes matched (matching.py): T, K in k_probes.py,
# P in p_probes.py, E in e_probes.py, and F in f_probes.py.
SERIES = ("T", "K", "P", "E", "F")

MATCHED = [Rule("code", None, "add, addt, and cle, their operands numbers, hexadecimal numbers "
                "of 1 to 4 bytes, program.s's int variables, system variables, or, in an event, "
                "an attribute other than a txt of a component on its page, "
                "each argument one operand or several joined by the arithmetic "
                "operators; " + REFERENCE_WORDS + "; on T, K, P, E, and F, on F naming only "
                "what its tables hold (statements.f_takes)", _covered)]
