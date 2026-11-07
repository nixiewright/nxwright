"""The if statement's probes (instructions/if_statement.py): if statements
added to the T base folder, in strict Nextion syntax, a few of one kind a
probe. Each compares the blocks the statement encoder gives the run of
lines (statements.encode_code) with those the Nextion Editor wrote, and
keeps them as one fixture, as the statement encoder's probes do
(statement_probes.py), in program.s or in page0's Touch Release event.

Run them with `tools.tft.probe run if_probes`.
"""
from tools.tft.probing.probe_runner import Probe
from tools.tft.probing.statement_probes import (event_lines, ours_in_event, ours_in_program,
                                            program_lines, theirs_in_event, theirs_in_program)

_FIXTURES = "if"


def _statement(condition: str, body: list, otherwise: list = None) -> list:
    """The lines of `if(condition)` with `body`, and an else of `otherwise`
    when given."""
    lines = ["if(%s)" % condition, "{", *body, "}"]
    if otherwise is not None:
        lines[-1:] = ["}else", "{", *otherwise, "}"]
    return lines


def _program_probe(name: str, lines: list, declarations: list = ()) -> Probe:
    return Probe(name, "T", program_lines(lines, declarations), ours_in_program,
                 theirs_in_program, _FIXTURES)


_COMPARISONS = ("==", "<", ">", "<=", ">=", "!=")
PROBES = [
    # Each comparison, alone.
    _program_probe("if-comparisons", [
        line for number, comparison in enumerate(_COMPARISONS)
        for line in _statement("sys0%s1" % comparison, ["sys1=%d" % number])]),
    # else, an empty body, an empty else, and an if within a body and an else.
    _program_probe("if-else", [
        *_statement("sys0==1", ["sys1=2"], ["sys1=3"]),
        *_statement("sys0==1", []),
        *_statement("sys0==1", ["sys1=4"], []),
        *_statement("sys0==1", [*_statement("sys1==2", ["sys2=9"]), "sys2=10"]),
        *_statement("sys0==1", ["dim=7"], _statement("sys1==2", ["dim=8"]))]),
    # Statements three levels deep, within bodies, an else, and an else if.
    _program_probe("if-nested", _statement(
        "sys0==1", _statement("sys1==2", _statement("sys2==3", ["dim=1"], ["dim=2"])),
        ["if(sys1==4||sys2==5)", "{", *_statement("dim>=10", ["dim=3"]), "}else if(sys1==6)",
         "{", *_statement("sys2<7&&dim>8", ["dim=4"]), "}"])),
    # A jump onto a jump onto a jump: each statement ends a body that an else
    # follows.
    _program_probe("if-nested-chain", _statement(
        "sys0==1", _statement("sys1==2", _statement("sys2==3", ["dim=1"], ["dim=2"]), ["dim=3"]),
        ["dim=4"])),
    # || over an empty body that another branch follows: the inverted
    # comparison lands on the jump after the body.
    _program_probe("if-or-empty-body", [
        *_statement("sys0==1||sys1==2", [], ["sys2=3"]),
        "if(sys0<1||sys1>2||sys2!=3)", "{", "}else if(dim==4)", "{", "dim=5", "}"]),
    # else if, with an else after it and without.
    _program_probe("if-else-if", [
        "if(sys0==1)", "{", "sys1=4", "}else if(sys0==2)", "{", "sys1=5", "}else", "{",
        "sys1=6", "}",
        "if(sys0==1)", "{", "sys1=7", "}else if(sys0==2)", "{", "sys1=8",
        "}else if(sys0>=3)", "{", "sys1=9", "}"]),
    # && of two and of three comparisons.
    _program_probe("if-and", [
        *_statement("sys0==1&&sys1==2", ["sys2=7"]),
        *_statement("sys0==1&&sys1==2&&sys2==3", ["dim=1"]),
        *_statement("sys0<1&&sys1>2", ["dim=2"], ["dim=3"])]),
    # || of two and of three comparisons, each comparison inverted once.
    _program_probe("if-or", [
        *_statement("sys0==1||sys1==2", ["sys2=8"]),
        *_statement("sys0==1||sys1==2||sys2==3", ["dim=2"]),
        *_statement("sys0<1||sys1>2||sys2<=3", ["dim=5"]),
        *_statement("sys0>=1||sys1!=2", ["dim=6"])]),
    # Each kind of operand: a number on the left, long numbers, a system
    # variable, a colour, and a declared int.
    _program_probe("if-operands", [
        *_statement("1==sys0", ["dim=6"]),
        *_statement("dim>=1000", ["sys2=11"]),
        *_statement("sys0<-1000", ["sys2=12"]),
        *_statement("sys0>-5", ["sys2=14"]),
        *_statement("sys0!=007", ["sys2=15"]),
        *_statement("a!=RED", ["a=1"]),
        *_statement("bkcmd==a", ["sys2=13"])], ["int a=1"]),
    # Spaces and tabs around an if's parts, which the encoder drops.
    _program_probe("if-spaces", [
        "if (sys0 == 1)", " {", "sys1 = 2", "} else if ( sys0 > 2 && sys1 < 3 )", "{",
        "sys1=3", "}\telse", "{", "sys1=4", " } "]),
    # An if with else if and else in an event.
    Probe("if-event", "T", event_lines([
        "if(sys0==1)", "{", "sys1=4", "}else if(sys0==2&&sys1<3)", "{", "sys1=5",
        "}else", "{", "sys1=6", "}"]),
        ours_in_event, theirs_in_event, _FIXTURES),
]
