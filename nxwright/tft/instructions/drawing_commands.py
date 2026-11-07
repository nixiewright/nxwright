"""The drawing commands: cls, fill, line, draw, cir, cirs, pic, picq, xpic,
and xstr, on the T, K, P, E, and F series, as the Nextion Editor 1.68.2
writes them (ResearchNotes/tft/drawing-commands.md).

Each is a command of table 4, its arguments between commas. Each argument
is a number, a hexadecimal number, an int variable of program.s, a system
variable, a colour's name, or, in an event, an attribute other than a txt
of a component of the line's page, as `cls t0.bco`. It may
also be such operands joined by the arithmetic operators, as an
assignment's value is. The statement encoder (statements.py) finds them
here and encodes them: `cls RED` is 09 06 04, then RED's operand, 04 04 01
00 00, and `cls RED+1` is the same, then `+1`. A space after a comma is
dropped, as the Nextion Editor drops it. The Nextion Editor checks no
picture's or font's ID against the project's, so neither does nxwright.tft.

xstr's last argument is a text, kept as written, its double quotes
included, or one operand, such as a txt:
`xstr 0,0,100,30,0,RED,WHITE,0,0,1,t0.txt` ends with t0.txt's operand. The
Nextion Editor refused texts joined there, as in `"a"+t0.txt` ("Invalid
Variables"), and so does nxwright.tft.
"""
import re

from nxwright.tft.matching import Rule
from nxwright.tft.statements import (REFERENCE_WORDS, TEXT, Command, attributes_are_encoded,
                              attributes_are_numbers, command_name, encodable, expression, f_takes,
                              operand_pattern, operands, renumbered)

# A command's argument: operands joined by the arithmetic operators, each a
# hexadecimal number, a number, its sign included, a name, or an attribute
# other than a txt, as the encoder reads them. Any other is refused, as the
# Nextion Editor refuses one it does not read, such as `5a`, `1_000`, or
# `-a` ("Invalid Variables"), and a txt ("Invalid variable operation").
_OPERAND = expression(operand_pattern(("number",)))
# xstr's text: a text, or one operand, a txt among them.
_TEXT_ARGUMENT = r"(?:%s|%s)" % (TEXT, operand_pattern(("number", "text")))

# Each command's number, and how many operands it takes: cls a colour; fill
# a place, a size, and a colour; line and draw two points and a colour; cir
# and cirs a centre, a radius, and a colour; pic a place and a picture; picq
# a place, a size, and a picture; xpic a place, a size, a place in the
# picture, and the picture; xstr a place, a size, a font, two colours, how
# the text is centred across and down, a fill, and the text.
COMMANDS = {"T": {
    "cls": Command(0x06, 4, operands(_OPERAND, 1)),
    "fill": Command(0x0D, 4, operands(_OPERAND, 5)),
    "line": Command(0x0C, 4, operands(_OPERAND, 5)),
    "draw": Command(0x1B, 4, operands(_OPERAND, 5)),
    "cir": Command(0x04, 4, operands(_OPERAND, 4)),
    "cirs": Command(0x14, 4, operands(_OPERAND, 4)),
    "pic": Command(0x01, 4, operands(_OPERAND, 3)),
    "picq": Command(0x0F, 4, operands(_OPERAND, 5)),
    "xpic": Command(0x0A, 4, operands(_OPERAND, 7)),
    "xstr": Command(0x12, 4, operands(_OPERAND, 10) + ", ?" + _TEXT_ARGUMENT),
}}
# K numbers picq, xstr, cirs, and draw its own way, the others as T does.
COMMANDS["K"] = renumbered(COMMANDS["T"], {"picq": 0x11, "xstr": 0x14, "cirs": 0x16, "draw": 0x1f})
# P numbers these its own way, in the same tables (ResearchNotes/tft/p-series.md).
COMMANDS["P"] = renumbered(COMMANDS["T"], {
    "fill": 0x0f, "line": 0x0d, "picq": 0x16, "xstr": 0x18, "cirs": 0x1a, "draw": 0x26})
# F numbers these its own way, in the same tables (ResearchNotes/tft/f-series.md).
COMMANDS["F"] = renumbered(COMMANDS["T"], {"draw": 0x22, "cirs": 0x18, "picq": 0x13,
                                         "xstr": 0x16})


def _covered(need) -> bool:
    """Whether the line of code `need` is one of these commands that the
    encoder encodes, on T. Each attribute the line refers to must be one
    the encoder encodes as a number on the line's page, but xstr's text,
    which may be a txt too (statements.attributes_are_numbers and
    attributes_are_encoded). So program.s, which has no page, takes
    none."""
    line = need.value.strip(" \t")
    # On F, the line may name only what F's tables hold.
    if need.series == "F" and not f_takes(line):
        return False
    name = command_name(line)
    if name not in COMMANDS["T"] or not encodable(line):
        return False
    numbers = re.sub(TEXT, "", line)
    if name == "xstr":
        numbers, _, text = numbers.rpartition(",")
        if not attributes_are_encoded(need, text):
            return False
    return attributes_are_numbers(need, numbers)


# The series this module's probes matched (matching.py): T, K in k_probes.py,
# P in p_probes.py, E in e_probes.py, and F in f_probes.py.
SERIES = ("T", "K", "P", "E", "F")

MATCHED = [Rule("code", None, "cls, fill, line, draw, cir, cirs, pic, picq, xpic, and xstr, "
                "their operands numbers, hexadecimal numbers of 1 to 4 bytes, program.s's int "
                "variables, system variables, colours' names, or, in an event, an attribute "
                "other than a txt of a component on its page, "
                "each argument one operand or several joined by the arithmetic operators; "
                "xstr's text one of any characters, with the "
                "escapes \\\\, \\\", and \\r, or one operand, an operand above "
                "or, in an event, the txt of a "
                "component on its page whose type gives code a txt; " + REFERENCE_WORDS
                + "; on T, K, P, E, and F, on F naming only what its tables hold "
                "(statements.f_takes)", _covered)]
