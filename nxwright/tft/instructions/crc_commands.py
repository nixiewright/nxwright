"""The CRC commands: crcrest, crcputs, crcputh, and crcputu, on the T, K, P,
E, and F series, as the Nextion Editor 1.68.2 writes them (ResearchNotes/tft/
crc-commands.md). As the vendor's instruction set documents them, crcrest
starts a CRC of a type, 1 for Modbus CRC16, from a start value. crcputs
adds the bytes of a value, a length of 0 taking them all. crcputh adds
bytes written in hexadecimal, and crcputu bytes of the serial buffer, from
a start, a count of them. The system variable crcval gives the CRC.

Each is a command of table 8, then its arguments between commas. crcputh's
argument is kept as written, as printh's bytes are: `crcputh 0d 0a` is 09
13 08, then `0d 0a`. The others' arguments are values, as the statement
encoder (statements.py) encodes an assignment's: an operand, or operands
joined by the arithmetic operators. An operand is a number, an int variable
of program.s, a system variable, a colour's name, or a component's
attribute other than a txt, such as `t0.bco`. A
hexadecimal number, its digits in pairs, is 03 and its value, 4 bytes,
however small: `crcrest 1,0xFFFF` is 09 17 08, `1,`, then 03 ff ff 00 00.

crcputs' value may also be a text between double quotes or a txt, but not
operands joined: the Nextion Editor refused `crcputs 0x01+1,4` ("Invalid
Variables"), and so does nxwright.tft. Elsewhere the Nextion Editor refuses a text
or a txt ("Invalid variable operation"), and so does nxwright.tft.
"""
import re

from nxwright.tft.matching import Rule
from nxwright.tft.statements import (RAW_ARGUMENT, REFERENCE_WORDS, TEXT, Command, arrays_fit,
                              attribute_kind, command_name, encodable, expression, f_takes,
                              named_attributes, operand_pattern, renumbered)

# One operand where a command takes a number: a hexadecimal number, a
# number, its sign included, a name, or a component's attribute other than a
# txt. The Nextion Editor refuses a text or a txt there.
_NUMBER = operand_pattern(("number",))
# Where a command takes a number: such operands joined by the arithmetic
# operators.
_NUMBERS = expression(_NUMBER)
# crcputs' value: one operand as above, a component's txt, or a text.
_VALUE = r"(?:%s|%s)" % (operand_pattern(("number", "text")), TEXT)

# Each command's number, its table, and its arguments: crcrest a type and a
# start value; crcputs a value and how many of its bytes; crcputh its bytes;
# crcputu a start and a count.
COMMANDS = {"T": {
    "crcrest": Command(0x17, 8, _NUMBERS + ", ?" + _NUMBERS),
    "crcputs": Command(0x15, 8, _VALUE + ", ?" + _NUMBERS),
    # crcputh's argument is kept as written, in the project's encoding. The
    # Nextion Editor kept hexadecimal bytes between spaces as written, and
    # `3G` and a backspace too (ResearchNotes/tft/crc-commands.md).
    "crcputh": Command(0x13, 8, RAW_ARGUMENT, raw=True),
    "crcputu": Command(0x18, 8, _NUMBERS + ", ?" + _NUMBERS),
}}
# K numbers each one past T's number.
COMMANDS["K"] = renumbered(COMMANDS["T"], {"crcrest": 0x18, "crcputs": 0x16, "crcputh": 0x14,
                                           "crcputu": 0x19})
# P numbers these its own way, in the same tables (ResearchNotes/tft/p-series.md).
COMMANDS["P"] = renumbered(COMMANDS["T"], {
    "crcputh": 0x1c, "crcputs": 0x20, "crcrest": 0x24, "crcputu": 0x25})
# F numbers these its own way, in the same tables (ResearchNotes/tft/f-series.md).
COMMANDS["F"] = renumbered(COMMANDS["T"], {
    "crcrest": 0x18, "crcputs": 0x16, "crcputh": 0x14, "crcputu": 0x19})


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
    # crcputh's argument is kept as written, so it names no attribute.
    if command_name(line) == "crcputh":
        return True
    # Outside the texts between double quotes.
    return arrays_fit(need, line) and all(
        attribute_kind(need, attribute) is not None
        for attribute in named_attributes(re.sub(TEXT, "", line)))


# The series this module's probes matched (matching.py): T, K in k_probes.py,
# P in p_probes.py, E in e_probes.py, and F in f_probes.py.
SERIES = ("T", "K", "P", "E", "F")

MATCHED = [Rule("code", None, "crcrest, crcputs, crcputh, and crcputu, their operands numbers, "
                "hexadecimal numbers of 1 to 4 bytes, program.s's int variables, system "
                "variables, colours' names, or, in an event, an attribute other than a txt of "
                "a component on its page, each argument but crcputs' value one operand or "
                "several joined by the arithmetic operators; crcputs' value also a text of "
                "any characters, with the "
                "escapes \\\\, \\\", and \\r, or the txt "
                "of a component on its page whose type gives code a txt; crcputh's argument "
                "of any characters, kept as written; " + REFERENCE_WORDS
                + "; on T, K, P, E, and F, on F naming only what its tables hold "
                "(statements.f_takes)", _covered)]
