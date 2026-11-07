"""The checkbox component's probes (component_types/checkbox.py): checkboxes
on the T base folder's pages, with other places, sizes, colours, and vals,
two of them, one among a text, a number, a button, a progress bar, a
variable, and a timer, one before a text, one on a second page, ten on a
page, and code in a checkbox's events; then a checkbox's val in code. Run
them with `tools.tft.probe run checkbox_probes`.

Each probe of a checkbox compares the whole file, part by part, and keeps
the user code alone as its fixtures (component_probes.py gives both). The
probe of code compares the blocks of page0's Touch Release event alone,
which it keeps as its fixture (statement_probes.py gives both).
"""
from functools import partial

from tools.tft.probing.attribute_probes import with_attributes
from tools.tft.probing.button_probes import button_component
from tools.tft.probing.component_probes import type_probe, with_components
from tools.tft.probing.number_probes import number_component
from tools.tft.probing.probe_runner import Probe
from tools.tft.probing.progress_bar_probes import progress_bar_component
from tools.tft.probing.statement_probes import ours_in_event, theirs_in_event
from tools.tft.probing.text_probes import text_component
from tools.tft.probing.timer_probes import timer_component
from tools.tft.probing.variable_probes import variable_component


def checkbox_component(name: str = "c0", x: int = 10, y: int = 10, w: int = 20, h: int = 20,
                       **attributes: int) -> str:
    """Returns a checkbox component in a page file's form, its other
    attributes, such as val, at their defaults unless given."""
    return ('\n[[component]]\nname = "%s"\ntype = "checkbox"\nx = %d\ny = %d\nw = %d\nh = %d\n'
            % (name, x, y, w, h)
            + "".join("%s = %d\n" % item for item in attributes.items()))


_probe = partial(type_probe, "checkbox")

# The probes keeping fixtures are the fewest that show each part: two
# checkboxes on a page, one checked and one not; one among a text, a number,
# a button, a progress bar, a variable, and a timer; one on a second page,
# numbered on from the first's; and its val in code.
PROBES = [
    _probe("one", with_components(checkbox_component())),
    _probe("two", with_components(checkbox_component(), checkbox_component("c1", y=60, val=0)),
           fixtures=True),
    _probe("unchecked", with_components(checkbox_component(val=0))),
    # The square inside follows the width alone.
    _probe("wider-than-tall", with_components(checkbox_component(w=40, h=20))),
    _probe("taller-than-wide", with_components(checkbox_component(w=20, h=44))),
    # Under 4 wide, a quarter of its width is 0.
    _probe("of-3-by-3", with_components(checkbox_component(x=0, y=0, w=3, h=3))),
    _probe("of-the-screen", with_components(checkbox_component(x=0, y=0, w=320, h=480))),
    _probe("at-the-edges", with_components(checkbox_component(x=300, y=460))),
    _probe("in-other-colours", with_components(checkbox_component(bco=1024, pco=63488))),
    _probe("among-the-types-matched",
           with_components(text_component(y=60), checkbox_component(), number_component(y=100),
                           button_component(y=140), progress_bar_component(y=200),
                           variable_component(), timer_component()), fixtures=True),
    _probe("before-a-text", with_components(checkbox_component(), text_component(y=60))),
    _probe("on-second-page", with_components(checkbox_component(), page="page1"),
           fixtures=True),
    _probe("ten-on-a-page", with_components(*[checkbox_component("c%d" % number,
                                                                 y=10 + 40 * number)
                                              for number in range(10)])),
    # The down event's code follows the Nextion Editor's own, which switches
    # its val.
    _probe("event-code", with_components(
        checkbox_component(), code="on c0.down:\n  sys0=1\non c0.up:\n  sys1=2\n")),
    _probe("named-with-14", with_components(checkbox_component("Checkbox_nam14"))),
    # A checkbox's val set, stepped, read, compared in if and while, as the
    # serial commands' operand, and a checkbox as the component of the
    # screen's commands.
    Probe("checkbox-val-in-code", "T", with_attributes(
        ["c0.val=0", "sys0=c1.val", "c1.val=c0.val", "if(c0.val==1)", "{", "c1.val=0", "}",
         "while(c0.val<1)", "{", "c0.val++", "}", "get c0.val", "print c1.val", "vis c0,0",
         "tsw c0,0", "click c1,1", "ref c1"],
        [checkbox_component(), checkbox_component("c1", y=60)]),
          ours_in_event, theirs_in_event, "checkbox"),
    # Each style: no border, a border of its borderc and borderw, sunken, at
    # its default, with a borderc and a borderw it does not keep, and raised,
    # unchecked.
    _probe("of-each-style", with_components(
        checkbox_component(w=40, h=30, style=0, bco=31, pco=2016),
        checkbox_component("c1", y=60, w=40, h=30, style=1, borderc=63488, borderw=3, bco=31),
        checkbox_component("c2", y=110, w=40, h=30, borderc=63488, borderw=3),
        checkbox_component("c3", y=160, w=40, h=30, style=3, val=0)), fixtures=True),
    # A border of one colour at the ends of its width, and its colour apart
    # from the checkbox's.
    _probe("of-borders", with_components(
        checkbox_component(w=40, h=30, style=1, borderc=1, borderw=0, bco=2, pco=3),
        checkbox_component("c1", y=60, w=60, h=60, style=1, borderc=65535, borderw=255,
                           bco=0, pco=4))),
    # Its borderc and borderw in code, read and set, and its val, whose
    # entry is two on at a style of 1.
    Probe("checkbox-borders-in-code", "T", with_attributes(
        ["sys0=c0.borderc", "c0.borderw=5", "c0.borderc=c0.bco", "c0.val=0", "sys1=c1.val"],
        [checkbox_component(w=40, h=30, style=1, borderc=63488, borderw=3),
         checkbox_component("c1", y=60)]),
          ours_in_event, theirs_in_event, "checkbox"),
]
