"""The xfloat component's probes (component_types/xfloat.py): xfloats on the
T base folder's pages, with other places, sizes, vals, vvs0, and vvs1, two
of them, one among a text, a number, a button, a checkbox, a variable, and
a timer, one before a text, one on a second page, ten on a page, and code
in an xfloat's events; then an xfloat's val in code; then xfloats with
other colours, centring, isbr, and spacing, and one in a second font; then
xfloats of each style, of borders at the ends of their colour and width,
with a picture or a crop of one behind them, a picture not given and
pictures given that an xfloat does not show, a picture behind xfloats in a
project of none, and their borders and pictures in code. Run them with
`tools.tft.probe run xfloat_probes`.

Each probe of an xfloat compares the whole file, part by part, and keeps
the user code alone as its fixtures (component_probes.py gives both). The
probe of code compares the blocks of page0's Touch Release event alone,
which it keeps as its fixture (statement_probes.py gives both).
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


def xfloat_component(name: str = "x0", x: int = 10, y: int = 10, w: int = 100, h: int = 30,
                     pictures: dict = None, **attributes: int) -> str:
    """Returns an xfloat component in a page file's form, in the base
    folder's font, its `pictures`, as {"pic": the name of a picture of the
    project}, and its other attributes, such as val, at their defaults unless
    given."""
    return ('\n[[component]]\nname = "%s"\ntype = "xfloat"\nx = %d\ny = %d\nw = %d\nh = %d\n'
            'font = "NotoSans24"\n' % (name, x, y, w, h)
            + "".join('%s = "%s"\n' % item for item in (pictures or {}).items())
            + "".join("%s = %d\n" % item for item in attributes.items()))


_probe = partial(type_probe, "xfloat")

# The probes keeping fixtures are the fewest that show each part: two
# xfloats on a page, one with a val and digits; one among a text, a number,
# a button, a checkbox, a variable, and a timer; one on a second page,
# numbered on from the first's; and its val in code.
PROBES = [
    _probe("one", with_components(xfloat_component())),
    _probe("two", with_components(xfloat_component(),
                                  xfloat_component("x1", y=60, val=1234, vvs0=2, vvs1=2)),
           fixtures=True),
    _probe("negative", with_components(xfloat_component(val=-12345, vvs1=2))),
    _probe("of-the-highest-val", with_components(xfloat_component(val=2147483647))),
    _probe("of-the-lowest-val", with_components(xfloat_component(val=-2147483648))),
    # The most digits before and after its point.
    _probe("of-10-and-8-digits", with_components(xfloat_component(val=1, vvs0=10, vvs1=8))),
    _probe("of-2-by-2", with_components(xfloat_component(x=0, y=0, w=2, h=2))),
    _probe("of-the-screen", with_components(xfloat_component(x=0, y=0, w=320, h=480))),
    _probe("at-the-edges", with_components(xfloat_component(x=220, y=450))),
    _probe("among-the-types-matched",
           with_components(text_component(), xfloat_component(y=50), number_component(y=90),
                           button_component(y=130), checkbox_component(y=190),
                           variable_component(), timer_component()), fixtures=True),
    _probe("before-a-text", with_components(xfloat_component(), text_component(y=60))),
    _probe("on-second-page", with_components(xfloat_component(), page="page1"),
           fixtures=True),
    _probe("ten-on-a-page", with_components(*[xfloat_component("x%d" % number,
                                                               y=10 + 45 * number)
                                              for number in range(10)])),
    _probe("event-code", with_components(
        xfloat_component(), code="on x0.down:\n  sys0=1\non x0.up:\n  sys1=2\n")),
    _probe("named-with-14", with_components(xfloat_component("Xflt_name_of14"))),
    # An xfloat's val set, stepped, read, compared in if and while, as the
    # serial commands' operand, and an xfloat as the component of the
    # screen's commands.
    Probe("xfloat-val-in-code", "T", with_attributes(
        ["x0.val=5", "sys0=x1.val", "x1.val=x0.val+sys0", "x0.val++", "if(x0.val<50)", "{",
         "x1.val=100", "}", "while(x1.val>0)", "{", "x1.val-=10", "}", "get x0.val",
         "print x1.val", "vis x0,0", "tsw x0,0", "click x1,1", "ref x1"],
        [xfloat_component(), xfloat_component("x1", y=60)]),
          ours_in_event, theirs_in_event, "xfloat"),
    # Its attributes that its memory alone gives, as a number's: its colours
    # at their ends, each xcen and ycen, isbr, spax, and spay; then a second
    # font.
    _probe("of-other-looks", with_components(
        xfloat_component(val=1234, vvs1=2, bco=0, pco=63488, xcen=0, ycen=2, isbr=0, spax=5,
                         spay=7),
        xfloat_component("x1", y=60, val=1234, vvs1=2, xcen=2, ycen=0, spax=255, spay=255),
        xfloat_component("x2", y=110, val=1234, vvs1=2, bco=1, pco=65535)), fixtures=True),
    _probe("in-a-second-font", with_the_first_in_a_second_font(
        xfloat_component(), xfloat_component("x1", y=60))),
    # Its border and what lies behind it, as a number's. Each xfloat's spax
    # and spay are apart, and its val, vvs0, and vvs1 are not 0, so that an
    # entry moved onto another would not match. First each style: a border
    # of its borderc and borderw, whose entries move every later entry two
    # on; sunken; raised; and none; the last three each with a borderc and a
    # borderw it does not keep.
    _probe("of-each-style", with_components(
        xfloat_component(val=1234, vvs0=3, vvs1=2, style=1, borderc=63488, borderw=3, spax=3,
                         spay=5),
        xfloat_component("x1", y=60, val=5678, vvs0=4, vvs1=1, style=2, borderc=63488,
                         borderw=3, spax=5),
        xfloat_component("x2", y=110, val=12, vvs0=2, vvs1=1, style=3, borderc=63488, borderw=3,
                         spay=7),
        xfloat_component("x3", y=160, val=34, vvs0=2, vvs1=1, borderc=63488, borderw=3,
                         isbr=1)), fixtures=True),
    # A border at the ends of its colour and of its width, which ends its
    # setbrush.
    _probe("of-borders", with_components(
        xfloat_component(val=1, vvs0=1, vvs1=1, style=1, borderc=0, borderw=0, spax=3),
        xfloat_component("x1", y=60, val=2, vvs0=1, vvs1=1, style=1, borderc=65535,
                         borderw=255, spay=5))),
    # What lies behind it: a picture, at a sta of 2, and a crop of one, at a
    # sta of 0, whose style has no entry, so every later entry is one back,
    # each with a bco it does not keep; then each with a 3D style, which
    # draws no border there and is written as a style of 0.
    _probe("of-a-picture-and-a-crop", with_pictures(
        SCREEN_PICTURES, xfloat_component(val=1234, vvs0=3, vvs1=2, sta=2,
                                          pictures={"pic": "bg2"}, bco=31, spax=3),
        xfloat_component("x1", y=60, val=5678, vvs0=4, vvs1=1, sta=0, pictures={"picc": "bg"},
                         bco=31, spay=5),
        xfloat_component("x2", y=110, val=12, vvs0=2, vvs1=1, sta=2, style=3,
                         pictures={"pic": "bg"}),
        xfloat_component("x3", y=160, val=34, vvs0=2, vvs1=1, sta=0, style=2,
                         pictures={"picc": "bg2"}, isbr=1)), fixtures=True),
    # A style of 1 behind a picture and a crop, which draws no border there
    # but gives its borderc's and borderw's entries, as a number's.
    _probe("of-a-border-behind-a-picture-and-a-crop", with_pictures(
        SCREEN_PICTURES,
        xfloat_component(val=1234, vvs0=3, vvs1=2, sta=2, style=1, borderc=63488, borderw=3,
                         pictures={"pic": "bg2"}),
        xfloat_component("x1", y=60, val=5678, vvs0=4, vvs1=1, sta=0, style=1, borderc=31,
                         borderw=7, pictures={"picc": "bg"}))),
    # A picture behind it, but none given; and a colour behind it, with a
    # picture and a crop given, which it does not keep.
    _probe("of-no-picture-and-of-a-colour-with-pictures", with_pictures(
        SCREEN_PICTURES, xfloat_component(val=12, vvs0=2, vvs1=1, sta=2, spax=3),
        xfloat_component("x1", y=60, val=34, vvs0=2, vvs1=1,
                         pictures={"pic": "bg", "picc": "bg2"}, spay=5))),
    # A picture and a crop behind xfloats in a project of no pictures, whose
    # entry's highest, the last picture, is -1.
    _probe("of-a-picture-in-a-project-of-none", with_components(
        xfloat_component(val=12, vvs0=2, vvs1=1, sta=2, spax=3),
        xfloat_component("x1", y=60, val=34, vvs0=2, vvs1=1, sta=0, spay=5))),
    # Its border and its picture read and set in code; then its val, vvs0,
    # and pco, whose entries are two on at a style of 1 and one back behind
    # a picture.
    Probe("xfloat-borders-and-pictures-in-code", "T", with_screen_pictures_and_code(
        ["sys0=x0.borderc", "x0.borderc=31", "x0.borderw=5", "sys1=x1.pic", "x1.pic=0",
         "x0.val=7", "x1.vvs0=3", "sys2=x1.pco+x0.vvs1"],
        xfloat_component(val=1234, vvs0=3, vvs1=2, style=1, borderc=63488, borderw=3, spax=3),
        xfloat_component("x1", y=60, val=5678, vvs0=4, vvs1=1, sta=2, pictures={"pic": "bg2"},
                         spay=5)),
          ours_in_event, theirs_in_event, "xfloat"),
]
