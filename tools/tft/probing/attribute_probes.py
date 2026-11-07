"""The probes of components' attributes in code: a text t0 and numbers n0
and n1 on the T base folder's page0, in strict Nextion syntax, with lines
naming their attributes in page0's Touch Release event. Each compares the
blocks the statement encoder gives the event's lines with those the Nextion
Editor wrote, and keeps them as one fixture, as the statement encoder's
probes do (statement_probes.py). The last names the page's own attributes
on a page with an effect, in nxlang, without the text and the numbers.

Run them with `tools.tft.probe run attribute_probes`.
"""
from dataclasses import dataclass
from pathlib import Path

from tools.tft.probing.component_probes import page_attribute_lines, with_components
from tools.tft.probing.number_probes import number_component
from tools.tft.probing.probe_runner import Probe
from tools.tft.probing.statement_probes import (ours_in_event, program_lines, theirs_in_event,
                                            touch_release_code)
from tools.tft.probing.text_probes import text_component

_FIXTURES = "attributes"


@dataclass(frozen=True, eq=False)
class AttributesChange:
    """A probe's change that puts `components`, each in a page file's form, on
    page0, and gives page0's Touch Release event `lines`, in strict Nextion
    syntax. A unit test reads what it adds, as it reads a
    component_probes.ComponentsChange's, to make the same page in memory
    (tests/tft/unit_inputs.py), its code strict. Two changes are equal only if
    they are the same one, as two functions are."""
    lines: tuple
    components: tuple
    # The page it puts the components on, named as a ComponentsChange names
    # it. Its code is strict Nextion syntax.
    page = "page0"
    strict = True

    @property
    def code(self) -> str:
        """Returns page0's event code: `lines` in its Touch Release event."""
        return touch_release_code(self.lines)

    def __call__(self, folder: Path):
        program_lines([])(folder)
        with_components(*self.components, code=self.code)(folder)


def with_attributes(lines: list, components: list = None) -> AttributesChange:
    """Returns a probe's change: puts `components`, in a page file's form, on
    page0, or else t0, n0, and n1, and gives page0's Touch Release event
    `lines` (AttributesChange)."""
    if components is None:
        components = [text_component(), number_component(y=60), number_component("n1", y=110)]
    return AttributesChange(tuple(lines), tuple(components))


def _probe(name: str, lines: list) -> Probe:
    return Probe(name, "T", with_attributes(lines), ours_in_event, theirs_in_event, _FIXTURES)


PROBES = [
    # A number's val set, stepped, and read, beside a text's txt set.
    _probe("attributes-lines", [
        "n0.val=5", "sys0=n0.val", "n1.val=n0.val+sys0", "n0.val++", "n1.val--",
        "n0.val+=1000", "n1.val-=n0.val", 't0.txt="Yo"', "n0.val=-2147483648"]),
    # A number's val in the conditions of if, else if, while, and for, on
    # either side, and as a for's start and step.
    _probe("attributes-conditions", [
        "if(n0.val==1)", "{", "n1.val=2", "}else if(sys0<n1.val&&n0.val!=3)", "{", "n1.val=3",
        "}",
        "while(n0.val<3)", "{", "n0.val++", "}",
        "for(n1.val=0;n1.val<n0.val||n1.val>=1000;n1.val++)", "{", "sys0++", "}"]),
    # The page's own attributes in its own code, read, set, and as a
    # command's operand: each its entry among the page's own.
    _probe("attributes-of-the-page", [
        "sys0=page0.bco", "sys0=page0.sta", "sys0=page0.x", "sys0=page0.y", "sys0=page0.w",
        "sys0=page0.h", "sys0=page0.vscope", "sys0=page0.id", "sys0=page0.endx",
        "sys0=page0.endy", "page0.bco=5", "page0.bco+=1", "cls page0.bco"]),
    # The serial buffer, u[i], read, set, and in a condition, and usize.
    _probe("attributes-serial-buffer", [
        "sys0=u[0]", "sys0=u[sys1]", "sys1=usize", "u[0]=5", "u[sys0]+=1", "if(u[1]==0x65)",
        "{", "sys0=1", "}"]),
    # The page's effect and swipe targets in its own code, read, set, and
    # stepped. Code cannot change an effect on T, K, and F.
    _probe("attributes-page-effect-and-swipes", [
        "sys0=page0.effect", "sys0=page0.up", "sys0=page0.down", "sys0=page0.left",
        "sys0=page0.right", "page0.up=1", "page0.down=2", "page0.left+=3", "page0.right=4"]),
    # The same on a page with an effect, which moves its swipe targets and its
    # sta two on, and gives it a first and a time to read.
    Probe("attributes-page-with-an-effect", "T", with_components(
        code="on page0.up:\n  sys0=page0.effect\n  sys0=page0.first\n  sys0=page0.time\n"
        "  sys0=page0.up\n  sys0=page0.right\n  sys0=page0.sta\n  page0.down=2\n"
        "  page0.left+=3\n", attributes=page_attribute_lines(effect=1)),
        ours_in_event, theirs_in_event, _FIXTURES),
]
