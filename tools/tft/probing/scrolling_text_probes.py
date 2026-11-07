"""The scrolling text component's probes (component_types/scrolling_text.py):
scrolling texts on the T base folder's pages, at their defaults but for
their place, size, and txt: one, two, one among a text, a number, a button,
and a timer, one on a second page, with timers before and after, with a
timer on another page, twelve, and code in a scrolling text's events; then
scrolling texts with the attributes their memory alone gives, such as their
dir; then a scrolling text's txt, tim, and en in code; then scrolling texts
of each style, with a picture or a crop behind them, and in a second font,
and their borders and pictures in code. Run them with
`tools.tft.probe run scrolling_text_probes`.

Each probe of a scrolling text compares the whole file, part by part, and
keeps the user code alone as its fixtures (component_probes.py gives both).
The probe of code compares the blocks of page0's Touch Release event alone,
which it keeps as its fixture (statement_probes.py gives both).
"""
from functools import partial

from tools.tft.probing.attribute_probes import with_attributes
from tools.tft.probing.button_probes import button_component
from tools.tft.probing.component_probes import (PagesChange, on_pages, type_probe, with_components,
                                            with_the_first_in_a_second_font)
from tools.tft.probing.number_probes import number_component
from tools.tft.probing.picture_probes import (SCREEN_PICTURES, with_pictures,
                                          with_screen_pictures_and_code)
from tools.tft.probing.probe_runner import Probe
from tools.tft.probing.qr_code_probes import qr_code_component
from tools.tft.probing.statement_probes import ours_in_event, theirs_in_event
from tools.tft.probing.text_probes import text_component
from tools.tft.probing.timer_probes import timer_component


def scrolling_text_component(name: str = "g0", x: int = 10, y: int = 10, w: int = 240,
                             h: int = 30, txt: str = "newtxt", txt_maxl: int = 10,
                             pictures: dict = None, **attributes: int) -> str:
    """Returns a scrolling text component in a page file's form, in the base
    folder's font, its `pictures`, as {"pic": the name of a picture of the
    project}, and its other attributes, such as dir, at their defaults
    unless given."""
    return ('\n[[component]]\nname = "%s"\ntype = "scrolling-text"\nx = %d\ny = %d\nw = %d\n'
            'h = %d\nfont = "NotoSans24"\ntxt = "%s"\ntxt_maxl = %d\n'
            % (name, x, y, w, h, txt, txt_maxl)
            + "".join('%s = "%s"\n' % item for item in (pictures or {}).items())
            + "".join("%s = %d\n" % item for item in attributes.items()))


def _on_two_pages(first: str, second: str) -> PagesChange:
    """Returns a change that puts `first` on page0 and `second` on page1
    (component_probes.PagesChange)."""
    return on_pages(with_components(first), with_components(second, page="page1"))


_probe = partial(type_probe, "scrolling-text")

# The probes keeping fixtures are the fewest that show each part: one; two,
# of other places, sizes, and txts; one among other types, a timer among
# them; one on a second page; timers before and after one, which number
# their "S " blocks together; each dir; and its other looks.
PROBES = [
    _probe("one", with_components(scrolling_text_component()), fixtures=True),
    _probe("two", with_components(
        scrolling_text_component(),
        scrolling_text_component("g1", y=60, w=100, h=40, txt="ab", txt_maxl=20)),
        fixtures=True),
    _probe("among-the-types-matched", with_components(
        text_component(), scrolling_text_component(y=50), number_component(y=90),
        button_component(y=130), timer_component()), fixtures=True),
    _probe("on-second-page", with_components(scrolling_text_component(), page="page1"),
           fixtures=True),
    _probe("between-timers", with_components(
        timer_component(), scrolling_text_component(), timer_component("tm1"),
        scrolling_text_component("g1", y=60)), fixtures=True),
    _probe("after-a-timer-on-another-page", _on_two_pages(timer_component(),
                                                         scrolling_text_component())),
    _probe("before-a-timer-on-another-page", _on_two_pages(scrolling_text_component(),
                                                          timer_component())),
    _probe("three", with_components(scrolling_text_component(),
                                    scrolling_text_component("g1", y=50),
                                    scrolling_text_component("g2", y=90))),
    _probe("at-the-edges", with_components(scrolling_text_component(x=0, y=0, w=320, h=480))),
    # Twelve on a page, the most nxwright's build takes of timers and
    # scrolling texts together; then six of each, one after the other.
    _probe("twelve", with_components(*[
        scrolling_text_component("g%d" % number, y=40 * number, h=30) for number in range(12)])),
    _probe("six-between-six-timers", with_components(*[
        component for number in range(6)
        for component in (timer_component("tm%d" % number),
                          scrolling_text_component("g%d" % number, y=80 * number))])),
    # Between two QR codes, which keep their txts after the page's
    # components' memory too, in ID order.
    _probe("between-qr-codes", with_components(
        qr_code_component(x=10, y=10, w=80, h=80, txt="ab", txt_maxl=4),
        scrolling_text_component(y=100),
        qr_code_component("qr1", x=10, y=140, w=80, h=80, txt="cd", txt_maxl=8))),
    _probe("event-code", with_components(
        scrolling_text_component(), code="on g0.down:\n  sys0=1\non g0.up:\n  sys1=2\n")),
    _probe("named-with-14", with_components(scrolling_text_component("Scroll_name_14"))),
    # An empty txt, one of digits, and the least and the most txt_maxl the
    # rule takes.
    _probe("empty-txt", with_components(scrolling_text_component(txt=""))),
    _probe("txt-of-digits", with_components(scrolling_text_component(txt="0123456789"))),
    _probe("txt-maxl-of-1", with_components(scrolling_text_component(txt="a", txt_maxl=1))),
    _probe("txt-maxl-of-200", with_components(
        scrolling_text_component(txt="a" * 200, txt_maxl=200))),
    # Its attributes that its memory alone gives: each dir; dis and tim at
    # their ends, and en 0; its colours, centring, isbr, and spacing; and
    # vvs0 to vvs3, which its code sets as it scrolls.
    _probe("of-each-dir", with_components(
        scrolling_text_component(dir=0), scrolling_text_component("g1", y=50, dir=2),
        scrolling_text_component("g2", y=90, dir=3)), fixtures=True),
    _probe("at-the-ends-of-dis-and-tim", with_components(
        scrolling_text_component(dis=2, tim=80),
        scrolling_text_component("g1", y=50, dis=50, tim=65534, en=0))),
    _probe("of-other-looks", with_components(
        scrolling_text_component(bco=0, pco=63488, xcen=0, ycen=2, isbr=1, spax=255, spay=255),
        scrolling_text_component("g1", y=50, xcen=2, ycen=0)), fixtures=True),
    _probe("of-set-vvs", with_components(
        scrolling_text_component(vvs0=5, vvs1=6, vvs2=7, vvs3=32767))),
    # A scrolling text's txt read, set, and compared, and its tim and en
    # read and set.
    Probe("scrolling-text-txt-tim-and-en-in-code", "T", with_attributes(
        ['g0.txt="hi"', "t0.txt=g0.txt", 'if(g0.txt=="a")', "{", "sys0=1", "}", "sys1=g0.tim",
         "g0.tim=200", "sys2=g0.en", "g0.en=0"],
        [text_component(), scrolling_text_component(y=50)]),
          ours_in_event, theirs_in_event, "scrolling-text"),
    # Each style: a border of its borderc and borderw, whose entries move
    # every later entry two on; sunken; raised; and none; the last three each
    # with a borderc and a borderw it does not keep.
    _probe("of-each-style", with_components(
        scrolling_text_component(style=1, borderc=63488, borderw=3),
        scrolling_text_component("g1", y=50, style=2, borderc=63488, borderw=3),
        scrolling_text_component("g2", y=90, style=3, borderc=63488, borderw=3),
        scrolling_text_component("g3", y=130, borderc=63488, borderw=3)), fixtures=True),
    # A border at the ends of its width, which ends its setbrushes, and of
    # its colour.
    _probe("of-borders", with_components(
        scrolling_text_component(style=1, borderc=1, borderw=0),
        scrolling_text_component("g1", y=50, style=1, borderc=65535, borderw=255))),
    # What lies behind it: a picture, at a sta of 2, and a crop of one, at a
    # sta of 0, whose style has no entry, so every later entry is one back,
    # each with a bco it does not keep.
    _probe("of-a-picture-and-a-crop", with_pictures(
        SCREEN_PICTURES, scrolling_text_component(sta=2, pictures={"pic": "bg2"}, bco=31),
        scrolling_text_component("g1", y=50, sta=0, pictures={"picc": "bg"}, bco=31)),
        fixtures=True),
    # A 3D style behind a picture and a crop, which draws no border there:
    # sunken behind a picture, and raised behind a crop.
    _probe("of-3d-styles-behind-a-picture-and-a-crop", with_pictures(
        SCREEN_PICTURES, scrolling_text_component(sta=2, pictures={"pic": "bg2"}, style=2),
        scrolling_text_component("g1", y=50, sta=0, pictures={"picc": "bg"}, style=3))),
    # A style of 1 behind a picture and a crop, which draws no border there
    # but gives its borderc's and borderw's entries.
    _probe("of-a-border-behind-a-picture-and-a-crop", with_pictures(
        SCREEN_PICTURES,
        scrolling_text_component(sta=2, pictures={"pic": "bg2"}, style=1, borderc=63488,
                                 borderw=3),
        scrolling_text_component("g1", y=50, sta=0, pictures={"picc": "bg"}, style=1,
                                 borderc=31, borderw=7))),
    # A picture behind it, but none given; and a colour behind it, with a
    # picture and a crop given, which it does not keep.
    _probe("of-no-picture-and-of-a-colour-with-pictures", with_pictures(
        SCREEN_PICTURES, scrolling_text_component(sta=2),
        scrolling_text_component("g1", y=50, pictures={"pic": "bg", "picc": "bg2"}))),
    # The first in a second font, which its memory alone gives.
    _probe("in-a-second-font", with_the_first_in_a_second_font(
        scrolling_text_component(), scrolling_text_component("g1", y=50))),
    # Its border and its picture in code, and its tim, whose entry is two on
    # at a style of 1 and one back behind a picture.
    Probe("scrolling-text-borders-and-pictures-in-code", "T", with_screen_pictures_and_code(
        ["sys0=g0.borderc", "g0.borderw=5", "g0.tim=200", "sys1=g1.pic", "g1.pic=0",
         "sys2=g1.tim+g0.en"],
        scrolling_text_component(style=1, borderc=63488, borderw=3),
        scrolling_text_component("g1", y=50, sta=2, pictures={"pic": "bg2"})),
          ours_in_event, theirs_in_event, "scrolling-text"),
]
