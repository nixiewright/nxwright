"""The statement encoder: a line of code into its block, or a run of lines
into theirs. It encodes operands, assignments, the arithmetic operators, and
the commands of a new project's program.s. The control statements and the
other commands are each a module of instructions/.

A run of lines, program.s's or an event's, gives its blocks in order
(encode_code): a line by encode_line, and a control statement, which spans
several lines, by its module, as one. Each is given the compile's context
(compile_context.py), which gives the project and its tables: the pages and
components that code names, and where each object's entries start.

A block is a line's parts, back to back, as the Nextion Editor 1.68.2 writes
them on the T series (ResearchNotes/tft/statements.md):

  - an operator, as its text: `sys0=sys1<<2` keeps `=` and `<<`, and
    `sys0*=-2` keeps `*=`;
  - a number of three characters at most, as written: `5`, `-99`, `007`. A
    longer one is 03, then its value, 4 bytes little-endian: `1000` is
    03 e8 03 00 00, and `0007` is 03 07 00 00 00;
  - a hexadecimal number, 1 to 4 bytes after any leading zeros, without a
    sign: 03, then its value, however small: `0x12` is 03 12 00 00 00;
  - an int variable of program.s: 05, then 4 for each variable declared
    before it, sys0 being the first: sys1 is 05 04 00 00 00;
  - a system variable, or a colour's name: 04, then its table, 4 or 8, its
    number in that table, and two 0 bytes: baud is 04 04 0e 00 00;
  - a component's attribute, in an event: 01, then the number of the
    attribute's entry, counted across the project (component_types'
    first_entries and code_entry), 4 bytes: t0.txt is 01 3d 00 00 00 when
    t0 is a page's first text. A global component of any page is named by
    its page's name too, as `page1.va0.val`, in an event or in program.s,
    and written the same way;
  - a component's attribute reached through the screen's arrays (INDIRECT),
    `b[1].txt` or `p[0].b[1].txt`: as written, compacted, but for its first
    index, which is written as an assignment's value: `b[sys0+1].txt` is
    `b[`, sys0's operand, then `+1].txt`. One by the page's name,
    `page1.b[sys0].txt`, is written whole as its text, compacted, its index
    included;
  - a text, between double quotes, of any characters, with a double
    quote or a backslash only in the escapes
    `\\\\`, `\\"`, and `\\r`: as written, in the project's encoding,
    quotes and escapes included: "Yo" is 22 59 6f 22, "a\\\\b" is
    22 61 5c 5c 62 22, "é" in iso-8859-1 is 22 e9 22, and "中" in gb2312
    is 22 d6 d0 22;
  - a command: 09, its number, its table, 4 or 8, then its arguments:
    `page 0` is 09 0b 04 30, and `page settings` 09 0b 04, then
    `settings`, a page's name kept as written. printh keeps its argument as
    written, its hexadecimal bytes in either case, spaces included. A
    command's component, a component of the line's page by name, is kept as
    written: `vis t0,0` is 09 05 04, then `t0,0`. Any other name is a
    variable's, written as its operand: `vis sys0,0` in program.s gives 05
    00 00 00 00 for sys0. Any other component is written as any number
    argument is, as an ID: `vis 1000,0` gives 03 e8 03 00 00 for 1000. One
    reached through the screen's arrays, `b[i]`, is written as a
    reference is (INDIRECT):
    `vis b[sys0],0` is 09 05 04, `b[`, sys0's operand, then `],0`. Each
    other argument is a value, as an assignment's: `cls RED+1` is 09 06 04,
    RED's operand, then `+1`. A command that takes no argument is its three
    bytes alone: `doevents` is 09 21 08;
  - a component's method's call, on P (METHOD_CALL): the method's operand,
    as an attribute's, then its arguments, as a command's, between
    parentheses: `fs0.close()` is 01, close's entry, then `()`.

Spaces are dropped elsewhere. A line that gives no block, an int
declaration, a comment, or one of spaces alone, gives None.

A line of any length is encoded. nxwright's build refuses a line longer
than the Nextion Editor compiles on the project's series.

An attribute in program.s is refused, as program.s has no page to look
the component up on, but for one of a global component named by its page.
The Nextion Editor refuses a local component of another page ("Invalid
Variables"), and so does the encoder. A reference through the screen's
arrays is looked up as the screen runs the line, so the encoder writes one
wherever it is.

Commands are found in this module's own, those of a new project's program.s,
then in each module of instructions/ that has COMMANDS: {series' letter:
{command's name: Command}}. Each series numbers its commands and variables
its own way, so each table is a series': T's, K's, P's, and F's are known,
and E's are P's. K and F write every block as T does, but for those numbers
(ResearchNotes/tft/k-series.md and f-series.md).
"""
from dataclasses import dataclass, replace
from functools import lru_cache
import importlib
import pkgutil
import re
import struct

from nxwright import NxwrightError
from nxwright.language.code_lines import compact
from nxwright.project.attribute_descriptions import code_cannot_change, describe
from nxwright.project.device_settings import TextCodec
from nxwright.project.editor_language import NAMES_THE_EDITOR_REFUSES
from nxwright.project.editor_limits import code_cannot_change_on_series
from nxwright.project.page_text import is_string_attribute

from nxwright.tft import component_types
from nxwright.tft.matching import Rule
from nxwright.tft.project import Project, program_variables


@dataclass(frozen=True)
class CodePlace:
    """What a line of code belongs to: program.s or a macro, which have no
    page, when `page` is None, or the event `event` (such as "up") of the
    object `object_name` on the page whose ID is `page`."""
    page: object = None
    object_name: str = None
    event: str = None


@dataclass(frozen=True)
class Command:
    """A command's number and its table, 4 or 8, both None for a command
    whose block starts with its name and a space, as add's does
    (instructions/waveform_commands.py); `arguments`, the pattern its
    arguments must match as written, such as a regular expression, "" for
    a command alone on its line, or None for any; whether they are kept as
    written (`raw`), as printh's argument, or else encoded as
    operands, between commas; whether an argument is a component
    (`component`): a component of the line's page, by name, kept as
    written, as in `vis t0,0`, a variable, written as its operand, as in
    `vis sys0,0`, or else written as any number argument is,
    as an ID, `vis 1000,0`, or operands joined by the arithmetic operators,
    `vis sys0+1,0`; which arguments, counted from 0
    (`component_places`): the first, unless the command gives others, as
    cfgpio gives its third in `cfgpio 2,1,n0`, and setlayer both of its
    two; and whether the argument is a page of the project, by its name,
    kept as written, or else a value, as an assignment's (`page`), as in
    `page main` and `page sys0+1`."""
    number: int
    table: int
    arguments: str = None
    raw: bool = False
    component: bool = False
    component_places: tuple = (0,)
    page: bool = False

    def block_start(self) -> bytes:
        """Returns the first three bytes of the command's block: 09, then
        its number, then its table. The block's arguments follow them. A
        command whose number is None, as add's, has no such bytes, so it
        must not be asked for them."""
        return bytes([COMMAND_TAG, self.number, self.table])


def operands(operand: str, count: int) -> str:
    """Returns the pattern of `count` arguments, each matching the pattern
    `operand`, between commas, each comma followed by one space at most.
    nxwright's build drops every space beside a comma, so the encoder meets
    none there from a project."""
    return operand + ("(?:, ?%s){%d}" % (operand, count - 1) if count > 1 else "")


def operand_pattern(kinds: tuple = ()) -> str:
    """Returns the pattern of one operand of a command, as the encoder reads
    it: a hexadecimal number, a number, its sign included, a name, or a
    component's attribute of one of `kinds`: "number", any attribute but a
    txt, such as `t0.bco`, and "text", a txt. An attribute may be another
    page's global component's, as `page1.va0.val`, or one reached through
    the screen's arrays (INDIRECT), as `b[2].val`, of the same names.
    Whether the component's type has the attribute, attribute_kind tells."""
    if not kinds:
        return r"(?:%s|-?[0-9]+|[A-Za-z_][A-Za-z0-9_]*)" % HEX_NUMBER
    attribute = r"\.(?:%s)" % "|".join(_ATTRIBUTE_NAMES[kind] for kind in kinds)
    return (r"(?:%s|-?[0-9]+|%s%s|[A-Za-z_][A-Za-z0-9_]*(?:(?:\.[A-Za-z_][A-Za-z0-9_]*)?%s)?)"
            % (HEX_NUMBER, INDIRECT_HEAD, attribute, attribute))


def expression(operand: str) -> str:
    """Returns the pattern of operands that each match the pattern
    `operand`, joined by the arithmetic operators, as `n0.val*2+1`. The
    Nextion Editor takes one where a command takes a number alone, and
    writes each operator as its text, as in an assignment. It refuses an
    operator right after another ("Invalid Variables"), as in `cls RED+*1`,
    which nxwright's build lets through, and so does the encoder, but for a
    minus before a number, which starts the number, as in `10+-5`."""
    return r"%s(?:(?:<<|>>|[-+*/%%&|^])%s)*" % (operand, operand)


def renumbered(commands: dict, numbers: dict) -> dict:
    """Returns `commands`, {name: Command}, with the number `numbers` gives a
    command by its name in place of its own: the same commands in the table
    of another series, which numbers some of them its own way."""
    return {name: replace(command, number=numbers.get(name, command.number))
            for name, command in commands.items()}


def command_name(line: str) -> str:
    """Returns the word `line` starts with, as the encoder reads a command's
    name: the word before the first space, or the whole line, stripped. It
    is a command when it is one of a module's COMMANDS."""
    return line.strip(" \t").split(" ", 1)[0]


class StatementError(NxwrightError):
    """A line the encoder does not encode. Its message says what."""


# The system variables and the colours' names of the T and K series, as
# (table, number). Every one the Nextion Editor 1.68.2 knows on T, each read
# into sys0 and set from it. K numbers 16 of table 4's system variables and
# two colours its own way, the others as T does. K also has system variables
# T has not, its GPIO pins', its PWM outputs', and its clock's, each read and
# set alike. The vendor does not document bcpu, tpdir, runmod, and portbusy:
# TFTTool's command tables name them (INDEPENDENCE.md, Public documents).
SYSTEM_VARIABLES = {"T": {
    "dp": (4, 0x00), "thc": (4, 0x02), "dim": (4, 0x03), "wup": (4, 0x04), "sya0": (4, 0x05),
    "tch0": (4, 0x06), "sya1": (4, 0x07), "tch1": (4, 0x08), "tch2": (4, 0x09),
    "tch3": (4, 0x0a), "rand": (4, 0x0d), "baud": (4, 0x0e), "thsp": (4, 0x0f),
    "ussp": (4, 0x10), "thup": (4, 0x11), "usup": (4, 0x12), "addr": (4, 0x13),
    "dims": (4, 0x14), "bcpu": (4, 0x15), "spax": (4, 0x16), "spay": (4, 0x17),
    "thdra": (8, 0x04), "appid": (8, 0x05), "bkcmd": (8, 0x06), "usize": (8, 0x07),
    "sleep": (8, 0x08), "tpdir": (8, 0x09), "bauds": (8, 0x0a), "delay": (8, 0x0b),
    "recmod": (8, 0x0d), "runmod": (8, 0x0e), "crcval": (8, 0x0f), "sendxy": (8, 0x10),
    "portbusy": (8, 0x11),
}}
SYSTEM_VARIABLES["K"] = {**SYSTEM_VARIABLES["T"],
    "tch0": (4, 0x07), "sya1": (4, 0x09), "tch1": (4, 0x0b), "tch2": (4, 0x0e),
    "tch3": (4, 0x11), "rand": (4, 0x20), "baud": (4, 0x21), "thsp": (4, 0x23),
    "ussp": (4, 0x24), "thup": (4, 0x25), "usup": (4, 0x26), "addr": (4, 0x27),
    "dims": (4, 0x28), "bcpu": (4, 0x29), "spax": (4, 0x2a), "spay": (4, 0x2b),
    "pio0": (4, 0x08), "pio1": (4, 0x0c), "pio2": (4, 0x0f), "pio3": (4, 0x12),
    "pio4": (4, 0x15), "pio5": (4, 0x18), "pio6": (4, 0x1b), "pio7": (4, 0x1d),
    "pwm4": (4, 0x14), "pwm5": (4, 0x17), "pwm6": (4, 0x1a), "pwm7": (4, 0x1c),
    "pwmf": (4, 0x22), "rtc0": (4, 0x06), "rtc1": (4, 0x0a), "rtc2": (4, 0x0d),
    "rtc3": (4, 0x10), "rtc4": (4, 0x13), "rtc5": (4, 0x16), "rtc6": (4, 0x19),
}
COLOURS = {"T": {
    "RED": (4, 0x01), "BLUE": (4, 0x0b), "GRAY": (4, 0x0c), "WHITE": (8, 0x00),
    "BLACK": (8, 0x01), "GREEN": (8, 0x02), "BROWN": (8, 0x03), "YELLOW": (8, 0x0c),
}}
COLOURS["K"] = {**COLOURS["T"], "BLUE": (4, 0x1e), "GRAY": (4, 0x1f)}
# P numbers most system variables and colours its own way, each read into
# sys0 and set from it alike (ResearchNotes/tft/p-series.md). It has every
# system variable the Nextion Editor knows but lowpower, among them the
# sound's, scache, tprc, and aph, which K has not.
SYSTEM_VARIABLES["P"] = {
    "dp": (4, 0x00), "eq0": (4, 0x01), "eq1": (4, 0x02), "eq2": (4, 0x03), "eq3": (4, 0x04),
    "eq4": (4, 0x05), "eq5": (4, 0x06), "eq6": (4, 0x07), "eq7": (4, 0x08), "eq8": (4, 0x09),
    "eq9": (4, 0x0a), "thc": (4, 0x0c), "aph": (4, 0x0d), "eqh": (4, 0x0e), "eql": (4, 0x0f),
    "dim": (4, 0x10), "eqm": (4, 0x11), "wup": (4, 0x12), "sya0": (4, 0x13), "rtc0": (4, 0x14),
    "tch0": (4, 0x15), "pio0": (4, 0x16), "sya1": (4, 0x17), "rtc1": (4, 0x18),
    "tch1": (4, 0x19), "pio1": (4, 0x1a), "rtc2": (4, 0x1b), "tch2": (4, 0x1c),
    "pio2": (4, 0x1d), "rtc3": (4, 0x1e), "tch3": (4, 0x1f), "pio3": (4, 0x20),
    "rtc4": (4, 0x21), "pwm4": (4, 0x22), "pio4": (4, 0x23), "rtc5": (4, 0x24),
    "pwm5": (4, 0x25), "pio5": (4, 0x26), "rtc6": (4, 0x27), "pwm6": (4, 0x28),
    "pio6": (4, 0x29), "pwm7": (4, 0x2a), "pio7": (4, 0x2b), "tprc": (4, 0x2e),
    "rand": (4, 0x2f), "baud": (4, 0x30), "pwmf": (4, 0x31), "thsp": (4, 0x32),
    "ussp": (4, 0x33), "thup": (4, 0x34), "usup": (4, 0x35), "addr": (4, 0x36),
    "dims": (4, 0x37), "bcpu": (4, 0x38), "spax": (4, 0x39), "spay": (4, 0x3a),
    "thdra": (8, 0x04), "appid": (8, 0x05), "bkcmd": (8, 0x06), "usize": (8, 0x07),
    "sleep": (8, 0x08), "tpdir": (8, 0x09), "bauds": (8, 0x0a), "delay": (8, 0x0b),
    "audio0": (8, 0x0c), "audio1": (8, 0x0d), "recmod": (8, 0x0f), "runmod": (8, 0x10),
    "scache": (8, 0x11), "volume": (8, 0x12), "crcval": (8, 0x13), "sendxy": (8, 0x14),
    "portbusy": (8, 0x15),
}
COLOURS["P"] = {
    "RED": (4, 0x0b), "BLUE": (4, 0x2c), "GRAY": (4, 0x2d), "WHITE": (8, 0x00),
    "BLACK": (8, 0x01), "GREEN": (8, 0x02), "BROWN": (8, 0x03), "YELLOW": (8, 0x0e),
}
# F knows every system variable and colour T does, each read into sys0 and
# set from it alike, and numbers 16 of the system variables and two colours
# its own way. It has the GPIO pins' system variables and lowpower too, as
# nxwright gives them to F, which T has not (ResearchNotes/tft/f-series.md).
SYSTEM_VARIABLES["F"] = {**SYSTEM_VARIABLES["T"],
    "sya1": (4, 0x08), "tch1": (4, 0x09), "tch2": (4, 0x0b), "tch3": (4, 0x0d),
    "rand": (4, 0x19), "baud": (4, 0x1a), "thsp": (4, 0x1c), "ussp": (4, 0x1d),
    "thup": (4, 0x1e), "usup": (4, 0x1f), "addr": (4, 0x20), "dims": (4, 0x21),
    "bcpu": (4, 0x22), "spax": (4, 0x23), "spay": (4, 0x24), "portbusy": (8, 0x12),
    "pio0": (4, 0x07), "pio1": (4, 0x0a), "pio2": (4, 0x0c), "pio3": (4, 0x0e),
    "pio4": (4, 0x10), "pio5": (4, 0x12), "pio6": (4, 0x14), "pio7": (4, 0x16),
    "pwm4": (4, 0x0f), "pwm5": (4, 0x11), "pwm6": (4, 0x13), "pwm7": (4, 0x15),
    "pwmf": (4, 0x1b), "lowpower": (8, 0x11),
}
COLOURS["F"] = {**COLOURS["T"], "BLUE": (4, 0x17), "GRAY": (4, 0x18)}
# A command's argument kept as written (Command.raw), as printh's,
# crcputh's, and lcd_dev's: any characters, the first and the last no space,
# as a line's arguments come stripped. They are written in the project's
# encoding. The Nextion Editor kept printh's hexadecimal bytes as written,
# and `printh 3G` too.
RAW_ARGUMENT = r"\S(?:.*\S)?"
# The commands of a new project's program.s, which K and F number as T does:
# `page`, with a page's name or a value, as an assignment's, in program.s or
# in an event, and printh, its argument kept as written. Others are
# instructions/'s.
_PROGRAM_COMMANDS = {
    "page": Command(0x0b, 4, page=True),
    "printh": Command(0x0b, 8, RAW_ARGUMENT, raw=True)}
COMMANDS = {"T": _PROGRAM_COMMANDS, "K": _PROGRAM_COMMANDS, "F": _PROGRAM_COMMANDS,
            "P": {"page": Command(0x0c, 4, page=True),
                  "printh": Command(0x0f, 8, RAW_ARGUMENT, raw=True)}}
# E numbers its system variables and its colours as P does, and its
# commands too (series_commands) (ResearchNotes/tft/e-series.md).
for _table in (SYSTEM_VARIABLES, COLOURS):
    _table["E"] = _table["P"]
_ARITHMETIC = ("+", "-", "*", "/", "%", "&", "|", "^", "<<", ">>")
# The assigning operators: `=`, and each arithmetic operator's own, such as
# `*=`, which the Nextion Editor writes as `+=` is written.
_ASSIGNING = ("=", "+=", "-=", "*=", "/=", "%=", "&=", "|=", "^=", "<<=", ">>=")
_STEPPING = ("++", "--")
# A name, as of a component, an attribute, a page, or an int variable.
NAME = r"[A-Za-z_][A-Za-z0-9_]*"
# A component's attribute: `t0.txt`, a component of the line's page, or
# `page1.va0.val`, a component of the page named before it, which must be
# global unless that page is the line's own (_attribute_entry).
ATTRIBUTE = r"(?:%s\.)?%s\.%s" % (NAME, NAME, NAME)
# A component's attribute reached through the screen's arrays: `b[i].name`,
# the component whose ID is i on the page the screen shows;
# `p[i].b[j].name`, the component j of the page i; or `page1.b[i].name`,
# the component i of the page named (PAGE_INDIRECT). The screen looks the
# component up as it runs the line. So the Nextion Editor checks no
# attribute's name and no kind, and writes the reference as its text,
# compacted, but for its first index after `b` or `p` (_indirect_operand). It
# refuses an index that holds another such reference: neither index holds a
# bracket.
PAGE_INDIRECT_HEAD = r"%s\.b\[[^\[\]]*\]" % NAME
INDIRECT_HEAD = r"(?:p\[[^\[\]]*\]\.|%s\.)?b\[[^\[\]]*\]" % NAME
INDIRECT = INDIRECT_HEAD + r"\.[A-Za-z_][A-Za-z0-9_]*"
# A reference by the page's name: the Nextion Editor writes it whole as its
# text, compacted, its index included, as it writes p[i].b[j]'s second index
# (ResearchNotes/tft/statements.md).
PAGE_INDIRECT = PAGE_INDIRECT_HEAD + r"\.[A-Za-z_][A-Za-z0-9_]*"
# A byte of the serial buffer, as `u[0]` or `u[sys1]`, read in protocol
# reparse mode (_serial_operand).
SERIAL_BUFFER = r"u\[[^\[\]]*\]"
# `b[i]` as a command's component, as `vis b[1],0`, its index written as a
# reference's first index. The Nextion Editor refuses a space in it, and
# `p[i].b[j]` there ("Invalid Component ID").
INDIRECT_COMPONENT = r"b\[[^\[\]\s]+\]"
# A component's method's call, as `fs0.read(t0.txt,0,3)`: the method, named
# as an attribute is, then its arguments between parentheses
# (_method_call_block).
METHOD_CALL = re.compile(r"(?P<method>%s)\((?P<arguments>.*)\)" % ATTRIBUTE, re.ASCII)
# A txt of a component of the line's page, or of another page's global one,
# as a method's argument: `t0.txt` or `page1.t0.txt`.
TXT = r"(?:%s\.)?%s\.txt" % (NAME, NAME)
_INDIRECT = re.compile(r"(?P<array>[bp])\[(?P<index>[^\[\]]*)\](?P<rest>.*)", re.ASCII)
# A hexadecimal number of 1 to 8 digits after any leading zeros, so no more
# than 4 bytes hold its value. A command takes one only if it includes it in
# its arguments' pattern.
HEX_NUMBER = r"0[xX]0*[0-9A-Fa-f]{1,8}"
# The names of a component's attributes of each kind, as operand_pattern
# takes them. A txt is the one text of the types nxwright knows. Any other
# attribute is a number, such as a txt_maxl.
_ATTRIBUTE_NAMES = {"number": r"(?!txt\b)[A-Za-z_][A-Za-z0-9_]*", "text": r"txt\b"}
# A text between double quotes: any characters, as each is written as its
# bytes; a double quote or a backslash only in the escapes `\\`, `\"`, and
# `\r`, as nxwright's build refuses any other escape. Which characters a
# project's encoding writes, the frame's rule of a line past ASCII checks
# ("text in code").
TEXT = r'"(?:[^"\\]|\\[\\"r])*"'
# The codec encodable writes a line's texts in, as no project gives one:
# utf-8, which writes every character TEXT takes.
_CHECKING_CODEC = TextCodec("utf-8")
# The words of a control statement's head, which are no names of a series'
# tables (_names_known). A name alone, outside an attribute.
_KEYWORDS = frozenset({"if", "else", "while", "for"})
_NAME_ALONE = re.compile(r"(?<![\w.])[A-Za-z_][A-Za-z0-9_]*(?![\w.\[])")
# A line's parts: a hexadecimal number, a number, a reference through the
# screen's arrays, a component's attribute, a name, a text, or an operator,
# the longest first. A hexadecimal number comes before a number, which would
# otherwise take its 0. A reference and an attribute come before a name,
# which would otherwise take their first letters.
_PART = re.compile(r"\s*(?:(?P<hex>%s)(?![0-9A-Za-z_])" % HEX_NUMBER
                   + r"|(?P<number>\d+)|(?P<indirect>%s)" % INDIRECT
                   + r"|(?P<serial>%s)" % SERIAL_BUFFER
                   + r"|(?P<attribute>%s)" % ATTRIBUTE
                   + r"|(?P<name>[A-Za-z_][A-Za-z0-9_]*)|(?P<text>%s)" % TEXT
                   + r"|(?P<operator><<=|>>=|<<|>>|\+\+|--|[-+*/%&|^]=|[-+*/%&|^=,]))", re.ASCII)
# The start of a line that sets a txt, as `t0.txt=` or `page1.va1.txt=`.
_TXT_TARGET = re.compile(r"(?:%s\.)?[A-Za-z_][A-Za-z0-9_]*\.txt\b" % NAME, re.ASCII)
# A component's attribute, as `t0.txt` or `page1.va0.val`.
_ATTRIBUTE = re.compile(ATTRIBUTE, re.ASCII)
_COMMAND_LINE = re.compile(r"(?P<name>[A-Za-z_][A-Za-z0-9_]*) (?P<arguments>.*)")
# A number this many characters long, or longer, is stored as its value.
LONG_NUMBER = 4
# The first byte of a system variable's or a colour's operand, of an int
# variable's, and of a command's block, and the bytes an int variable takes
# in program.s's area, by which its operand counts (the module's docstring).
# The decoder reads them too (decompiling/code.py).
SYSTEM_VARIABLE_TAG = 0x04
PROGRAM_VARIABLE_TAG = 0x05
COMMAND_TAG = 0x09
PROGRAM_VARIABLE_SIZE = 4


def encode_line(line: str, place: CodePlace, context) -> bytes:
    """Returns the block of `line`, which belongs to `place` in the
    project of `context`, a CompileContext, without its size word, or None
    when the line gives no block. Raises StatementError for a line it does
    not encode, saying why."""
    project = context.project
    series = project.settings.model.series
    if series not in SYSTEM_VARIABLES:
        raise StatementError("the %s series' code is not encoded yet" % series)
    if place.page is not None and line.strip(" \t").startswith("int "):
        raise StatementError("%r: the Nextion Editor refuses an int declaration in an event "
                             "(\"Error:Global variable definitions must precede all code "
                             "in the program.c\")" % line)
    # The names a command may give as its component: the page's own and its
    # components', none in program.s.
    components = () if place.page is None else context.component_names(place.page)
    return _block(line, series, context.program_variables,
                  lambda text: _attribute_entry(text, line, place, context), components,
                  context.page_names, project.codec)


def encode_code(lines: list, place: CodePlace, context) -> list:
    """Returns the blocks of a run of lines that belong to `place`, in
    order, each without its size word: program.s's lines, or an event's, as
    matching.code_lines gives them. A control statement's lines are taken
    together, by its module of instructions/; every other line gives its
    block through encode_line, or none. `context` is the compile's
    CompileContext. Raises StatementError for a line or a statement it does
    not encode."""
    blocks, at = [], 0
    statements = _control_statements()
    while at < len(lines):
        module = next((module for module in statements if module.starts_statement(lines[at])),
                      None)
        if module is None:
            block = encode_line(lines[at], place, context)
            if block is not None:
                blocks.append(block)
            at += 1
        else:
            found, at = module.encode_statement(lines, at, place, context, encode_code)
            blocks.extend(found)
    return blocks


def operand(text: str, place: CodePlace, context) -> bytes:
    """Returns the bytes of the one operand `text`, as encode_line gives it
    in a line that belongs to `place`, in the project of `context`, a
    CompileContext: a number, a hexadecimal number, an int variable, a
    system variable, a colour's name, a component's attribute, or one
    reached through the screen's arrays (INDIRECT). Raises StatementError
    for anything else."""
    return _one_operand(text, context.project, context.program_variables,
                        lambda attribute: _attribute_entry(attribute, text, place, context))


def drawing_operand(text: str, project: Project) -> bytes:
    """Returns the bytes of the one operand `text` of `project`, as operand
    gives it in program.s, for a component's drawing: a number, or a
    variable, such as sya0. Raises StatementError for an attribute, and for
    anything that is not one operand."""

    def refused(attribute: str) -> int:
        raise StatementError("%r: a drawing's operand is a number or a variable, not an "
                             "attribute" % attribute)

    return _one_operand(text, project, program_variables(project), refused)


def _one_operand(text: str, project: Project, variables: list, attribute_entry) -> bytes:
    """Returns the bytes of the one operand `text` of `project`, whose
    program.s declares the int variables `variables`. `attribute_entry`
    gives the number of an attribute's entry (operand)."""
    series = project.settings.model.series
    if series not in SYSTEM_VARIABLES:
        raise StatementError("the %s series' code is not encoded yet" % series)
    parts = _parts(text)
    if (len(parts) != 1
            or parts[0][0] not in ("number", "hex", "name", "attribute", "indirect",
                                   "serial")):
        raise StatementError("%r is not one operand" % text)
    return _operand(parts[0], series, variables, attribute_entry, project.codec)


def _attribute_entry(text: str, line: str, place: CodePlace, context) -> int:
    """Returns the number of the entry of the attribute `text`, for `line`,
    which holds it and belongs to `place`: such as t0.txt, of a component of
    the line's page, or page1.va0.val, of a component of the page named.
    Raises StatementError for a local component of another page, which the
    Nextion Editor refuses ("Invalid Variables"), and for a component named
    without its page in program.s, which has none."""
    project = context.project
    *page_name, object_name, attribute = text.split(".")
    number = place.page
    if page_name:
        number = context.page_number(page_name[0])
        if number is None:
            raise StatementError("%r: the project has no page %s" % (line, page_name[0]))
    if number is None:
        raise StatementError("%r: the Nextion Editor refuses an attribute in program.s "
                             "without its page (\"Invalid Variables\", or \"Invalid Page ID\" "
                             "for page)" % line)
    found = context.component(number, object_name)
    if found is not None and found is project.pages[number].objects[0]:
        try:
            entry = page_code_entry(found, attribute, project.settings.model.series)
        except KeyError:
            raise StatementError("%r: the page %s's %s is not encoded"
                                 % (line, object_name, attribute)) from None
        return context.first_entries[(number, object_name)] + entry
    module = found is not None and component_types.object_module(found)
    if not module:
        raise StatementError("%r: %s is no component nxwright knows on the page"
                             % (line, object_name))
    if number != place.page and not component_types.is_global(found):
        raise StatementError("%r: the Nextion Editor refuses the local component %s of another "
                             "page (\"Invalid Variables\")" % (line, object_name))
    try:
        entry = component_types.code_entry(module, found, attribute,
                                           project.settings.model.series)
    except KeyError:
        raise StatementError("%r: %s's %s is not encoded" % (line, object_name, attribute))
    return context.first_entries[(number, object_name)] + entry


# The entries a page's own attributes have on T, K, and F, by name: those
# every object has (component_types.object_entries), its sta, and its
# background, its bco or its pic by its sta
# (component_types.PAGE_BACKGROUND_NAMES), as the frame writes them
# (frame._page_entries). An effect moves the last two two on
# (component_types.page_entry). Code names one by its entry, as a
# component's: `sys0=page0.x` gave 01 09 00 00 00.
_PAGE_CODE_ENTRIES = {"type": 0, "id": 1, "vscope": 3, "x": 9, "y": 10, "w": 11,
                      "h": 12, "endx": 13, "endy": 14, "sta": 23}
# A page's effect, first, and time, and its swipe targets, as code names them
# on T, K, and F: by the entries P gives them, though the frame writes no
# entry of them on these series. An effect moves the swipe targets two on,
# as it moves the sta. The screen holds none of them, and reads 0
# (nxwright's editor_limits.py), but the Nextion Editor compiles code that
# names them.
_PAGE_EFFECT_CODE_ENTRIES = {"effect": 15, "first": 16, "time": 17}
_PAGE_SWIPE_CODE_ENTRIES = {"up": 19, "down": 20, "left": 21, "right": 22}


def page_code_entry(page, name: str, series: str) -> int:
    """Returns the number, among the page `page`'s own entries on `series`,
    of the entry of its attribute `name`, as code names it: on P and E, by
    the names of the entries the frame writes there
    (component_types.p_page_named_entries); on T, K, and F, by
    _PAGE_CODE_ENTRIES and its background's, which the frame writes, and by
    P's entries of its effect and swipe targets, which it does not. Raises
    KeyError for an attribute the page has no entry of, which nxwright cannot
    write."""
    if series in component_types.SERIES_WRITTEN_AS_P:
        return component_types.p_page_named_entries(page)[name]
    if name in _PAGE_EFFECT_CODE_ENTRIES:
        return _PAGE_EFFECT_CODE_ENTRIES[name]
    if name in _PAGE_SWIPE_CODE_ENTRIES:
        moved = component_types.EFFECT_ENTRIES * component_types.has_effect(page)
        return _PAGE_SWIPE_CODE_ENTRIES[name] + moved
    if name in _PAGE_CODE_ENTRIES:
        number = _PAGE_CODE_ENTRIES[name]
    elif name == component_types.PAGE_BACKGROUND_NAMES.get(component_types.page_sta(page)):
        number = component_types.PAGE_BACKGROUND_ENTRY
    else:
        raise KeyError(name)
    return component_types.page_entry(page, number)


def past_ascii_covered(need) -> bool:
    """Whether the line of code `need`, which holds a character past ASCII
    outside a comment, is one nxwright writes in its encoding, `need`'s
    subject (matching.py, "text in code"): each of its characters is one
    the encoding writes. The Nextion Editor misreads some texts in an
    encoding of two-byte characters, by their bytes, and refuses them, but
    nxwright's build refuses those first. The line's own rule checks the
    rest."""
    codec, line = component_types.codec_of(need.subject), need.value.strip(" \t")
    try:
        codec.encode(line, line)
    except NxwrightError:
        return False
    return True


def encodable(line: str, series: str = "T") -> bool:
    """Whether encode_line encodes `line` on `series`, as far as the line
    itself tells: any name not a system variable or a colour is taken for an
    int variable of program.s, which nxwright's build checks is declared."""
    try:
        _block(line, series, None, codec=_CHECKING_CODEC)
    except StatementError:
        return False
    return True


def encodable_operand(text: str) -> bool:
    """Whether `text` is one operand, a number, a hexadecimal number, a
    name, a byte of the serial buffer (SERIAL_BUFFER), or a component's
    attribute, that encode_line encodes on T, as far as the text itself
    tells, as encodable does. Whether an attribute is one the encoder
    encodes, attribute_kind tells."""
    try:
        parts = _parts(text)
        if len(parts) != 1 or parts[0][0] not in ("number", "hex", "name", "serial",
                                                  "attribute"):
            return False
        _operand(parts[0], "T", None, codec=_CHECKING_CODEC)
    except StatementError:
        return False
    return True


def _block(line: str, series: str, variables, attribute_entry=None, components=None,
           pages=None, codec=None) -> bytes:
    """Returns the block of `line` on `series`, or None, as encode_line does.
    `variables` are program.s's int variables in order, or None to take any
    name for one. `attribute_entry` gives an attribute's entry number, or is
    None to take any attribute, as encodable does. `components` are the
    names of the components a command may name, or None to take any.
    `pages` are the names of the project's pages, or None, which takes a
    name `page` gives for a variable. `codec` writes the line's texts, the
    project's (Project.codec)."""
    stripped = line.strip(" \t")
    if not stripped or stripped.startswith("//") or stripped.startswith("int "):
        return None
    # A command alone on its line, as doevents.
    if stripped in series_commands(series):
        return _command_block(stripped, "", series, variables, attribute_entry, components,
                              pages, codec)
    # A command's name and its arguments are apart by a space, as an
    # assignment's parts may be too: `dim = 50`.
    command = _COMMAND_LINE.fullmatch(stripped)
    if command is not None and command.group("name") in series_commands(series):
        return _command_block(command.group("name"), command.group("arguments"), series,
                              variables, attribute_entry, components, pages, codec)
    call = METHOD_CALL.fullmatch(stripped)
    if call is not None:
        return _method_call_block(call, series, variables, attribute_entry, codec)
    return _assignment_block(_parts(stripped), series, variables, attribute_entry, codec)


def covers_line(need) -> bool:
    """Whether MATCHED covers the line of code `need`, as it covers any line
    (_covered). A control statement's module asks it of a part it encodes
    as a line of its own, as a for's start."""
    return _covered(need)


def _covered(need) -> bool:
    """Whether MATCHED covers the line of code `need`: a line encode_line
    encodes, other than an int declaration and a command of instructions/.
    Each attribute the line refers to must be one encoded as a number
    (attribute_kind), and one it sets one code can change
    (sets_only_changeable_attributes). A line with a text, or one that sets
    a txt or another text, as a path, must set it as the encoder writes
    one (_text_assignment_covered).
    In program.s, the frame reads a declaration, so its list covers those it
    reads; in an event, the Nextion Editor refuses one. A command of instructions/ is
    its module's to cover, by its own MATCHED. On P, the line must be one of
    P's own commands of this module's table (_covered_on_p), or one T's
    rules cover that names only what P's tables hold (p_takes)."""
    line = need.value.strip(" \t")
    if line.startswith("int "):
        return False
    # A comment gives no block, whatever it holds.
    if line.startswith("//"):
        return True
    written_as_p = need.series in component_types.SERIES_WRITTEN_AS_P
    # printh keeps its argument as written, so nothing in it is read as a
    # text, an attribute, or a name.
    if command_name(line) == "printh":
        return encodable(line, "P" if written_as_p else "T")
    if written_as_p:
        return _covered_on_p(need, line) or (p_takes(line) and _covered_as_on_t(need, line))
    if need.series == "F":
        return _covered_on_f(need, line)
    return _covered_as_on_t(need, line)


def _covered_on_f(need, line: str) -> bool:
    """Whether the line `line` of the code `need` is one nxwright writes on F:
    one T's rules cover (_covered_as_on_t) whose names F's tables hold
    (f_takes). T's rules check a component's attribute and a text as on T;
    the attribute is of a type nxwright writes on F, as the check refuses any
    other type there."""
    return f_takes(line) and _covered_as_on_t(need, line)


def _covered_as_on_t(need, line: str) -> bool:
    """Whether the line `line` of the code `need` is one T's and K's probes
    showed (_covered)."""
    name = command_name(line)
    if name not in COMMANDS["T"] and name in series_commands("T"):
        return False
    # A method's call is its type's to cover, as a file stream's
    # (component_types/file_stream.py).
    if METHOD_CALL.fullmatch(line):
        return False
    if not sets_only_changeable_attributes(need, line):
        return False
    if refers_through_arrays(line):
        if name == "page":
            return _page_reference_covered(need, line)
        return indirect_covered(need)
    if _holds_a_text(line) or _TXT_TARGET.match(line) or _sets_a_text(need, line):
        return _text_assignment_covered(need, line)
    return attributes_are_numbers(need, line) and encodable(line)


def _holds_a_text(line: str) -> bool:
    """Whether `line` holds a text among its own parts, not only inside an
    index, as `sys0=u["a"]` does. A line the encoder cannot read is taken
    for one, as a quote in it may start a text."""
    try:
        return any(kind == "text" for kind, _ in _parts(line))
    except StatementError:
        return '"' in line


def _sets_a_text(need, line: str) -> bool:
    """Whether the line `line` of the code `need` starts with an attribute
    the encoder encodes as a text, as a path: `xp0.path=t0.txt`. A txt's
    line _TXT_TARGET finds."""
    target = _ATTRIBUTE.match(line)
    return target is not None and attribute_kind(need, target.group(0)) == "text"


def p_takes(code: str) -> bool:
    """Whether the code `code`, a line or a control statement's head, names
    only what P's tables hold, so that a rule of T and K covers it on P
    too:
      - names that are P's system variables or colours, or else int
        variables. A name the Nextion Editor gives a system variable, but
        P's table does not hold, as lowpower, is left out. Components'
        attributes are T's rules' to check, as on T;
      - no command of T's tables."""
    return command_name(code) not in series_commands("T") and _names_known(code, "P")


def f_takes(code: str) -> bool:
    """Whether the code `code`, a line or a control statement's head, names
    only what F's tables hold, so that a rule of T covers it on F too: F's
    system variables and colours, or else int variables (_names_known). F's
    tables hold every system variable nxwright gives F, so it refuses only
    names that nxwright's build refuses on F too, as P's lacked ones are on
    P (p_takes). Components' attributes are T's rules' to check, as on T."""
    return _names_known(code, "F")


def _names_known(code: str, series: str) -> bool:
    """Whether each name the code `code` holds alone, outside its texts and
    its attributes, is one `series` knows: its system variables and colours,
    or else an int variable (p_takes, f_takes)."""
    bare = re.sub(TEXT, '""', code)
    names = _NAME_ALONE.findall(re.sub(ATTRIBUTE, "", bare))
    return all(word in _KEYWORDS or word in SYSTEM_VARIABLES[series] or word in COLOURS[series]
               or word not in NAMES_THE_EDITOR_REFUSES for word in names)


def _covered_on_p(need, line: str) -> bool:
    """Whether the line `line` of the code `need` is `page`, the other of P's
    own commands of this module's table beside printh (_covered), in every
    form T's rule takes, by number, by name, by variable, of any value, and
    with a reference through the screen's arrays or to another page's
    global (_covered_as_on_t)."""
    return (command_name(line) == "page" and _names_known(line, "P")
            and _covered_as_on_t(need, line))


def _text_assignment_covered(need, line: str) -> bool:
    """Whether the line of `need` sets a txt, or another text such as a
    path, as the encoder writes one. It is then set with `=`, or added to with
    `+=`, texts and txts joined with `+`; or cut with `-=` and one number of
    characters: a number, a hexadecimal number, a variable, a colour's name,
    or an attribute the encoder encodes as a number. Each txt must be one the encoder encodes as
    a text (attribute_kind), and each text one the encoder reads (TEXT)."""
    try:
        parts = _parts(line)
    except StatementError:
        return False
    if (len(parts) < 3 or parts[0][0] != "attribute"
            or attribute_kind(need, parts[0][1]) != "text"):
        return False
    operator, values = parts[1], parts[2:]
    if operator == ("operator", "-="):
        kind, text = values[0] if len(values) == 1 else (None, None)
        return ((kind in ("number", "hex", "name")
                 or (kind == "attribute" and attribute_kind(need, text) == "number"))
                and encodable(line))
    # nxwright's build refuses a txt named on its page set with another
    # operator, as `t0.txt*=2`, so no project the check sees holds one.
    count_fits = operator in (("operator", "="), ("operator", "+=")) and len(values) % 2 == 1
    return (count_fits and all(part == ("operator", "+") for part in values[1::2])
            and all(part[0] == "text"
                    or (part[0] == "attribute" and attribute_kind(need, part[1]) == "text")
                    for part in values[0::2])
            and encodable(line))


def refers_through_arrays(line: str) -> bool:
    """Whether `line` holds a component's attribute reached through the
    screen's arrays (INDIRECT) among its parts, outside its texts."""
    try:
        return any(kind == "indirect" for kind, _ in _parts(line))
    except StatementError:
        return False


def _page_reference_covered(need, line: str) -> bool:
    """Whether `line`, `page` with a value that refers to a component's
    attribute through the screen's arrays, is one the encoder writes. The
    value is operands joined by the arithmetic operators, as an
    assignment's (encodable). Each attribute must be one encoded as a
    number, and in program.s each reference must name its page
    (attributes_are_numbers). A reference may name any attribute, a txt
    among them, which the Nextion Editor compiled as `page b[1].txt`. It
    must not hold a space, which the Nextion Editor refused there
    ("Invalid Page ID")."""
    try:
        parts = _parts(line[len("page"):])
    except StatementError:
        return False
    references = [text for kind, text in parts if kind == "indirect"]
    return (all(re.search(r"\s", text) is None for text in references)
            and attributes_are_numbers(need, line) and encodable(line))


def indirect_covered(need) -> bool:
    """Whether the line of code `need`, on T, K, P, or F, refers to a
    component's attribute through the screen's arrays (INDIRECT), in an
    assignment the encoder writes (_covered). On P, p_takes must take the
    line first. A command with one is its own module's to cover, and `page`
    with one _page_reference_covered's.

    Such a reference is of either kind, as the Nextion Editor knows no kind
    of it (_part_kind):
      - a line that sets one takes a value of any operands joined by the
        arithmetic operators, or `++` or `--`;
      - a line that sets a variable, or an attribute of a number, takes
        numbers and references, joined by the arithmetic operators;
      - a line that sets a txt takes texts, txts, and references, joined
        by `+`, or one number or reference that `-=` cuts.
    Each attribute of the page's components the line names, its references'
    indexes' included, must be one the encoder encodes, and an index's a
    number. In program.s, which has no page to look a component up on, the
    Nextion Editor refuses `b[i]` alone, and takes `p[i].b[j]` and
    `page1.b[i]`; so does a macro here, which has no page either."""
    line = need.value.strip(" \t")
    if (not refers_through_arrays(line) or command_name(line) in series_commands("T")
            or not sets_only_changeable_attributes(need, line)):
        return False
    try:
        parts = _parts(line)
    except StatementError:
        return False
    references = [text for kind, text in parts if kind == "indirect"]
    if need.subject != "event" and not all(names_its_page(text) for text in references):
        return False
    if not all(attributes_are_numbers(need, text) for text in references):
        return False
    if len(parts) < 2 or parts[0][0] not in ("name", "attribute", "indirect"):
        return False
    target, operator, values = parts[0], parts[1], parts[2:]
    if operator in (("operator", step) for step in _STEPPING):
        return not values and encodable(line)
    if (operator not in (("operator", assigning) for assigning in _ASSIGNING)
            or len(values) % 2 == 0):
        return False
    kinds, joins = [_part_kind(need, part) for part in values[0::2]], values[1::2]
    if None in kinds or not all(join in (("operator", arithmetic) for arithmetic in _ARITHMETIC)
                                for join in joins):
        return False
    wanted = ("any" if target[0] == "indirect" else "number" if target[0] == "name"
              else attribute_kind(need, target[1]))
    return _value_fits(wanted, operator[1], kinds, joins) and encodable(line)


def _value_fits(wanted: str, operator: str, kinds: list, joins: list) -> bool:
    """Whether a value of operands of `kinds`, joined by `joins`, fits a
    target of the kind `wanted`, set with `operator`, in a line that refers
    through the screen's arrays (indirect_covered): any value for a
    reference; no text for a number; and for a txt, set with `=` or `+=`, no
    number joined by `+`, or one number or reference that `-=` cuts."""
    if wanted == "number":
        return "text" not in kinds
    if wanted == "text" and operator not in ("=", "+=", "-="):
        return False
    if wanted == "text" and operator == "-=":
        return len(kinds) == 1 and kinds[0] in ("number", "any")
    if wanted == "text":
        return "number" not in kinds and all(join == ("operator", "+") for join in joins)
    return wanted == "any"


def _part_kind(need, part: tuple):
    """Returns the kind of the operand `part`, as (kind, text) in the line of
    code `need`: "number" for a number, a hexadecimal number, or a name;
    "text" for a text; an attribute's kind (attribute_kind); "any" for a
    reference through the screen's arrays, whose kind the Nextion Editor
    does not know; or None for one the encoder does not encode."""
    kind, text = part
    if kind in ("number", "hex", "name", "serial"):
        return "number"
    if kind == "text":
        return "text"
    if kind == "attribute":
        return attribute_kind(need, text)
    return "any" if kind == "indirect" else None


def attribute_kind(need, attribute: str):
    """Returns how the encoder encodes `attribute`, such as n0.val, in the
    line of code `need`: as a "number" or a "text", or None when it does not
    encode it there. It encodes the attribute of a component of the line's
    page, which the need's context gives (matching.py), when what describes
    the component gives the attribute's entry on the need's series
    (component_types.code_entry and object_module), and a page's own
    attribute whose entry it knows (page_code_entry), as a number. It does
    not encode, in program.s, a component's without its page
    (named_component)."""
    page_object, name = named_component(need, attribute)
    if page_object is not None and component_types.type_name(page_object) == "page":
        try:
            page_code_entry(page_object, name, need.series)
        except KeyError:
            return None
        return "number"
    module = None if page_object is None else component_types.object_module(page_object)
    if module is None:
        return None
    try:
        component_types.code_entry(module, page_object, name, need.series)
    except KeyError:
        return None
    return "text" if is_string_attribute(page_object.attribute("type")[0], name) else "number"


def named_component(need, attribute: str) -> tuple:
    """Returns the component that `attribute`, such as n0.val or
    page1.va0.val, names in the line of code `need`, or None, and the
    attribute's name. That is a component of the line's page, or a global
    component of the page named before it (the context's globals,
    matching.py). In program.s, which has no page, it is a global one alone.
    With `need` None, it is none."""
    *page_name, object_name, name = attribute.split(".")
    context = need.context if need is not None else {}
    if not page_name and object_name == context.get("page"):
        return context.get("page_object"), name
    if not page_name or page_name[0] == context.get("page"):
        return context.get("objects", {}).get(object_name), name
    return context.get("globals", {}).get((page_name[0], object_name)), name


def attributes_are_numbers(need, text: str) -> bool:
    """Whether each component's attribute that `text`, a line of code or a
    part of one, refers to is one attribute_kind gives as a number in the
    line of code `need`, and each reference through the screen's arrays one
    the line may hold (arrays_fit). With `need` None, whether `text` refers
    to none."""
    return arrays_fit(need, text) and all(
        need is not None and attribute_kind(need, attribute) == "number"
        for attribute in named_attributes(text))


def is_a_variable(need, name: str) -> bool:
    """Whether `name` is a variable in the line of code `need`: a system
    variable or a colour of its series, or an int variable of program.s
    (matching.py gives them)."""
    return (name in SYSTEM_VARIABLES.get(need.series, {}) or name in COLOURS.get(need.series, {})
            or name in need.context.get("variables", ()))


def component_taken(need, component: str) -> bool:
    """Whether `component`, a command's argument where a component goes, is
    the line of code `need`'s page or one of its components, by name
    (matching.py gives them), or else a variable (is_a_variable), written
    as its operand; in an event, one reached through the screen's arrays
    (INDIRECT_COMPONENT); or else operands, as an ID."""
    if re.fullmatch(INDIRECT_COMPONENT, component):
        return need.subject == "event"
    if re.fullmatch(NAME, component):
        return (component in need.context.get("components", {})
                or component == need.context.get("page") or is_a_variable(need, component))
    return True


def attributes_are_encoded(need, text: str) -> bool:
    """Whether each component's attribute that `text`, a line of code or a
    part of one, refers to is one attribute_kind gives as a number or a
    text in the line of code `need`, and each reference through the
    screen's arrays one the line may hold (arrays_fit). With `need` None,
    whether `text` refers to none."""
    return arrays_fit(need, text) and all(
        need is not None and attribute_kind(need, attribute) is not None
        for attribute in named_attributes(text))


def method_call_covered(need, type_name: str, arguments: dict) -> bool:
    """Whether the line of code `need` is a call (METHOD_CALL) of a method of
    a component of its page whose type is `type_name`, that the encoder
    encodes. `arguments`, {method: pattern}, gives the pattern each method's
    arguments must match. Each attribute the line refers to outside its
    texts must be one the encoder encodes (attributes_are_encoded)."""
    line = need.value.strip(" \t")
    call = METHOD_CALL.fullmatch(line)
    if call is None:
        return False
    page_object, method = named_component(need, call.group("method"))
    if (page_object is None or component_types.type_name(page_object) != type_name
            or method not in arguments):
        return False
    return (re.fullmatch(arguments[method], call.group("arguments")) is not None
            and encodable(line, "P") and attributes_are_encoded(need, re.sub(TEXT, "", line)))


# Describes, in the rules of the commands, the attributes that
# operand_pattern takes beyond a component's on the line's page.
REFERENCE_WORDS = ("an attribute may be another page's global component's, named by its page, "
                   "or one reached through the screen's arrays, `b[i]`, `p[i].b[j]`, or "
                   "`page1.b[i]`, by the page's name, and in program.s `p[i].b[j]` or "
                   "`page1.b[i]` alone")


def arrays_fit(need, text: str) -> bool:
    """Whether each reference through the screen's arrays that `text` holds,
    outside its texts, may be in the line of code `need`. In an event, any
    may be, but one by the name of the line's own page, which nxwright's
    build refuses first.
    In program.s or a macro, which have no page of their own, only one that
    names its page may be (names_its_page), as the Nextion Editor refused
    `b[i]` in program.s ("Invalid Variables"). With `need` None, none may
    be."""
    references = re.findall(INDIRECT_HEAD, re.sub(TEXT, '""', text))
    if not references:
        return True
    if need is None:
        return False
    if need.subject == "event":
        own = "%s.b[" % need.context.get("page")
        return not any(found.startswith(own) for found in references)
    return all(names_its_page(found) for found in references)


def names_its_page(reference: str) -> bool:
    """Whether `reference`, through the screen's arrays (INDIRECT), names
    the page it reaches into, by its number, `p[i].b[j]`, or by its name,
    `page1.b[i]`, rather than `b[i]`, which reaches into the page shown."""
    return not reference.startswith("b[")


def named_attributes(text: str) -> list:
    """Returns each component's attribute that `text`, a line of code or a
    part of one, names directly, as `t0.txt` or `page1.va0.val`, those in a
    reference's indexes among them. The page's name before a reference, as
    in `page1.b[n0.val]`, is left out, as `page1.b` is no attribute, but its
    index's attributes are given, as `b[n0.val]`'s are."""
    return _ATTRIBUTE.findall(re.sub(r"%s\.(?=b\[)" % NAME, "", text))


def sets_only_changeable_attributes(need, text: str) -> bool:
    """Whether `text`, a line of code or a for's start or step, sets no
    component's attribute that code cannot change, as nxwright gives them:
    on every series, such as a waveform's id
    (attribute_descriptions.code_cannot_change), and on the line's series,
    such as a component's x on T (editor_limits.code_cannot_change_on_series).
    The Nextion Editor refuses a line that sets one ("Assignment operation
    failed"). Nor does it set a method, which code calls, as a file stream's
    open, which the Nextion Editor refuses too ("Invalid Variables"). `need`
    is the line's, whose context gives the components of its page
    (matching.py). A text the encoder cannot read sets none, and is left to
    the other checks."""
    try:
        parts = _parts(text)
    except StatementError:
        return True
    setting = [("operator", operator) for operator in _ASSIGNING + _STEPPING]
    if len(parts) < 2 or parts[0][0] != "attribute" or parts[1] not in setting:
        return True
    page_object, attribute = named_component(need, parts[0][1])
    if page_object is None:
        return True
    type_name = component_types.type_name(page_object)
    described = describe(type_name, attribute)
    return not (code_cannot_change(type_name, attribute)
                or code_cannot_change_on_series(type_name, attribute, need.series)
                or (described is not None and described.method))


# The series this module's probes matched (matching.py): T, K in k_probes.py,
# P in p_probes.py, E in e_probes.py, where _covered_on_p and p_takes keep P
# and E to what P's tables hold, and F in f_probes.py, where _covered_on_f
# keeps F to what F's tables hold.
SERIES = ("T", "K", "P", "E", "F")

MATCHED = [Rule("code", None, "assignments, with `=`, or with an arithmetic operator's own, "
                "such as `*=` or `<<=`, of numbers, hexadecimal numbers of 1 to 4 bytes after "
                "any leading zeros, program.s's int variables, system variables, and colours' "
                "names, joined by the arithmetic operators, a colour's name set as any "
                "variable; ++ and --; "
                "`page` with a page's name or a value, as an assignment's; printh, its "
                "argument kept as written; and, in an event, the "
                "attributes the page's components write, as numbers, such as a text's bco or "
                "a component's x, but a txt, set only where nxwright lets code change them on "
                "the line's series; and the txt of a component whose type gives code its txt, "
                "set with `=`, or added to with `+=`, texts of any characters, in the "
                "project's encoding, with the escapes \\\\, \\\", and \\r, and txts joined "
                "with `+`, or cut with `-=` and a number, a hexadecimal number, "
                "a variable, a colour's name, or an attribute encoded as a "
                "number; a global component of any page named by its page, as "
                "`page1.va0.val`, wherever a component of the line's page goes, in program.s "
                "too; in an event, each attribute of the page's own whose entry the frame "
                "writes, and on T, K, and F its effect, first, time, and swipe targets too, "
                "which it does not (page_code_entry), as a number; a byte of the serial "
                "buffer, `u[i]`, "
                "read or set as a number; on T and K; and on P and E, "
                "printh, `page` as on T, and the lines above "
                "that hold what P's probes of code showed alone (p_takes): its system "
                "variables, colours, and int variables, and components' attributes, a global "
                "one of another page's named by its page as on T; "
                "on F, the lines above that name only F's system variables and colours, or "
                "else int variables (f_takes), with F's numbers of them; "
                "and, on T, K, P, E, and F, a component's attribute reached "
                "through the screen's arrays, `b[i].name` or `p[i].b[j].name`, any name, its "
                "first index a value as an assignment's, without a text, or "
                "`page1.b[i].name`, by the page's name, but the line's own page's in an "
                "event: set with any "
                "assigning operator, a txt's with `=`, `+=`, or `-=` alone, to operands of any "
                "kind joined by the arithmetic operators, or with `++` or `--`; or the value "
                "given to a variable or an attribute, beside numbers when it sets one, and "
                "beside texts and txts joined by `+` when it sets a txt, or cutting a txt with "
                "`-=`; among `page`'s operands, any name but txt, without a space; in an "
                "event, and in program.s as "
                "`p[i].b[j]` or `page1.b[i]` alone",
                _covered)]


def _parts(line: str) -> list:
    """Returns the parts of `line`, as (kind, text): "hex", "number",
    "indirect" (INDIRECT), "serial" (SERIAL_BUFFER), "attribute", "name",
    "text", or "operator". A
    minus right after an assigning operator, such as `=` or `*=`, after an
    arithmetic operator, as in `2*-16`, or after `,`, starts a number, which
    the Nextion Editor writes as written. Raises StatementError for anything
    else."""
    parts, at = [], 0
    while at < len(line):
        found = _PART.match(line, at)
        if found is None or found.end() == at:
            raise StatementError("%r: %r is no part of a line nxwright encodes" % (line, line[at:]))
        kind = found.lastgroup
        text = found.group(kind)
        if (kind == "number" and parts and parts[-1] == ("operator", "-")
                and (len(parts) == 1 or parts[-2] in (
                    ("operator", operator) for operator in _ASSIGNING + _ARITHMETIC + (",",)))):
            parts[-1] = ("number", "-" + text)
        elif (kind == "number" and len(parts) > 1 and parts[-1] == ("operator", "--")
              and parts[-2][0] != "operator"):
            # `--` between an operand and a number, as in `sys0--1`, is a
            # minus, then a negative number, as the Nextion Editor writes it.
            parts[-1:] = [("operator", "-"), ("number", "-" + text)]
        else:
            parts.append((kind, text))
        at = found.end()
        # Spaces at the end of the line.
        if not line[at:].strip(" \t"):
            break
    return parts


def _assignment_block(parts: list, series: str, variables, attribute_entry=None,
                      codec=None) -> bytes:
    """Returns the block of an assignment, as `sys0=sys1+2`, `sys0+=1`, or
    `sys0++`, from its parts. Its target is written as its operand, a byte
    of the serial buffer (SERIAL_BUFFER) among them, then its operator."""
    if len(parts) < 2 or parts[0][0] not in ("name", "attribute", "indirect", "serial"):
        raise StatementError("%s: no assignment nxwright encodes" % _shown(parts))
    target, operator = parts[0], parts[1]
    if operator in (("operator", step) for step in _STEPPING) and len(parts) == 2:
        return (_operand(target, series, variables, attribute_entry, codec)
                + operator[1].encode("ascii"))
    if operator not in (("operator", assigning) for assigning in _ASSIGNING):
        raise StatementError("%s: no assignment nxwright encodes" % _shown(parts))
    return (_operand(target, series, variables, attribute_entry, codec)
            + operator[1].encode("ascii")
            + _value_block(parts[2:], _shown(parts), series, variables, attribute_entry, codec))


def _value_block(parts: list, shown: str, series: str, variables, attribute_entry=None,
                 codec=None) -> bytes:
    """Returns the bytes of a value, as an assignment's and `page`'s, from
    its parts: operands joined by the arithmetic operators, each operator
    as written. `shown` is the line, for an error. `codec` writes its texts
    (_operand)."""
    if not parts or len(parts) % 2 == 0:
        raise StatementError("%s: no value nxwright encodes" % shown)
    block = b""
    for number, part in enumerate(parts):
        if number % 2:
            if part not in (("operator", arithmetic) for arithmetic in _ARITHMETIC):
                raise StatementError("%s: %r is no operator nxwright encodes" % (shown, part[1]))
            block += part[1].encode("ascii")
        else:
            block += _operand(part, series, variables, attribute_entry, codec)
    return block


def _command_block(name: str, arguments: str, series: str, variables,
                   attribute_entry=None, components=None, pages=None, codec=None) -> bytes:
    """Returns the block of the command `name`, given its `arguments` as the
    line has them. A command that takes a component: a name that is one of
    `components`, or any name when that is None, is kept as written; any
    other name must be a variable's, written as its operand; and an ID is
    written as any number is. A page's name, one of `pages`, is kept as written;
    any other argument of `page` is a value, as an assignment's."""
    command = series_commands(series)[name]
    head = ((name + " ").encode("ascii") if command.number is None
            else command.block_start())
    arguments = arguments.strip(" \t")
    if command.arguments is not None and not re.fullmatch(command.arguments, arguments):
        raise StatementError("%s %s: those arguments are not encoded" % (name, arguments))
    # The Nextion Editor refuses an int variable named as a page, so in a
    # project it compiles, a name is never both.
    if command.raw or (command.page and pages is not None and arguments in pages):
        written = (arguments.encode("ascii") if codec is None
                   else codec.encode_keeping_bytes(arguments, arguments))
        return head + written
    # Any other argument of `page` is a value, as an assignment's. The
    # Nextion Editor checks no number against the project's pages. It
    # refused a txt named directly, as `page t0.txt`, a text ("Invalid Page
    # ID"), and a space in a reference through the screen's arrays, which
    # the rule leaves out.
    if command.page:
        parts = _parts(arguments)
        if any(kind == "text" for kind, _ in parts):
            raise StatementError("page %s: the Nextion Editor refuses a text as a page "
                                 "(\"Invalid Page ID\")" % arguments)
        return head + _value_block(parts, "page " + arguments, series, variables,
                                   attribute_entry)

    def operands_block(text: str) -> bytes:
        # `text` is the whole of the arguments, or one of them beside a
        # component.
        return _arguments_block(text, "%s %s" % (name, arguments), series, variables,
                                attribute_entry, codec)

    if not command.component:
        return head + operands_block(arguments)
    # The command's pattern, checked above, takes no text, so its commas
    # part its arguments. A component given by its name, the page's own
    # included, is kept as written. Any other is written as any number
    # argument is: `0x01` is 03 01 00 00 00, `1000` is 03 and its value, and
    # `sys0+1` is sys0's operand, then `+1`.
    pieces = arguments.split(",")
    written = []
    for place, piece in enumerate(pieces):
        if place not in command.component_places:
            written.append(operands_block(piece))
            continue
        piece = piece.strip(" \t")
        if re.fullmatch(INDIRECT_COMPONENT, piece):
            # The Nextion Editor refused `b[i]` in program.s ("Invalid
            # Component ID").
            if components == ():
                raise StatementError("%s %s: the Nextion Editor refuses b[i] as a component "
                                     "in program.s" % (name, arguments))
            written.append(_indirect_operand(piece, series, variables, attribute_entry))
        elif re.fullmatch(NAME, piece) and (components is None or piece in components):
            written.append(piece.encode("ascii"))
        elif re.fullmatch(NAME, piece):
            # A name that is no component of the line's page, as any name in
            # program.s, which has no page, is a variable's: the Nextion
            # Editor wrote `vis sys0,0`, `tsw a,1`, `ref dim`, and `vis RED,0`
            # in program.s as their operands. It refused any other name, as
            # `vis zz,0` ("Invalid Component ID").
            if not (piece in SYSTEM_VARIABLES[series] or piece in COLOURS[series]
                    or variables is None or piece in variables):
                where = "the line's page" if components else "program.s"
                raise StatementError("%s %s: %s is neither a component of %s nor a variable, "
                                     "which the Nextion Editor refuses (\"Invalid Component "
                                     "ID\")" % (name, arguments, piece, where))
            written.append(operands_block(piece))
        else:
            written.append(operands_block(piece))
    return head + b",".join(written)



def _arguments_block(text: str, shown: str, series: str, variables, attribute_entry=None,
                     codec=None) -> bytes:
    """Returns the bytes of `text`, arguments between commas, as a command's
    and a method's call's: each a value, as an assignment's, the commas
    kept. An empty argument gives no bytes. `shown` is the line, for an
    error."""
    values = [[]]
    for part in _parts(text):
        if part == ("operator", ","):
            values.append([])
        else:
            values[-1].append(part)
    return b",".join(_value_block(value, shown, series, variables, attribute_entry, codec)
                     if value else b"" for value in values)


def _method_call_block(call, series: str, variables, attribute_entry=None,
                       codec=None) -> bytes:
    """Returns the block of `call`, a component's method's call
    (METHOD_CALL): the method's operand, as an attribute's, then its
    arguments, as a command's, between parentheses."""
    method = _operand(("attribute", call.group("method")), series, variables, attribute_entry)
    return (method + b"(" + _arguments_block(call.group("arguments"), call.group(0), series,
                                             variables, attribute_entry, codec) + b")")


@lru_cache(maxsize=None)
def series_commands(series: str) -> dict:
    """Returns the commands of `series` this module and instructions/ give,
    P's for a series written as P (component_types.SERIES_WRITTEN_AS_P).
    Kept, as a compile asks for them once a line."""
    if series in component_types.SERIES_WRITTEN_AS_P:
        series = "P"
    found = dict(COMMANDS.get(series, {}))
    for module in _instruction_modules():
        found.update(getattr(module, "COMMANDS", {}).get(series, {}))
    return found


@lru_cache(maxsize=None)
def _control_statements() -> tuple:
    """Returns the modules of instructions/ that encode a control statement,
    those giving starts_statement. Kept, as a compile asks for them once a
    run of lines."""
    return tuple(module for module in _instruction_modules()
                 if hasattr(module, "starts_statement"))


def _instruction_modules() -> list:
    """Returns the modules of instructions/."""
    package = importlib.import_module("nxwright.tft.instructions")
    return [importlib.import_module("nxwright.tft.instructions." + module.name)
            for module in pkgutil.iter_modules(package.__path__)]


def _hex_operand(text: str) -> bytes:
    """Returns the operand of the hexadecimal number `text`, such as 0x12:
    03, then its value, 4 bytes, however small, as the Nextion Editor
    writes one."""
    return b"\x03" + struct.pack("<I", int(text, 16))


def system_variable_operand(name: str, series: str):
    """Returns the operand of the system variable or the colour `name` on
    `series`, 04, its two bytes, then two zeros, or None when `name` is
    neither. The Nextion Editor's own code names some, as a scrolling
    text's names sya0."""
    known = SYSTEM_VARIABLES[series].get(name) or COLOURS[series].get(name)
    return None if known is None else bytes([SYSTEM_VARIABLE_TAG, known[0], known[1], 0, 0])


def _operand(part: tuple, series: str, variables, attribute_entry=None, codec=None) -> bytes:
    """Returns an operand's bytes: a number, a hexadecimal number, a text,
    or a variable's, a colour's, or a component's attribute's reference,
    directly or through the screen's arrays (_indirect_operand). A text is
    written as it is, its quotes included, in `codec`, the project's: in
    iso-8859-1, `"é"` is 22 e9 22."""
    kind, text = part
    if kind == "indirect":
        return _indirect_operand(text, series, variables, attribute_entry)
    if kind == "serial":
        return _serial_operand(text, series, variables, attribute_entry, codec)
    if kind == "text":
        # A text comes from a value alone (_value_block), whose callers give
        # the codec.
        assert codec is not None, "a text needs its project's codec"
        return codec.encode_keeping_bytes(text, text)
    if kind == "hex":
        return _hex_operand(text)
    if kind == "attribute":
        return component_types.entry_operand(0 if attribute_entry is None
                                             else attribute_entry(text))
    if kind == "number":
        if len(text) < LONG_NUMBER:
            return text.encode("ascii")
        # A number past 32 bits keeps its low 32, as `page 2147483648` gave
        # 03 00 00 00 80 (ResearchNotes/tft/statements.md).
        value = (int(text) + 2 ** 31) % 2 ** 32 - 2 ** 31
        return component_types.value_operand(value)
    if kind != "name":
        raise StatementError("%r is no operand" % text)
    known = system_variable_operand(text, series)
    if known is not None:
        return known
    if variables is None:
        return bytes([PROGRAM_VARIABLE_TAG, 0, 0, 0, 0])
    if text in variables:
        return bytes([PROGRAM_VARIABLE_TAG]) + struct.pack(
            "<I", PROGRAM_VARIABLE_SIZE * list(variables).index(text))
    raise StatementError("%s is no variable nxwright knows" % text)


def _indirect_operand(text: str, series: str, variables, attribute_entry=None) -> bytes:
    """Returns the bytes of `text`, a component's attribute reached through
    the screen's arrays (INDIRECT): `b[` or `p[`, its first index as an
    assignment's value (_value_block), then the rest as written, compacted.
    The second index of `p[i].b[j]` stays as written: in
    `p[sys0].b[sys1].txt`, sys0 becomes its operand, and sys1 stays text. A
    reference by the page's name, as `page1.b[sys0].txt`, is written whole as
    its text, compacted, its index included (PAGE_INDIRECT).
    Raises StatementError for a first index that is empty or holds a text,
    which the Nextion Editor refuses ("Invalid Variables"), or for a rest of
    other characters than ASCII, which nxwright's build refuses ("the
    Nextion Editor refuses this value, which is not operands joined by
    operators")."""
    if re.fullmatch(PAGE_INDIRECT, text):
        written = compact(text)
        if not written.isascii():
            raise StatementError("%r: nxwright's build refuses a reference past ASCII" % text)
        return written.encode("ascii")
    found = _INDIRECT.fullmatch(text)
    index = _parts(found.group("index"))
    if not index or any(kind == "text" for kind, _ in index):
        raise StatementError("%r: the Nextion Editor refuses an index that is empty or holds a "
                             "text (\"Invalid Variables\")" % text)
    rest = compact(found.group("rest"))
    if not rest.isascii():
        raise StatementError("%r: nxwright's build refuses a reference past ASCII" % text)
    return (found.group("array").encode("ascii") + b"["
            + _value_block(index, repr(text), series, variables, attribute_entry)
            + b"]" + rest.encode("ascii"))


def _serial_operand(text: str, series: str, variables, attribute_entry=None,
                    codec=None) -> bytes:
    """Returns the bytes of `text`, a byte of the serial buffer, `u[i]`:
    `u[`, its index as an assignment's value (_value_block), then `]`, as
    `b[i]`'s index is written (_indirect_operand). Raises StatementError for
    an empty index, which gives no value to write."""
    return (b"u[" + _value_block(_parts(text[2:-1]), repr(text), series, variables,
                                 attribute_entry, codec) + b"]")


def _shown(parts: list) -> str:
    return repr("".join(text for _, text in parts))
