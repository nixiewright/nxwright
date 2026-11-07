"""The commands of sound, of motion, and of layers that the P and E series
have, and T and K have not: beep, play, move, and setlayer, as the Nextion
Editor 1.68.2 writes them on P and E (ResearchNotes/tft/p-series.md), and beep
alone on F, under a number of its own (ResearchNotes/tft/f-series.md). As the
vendor's instruction set describes them, beep sounds the buzzer for a
time, play plays an audio resource on a channel, move moves a component
from one place to another, and setlayer puts a component above another.

Each is a command of table 4 or 8, then its arguments between commas.
beep's, play's, and move's are each encoded by the statement encoder
(statements.py) as in any line: `play sys0,n0.val,1` is 09 28 04, sys0's
operand, a comma, n0.val's, a comma, and `1`. move's first argument is a
component, and setlayer's two are, each written as vis's is
(screen_commands.py): by its name, kept as written, as `setlayer t0,n0`
is 09 2f 08, then `t0,n0`, as a variable's operand, as `setlayer sys0,a`
gives sys0's operand, a comma, then a's, or else as any number argument
is, as `setlayer 1,1000` gives 03 e8 03 00 00 for 1000.
"""
from dataclasses import replace

from nxwright.tft.component_types import SERIES_WRITTEN_AS_P
from nxwright.tft.matching import Rule
from nxwright.tft.statements import (INDIRECT_COMPONENT, NAME, Command, attributes_are_numbers,
                              command_name, component_taken, encodable, expression, f_takes,
                              operand_pattern, operands)

# Where a command takes a number: operands joined by the arithmetic
# operators, each a hexadecimal number, a number, a name, or an attribute
# other than a txt.
_NUMBER = expression(operand_pattern(("number",)))
# move's component: a name, one reached through the screen's arrays,
# `b[i]` (statements.INDIRECT_COMPONENT), or else operands joined by the
# arithmetic operators, as an ID. A txt is no component: the Nextion Editor
# refused `move t0.txt,0,0,10,10,0,100` ("Invalid Component ID"), which
# nxwright's build lets through.
_COMPONENT = r"(?:%s|%s|%s)" % (NAME, INDIRECT_COMPONENT, _NUMBER)
# setlayer's component: a name, or else operands joined by the arithmetic
# operators, as an ID. The Nextion Editor refused a txt as either
# component, as `setlayer t0.txt,n0` ("Invalid Component ID").
_LAYERED = r"(?:%s|%s)" % (NAME, _NUMBER)

# Each command's number, its table, and its arguments, on P: beep a time;
# play a channel, a resource, and whether it loops; move a component, its
# place before and after, its priority, and its time; setlayer the
# component to put above the other.
COMMANDS = {"P": {
    "beep": Command(0x13, 4, _NUMBER),
    "play": Command(0x28, 4, operands(_NUMBER, 3)),
    "move": Command(0x0E, 4, _COMPONENT + ", ?" + operands(_NUMBER, 6), component=True),
    "setlayer": Command(0x2F, 8, "%s,%s" % (_LAYERED, _LAYERED), component=True,
                        component_places=(0, 1)),
}}
# F has beep alone, of these, under its own number, its argument as on P.
COMMANDS["F"] = {"beep": replace(COMMANDS["P"]["beep"], number=0x11)}


def _covered(need) -> bool:
    """Whether the line of code `need` is one of these commands that the
    encoder encodes, on the line's series, P's table on E. Each attribute
    the line refers to must be one the encoder encodes as a number
    (statements.attributes_are_numbers). A component named must be the
    line's page, one of its components, or a variable
    (statements.component_taken)."""
    line = need.value.strip(" \t")
    # On F, the line may name only what F's tables hold.
    if need.series == "F" and not f_takes(line):
        return False
    name = command_name(line)
    series = "P" if need.series in SERIES_WRITTEN_AS_P else need.series
    if (name not in COMMANDS.get(series, {}) or not encodable(line, series)
            or not attributes_are_numbers(need, line)):
        return False
    arguments = line[len(name):].strip(" \t").split(",")
    if name == "move":
        return component_taken(need, arguments[0].strip(" \t"))
    if name == "setlayer":
        return all(component_taken(need, component) for component in arguments)
    return True


# The series this module's probes matched (matching.py): P in p_probes.py,
# E in e_probes.py, and F in f_probes.py.
SERIES = ("P", "E", "F")

MATCHED = [Rule("code", None, "beep, play, move, and setlayer: their operands numbers, "
                "hexadecimal numbers of 1 to 4 bytes, program.s's int variables, system "
                "variables, colours' names, or, in an event, an attribute other than a txt of "
                "a component on its page, each argument but a component one operand or several "
                "joined by the arithmetic operators; move's component the line's page or one of "
                "its components, by name, or a variable, or, in an event, `b[i]`, or else one "
                "operand or several joined by the arithmetic operators; setlayer's two "
                "components each by name, a variable, or else so; in an event, and in "
                "program.s; "
                "on P and E, and beep alone on F, naming only what its tables hold "
                "(statements.f_takes)", _covered)]
