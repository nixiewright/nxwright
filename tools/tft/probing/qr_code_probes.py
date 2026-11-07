"""The QR code component's probes (component_types/qr_code.py): QR codes on
the T base folder's pages, with other places, sizes, texts, and txt_maxl,
two of them, one among a text, a number, a button, a checkbox, a variable,
and a timer, one before a text, one on a second page, five on a page, and
code in a QR code's events; then a QR code's txt in code; then QR codes of
other colours and margins, and with logos. Run them with `tools.tft.probe run
qr_code_probes`.

Each probe of a QR code compares the whole file, part by part, and keeps
the user code alone as its fixtures (component_probes.py gives both). The
probe of code compares the blocks of page0's Touch Release event alone,
which it keeps as its fixture (statement_probes.py gives both).
"""
from functools import partial

from tools.tft.probing.attribute_probes import with_attributes
from tools.tft.probing.button_probes import button_component
from tools.tft.probing.checkbox_probes import checkbox_component
from tools.tft.probing.component_probes import type_probe, with_components
from tools.tft.probing.number_probes import number_component
from tools.tft.probing.picture_probes import with_pictures
from tools.tft.probing.probe_runner import Probe
from tools.tft.probing.statement_probes import ours_in_event, theirs_in_event
from tools.tft.probing.text_probes import text_component
from tools.tft.probing.timer_probes import timer_component
from tools.tft.probing.variable_probes import variable_component


def qr_code_component(name: str = "qr0", x: int = 10, y: int = 10, w: int = 100, h: int = 100,
                      txt: str = None, txt_maxl: int = None, pic: str = None,
                      **attributes: int) -> str:
    """Returns a QR code component in a page file's form, its txt, its
    txt_maxl, its pic, a picture of the project by its name, and its other
    attributes, such as sta, at their defaults unless given."""
    lines = ['\n[[component]]\nname = "%s"\ntype = "qr-code"\nx = %d\ny = %d\nw = %d\nh = %d\n'
             % (name, x, y, w, h)]
    if txt is not None:
        lines.append('txt = "%s"\n' % txt)
    if txt_maxl is not None:
        lines.append("txt_maxl = %d\n" % txt_maxl)
    if pic is not None:
        lines.append('pic = "%s"\n' % pic)
    lines += ["%s = %d\n" % item for item in attributes.items()]
    return "".join(lines)


_probe = partial(type_probe, "qr-code")

# Two pictures for logos: red, picture 0, and logo, picture 1.
_LOGOS = [("red", (8, 8), (255, 0, 0)), ("logo", (20, 20), (0, 0, 255))]

# The probes keeping fixtures are the fewest that show each part: two QR
# codes on a page, one of another text and txt_maxl; one among a text, a
# number, a button, a checkbox, a variable, and a timer; one on a second
# page, numbered on from the first's; and its txt in code.
PROBES = [
    _probe("one", with_components(qr_code_component())),
    _probe("two", with_components(qr_code_component(),
                                  qr_code_component("qr1", x=150, txt="Hello123", txt_maxl=20)),
           fixtures=True),
    _probe("of-digits", with_components(qr_code_component(txt="0123456789"))),
    _probe("empty", with_components(qr_code_component(txt=""))),
    _probe("txt-maxl-1", with_components(qr_code_component(txt="A", txt_maxl=1))),
    # The most a page takes: past 154, a QR code needs more temporary memory
    # than a page of NX4832T035 leaves, which nxwright's build refuses.
    _probe("txt-maxl-154", with_components(qr_code_component(txt="Yo", txt_maxl=154))),
    _probe("full", with_components(qr_code_component(txt="Press", txt_maxl=5))),
    # Its drawing gives its width alone.
    _probe("taller-than-wide", with_components(qr_code_component(w=80, h=120))),
    _probe("small", with_components(qr_code_component(x=0, y=0, w=40, h=40))),
    _probe("large", with_components(qr_code_component(x=0, y=0, w=320, h=320))),
    _probe("at-the-edges", with_components(qr_code_component(x=220, y=380))),
    _probe("among-the-types-matched",
           with_components(text_component(), qr_code_component(y=50), number_component(y=160),
                           button_component(y=200), checkbox_component(y=260),
                           variable_component(), timer_component()), fixtures=True),
    _probe("before-a-text", with_components(qr_code_component(), text_component(y=120))),
    _probe("on-second-page", with_components(qr_code_component(), page="page1"),
           fixtures=True),
    _probe("five-on-a-page", with_components(*[qr_code_component("qr%d" % number,
                                                                 x=10 + 60 * number, w=50,
                                                                 h=50)
                                               for number in range(5)])),
    _probe("event-code", with_components(
        qr_code_component(), code="on qr0.down:\n  sys0=1\non qr0.up:\n  sys1=2\n")),
    _probe("named-with-14", with_components(qr_code_component("QRco_name_of14"))),
    # A QR code's txt set to a text, as the serial commands' operand, and a
    # QR code as the component of the screen's commands.
    Probe("qr-code-txt-in-code", "T", with_attributes(
        ['qr0.txt="Hello"', 'qr1.txt="Abc12"', "print qr0.txt", "vis qr0,0", "tsw qr0,0",
         "click qr1,1", "ref qr1"],
        [qr_code_component(), qr_code_component("qr1", x=150)]),
          ours_in_event, theirs_in_event, "qr-code"),
    # Its colours and margin away from their defaults.
    _probe("colours-and-margin", with_components(
        qr_code_component(bco=31, pco=2016, dis=20), qr_code_component("qr1", y=150, dis=0, bco=0,
                                                                       pco=65535),
        qr_code_component("qr2", x=150, y=150, dis=255)), fixtures=True),
    # Logos, of sta 1: the project's second picture and its first, which
    # give a QR code one entry more.
    _probe("logos", with_pictures(
        _LOGOS, qr_code_component(sta=1, pic="logo"),
        qr_code_component("qr1", y=150, sta=1, pic="red")), fixtures=True),
    # A pic without a logo, which it does not keep, and a logo without a
    # picture.
    _probe("pic-without-a-logo", with_pictures(_LOGOS, qr_code_component(sta=0, pic="logo"))),
    _probe("logo-without-a-picture", with_components(qr_code_component(sta=1))),
]
