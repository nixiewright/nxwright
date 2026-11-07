"""The probes of a component's attribute reached through the screen's arrays,
`b[i].name`, `p[i].b[j].name`, and `page1.b[i].name` (statements.INDIRECT): in
assignments, with each kind of index, across pages, in the conditions of if,
while, and for, in program.s, as an operand of each family of commands, and
`b[i]` as the component of vis, tsw, click, and ref. Run them with
`tools.tft.probe run indirect_probes`.

The probes of an event give page0's Touch Release event their lines, beside
the text t0, object 1, and the numbers n0 and n1, objects 2 and 3, with
`int a=1` declared. Each compares the blocks of its run of lines, and keeps
them as its fixture (statement_probes.py gives both). The probes of
`page1.b[i]` add page1, with the number n0 and the text t1, objects 1 and 2,
for the reference to reach into.
"""
from tools.tft.probing.component_probes import PagesChange, on_pages, with_components
from tools.tft.probing.number_probes import number_component
from tools.tft.probing.probe_runner import Probe
from tools.tft.probing.statement_probes import (beside_a_text_and_numbers, ours_in_event,
                                            ours_in_program, program_lines, theirs_in_event,
                                            theirs_in_program)
from tools.tft.probing.text_probes import text_component

FIXTURES = "indirect"
# page1, which the references by a page's name reach into.
_PAGE1 = with_components(number_component("n0", y=60), text_component("t1", y=110),
                         page="page1")


def _event_probe(name: str, lines: list) -> Probe:
    return Probe("indirect-" + name, "T", beside_a_text_and_numbers(lines), ours_in_event,
                 theirs_in_event, FIXTURES)


def _beside_page1(change) -> PagesChange:
    """Returns a change that makes `change`, on page0 or in program.s, then
    adds page1 (_PAGE1)."""
    return on_pages(change, _PAGE1)


def _braced(head: str, *body: str) -> list:
    return [head, "{", *body, "}"]


PROBES = [
    # Set to values of each kind, and given as one, with each assigning
    # operator; attributes the page has not, such as foo, and the page's own,
    # b[0].
    _event_probe("assignments", [
        'b[1].txt="Yo"', "b[2].val=n1.val", "sys0=b[2].val", "t0.txt=b[1].txt",
        "n0.val=b[1].txt_maxl", "n0.val=b[3].type", 'b[1].txt=b[1].txt+"a"',
        'b[1].txt+="a"+t0.txt', "b[2].val+=n0.val", "b[1].txt-=1", "t0.txt-=b[2].val",
        "b[2].val++", "b[3].val--", "b[1].bco=RED", "b[0].bco=5", 't0.txt="a"+b[1].txt',
        "t0.txt+=b[1].txt", "sys0+=b[2].val", "sys0=b[2].val+b[3].val", "n0.val=n1.val*b[2].val",
        "b[2].val=n1.val*2-1", "b[1].txt=t0.txt+n0.val", 'b[2].val="a"', "b[1].foo=5"]),
    # The first index as a value: a variable, an int variable, a val, an
    # expression, a negative number, a long one, a colour, a hexadecimal
    # number, and spaces, which the Nextion Editor drops.
    _event_probe("indexes", [
        'b[sys0].txt="a"', 'b[a].txt="a"', 'b[n0.val].txt="a"', 'b[sys0*2-1].txt="a"',
        'b[-1].txt="a"', 'b[1000].txt="a"', 'b[RED].txt="a"', 'b[0x01].txt="a"',
        'b[ 1 ].txt="a"']),
    # Across pages: the page's index as a value, the component's as written.
    _event_probe("across-pages", [
        'p[0].b[1].txt="Hi"', 'p[sys0].b[sys1].txt="a"', 'p[n0.val].b[n1.val].txt="a"',
        "sys0=p[0].b[2].val", "t0.txt=p[0].b[1].txt", "p[0].b[2].val=b[3].val",
        'p[0].b[ sys0 ].txt="a"']),
    # Beside an operand of either kind, and as a for's start and step.
    _event_probe("conditions",
                 _braced("if(b[2].val==1)", "sys0=1") + _braced('if(b[1].txt=="a")', "sys0=2")
                 + _braced("if(b[1].txt==1)", "sys0=3") + _braced("if(n0.val==b[1].txt)", "sys0=4")
                 + _braced("if(t0.txt==b[1].txt&&n0.val==b[2].val)", "sys0=5")
                 + _braced("if(p[0].b[2].val!=sys0)", "sys0=6")
                 + _braced("while(b[2].val<5)", "b[2].val++")
                 + _braced("for(b[2].val=0;b[2].val<3;b[2].val++)", "sys0++")
                 + _braced("for(sys0=b[2].val;sys0<p[0].b[3].val;sys0++)", "n0.val++")),
    # As an operand of a command of each family, an expression's among them,
    # where the command takes a number or a text, and in `page`'s value.
    _event_probe("in-commands", [
        "cls b[2].val", "cls b[2].val+1", "fill b[1].x,0,10,10,RED", "cov b[2].val,t0.txt,0",
        "cov t0.txt,b[2].val,0", "strlen b[1].txt,b[2].val", "covx b[2].val,b[1].txt,0,0",
        "xstr 0,0,50,20,0,RED,WHITE,0,0,1,b[1].txt", "print b[1].txt", "prints b[1].txt,0",
        "get b[2].val", "crcputs b[1].txt,0", "pa_q b[1].txt,b[2].val",
        "randset b[2].val,b[3].val", "cls p[0].b[2].val", "add b[2].val,0,b[3].val",
        "addt b[2].val,0,10", "cle b[2].val,0", "ucopy b[2].val,0,4,0", "udelete b[2].val",
        "page b[sys0].val+1", "page 1+b[n0.val].val", "page p[0].b[2].val"]),
    # K's own commands, of the EEPROM and the GPIO pins, and `b[i]` as
    # cfgpio's component.
    Probe("indirect-in-eeprom-commands", "K", beside_a_text_and_numbers([
        "wepo b[2].val,0", "wepo b[1].txt,0", "repo b[2].val,0", "wept b[2].val,10",
        "rept b[2].val,10", "cfgpio b[2].val,b[3].val,n0", "cfgpio 2,1,b[sys0]",
        "cfgpio 2,1,b[n0.val+1]"]), ours_in_event, theirs_in_event, FIXTURES),
    # `b[i]` as a command's component, its index of each kind.
    _event_probe("as-components", [
        "vis b[1],0", "vis b[sys0],0", "vis b[n0.val],1", "vis b[sys0+1],0", "tsw b[1],0",
        "click b[1],1", "ref b[a]", "vis b[1],b[2].val"]),
    # In program.s, `p[i].b[j]` alone, set, given, in commands, `page` among
    # them, and in a condition.
    Probe("indirect-in-program-s", "T", program_lines(
        ['p[0].b[1].txt="a"', "p[0].b[2].val=5", "sys0=p[0].b[1].val", "cls p[0].b[2].val",
         "page p[0].b[2].val"]
        + _braced("if(p[0].b[2].val==1)", "sys0=1")), ours_in_program, theirs_in_program,
        FIXTURES),
    # A component of another page by the page's name, written whole as its
    # text, its index included, without spaces: set and given, with each kind
    # of index, stepped, in each control statement, and as a command's
    # operand.
    Probe("indirect-another-page", "T", _beside_page1(beside_a_text_and_numbers(
        ["page1.b[1].val=5", "sys0=page1.b[1].val", "page1.b[sys0].val=5", "page1.b[a].val=5",
         "page1.b[sys0+1].val=5", "page1.b[n0.val].val=5", "page1.b[1000].val=5",
         'page1.b[2].txt="a"', "t0.txt=page1.b[2].txt", "page1.b[ 1 ].val=5",
         "page1.b[1].val+=n0.val", "page1.b[1].val++", "t0.txt+=page1.b[2].txt",
         "cls page1.b[1].val", "cov page1.b[1].val,t0.txt,0", "prints page1.b[2].txt,0",
         "get page1.b[1].val", "crcputs page1.b[2].txt,0", "ucopy page1.b[1].val,0,4,0",
         "randset page1.b[1].val,10", "page page1.b[1].val"]
        + _braced("if(page1.b[1].val==1)", "sys0=1")
        + _braced("while(page1.b[1].val<3)", "page1.b[1].val++")
        + _braced("for(page1.b[1].val=0;page1.b[1].val<3;page1.b[1].val++)", "sys0++"))),
        ours_in_event, theirs_in_event, FIXTURES),
    # In program.s, which takes it as it takes `p[i].b[j]`: set, given, and in
    # a condition.
    Probe("indirect-another-page-in-program-s", "T", _beside_page1(program_lines(
        ["page1.b[1].val=5", "sys0=page1.b[sys0].val"]
        + _braced("if(page1.b[1].val==1)", "sys0=1"))), ours_in_program, theirs_in_program,
        FIXTURES),
]
