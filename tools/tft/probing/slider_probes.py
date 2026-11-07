"""The slider component's probes (component_types/slider.py): sliders on the
T base folder's pages, with other places, sizes, and vals, two of them, one
among a text, a number, a button, a checkbox, a variable, and a timer, one
after a timer, one beside its page's load code, one before a text, one on a
second page, ten on a page, and code in its three events; then a slider's
val in code; then sliders of other colours, sizes, modes, and bounds, their
vals outside them too; then sliders with pictures or crops behind their
tracks, or a picture as their cursor, and their pictures in code. Run them
with `tools.tft.probe run slider_probes`.

Each probe of a slider compares the whole file, part by part, and keeps the
user code alone as its fixtures (component_probes.py gives both). The probe
of code compares the blocks of page0's Touch Release event alone, which it
keeps as its fixture (statement_probes.py gives both).
"""
from functools import partial

from tools.tft.probing.attribute_probes import with_attributes
from tools.tft.probing.button_probes import button_component
from tools.tft.probing.checkbox_probes import checkbox_component
from tools.tft.probing.component_probes import type_probe, with_components
from tools.tft.probing.number_probes import number_component
from tools.tft.probing.picture_probes import with_pictures, with_pictures_and_code
from tools.tft.probing.probe_runner import Probe
from tools.tft.probing.statement_probes import ours_in_event, theirs_in_event
from tools.tft.probing.text_probes import text_component
from tools.tft.probing.timer_probes import timer_component
from tools.tft.probing.variable_probes import variable_component


def slider_component(name: str = "h0", x: int = 10, y: int = 10, w: int = 200, h: int = 25,
                     pictures: dict = None, **attributes: int) -> str:
    """Returns a slider component in a page file's form, its `pictures`, as
    {"pic": the name of a picture of the project}, and its other attributes,
    such as val, at their defaults unless given."""
    return ('\n[[component]]\nname = "%s"\ntype = "slider"\nx = %d\ny = %d\nw = %d\nh = %d\n'
            % (name, x, y, w, h)
            + "".join('%s = "%s"\n' % item for item in (pictures or {}).items())
            + "".join("%s = %d\n" % item for item in attributes.items()))


# Three pictures to put behind a slider's track and as its cursor: red,
# picture 0, and bg and bg2, pictures 1 and 2, as large as the screen, so
# that a crop of either fills any slider.
PICTURES = [("red", (8, 4), (255, 0, 0)), ("bg", (320, 480), (0, 0, 255)),
            ("bg2", (320, 480), (0, 255, 0))]
# A slider's colours and its ch and dis away from their defaults, which a
# picture or a crop behind its track does not keep.
_COLOURS = dict(bco=31, bco1=2016, pco=63488, ch=30, dis=80)
# The components and lines of the probe of pictures in code below.
PICTURES_IN_CODE = ["sys0=h0.pic", "h0.pic1=1", "sys0=h1.picc+h1.picc1", "h1.picc=2",
                    "sys0=h0.pic2", "h0.pic2=0", "h0.val=5", "sys0=h1.maxval-h1.minval",
                    "h1.val++"]
PICTURES_IN_CODE_COMPONENTS = (
    slider_component(sta=2, psta=1, pictures={"pic": "red", "pic1": "bg", "pic2": "bg2"}),
    slider_component("h1", y=60, sta=0, pictures={"picc": "bg", "picc1": "bg2"}))


_probe = partial(type_probe, "slider")

# The probes keeping fixtures are the fewest that show each part: two
# sliders on a page, each giving its load section a block; one among a text,
# a number, a button, a checkbox, a variable, and a timer; one on a second
# page, numbered on from the first's; and its val in code.
PROBES = [
    _probe("one", with_components(slider_component())),
    _probe("two", with_components(slider_component(), slider_component("h1", y=60, w=150, h=40,
                                                                       val=20)),
           fixtures=True),
    _probe("of-0", with_components(slider_component(val=0))),
    _probe("of-73", with_components(slider_component(val=73))),
    _probe("of-100", with_components(slider_component(val=100))),
    _probe("small", with_components(slider_component(x=0, y=0, w=20, h=10))),
    _probe("of-the-screen", with_components(slider_component(x=0, y=0, w=320, h=480))),
    _probe("at-the-edges", with_components(slider_component(x=120, y=455))),
    _probe("among-the-types-matched",
           with_components(text_component(), slider_component(y=50), number_component(y=90),
                           button_component(y=130), checkbox_component(y=190),
                           variable_component(), timer_component()), fixtures=True),
    # A timer, then a slider: each adds its blocks to the load section, in
    # the order of their IDs.
    _probe("after-a-timer", with_components(timer_component(), slider_component())),
    # The page's own load code follows the slider's block.
    _probe("with-page-load-code", with_components(slider_component(),
                                                  code="on page0.load:\n  sys2=1\n")),
    _probe("before-a-text", with_components(slider_component(), text_component(y=60))),
    _probe("on-second-page", with_components(slider_component(), page="page1"),
           fixtures=True),
    _probe("ten-on-a-page", with_components(*[slider_component("h%d" % number,
                                                               y=10 + 45 * number)
                                              for number in range(10)])),
    # The slide event's place is the record's fourth, a timer's timer
    # event's.
    _probe("event-code", with_components(
        slider_component(),
        code="on h0.down:\n  sys0=1\non h0.up:\n  sys1=2\non h0.slide:\n  sys2=3\n")),
    _probe("slide-code-alone", with_components(slider_component(),
                                               code="on h0.slide:\n  sys2=3\n")),
    _probe("named-with-14", with_components(slider_component("Slid_name_of14"))),
    # A slider's val set, stepped, read, compared in if and while, as the
    # serial commands' operand, and a slider as the component of the
    # screen's commands.
    Probe("slider-val-in-code", "T", with_attributes(
        ["h0.val=5", "sys0=h1.val", "h1.val=h0.val+sys0", "h0.val++", "if(h0.val<50)", "{",
         "h1.val=100", "}", "while(h1.val>0)", "{", "h1.val-=10", "}", "get h0.val",
         "print h1.val", "vis h0,0", "tsw h0,0", "click h1,1", "ref h1"],
        [slider_component(), slider_component("h1", y=60)]),
          ours_in_event, theirs_in_event, "slider"),
    # Its colours, its cursor's size, its dis, and its ch away from their
    # defaults, and a cursor of no size.
    _probe("colours-and-sizes", with_components(
        slider_component(bco=31, bco1=2016, pco=63488, dis=0, wid=20, hig=10, ch=10),
        slider_component("h1", y=110, wid=0, hig=0, dis=100, ch=0, val=0)), fixtures=True),
    # Upright sliders, one of other bounds, its val at its maxval.
    _probe("upright", with_components(
        slider_component(w=25, h=200, mode=1, val=30),
        slider_component("h1", x=60, w=25, h=200, mode=1, minval=5, maxval=60000, val=60000)),
        fixtures=True),
    # Other bounds across, its val between them.
    _probe("other-bounds", with_components(slider_component(minval=10, maxval=200, val=150))),
    # The highest bounds, its val at their top.
    _probe("highest-bounds", with_components(
        slider_component(minval=65534, maxval=65535, val=65535))),
    # A val outside its bounds: above its maxval, below its minval, and
    # between a minval above its maxval; then the most and least each takes,
    # a minval of 65535 above a maxval of 0, and a val of 0 below a minval
    # of 65535.
    _probe("val-outside-its-bounds", with_components(
        slider_component(val=200), slider_component("h1", y=60, minval=50, val=10),
        slider_component("h2", y=110, minval=80, maxval=20, val=50),
        slider_component("h3", y=160, minval=65535, maxval=0, val=65535),
        slider_component("h4", y=210, minval=65535, maxval=65535, val=0))),
    # What lies behind its track: pictures, at a sta of 2, and crops of
    # them, at a sta of 0, each with its colours, ch, and dis away from
    # their defaults, which it does not keep.
    _probe("of-pictures-and-crops", with_pictures(
        PICTURES, slider_component(sta=2, pictures={"pic": "bg", "pic1": "bg2"}, **_COLOURS),
        slider_component("h1", y=60, sta=0, pictures={"picc": "bg", "picc1": "bg2"},
                         **_COLOURS)), fixtures=True),
    # A cursor of a picture, at a psta of 1, before a colour and before
    # pictures behind its track.
    _probe("of-a-picture-cursor", with_pictures(
        PICTURES, slider_component(psta=1, pictures={"pic2": "red"}, **_COLOURS),
        slider_component("h1", y=60, sta=2, psta=1,
                         pictures={"pic": "red", "pic1": "bg", "pic2": "bg2"})), fixtures=True),
    # Pictures behind its track and as its cursor, but none given; and a
    # colour behind it and a round cursor, with pictures given, which it
    # does not keep.
    _probe("of-no-pictures-and-of-colours-with-pictures", with_pictures(
        PICTURES, slider_component(sta=2, psta=1), slider_component("h1", y=60, sta=0),
        slider_component("h2", y=110, pictures={"pic": "red", "pic1": "bg", "pic2": "bg2",
                                                 "picc": "bg", "picc1": "bg2"}))),
    # Its pictures in code, read and set, and its val, maxval, minval, and
    # pic2, whose entries are numbered one down with a picture or a crop
    # behind its track.
    Probe("slider-pictures-in-code", "T",
          with_pictures_and_code(PICTURES, PICTURES_IN_CODE, *PICTURES_IN_CODE_COMPONENTS),
          ours_in_event, theirs_in_event, "slider"),
]
