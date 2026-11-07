"""The variable component's probes (component_types/variable.py): variables
of a number on the T base folder's page, with other vals, two of them, one
before a text, one beside a text, a number, and a button, one on a second
page, and five on a page, then variables of a text, with other texts and
txt_maxl, and a variable's val and txt in code. Run them with `tools.tft.probe
run variable_probes`.

Each probe of a variable compares the whole file, part by part, and keeps
the user code alone as its fixtures (component_probes.py gives both). Each
probe of code compares the blocks of page0's Touch Release event alone,
which it keeps as its fixture (statement_probes.py gives both).
"""
from functools import partial

from tools.tft.probing.attribute_probes import with_attributes
from tools.tft.probing.button_probes import button_component
from tools.tft.probing.component_probes import type_probe, with_components
from tools.tft.probing.number_probes import number_component
from tools.tft.probing.probe_runner import Probe
from tools.tft.probing.statement_probes import ours_in_event, theirs_in_event
from tools.tft.probing.text_probes import text_component


def variable_component(name: str = "va0", val: int = 0) -> str:
    """Returns a variable component in a page file's form."""
    return '\n[[component]]\nname = "%s"\ntype = "variable"\nval = %d\n' % (name, val)


def text_variable_component(name: str = "va0", txt: str = "newtxt", txt_maxl: int = 10) -> str:
    """Returns a variable of a text, its sta 1, in a page file's form."""
    return ('\n[[component]]\nname = "%s"\ntype = "variable"\nsta = 1\ntxt = "%s"\n'
            'txt_maxl = %d\n' % (name, txt, txt_maxl))


_probe = partial(type_probe, "variable")


def _code_probe(name: str, lines: list) -> Probe:
    """Returns a probe of `lines` in page0's Touch Release event, beside va0
    and va1."""
    change = with_attributes(lines, [variable_component(), variable_component("va1")])
    return Probe("variable-" + name, "T", change, ours_in_event, theirs_in_event, "variable")


# The probes keeping fixtures are the fewest that show each part: two
# variables on a page; a variable among a text, a number, and a button, the
# types already matched; and a variable on a second page, numbered on from
# the first's.
PROBES = [
    _probe("one", with_components(variable_component())),
    _probe("two", with_components(variable_component(), variable_component("va1")),
           fixtures=True),
    _probe("of-123", with_components(variable_component(val=123))),
    _probe("of-minus-5", with_components(variable_component(val=-5))),
    _probe("of-the-least", with_components(variable_component(val=-2147483648))),
    _probe("of-the-most", with_components(variable_component(val=2147483647))),
    _probe("among-a-text-a-number-and-a-button",
           with_components(text_component(), variable_component(), number_component(y=60),
                           button_component(y=110)), fixtures=True),
    _probe("before-a-text", with_components(variable_component(), text_component())),
    _probe("on-second-page", with_components(variable_component(), page="page1"),
           fixtures=True),
    _probe("five-on-a-page", with_components(*[variable_component("va%d" % number)
                                               for number in range(5)])),
    _probe("named-with-14", with_components(variable_component("Vari_name_of14"))),
    # A variable's val set, stepped, read, and compared in if, else if,
    # while, and for, and as the operand of the serial commands.
    _code_probe("val-in-code", [
        "va0.val=5", "sys0=va0.val", "va1.val=va0.val+sys0", "va0.val++", "va1.val--",
        "va0.val+=1000", "va1.val-=va0.val", "va0.val=-2147483648", "get va0.val",
        "print va1.val"]),
    # A variable as the component of the screen's commands, by its name.
    _code_probe("in-screen-commands", ["vis va0,0", "tsw va0,0", "click va1,1", "ref va1"]),
    # Variables of a text: at its defaults, its txt and txt_maxl at their
    # bounds and between, and beside a variable of a number.
    _probe("of-a-text", with_components(text_variable_component())),
    _probe("of-an-empty-text", with_components(text_variable_component(txt=""))),
    _probe("of-a-text-of-txt-maxl-1",
           with_components(text_variable_component(txt="A", txt_maxl=1))),
    _probe("of-a-text-of-txt-maxl-200",
           with_components(text_variable_component(txt="Go12", txt_maxl=200))),
    _probe("of-a-text-beside-one-of-a-number",
           with_components(text_variable_component(), variable_component("va1"),
                           text_variable_component("va2", txt="Hi")), fixtures=True),
    # The attributes the other sta writes: a variable of a number given a txt
    # and a txt_maxl, and one of a text given a val.
    _probe("of-a-number-with-a-txt",
           with_components(variable_component(val=7) + 'txt = "abc"\ntxt_maxl = 20\n')),
    _probe("of-a-text-with-a-val",
           with_components(text_variable_component() + "val = 123\n")),
    # A variable of a text's txt set, and as the operand of the serial and
    # text commands, beside a variable of a number.
    Probe("variable-txt-in-code", "T", with_attributes(
        ['va0.txt="Yo"', 'va0.txt=""', "get va0.txt", "print va0.txt", "prints va0.txt,2",
         "strlen va0.txt,sys0", "btlen va0.txt,sys1", "cov va0.txt,sys0,0",
         "substr va0.txt,va0.txt,0,2", 'spstr va0.txt,va0.txt,"a",0'],
        [text_variable_component(), variable_component("va1")]),
          ours_in_event, theirs_in_event, "variable"),
    _code_probe("val-in-conditions", [
        "if(va0.val==1)", "{", "va1.val=2", "}else if(sys0<va1.val&&va0.val!=3)", "{",
        "va1.val=3", "}",
        "while(va0.val<3)", "{", "va0.val++", "}",
        "for(va1.val=0;va1.val<va0.val;va1.val++)", "{", "sys0++", "}"]),
]
