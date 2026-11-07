"""The button component's probes (component_types/button.py): buttons on the
T base folder's page, with other places, sizes, texts, and txt_maxl, two of
them, one beside a text and a number, one on a second page, a second font,
and code in a button's events, then a button's txt and val in code; then
buttons with other colours, centring, isbr, val, and spacing, and one in a
second font. Run them with `tools.tft.probe run button_probes`.

Each probe of a button compares the whole file, part by part, and keeps the
user code alone as its fixtures (component_probes.py gives both). Each
probe of code compares the blocks of page0's Touch Release event alone,
which it keeps as its fixture (statement_probes.py gives both).
"""
from functools import partial

from tools.tft.probing.attribute_probes import with_attributes
from tools.tft.probing.component_probes import (type_probe, with_components, with_second_font,
                                            with_the_first_in_a_second_font)
from tools.tft.probing.number_probes import number_component
from tools.tft.probing.probe_runner import Probe
from tools.tft.probing.statement_probes import ours_in_event, theirs_in_event
from tools.tft.probing.text_probes import text_component


def button_component(name: str = "b0", x: int = 10, y: int = 10, w: int = 100, h: int = 50,
                     txt: str = "newtxt", txt_maxl: int = 10, pictures: dict = None,
                     **attributes: int) -> str:
    """Returns a button component in a page file's form, in the base folder's
    font, its `pictures`, as {"pic": the name of a picture of the project},
    and its other attributes, such as bco, at their defaults unless given."""
    return ('\n[[component]]\nname = "%s"\ntype = "button"\nx = %d\ny = %d\nw = %d\nh = %d\n'
            'font = "NotoSans24"\ntxt = "%s"\ntxt_maxl = %d\n'
            % (name, x, y, w, h, txt, txt_maxl)
            + "".join('%s = "%s"\n' % item for item in (pictures or {}).items())
            + "".join("%s = %d\n" % item for item in attributes.items()))


_probe = partial(type_probe, "button")


def _ten_buttons() -> list:
    """Returns ten buttons, b0 to b9, in two columns: the last has ID 10."""
    return [button_component("b%d" % number, x=10 + 150 * (number % 2),
                             y=10 + 90 * (number // 2)) for number in range(10)]


def with_button_code(lines: list):
    """Returns a probe's change: puts b0 and b1 on page0, and gives page0's
    Touch Release event `lines`."""
    return with_attributes(lines, [button_component(), button_component("b1", y=70)])


def _code_probe(name: str, lines: list) -> Probe:
    return Probe("button-" + name, "T", with_button_code(lines), ours_in_event, theirs_in_event,
                 "button")


# A button's val in the conditions of if, else if, while, and for, on either
# side, and as a for's start and step.
VAL_IN_CONDITIONS = [
    "if(b0.val==1)", "{", "b1.val=1", "}else if(b1.val!=0&&sys0<b0.val)", "{", "b1.val=0", "}",
    "while(b0.val<1)", "{", "b0.val++", "}",
    "for(b1.val=0;b1.val<b0.val;b1.val++)", "{", "sys0++", "}"]

_EVENT_CODE = "on b0.down:\n  sys0=1\non b0.up:\n  sys1=2\n"

# The probes keeping fixtures are the fewest that show each part: two
# buttons on a page; a button beside a text and a number, the types already
# matched; code in a button's events, after the Nextion Editor's own; and a
# button on a second page, numbered on from the first's.
PROBES = [
    _probe("one", with_components(button_component())),
    _probe("two", with_components(button_component(), button_component("b1", y=70)),
           fixtures=True),
    _probe("beside-a-text-and-a-number",
           with_components(button_component(), text_component(y=70), number_component(y=110)),
           fixtures=True),
    _probe("after-a-text", with_components(text_component(), button_component(y=50))),
    _probe("empty", with_components(button_component(txt=""))),
    _probe("txt-maxl-1", with_components(button_component(txt="A", txt_maxl=1))),
    _probe("padded-then-another", with_components(button_component(txt="A", txt_maxl=1),
                                                  button_component("b1", y=70))),
    _probe("txt-maxl-200", with_components(button_component(txt="Yo", txt_maxl=200))),
    _probe("full", with_components(button_component(txt="Press", txt_maxl=5))),
    _probe("of-digits", with_components(button_component(txt="Go12"))),
    _probe("of-2-by-2", with_components(button_component(x=0, y=0, w=2, h=2))),
    _probe("at-the-edges", with_components(button_component(x=220, y=430))),
    _probe("ten-on-a-page", with_components(*_ten_buttons())),
    _probe("of-the-screen", with_components(button_component(x=0, y=0, w=320, h=480))),
    _probe("event-code", with_components(button_component(), code=_EVENT_CODE),
           fixtures=True),
    _probe("named-with-14", with_components(button_component("Butn_name_of14"),
                                            code="on Butn_name_of14.up:\n  sys0=1\n")),
    _probe("on-second-page", with_components(button_component(), page="page1"),
           fixtures=True),
    _probe("second-font", with_second_font(button_component())),
    # A button's txt and val set, stepped, and read.
    _code_probe("txt-and-val-in-code", [
        'b0.txt="Yo"', 'b1.txt=""', "b0.val=1", "sys0=b0.val", "b1.val=b0.val+sys0", "b0.val++",
        "b1.val--", "b0.val+=2", "b1.val-=b0.val", "b0.val=1000", "b1.val=-5"]),
    _code_probe("val-in-conditions", VAL_IN_CONDITIONS),
    # The same, compared as whole files.
    _probe("val-in-conditions-whole-file", with_button_code(VAL_IN_CONDITIONS)),
    # A button's txt and val as the operands of the serial and text commands.
    _code_probe("txt-and-val-in-commands", [
        "get b0.txt", "get b0.val", "print b0.txt", "print b0.val", "prints b0.txt,2",
        "prints b0.val,0", "strlen b0.txt,sys0", "btlen b0.txt,sys1", "cov b0.txt,sys0,0",
        "covx b0.txt,sys0,0,0", "substr b0.txt,b1.txt,0,2", 'spstr b0.txt,b1.txt,"a",0']),
    # Its attributes that its memory alone gives, each pair apart: its four
    # colours, each xcen and ycen, isbr, and its val; then spax and spay,
    # which its drawing and entries give; then a second font.
    _probe("of-other-colours", with_components(
        button_component(bco=1, bco2=2, pco=3, pco2=4),
        button_component("b1", y=70, bco=65535, bco2=0, pco=63488, pco2=31)), fixtures=True),
    _probe("of-other-placing", with_components(
        button_component(xcen=0, ycen=2, isbr=1), button_component("b1", y=70, xcen=2, ycen=0))),
    _probe("pressed-from-the-start", with_components(
        button_component(val=1), button_component("b1", y=70))),
    _probe("of-spacing", with_components(
        button_component(spax=5, spay=7), button_component("b1", y=70, spax=255, spay=3)),
        fixtures=True),
    _probe("in-a-second-font", with_the_first_in_a_second_font(
        button_component(), button_component("b1", y=70))),
]
