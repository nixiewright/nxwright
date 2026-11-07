"""The probes of the serial commands (instructions/serial_commands.py):
lines of them added to the T base folder, in strict Nextion syntax, each
compared with the blocks the Nextion Editor wrote, through the statement
probes' own ways of cutting them (statement_probes.py). Run them with
`tools.tft.probe run serial_command_probes`.

The probes in page0's Touch Release event put a text, t0, on page0, whose
txt the lines use, and keep fixtures: the event's blocks, back to back
with their size words. Most put a number, n0, beside it, whose val the
lines use. One adds a second number, n1, and a timer, tm0, and one has a
touch capture, tc0, in the number's place.
"""
from tools.tft.probing.attribute_probes import with_attributes
from tools.tft.probing.number_probes import number_component
from tools.tft.probing.probe_runner import Probe
from tools.tft.probing.statement_probes import (ProgramChange, ours_in_event, ours_in_program,
                                            program_lines, theirs_in_event, theirs_in_program,
                                            touch_release_code)
from tools.tft.probing.text_probes import text_component
from tools.tft.probing.timer_probes import timer_component
from tools.tft.probing.touch_capture_probes import touch_capture_component

FIXTURES = "serial-commands"


def _with_a_text_and_a_number(lines: list, declarations: list = ()):
    """Returns a change that gives page0's Touch Release event `lines`, adds
    `declarations` to program.s, and puts the text t0 and the number n0 on
    page0."""
    return ProgramChange(declarations=tuple(declarations),
                         components=(text_component("t0", txt="12"),
                                     number_component("n0", y=60, val=7)),
                         code=touch_release_code(lines))


PROBES = [
    # Each command, with a text's txt and a number's val.
    Probe("serial-commands-each", "T", _with_a_text_and_a_number([
        "get t0.txt", "get n0.val", "print t0.txt", "print n0.val", "prints t0.txt,0",
        "prints n0.val,4", "sendme"]),
        ours_in_event, theirs_in_event, FIXTURES),
    # Each kind of operand: numbers, long and negative ones, a text, an int
    # variable, system variables, and a colour; and a space after a comma.
    Probe("serial-commands-operands", "T", _with_a_text_and_a_number([
        "get sys0", "get 123", 'get "hi"', "get 1000", "get -5", "get RED", "get dim", "get a",
        'print "hi"', "print sys0", "print 1000", 'prints "hi",1', "prints sys0,2",
        "prints t0.txt, 0", "prints n0.val,sys1"], ["int a=1"]),
        ours_in_event, theirs_in_event, FIXTURES),
    # The commands in program.s, before its page 0, without attributes.
    Probe("serial-commands-in-program", "T", program_lines([
        "get sys0", "get 1000", 'print "hi"', 'prints "hi",1', "prints 5,sys2", "sendme"]),
        ours_in_program, theirs_in_program),
    # A val as prints' length, and a timer's tim and en as each command's
    # operands, beside a second number and a timer.
    Probe("serial-commands-vals-and-a-timer", "T", with_attributes(
        ["prints t0.txt,n0.val", "prints n0.val,n1.val", "get tm0.tim", "get tm0.en",
         "print tm0.tim", "print tm0.en", "prints tm0.tim,2", "prints t0.txt,tm0.tim"],
        [text_component("t0", txt="12"), number_component("n0", y=60, val=7),
         number_component("n1", y=110), timer_component()]),
        ours_in_event, theirs_in_event, FIXTURES),
    # A touch capture's val as each command's operand and as prints'
    # length.
    Probe("serial-commands-touch-capture-val", "T", with_attributes(
        ["get tc0.val", "print tc0.val", "prints tc0.val,1", "prints t0.txt,tc0.val"],
        [text_component("t0", txt="12"), touch_capture_component(val=5)]),
        ours_in_event, theirs_in_event, FIXTURES),
]
