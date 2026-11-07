"""The undocumented commands the T and K series take: comok, draw3d,
draw_h, fstr, getpassw, getv, i, init, lcd_dev, lcd_refx, lhmi_cle, nstr,
qrcode, rfpt, setbaudz, setbrush, showqq, strsize, timerset, wfpt,
whmi_cle, and zstr, as the Nextion Editor 1.68.2 writes them
(ResearchNotes/tft/undocumented-commands.md); P, all but fstr, under numbers
of its own (ResearchNotes/tft/p-series.md); and F, all of them, under numbers of
its own, and piccolor, which F alone has (ResearchNotes/tft/f-series.md). The
vendor's instruction set does not give them. TFTTool's command tables name
them (INDEPENDENCE.md, Public documents), and the Nextion Editor compiles
them. nxwright's code checks give how many arguments each takes
(language/code_checks.py). What they do on the screen is not known.

Each is a command of table 4 or 8, its arguments between commas.
getpassw, lcd_refx, lhmi_cle, and showqq take none. Most arguments are
numbers: operands joined by the arithmetic operators, each a number, a
hexadecimal number, an int variable of program.s, a system variable, a
colour's name, or a component's attribute other than a txt, encoded as in
any line. The Nextion Editor refuses a text or a txt there ("Invalid
variable operation"). getv's argument, fstr's and nstr's first, zstr's
fifth, qrcode's eighth, and each of strsize's take one operand of any kind,
a text or a txt among them, but no operator ("Invalid Variables"):
`fstr "abc",sys0+1,0` is 09 10 04, then `"abc"`, a comma, sys0's operand,
`+1`, a comma, and `0`.

piccolor takes four: three numbers, then one operand of any kind, a text
or a txt among them, but no operator: `piccolor 0,0,0,sys0` is 09 22 08,
then `0,0,0,` and sys0's operand.

i takes four: two such operands, then two numbers. Its two operands must
be of one kind, two texts or two numbers: the Nextion Editor refuses a text
beside a number ("SYNTAX ERROR: Variable type does not match"), but not
beside one reached through the screen's arrays, which it does not check.

comok and lcd_dev keep their arguments as written, as printh does. comok
takes seven, between commas, and nxwright's build drops a space beside a
comma before the encoder sees the line: `comok 0, 0 ,0,0,0,0,"a b"` is
09 01 08, then `0,0,0,0,0,0,"a b"`. A space inside an argument stays, as
the Nextion Editor keeps it: `comok 0 1,0,0,0,0,0,0` is 09 01 08, then
`0 1,0,0,0,0,0,0`. lcd_dev takes one, of any
characters, as hexadecimal bytes between spaces, `sys0`, or `001`, kept
as written: `lcd_dev 01 02` is 09 19 08, then `01 02`.
"""
import re

from nxwright.tft.component_types import SERIES_WRITTEN_AS_P
from nxwright.tft.matching import Rule
from nxwright.tft.statements import (INDIRECT_HEAD, RAW_ARGUMENT, REFERENCE_WORDS, TEXT, Command,
                              attribute_kind, attributes_are_encoded, command_name, encodable,
                              expression, f_takes, operand_pattern, operands, renumbered)

# One operand of any kind, as the encoder reads it: a component's
# attribute, a txt among them, a hexadecimal number, a number, its sign
# included, a name, or a text. The Nextion Editor refused an expression.
_OPERAND = r"(?:%s|%s)" % (operand_pattern(("number", "text")), TEXT)
# Where a command takes a number: operands joined by the arithmetic
# operators, each a hexadecimal number, a number, its sign included, an
# attribute other than a txt, or a name.
_NUMBER = expression(operand_pattern(("number",)))
# One of comok's arguments, kept as written: texts between double quotes
# and other characters but a comma, of any kind, in the project's encoding.
# nxwright's build drops a space beside a comma or an operator, and keeps
# any other, which the Nextion Editor keeps too, as `comok 0 1,...` gave
# `0 1,...`.
_KEPT = r'(?:%s|[^,"])+' % TEXT


def _arguments(*places: str) -> str:
    """Returns the pattern of the arguments `places`, between commas, each
    comma followed by one space at most."""
    return ", ?".join(places)


# Each command's number, its table, and its arguments.
COMMANDS = {"T": {
    "comok": Command(0x01, 8, ",".join([_KEPT] * 7), raw=True),
    "draw3d": Command(0x07, 8, operands(_NUMBER, 7)),
    "draw_h": Command(0x0A, 8, operands(_NUMBER, 13)),
    "fstr": Command(0x10, 4, _arguments(_OPERAND, _NUMBER, _NUMBER)),
    "getpassw": Command(0x23, 8, ""),
    "getv": Command(0x1A, 4, _OPERAND),
    "i": Command(0x00, 4, _arguments(_OPERAND, _OPERAND, _NUMBER, _NUMBER)),
    "init": Command(0x16, 4, _NUMBER),
    # lcd_dev's argument is kept as written, in the project's encoding. The
    # Nextion Editor kept hexadecimal bytes between spaces as written, and
    # `sys0`, `0`, `0x01`, `001`, and `"x"` too
    # (ResearchNotes/tft/undocumented-commands.md).
    "lcd_dev": Command(0x19, 8, RAW_ARGUMENT, raw=True),
    "lcd_refx": Command(0x24, 8, ""),
    "lhmi_cle": Command(0x1A, 8, ""),
    "nstr": Command(0x11, 4, _arguments(_OPERAND, _NUMBER, _NUMBER)),
    "qrcode": Command(0x08, 8, _arguments(operands(_NUMBER, 7), _OPERAND)),
    "rfpt": Command(0x17, 4, operands(_NUMBER, 3)),
    "setbaudz": Command(0x25, 8, _NUMBER),
    "setbrush": Command(0x1C, 8, operands(_NUMBER, 15)),
    "showqq": Command(0x0D, 8, ""),
    "strsize": Command(0x12, 8, operands(_OPERAND, 3)),
    "timerset": Command(0x22, 8, operands(_NUMBER, 4)),
    "wfpt": Command(0x18, 4, operands(_NUMBER, 3)),
    "whmi_cle": Command(0x1B, 8, operands(_NUMBER, 2)),
    "zstr": Command(0x13, 4, _arguments(operands(_NUMBER, 4), _OPERAND)),
}}
# K numbers comok, draw3d, draw_h, i, and qrcode as T does, and the others
# its own way.
COMMANDS["K"] = renumbered(COMMANDS["T"], {
    "fstr": 0x12, "getpassw": 0x24, "getv": 0x1E, "init": 0x18, "lcd_dev": 0x1A,
    "lcd_refx": 0x25, "lhmi_cle": 0x1B, "nstr": 0x13, "rfpt": 0x1B, "setbaudz": 0x26,
    "setbrush": 0x1D, "showqq": 0x0E, "strsize": 0x13, "timerset": 0x23, "wfpt": 0x1C,
    "whmi_cle": 0x1C, "zstr": 0x15})
# P numbers them its own way, in the same tables, and lacks fstr, which the
# Nextion Editor refuses there ("Do not support such instruction for this
# series device"). It numbers comok and i as T does.
COMMANDS["P"] = renumbered({name: command for name, command in COMMANDS["T"].items()
                            if name != "fstr"}, {
    "draw3d": 0x08, "qrcode": 0x09, "draw_h": 0x0E, "showqq": 0x12, "nstr": 0x17,
    "zstr": 0x19, "strsize": 0x1B, "init": 0x1F, "rfpt": 0x22, "wfpt": 0x23, "getv": 0x25,
    "lcd_dev": 0x26, "lhmi_cle": 0x27, "whmi_cle": 0x28, "setbrush": 0x2A, "timerset": 0x31,
    "getpassw": 0x32, "lcd_refx": 0x33, "setbaudz": 0x34})
# F numbers these its own way, in the same tables (ResearchNotes/tft/f-series.md).
COMMANDS["F"] = renumbered(COMMANDS["T"], {
    "fstr": 0x14, "getpassw": 0x25, "getv": 0x21, "init": 0x1d, "lcd_dev": 0x1a,
    "lcd_refx": 0x26, "lhmi_cle": 0x1b, "nstr": 0x15, "rfpt": 0x1e, "setbaudz": 0x27,
    "setbrush": 0x1d, "showqq": 0x0e, "strsize": 0x13, "timerset": 0x24, "wfpt": 0x1f,
    "whmi_cle": 0x1c, "zstr": 0x17})
# piccolor, which F alone has: three numbers, then one operand of any kind,
# which may not be an expression ("Invalid Variables").
COMMANDS["F"]["piccolor"] = Command(0x22, 8, _arguments(operands(_NUMBER, 3), _OPERAND))


def init_block(object_id: int) -> bytes:
    """Returns the block of init on P with the object's ID `object_id`, as
    text: 09 1f 04, then `1` for ID 1. The Nextion Editor adds one to its
    page's load section, before the page's own load code, for each object of
    a type whose load_start gives one, such as a select
    (component_types/select.py) or a timer."""
    return COMMANDS["P"]["init"].block_start() + b"%d" % object_id


def _kind(need, argument: str):
    """Returns the kind of the operand `argument` of the line of code `need`:
    "text" for a text or a txt, "number" for any other, or None for one
    reached through the screen's arrays, whose kind the Nextion Editor does
    not check, or an attribute the encoder does not encode."""
    if argument.startswith('"'):
        return "text"
    if re.match(INDIRECT_HEAD, argument):
        return None
    return attribute_kind(need, argument) if "." in argument else "number"


def _of_one_kind(need, line: str) -> bool:
    """Whether i's first two arguments, in the line `line` of the code
    `need`, are of one kind, as the Nextion Editor checks them."""
    # Each argument runs to the next comma outside a text.
    first, second = (argument.strip() for argument in
                     re.findall(r"(?:%s|[^,\"])+" % TEXT, line[len("i"):])[:2])
    return len({_kind(need, first), _kind(need, second)} - {None}) <= 1


def _covered(need) -> bool:
    """Whether the line of code `need` is one of these commands that the
    encoder encodes, of the line's series' table, P's on E: on P and E, any
    but fstr. Each attribute the line refers to must be one the encoder
    encodes (statements.attributes_are_encoded), comok's kept as written
    among them, so program.s, which has no page, takes none of a page's
    own. i's first two arguments must be of one kind (_of_one_kind)."""
    line = need.value.strip(" \t")
    # On F, the line may name only what F's tables hold.
    if need.series == "F" and not f_takes(line):
        return False
    # A need of no series is taken for T's.
    series = "P" if need.series in SERIES_WRITTEN_AS_P else need.series or "T"
    if command_name(line) not in COMMANDS[series] or not encodable(line, series):
        return False
    if command_name(line) == "i" and not _of_one_kind(need, line):
        return False
    # lcd_dev's argument is kept as written, so it names no attribute.
    if command_name(line) == "lcd_dev":
        return True
    # Outside the texts between double quotes.
    return attributes_are_encoded(need, re.sub(TEXT, "", line))


# The series this module's probes matched (matching.py): T, K in k_probes.py,
# P in p_probes.py, E in e_probes.py, and F in f_probes.py.
SERIES = ("T", "K", "P", "E", "F")

MATCHED = [Rule("code", None, "comok, draw3d, draw_h, fstr, getpassw, getv, i, init, lcd_dev, "
                "lcd_refx, lhmi_cle, nstr, qrcode, rfpt, setbaudz, setbrush, showqq, strsize, "
                "timerset, wfpt, whmi_cle, and zstr, and on F piccolor, each with the number "
                "of arguments it takes: where a command takes a number, one operand or several "
                "joined by the arithmetic operators, each a number, a hexadecimal number of 1 "
                "to 4 bytes, program.s's int variables, a system variable, a colour's name, or, "
                "in an event, an attribute other than a txt of a component on its page; getv's "
                "argument, fstr's and nstr's first, zstr's fifth, qrcode's eighth, piccolor's "
                "fourth, and each of strsize's one such operand, or a text of any characters"
                ", with the escapes \\\\, \\\", and \\r, or a txt; i's "
                "first two such operands of one kind, two texts or two numbers, but for one "
                "reached through the screen's arrays, then two numbers; comok's seven "
                "arguments kept as written, of any kind, texts and other characters but a "
                "comma; "
                "lcd_dev's argument of any characters, kept as written; "
                + REFERENCE_WORDS
                + "; on T, K, and F, and on P and E but fstr, which they have not; on F, "
                "naming only what its tables hold (statements.f_takes)", _covered)]
