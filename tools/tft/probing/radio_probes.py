"""The radio component's probes (component_types/radio.py): radios on the T
base folder's pages, with other places, sizes, colours, and vals, two of
them, one among a text, a number, a button, a checkbox, a variable, and a
timer, one before a text, one on a second page, ten on a page, and code in
a radio's events; then a radio's val in code. Run them with `tools.tft.probe
run radio_probes`.

Each probe of a radio compares the whole file, part by part, and keeps the
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
from tools.tft.probing.probe_runner import Probe
from tools.tft.probing.statement_probes import ours_in_event, theirs_in_event
from tools.tft.probing.text_probes import text_component
from tools.tft.probing.timer_probes import timer_component
from tools.tft.probing.variable_probes import variable_component


def radio_component(name: str = "r0", x: int = 10, y: int = 10, w: int = 20, h: int = 20,
                    **attributes: int) -> str:
    """Returns a radio component in a page file's form, its other attributes,
    such as val, at their defaults unless given."""
    return ('\n[[component]]\nname = "%s"\ntype = "radio"\nx = %d\ny = %d\nw = %d\nh = %d\n'
            % (name, x, y, w, h)
            + "".join("%s = %d\n" % item for item in attributes.items()))


_probe = partial(type_probe, "radio")

# The probes keeping fixtures are the fewest that show each part: two radios
# on a page, one chosen and one not; one among a text, a number, a button, a
# checkbox, a variable, and a timer; one on a second page, numbered on from
# the first's; and its val in code.
PROBES = [
    _probe("one", with_components(radio_component())),
    _probe("two", with_components(radio_component(), radio_component("r1", y=60, val=0)),
           fixtures=True),
    _probe("not-chosen", with_components(radio_component(val=0))),
    # The radius follows the width alone, less 1 when it is even.
    _probe("wider-than-tall", with_components(radio_component(w=40, h=21))),
    _probe("taller-than-wide-and-odd", with_components(radio_component(w=21, h=44))),
    # The smallest a radio may be, a radius of 0, and an odd width of 3, a
    # radius of 1.
    _probe("of-2-by-2", with_components(radio_component(x=0, y=0, w=2, h=2))),
    _probe("of-3-by-3", with_components(radio_component(x=0, y=0, w=3, h=3))),
    _probe("of-the-screen", with_components(radio_component(x=0, y=0, w=320, h=480))),
    _probe("at-the-edges", with_components(radio_component(x=300, y=460))),
    _probe("in-other-colours", with_components(radio_component(bco=1024, pco=63488))),
    _probe("among-the-types-matched",
           with_components(text_component(y=60), radio_component(), number_component(y=100),
                           button_component(y=140), checkbox_component(y=200),
                           variable_component(), timer_component()), fixtures=True),
    _probe("before-a-text", with_components(radio_component(), text_component(y=60))),
    _probe("on-second-page", with_components(radio_component(), page="page1"), fixtures=True),
    _probe("ten-on-a-page", with_components(*[radio_component("r%d" % number, y=10 + 40 * number)
                                              for number in range(10)])),
    # The down event's code follows the Nextion Editor's own, which switches
    # its val.
    _probe("event-code", with_components(
        radio_component(), code="on r0.down:\n  sys0=1\non r0.up:\n  sys1=2\n")),
    _probe("named-with-14", with_components(radio_component("Radio_name_o14"))),
    # A radio's val set, stepped, read, compared in if and while, as the
    # serial commands' operand, and a radio as the component of the screen's
    # commands.
    Probe("radio-val-in-code", "T", with_attributes(
        ["r0.val=0", "sys0=r1.val", "r1.val=r0.val", "if(r0.val==1)", "{", "r1.val=0", "}",
         "while(r0.val<1)", "{", "r0.val++", "}", "get r0.val", "print r1.val", "vis r0,0",
         "tsw r0,0", "click r1,1", "ref r1"],
        [radio_component(), radio_component("r1", y=60)]),
          ours_in_event, theirs_in_event, "radio"),
]
