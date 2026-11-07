"""The crop component's probes (component_types/crop.py): crops on the T base
folder's pages, showing a part of one of the project's pictures, as large as
the screen or smaller, or none: two of them, one among a text, a number, a
button, a variable, a timer, and a picture, one before a text, one on a
second page, ten on a page, one at the screen's edges, with a picc past the
project's pictures, with vvs0 and vvs1 away from 0, and code in a crop's
events; then a crop's picc in code. Run them with `tools.tft.probe run
crop_probes`.

Each probe of a crop compares the whole file, part by part, and keeps the
user code alone as its fixtures (component_probes.py gives both). Each probe
of code compares the blocks of page0's Touch Release event alone, which it
keeps as its fixture (statement_probes.py gives both).
"""
from functools import partial

from tools.tft.probing.button_probes import button_component
from tools.tft.probing.component_probes import type_probe, with_components
from tools.tft.probing.number_probes import number_component
from tools.tft.probing.picture_probes import (picture_component, with_pictures,
                                         with_pictures_and_code)
from tools.tft.probing.probe_runner import Probe
from tools.tft.probing.statement_probes import ours_in_event, theirs_in_event
from tools.tft.probing.text_probes import text_component
from tools.tft.probing.timer_probes import timer_component
from tools.tft.probing.variable_probes import variable_component

# The project's pictures, as large as the screen, as nxwright's description
# of a crop's picc advises. A smaller one compiles too (of-a-small-picture).
_RED = ("bg", (320, 480), (255, 0, 0))
_BLUE = ("bg2", (320, 480), (0, 0, 255))


def crop_component(name: str = "q0", x: int = 10, y: int = 20, w: int = 50, h: int = 30,
                   picc: str = "bg", vvs0: int = None, vvs1: int = None,
                   **attributes: int) -> str:
    """Returns a crop component in a page file's form, showing a part of the
    project's picture `picc`, or none when `picc` is None, its vvs0, vvs1,
    and other attributes at their defaults unless given."""
    lines = ['\n[[component]]\nname = "%s"\ntype = "crop"\nx = %d\ny = %d\nw = %d\nh = %d\n'
             % (name, x, y, w, h)]
    if picc is not None:
        lines.append('picc = "%s"\n' % picc)
    lines += ["%s = %d\n" % (attribute, value)
              for attribute, value in (("vvs0", vvs0), ("vvs1", vvs1)) if value is not None]
    lines += ["%s = %d\n" % item for item in attributes.items()]
    return "".join(lines)


_probe = partial(type_probe, "crop")


def _code_probe(name: str, lines: list) -> Probe:
    """Returns a probe of `lines` in page0's Touch Release event, beside q0
    and q1, in a project of two pictures."""
    change = with_pictures_and_code([_RED, _BLUE], lines, crop_component(),
                                    crop_component("q1", y=200, w=40, h=60, picc="bg2"))
    return Probe("crop-" + name, "T", change, ours_in_event, theirs_in_event, "crop")


# The probes keeping fixtures are the fewest that show each part: two crops
# on a page, of two pictures; a crop among a text, a number, a button, a
# variable, a timer, and a picture; and a crop on a second page, numbered on
# from the first's.
PROBES = [
    _probe("one", with_pictures([_RED], crop_component())),
    _probe("two", with_pictures([_RED, _BLUE], crop_component(),
                                crop_component("q1", y=200, w=40, h=60, picc="bg2")),
           fixtures=True),
    _probe("of-none", with_components(crop_component(picc=None))),
    # A picc given as a number, past the project's two pictures.
    _probe("of-a-number-past-the-last", with_pictures(
        [_RED, _BLUE], crop_component().replace('picc = "bg"', "picc = 5"))),
    # A picture smaller than the screen, which nxwright's build takes.
    _probe("of-a-small-picture", with_pictures([("small", (8, 4), (0, 255, 0))],
                                               crop_component(picc="small"))),
    _probe("starting-elsewhere", with_pictures([_RED], crop_component(vvs0=5, vvs1=7))),
    # Past the picture's edge, which is 320 by 480. nxwright gives a vvs0 or
    # vvs1 in 2 bytes, from 0 to 65535.
    _probe("starting-past-the-edge", with_pictures([_RED], crop_component(vvs0=300, vvs1=500))),
    # Numbers of 4 and 5 characters, which code writes as 03 and their values.
    _probe("starting-at-4-and-5-digits", with_pictures([_RED], crop_component(vvs0=1000,
                                                                              vvs1=32767))),
    # Read as -99 and -999, either side of where code writes a number as 03
    # and its value, at 4 characters, its minus included.
    _probe("starting-at-minus-99-and-999", with_pictures([_RED], crop_component(vvs0=65437,
                                                                                vvs1=64537))),
    # Past 32767, which the screen reads as a signed 16-bit number.
    _probe("starting-past-32767", with_pictures([_RED], crop_component(vvs0=40000,
                                                                       vvs1=65535))),
    _probe("among-the-types-matched",
           with_pictures([_RED], text_component(), crop_component(y=60), number_component(y=100),
                         button_component(y=140), variable_component(), timer_component(),
                         # Apart from the others: the Nextion Editor writes
                         # more for components that overlap.
                         picture_component(x=200, y=300, w=40, h=40, pic="bg")), fixtures=True),
    _probe("before-a-text", with_pictures([_RED], crop_component(), text_component(y=60))),
    _probe("on-second-page", with_pictures([_RED], crop_component(), page="page1"),
           fixtures=True),
    _probe("ten-on-a-page", with_pictures([_RED], *[crop_component("q%d" % number,
                                                                   y=10 + 40 * number)
                                                    for number in range(10)])),
    _probe("at-the-edges", with_pictures([_RED], crop_component(x=270, y=450))),
    _probe("event-code", with_pictures([_RED], crop_component(),
                                       code="on q0.down:\n  sys0=1\non q0.up:\n  sys1=2\n")),
    _probe("named-with-14", with_pictures([_RED], crop_component("Crop_name_of14"))),
    # A crop's picc set, stepped, read, and compared, and a crop as the
    # component of the screen's commands.
    _code_probe("picc-in-code", [
        "q0.picc=1", "sys0=q1.picc", "q1.picc=q0.picc", "q0.picc++", "if(q0.picc==1)", "{",
        "q1.picc=0", "}", "vis q0,0", "tsw q0,0", "click q1,1", "ref q1"]),
]
