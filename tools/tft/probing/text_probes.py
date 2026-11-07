"""The text component's probes (component_types/text.py): texts on the T base
folder's page, with other places, sizes, texts, and txt_maxl, two of them,
one on a second page, four that touch, a second font, and code in a text's
event, setting a text's txt; then texts with other colours, centring, isbr,
pw, and spacing, and one in a second font. Run them with
`tools.tft.probe run text_probes`.

Each probe compares the whole file, part by part, and keeps the user code
alone as its fixtures (component_probes.py gives both).
"""
from functools import partial
from pathlib import Path

from tools.tft.probing.component_probes import (on_pages, type_probe, with_components,
                                            with_second_font, with_the_first_in_a_second_font)


def text_component(name: str = "t0", x: int = 10, y: int = 10, w: int = 100, h: int = 30,
                   txt: str = "Hi", txt_maxl: int = 10, pictures: dict = None,
                   **attributes: int) -> str:
    """Returns a text component in a page file's form, in the base folder's
    font, its `pictures`, as {"pic": the name of a picture of the project},
    and its other attributes, such as bco, at their defaults unless given."""
    return ('\n[[component]]\nname = "%s"\ntype = "text"\nx = %d\ny = %d\nw = %d\nh = %d\n'
            'font = "NotoSans24"\ntxt = "%s"\ntxt_maxl = %d\n' % (name, x, y, w, h, txt, txt_maxl)
            + "".join('%s = "%s"\n' % item for item in (pictures or {}).items())
            + "".join("%s = %d\n" % item for item in attributes.items()))


def _with_two_more_ints(folder: Path):
    """A text, with two more int variables, which move its base."""
    with_components(text_component())(folder)
    program = folder / "program.nx"
    program.write_text(program.read_text(encoding="utf-8").replace(
        "int sys0=0,sys1=0,sys2=0", "int sys0=0,sys1=0,sys2=0,a=5,b=6"), encoding="utf-8")


def _texts(count: int, columns: int = 2, w: int = 100, h: int = 30, across: int = 150,
           down: int = 50) -> list:
    """Returns `count` texts, t0 onwards, of `w` by `h`, in `columns`
    columns, `across` and `down` pixels apart. Past 3 texts, the page's
    memory starts with more than 4 bytes of 0xFF (frame.py)."""
    return [text_component("t%d" % number, x=10 + across * (number % columns),
                           y=10 + down * (number // columns), w=w, h=h)
            for number in range(count)]


def _one_then_four(folder: Path):
    """A text on page0, then four on page1: each page's memory starts with
    its own run of 0xFF bytes, 4 bytes, then 8."""
    with_components(*_texts(1))(folder)
    with_components(*_texts(4), page="page1")(folder)


def _setting_txt(value: str):
    return with_components(text_component(), code='on t0.up:\n  t0.txt="%s"\n' % value)


_probe = partial(type_probe, "text")

_SET_TXT = 'on t0.up:\n  t0.txt="Yo"\n'

# A text on page0, then another on page1, setting its own txt: page1's
# entries numbered on from page0's text.
_ON_TWO_PAGES = on_pages(with_components(text_component()),
                         with_components(text_component(y=60), page="page1", code=_SET_TXT))

# Two texts on page0, then a text on page1: three objects before page1.
_TWO_THEN_A_PAGE = on_pages(with_components(text_component(), text_component("t1", y=60)),
                            with_components(text_component(), page="page1", code=_SET_TXT))

# The probes keeping fixtures are the fewest that show each part: two texts
# on a page, their entries, memory, records, and objects' table; a text on a
# second page, numbered on from the first's; txt_maxl 20, whose memory is
# rounded up; and, at the end, a text's other looks, in its memory, and its
# spacing, in its drawing and entries.
PROBES = [
    _probe("one", with_components(text_component())),
    _probe("two", with_components(text_component(), text_component("t1", y=60)), fixtures=True),
    _probe("empty", with_components(text_component(txt=""))),
    _probe("full", with_components(text_component(txt="0123456789"))),
    _probe("txt-maxl-1", with_components(text_component(txt="H", txt_maxl=1))),
    _probe("txt-maxl-20", with_components(text_component(txt_maxl=20)), fixtures=True),
    _probe("txt-maxl-200", with_components(text_component(txt_maxl=200))),
    _probe("at-0-0", with_components(text_component(x=0, y=0, w=50, h=20))),
    _probe("of-2-by-2", with_components(text_component(x=0, y=0, w=2, h=2))),
    _probe("at-the-edges", with_components(text_component(x=220, y=450))),
    _probe("of-the-screen", with_components(text_component(x=0, y=0, w=320, h=480))),
    _probe("second-font", with_second_font(text_component())),
    _probe("event-code", with_components(text_component(), code="on t0.up:\n  sys0=1\n")),
    _probe("setting-txt", with_components(text_component(), code=_SET_TXT)),
    _probe("setting-second-txt", with_components(text_component(), text_component("t1", y=60),
                                                 code='on t0.up:\n  t1.txt="Yo"\n')),
    _probe("on-second-page", with_components(text_component(), page="page1", code=_SET_TXT),
           fixtures=True),
    _probe("named-with-14", with_components(text_component("Text_name_of14"),
                                            code='on Text_name_of14.up:\n'
                                                 '  Text_name_of14.txt="Yo"\n')),
    _probe("on-two-pages", _ON_TWO_PAGES, fixtures=True),
    _probe("four-on-a-page", with_components(*_texts(4))),
    _probe("eight-on-a-page", with_components(*_texts(8))),
    _probe("forty-on-a-page", with_components(*_texts(40, columns=4, w=70, h=40, across=77,
                                                      down=46))),
    # Four texts in a grid, each sharing a side with two others and a corner
    # with the third, but no pixel: they touch, and do not overlap.
    _probe("touching", with_components(*_texts(4, across=100, down=30))),
    _probe("one-then-four-on-a-page", _one_then_four),
    _probe("two-then-a-page", _TWO_THEN_A_PAGE),
    _probe("with-two-more-ints", _with_two_more_ints),
    _probe("setting-empty-txt", _setting_txt("")),
    _probe("setting-txt-of-10", _setting_txt("0123456789")),
    _probe("setting-txt-past-txt-maxl", _setting_txt("abcdefghijklmnopqrst")),
    _probe("events-of-text-and-page", with_components(
        text_component(), code='on page0.down:\n  t0.txt="Ab"\n\n'
                               'on t0.down:\n  sys0=1\n\non t0.up:\n  sys1=2\n')),
    # Its attributes that its memory alone gives: its colours at their ends,
    # each xcen and ycen, isbr, and pw; then spax and spay, which its drawing
    # and entries give too; then a second font.
    _probe("of-other-looks", with_components(
        text_component(bco=0, pco=63488, xcen=0, ycen=2, isbr=1, pw=1),
        text_component("t1", y=60, xcen=2, ycen=0),
        text_component("t2", y=110, bco=1, pco=65535)), fixtures=True),
    # pw apart from isbr, each way round, which the probe of other looks,
    # giving both 1, could not tell apart.
    _probe("of-pw-apart-from-isbr", with_components(
        text_component(pw=1, isbr=0), text_component("t1", y=60, pw=0, isbr=1)),
        fixtures=True),
    _probe("of-spacing", with_components(
        text_component(spax=5, spay=7), text_component("t1", y=60, spax=255, spay=255)),
        fixtures=True),
    _probe("in-a-second-font", with_the_first_in_a_second_font(
        text_component(), text_component("t1", y=60))),
]
