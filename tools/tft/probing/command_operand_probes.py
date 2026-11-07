"""The probes of commands' operands (statements.py and instructions/): an
expression where a command takes a number, as in `cls RED+1`; a component's
val, a timer's tim or en in the drawing and screen commands; a hexadecimal
number in every family of commands; crcputh's most bytes; and texts with
the escapes the screen reads, `\\\\`, `\\"`, and `\\r`, in commands,
assignments, and conditions. Run them with
`tools.tft.probe run command_operand_probes`.

The probes in page0's Touch Release event put a text, t0, two numbers, n0
and n1, a timer, tm0, and a waveform, s0, on page0. Each probe on T keeps
fixtures: the blocks of the event or of program.s, back to back with their
size words. The probe of K's own commands keeps its own, on K.
"""
from tools.tft.probing.attribute_probes import with_attributes
from tools.tft.probing.number_probes import number_component
from tools.tft.probing.probe_runner import Probe
from tools.tft.probing.statement_probes import (ours_in_event, ours_in_program, program_lines,
                                            theirs_in_event, theirs_in_program)
from tools.tft.probing.text_probes import text_component
from tools.tft.probing.timer_probes import timer_component
from tools.tft.probing.waveform_probes import waveform_component

FIXTURES = "command-operands"

COMPONENTS = [text_component(), number_component(y=60), number_component("n1", y=110),
              timer_component(), waveform_component(y=200)]


# The lines of the probe of K's own commands: an expression, a number's val,
# and a hexadecimal number where each takes a number, repo's destination
# and wepo's value as a hexadecimal number, and wepo's value as a text with
# each escape.
EEPROM_AND_GPIO = [
    "wepo n0.val,5+1", "repo n0.val,5+1", "wept 0+0,10", "rept 0,10*2", "cfgpio 1+1,1,n0",
    "cfgpio 2,0+1,n0", "wepo n0.val,0x10", "repo n0.val,0x10", "repo 0x05,0",
    "wept 0x00,0x10", "rept 0x00,0x0A", "cfgpio 0x02,0x01,n0", "wepo 0x05,0",
    "wept n0.val,n1.val", "rept n0.val,n1.val", "cfgpio n0.val,n1.val,n0",
    r'wepo "a\\b\"c\r",0']


def _probe(name: str, lines: list, series: str = "T") -> Probe:
    return Probe("command-operands-" + name, series, with_attributes(lines, COMPONENTS),
                 ours_in_event, theirs_in_event, FIXTURES)


PROBES = [
    # An expression in each argument of each drawing command, each
    # arithmetic operator, and several operators in one argument.
    _probe("expressions-in-drawing-commands", [
        "cls RED+1", "fill 1+1,2+2,3+3,4+4,RED+1", "line 1+1,2+2,3+3,4+4,RED+1",
        "draw 1+1,2+2,3+3,4+4,RED+1", "cir 50+1,50+1,10+1,RED+1", "cirs 50+1,50+1,10+1,RED+1",
        "pic 1+1,2+2,0*1", "picq 1+1,2+2,3+3,4+4,0*1", "xpic 1+1,2+2,3+3,4+4,5+5,6+6,0*1",
        'xstr 1+1,2+2,100+1,30+1,0*1,RED+1,WHITE+1,0+1,0+1,1+1,"a"',
        "cls RED-1", "cls RED*2", "cls RED/2", "cls RED%2", "cls RED&1", "cls RED|1",
        "cls RED^1", "cls RED<<1", "cls RED>>1", "fill 0,0,10+5*2,10,RED",
        "fill 0,0,10-5+2,10,RED", "line 0,0,n0.val*2,10,RED", "cirs 10,10,n0.val/2,RED",
        "cls -5+1"]),
    # An expression where each other family's command takes a number: the
    # screen commands after the component, prints' length, the text
    # commands' lengths, forms, starts, counts, and parts, the CRC commands
    # but crcputs' value, and every argument of the waveform commands, the
    # ID included.
    _probe("expressions-in-other-commands", [
        "vis t0,1+0", "tsw t0,n0.val+1", "click t0,1-1", "randset 0+1,100*2",
        "prints t0.txt,n0.val+1", 'prints "ab",1+1', "covx n0.val,t0.txt,n1.val*2,1+0",
        "cov n0.val,t0.txt,1+1", "substr t0.txt,t0.txt,n0.val,1*2",
        'spstr t0.txt,t0.txt,"a",n0.val+0', "crcrest 0+1,0xFFFF+1", "crcputs t0.txt,0+1",
        "crcputs n0.val,4-2", "crcputu sys0+1,1+1", "add s0.id,0,sys0+1",
        "add s0.id+0,0+0,n0.val*2", "addt s0.id,1*1,10+5", "cle s0.id,255-0", "cle 5+0,0"]),
    # A number's val and a timer's tim and en in each drawing command and
    # in the screen commands.
    _probe("attributes-in-drawing-and-screen-commands", [
        "cls n0.val", "fill n0.val,n1.val,tm0.tim,n0.val+1,tm0.en",
        "line n0.val,0,10,n1.val,RED", "draw n0.val,0,10,10,tm0.tim",
        "cir n0.val,10,10,RED", "cirs 10,n1.val,10,RED", "pic n0.val,n1.val,0",
        "picq n0.val,0,10,10,0", "xpic n0.val,0,10,10,0,0,tm0.en",
        'xstr n0.val,n1.val,100,30,0,n0.val,n1.val,0,0,1,"a"', "vis t0,n0.val",
        "tsw t0,tm0.en", "click t0,n1.val", "randset tm0.tim,n0.val", "vis 1,n0.val*2"]),
    # A hexadecimal number in each drawing command, the screen commands,
    # the serial commands, the text commands, and the waveform commands.
    _probe("hex-numbers", [
        "cls 0xF800", "fill 0x00,0x00,0x0A,0x0A,0xF800", "line 0x00,0,10,10,RED",
        "draw 0x00,0x00,0x0A,0x0A,0x001F", "cir 0x10,0x10,0x05,0xF800", "cirs 10,10,0x05,RED",
        "pic 0x00,0x00,0x00", "picq 0x00,0x00,0x0A,0x0A,0x00",
        "xpic 0x00,0x00,0x0A,0x0A,0x00,0x00,0x00",
        'xstr 0,0,100,30,0,0xF800,0x0000,0,0,1,"a"', "vis t0,0x01", "vis 1,0x01",
        "click t0,0x01", "randset 0x00,0x64", "get 0x10", "print 0x10", "prints 0x10,2",
        'prints "ab",0x01', "covx 0x12,t0.txt,1+1,0x00", "cov sys0,t0.txt,0x01",
        "cov 0x12,t0.txt,0", "substr t0.txt,t0.txt,0+1,0x02", "add 0x05,0,0x10",
        "addt 0x05,0x00,0x01", "cle s0.id,0x01", "crcputs 0x01,4"]),
    # A hexadecimal number in the other places: tsw's state, cle's ID, and
    # the text commands' sources, destinations, and separator, where the
    # Nextion Editor does not check an operand's kind.
    _probe("hex-numbers-in-other-places", [
        "tsw t0,0x01", "cle 0x05,0", "strlen t0.txt,0x10", "btlen 0x10,sys0",
        "substr 0x10,t0.txt,0,1", "spstr t0.txt,t0.txt,0x2C,0", "cov n0.val,0x10,0",
        "covx n0.val,0x10,0,0"]),
    # crcputh with 253 bytes, as many as a line of 767 characters holds.
    _probe("crcputh-253-bytes", ["crcputh " + " ".join("%02x" % number
                                                        for number in range(253))]),
    # Texts with each escape the screen reads, in the commands that take a
    # text, and in assignments.
    _probe("escapes", [
        r'xstr 0,0,100,30,0,RED,WHITE,0,0,1,"a\\b"', r'xstr 0,0,100,30,0,RED,WHITE,0,0,1,"a\"b"',
        r'xstr 0,0,100,30,0,RED,WHITE,0,0,1,"a\rb"', r'xstr 0,0,100,30,0,RED,WHITE,0,0,1,"\\"',
        r'prints "a\\b",0', r'print "a\"b"', r'get "\r"', r'spstr t0.txt,t0.txt,"\\",0',
        r'strlen "a\\b",sys0', r'btlen "a\"b",sys0', r'crcputs "a\\b",0', r't0.txt="a\\b"',
        r't0.txt="a\"b"', r't0.txt="a\rb"', r't0.txt+="\r"', r't0.txt="a"+"\\"+t0.txt',
        r't0.txt="\"\\\r"']),
    # Texts with the escapes in the conditions of if, while, and for. The
    # Nextion Editor refused a text ending in `\\` there ("SYNTAX ERROR#1").
    _probe("escapes-in-conditions", [
        r'if(t0.txt=="a\\b")', "{", "sys0=1", "}", r'while(t0.txt!="\"")', "{", "sys0=2", "}",
        r'for(sys0=0;t0.txt=="\r";sys0++)', "{", "sys1=3", "}",
        r'if(t0.txt=="\\\\a"||"a\"b"!=t0.txt)', "{", "sys0=4", "}"]),
    # Expressions and hexadecimal numbers in program.s, before its page 0.
    Probe("command-operands-in-program", "T", program_lines([
        "cls RED+1", "fill 0x00,0,10*2,10,RED", "randset 0+1,0x64", "add 1+0,0,0x10",
        "crcrest 0+1,0xFFFF", r'xstr 0,0,100,30,0,RED,WHITE,0,0,1,"a\\b"']),
        ours_in_program, theirs_in_program, FIXTURES),
    # K's own commands (EEPROM_AND_GPIO).
    _probe("eeprom-and-gpio", EEPROM_AND_GPIO, series="K"),
]
