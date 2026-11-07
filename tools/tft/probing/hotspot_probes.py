"""The hotspot component's probes (component_types/hotspot.py): hotspots on the
T base folder's page, with other places and sizes, two and ten of them, one
among a text, a number, a button, a variable, a timer, and a progress bar,
one before a text, one on a second page, and code in a hotspot's events,
then a hotspot as the component of the screen's commands. Run them with
`tools.tft.probe run hotspot_probes`.

Each probe of a hotspot compares the whole file, part by part, and keeps the
user code alone as its fixtures (component_probes.py gives both). The probe
of code compares the blocks of page0's Touch Release event alone, which it
keeps as its fixture (statement_probes.py gives both).
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


def hotspot_component(name: str = "m0", x: int = 10, y: int = 10, w: int = 100,
                      h: int = 50, **attributes: int) -> str:
    """Returns a hotspot component in a page file's form, its attributes,
    such as aph, at their defaults unless given."""
    return ('\n[[component]]\nname = "%s"\ntype = "hotspot"\nx = %d\ny = %d\nw = %d\nh = %d\n'
            % (name, x, y, w, h) + "".join("%s = %d\n" % item for item in attributes.items()))


_probe = partial(type_probe, "hotspot")

# The probes keeping fixtures are the fewest that show each part: two
# hotspots on a page; one among a text, a number, a button, a variable, a
# timer, and a progress bar; one on a second page, numbered on from the
# first's; and a hotspot in the screen's commands.
PROBES = [
    _probe("one", with_components(hotspot_component())),
    _probe("two", with_components(hotspot_component(), hotspot_component("m1", y=80)),
           fixtures=True),
    _probe("among-the-types-matched",
           with_components(text_component(y=70), hotspot_component(), number_component(y=110),
                           button_component(y=150), variable_component(), timer_component(),
                           progress_bar_component(y=210)), fixtures=True),
    # A text after a hotspot: its drawing and fill follow the hotspot's blocks.
    _probe("before-a-text", with_components(hotspot_component(), text_component(y=70))),
    # Eleven objects: the run of 0xFF bytes that starts the page's memory is
    # 12 bytes if each hotspot counts in it, though a hotspot has no memory.
    _probe("ten-on-a-page", with_components(*[hotspot_component("m%d" % number,
                                                                y=10 + 45 * number, h=40)
                                              for number in range(10)])),
    _probe("of-2-by-2", with_components(hotspot_component(x=0, y=0, w=2, h=2))),
    _probe("at-the-edges", with_components(hotspot_component(x=220, y=430))),
    _probe("of-the-screen", with_components(hotspot_component(x=0, y=0, w=320, h=480))),
    _probe("named-with-14", with_components(hotspot_component("Hots_name_of14"))),
    _probe("event-code", with_components(
        hotspot_component(), code="on m0.down:\n  sys0=1\non m0.up:\n  sys1=2\n")),
    _probe("on-second-page", with_components(hotspot_component(), page="page1"),
           fixtures=True),
    # A hotspot as the component of vis, tsw, click, and ref.
    Probe("hotspot-in-commands", "T", with_attributes(
        ["vis m0,0", "tsw m0,0", "click m1,1", "ref m1"],
        [hotspot_component(), hotspot_component("m1", y=80)]),
          ours_in_event, theirs_in_event, "hotspot"),
]
