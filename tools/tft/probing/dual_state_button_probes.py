"""The dual-state button component's probes
(component_types/dual_state_button.py): dual-state buttons on the T base
folder's pages, with other places, sizes, texts, txt_maxl, and vals, two of
them, one among a text, a number, a button, a checkbox, a variable, and a
timer, one before a text, one on a second page, ten on a page, and code in
a dual-state button's events; then a dual-state button's txt and val in
code; then dual-state buttons with other colours, centring, isbr, and
spacing, and one in a second font; then dual-state buttons of each style,
of borders at the ends of their colour and width, with pictures or crops
behind them, released and pressed in, pictures not given and pictures
given that a dual-state button does not show, pictures behind dual-state
buttons in a project of none, and their borders and pictures in code. Run
them with `tools.tft.probe run dual_state_button_probes`.

Each probe of a dual-state button compares the whole file, part by part,
and keeps the user code alone as its fixtures (component_probes.py gives
both). The probe of code compares the blocks of page0's Touch Release event
alone, which it keeps as its fixture (statement_probes.py gives both).
"""
from functools import partial

from tools.tft.probing.attribute_probes import with_attributes
from tools.tft.probing.button_probes import button_component
from tools.tft.probing.checkbox_probes import checkbox_component
from tools.tft.probing.component_probes import (type_probe, with_components,
                                            with_the_first_in_a_second_font)
from tools.tft.probing.number_probes import number_component
from tools.tft.probing.picture_probes import (SCREEN_PICTURES, with_pictures,
                                          with_screen_pictures_and_code)
from tools.tft.probing.probe_runner import Probe
from tools.tft.probing.statement_probes import ours_in_event, theirs_in_event
from tools.tft.probing.text_probes import text_component
from tools.tft.probing.timer_probes import timer_component
from tools.tft.probing.variable_probes import variable_component


def dual_state_button_component(name: str = "bt0", x: int = 10, y: int = 10, w: int = 60,
                                h: int = 60, txt: str = "newtxt", txt_maxl: int = 10,
                                val: int = 0, pictures: dict = None,
                                **attributes: int) -> str:
    """Returns a dual-state button component in a page file's form, in the
    base folder's font, its `pictures`, as {"pic": the name of a picture of
    the project}, and its other attributes, such as bco, at their defaults
    unless given."""
    return ('\n[[component]]\nname = "%s"\ntype = "dual-state-button"\nx = %d\ny = %d\nw = %d\n'
            'h = %d\nfont = "NotoSans24"\ntxt = "%s"\ntxt_maxl = %d\nval = %d\n'
            % (name, x, y, w, h, txt, txt_maxl, val)
            + "".join('%s = "%s"\n' % item for item in (pictures or {}).items())
            + "".join("%s = %d\n" % item for item in attributes.items()))


# The colours, released and pressed in, of the dual-state buttons of the
# probes of their border and pictures: each apart from the others.
_COLOURS = dict(bco=1000, bco2=2000, pco=3000, pco2=4000)


def _looking(name: str, y: int, **attributes) -> str:
    """Returns a dual-state button of _COLOURS, at 10, `y`, with
    `attributes`."""
    return dual_state_button_component(name, y=y, **{**_COLOURS, **attributes})


_probe = partial(type_probe, "dual-state-button")

# The probes keeping fixtures are the fewest that show each part: two
# dual-state buttons on a page, one pressed in and one not; one among a
# text, a number, a button, a checkbox, a variable, and a timer; one on a
# second page, numbered on from the first's; and its txt and val in code.
PROBES = [
    _probe("one", with_components(dual_state_button_component())),
    _probe("two", with_components(dual_state_button_component(),
                                  dual_state_button_component("bt1", y=100, val=1)),
           fixtures=True),
    _probe("pressed-in", with_components(dual_state_button_component(val=1))),
    _probe("empty", with_components(dual_state_button_component(txt=""))),
    _probe("txt-maxl-1", with_components(dual_state_button_component(txt="A", txt_maxl=1))),
    _probe("txt-maxl-200", with_components(dual_state_button_component(txt="Yo",
                                                                       txt_maxl=200))),
    _probe("of-digits", with_components(dual_state_button_component(txt="Go12"))),
    _probe("of-2-by-2", with_components(dual_state_button_component(x=0, y=0, w=2, h=2))),
    _probe("of-the-screen", with_components(dual_state_button_component(x=0, y=0, w=320,
                                                                        h=480))),
    _probe("at-the-edges", with_components(dual_state_button_component(x=260, y=420))),
    _probe("among-the-types-matched",
           with_components(text_component(), dual_state_button_component(y=50),
                           number_component(y=120), button_component(y=160),
                           checkbox_component(y=220), variable_component(),
                           timer_component()), fixtures=True),
    _probe("before-a-text", with_components(dual_state_button_component(),
                                            text_component(y=80))),
    _probe("on-second-page", with_components(dual_state_button_component(), page="page1"),
           fixtures=True),
    _probe("ten-on-a-page", with_components(*[dual_state_button_component(
        "bt%d" % number, y=10 + 45 * number, h=40) for number in range(10)])),
    # The down event's code follows the Nextion Editor's own, which switches
    # its val and refs it.
    _probe("event-code", with_components(
        dual_state_button_component(), code="on bt0.down:\n  sys0=1\non bt0.up:\n  sys1=2\n")),
    _probe("named-with-14", with_components(dual_state_button_component("Dual_name_of14"))),
    # A dual-state button's txt set to a text, its val set and read, stepped,
    # and compared in if and while, both as the serial commands' operands,
    # and a dual-state button as the component of the screen's commands.
    Probe("dual-state-button-txt-and-val-in-code", "T", with_attributes(
        ['bt0.txt="On"', "bt0.val=1", "sys0=bt1.val", "bt1.val=bt0.val",
         "if(bt0.val==1)", "{", "bt1.val=0", "}", "while(bt0.val<1)", "{", "bt0.val++", "}",
         "get bt0.val", "print bt1.txt", "vis bt0,0", "tsw bt0,0", "click bt1,1", "ref bt1"],
        [dual_state_button_component(), dual_state_button_component("bt1", y=100)]),
          ours_in_event, theirs_in_event, "dual-state-button"),
    # Its attributes that its memory alone gives, as a button's, each pair
    # apart: its four colours, each xcen and ycen, and isbr; then spax and
    # spay, which its drawing and entries give; then a second font.
    _probe("of-other-colours", with_components(
        dual_state_button_component(bco=1, bco2=2, pco=3, pco2=4),
        dual_state_button_component("bt1", y=70, bco=65535, bco2=0, pco=63488, pco2=31)),
        fixtures=True),
    _probe("of-other-placing", with_components(
        dual_state_button_component(xcen=0, ycen=2, isbr=1),
        dual_state_button_component("bt1", y=70, xcen=2, ycen=0))),
    _probe("of-spacing", with_components(
        dual_state_button_component(spax=5, spay=7),
        dual_state_button_component("bt1", y=70, spax=255, spay=3)), fixtures=True),
    _probe("in-a-second-font", with_the_first_in_a_second_font(
        dual_state_button_component(), dual_state_button_component("bt1", y=70))),
    # Its border and what lies behind it, as a button's. Each dual-state
    # button's colours released and pressed in are apart, and so are its spax
    # and spay, so that an entry moved onto another would not match. First
    # each style: none; a border of its borderc and borderw, whose entries
    # move every later entry two on; sunken; raised; and its default, raised
    # and sunken while it is pressed in, the last with a borderc and a
    # borderw it does not keep. The third starts pressed in.
    _probe("of-each-style", with_components(
        _looking("bt0", 10, style=0, spax=3),
        _looking("bt1", 80, style=1, borderc=63488, borderw=3, spay=5),
        _looking("bt2", 150, style=2, val=1),
        _looking("bt3", 220, style=3, isbr=1),
        _looking("bt4", 290, borderc=63488, borderw=3, spax=7)), fixtures=True),
    # Borders whose borderc is written as digits, 999 and 0, or as a long
    # number, 1000, and whose borderw, which ends its setbrushes, is at each
    # end.
    _probe("of-borders", with_components(
        _looking("bt0", 10, style=1, borderc=999, borderw=0, spax=3),
        _looking("bt1", 80, style=1, borderc=1000, borderw=255, spay=5),
        _looking("bt2", 150, style=1, borderc=0, borderw=1))),
    # What lies behind it: pictures, at a sta of 2, and crops of them, at a
    # sta of 0, released and pressed in, whose style has no entry, so every
    # later entry is one back, each with colours it does not keep; then each
    # with another style, which draws no border there. The first starts
    # pressed in.
    _probe("of-pictures-and-crops", with_pictures(
        SCREEN_PICTURES,
        _looking("bt0", 10, sta=2, pictures={"pic": "bg", "pic2": "bg2"}, val=1, spax=3),
        _looking("bt1", 80, sta=0, pictures={"picc": "bg2", "picc2": "bg"}, spay=5),
        _looking("bt2", 150, sta=2, style=2, pictures={"pic": "bg2", "pic2": "bg"}),
        _looking("bt3", 220, sta=0, style=0, pictures={"picc": "bg", "picc2": "bg2"},
                 isbr=1),
        _looking("bt4", 290, sta=2, style=3, pictures={"pic": "bg", "pic2": "bg"})),
        fixtures=True),
    # A style of 1 behind pictures and crops, which draws no border there
    # but gives its borderc's and borderw's entries, as a button's.
    _probe("of-a-border-behind-pictures-and-crops", with_pictures(
        SCREEN_PICTURES,
        _looking("bt0", 10, sta=2, style=1, borderc=63488, borderw=3,
                 pictures={"pic": "bg", "pic2": "bg2"}),
        _looking("bt1", 80, sta=0, style=1, borderc=31, borderw=7,
                 pictures={"picc": "bg2", "picc2": "bg"}))),
    # Pictures behind it, but none given; and a colour behind it, with
    # pictures and crops given, which it does not keep.
    _probe("of-no-picture-and-of-a-colour-with-pictures", with_pictures(
        SCREEN_PICTURES, _looking("bt0", 10, sta=2, spax=3),
        _looking("bt1", 80, pictures={"pic": "bg", "pic2": "bg2", "picc": "bg2",
                                     "picc2": "bg"}, spay=5))),
    # Pictures and crops behind dual-state buttons in a project of no
    # pictures, whose entries' highest, the last picture, is -1.
    _probe("of-pictures-in-a-project-of-none", with_components(
        _looking("bt0", 10, sta=2, spax=3), _looking("bt1", 80, sta=0, spay=5))),
    # Its border read in code, which cannot set it, and its pictures read and
    # set; then its val and pco2, whose entries are two on at a style of 1
    # and one back behind a picture.
    Probe("dual-state-button-borders-and-pictures-in-code", "T",
          with_screen_pictures_and_code(
              ["sys0=bt0.borderc", "sys1=bt0.borderw", "sys2=bt1.pic2", "bt1.pic=0",
               "bt1.pic2=1", "bt0.val=1", "bt1.val=0", "sys0=bt1.pco2+bt0.pco"],
              _looking("bt0", 10, style=1, borderc=63488, borderw=3, spax=3),
              _looking("bt1", 80, sta=2, pictures={"pic": "bg2", "pic2": "bg"}, spay=5)),
          ours_in_event, theirs_in_event, "dual-state-button"),
]
