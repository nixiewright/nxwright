"""The probes of forms of code that the Nextion Editor writes as plainer ones
(project.plain_lines, frame.read_int_declaration, and statements' _parts):
int declarations with spaces after their commas, indented, with a comment
after them, and of names without a value; lines of code, in program.s, in
an event, and in a macro, indented and with a comment after them; a negative
number after each arithmetic operator, in assignments and in commands'
operands; and a label of 762 characters, whose goto's line is the longest
the Nextion Editor compiles. Run them with
`tools.tft.probe run code_form_probes`.

Most probes put their lines in page0's Touch Release event. Those of
comments and of negative numbers in assignments put the text t0 and the
numbers n0 and n1 on page0, and declare `int a=1` (statement_probes.py).
The probe of commands puts the waveform s0 and the number n0 there instead.
These compare the event's blocks, and keep them as fixtures.

The others compare the whole file. The declarations' values lie in the
user code's int variables, outside program.s's blocks. The frame writes a
goto's place once it has every page's, and a macro's lines lie outside the
event's blocks.
"""
from tools.tft.probing.component_probes import editor_file, whole_file
from tools.tft.probing.macro_probes import with_macros
from tools.tft.probing.number_probes import number_component
from tools.tft.probing.probe_runner import Probe
from tools.tft.probing.statement_probes import (ProgramChange, beside_a_text_and_numbers, event_lines,
                                            ours_in_event, program_lines, theirs_in_event,
                                            touch_release_code)
from tools.tft.probing.waveform_probes import waveform_component

FIXTURES = "code-forms"

# A label's name of 762 characters: `goto` and a space before it make a
# line of 767, the longest the Nextion Editor compiles on T.
_LONGEST_LABEL = ("abcdefghijklmnopqrstuvwxyz" * 30)[:762]


def _beside_a_waveform(lines: list) -> ProgramChange:
    """Returns a change that gives page0's Touch Release event `lines`, and
    puts the waveform s0 and the number n0 on page0 (ProgramChange)."""
    return ProgramChange(code=touch_release_code(lines),
                         components=(waveform_component(), number_component(y=150)))


PROBES = [
    Probe("code-forms-declarations", "T", program_lines(["sys0=5 // a comment"], [
        "int a=1, b=2", "  int c=3", "int d=4 // a comment", "int e", "int f, g=7,  h"]),
        whole_file, editor_file),
    Probe("code-forms-comments-after-code", "T", beside_a_text_and_numbers([
        "sys0=1 // a comment", "  sys1=2 // b", "\tsys2=3", 't0.txt="http://x" // c',
        "n0.val=a\t// tab"]),
        ours_in_event, theirs_in_event, FIXTURES),
    Probe("code-forms-negative-after-operators", "T", beside_a_text_and_numbers([
        "sys0=2*-16", "sys1=5+-3", "sys2=sys0--1", "sys0=8/-2", "sys0=7%-3", "sys0=6&-1",
        "sys0=6|-1", "sys0=6^-1", "sys0=1<<-1", "sys0=8>>-1", "n0.val=n1.val*-2",
        "sys0=a+-1", "sys0+=-4", "n0.val=1--2-3", "sys0=2*-999", "sys0=2*-1000"]),
        ours_in_event, theirs_in_event, FIXTURES),
    Probe("code-forms-negative-in-commands", "T", _beside_a_waveform([
        "cls RED+-1", "fill 0,0,10,10,RED*-1", "crcrest 1,sys0+-1", "add s0.id,0,sys0+-1",
        "add s0.id,0,n0.val--1"]),
        ours_in_event, theirs_in_event, FIXTURES),
    Probe("code-forms-label-of-762", "T", event_lines([_LONGEST_LABEL + ":", "sys0++",
                                                       "goto " + _LONGEST_LABEL]),
          whole_file, editor_file),
    # A macro's lines indented, with comments after them, a label's and a
    # goto's among them.
    Probe("code-forms-in-a-macro", "T", with_macros(
        [("m", ["sys0=1 // a comment", "  sys1=2", "\tsys2=3 // c", "again: // a label",
                "sys0++", "if(sys0<3) // a condition", "{", "  goto again // back", "}"])],
        ["call m"]),
        whole_file, editor_file),
]
