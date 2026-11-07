"""The probes of code that names a global component of another page by that
page's name, as `page1.va0.val` (statements.py): in page0's Touch Release
event, set, read, stepped, in the conditions of if, while, and for, as a
for's start and step, and as an operand of each family of commands;
in program.s; and in shift-jis, a text in an assignment to one, which the
Nextion Editor reads in pairs as any assignment's. Run them with
`tools.tft.probe run other_page_probes`.

page0 holds the text t0. page1 holds the global variable va0, the global
number n0, the local text t1, and the global variable of a text va1. Each
probe compares the blocks of its run of lines, and keeps them as its
fixture (statement_probes.py gives both).
"""
from tools.tft.probing.component_probes import PagesChange, on_pages, with_components
from tools.tft.probing.encoding_probes import in_encoding
from tools.tft.probing.number_probes import number_component
from tools.tft.probing.probe_runner import Probe
from tools.tft.probing.statement_probes import (ProgramChange, ours_in_event, ours_in_program,
                                            theirs_in_event, theirs_in_program,
                                            touch_release_code)
from tools.tft.probing.text_probes import text_component
from tools.tft.probing.variable_probes import text_variable_component, variable_component

FIXTURES = "other-page"
_GLOBAL = "vscope = 1\n"


def _on_two_pages(page0: ProgramChange) -> PagesChange:
    """Returns a change that makes `page0`, which gives page0 the text t0 and
    its code, then puts page1's components on page1. A unit test reads what
    it adds, to make the same pages in memory (component_probes.PagesChange)."""
    return on_pages(page0, with_components(
        variable_component() + _GLOBAL, number_component("n0", y=60, vscope=1),
        text_component("t1", y=110), text_variable_component("va1") + _GLOBAL, page="page1"))


def _in_an_event(lines: list) -> PagesChange:
    """Returns a change that gives page0's Touch Release event `lines`,
    beside page0's text and page1's components (_on_two_pages)."""
    return _on_two_pages(ProgramChange(components=(text_component(),),
                                       code=touch_release_code(lines)))


def _in_program(lines: list) -> PagesChange:
    """Returns a change that adds `lines` to program.s, beside page0's text
    and page1's components (_on_two_pages)."""
    return _on_two_pages(ProgramChange(program=tuple(lines), components=(text_component(),)))


PROBES = [
    Probe("other-page-in-an-event", "T", _in_an_event([
        "page1.va0.val=5", "page1.va0.val=dp", "sys0=page1.n0.val", 'page1.va1.txt="a"',
        't0.txt=page1.va1.txt+"b"', "page1.va1.txt+=t0.txt", "page1.n0.val++",
        "page1.n0.val*=2", 'page0.t0.txt="a"', 'if(page1.va1.txt=="a")', "{", "sys0=1", "}",
        "if(page1.n0.val==1)", "{", "sys0=2", "}",
        "while(page1.n0.val<5)", "{", "page1.n0.val++", "}",
        "for(page1.n0.val=0;page1.n0.val<3;page1.n0.val++)", "{", "sys0++", "}"]),
        ours_in_event, theirs_in_event, FIXTURES),
    Probe("other-page-in-commands", "T", _in_an_event([
        "cls page1.n0.val", "cls page1.n0.val+1", "get page1.n0.val", "prints page1.va1.txt,0",
        "cov page1.n0.val,t0.txt,0", "xstr 0,0,50,20,0,RED,WHITE,0,0,1,page1.va1.txt",
        "strlen page1.va1.txt,sys0", "pa_q page1.va1.txt,page1.n0.val",
        "page page1.n0.val+1", "fstr page1.va1.txt,page1.n0.val,0"]),
        ours_in_event, theirs_in_event, FIXTURES),
    Probe("other-page-in-program-s", "T",
          _in_program(["page1.va0.val=5", "sys0=page1.n0.val", 'page1.va1.txt="a"',
                       "cls page1.n0.val"]),
          ours_in_program, theirs_in_program, FIXTURES),
    # A text that ends in 表, whose last byte is 0x5C, read in pairs alone in
    # an assignment to another page's global component, as in any assignment.
    Probe("other-page-in-shift-jis", "T", in_encoding("shift-jis", _in_an_event(
        ['page1.va1.txt="日表"+t0.txt', 'page1.va1.txt+="表"'])),
        ours_in_event, theirs_in_event, FIXTURES),
]
