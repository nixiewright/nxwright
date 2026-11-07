"""The commands of files on the SD card that the P and E series have, and T
and K have not: newdir, deldir, delfile, refile, redir, newfile, findfile,
finddir, rdfile, and twfile, as the Nextion Editor 1.68.2 writes them on P
and E (ResearchNotes/tft/p-series.md). As the vendor's instruction set describes
them, newdir and deldir make and delete a folder, delfile deletes a file,
refile and redir rename a file and a folder, newfile makes a file of a
size, findfile and finddir give whether a file or a folder is there,
rdfile sends part of a file over the serial line, and twfile takes one
from it.

Each is a command of table 8, then its arguments between commas, each
encoded by the statement encoder (statements.py) as in any line:
`findfile "sd0/a.txt",n0.val` is 09 29 08, then `"sd0/a.txt"`, a comma,
and n0.val's operand. A path, and where findfile and finddir give their
answer, each take one operand of any kind, a text or a txt among them, but
no expression. Where a command takes a number, a size, a start, or a
count, it takes operands joined by the arithmetic operators, but no text
or txt.
"""
import re

from nxwright.tft.matching import Rule
from nxwright.tft.statements import (TEXT, Command, attributes_are_encoded, command_name, encodable,
                              expression, operand_pattern)

# A path, and where findfile and finddir give their answer: one operand of
# any kind, a text or a txt among them, as the Nextion Editor does not
# check an operand's kind there. It compiled `delfile 5`, `delfile n0.val`,
# `findfile "sd0/a.txt",t0.txt`, and `findfile "sd0/a.txt","b"`, and refused
# an expression ("Invalid Variables").
_ANY = r"(?:%s|%s)" % (operand_pattern(("number", "text")), TEXT)
# Where a command takes a number: operands joined by the arithmetic
# operators, each a hexadecimal number, a number, a name, or an attribute
# other than a txt. The Nextion Editor refused a text or a txt there
# ("Invalid variable operation").
_NUMBER = expression(operand_pattern(("number",)))


def _arguments(*places: str) -> str:
    """Returns the pattern of the arguments `places`, between commas, each
    comma followed by one space at most."""
    return ", ?".join(places)


# Each command's number, its table, and its arguments, on P.
COMMANDS = {"P": {
    "newdir": Command(0x14, 8, _ANY),
    "deldir": Command(0x13, 8, _ANY),
    "delfile": Command(0x18, 8, _ANY),
    "refile": Command(0x0B, 8, _arguments(_ANY, _ANY)),
    "redir": Command(0x03, 8, _arguments(_ANY, _ANY)),
    "newfile": Command(0x19, 8, _arguments(_ANY, _NUMBER)),
    "findfile": Command(0x29, 8, _arguments(_ANY, _ANY)),
    "finddir": Command(0x1E, 8, _arguments(_ANY, _ANY)),
    "rdfile": Command(0x0A, 8, _arguments(_ANY, _NUMBER, _NUMBER, _NUMBER)),
    "twfile": Command(0x0C, 8, _arguments(_ANY, _NUMBER)),
}}


def _covered(need) -> bool:
    """Whether the line of code `need` is one of these commands that the
    encoder encodes, on P. Each attribute the line refers to must be one
    the encoder encodes (statements.attributes_are_encoded), so program.s,
    which has no page, takes none of a page's own."""
    line = need.value.strip(" \t")
    if command_name(line) not in COMMANDS["P"] or not encodable(line, "P"):
        return False
    # Outside the texts between double quotes.
    return attributes_are_encoded(need, re.sub(TEXT, "", line))


# The series this module's probes matched (matching.py): P in p_probes.py,
# and E in e_probes.py.
SERIES = ("P", "E")

MATCHED = [Rule("code", None, "newdir, deldir, delfile, refile, redir, newfile, findfile, "
                "finddir, rdfile, and twfile: their paths, and findfile's and finddir's "
                "answer's destination, each one operand of any kind, a text of any characters"
                ", with the escapes \\\\, \\\", and \\r, a txt, or any operand below, but no "
                "expression, which the Nextion Editor refuses; where they "
                "take a number, one operand or several joined by the arithmetic operators, each "
                "a number, a hexadecimal number of 1 to 4 bytes, program.s's int variables, "
                "system variables, colours' names, or, in an event, an attribute other than a "
                "txt of a component on its page; in an event, and in program.s; on P and E",
                _covered)]
