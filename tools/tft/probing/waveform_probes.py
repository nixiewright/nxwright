"""The waveform component's probes (component_types/waveform.py): waveforms
on the T base folder's pages, with other places and sizes, two of them, one
among a text, a number, a button, a slider, a QR code, a variable, and a
timer, one before a text, one on a second page, five on a page, and code in
a waveform's events; then a waveform's id in code; then waveforms of 1 to 4
channels, of other colours, grids, scales, and directions; then waveforms
with a picture or a crop behind them, and of the values the Nextion
Editor's panel never shows, and their pic and picc in code. Run them with
`tools.tft.probe run waveform_probes`.

Each probe of a waveform compares the whole file, part by part, and keeps
the user code alone as its fixtures (component_probes.py gives both). The
probe of code compares the blocks of page0's Touch Release event alone,
which it keeps as its fixture (statement_probes.py gives both).
"""
from functools import partial

from tools.tft.probing.attribute_probes import with_attributes
from tools.tft.probing.button_probes import button_component
from tools.tft.probing.component_probes import type_probe, with_components
from tools.tft.probing.number_probes import number_component
from tools.tft.probing.picture_probes import with_pictures, with_pictures_and_code
from tools.tft.probing.probe_runner import Probe
from tools.tft.probing.qr_code_probes import qr_code_component
from tools.tft.probing.slider_probes import slider_component
from tools.tft.probing.statement_probes import ours_in_event, theirs_in_event
from tools.tft.probing.text_probes import text_component
from tools.tft.probing.timer_probes import timer_component
from tools.tft.probing.variable_probes import variable_component


def waveform_component(name: str = "s0", x: int = 10, y: int = 10, w: int = 200,
                       h: int = 100, pic: str = None, picc: str = None,
                       **attributes: int) -> str:
    """Returns a waveform component in a page file's form, its pic and its
    picc, pictures of the project by their names, and its other attributes,
    such as ch, at their defaults unless given."""
    pictures = "".join('%s = "%s"\n' % (attribute, picture)
                       for attribute, picture in (("pic", pic), ("picc", picc))
                       if picture is not None)
    return ('\n[[component]]\nname = "%s"\ntype = "waveform"\nx = %d\ny = %d\nw = %d\nh = %d\n'
            % (name, x, y, w, h) + pictures
            + "".join("%s = %d\n" % item for item in attributes.items()))


def _small(name: str, y: int, **attributes: int) -> str:
    """Returns a waveform of 100 by 60 at the screen's left edge, of
    `attributes`."""
    return waveform_component(name, x=0, y=y, w=100, h=60, **attributes)


# Two pictures to put behind a waveform: red, picture 0, and bg, picture 1,
# as large as the screen, so that a crop of it fills any waveform.
_PICTURES = [("red", (8, 4), (255, 0, 0)), ("bg", (320, 480), (0, 0, 255))]


_probe = partial(type_probe, "waveform")

# The probes keeping fixtures are the fewest that show each part: two
# waveforms on a page, of other widths, so of other buffers; one among a
# text, a number, a button, a slider, which adds to the load section too, a
# QR code, whose txt lies before the buffers, a variable, and a timer; and
# one on a second page, numbered on from the first's.
PROBES = [
    _probe("one", with_components(waveform_component())),
    _probe("two", with_components(waveform_component(),
                                  waveform_component("s1", y=150, w=100, h=100)),
           fixtures=True),
    _probe("narrow", with_components(waveform_component(x=0, y=0, w=2, h=20))),
    _probe("short", with_components(waveform_component(h=2))),
    _probe("full-width", with_components(waveform_component(x=0, y=0, w=320, h=480))),
    # Its default size, 200 by 200, at the screen's right and bottom edges.
    _probe("at-the-edges", with_components(waveform_component(x=120, y=280, h=200))),
    _probe("among-the-types-matched",
           with_components(text_component(), waveform_component(y=50), number_component(y=160),
                           button_component(y=200), slider_component(y=260),
                           qr_code_component(x=220, y=300, txt="ab"), variable_component(),
                           timer_component()), fixtures=True),
    _probe("before-a-text", with_components(waveform_component(), text_component(y=120))),
    _probe("on-second-page", with_components(waveform_component(), page="page1"), fixtures=True),
    _probe("five-on-a-page", with_components(*[
        waveform_component("s%d" % number, y=10 + 90 * number, w=60 + 61 * number, h=80)
        for number in range(5)])),
    _probe("event-code", with_components(
        waveform_component(), code="on s0.down:\n  sys0=1\non s0.up:\n  sys1=2\n")),
    _probe("named-with-14", with_components(waveform_component("Wave_name_of14"))),
    # A waveform's id read, in a sum, compared in if, while, and for, and a
    # waveform as the component of the screen's commands. Code cannot set
    # its id: the Nextion Editor refuses that.
    Probe("waveform-id-in-code", "T", with_attributes(
        ["sys0=s0.id", "sys1=s0.id+sys0", "if(s0.id==1)", "{", "sys0=2", "}",
         "while(sys0<s1.id)", "{", "sys0++", "}", "for(sys0=0;sys0<s0.id;sys0++)", "{",
         "sys1++", "}", "vis s0,0", "tsw s0,0", "click s1,1", "ref s1"],
        [waveform_component(), waveform_component("s1", y=150)]),
          ours_in_event, theirs_in_event, "waveform"),
    # Its channels: one of each ch from 1 to 4, whose entries, record, and
    # buffer grow with it.
    _probe("channels", with_components(*[_small("s%d" % number, 70 * number, ch=number + 1)
                                         for number in range(4)]), fixtures=True),
    # Its colours, grid, scale, and direction away from their defaults.
    _probe("attributes", with_components(
        _small("s0", 0, bco=31, gdc=2016, gdw=0, gdh=255, dis=10, dir=2, pco0=0),
        _small("s1", 70, dis=1000, dir=1, ch=4, pco1=1, pco2=2, pco3=3),
        _small("s2", 140, ch=2, pco0=65535, pco1=4660, bco=65535)), fixtures=True),
    # Colours of channels it does not have, which it does not keep.
    _probe("colours-past-its-channels", with_components(
        _small("s0", 0, ch=2, pco2=1, pco3=4660), _small("s1", 70, ch=1, pco1=7))),
    _probe("four-channels-wide", with_components(waveform_component(x=0, w=320, ch=4))),
    # What lies behind it: a picture, at a sta of 2, and a crop of one, at a
    # sta of 0, each with its colour and grid away from their defaults,
    # which it does not keep; the second of 4 channels.
    _probe("of-a-picture-and-a-crop", with_pictures(
        _PICTURES, _small("s0", 0, sta=2, pic="bg", bco=31, gdc=2016, gdw=20, gdh=30),
        _small("s1", 70, sta=0, picc="bg", ch=4, pco1=1, pco2=2, pco3=3, dis=200)),
        fixtures=True),
    # A picture behind it, but none given; and its colour behind it, with a
    # picture and a crop given, which it does not keep.
    _probe("of-no-picture-and-of-a-colour-with-pictures", with_pictures(
        _PICTURES, _small("s0", 0, sta=2), _small("s1", 70, pic="red", picc="bg"))),
    # The values the Nextion Editor's panel never shows, at their ends, and
    # apart from each other.
    _probe("of-hidden-values", with_components(
        _small("s0", 0, objWid=65535, objHig=32768, inittrue=255),
        _small("s1", 70, objWid=5, objHig=7, inittrue=1)), fixtures=True),
    # A molloc and a molloc_s, which every type has, and which change
    # nothing in the file.
    _probe("of-molloc", with_components(waveform_component(molloc=1000, molloc_s=2000))),
    # A waveform's pic and picc in code, and its colours and dis, which are
    # numbered three down with a picture or a crop behind it.
    Probe("waveform-pic-and-picc-in-code", "T", with_pictures_and_code(
        _PICTURES,
        ["sys0=s0.pic", "s0.pic=1", "sys0=s1.picc", "s1.picc=0", "sys0=s0.pco0+s0.dis",
         "s1.pco3=5", "add s0.id,0,s1.dis"],
        _small("s0", 0, sta=2, pic="bg"), _small("s1", 70, sta=0, picc="bg", ch=4)),
          ours_in_event, theirs_in_event, "waveform"),
]
