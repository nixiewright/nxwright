"""The device and serial buffer commands: rest, touch_j, code_c, ucopy, and
udelete, on the T, K, P, E, and F series, as the Nextion Editor 1.68.2 writes
them (ResearchNotes/tft/device-and-buffer-commands.md). As the vendor's instruction
set documents them, rest starts the screen again, touch_j calibrates its
touch panel, and code_c clears the instructions waiting in the serial
buffer. In protocol reparse mode, ucopy copies bytes of the serial buffer
into a destination: from a start, a count of them, to a place in the
destination. udelete deletes a count of the buffer's first bytes.

rest is a command of table 4, and the others of table 8. rest, touch_j,
and code_c take no argument. ucopy's and udelete's arguments are operands,
between commas, as the statement encoder (statements.py) encodes them in
any line: a number, a hexadecimal number, an int variable of program.s, a
system variable, a colour's name, or a component's attribute other than a
txt, such as a val or `t0.bco`. Where they take a number, several operands
may be joined by the arithmetic operators, as an assignment's value is:
`udelete sys0+1` is 09 11 08, sys0's operand, then `+1`. ucopy's
destination is one operand, and may also be a txt: `ucopy t0.txt,0,4,0` is
09 05 08, t0.txt's operand, then `,0,4,0`.

Where a command takes a number, the Nextion Editor refuses a text or a txt
("Invalid variable operation"), and so does nxwright.tft.
"""
from nxwright.tft.matching import Rule
from nxwright.tft.statements import (HEX_NUMBER, INDIRECT_HEAD, NAME, REFERENCE_WORDS, Command,
                              attributes_are_encoded, command_name, encodable, expression,
                              f_takes, operand_pattern, renumbered)

# Where a command takes a number: operands joined by the arithmetic
# operators, each a hexadecimal number, a number, its sign included, a name,
# or a component's attribute other than a txt. The Nextion Editor refuses a
# text or a txt there.
_NUMBER = expression(operand_pattern(("number",)))
# ucopy's destination: a name, or a component's attribute, a txt among them,
# another page's global component's, or one reached through the screen's
# arrays (statements.INDIRECT_HEAD); or a number, its sign included, or a
# hexadecimal number, each written as any operand. The Nextion Editor
# refused an expression there ("Invalid Variables"), which nxwright's build
# lets through.
_DESTINATION = r"(?:%s\.%s|%s(?:(?:\.%s)?\.%s)?|%s|-?[0-9]+)" % (
    INDIRECT_HEAD, NAME, NAME, NAME, NAME, HEX_NUMBER)

# Each command's number, its table, and its arguments: ucopy a destination,
# a start, a count, and a place in the destination; udelete a count.
COMMANDS = {"T": {
    "rest": Command(0x19, 4, ""),
    "touch_j": Command(0x14, 8, ""),
    "code_c": Command(0x06, 8, ""),
    "ucopy": Command(0x05, 8, ", ?".join([_DESTINATION, _NUMBER, _NUMBER, _NUMBER])),
    "udelete": Command(0x11, 8, _NUMBER),
}}
# K numbers rest, touch_j, and udelete its own way, the others as T does.
COMMANDS["K"] = renumbered(COMMANDS["T"], {"rest": 0x1d, "touch_j": 0x15, "udelete": 0x12})
# P numbers these its own way, in the same tables (ResearchNotes/tft/p-series.md).
COMMANDS["P"] = renumbered(COMMANDS["T"], {
    "ucopy": 0x06, "code_c": 0x07, "touch_j": 0x1d, "udelete": 0x1a, "rest": 0x24})
# F numbers these its own way, in the same tables (ResearchNotes/tft/f-series.md).
COMMANDS["F"] = renumbered(COMMANDS["T"], {"rest": 0x20, "touch_j": 0x15, "udelete": 0x12})


def _covered(need) -> bool:
    """Whether the line of code `need` is one of these commands that the
    encoder encodes, on T. Each attribute the line refers to must be one
    the encoder encodes (statements.attributes_are_encoded), so program.s,
    which has no page, takes none of a page's own."""
    line = need.value.strip(" \t")
    # On F, the line may name only what F's tables hold.
    if need.series == "F" and not f_takes(line):
        return False
    return (command_name(line) in COMMANDS["T"] and encodable(line)
            and attributes_are_encoded(need, line))


# The series this module's probes matched (matching.py): T, K in k_probes.py,
# P in p_probes.py, E in e_probes.py, and F in f_probes.py.
SERIES = ("T", "K", "P", "E", "F")

MATCHED = [Rule("code", None, "rest, touch_j, and code_c alone; ucopy and udelete, their "
                "operands numbers, hexadecimal numbers of 1 to 4 bytes, program.s's int "
                "variables, system variables, colours' names, or, in an event, an attribute "
                "other than a txt of a component on its page; where they take a number, one "
                "operand or several joined by the arithmetic operators; ucopy's destination "
                "one operand of these, or the txt of a component on its page whose type gives "
                "code a txt, but no expression, which the Nextion Editor refuses; "
                + REFERENCE_WORDS
                + "; on T, K, P, E, and F, on F naming only what its tables hold "
                "(statements.f_takes)", _covered)]
