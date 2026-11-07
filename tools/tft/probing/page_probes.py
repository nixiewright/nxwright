"""The page's probes (frame.py): pages of the T base folder with their own
attributes away from their defaults. One gives two pages their bco, one
of them beside a text, whose background fill reads it. One gives pages
their swipe targets up, down, left, and right: each a page's ID, every one
apart from the others, and one beyond the project's pages. Two name a
page's effect and swipe targets in its own code, one on a page with an
effect. Then pages with
no background, and with a picture behind them, their sta 0 and 2: beside a
text, a number, and a button; a picture past the project's last, and one
in a project of none; a bco or a pic that a page's sta does not show;
beside a text and a number that overlap, and code
that names a component; and beside a component of each drawn type. Last, a
page of 250 texts, the most components the Nextion Editor takes on a page.
Run them with `tools.tft.probe run page_probes`.

Each probe compares the whole file, part by part, and keeps the user code
alone as its fixtures (component_probes.py gives both).
"""
from pathlib import Path

from tools.tft.probing.button_probes import button_component
from tools.tft.probing.checkbox_probes import checkbox_component
from tools.tft.probing.component_probes import (on_pages, page_attribute_lines, type_probe,
                                            with_components, with_page_attribute_lines)
from tools.tft.probing.crop_probes import crop_component
from tools.tft.probing.dual_state_button_probes import dual_state_button_component
from tools.tft.probing.gauge_probes import gauge_component
from tools.tft.probing.hotspot_probes import hotspot_component
from tools.tft.probing.number_probes import number_component
from tools.tft.probing.picture_probes import PicturesChange, picture_component, with_pictures
from tools.tft.probing.progress_bar_probes import progress_bar_component
from tools.tft.probing.qr_code_probes import qr_code_component
from tools.tft.probing.radio_probes import radio_component
from tools.tft.probing.scrolling_text_probes import scrolling_text_component
from tools.tft.probing.slider_probes import slider_component
from tools.tft.probing.text_probes import text_component
from tools.tft.probing.timer_probes import timer_component
from tools.tft.probing.variable_probes import variable_component
from tools.tft.probing.waveform_probes import waveform_component
from tools.tft.probing.xfloat_probes import xfloat_component


def with_page_attributes(page: str, **attributes):
    """Returns a change that gives the page `page` `attributes`, in its page
    file's table of the page, before its components. A number is written as
    it is, and a text, such as a picture's name, between double quotes."""
    def change(folder: Path):
        with_page_attribute_lines(folder, page, page_attribute_lines(**attributes))
    return change


# page0 of bco 0, beside a text, and page1 of bco 63488.
_OTHER_COLOURS = on_pages(
    with_components(text_component(), attributes=page_attribute_lines(bco=0)),
    with_components(page="page1", attributes=page_attribute_lines(bco=63488)))

# page0 and page1 each with their four swipe targets on four pages apart, and
# page2 with an up of 200, which no page of the project has.
_SWIPES = on_pages(
    with_components(attributes=page_attribute_lines(up=1, down=2, left=3, right=0)),
    with_components(page="page1", attributes=page_attribute_lines(up=3, down=0, left=2, right=1)),
    with_components(page="page2", attributes=page_attribute_lines(up=200)),
    with_components(page="page3"))


# page0's effect and its swipe targets in its own code: read, set, and
# stepped. Code cannot change an effect on T, K, and F.
_EFFECT_AND_SWIPES_CODE = ("on page0.up:\n  sys0=page0.effect\n  sys0=page0.up\n"
                           "  sys0=page0.down\n  sys0=page0.left\n  sys0=page0.right\n"
                           "  page0.up=1\n  page0.down=2\n  page0.left+=3\n  page0.right=4\n")
_EFFECT_AND_SWIPES_IN_CODE = with_components(code=_EFFECT_AND_SWIPES_CODE)
# The same on a page with an effect, which moves its swipe targets and its sta
# two on, and gives it a first and a time to read.
_AN_EFFECT_IN_CODE = with_components(
    code=_EFFECT_AND_SWIPES_CODE + "  sys0=page0.first\n  sys0=page0.time\n  sys0=page0.sta\n",
    attributes=page_attribute_lines(effect=1))


# Three pictures as large as the screen, pictures 0 to 2, each its own colour.
_PICTURES = [("a", (320, 480), (255, 0, 0)), ("b", (320, 480), (0, 255, 0)),
             ("c", (320, 480), (0, 0, 255))]
# A text, a number, and a button, apart.
_APART = (text_component(), number_component(y=60), button_component(y=200))
# A text and a number that overlap, so that each has refs on T, K, and F.
_OVERLAPPING = (text_component(), number_component(x=60, y=20))


# page0 with no background, beside _APART; page1 of bco 2016, beside a number.
_NO_BACKGROUND = on_pages(
    with_components(*_APART, attributes=page_attribute_lines(sta=0)),
    with_components(number_component(y=100), page="page1",
                    attributes=page_attribute_lines(bco=2016)))

# page0 with picture 1 behind it, beside _APART; page1 with picture 2, beside a
# number; and page2 with a picture behind it but none given, its pic 65535.
_PICTURES_BEHIND = on_pages(
    with_pictures(_PICTURES, *_APART, attributes=page_attribute_lines(sta=2, pic="b")),
    with_components(number_component(y=100), page="page1",
                    attributes=page_attribute_lines(sta=2, pic="c")),
    with_components(page="page2", attributes=page_attribute_lines(sta=2)))

# page0 with picture 5 behind it, in a project of three, 0 to 2, beside a text:
# a pic is written as it is given.
_A_PICTURE_PAST_THE_LAST = with_pictures(_PICTURES, text_component(),
                                         attributes=page_attribute_lines(sta=2, pic=5))

# page0 with a picture behind it, beside a text, in a project of no pictures:
# its entry 24 goes up to -1.
_A_PICTURE_WITHOUT_PICTURES = with_components(text_component(),
                                              attributes=page_attribute_lines(sta=2))

# Pages whose page files give a bco or a pic their sta does not show: page0
# with picture 1 behind it and a bco of 31, beside a text; page1 with no
# background, a bco of 31, and picture 0; and page2 of bco 63488, with picture
# 2. Each keeps the one its sta shows, or none.
_HIDDEN_BACKGROUNDS = on_pages(
    with_pictures(_PICTURES, text_component(),
                  attributes=page_attribute_lines(sta=2, pic="b", bco=31)),
    with_components(page="page1", attributes=page_attribute_lines(sta=0, bco=31, pic="a")),
    with_components(page="page2", attributes=page_attribute_lines(bco=63488, pic="c")))

# page0 with no background, beside _OVERLAPPING, whose refs are then their
# background fills' runs alone, and code in its text's down event setting its
# number's val; page1 beside a number, code in its down event setting its val.
# Each number's entries are numbered past page0's, one fewer.
_NO_BACKGROUND_AND_CODE = on_pages(
    with_components(*_OVERLAPPING, code="on t0.down:\n  n0.val=5\n",
                    attributes=page_attribute_lines(sta=0)),
    with_components(number_component(y=100), page="page1", code="on n0.down:\n  n0.val=7\n"))


def in_a_grid(number: int) -> dict:
    """Returns the place and size of the component `number` of a grid of 4
    columns, apart from the others: 70 by 80, 5 rows on the screen."""
    return {"x": 5 + 80 * (number % 4), "y": 5 + 95 * (number // 4), "w": 70, "h": 80}


def in_a_landscape_grid(number: int) -> dict:
    """Returns the place and size of the component `number` of a grid of 6
    columns, apart from the others: 70 by 80, 3 rows on a screen of 480 by
    320, as NX4832T035's at 90 and 270 degrees."""
    return {"x": 5 + 78 * (number % 6), "y": 5 + 100 * (number // 6), "w": 70, "h": 80}


def _every_type(grid=in_a_grid) -> list:
    """Returns a component of each drawn type, placed by `grid`, then a
    second text, over the first text and the number, so that the three have
    refs, and a variable and a timer, which are not drawn. The crop and the
    picture show picture 0."""
    drawn = [text_component, number_component, button_component,
             lambda **place: crop_component(picc="a", **place),
             lambda **place: picture_component(pic="a", **place), progress_bar_component,
             checkbox_component, radio_component, dual_state_button_component,
             hotspot_component, xfloat_component, slider_component, gauge_component,
             qr_code_component, waveform_component, scrolling_text_component]
    return ([component(**grid(number)) for number, component in enumerate(drawn)]
            + [text_component("t1", x=40, y=40, w=70, h=30), variable_component(),
               timer_component()])


def every_type_on_no_background(grid=in_a_grid) -> PicturesChange:
    """Returns a change that puts a component of each type, placed by `grid`,
    on a page with no background. A unit test reads what it adds, to make
    the same page in memory (picture_probes.PicturesChange)."""
    return with_pictures(_PICTURES[:1], *_every_type(grid),
                         attributes=page_attribute_lines(sta=0))


def every_type_on_a_picture(grid=in_a_grid) -> PicturesChange:
    """Returns a change that puts a component of each type, placed by `grid`,
    on a page with picture 1 behind it, so that its ID is not the crop's and
    the picture's. A unit test reads what it adds, to make the same page in
    memory (picture_probes.PicturesChange)."""
    return with_pictures(_PICTURES[:2], *_every_type(grid),
                         attributes=page_attribute_lines(sta=2, pic="b"))


def small_texts(count: int) -> list:
    """Returns `count` texts in rows of 19, 4 pixels apart. Each is 12 by 12,
    with a txt of a and a txt_maxl of 1, so that the memory of 250 texts, the
    most components the Nextion Editor takes on a page, fits T's."""
    return [text_component("t%d" % number, x=10 + 16 * (number % 19), y=10 + 16 * (number // 19),
                           w=12, h=12, txt="a", txt_maxl=1) for number in range(count)]


PROBES = [
    type_probe("page", "of-other-colours", _OTHER_COLOURS, fixtures=True),
    type_probe("page", "of-swipes", _SWIPES, fixtures=True),
    type_probe("page", "of-its-effect-and-swipes-in-code", _EFFECT_AND_SWIPES_IN_CODE,
               fixtures=True),
    type_probe("page", "of-an-effect-in-code", _AN_EFFECT_IN_CODE, fixtures=True),
    type_probe("page", "of-no-background", _NO_BACKGROUND, fixtures=True),
    type_probe("page", "of-pictures", _PICTURES_BEHIND, fixtures=True),
    type_probe("page", "of-a-picture-past-the-last", _A_PICTURE_PAST_THE_LAST),
    type_probe("page", "of-a-picture-without-pictures", _A_PICTURE_WITHOUT_PICTURES,
               fixtures=True),
    type_probe("page", "of-hidden-backgrounds", _HIDDEN_BACKGROUNDS),
    type_probe("page", "of-no-background-and-code", _NO_BACKGROUND_AND_CODE, fixtures=True),
    type_probe("page", "every-type-on-no-background", every_type_on_no_background(),
               fixtures=True),
    type_probe("page", "every-type-on-a-picture", every_type_on_a_picture(),
               fixtures=True),
    type_probe("page", "of-250-texts", with_components(*small_texts(250))),
]
