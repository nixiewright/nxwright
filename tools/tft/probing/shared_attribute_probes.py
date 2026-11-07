"""The probes of the attributes every component with a place has, and the
page too, that nxwright writes alike for each type: a component of each type,
and the page, with their aph and sendkey away from their defaults, which
the record's head gives; then with their drag, movex, movey, groupid0,
groupid1, and lockobj away from theirs, which change nothing in the file;
then with an effect, its first, and its time, which give two more entries,
with code and a second page after them; then global, of vscope 1, which
puts their memory before every page's, after the int variables.
Run them with `tools.tft.probe run shared_attribute_probes`.

Each probe compares the whole file, part by part, and keeps the user code
alone as its fixtures (component_probes.py gives both).
"""
from dataclasses import dataclass
from pathlib import Path

from tools.tft.probing.button_probes import button_component
from tools.tft.probing.checkbox_probes import checkbox_component
from tools.tft.probing.component_probes import (PagesChange, on_pages, page_attribute_lines,
                                            type_probe, with_components)
from tools.tft.probing.crop_probes import crop_component
from tools.tft.probing.dual_state_button_probes import dual_state_button_component
from tools.tft.probing.gauge_probes import gauge_component
from tools.tft.probing.hotspot_probes import hotspot_component
from tools.tft.probing.number_probes import number_component
from tools.tft.probing.picture_probes import (SCREEN_PICTURES, PicturesChange, picture_component,
                                          with_pictures)
from tools.tft.probing.progress_bar_probes import progress_bar_component
from tools.tft.probing.qr_code_probes import qr_code_component
from tools.tft.probing.radio_probes import radio_component
from tools.tft.probing.scrolling_text_probes import scrolling_text_component
from tools.tft.probing.slider_probes import slider_component
from tools.tft.probing.statement_probes import program_text
from tools.tft.probing.text_probes import text_component
from tools.tft.probing.timer_probes import timer_component
from tools.tft.probing.touch_capture_probes import touch_capture_component
from tools.tft.probing.variable_probes import variable_component
from tools.tft.probing.waveform_probes import waveform_component
from tools.tft.probing.xfloat_probes import xfloat_component

# A builder of each drawn type, taking a place and a size; the crop and the
# picture show picture 0, bg.
_DRAWN = [text_component, number_component, button_component,
          lambda **place: crop_component(picc="bg", **place),
          lambda **place: picture_component(pic="bg", **place), progress_bar_component,
          checkbox_component, radio_component, dual_state_button_component, hotspot_component,
          xfloat_component, slider_component, gauge_component, qr_code_component,
          waveform_component, scrolling_text_component]
# The types that are not drawn, which have groupid0, groupid1, lockobj, and
# vscope alone.
_UNDRAWN = [variable_component, timer_component, touch_capture_component]


def _in_a_grid(number: int) -> dict:
    """Returns the place and size of the component `number` of a grid of 4
    columns, apart from the others: 70 by 80, 4 rows on the screen."""
    return {"x": 5 + 80 * (number % 4), "y": 5 + 95 * (number // 4), "w": 70, "h": 80}


def _with_lines(component: str, **attributes: int) -> str:
    """Returns `component`, a component in a page file's form, with
    `attributes` added after its own."""
    return component + "".join("%s = %d\n" % item for item in attributes.items())


def _each_type(drawn_attributes, undrawn_attributes, page_attributes: dict,
               code: str = "") -> PicturesChange:
    """Returns a probe's change: a component of each type on page0, the
    drawn ones in a grid, each with drawn_attributes(its number), each one
    not drawn with undrawn_attributes(its number), and the page with
    `page_attributes` and `code` (PicturesChange)."""
    components = ([_with_lines(build(**_in_a_grid(number)), **drawn_attributes(number))
                   for number, build in enumerate(_DRAWN)]
                  + [_with_lines(build(), **undrawn_attributes(number))
                     for number, build in enumerate(_UNDRAWN)])
    return with_pictures(SCREEN_PICTURES[:1], *components, code=code,
                         attributes=page_attribute_lines(**page_attributes))


@dataclass(frozen=True, eq=False)
class IntsChange(PagesChange):
    """A PagesChange, then `ints`, int variables each such as "a=5", added to
    program.nx's declaration of sys0, sys1, and sys2
    (statement_probes.program_text). A unit test reads them, to make the
    same program.s in memory (tests/tft/unit_inputs.py)."""
    ints: tuple = ()

    def __call__(self, folder: Path):
        super().__call__(folder)
        program = folder / "program.nx"
        program.write_text(program_text(program.read_text(encoding="utf-8"), ints=self.ints),
                           encoding="utf-8")


# Each drawn type, and the page, with an effect, its first, and its time;
# code on page0 that names entries the effects move; and a text on page1,
# whose entries follow page0's, page1 with no background and an effect,
# one entry fewer and two more.
_EFFECTS_AND_A_SECOND_PAGE = on_pages(
    _each_type(lambda number: {"effect": number % 8 + 1, "first": 6 * number,
                               "time": 150 + 1000 * number},
               lambda number: {}, {"effect": 3, "first": 9, "time": 777},
               'on t0.up:\n  t0.txt="Yo"\n  n0.val=5\n'),
    with_components(text_component(), page="page1", code='on t0.up:\n  t0.txt="Hi"\n',
                    attributes=page_attribute_lines(sta=0, effect=2)))

# Every other type global on page0, from the number on, and every other
# type not drawn, from the variable on; on page1, a global text and
# waveform, whose memory follows page0's globals', beside a QR code and a
# text of their page, with code that names them; and two more ints, which
# come before the global objects' memory. The QR code's txt fills its
# txt_maxl and its 0, 8 bytes, as the Nextion Editor leaves bytes of the
# page before in the padding after a QR code's txt.
_GLOBALS_ON_TWO_PAGES = IntsChange((
    _each_type(lambda number: {"vscope": number % 2}, lambda number: {"vscope": (number + 1) % 2},
               {}, 'on t0.up:\n  t0.txt="Yo"\n  n0.val=5\n  qr0.txt=t0.txt\n'),
    with_components(text_component("t0", vscope=1), waveform_component("s0", y=60, vscope=1),
                    qr_code_component("qr0", y=200, txt="abcdefg", txt_maxl=7),
                    text_component("t1", y=320),
                    page="page1", code='on t1.up:\n  t0.txt="Hi"\n  t1.txt=t0.txt\n')),
    ("a=5", "b=6"))


PROBES = [
    # aph from 127 down to 7, and 0 for the last, and each sendkey: none,
    # on release, on press, and both, in turn; the page's too.
    type_probe("shared-attributes", "aph-and-sendkey-of-each-type", _each_type(
        lambda number: {"aph": 127 - 8 * number if number < 15 else 0, "sendkey": number % 4},
        lambda number: {}, {"aph": 50, "sendkey": 3}), fixtures=True),
    # A drag on every other one, movex and movey at the ends of their 2
    # bytes, groupid0 and groupid1 of 4 bytes, and a lock on every other
    # one; the page's too, and those of the types that are not drawn.
    type_probe("shared-attributes", "groups-locks-and-drags-of-each-type", _each_type(
        lambda number: {"drag": number % 2, "movex": 65535 - number, "movey": 32768 + number,
                        "groupid0": 4294967295 - number, "groupid1": 1000 * number + 1,
                        "lockobj": (number + 1) % 2},
        lambda number: {"groupid0": number + 1, "groupid1": 4294967294, "lockobj": 1},
        {"drag": 1, "groupid0": 7, "groupid1": 8, "lockobj": 1})),
    # Each effect, 1 to 8, with firsts from 0 to 90 and times from 150 to
    # 15150, and the page's; code on page0, and a second page.
    type_probe("shared-attributes", "effects-of-each-type", _EFFECTS_AND_A_SECOND_PAGE,
               fixtures=True),
    # Every type global, and the page too, with code naming them: their
    # memory, then the QR code's and the scrolling text's txts, then the
    # word of the waveform's buffer, all after the ints.
    type_probe("shared-attributes", "every-type-global", _each_type(
        lambda number: {"vscope": 1}, lambda number: {"vscope": 1}, {"vscope": 1},
        'on t0.up:\n  t0.txt="Yo"\n  n0.val=5\n'), fixtures=True),
    # Globals on two pages, each page's after the last page's, beside
    # components of their page, with two more ints and code on both pages.
    type_probe("shared-attributes", "globals-on-two-pages", _GLOBALS_ON_TWO_PAGES,
               fixtures=True),
]
