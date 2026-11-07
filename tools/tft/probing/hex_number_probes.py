"""The probes of hexadecimal numbers in assignments and in the conditions of
if, while, and for (statements.py and control_statements.py): lines added
to the T base folder, in strict Nextion syntax, each compared with the
blocks the Nextion Editor wrote, through the statement probes' own ways of
cutting them (statement_probes.py). Run them with
`tools.tft.probe run hex_number_probes`.

The probes in page0's Touch Release event put a text, t0, and two numbers,
n0 and n1, on page0, and declare the int variable a in program.s. Each
probe keeps fixtures: the blocks of the event or of program.s, back to back
with their size words.
"""
from tools.tft.probing.probe_runner import Probe
from tools.tft.probing.statement_probes import (beside_a_text_and_numbers, ours_in_event,
                                            ours_in_program, program_lines, theirs_in_event,
                                            theirs_in_program)

FIXTURES = "hex-numbers"


PROBES = [
    # A hexadecimal number as an assignment's whole value, of 1 to 4 bytes,
    # with 0X, and set to a system variable, an int variable, and a number's
    # val; then beside each arithmetic operator, with += and -=.
    Probe("hex-numbers-in-assignments", "T", beside_a_text_and_numbers([
        "sys0=0x12", "sys0=0xFFFF", "sys0=0x00", "sys0=0xFFFFFFFF", "sys0=0X12",
        "n0.val=0x12", "a=0x0102", "sys0 = 0x12", "sys0=sys1+0x12", "sys0=0x12+sys1",
        "sys0=0x10*2", "sys0=0xFF&sys1", "sys0=sys1<<0x02", "sys0=0x01+0x02", "sys0+=0x10",
        "sys0-=0x01", "n0.val+=0x0A", "sys0=n0.val%0x10", "sys0=sys1-0x01", "sys0=0x10/2",
        "sys0=sys1|0x01", "sys0=sys1^0xFF", "sys0=sys1>>0x01"]),
        ours_in_event, theirs_in_event, FIXTURES),
    # A hexadecimal number on each side of a comparison, in if, while, and
    # for, the for's start and step among them, with each comparison,
    # joined with && and ||, and two of them compared.
    Probe("hex-numbers-in-conditions", "T", beside_a_text_and_numbers([
        "if(sys0==0x12)", "{", "sys1=1", "}", "if(0x12!=sys0)", "{", "sys1=2", "}",
        "if(n0.val<0xFF)", "{", "sys1=3", "}", "while(sys0<0x10)", "{", "sys0++", "}",
        "for(sys0=0x00;sys0<0x10;sys0+=0x01)", "{", "sys1++", "}",
        "if(sys0==0x12&&sys1>0x01)", "{", "sys1=4", "}", "if(0x01==0x02)", "{", "sys1=5", "}",
        "if(sys0<=0x12||sys1>=0x01)", "{", "sys1=6", "}"]),
        ours_in_event, theirs_in_event, FIXTURES),
    # Assignments in program.s, before its page 0.
    Probe("hex-numbers-in-program", "T", program_lines([
        "sys0=0x12", "sys1=sys0+0xFF", "sys2=0xFFFF"]),
        ours_in_program, theirs_in_program, FIXTURES),
]
