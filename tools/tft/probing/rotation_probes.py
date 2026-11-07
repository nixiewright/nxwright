"""The probes of a project's rotation (packaging.py and
frame.py): the T base folder turned to 90, 180, and 270
degrees by nxwright's device command, which turns its fonts and gives each
page the screen's size at the rotation. First a text at each rotation; then
a component of each drawn type on a picture at each rotation, laid out for
the turned screen, and on no background at 90 degrees; then pages with
pictures behind them at 90 and 270 degrees. Run them with
`tools.tft.probe run rotation_probes`.

Each compares the whole file, part by part, and one keeps the user code
alone as its fixtures (component_probes.py gives both).
"""
from tools.tft.probing import page_probes
from tools.tft.probing.component_probes import type_probe, with_components
from tools.tft.probing.model_probes import ScreenChange
from tools.tft.probing.page_probes import every_type_on_a_picture, every_type_on_no_background
from tools.tft.probing.text_probes import text_component


def turned(degrees: int, change) -> ScreenChange:
    """Returns a probe's change: `change`, then the folder turned to
    `degrees`, as nxwright's device command turns it
    (model_probes.ScreenChange)."""
    return ScreenChange(change, rotation=degrees)


def _grid(degrees: int):
    """The grid that fits the screen at `degrees`: the page probes' own at 0
    and 180 degrees, and one of three rows at 90 and 270."""
    return (page_probes.in_a_landscape_grid if degrees in (90, 270)
            else page_probes.in_a_grid)


def _page_probe(name: str):
    """The change of the page's probe `name` (page_probes.py)."""
    return next(probe.change for probe in page_probes.PROBES if probe.name == name)


PROBES = ([type_probe("rotation", "%d" % degrees,
                      turned(degrees, with_components(text_component("t0", txt="Hi"))))
           for degrees in (90, 180, 270)]
          + [type_probe("rotation", "%d-every-type-on-a-picture" % degrees,
                        turned(degrees, every_type_on_a_picture(_grid(degrees))),
                        fixtures=degrees == 90)
             for degrees in (90, 180, 270)]
          + [type_probe("rotation", "90-every-type-on-no-background",
                        turned(90, every_type_on_no_background(_grid(90))))]
          + [type_probe("rotation", "%d-pictures" % degrees,
                        turned(degrees, _page_probe("page-of-pictures")))
             for degrees in (90, 270)])
