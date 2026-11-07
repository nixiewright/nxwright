"""The probes of labels and goto (instructions/goto_statement.py and
label_numbers.py): code on the T base folder, in program.s and in events of
pages and components, beside timers, a button, a slider, and a scrolling
text, whose "S " blocks share the labels' numbers. Run them with
`tools.tft.probe run goto_probes`.

Each compares the whole file, part by part, compiled as the compile command
compiles it, and keeps the user code as the statement encoder gives it as
its fixtures.
"""
from pathlib import Path

from nxwright.tft import frame
from tools.tft.probing.button_probes import button_component
from tools.tft.probing.component_probes import editor_file, on_pages, whole_file, with_components
from tools.tft.probing.frame_probes import parts_and_pieces
from tools.tft.probing.probe_runner import Parts, Probe
from nxwright.tft.project import Project
from tools.tft.probing.scrolling_text_probes import scrolling_text_component
from tools.tft.probing.slider_probes import slider_component
from tools.tft.probing.statement_probes import ProgramChange
from tools.tft.probing.text_probes import text_component
from tools.tft.probing.timer_probes import timer_component

FIXTURES = "goto"


def _code(events: dict) -> str:
    """Returns events' code in a page file's form, {event: lines}, an event
    such as page0.up or tm0.timer."""
    return "".join("on %s:\n%s" % (event, "".join("  %s\n" % line for line in lines))
                   for event, lines in events.items())


def project_with_code(page0: list, events0: dict, program: list = (), page1: list = None,
                      events1: dict = None):
    """Returns a probe's change: program.s's `program` lines, before its
    page 0; page0's components `page0` and their events' code `events0`; and
    a second page, page1, of `page1` and `events1`, if given. Its code is
    strict Nextion syntax. A unit test reads what it adds, to make the same
    pages in memory (ProgramChange, PagesChange)."""
    first = ProgramChange(tuple(program), (), tuple(page0), _code(events0))
    if page1 is None:
        return first
    return on_pages(first, with_components(*page1, page="page1", code=_code(events1 or {})))


def _user_code(project: Path) -> Parts:
    """Returns the user code of `project`, part by part, through the
    statement encoder, with where each of its pieces lies: a probe's kept."""
    return parts_and_pieces(*frame.laid_out(Project.from_file(project)))


def _probe(name: str, change) -> Probe:
    return Probe("goto-" + name, "T", change, whole_file, editor_file, FIXTURES, _user_code)


PROBES = [
    # A label a goto jumps back to from an if's body, a goto forward past a
    # line, and a label at the event's end, which its goto jumps past.
    _probe("in-an-event", project_with_code([text_component()], {"page0.up": [
        "sys0=0", "loop:", "sys0++", "if(sys0<5)", "{", "goto loop", "}", "goto done",
        "sys1=1", "done:", "sys2=2", "goto end", "sys2=3", "end:"]})),
    # Labels first, then their gotos, a label after them, and names of
    # digits and _, of 30 characters among them.
    _probe("labels-then-gotos", project_with_code([text_component()], {"page0.up": [
        "a:", "sys0=1", "b:", "sys0=2", "_x9:", "goto a", "goto b", "goto _x9", "loop:",
        "goto loop", "label_of_thirty_characters_ab:", "goto label_of_thirty_characters_ab"]})),
    # Labels and gotos in program.s, then in page0's down, up, and unload
    # events, a while's and a for's among them: one counter numbers them
    # all.
    _probe("across-program-and-events", project_with_code([text_component()], {
        "page0.down": ["d1:", "goto d1x", "d1x:"],
        "page0.up": ["while(sys0<3)", "{", "sys0++", "}", "u1:", "for(sys1=0;sys1<2;sys1++)",
                     "{", "goto u2", "}", "u2:", "goto u1"],
        "page0.unload": ["x1:", "goto x1"]},
        program=["goto p2", "sys0=1", "p2:", "sys1=2"])),
    # Beside a timer and a button: the timer's first number, the page's
    # label, the timer's "S " block and its event's labels, then the
    # button's two events' labels.
    _probe("beside-a-timer-and-a-button", project_with_code(
        [text_component(), timer_component(), button_component(y=300)],
        {"page0.up": ["u1:"], "tm0.timer": ["t1:", "goto t1"],
         "b0.down": ["b1:", "goto b1"], "b0.up": ["b2:"]})),
    # In page0's load and loadend events, numbered before its up event, and
    # on a second page, each beside a timer.
    _probe("in-load-loadend-and-a-second-page", project_with_code(
        [text_component(), timer_component()],
        {"page0.load": ["l1:"], "page0.up": ["u1:", "goto u1"], "page0.loadend": ["e1:"]},
        page1=[text_component("t5"), timer_component("tm1")],
        events1={"page1.up": ["p1:"]})),
    # Beside a slider: its three events' labels, in the order of its type's
    # EVENTS, down, up, and slide.
    _probe("beside-a-slider", project_with_code([text_component(), slider_component(y=100)], {
        "page0.up": ["u1:"], "h0.slide": ["s1:", "goto s1"], "h0.down": ["d1:"],
        "h0.up": ["u2:", "goto u2"]})),
    # Beside a scrolling text and a timer: the scrolling text's three first
    # numbers, then its second before its up event's labels.
    _probe("beside-a-scrolling-text", project_with_code(
        [text_component(), scrolling_text_component(y=400), timer_component()],
        {"page0.up": ["u1:"], "g0.up": ["g1:", "goto g1"], "tm0.timer": ["t1:"]})),
]
