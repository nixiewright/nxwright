"""The commands of components and of the screen, on the T, K, P, E, and F
series, as the Nextion Editor 1.68.2 writes them
(ResearchNotes/tft/screen-commands.md): vis, tsw, ref, and click, which take a
component; ref_stop, ref_star, doevents, com_stop, and com_star, which take
no argument; and randset.

Each is a command of table 4 or 8, then its arguments between commas. A
command's component is given by its name, or else by operands joined by
the arithmetic operators, as an ID. The name of the line's page or of one
of its components is kept as written: `vis t0,0` is 09 05 04, then `t0,0`.
Any other name is a variable's, as any name in program.s, which has no
page, and is written as its operand: `vis sys0,0` in program.s is 09 05
04, sys0's operand, then `,0`. Any other component is written as any
number argument is: up to 3 characters as written, as `vis 255,0`, past
them as 03 and its value, as `vis 1000,0`, and `ref sys0+1` as sys0's
operand, then `+1`. The other arguments are values, as the statement
encoder (statements.py) encodes an assignment's: an operand, or
operands joined by the arithmetic operators. `vis t0,sys0` is 09 05 04,
`t0,`, then sys0's operand, and `vis t0,sys0+1` the same, then `+1`. A
command that takes no argument is its three bytes alone: `doevents` is 09
21 08.
"""
from nxwright.tft.matching import Rule
from nxwright.tft.statements import (INDIRECT_COMPONENT, NAME, REFERENCE_WORDS, Command,
                              attributes_are_numbers, command_name, component_taken, encodable,
                              expression, f_takes, operand_pattern, operands, renumbered)

# An argument other than a component: operands joined by the arithmetic
# operators, each a hexadecimal number, a number, its sign included, a
# name, or an attribute other than a txt, as the encoder reads them.
_OPERAND = expression(operand_pattern(("number",)))
# A component: a name, one reached through the screen's arrays, `b[i]`
# (statements.INDIRECT_COMPONENT), or else operands joined by the
# arithmetic operators, as an ID. The Nextion Editor checks no ID against
# the page's components. A txt is no component: the Nextion Editor refuses
# one ("Invalid Component ID"), which nxwright's build lets through.
_COMPONENT = r"(?:%s|%s|%s)" % (NAME, INDIRECT_COMPONENT, _OPERAND)
# A component, then one operand.
_COMPONENT_AND_OPERAND = _COMPONENT + ", ?" + _OPERAND

# Each command's number, its table, and its arguments: vis and tsw a
# component and whether it is shown or takes touches; click a component
# and whether it is pressed or released; ref a component; randset the least
# and the most of the numbers rand gives. ref_stop, ref_star, doevents,
# com_stop, and com_star take none: the Nextion Editor refuses an argument
# to them ("Invalid number of arguments"), which nxwright's build lets
# through.
COMMANDS = {"T": {
    "vis": Command(0x05, 4, _COMPONENT_AND_OPERAND, component=True),
    "tsw": Command(0x09, 4, _COMPONENT_AND_OPERAND, component=True),
    "click": Command(0x00, 8, _COMPONENT_AND_OPERAND, component=True),
    "ref": Command(0x03, 4, _COMPONENT, component=True),
    "ref_stop": Command(0x1D, 8, ""),
    "ref_star": Command(0x1F, 8, ""),
    "doevents": Command(0x21, 8, ""),
    "com_stop": Command(0x1E, 8, ""),
    "com_star": Command(0x20, 8, ""),
    "randset": Command(0x16, 8, operands(_OPERAND, 2)),
}}
# K numbers randset and the commands without arguments its own way, the
# others as T does.
COMMANDS["K"] = renumbered(COMMANDS["T"], {
    "randset": 0x17, "ref_stop": 0x1e, "com_stop": 0x1f, "ref_star": 0x20, "com_star": 0x21,
    "doevents": 0x22})
# P numbers these its own way, in the same tables (ResearchNotes/tft/p-series.md).
COMMANDS["P"] = renumbered(COMMANDS["T"], {
    "randset": 0x21, "ref_stop": 0x2b, "com_stop": 0x2c, "ref_star": 0x2d, "com_star": 0x2e,
    "doevents": 0x30})
# F numbers these its own way, in the same tables (ResearchNotes/tft/f-series.md).
COMMANDS["F"] = renumbered(COMMANDS["T"], {
    "ref_stop": 0x1e, "doevents": 0x23, "com_stop": 0x1f, "com_star": 0x21,
    "ref_star": 0x20, "randset": 0x17})


def _covered(need) -> bool:
    """Whether the line of code `need` is one of these commands that the
    encoder encodes, on T. A component named must be the line's page, one
    of its components (matching.py gives them), or a variable
    (statements.component_taken), or, in an event, one reached through the
    screen's arrays, `b[i]`. A variable was probed in program.s alone: in
    an event, nxwright's build refuses a name that is not on the page. Each
    attribute the line refers to must be one the encoder encodes as a
    number (statements.attributes_are_numbers), so program.s takes none but
    another page's global's."""
    line = need.value.strip(" \t")
    # On F, the line may name only what F's tables hold.
    if need.series == "F" and not f_takes(line):
        return False
    name = command_name(line)
    if (name not in COMMANDS["T"] or not encodable(line)
            or not attributes_are_numbers(need, line)):
        return False
    if not COMMANDS["T"][name].component:
        return True
    return component_taken(need, line[len(name):].strip(" \t").split(",", 1)[0].strip(" \t"))


# The series this module's probes matched (matching.py): T, K in k_probes.py,
# P in p_probes.py, E in e_probes.py, and F in f_probes.py.
SERIES = ("T", "K", "P", "E", "F")

MATCHED = [Rule("code", None, "vis, tsw, click, and ref, their component the line's page "
                "or one of its components, by name, or a variable, or else one operand or "
                "several joined by "
                "the arithmetic operators; ref_stop, "
                "ref_star, doevents, com_stop, and com_star; "
                "and randset; their operands numbers, hexadecimal numbers of 1 to 4 bytes, "
                "program.s's int variables, system variables, colours' names, or, in an event, "
                "an attribute other than a txt of a component on its page, "
                "each argument but the component one operand or several "
                "joined by the arithmetic operators; `b[i]` as the component too, "
                "in an event, its index a value as an assignment's, without a space; "
                + REFERENCE_WORDS + "; on T, K, P, E, and F, on F naming only what its tables "
                "hold (statements.f_takes)", _covered)]
