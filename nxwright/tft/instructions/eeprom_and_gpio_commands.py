"""The commands of the EEPROM and the GPIO pins that K and P have and T has
not: wepo, repo, wept, rept, and cfgpio, as the Nextion Editor 1.68.2
writes them on K (ResearchNotes/tft/eeprom-and-gpio-commands.md), on P under
numbers of its own (ResearchNotes/tft/p-series.md), and on F, which has wepo,
repo, and cfgpio alone, under numbers of its own too
(ResearchNotes/tft/f-series.md). As the vendor's instruction set describes
them, wepo writes a value to the EEPROM and repo reads one from it, wept
and rept move bytes between the EEPROM and the serial line, and cfgpio
sets a GPIO pin's mode.

Each is a command of table 4 or 8, then its arguments between commas. An
argument is an operand, as the statement encoder (statements.py) encodes
it: a number, a hexadecimal number, an int variable of program.s, a system
variable, or, in an event, an attribute of a component of the line's page,
its txt among them. wepo's value, and repo's destination, may be a text
between double quotes too: `repo "a",0` is 09 0e 04, then `"a",0`.
`wepo n0.val,20` is 09 0f 04, n0.val's operand, a comma, then `20`.

Where a command takes a number, an address, a length, a pin, or a mode,
the Nextion Editor refuses a text or a txt ("Invalid variable operation"),
and so does nxwright.tft. There it takes any other attribute, such as a val or
`t0.bco`, or operands joined by the arithmetic operators, as an
assignment's value is: `wept 0+0,10` is 09 1a 04, then `0+0,10`. It
refuses them as wepo's value ("Invalid Variables"), and nxwright refuses them
as repo's destination too, as the Nextion Editor refused an expression as
each command's destination tried, such as cov's and ucopy's. cfgpio's
third argument is a component of the line's page, by name, kept as
written: `cfgpio 2,1,n0` is 09 0d 08, then `2,1,n0`. Any other name is a
variable's, written as its operand: `cfgpio 1,1,sys0` is 09 0d 08, `1,1,`,
then sys0's operand. The Nextion Editor refuses a name that is neither
("Invalid Component ID"). Any other component is written as any number
argument is: `cfgpio 3,1,1000` gives 03 e8 03 00 00 for 1000. In an
event, it may be `b[i]` too, written as the screen's commands write it
(statements.py).
"""
import re

from nxwright.tft.component_types import SERIES_WRITTEN_AS_P
from nxwright.tft.matching import Rule
from nxwright.tft.statements import (INDIRECT_COMPONENT, NAME, REFERENCE_WORDS, TEXT, Command,
                              attributes_are_encoded, attributes_are_numbers, command_name,
                              encodable, expression, f_takes, is_a_variable, operand_pattern,
                              renumbered)

# A value: a component's attribute, its txt among them, a hexadecimal
# number, a number, its sign included, or a name, as the encoder reads them.
_VALUE = operand_pattern(("number", "text"))
# Where a command takes a number: operands joined by the arithmetic
# operators, each a hexadecimal number, a number, its sign included, a
# name, or an attribute other than a txt.
_NUMBER = expression(operand_pattern(("number",)))
# A component: a name, `b[i]`, or else operands joined by the arithmetic
# operators, as an ID, written as any number argument is. A txt is no
# component: the Nextion Editor refused `cfgpio 1,1,t0.txt` ("Invalid
# Component ID"), which nxwright's build lets through.
_COMPONENT = r"(?:%s|%s|%s)" % (NAME, INDIRECT_COMPONENT, _NUMBER)
# Each command's number, its table, and its arguments: wepo a value or a
# text and an address; repo where the value goes and an address; wept and
# rept an address and a length; cfgpio a pin, a mode, and a component.
COMMANDS = {"K": {
    "wepo": Command(0x0F, 4, "(?:%s|%s),%s" % (_VALUE, TEXT, _NUMBER)),
    "repo": Command(0x0E, 4, "(?:%s|%s),%s" % (_VALUE, TEXT, _NUMBER)),
    "wept": Command(0x1A, 4, "%s,%s" % (_NUMBER, _NUMBER)),
    "rept": Command(0x19, 4, "%s,%s" % (_NUMBER, _NUMBER)),
    # Its component is its third argument, counted from 0.
    "cfgpio": Command(0x0D, 8, "%s,%s,%s" % (_NUMBER, _NUMBER, _COMPONENT), component=True,
                      component_places=(2,)),
}}
# P numbers them its own way, in the same tables.
COMMANDS["P"] = renumbered(COMMANDS["K"], {
    "repo": 0x11, "wepo": 0x12, "rept": 0x20, "wept": 0x21, "cfgpio": 0x11})
# F has wepo, repo, and cfgpio, and numbers the first two its own way. It
# lacks wept and rept, which nxwright's build refuses there.
COMMANDS["F"] = {name: command for name, command in
                 renumbered(COMMANDS["K"], {"wepo": 0x10, "repo": 0x0F}).items()
                 if name in ("wepo", "repo", "cfgpio")}


def _covered(need) -> bool:
    """Whether the line of code `need` is one of these commands that the
    encoder encodes, on the line's series, P's table on E. Each attribute
    the line refers to must be that of a component of the line's page whose
    type has it (statements.attributes_are_encoded). A component named must
    be one of the line's page (matching.py gives them), or a variable
    (statements.is_a_variable), or, in an event, `b[i]`, its index a
    number."""
    line = need.value.strip(" \t")
    # On F, the line may name only what F's tables hold.
    if need.series == "F" and not f_takes(line):
        return False
    name = command_name(line)
    series = "P" if need.series in SERIES_WRITTEN_AS_P else need.series
    series = series if series in COMMANDS else "K"
    if name not in COMMANDS[series] or not encodable(line, series):
        return False
    arguments = line[len(name):].strip(" \t")
    # Outside the texts between double quotes.
    if not attributes_are_encoded(need, re.sub(TEXT, "", arguments)):
        return False
    command = COMMANDS[series][name]
    if not command.component:
        return True
    component = arguments.split(",")[command.component_places[0]]
    if re.fullmatch(INDIRECT_COMPONENT, component):
        return need.subject == "event" and attributes_are_numbers(need, component)
    if re.fullmatch(NAME, component):
        return component in need.context.get("components", {}) or is_a_variable(need, component)
    return True


# The series this module's probes matched (matching.py): K, P in p_probes.py,
# E in e_probes.py, and F in f_probes.py, as T has none of these commands.
SERIES = ("K", "P", "E", "F")

MATCHED = [Rule("code", None, "wepo, repo, wept, rept, and cfgpio, their operands numbers, "
                "hexadecimal numbers of 1 to 4 bytes, program.s's int variables, system "
                "variables, a text of any characters, with the "
                "escapes \\\\, \\\", and \\r, where wepo takes a value or repo a "
                "destination, or, in an event, an attribute of a component on its page, its "
                "txt among them; "
                "where a command takes a number, no text or txt, but one operand or several "
                "joined by the "
                "arithmetic operators; cfgpio's component one of the line's page, by name, or "
                "a variable, or else one operand or several joined by the arithmetic operators, "
                "or, in an "
                "event, `b[i]`, its index a value as an assignment's, without a space; "
                + REFERENCE_WORDS + "; on K, P, and E, and on F but wept and rept, "
                "naming only what its tables hold (statements.f_takes)",
                _covered)]
