"""The touch capture component's probes (component_types/touch_capture.py):
touch captures on the T base folder's pages, at their defaults and with
other vals, two of them, one among a text, a number, a button, a slider, a
waveform, a variable, and a timer, one on a second page, five on a page,
and code in a touch capture's events; then a touch capture's val in code.
Run them with `tools.tft.probe run touch_capture_probes`.

Each probe of a touch capture compares the whole file, part by part, and
keeps the user code alone as its fixtures (component_probes.py gives both).
The probe of code compares the blocks of page0's Touch Release event alone,
which it keeps as its fixture (statement_probes.py gives both).
"""
from functools import partial

from tools.tft.probing.attribute_probes import with_attributes
from tools.tft.probing.button_probes import button_component
from tools.tft.probing.component_probes import type_probe, with_components
from tools.tft.probing.number_probes import number_component
from tools.tft.probing.probe_runner import Probe
from tools.tft.probing.slider_probes import slider_component
from tools.tft.probing.statement_probes import ours_in_event, theirs_in_event
from tools.tft.probing.text_probes import text_component
from tools.tft.probing.timer_probes import timer_component
from tools.tft.probing.variable_probes import variable_component
from tools.tft.probing.waveform_probes import waveform_component


def touch_capture_component(name: str = "tc0", val: int = None) -> str:
    """Returns a touch capture component in a page file's form, its val at
    its default unless given."""
    return ('\n[[component]]\nname = "%s"\ntype = "touch-capture"\n' % name
            + ("" if val is None else "val = %d\n" % val))


_probe = partial(type_probe, "touch-capture")

# The probes keeping fixtures are the fewest that show each part: two touch
# captures on a page, one of another val; one among a text, a number, a
# button, a slider and a waveform, which add to the load section too, a
# variable, and a timer; one on a second page, numbered on from the first's;
# and its val in code.
PROBES = [
    _probe("one", with_components(touch_capture_component())),
    _probe("two", with_components(touch_capture_component(),
                                  touch_capture_component("tc1", val=5)), fixtures=True),
    _probe("of-255", with_components(touch_capture_component(val=255))),
    _probe("among-the-types-matched",
           with_components(text_component(), touch_capture_component(), number_component(y=60),
                           button_component(y=110), slider_component(y=170),
                           waveform_component(y=220), variable_component(), timer_component()),
           fixtures=True),
    _probe("on-second-page", with_components(touch_capture_component(), page="page1"),
           fixtures=True),
    _probe("five-on-a-page", with_components(*[touch_capture_component("tc%d" % number)
                                               for number in range(5)])),
    _probe("event-code", with_components(
        touch_capture_component(), code="on tc0.down:\n  sys0=1\non tc0.up:\n  sys1=2\n")),
    _probe("named-with-14", with_components(touch_capture_component("Touch_name_o14"))),
    # A touch capture's val read, in a sum, and compared in if, while, and
    # for. Code cannot set it: the Nextion Editor refuses that.
    Probe("touch-capture-val-in-code", "T", with_attributes(
        ["sys0=tc0.val", "sys1=tc1.val+sys0", "if(tc0.val==1)", "{", "sys0=2", "}",
         "while(sys0<tc1.val)", "{", "sys0++", "}", "for(sys0=0;sys0<tc0.val;sys0++)", "{",
         "sys1++", "}"],
        [touch_capture_component(), touch_capture_component("tc1", val=3)]),
          ours_in_event, theirs_in_event, "touch-capture"),
]
