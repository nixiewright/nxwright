"""The probes of conditions past what the first probes of if, while, and
for showed (control_statements.py): more than 3 comparisons, up to 80 in a
condition of 788 characters; texts that hold && or ||, which the Nextion
Editor leaves in the text; and texts of up to 740 characters together. Run
them with `tools.tft.probe run condition_probes`.

The probes of numbers alone are in program.s; those of texts are in page0's
Touch Release event, beside the text t0. Each compares the blocks of its
run of lines, and keeps them as its fixture (statement_probes.py gives
both).
"""
from tools.tft.probing.attribute_probes import with_attributes
from tools.tft.probing.for_probes import LONGEST_START
from tools.tft.probing.probe_runner import Probe
from tools.tft.probing.statement_probes import (ours_in_event, ours_in_program, program_lines,
                                            theirs_in_event, theirs_in_program)
from tools.tft.probing.text_probes import text_component

FIXTURES = "conditions"


def _joined(join: str, count: int, name: str = "sys0") -> str:
    """Returns a condition of `count` comparisons of `name` with 0, 1, and
    so on, joined by `join`."""
    return join.join("%s==%d" % (name, number) for number in range(count))


def _braced(head: str, body: str) -> list:
    return [head, "{", body, "}"]


def _program_probe(name: str, lines: list) -> Probe:
    return Probe("conditions-" + name, "T", program_lines(lines), ours_in_program,
                 theirs_in_program, FIXTURES)


def _event_probe(name: str, lines: list) -> Probe:
    return Probe("conditions-" + name, "T", with_attributes(lines, [text_component()]),
                 ours_in_event, theirs_in_event, FIXTURES)


PROBES = [
    # An if of 4 comparisons joined by &&, of 5 by ||, of 12 by &&, and of 80
    # by ||, a condition of 788 characters.
    _program_probe("many-comparisons-in-if", [
        *_braced("if(%s)" % _joined("&&", 4), "sys1=1"),
        *_braced("if(%s)" % _joined("||", 5), "sys1=2"),
        *_braced("if(%s)" % _joined("&&", 12), "sys1=3"),
        *_braced("if(%s)" % _joined("||", 80), "sys1=4")]),
    # A while of 12 comparisons joined by &&, and one of 80 joined by ||.
    _program_probe("many-comparisons-in-while", [
        *_braced("while(%s)" % _joined("&&", 12, "sys1"), "sys1++"),
        *_braced("while(%s)" % _joined("||", 80), "sys0++")]),
    # A for whose condition has 80 comparisons joined by ||, and one whose
    # start has the longest a line takes on T, 767 characters, too.
    _program_probe("many-comparisons-in-for", [
        *_braced("for(sys2=0;%s;sys2++)" % _joined("||", 80), "sys1++"),
        *_braced("for(%s;%s;sys0++)" % (LONGEST_START, _joined("||", 80, "sys1")), "sys2++")]),
    # Texts that hold && or ||, alone or beside a comparison of numbers, in
    # if and while, one with an escape.
    _event_probe("texts-holding-joins", [
        *_braced('if(t0.txt=="a&&b")', "sys0=1"),
        *_braced('if(t0.txt=="a||b"&&sys0==1)', "sys0=2"),
        *_braced('if(t0.txt=="&&"||t0.txt=="||")', "sys0=3"),
        *_braced('while(t0.txt!="x&&y")', 't0.txt="x&&y"'),
        *_braced(r'if(t0.txt=="a\"&&b"||sys0==4)', "sys0=5")]),
    # A text of 740 characters, and two of 450 and 290.
    _event_probe("long-texts", [
        *_braced('if(t0.txt=="%s")' % ("a" * 740), "sys0=1"),
        *_braced('if(t0.txt=="%s"||t0.txt=="%s")' % ("b" * 450, "c" * 290), "sys0=2")]),
]
