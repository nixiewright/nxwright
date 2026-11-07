"""The probes of drawn components that overlap (overlaps.py): texts on the T
base folder's pages that share pixels: two, two that share one pixel, two
beside a third apart, one inside another, one under four others and one
over them, chains of three, four, and five whose IDs run in different
orders, one of them beside a sixth text apart, three with IDs past 9, two
on a second page, and two with code in their events. Then the types the
rule covers, under a picture and in a chain: first a text, a crop, a
number, a button, a progress bar, and a picture; then a checkbox, a radio,
and a dual-state button, with some of the others; then a hotspot and an
xfloat, with a text; then a slider, a gauge, a QR code, and a waveform,
with a text; then scrolling texts, with texts. Run them with
`tools.tft.probe run overlap_probes`.

Each probe compares the whole file, part by part, and keeps the user code
alone as its fixtures (component_probes.py gives both).
"""
from functools import partial

from tools.tft.probing.button_probes import button_component
from tools.tft.probing.checkbox_probes import checkbox_component
from tools.tft.probing.component_probes import type_probe, with_components
from tools.tft.probing.crop_probes import crop_component
from tools.tft.probing.dual_state_button_probes import dual_state_button_component
from tools.tft.probing.gauge_probes import gauge_component
from tools.tft.probing.hotspot_probes import hotspot_component
from tools.tft.probing.number_probes import number_component
from tools.tft.probing.picture_probes import picture_component, with_pictures
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

# A picture as large as the screen, for the crop and the picture.
_PICTURE = ("bg", (320, 480), (255, 0, 0))


def _chain_places(ids: list) -> dict:
    """Returns the places of components in a chain, each overlapping the one
    before and the one after alone: {ID: (x, y, width, height)}, for the IDs
    `ids` from left to right."""
    return {number: (10 + 50 * place, 10 + 20 * place, 80, 30)
            for place, number in enumerate(ids)}


def _texts_at(places: dict) -> list:
    """Returns a text for each ID of `places`, {ID: (x, y, width, height)},
    in ID order, named t0 onwards. The page's components take IDs from 1 in
    that order, so `places` must give the IDs from 1 on."""
    return [text_component("t%d" % (number - 1), *places[number]) for number in sorted(places)]


def _in_a_chain(place: int) -> dict:
    """Returns the place and size of a chain's component `place`, from 0,
    as a component's helper takes them: 60 by 30, overlapping the one before
    and the one after alone, six of them across the screen."""
    return {"x": 10 + 45 * place, "y": 10 + 20 * place, "w": 60, "h": 30}


_probe = partial(type_probe, "overlap")

# Ten texts apart, in two columns, then three in a chain below them: IDs 11,
# 12, and 13.
_PAST_9 = {**{number + 1: (10 + 160 * (number % 2), 10 + 50 * (number // 2), 100, 30)
              for number in range(10)},
           **{11 + place: (10 + 50 * place, 300 + 20 * place, 80, 30) for place in range(3)}}
# Four small texts apart, and one over them all.
_SMALL = [(10, 10, 40, 20), (10, 60, 40, 20), (10, 110, 40, 20), (10, 160, 40, 20)]
_LARGE = (0, 0, 200, 200)

# The probes keeping fixtures are the fewest that show each part: two
# texts; a chain whose walk lists a component behind it, then one of lower
# ID than any before, beside a text apart; refs of IDs past 9; and the types
# the rule covers under a picture, in its three probes of them.
PROBES = [
    _probe("two", with_components(*_texts_at({1: (10, 10, 100, 30), 2: (60, 20, 100, 30)})),
           fixtures=True),
    # t1's top left pixel is t0's bottom right one.
    _probe("by-one-pixel", with_components(*_texts_at({1: (10, 10, 100, 30),
                                                      2: (109, 39, 100, 30)}))),
    _probe("two-beside-one-apart", with_components(*_texts_at(
        {1: (10, 10, 100, 30), 2: (60, 20, 100, 30), 3: (10, 200, 100, 30)}))),
    _probe("one-inside-another", with_components(*_texts_at({1: (50, 50, 40, 20),
                                                            2: (10, 10, 150, 150)}))),
    _probe("one-under-four", with_components(*_texts_at(
        dict(enumerate([_LARGE] + _SMALL, start=1))))),
    _probe("one-over-four", with_components(*_texts_at(
        dict(enumerate(_SMALL + [_LARGE], start=1))))),
    _probe("chain-1-3-2", with_components(*_texts_at(_chain_places([1, 3, 2])))),
    _probe("chain-1-2-3-4", with_components(*_texts_at(_chain_places([1, 2, 3, 4])))),
    _probe("chain-1-4-2-3", with_components(*_texts_at(_chain_places([1, 4, 2, 3])))),
    _probe("chain-1-2-5-4-3", with_components(*_texts_at(_chain_places([1, 2, 5, 4, 3])))),
    _probe("chain-3-5-1-4-2", with_components(*_texts_at(_chain_places([3, 5, 1, 4, 2])))),
    _probe("chain-1-4-5-3-6-beside-2", with_components(*_texts_at(
        {**_chain_places([1, 4, 5, 3, 6]), 2: (250, 400, 40, 20)})), fixtures=True),
    _probe("ids-past-9", with_components(*_texts_at(_PAST_9)), fixtures=True),
    _probe("on-second-page", with_components(
        *_texts_at({1: (10, 10, 100, 30), 2: (60, 20, 100, 30)}), page="page1")),
    _probe("event-code", with_components(
        *_texts_at({1: (10, 10, 100, 30), 2: (60, 20, 100, 30)}),
        code="on t0.down:\n  sys0=1\non t1.up:\n  sys1=2\n")),
    # A picture over the screen, over a component of each other type, and a
    # variable and a timer, which are not drawn.
    _probe("types-under-a-picture", with_pictures(
        [_PICTURE], text_component(), crop_component(y=60), number_component(y=100),
        button_component(y=140), progress_bar_component(y=200), variable_component(),
        timer_component(), picture_component(x=0, y=0, w=320, h=480, pic="bg")),
        fixtures=True),
    _probe("types-in-a-chain", with_pictures(
        [_PICTURE], picture_component(pic="bg", **_in_a_chain(0)),
        text_component(**_in_a_chain(1)), crop_component(**_in_a_chain(2)),
        number_component(**_in_a_chain(3)), progress_bar_component(**_in_a_chain(4)),
        button_component(**_in_a_chain(5)))),
    # A checkbox, a radio, and a dual-state button, whose down events start
    # with code of the Nextion Editor's own, beside a text, under a picture.
    _probe("more-types-under-a-picture", with_pictures(
        [_PICTURE], checkbox_component(), radio_component(y=50),
        dual_state_button_component(y=90), text_component(y=170),
        picture_component(x=0, y=0, w=320, h=480, pic="bg")), fixtures=True),
    _probe("more-types-in-a-chain", with_components(
        checkbox_component(**_in_a_chain(0)), radio_component(**_in_a_chain(1)),
        dual_state_button_component(**_in_a_chain(2)), text_component(**_in_a_chain(3)),
        number_component(**_in_a_chain(4)), button_component(**_in_a_chain(5)))),
    # A hotspot, whose drawing has no blocks, and an xfloat, beside a text,
    # under a picture; then in a chain, two hotspots apart.
    _probe("hotspot-and-xfloat-under-a-picture", with_pictures(
        [_PICTURE], hotspot_component(), xfloat_component(y=80), text_component(y=130),
        picture_component(x=0, y=0, w=320, h=480, pic="bg")), fixtures=True),
    _probe("hotspot-and-xfloat-in-a-chain", with_components(
        hotspot_component(**_in_a_chain(0)), xfloat_component(**_in_a_chain(1)),
        hotspot_component("m1", **_in_a_chain(2)), text_component(**_in_a_chain(3)))),
    # A slider and a waveform, whose drawings have no blocks, a gauge, and a
    # QR code, beside a text, under a picture; then in a chain.
    _probe("slider-gauge-qr-code-and-waveform-under-a-picture", with_pictures(
        [_PICTURE], slider_component(), gauge_component(y=50), qr_code_component(y=160),
        waveform_component(y=270), text_component(y=380),
        picture_component(x=0, y=0, w=320, h=480, pic="bg")), fixtures=True),
    _probe("slider-gauge-qr-code-and-waveform-in-a-chain", with_components(
        slider_component(**_in_a_chain(0)), gauge_component(**_in_a_chain(1)),
        qr_code_component(**_in_a_chain(2)), waveform_component(**_in_a_chain(3)),
        text_component(**_in_a_chain(4)))),
    # Scrolling texts, whose drawings are their own, over and under a text,
    # over each other, and under a picture; then in a chain.
    _probe("scrolling-text-under-a-picture", with_pictures(
        [_PICTURE], scrolling_text_component(), text_component(x=60, y=20),
        scrolling_text_component("g1", y=80), scrolling_text_component("g2", x=40, y=95),
        text_component("t1", y=150), scrolling_text_component("g3", x=50, y=160),
        picture_component(x=0, y=0, w=320, h=480, pic="bg")), fixtures=True),
    _probe("scrolling-text-in-a-chain", with_components(
        text_component(**_in_a_chain(0)), scrolling_text_component(**_in_a_chain(1)),
        text_component("t1", **_in_a_chain(2)), scrolling_text_component("g1", **_in_a_chain(3)),
        scrolling_text_component("g2", **_in_a_chain(4)))),
]
