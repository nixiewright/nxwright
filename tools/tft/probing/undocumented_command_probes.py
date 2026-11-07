"""The probes of the undocumented commands
(instructions/undocumented_commands.py): lines of them added to the T base
folder, in strict Nextion syntax, each compared with the blocks the
Nextion Editor wrote, through the statement probes' own ways of cutting
them (statement_probes.py). Run them with
`tools.tft.probe run undocumented_command_probes`.

The probes in page0's Touch Release event put a text, t0, and two numbers,
n0 and n1, on page0, whose txt and vals the lines use, and declare the int
variable a in program.s. Each probe keeps fixtures: the blocks of the event
or of program.s, back to back with their size words.
"""
from tools.tft.probing.probe_runner import Probe
from tools.tft.probing.statement_probes import (beside_a_text_and_numbers, event_lines,
                                            ours_in_event, ours_in_program, program_lines,
                                            theirs_in_event, theirs_in_program)

FIXTURES = "undocumented-commands"


def _zeros(name: str, count: int) -> str:
    """Returns the line of the command `name` given `count` zeros."""
    return "%s %s" % (name, ",".join(["0"] * count))


def _probes(dropped: frozenset = frozenset()) -> list:
    """Returns the probes, each without its lines of the commands
    `dropped`."""
    def kept(lines: list) -> list:
        return [line for line in lines if line.split(" ", 1)[0] not in dropped]
    return [
        # Each command, with the number of arguments it takes, each a zero.
        Probe("undocumented-commands-each", "T", beside_a_text_and_numbers(kept([
            "getpassw", "lcd_refx", "lhmi_cle", "showqq", "getv 0", "init 0", "setbaudz 0",
            _zeros("whmi_cle", 2), _zeros("fstr", 3), _zeros("nstr", 3), _zeros("rfpt", 3),
            _zeros("strsize", 3), _zeros("wfpt", 3), _zeros("timerset", 4), _zeros("zstr", 5),
            _zeros("comok", 7), _zeros("draw3d", 7), _zeros("qrcode", 8), _zeros("draw_h", 13),
            _zeros("setbrush", 15), "lcd_dev 00 00 00 00"])),
            ours_in_event, theirs_in_event, FIXTURES),
        # Where a command takes a number: an int variable of program.s, a system
        # variable, a number's val, a long number, hexadecimal numbers, a
        # colour's name, a negative number, operands joined by the arithmetic
        # operators, a text's bco, a reference through the screen's arrays, and
        # a space after a comma. Where it takes one operand of any kind: a text,
        # one with each escape, a txt, a val, a variable, a number, and
        # references through the screen's arrays.
        Probe("undocumented-commands-operands", "T", beside_a_text_and_numbers(kept([
            "getv sys0", "getv n0.val", "getv \"abc\"", "getv t0.txt", "init a",
            "setbaudz 1000", "whmi_cle 0x01,0xFFFFFFFF", "fstr \"abc\",sys0+1,n0.val",
            "fstr t0.txt,RED,0", "nstr \"a\",1,2", "nstr t0.txt,0x01,1000",
            "rfpt n0.val*2,n1.val-1,-1", "strsize \"abc\",t0.txt,sys0",
            "strsize n0.val,\"a\",t0.txt", "wfpt sys0, 1, 2", "timerset n0.val*2,RED,0x01,-1",
            "zstr 0,0,0,0,\"abc\"", "zstr sys0+1,n0.val,0,0,t0.txt",
            "draw3d 1,2,3,4,5,6,dim", "qrcode 0,0,0,0,0,0,0,\"abc\"",
            "qrcode 1+1,0,0,0,0,0,0,t0.txt", "getv b[1].txt", "fstr b[1].txt,b[2].val,0",
            r'getv "a\"b\\c\r"', "init t0.bco", "nstr p[0].b[1].txt,0,0"])),
            ours_in_event, theirs_in_event, FIXTURES),
        # comok's seven arguments, of each kind, and a text with a space, kept
        # as written; and lcd_dev's bytes, 1, 2, and 8 of them, in either case,
        # and as many as a line holds.
        Probe("undocumented-commands-kept-as-written", "T", beside_a_text_and_numbers(kept([
            "comok \"a\",t0.txt,sys0+1,n0.val,0x01,RED,1000", "comok 0,0,0,0,0,0,\"a b\"",
            "lcd_dev 01", "lcd_dev ff ff", "lcd_dev 0A 0b", "lcd_dev 00 01 02 03 04 05 06 07",
            "lcd_dev " + " ".join(["%02x" % (number % 256) for number in range(253)])])),
            ours_in_event, theirs_in_event, FIXTURES),
        # lcd_dev's argument of other characters than hexadecimal bytes, kept
        # as written, and comok's arguments with spaces outside its texts,
        # which nxwright's build drops before the Nextion Editor or the
        # compile sees the line.
        Probe("undocumented-commands-kept-as-written-of-other-forms", "T",
              beside_a_text_and_numbers(kept(["lcd_dev sys0", "lcd_dev 0x01", "lcd_dev 001",
                                              'comok 0, 0 ,0,0,0,0,"a b"'])),
              ours_in_event, theirs_in_event, FIXTURES),
        # In strict Nextion syntax, so that each line reaches the Nextion
        # Editor as written: lcd_dev's argument of a text, and a space inside
        # one of comok's arguments, each kept as written.
        Probe("undocumented-commands-kept-as-written-in-strict-syntax", "T", event_lines([
            'lcd_dev "x"', "comok 0 1,0,0,0,0,0,0"]), ours_in_event, theirs_in_event, FIXTURES),
        # i: its first two arguments of one kind, two numbers, each of each
        # kind, or two texts, a text or a txt; one reached through the
        # screen's arrays beside either kind; and its last two numbers, joined
        # by the arithmetic operators.
        Probe("undocumented-commands-i", "T", beside_a_text_and_numbers(kept([
            "i 0,0,0,0", "i 1,2,3,4", "i sys0,a,1,2", "i n0.val,n1.val,0,0", "i RED,0x01,0,0",
            "i t0.txt,t0.txt,1,2", "i \"a\",\"b\",0,0", "i t0.txt,\"a\",0,0",
            "i b[1].txt,0,0,0", "i b[1].val,\"a\",0,0", "i 0,0,sys0+1,n0.val*2",
            "i 0,0,-1,RED"])),
            ours_in_event, theirs_in_event, FIXTURES),
        Probe("undocumented-commands-i-in-program", "T", program_lines(kept([
            "i 0,0,0,0", "i sys0,a,1,2", "i \"a\",\"b\",0,0"]), ["int a=1"]),
            ours_in_program, theirs_in_program),
        # The commands in program.s, before its page 0, without a component's
        # attribute but through `p[i].b[j]`.
        Probe("undocumented-commands-in-program", "T", program_lines(kept([
            _zeros("comok", 7), "lcd_dev 01 02", "getv sys0", "fstr \"a\",0,0", "getpassw",
            "timerset sys0+1,a,0,0", "strsize \"a\",sys0,a", "getv p[0].b[2].val"]),
            ["int a=1"]),
            ours_in_program, theirs_in_program, FIXTURES),
    ]


PROBES = _probes()


def probes_without(commands) -> list:
    """Returns the probes, each without its lines of the commands
    `commands`, for a series that lacks them, as P lacks fstr. Each keeps
    its name."""
    return _probes(frozenset(commands))
