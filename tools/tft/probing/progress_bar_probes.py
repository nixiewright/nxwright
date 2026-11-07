"""The progress bar component's probes (component_types/progress_bar.py):
progress bars on the T base folder's page, with other places, sizes, and
vals, two of them, one among a text, a number, a button, and a variable,
one before a timer, one on a second page, and code in a progress bar's
events, then a progress bar's val in code; then progress bars of other
colours and corners, filled upward, and drawn in pictures, and their
pictures in code. Run them with `tools.tft.probe run progress_bar_probes`.

Each probe of a progress bar compares the whole file, part by part, and
keeps the user code alone as its fixtures (component_probes.py gives both).
The probe of code compares the blocks of page0's Touch Release event alone,
which it keeps as its fixture (statement_probes.py gives both).
"""
from functools import partial

from tools.tft.probing.attribute_probes import with_attributes
from tools.tft.probing.button_probes import button_component
from tools.tft.probing.component_probes import type_probe, with_components
from tools.tft.probing.number_probes import number_component
from tools.tft.probing.picture_probes import with_pictures, with_pictures_and_code
from tools.tft.probing.probe_runner import Probe
from tools.tft.probing.statement_probes import ours_in_event, theirs_in_event
from tools.tft.probing.text_probes import text_component
from tools.tft.probing.timer_probes import timer_component
from tools.tft.probing.variable_probes import variable_component


def progress_bar_component(name: str = "j0", x: int = 10, y: int = 10, w: int = 128,
                           h: int = 30, val: int = 50, pictures: dict = None,
                           **attributes: int) -> str:
    """Returns a progress bar component in a page file's form, its
    `pictures`, as {"bpic": the name of a picture of the project}, and its
    other attributes, such as dez, at their defaults unless given."""
    return ('\n[[component]]\nname = "%s"\ntype = "progress-bar"\nx = %d\ny = %d\nw = %d\n'
            'h = %d\nval = %d\n' % (name, x, y, w, h, val)
            + "".join('%s = "%s"\n' % item for item in (pictures or {}).items())
            + "".join("%s = %d\n" % item for item in attributes.items()))


# Two pictures to draw a progress bar in: bg and bg2, pictures 0 and 1, as
# large as the screen, so that a part of either fits any progress bar.
PICTURES = [("bg", (320, 480), (0, 0, 255)), ("bg2", (320, 480), (0, 255, 0))]


# The components and lines of the probes the tests take as inputs, so that
# the tests and the probes share them.
OTHER_LOOKS = (progress_bar_component(val=30, bco=31, pco=63488, dis=0),
               progress_bar_component("j1", y=60, val=70, bco=0, pco=65535, dis=100))
UPWARD = (progress_bar_component(x=20, y=40, w=40, h=100, val=30, dez=1),
          progress_bar_component("j1", x=100, y=40, w=30, h=128, val=73, dez=1, pco=63488))
OF_PICTURES = (progress_bar_component(x=20, y=40, w=90, h=50, val=30, sta=1, bco=31, pco=63488,
                                      pictures={"bpic": "bg", "ppic": "bg2"}),
               progress_bar_component("j1", x=150, y=40, w=40, h=100, val=73, sta=1, dez=1,
                                      pictures={"bpic": "bg2", "ppic": "bg"}))
VAL_IN_CODE = ["j0.val=5", "sys0=j0.val", "j1.val=j0.val+sys0", "j0.val++", "j1.val--",
               "if(j0.val<50)", "{", "j1.val=100", "}", "while(j1.val>0)", "{", "j1.val-=10",
               "}", "for(j0.val=0;j0.val<100;j0.val+=25)", "{", "sys0++", "}", "get j0.val",
               "print j1.val"]
VAL_IN_CODE_COMPONENTS = (progress_bar_component(), progress_bar_component("j1", y=60))
PICTURES_IN_CODE = ["sys0=j0.bpic", "j0.ppic=1", "j0.bpic=j0.ppic", "j0.val=5",
                    "sys0=j0.dez+j1.dis", "j1.dis=10", "j1.pco=j0.val"]
PICTURES_IN_CODE_COMPONENTS = (
    progress_bar_component(sta=1, pictures={"bpic": "bg", "ppic": "bg2"}),
    progress_bar_component("j1", y=60))

_probe = partial(type_probe, "progress-bar")

# The probes keeping fixtures are the fewest that show each part: two
# progress bars on a page; one among a text, a number, a button, and a
# variable; one on a second page, numbered on from the first's; and its val
# in code.
PROBES = [
    _probe("one", with_components(progress_bar_component())),
    _probe("two", with_components(progress_bar_component(),
                                  progress_bar_component("j1", y=60, val=20)), fixtures=True),
    _probe("among-the-types-matched",
           with_components(text_component(y=60), progress_bar_component(),
                           number_component(y=100), button_component(y=140),
                           variable_component()), fixtures=True),
    # A timer after a progress bar: its load blocks, in its page's load
    # section, give a place after the progress bar's drawing. A timer is
    # matched on T alone, so this probe is not run on K.
    _probe("before-a-timer", with_components(
        progress_bar_component(), timer_component(),
        code="on page0.load:\n  sys2=1\non tm0.timer:\n  sys0++\n")),
    _probe("of-0", with_components(progress_bar_component(val=0))),
    _probe("of-73", with_components(progress_bar_component(val=73))),
    _probe("of-100", with_components(progress_bar_component(val=100))),
    _probe("of-2-by-2", with_components(progress_bar_component(x=0, y=0, w=2, h=2))),
    _probe("at-the-edges", with_components(progress_bar_component(x=192, y=450))),
    _probe("of-the-screen", with_components(progress_bar_component(x=0, y=0, w=320, h=480))),
    _probe("named-with-14", with_components(progress_bar_component("Prog_name_of14"))),
    _probe("event-code", with_components(
        progress_bar_component(), code="on j0.down:\n  sys0=1\non j0.up:\n  sys1=2\n")),
    _probe("on-second-page", with_components(progress_bar_component(), page="page1"),
           fixtures=True),
    # A progress bar's val set, stepped, read, compared in if, while, and
    # for, and as the serial commands' operand.
    Probe("progress-bar-val-in-code", "T",
          with_attributes(VAL_IN_CODE, list(VAL_IN_CODE_COMPONENTS)),
          ours_in_event, theirs_in_event, "progress-bar"),
    # Its colours and corners away from their defaults, and at their ends.
    _probe("of-other-looks", with_components(*OTHER_LOOKS), fixtures=True),
    # Filled upward, at two places and sizes.
    _probe("upward", with_components(*UPWARD), fixtures=True),
    # Drawn in pictures, across and upward, the first with colours away
    # from their defaults, which it does not keep.
    _probe("of-pictures", with_pictures(PICTURES, *OF_PICTURES), fixtures=True),
    # Drawn in pictures, but none given, and its dis away from its default,
    # which it does not keep; and drawn in colours, with pictures given,
    # which it does not keep.
    _probe("of-no-pictures-and-of-colours-with-pictures", with_pictures(
        PICTURES, progress_bar_component(sta=1, dis=50),
        progress_bar_component("j1", y=60, pictures={"bpic": "bg", "ppic": "bg2"}))),
    # Its pictures in code, read and set, and its val and dis, whose entries
    # are one down drawn in pictures.
    Probe("progress-bar-pictures-in-code", "T",
          with_pictures_and_code(PICTURES, PICTURES_IN_CODE, *PICTURES_IN_CODE_COMPONENTS),
          ours_in_event, theirs_in_event, "progress-bar"),
]
