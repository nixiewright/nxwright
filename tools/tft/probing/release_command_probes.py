"""The probes of every command, system variable, and colour, one for each
series, which the release sample takes (release_sample.py): a program.s of
every command, system variable, and colour the series has. The commands
that nxwright's other probes have checked only in an event are in page0's
Touch Release event instead, beside a text and two numbers that some of
them name. Each compares the whole file.

A pass runs them in the release sample. Run them alone with
`tools.tft.probe run release_command_probes`.
"""
from tools.tft.probing.component_probes import editor_file, whole_file
from tools.tft.probing.number_probes import number_component
from tools.tft.probing.probe_runner import Probe
from tools.tft.probing.statement_probes import ProgramChange, touch_release_code
from tools.tft.probing.text_probes import text_component
from nxwright.tft.statements import COLOURS, SYSTEM_VARIABLES, series_commands

# A line of each command, in program.s, as nxwright's probes have checked it
# there, on at least one series. A series takes those of the commands it
# has (statements.series_commands).
_PROGRAM_LINES = {
    "add": "add 1,0,10", "addt": "addt 1,0,100", "beep": "beep 100", "beepset": "beepset 0,0",
    "btlen": 'btlen "abc",sys1', "cfgpio": "cfgpio 0,0,0", "cir": "cir 160,240,100,sys0",
    "cirs": "cirs 160,240,50,BROWN", "cle": "cle 1,255", "cls": "cls BLUE", "code_c": "code_c",
    "com_star": "com_star", "com_stop": "com_stop", "comok": "comok 0,0,0,0,0,0,0",
    "cov": "cov 5,sys1,0", "covx": "covx sys0,sys1,0,0", "crcputh": "crcputh 31 32",
    "crcputs": "crcputs dim,1", "crcputu": "crcputu 0,3", "crcrest": "crcrest 1,dim",
    "cuts": "cuts 0,0,0,0,0,0,0", "doevents": "doevents", "draw": "draw 1,1,318,478,dim",
    "fill": "fill 0,0,320,480,WHITE", "findfile": 'findfile "sd0/x.txt",sys0',
    "fstr": 'fstr "a",0,0', "get": "get sys0", "getpassw": "getpassw", "gets": "gets 0,0",
    "getv": "getv sys0", "i": "i 0,0,0,0", "lcd_dev": "lcd_dev 01 02",
    "line": "line 0,0,319,479,RED", "move": "move 1,0,0,10,10,0,10", "newdir": 'newdir "sd0/x/"',
    "pa_q": 'pa_q "ni",sys0', "page": "page 0", "pic": "pic 0,0,0",
    "piccolor": "piccolor 0,0,0,sys0", "picq": "picq 0,0,8,4,1", "play": "play 0,0,0",
    "print": 'print "hi"', "printh": "printh ff", "prints": 'prints "hi",1',
    "randset": "randset 0,100", "ref": "ref 0", "ref_star": "ref_star", "ref_stop": "ref_stop",
    "repo": "repo sys0,0", "rept": "rept 0,10", "rest": "rest", "sendme": "sendme",
    "setlayer": "setlayer 1,2", "sets": "sets 1,2", "spstr": 'spstr "a,b",sys0,",",1',
    "strlen": 'strlen "abc",sys0', "strsize": 'strsize "a",sys0,a',
    "substr": 'substr "hello",sys2,1,2', "timerset": "timerset sys0+1,a,0,0",
    "touch_j": "touch_j", "tsw": "tsw 255,1", "ucopy": "ucopy sys0,0,2,0", "udelete": "udelete 1",
    "vis": "vis 255,0", "wepo": "wepo 5,0", "wept": "wept sys0,sys1",
    "xnum": "xnum 0,0,0,0,0,0,0,0,0,0", "xpic": "xpic 0,0,4,4,2,1,1",
    "xstr": 'xstr 0,0,100,30,0,RED,WHITE,1,1,1,"in program.s"',
}
# A line of each command that nxwright's probes have checked only in an event,
# beside the text t0 and the numbers n0 and n1.
_EVENT_LINES = {
    "cfguart": "cfguart sys0,1,2,3", "click": "click t0,1", "deldir": "deldir t0.txt",
    "delfile": "delfile 5", "draw3d": "draw3d 0,0,0,0,0,0,0",
    "draw_h": "draw_h 0,0,0,0,0,0,0,0,0,0,0,0,0", "finddir": 'finddir "sd0/a/",5',
    "init": "init 0", "lcd_refx": "lcd_refx", "lhmi_cle": "lhmi_cle", "meup": "meup n0.val,1",
    "newfile": 'newfile "sd0/a.txt",10', "nstr": "nstr 0,0,0", "pa_txt": 'pa_txt "a",sys0,0,1',
    "qrcode": "qrcode 0,0,0,0,0,0,0,0", "rdfile": 'rdfile "sd0/a.txt",0,10,0',
    "redir": 'redir t0.txt,"sd0/b/"', "refile": "refile t0.txt,t0.txt", "rfpt": "rfpt 0,0,0",
    "setbaudz": "setbaudz 0", "setbrush": "setbrush 0,0,0,0,0,0,0,0,0,0,0,0,0,0,0",
    "showqq": "showqq", "twfile": "twfile t0.txt,sys0", "wfpt": "wfpt 0,0,0",
    "whmi_cle": "whmi_cle 0,0", "zstr": "zstr 0,0,0,0,0",
}


def _commands_probe(series: str) -> Probe:
    """Returns the probe of every command, system variable, and colour that
    `series` has: each command in a line of its own, then each system
    variable and colour read into sys0. The int a is declared for the lines
    that name it."""
    commands = series_commands(series)
    program = ([line for name, line in _PROGRAM_LINES.items() if name in commands]
               + ["sys0=%s" % name for name in (*SYSTEM_VARIABLES[series], *COLOURS[series])])
    event = [line for name, line in _EVENT_LINES.items() if name in commands]
    change = ProgramChange(program=tuple(program), declarations=("int a=1",),
                           components=(text_component("t0"), number_component("n0", y=60),
                                       number_component("n1", y=110)),
                           code=touch_release_code(event))
    return Probe("release-sample-%s-commands" % series.lower(), series, change, whole_file,
                 editor_file)


PROBES = [_commands_probe(series) for series in ("T", "K", "P", "E", "F")]
