"""The probes of a project's screen model (packaging.py and
frame.py): each base folder moved to each other screen
model of its series by nxwright's device command, which gives each page the
model's screen size. On T and K, a component of each drawn type on a
picture, laid out to fit the least of the models, 240 by 272; on P and E,
the page's probe of pictures, beside a text, a number, and a button. Then
one model of each series turned. Run them with `tools.tft.probe run model_probes`.

Each compares the whole file, part by part, and one keeps the user code
alone as its fixtures (component_probes.py gives both).
"""
from dataclasses import dataclass
from pathlib import Path

from nxwright.project.screen_models import MODELS
from nxwright.source.device_change import change_device

from tools.tft.probing import page_probes
from nxwright.tft.component_types import SERIES_WRITTEN_AS_P
from tools.tft.probing.component_probes import editor_file, user_code_kept, whole_file
from tools.tft.probing.probe_runner import BASE_MODELS, Probe, ProbeError

# The series these probes cover.
_SERIES = ("T", "K", "P", "E")
FIXTURES = "model"


@dataclass(frozen=True, eq=False)
class ScreenChange:
    """A probe's change: `change`, then the folder moved to the screen model
    named `screen` and turned to `rotation` degrees, each when given, as
    nxwright's device command does. That command gives each page the new
    screen's size, and changes nothing else a page holds. A unit test reads
    all three, to make the pages `change` adds in memory on that screen
    (tests/tft/unit_inputs.py). Raises ProbeError when nxwright's checks then
    refuse the folder. Two changes are equal only if they are the same one,
    as two functions are."""
    change: object
    screen: str = None
    rotation: int = None

    def __call__(self, folder: Path):
        self.change(folder)
        done = change_device(folder, screen=self.screen, rotation=self.rotation)
        if done.refusals:
            where = " ".join(([] if self.screen is None else ["on %s" % self.screen])
                             + ([] if self.rotation is None else ["at %d degrees" % self.rotation]))
            raise ProbeError("%s, nxwright refuses %s" % (where, done.refusals))


def moved(model: str, change, degrees: int = None) -> ScreenChange:
    """Returns a probe's change: `change`, then the folder moved to the
    screen model `model`, and turned to `degrees` when given (ScreenChange)."""
    return ScreenChange(change, model, degrees)


def _in_a_small_grid(number: int) -> dict:
    """Returns the place and size of the component `number` of a grid of 4
    columns, apart from the others: 50 by 50, 4 rows on a screen of 240 by
    272, which every model of T and K holds."""
    return {"x": 5 + 58 * (number % 4), "y": 5 + 60 * (number // 4), "w": 50, "h": 50}


def _contents(series: str):
    """A component of each drawn type on T and K; the page's probe of
    pictures on P and E, whose types are the text, the number, and the
    button."""
    if series in SERIES_WRITTEN_AS_P:
        return next(probe.change for probe in page_probes.PROBES
                    if probe.name == "page-of-pictures")
    return page_probes.every_type_on_a_picture(_in_a_small_grid)


def _probe(series: str, model: str, degrees: int = None) -> Probe:
    name = "model-%s%s" % (model, "" if degrees is None else "-at-%d" % degrees)
    keeps = model == "NX3224T024"
    return Probe(name, series, moved(model, _contents(series), degrees), whole_file,
                 editor_file, FIXTURES if keeps else None, user_code_kept if keeps else None)


PROBES = ([_probe(model.series, model.name) for model in MODELS
           if model.series in _SERIES and model.name != BASE_MODELS[model.series]]
          + [_probe("T", "NX4827T043", 90), _probe("K", "NX3224K028", 270),
             _probe("P", "NX1060P101", 90), _probe("E", "NX4880E043", 90)])
