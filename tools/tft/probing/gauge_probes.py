"""The gauge component's probes (component_types/gauge.py): gauges on the T
base folder's pages, of sta 1, with other places, sizes, and vals, two of
them, one among a text, a number, a button, a checkbox, a variable, and a
timer, one before a text, one on a second page, five on a page, and code in
a gauge's events; then a gauge's val in code; then gauges of other needles
and colours, and with a picture or a crop behind them, and their pictures
in code. Run them with `tools.tft.probe run gauge_probes`.

Each probe of a gauge compares the whole file, part by part, and keeps the
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


def gauge_component(name: str = "z0", x: int = 10, y: int = 10, w: int = 100, h: int = 100,
                    sta: int = 1, pictures: dict = None, **attributes: int) -> str:
    """Returns a gauge component in a page file's form, its sta 1, which T
    and K take, unless given, its `pictures`, as {"pic": the name of a
    picture of the project}, and its other attributes, such as val, at
    their defaults unless given."""
    return ('\n[[component]]\nname = "%s"\ntype = "gauge"\nx = %d\ny = %d\nw = %d\nh = %d\n'
            'sta = %d\n' % (name, x, y, w, h, sta)
            + "".join('%s = "%s"\n' % item for item in (pictures or {}).items())
            + "".join("%s = %d\n" % item for item in attributes.items()))


# Three pictures to put behind a gauge: red, picture 0, and bg and bg2,
# pictures 1 and 2, as large as the screen, so that a crop of either fills
# any gauge.
_PICTURES = [("red", (8, 4), (255, 0, 0)), ("bg", (320, 480), (0, 0, 255)),
             ("bg2", (320, 480), (0, 255, 0))]
# A gauge's needle and colours away from their defaults, which a picture or
# a crop behind it keeps but its bco.
_LOOKS = dict(bco=31, pco=63488, pco2=2016, format=90, up=40, down=20, left=100, hig=10, wid=5,
              vvs0=3, vvs1=9, vvs2=4, val=45)


_probe = partial(type_probe, "gauge")

# The probes keeping fixtures are the fewest that show each part: two
# gauges on a page, one wider than tall at a val of 90; one among a text, a
# number, a button, a checkbox, a variable, and a timer; one on a second
# page, numbered on from the first's; and its val in code.
PROBES = [
    _probe("one", with_components(gauge_component())),
    _probe("two", with_components(gauge_component(),
                                  gauge_component("z1", y=150, w=120, h=80, val=90)),
           fixtures=True),
    _probe("of-180", with_components(gauge_component(val=180))),
    _probe("of-360", with_components(gauge_component(val=360))),
    # Its needle is half its height long, whatever its width.
    _probe("taller-than-wide", with_components(gauge_component(w=80, h=120))),
    _probe("small", with_components(gauge_component(x=0, y=0, w=20, h=20))),
    _probe("large", with_components(gauge_component(x=0, y=0, w=320, h=320))),
    _probe("at-the-edges", with_components(gauge_component(x=220, y=380))),
    _probe("among-the-types-matched",
           with_components(text_component(), gauge_component(y=50), number_component(y=160),
                           button_component(y=200), checkbox_component(y=260),
                           variable_component(), timer_component()), fixtures=True),
    _probe("before-a-text", with_components(gauge_component(), text_component(y=120))),
    _probe("on-second-page", with_components(gauge_component(), page="page1"), fixtures=True),
    _probe("five-on-a-page", with_components(*[gauge_component("z%d" % number,
                                                               x=10 + 60 * number, w=50, h=50)
                                               for number in range(5)])),
    _probe("event-code", with_components(
        gauge_component(), code="on z0.down:\n  sys0=1\non z0.up:\n  sys1=2\n")),
    _probe("named-with-14", with_components(gauge_component("Gaug_name_of14"))),
    # A gauge's val set, stepped, read, compared in if and while, as the
    # serial commands' operand, and a gauge as the component of the screen's
    # commands.
    Probe("gauge-val-in-code", "T", with_attributes(
        ["z0.val=90", "sys0=z1.val", "z1.val=z0.val+sys0", "z0.val++", "if(z0.val<180)", "{",
         "z1.val=360", "}", "while(z1.val>0)", "{", "z1.val-=45", "}", "get z0.val",
         "print z1.val", "vis z0,0", "tsw z0,0", "click z1,1", "ref z1"],
        [gauge_component(), gauge_component("z1", y=150)]),
          ours_in_event, theirs_in_event, "gauge"),
    # Its needle and colours away from their defaults, at both ends of each
    # rule, every two values of a gauge apart that could trade places.
    _probe("of-other-looks", with_components(
        gauge_component(**_LOOKS),
        gauge_component("z1", x=10, y=120, w=120, h=80, bco=0, pco=1, pco2=2, format=0,
                        up=32767, down=0, left=1024, hig=100, wid=20, vvs0=128, vvs1=0,
                        vvs2=127, val=360),
        gauge_component("z2", x=10, y=220, bco=65535, pco=65534, pco2=4, format=360, up=0,
                        down=32767, left=0, hig=0, wid=1, vvs0=0, vvs1=128, vvs2=1, val=0)),
        fixtures=True),
    # What lies behind it: a picture, at a sta of 2, and a crop of one, at a
    # sta of 0, with its needle and colours away from their defaults.
    _probe("of-a-picture-and-a-crop", with_pictures(
        _PICTURES, gauge_component(sta=2, pictures={"pic": "bg"}, **_LOOKS),
        gauge_component("z1", y=120, sta=0, pictures={"picc": "bg2"}, **_LOOKS)),
        fixtures=True),
    # A picture behind it, but none given; and a colour behind it, with a
    # picture and a crop given, which it does not keep.
    _probe("of-no-picture-and-of-a-colour-with-pictures", with_pictures(
        _PICTURES, gauge_component(sta=2),
        gauge_component("z1", y=120, pictures={"pic": "red", "picc": "bg"}))),
    # Its pic and picc in code, read and set, beside its val and pco.
    Probe("gauge-pictures-in-code", "T", with_pictures_and_code(
        _PICTURES,
        ["sys0=z0.pic", "z0.pic=1", "sys0=z1.picc", "z1.picc=0", "z0.val=5",
         "sys0=z0.pco+z1.val"],
        gauge_component(sta=2, pictures={"pic": "bg"}),
        gauge_component("z1", y=120, sta=0, pictures={"picc": "bg2"})),
          ours_in_event, theirs_in_event, "gauge"),
]
