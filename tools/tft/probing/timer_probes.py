"""The timer component's probes (component_types/timer.py): timers on the T
base folder's pages, with other tims and ens, two, three, and twelve of
them, one among the types already matched, one before a text, timers on two
pages, and code in a timer's event and in its page's load event; then a
timer's tim and en in code. Run them with `tools.tft.probe run timer_probes`.

Each probe of a timer compares the whole file, part by part, and keeps the
user code alone as its fixtures (component_probes.py gives both). Each
probe of code compares the blocks of page0's Touch Release event alone,
which it keeps as its fixture (statement_probes.py gives both).
"""
from functools import partial

from tools.tft.probing.attribute_probes import with_attributes
from tools.tft.probing.button_probes import button_component
from tools.tft.probing.component_probes import PagesChange, on_pages, type_probe, with_components
from tools.tft.probing.number_probes import number_component
from tools.tft.probing.probe_runner import Probe
from tools.tft.probing.statement_probes import ours_in_event, theirs_in_event
from tools.tft.probing.text_probes import text_component
from tools.tft.probing.variable_probes import variable_component


def timer_component(name: str = "tm0", tim: int = None, en: int = None) -> str:
    """Returns a timer component in a page file's form, its tim and en at
    their defaults unless given."""
    lines = ['\n[[component]]\nname = "%s"\ntype = "timer"\n' % name]
    lines += ["%s = %d\n" % (attribute, value)
              for attribute, value in (("tim", tim), ("en", en)) if value is not None]
    return "".join(lines)


def _on_pages(*pages: list) -> PagesChange:
    """Returns a change that puts each list of components of `pages` on a
    page of its own: the first on page0, the others on new pages page1,
    page2, and so on (component_probes.PagesChange)."""
    return on_pages(*(with_components(*components, page="page%d" % number)
                      for number, components in enumerate(pages)))


_probe = partial(type_probe, "timer")


def _code_probe(name: str, lines: list) -> Probe:
    """Returns a probe of `lines` in page0's Touch Release event, beside tm0
    and tm1."""
    change = with_attributes(lines, [timer_component(), timer_component("tm1", tim=1000)])
    return Probe("timer-" + name, "T", change, ours_in_event, theirs_in_event, "timer")


# The probes keeping fixtures are the fewest that show each part: two timers
# on a page; a timer among a text, a number, a button, and a variable, the
# types already matched; timers on two pages, whose "S " numbers count the
# first page's; and code in a timer's event and its page's load event.
PROBES = [
    _probe("one", with_components(timer_component())),
    _probe("two", with_components(timer_component(), timer_component("tm1")), fixtures=True),
    _probe("of-1000-off", with_components(timer_component(tim=1000, en=0))),
    _probe("of-50", with_components(timer_component(tim=50))),
    _probe("of-65534", with_components(timer_component(tim=65534))),
    _probe("among-a-text-a-number-a-button-and-a-variable",
           with_components(text_component(), timer_component(), number_component(y=60),
                           button_component(y=110), variable_component()), fixtures=True),
    _probe("before-a-text", with_components(timer_component(), text_component())),
    _probe("three-on-a-page", with_components(*[timer_component("tm%d" % number)
                                                for number in range(3)])),
    # The Nextion Editor takes at most 12 timers and scrolling texts on a
    # page.
    _probe("twelve-on-a-page", with_components(*[timer_component("tm%d" % number)
                                                 for number in range(12)])),
    _probe("on-two-pages", _on_pages([timer_component(), timer_component("tm1")],
                                     [timer_component(tim=100)]), fixtures=True),
    # Timers on three pages, so that the "S " numbers of page2's count the
    # timers of two pages before it.
    _probe("on-three-pages", _on_pages([timer_component()],
                                       [timer_component(), timer_component("tm1")],
                                       [timer_component(), timer_component("tm1")])),
    _probe("event-code", with_components(
        timer_component(), timer_component("tm1", tim=50),
        code="on page0.load:\n  sys2=1\non tm0.timer:\n  sys0++\n  sys1=2\n"
             "on tm1.timer:\n  sys1++\n"), fixtures=True),
    _probe("named-with-14", with_components(timer_component("Time_name_of14"))),
    # A timer's tim and en set, stepped, read, and compared, and a timer as
    # the component of the screen's commands. The serial commands take a
    # txt or a val alone, so not a tim.
    _code_probe("tim-and-en-in-code", [
        "tm0.en=0", "tm0.tim=100", "sys0=tm0.tim", "tm1.tim+=50", "tm1.en=tm0.en",
        "if(tm0.en==1)", "{", "tm1.tim=tm0.tim*2", "}", "while(tm1.tim<1000)", "{",
        "tm1.tim++", "}", "vis tm0,0", "tsw tm0,0", "click tm1,1", "ref tm1"]),
]
