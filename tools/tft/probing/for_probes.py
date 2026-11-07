"""The for statement's probes (instructions/for_statement.py): for
statements added to the T base folder, in strict Nextion syntax, a few of
one kind a probe. Each compares the blocks the statement encoder gives the
run of lines (statements.encode_code) with those the Nextion Editor wrote,
and keeps them as one fixture, as the statement encoder's probes do
(statement_probes.py), in program.s or in page0's Touch Release event.

Run them with `tools.tft.probe run for_probes`.
"""
from tools.tft.probing.probe_runner import Probe
from tools.tft.probing.statement_probes import (event_lines, ours_in_event, ours_in_program,
                                            program_lines, theirs_in_event, theirs_in_program)

_FIXTURES = "for"
# The longest start the Nextion Editor takes on T and K, 767 characters.
# It holds a for's start to the 767 characters it holds a line to, as a
# line of its own, not the whole head.
LONGEST_START = "sys0=" + "+".join(["1"] * 380 + ["11"])


def _for(start: str, condition: str, step: str, body: list) -> list:
    """The lines of `for(start;condition;step)` with `body`."""
    return ["for(%s;%s;%s)" % (start, condition, step), "{", *body, "}"]


def _program_probe(name: str, lines: list, declarations: list = ()) -> Probe:
    return Probe(name, "T", program_lines(lines, declarations), ours_in_program,
                 theirs_in_program, _FIXTURES)


PROBES = [
    # One comparison, && and || of two and three, and empty bodies, || before
    # one among them.
    _program_probe("for-conditions", [
        *_for("sys0=0", "sys0<3", "sys0++", ["sys1++"]),
        *_for("sys0=0", "sys0<3&&sys1>2", "sys0++", ["sys1++"]),
        *_for("sys0=0", "sys0<3&&sys1>2&&sys2!=4", "sys0++", ["sys1--"]),
        *_for("sys0=0", "sys0<3||sys1>2", "sys0++", []),
        *_for("sys0=9", "sys0>=3||sys1<=2||sys2==4", "sys0--", ["sys2++"]),
        *_for("sys0=10", "sys0>0", "sys0-=2", [])]),
    # Starts and steps of each kind of assignment and operand, and spaces and
    # tabs around a line's parts.
    _program_probe("for-starts-and-steps", [
        *_for("sys0=sys1+1", "sys0<=1000", "sys0+=sys1", []),
        *_for("dim=0", "dim<100", "dim++", ["sys0=dim"]),
        *_for("a=-1000", "a!=RED", "a+=1000", []),
        "for ( sys0 = 0 ; sys0 < 3 ; sys0 ++ )", " {", "sys1++", "\t} "], ["int a=1"]),
    # Statements within statements: a for within a for; a while and an if
    # ending a for's body; a for ending a while's body, and an if's that an
    # else follows; and a for within an else.
    _program_probe("for-nested", [
        *_for("dim=0", "dim<100", "dim++", _for("sys0=0", "sys0<3", "sys0++", [])),
        *_for("sys0=0", "sys0<5", "sys0++", ["while(sys1<3)", "{", "sys1++", "}"]),
        *_for("sys0=0", "sys0<5", "sys0++", ["if(sys1==2)", "{", "sys1=3", "}else", "{",
                                             "sys1=4", "}"]),
        "while(sys2<3)", "{", *_for("sys0=0", "sys0<3", "sys0++", ["sys1++"]), "}",
        "if(sys0==1)", "{", *_for("sys1=0", "sys1<3", "sys1++", ["sys2++"]), "}else", "{",
        *_for("sys2=0", "sys2<3", "sys2++", []), "}"]),
    # A for in an event.
    Probe("for-event", "T", event_lines(_for("sys0=0", "sys0<2", "sys0++", ["sys1++"])),
          ours_in_event, theirs_in_event, _FIXTURES),
    # A for whose start has 767 characters, so its head has 787.
    Probe("for-longest-start", "T", event_lines(_for(LONGEST_START, "sys0<10", "sys0++", [])),
          ours_in_event, theirs_in_event, _FIXTURES),
]
