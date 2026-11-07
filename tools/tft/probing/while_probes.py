"""The while statement's probes (instructions/while_statement.py): while
statements added to the T base folder, in strict Nextion syntax, a few of
one kind a probe. Each compares the blocks the statement encoder gives the
run of lines (statements.encode_code) with those the Nextion Editor wrote,
and keeps them as one fixture, as the statement encoder's probes do
(statement_probes.py), in program.s or in page0's Touch Release event.

Run them with `tools.tft.probe run while_probes`.
"""
from tools.tft.probing.probe_runner import Probe
from tools.tft.probing.statement_probes import (event_lines, ours_in_event, ours_in_program,
                                            program_lines, theirs_in_event, theirs_in_program)

_FIXTURES = "while"


def _while(condition: str, body: list) -> list:
    """The lines of `while(condition)` with `body`."""
    return ["while(%s)" % condition, "{", *body, "}"]


def _program_probe(name: str, lines: list, declarations: list = ()) -> Probe:
    return Probe(name, "T", program_lines(lines, declarations), ours_in_program,
                 theirs_in_program, _FIXTURES)


PROBES = [
    # One comparison, && and || of two and three, and an empty body.
    _program_probe("while-conditions", [
        *_while("sys0<3", ["sys0++"]),
        *_while("sys0<3&&sys1>2", ["sys0++"]),
        *_while("sys0<3&&sys1>2&&sys2!=4", ["sys1--"]),
        *_while("sys0<3||sys1>2", ["sys0++"]),
        *_while("sys0>=3||sys1<=2||sys2==4", ["sys2++"]),
        *_while("sys0==1", [])]),
    # || before an empty body: the inverted comparisons land on the jump
    # back to the condition.
    _program_probe("while-or-empty-body", [
        *_while("sys0==1||sys1==2", []),
        *_while("sys0<1||sys1>2||sys2!=3", [])]),
    # Statements within statements: an if ending a while's body, with and
    # without an else; a while within a while; a while ending an if's body
    # that an else follows, and within an else.
    _program_probe("while-nested", [
        *_while("sys0<5", ["if(sys1==2)", "{", "sys1=3", "}else", "{", "sys1=4", "}"]),
        *_while("sys0<5", ["if(sys1==2)", "{", "sys1=3", "}"]),
        *_while("sys0<5", [*_while("sys1<3", ["sys1++"])]),
        "if(sys0==1)", "{", *_while("sys1<3", ["sys1++"]), "}else", "{",
        *_while("sys2<3", ["sys2++"]), "}"]),
    # Each kind of operand, and spaces and tabs around a line's parts.
    _program_probe("while-operands", [
        *_while("dim>=1000", ["dim--"]),
        *_while("a!=RED", ["a=RED"]),
        *_while("-5<sys0", ["sys0--"]),
        "while ( sys0 < 3 )", " {", "sys0 ++", "\t} "], ["int a=1"]),
    # A while in an event.
    Probe("while-event", "T", event_lines(_while("sys0<2&&sys1<2", ["sys0++"])),
          ours_in_event, theirs_in_event, _FIXTURES),
]
