"""The probes of the drawing commands (instructions/drawing_commands.py):
lines of them added to the T base folder, in strict Nextion syntax, each
compared with the blocks the Nextion Editor wrote, through the statement
probes' own ways of cutting them (statement_probes.py). Run them with
`tools.tft.probe run drawing_probes`.

The probes in page0's Touch Release event keep fixtures: the event's blocks,
back to back with their size words.
"""
from tools.tft.probing.attribute_probes import with_attributes
from tools.tft.probing.button_probes import button_component
from tools.tft.probing.dual_state_button_probes import dual_state_button_component
from tools.tft.probing.number_probes import number_component
from tools.tft.probing.probe_runner import Probe
from tools.tft.probing.qr_code_probes import qr_code_component
from tools.tft.probing.scrolling_text_probes import scrolling_text_component
from tools.tft.probing.statement_probes import (event_lines, ours_in_event, ours_in_program,
                                            program_lines, theirs_in_event, theirs_in_program)
from tools.tft.probing.text_probes import text_component
from tools.tft.probing.timer_probes import timer_component
from tools.tft.probing.variable_probes import text_variable_component

FIXTURES = "drawing"
# Every character a text may hold: the printable ASCII characters but `"`
# and `\`.
_PRINTABLE = "".join(chr(code) for code in range(0x20, 0x7F) if chr(code) not in '"\\')

PROBES = [
    # Each command, its operands numbers and colours' names.
    Probe("drawing-each-command", "T", event_lines([
        "cls RED", "fill 0,0,100,50,RED", "line 0,0,100,100,GREEN", "draw 10,10,50,50,BLACK",
        "cir 50,50,20,RED", "cirs 50,50,20,BLUE"]),
        ours_in_event, theirs_in_event, FIXTURES),
    # Each kind of operand: program.s's int variables, system variables, and
    # numbers at their bounds, 999 the longest kept as text, 32 bits the
    # widest; and a space after each comma.
    Probe("drawing-operands", "T", event_lines([
        "cls a", "fill sys0,sys1,10,20,BLUE", "draw sys0,sys1,sys2,dim,WHITE",
        "line -5,0,100,-10,BLUE", "line -100,-1000,999,0,YELLOW",
        "fill 1000,0,10,10,65535", "cir 2147483647,-2147483648,0,GRAY", "cls 0",
        "cirs 0,0,0,0", "cir 50, 50, 20, RED"], ["int a=1"]),
        ours_in_event, theirs_in_event, FIXTURES),
    # The same commands in program.s, before its page 0.
    Probe("drawing-in-program", "T", program_lines([
        "cls BLUE", "fill 0,0,320,480,WHITE", "line 0,0,319,479,RED", "draw 1,1,318,478,dim",
        "cir 160,240,100,sys0", "cirs 160,240,50,BROWN"]),
        ours_in_program, theirs_in_program),
    # The commands of a picture, each kind of operand, and a picture the
    # project does not have: the base folder has none.
    Probe("drawing-pictures", "T", event_lines([
        "pic 0,0,0", "pic 10,20,1", "picq 0,0,8,4,0", "xpic 0,0,4,4,2,1,1", "pic sys0,sys1,a",
        "picq 0,0,1000,1000,dim", "xpic -5,-10,4,4,sys0,sys1,RED", "pic 0, 0, 5"], ["int a=1"]),
        ours_in_event, theirs_in_event, FIXTURES),
    # xstr: an empty text; spaces and commas in a text; every character a
    # text may hold; a comment's two slashes; each kind of operand, and a
    # font the project does not have; a space after each comma; and the
    # longest line the Nextion Editor takes on T and K, 767 characters.
    Probe("drawing-texts", "T", event_lines([
        'xstr 0,0,100,30,0,RED,WHITE,1,1,1,"hello"', 'xstr 10,10,50,20,0,BLACK,BLUE,0,0,0,""',
        'xstr 0,0,100,30,0,RED,WHITE,1,1,1,"a b,c"',
        'xstr 0,0,320,40,0,RED,WHITE,0,0,0,"%s"' % _PRINTABLE,
        'xstr 0,0,10,10,0,RED,WHITE,0,0,0,"// not a comment"',
        'xstr sys0,sys1,sys2,dim,a,65535,-1,2,2,3,"x"', 'xstr 0,0,10,10,3,GREEN,BROWN,0,0,0,"x"',
        'xstr 0, 0, 100, 30, 0, RED, WHITE, 1, 1, 1, "hi"',
        'xstr 0,0,10,10,0,RED,WHITE,0,0,0,"%s"' % ("a" * 732)], ["int a=1"]),
        ours_in_event, theirs_in_event, FIXTURES),
    # xstr's text as one operand: the txt of each type that gives code a
    # txt, a number's val, a timer's tim and en, an int and a system
    # variable, a colour's name, and numbers, beside those components.
    Probe("drawing-xstr-text-operands", "T", with_attributes(
        ["xstr 0,0,100,30,0,RED,WHITE,0,0,1,%s" % text for text in (
            "t0.txt", "va0.txt", "b0.txt", "bt0.txt", "qr0.txt", "g0.txt", "n0.val", "tm0.tim",
            "tm0.en", "sys0", "dim", "RED", "1000", "0x41", "-5")],
        [text_component(), number_component(y=60), timer_component(),
         text_variable_component(), button_component(x=150, y=200),
         dual_state_button_component(y=270), qr_code_component(x=150, y=270),
         scrolling_text_component(y=400)]),
        ours_in_event, theirs_in_event, FIXTURES),
    # The commands of a picture and xstr in program.s.
    Probe("drawing-pictures-and-texts-in-program", "T", program_lines([
        "pic 0,0,0", "picq 0,0,8,4,1", "xpic 0,0,4,4,2,1,1",
        'xstr 0,0,100,30,0,RED,WHITE,1,1,1,"in program.s"']),
        ours_in_program, theirs_in_program),
]
