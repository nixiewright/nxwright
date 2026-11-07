"""The probes of the commands of components and of the screen
(instructions/screen_commands.py): lines of them added to the T base
folder, in strict Nextion syntax, each compared with the blocks the Nextion
Editor wrote, through the statement probes' own ways of cutting them
(statement_probes.py). Run them with `tools.tft.probe run screen_command_probes`.

The probes in page0's Touch Release event put two texts on page0, t0 and
t1, which the lines name, and keep fixtures: the event's blocks, back to
back with their size words.
"""
from tools.tft.probing.probe_runner import Probe
from tools.tft.probing.statement_probes import (ProgramChange, ours_in_event, ours_in_program,
                                            program_lines, theirs_in_event, theirs_in_program,
                                            touch_release_code)
from tools.tft.probing.text_probes import text_component

FIXTURES = "screen-commands"


def _with_texts(lines: list, declarations: list = ()):
    """Returns a change that gives page0's Touch Release event `lines`, adds
    `declarations` to program.s, and puts the texts t0 and t1 on page0."""
    return ProgramChange(declarations=tuple(declarations),
                         components=(text_component("t0"), text_component("t1", y=60)),
                         code=touch_release_code(lines))


PROBES = [
    # Each command, its component by name.
    Probe("screen-commands-each", "T", _with_texts([
        "vis t0,0", "vis t1,1", "tsw t0,0", "ref t0", "click t0,1", "click t1,0", "ref_stop",
        "ref_star", "doevents", "com_stop", "com_star", "randset 0,100"]),
        ours_in_event, theirs_in_event, FIXTURES),
    # Components by ID, up to 255 for all of the page's; each kind of
    # operand; and a space after each comma.
    Probe("screen-commands-operands", "T", _with_texts([
        "vis 255,0", "vis 1,1", "tsw 255,1", "ref 0", "click 2,1", "vis t0,sys0", "tsw t1,a",
        "click t1,sys1", "vis t0, 1", "randset -5,1000", "randset sys0,a", "randset 0, 100"],
        ["int a=1"]),
        ours_in_event, theirs_in_event, FIXTURES),
    # The commands in program.s, before its page 0, their components by ID.
    Probe("screen-commands-in-program", "T", program_lines([
        "ref 0", "vis 255,0", "tsw 255,1", "ref_stop", "ref_star", "doevents", "com_stop",
        "com_star", "randset 0,100"]),
        ours_in_program, theirs_in_program),
    # IDs past 255, with a leading zero, and below 0, which the Nextion Editor
    # writes as any number, and the page's own name as the component.
    Probe("screen-commands-ids-and-the-page", "T", _with_texts([
        "vis 256,0", "vis 1000,0", "vis 007,0", "vis -1,0", "vis page0,0", "tsw 1000,0",
        "tsw -1,0", "click page0,1", "click 007,1", "ref page0", "ref 1000", "ref 0007",
        "ref -100", "vis 99999,0"]),
        ours_in_event, theirs_in_event, FIXTURES),
    # Hexadecimal IDs and operands joined by the arithmetic operators as the
    # component, each written as any number argument is.
    Probe("screen-commands-components-of-other-forms", "T", _with_texts([
        "vis 0x01,0", "tsw 0x02,1", "ref 0x0002", "vis 1+1,0", "ref sys0+1"]),
        ours_in_event, theirs_in_event, FIXTURES),
    # Variables as the component in program.s, which has no page: an int
    # variable of the base's and one declared, a system variable, and a
    # colour, each written as its operand.
    Probe("screen-commands-variables-in-program", "T", program_lines([
        "vis sys0,0", "tsw a,1", "ref dim", "vis RED,0"], ["int a=1"]),
        ours_in_program, theirs_in_program),
]
