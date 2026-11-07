"""The probes of a page's place and size away from its screen's
(frame.py, ResearchNotes/tft/user-code-frame.md): page0, with a text, at
another x and y, at another w and h, at the highest x, y, w, and h its
entries give, 6000 and 2000, and at a w and h of 2, the least the Nextion
Editor takes ("Width can not be less than 2"), as nxwright's build checks.
The Nextion Editor compiles each at its screen's place and size. Each is built on T, K, P, E,
and F, and compares the whole file. Run them with
`tools.tft.probe run page_place_probes`.
"""
from dataclasses import dataclass
from pathlib import Path
import re

from tools.tft.probing.component_probes import editor_file, user_code_kept, whole_file, with_components
from tools.tft.probing.probe_runner import Probe
from tools.tft.probing.text_probes import text_component

FIXTURES = "page-place"

# Each probe's name, and page0's place and size it gives, by attribute.
_PLACES = {
    "at-another-place": {"x": 10, "y": 5},
    "of-another-size": {"w": 200, "h": 240},
    "at-the-entries-highest": {"x": 6000, "y": 6000, "w": 2000, "h": 2000},
    "of-the-least-size": {"w": 2, "h": 2},
}
# The probes that keep the user code as fixtures, by name.
_KEEPING = {"t-page-of-another-size", "p-page-of-another-size"}


def placed_page_text(text: str, values) -> str:
    """Returns the text of a page file `text` with each attribute of `values`,
    pairs of a name and a number, such as ("w", 200), given that number in
    the page's own table, where the file gives it first."""
    for name, value in values:
        text = re.sub(r"(?m)^%s = \d+$" % name, "%s = %d" % (name, value), text, count=1)
    return text


@dataclass(frozen=True, eq=False)
class PlacedChange:
    """A probe's change that gives page0 `page_values`, pairs of an
    attribute of its place or size and a number, in its page file
    (placed_page_text), then puts `components` on it, as a
    component_probes.ComponentsChange does. A unit test reads both, to make
    the same page in memory (tests/tft/unit_inputs.py). Two changes are equal
    only if they are the same one, as two functions are."""
    page_values: tuple
    components: tuple
    page = "page0"
    code = ""

    def __call__(self, folder: Path):
        page_file = folder / "pages" / "page0.page.toml"
        page_file.write_text(placed_page_text(page_file.read_text(encoding="utf-8"),
                                              self.page_values), encoding="utf-8")
        with_components(*self.components)(folder)


def _placed(attributes: dict) -> PlacedChange:
    """Returns a probe's change: gives page0 `attributes`, its place and size
    in its page file, and a text (PlacedChange)."""
    return PlacedChange(tuple(attributes.items()), (text_component(),))


PROBES = [Probe("%s-page-%s" % (series.lower(), name), series, _placed(attributes), whole_file,
                editor_file,
                FIXTURES if "%s-page-%s" % (series.lower(), name) in _KEEPING else None,
                user_code_kept)
          for series in "TKPEF" for name, attributes in _PLACES.items()]
