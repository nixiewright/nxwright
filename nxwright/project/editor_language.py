"""The Nextion Editor's language, as its compile takes it: its commands
(EDITOR_COMMANDS), its system variables (EDITOR_SYSTEM_VARIABLES), its
colours (EDITOR_COLOURS), the names it refuses for a page or a component
(NAMES_THE_EDITOR_REFUSES), the int variables its new project declares
(EDITOR_PROGRAM_VARIABLES), and the commands and system variables each
screen series lacks (SERIES_LACKED_COMMANDS, SERIES_LACKED_VARIABLES). The
compiler, the test machine, and the language server read them; the page
checks of editor_limits.py read the names it refuses."""

# The Editor's system variables: the names its code reads and sets the
# screen's state by. sys0 to sys2 are not among them: program.s declares them
# (EDITOR_PROGRAM_VARIABLES). The Editor refuses each of these as a name
# (NAMES_THE_EDITOR_REFUSES), which is how the list was checked: every name
# nxwright knew as a system variable was tried, and the Editor refused all
# but eqlb, which it does not know. Seven more, which the community's "Full
# Instruction Set" (UNUF/nxt-doc) lists, were refused alike: scache, the
# serial line's send buffer switch, and bcpu, tpdir, runmod, portbusy, tprc,
# and aph.
#
# Three groups of them are lacked together by some series
# (SERIES_LACKED_VARIABLES): the GPIO pins', the real-time clock's, and the
# sound's.
GPIO_VARIABLES = frozenset(["pio%d" % pin for pin in range(8)]
                           + ["pwm%d" % pin for pin in range(4, 8)] + ["pwmf"])
_CLOCK_VARIABLES = frozenset("rtc%d" % part for part in range(7))
_SOUND_VARIABLES = frozenset(["audio0", "audio1", "volume", "eql", "eqm", "eqh"]
                             + ["eq%d" % band for band in range(10)])
EDITOR_SYSTEM_VARIABLES = frozenset(
    ["dp", "dim", "dims", "baud", "bauds", "bkcmd", "rand", "thup", "thsp", "ussp", "sendxy",
     "delay", "sleep", "wup", "usup", "crcval", "lowpower", "recmod", "addr", "usize", "appid",
     "spax", "spay", "thc", "thdra", "sya0", "sya1", "scache", "bcpu", "tpdir", "runmod",
     "portbusy", "tprc", "aph"]
    + ["tch%d" % n for n in range(4)]) | GPIO_VARIABLES | _CLOCK_VARIABLES | _SOUND_VARIABLES
# The Editor's commands: the words a line of its code may start with. They
# are the 65 of the vendor's instruction set (its sections 3 and 4, but
# `if`, `while`, and `for`), and those it does not document. The community's
# "Full Instruction Set" (UNUF/nxt-doc) lists the rest, such as `beep`, and
# `lcd_dev`, a fix of the touch's offsets that a user's program.s held. Each
# compiled in the Editor 3.1.73, but the eight of NO_NUMERIC_FORM, which no
# number of numeric arguments made compile. The Editor knows those, and
# judges their forms itself; written alone, it refused each.
NO_NUMERIC_FORM = frozenset(["i", "cfguart", "cuts", "gets", "meup", "xnum", "beepset",
                             "piccolor"])
EDITOR_COMMANDS = frozenset([
    "page", "ref", "click", "ref_stop", "ref_star", "get", "sendme", "covx", "cov", "touch_j",
    "substr", "vis", "tsw", "com_stop", "com_star", "randset", "code_c", "prints", "print",
    "printh", "add", "addt", "cle", "rest", "doevents", "strlen", "btlen", "wepo", "repo",
    "wept", "rept", "cfgpio", "ucopy", "move", "play", "twfile", "delfile", "refile",
    "findfile", "rdfile", "setlayer", "newdir", "deldir", "redir", "finddir", "udelete",
    "crcrest", "crcputs", "crcputh", "crcputu", "spstr", "newfile", "call", "return", "goto",
    "cls", "pic", "picq", "xpic", "xstr", "fill", "line", "draw", "cir", "cirs",
    # Undocumented.
    "beep", "lcd_dev", "getpassw", "lcd_refx", "lhmi_cle", "showqq", "getv", "init",
    "setbaudz", "pa_q", "whmi_cle", "fstr", "nstr", "rfpt", "strsize", "wfpt", "pa_txt",
    "timerset", "zstr", "comok", "draw3d", "qrcode", "draw_h", "setbrush",
    "sets"]) | NO_NUMERIC_FORM
# A word that is no command, which the Editor's compile refuses with other
# words than "Invalid command": it reads movelayer as a name ("Invalid
# Variables"), as it does any first word holding a capital letter.
REFUSED_AS_A_NAME = frozenset({"movelayer"})
# A command the Editor's compile refuses as no command ("Invalid command")
# when it is written alone, without the arguments it takes, where it
# refuses any other for its number of arguments.
NO_COMMAND_WHEN_ALONE = frozenset({"add"})
# The commands and system variables the Editor's compile refuses on a
# screen of each series, by the series' letter (screen_models.py,
# ScreenModel.series), saying "Do not support such instruction for this
# series device", or "such variable". It lists every such line at once,
# wherever the code is. A word not listed compiled on that series, or was
# not tried. One model of each series was probed, and two of the
# Enhanced, which agreed, so the Editor is taken to decide by series.
# (Worked out from the Editor 3.1.73.)
#
# The commands only the Intelligent and the Edge series took: the SD
# card's, and others.
_INTELLIGENT_AND_EDGE_COMMANDS = frozenset(
    ["findfile", "finddir", "newfile", "delfile", "newdir", "deldir", "refile", "redir",
     "play", "twfile", "rdfile", "move", "setlayer"])
#
# Of the undocumented commands, the Basic and Enhanced series refused sets,
# cuts, gets, and xnum for their series; the Basic, Enhanced, and Discovery
# refused cfguart, meup, and beepset; all but the Discovery refused
# piccolor; and the Edge and Intelligent refused fstr.
_NOT_ON_THE_BASIC_OR_ENHANCED = frozenset(["sets", "cuts", "gets", "xnum", "cfguart", "meup",
                                           "beepset", "piccolor"])
SERIES_LACKED_COMMANDS = {
    "T": _INTELLIGENT_AND_EDGE_COMMANDS | _NOT_ON_THE_BASIC_OR_ENHANCED
    | {"beep", "rept", "wepo", "repo", "wept", "cfgpio"},
    "K": _INTELLIGENT_AND_EDGE_COMMANDS | _NOT_ON_THE_BASIC_OR_ENHANCED | {"beep"},
    "F": _INTELLIGENT_AND_EDGE_COMMANDS | {"rept", "wept", "cfguart", "meup", "beepset"},
    "P": frozenset({"fstr", "piccolor"}),
    "E": frozenset({"fstr", "piccolor"}),
}
SERIES_LACKED_VARIABLES = {
    "T": GPIO_VARIABLES | _CLOCK_VARIABLES | _SOUND_VARIABLES
    | {"lowpower", "scache", "tprc", "aph"},
    "K": _SOUND_VARIABLES | {"lowpower", "scache", "tprc", "aph"},
    "F": _CLOCK_VARIABLES | _SOUND_VARIABLES | {"scache", "tprc", "aph"},
    "P": frozenset({"lowpower"}),
    "E": frozenset({"lowpower"}),
}
# The colour names the Editor's code may use, as RGB565 numbers: `cls BLACK`.
EDITOR_COLOURS = {"BLACK": 0, "BLUE": 31, "BROWN": 48192, "GREEN": 2016, "YELLOW": 65504,
                  "RED": 63488, "GRAY": 33840, "WHITE": 65535}
# Names the Editor refuses for a page or a component: its system variables
# and its colours. Opening the project, it says "Illegal name" for each, and
# renames it. The names are matched exactly, case included: `dim` is
# refused, but `DIM` and `dim1` are not. Names nxwright makes up skip them,
# and the build refuses them. (Worked out from the Editor 3.1.73, for an
# Intelligent screen and a basic one alike.)
NAMES_THE_EDITOR_REFUSES = EDITOR_SYSTEM_VARIABLES | frozenset(EDITOR_COLOURS)
# The int variables the Editor's new project declares in its program.s, and
# that declaration. The vendor's instruction set lists them among the system
# variables, but the Editor refuses code naming one that program.s does not
# declare, saying "Invalid Variables" as it compiles. (Worked out from the
# Editor 3.1.73.)
EDITOR_PROGRAM_VARIABLES = ("sys0", "sys1", "sys2")
EDITOR_PROGRAM_DECLARATION = "int sys0=0,sys1=0,sys2=0"
# The build's refusal of code naming one of them undeclared, given its name.
UNDECLARED_PROGRAM_VARIABLE = ("%%s is an int variable program.nx must declare, as the "
                               "Nextion Editor's new project does: %s"
                               % EDITOR_PROGRAM_DECLARATION)
