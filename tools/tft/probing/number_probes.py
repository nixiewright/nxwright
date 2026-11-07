"""The number component's probes (component_types/number.py): numbers on the
T base folder's page, with other places, sizes, and vals, two of them, one
beside a text, one on a second page, a second font, and code in a number's
event; then numbers with other colours, centring, isbr, spacing, lenths,
and formats, and one in a second font. Run them with
`tools.tft.probe run number_probes`.

Each probe compares the whole file, part by part, and keeps the user code
alone as its fixtures (component_probes.py gives both).
"""
from functools import partial

from tools.tft.probing.component_probes import (type_probe, with_components, with_second_font,
                                            with_the_first_in_a_second_font)
from tools.tft.probing.text_probes import text_component


def number_component(name: str = "n0", x: int = 10, y: int = 10, w: int = 100, h: int = 30,
                     val: int = 0, pictures: dict = None, **attributes: int) -> str:
    """Returns a number component in a page file's form, in the base folder's
    font, its `pictures`, as {"pic": the name of a picture of the project},
    and its other attributes, such as bco, at their defaults unless given."""
    return ('\n[[component]]\nname = "%s"\ntype = "number"\nx = %d\ny = %d\nw = %d\nh = %d\n'
            'font = "NotoSans24"\nval = %d\n' % (name, x, y, w, h, val)
            + "".join('%s = "%s"\n' % item for item in (pictures or {}).items())
            + "".join("%s = %d\n" % item for item in attributes.items()))


_probe = partial(type_probe, "number")

# The probes keeping fixtures are the fewest that show each part: two numbers
# on a page; a number beside a text, the type already matched; a number on a
# second page, numbered on from the first's; and, at the end, a number's
# other looks, in its memory.
PROBES = [
    _probe("one", with_components(number_component())),
    _probe("two", with_components(number_component(), number_component("n1", y=60)),
           fixtures=True),
    _probe("beside-a-text", with_components(number_component(), text_component(y=60)),
           fixtures=True),
    _probe("after-a-text", with_components(text_component(), number_component(y=60))),
    _probe("of-123", with_components(number_component(val=123))),
    _probe("of-minus-5", with_components(number_component(val=-5))),
    _probe("of-the-least", with_components(number_component(val=-2147483648))),
    _probe("of-the-most", with_components(number_component(val=2147483647))),
    _probe("at-0-0", with_components(number_component(x=0, y=0, w=50, h=20))),
    _probe("of-2-by-2", with_components(number_component(x=0, y=0, w=2, h=2))),
    _probe("at-the-edges", with_components(number_component(x=220, y=450))),
    _probe("of-the-screen", with_components(number_component(x=0, y=0, w=320, h=480))),
    _probe("event-code", with_components(number_component(), code="on n0.up:\n  sys0=1\n")),
    _probe("named-with-14", with_components(number_component("Numb_name_of14"),
                                            code="on Numb_name_of14.up:\n  sys0=1\n")),
    _probe("on-second-page", with_components(number_component(), page="page1"), fixtures=True),
    _probe("second-font", with_second_font(number_component())),
    # Its attributes that its memory alone gives: its colours at their ends,
    # each xcen and ycen, isbr, spax, and spay; then lenth and format; then a
    # second font.
    _probe("of-other-looks", with_components(
        number_component(val=123, bco=0, pco=63488, xcen=0, ycen=2, isbr=0, spax=5, spay=7),
        number_component("n1", y=60, val=123, xcen=2, ycen=0, spax=255, spay=255),
        number_component("n2", y=110, val=123, bco=1, pco=65535)), fixtures=True),
    _probe("of-lenths-and-formats", with_components(
        number_component(val=123, lenth=3, format=1),
        number_component("n1", y=60, val=123, lenth=15, format=2),
        number_component("n2", y=110, val=123, lenth=1, format=0))),
    _probe("in-a-second-font", with_the_first_in_a_second_font(
        number_component(), number_component("n1", y=60))),
]
