"""The button component's probes of its border and of what lies behind it
(component_types/button.py): buttons of each style, of borders at the ends
of their colour and width, with pictures or crops behind them, released
and pressed, pictures not given and pictures given that a button does not
show, pictures behind buttons in a project of none, and their borders and
pictures in code. Run them with
`tools.tft.probe run button_border_and_picture_probes`.

They are apart from button_probes.py, as they take pictures and code from
modules that import button_probes.py. Each probe of buttons compares the
whole file, part by part, and keeps the user code alone as its fixtures
(component_probes.py gives both). The probe of code compares the blocks of
page 0's Touch Release event.
"""
from functools import partial

from tools.tft.probing.button_probes import button_component
from tools.tft.probing.component_probes import type_probe, with_components
from tools.tft.probing.picture_probes import (SCREEN_PICTURES, with_pictures,
                                          with_screen_pictures_and_code)
from tools.tft.probing.probe_runner import Probe
from tools.tft.probing.statement_probes import ours_in_event, theirs_in_event

_probe = partial(type_probe, "button")
# Each button's colours released and pressed are apart, and so are its spax
# and spay, so that an entry moved onto another would not match.
_COLOURS = dict(bco=1000, bco2=2000, pco=3000, pco2=4000)


def _button(name: str, y: int, **attributes) -> str:
    """Returns a button of _COLOURS, at 10, `y`, with `attributes`."""
    return button_component(name, y=y, **{**_COLOURS, **attributes})


PROBES = [
    # Each style: none; a border of its borderc and borderw, whose entries
    # move every later entry two on; sunken; raised; and its default, raised
    # and sunken while it is pressed, the last with a borderc and a borderw
    # it does not keep. The third starts pressed.
    _probe("of-each-style", with_components(
        _button("b0", 10, style=0, spax=3),
        _button("b1", 70, style=1, borderc=63488, borderw=3, spay=5),
        _button("b2", 130, style=2, val=1),
        _button("b3", 190, style=3, isbr=1),
        _button("b4", 250, borderc=63488, borderw=3, spax=7)), fixtures=True),
    # Borders whose borderc is written as digits, 999 and 0, or as a long
    # number, 1000, and whose borderw, which ends its setbrushes, is at each
    # end.
    _probe("of-borders", with_components(
        _button("b0", 10, style=1, borderc=999, borderw=0, spax=3),
        _button("b1", 70, style=1, borderc=1000, borderw=255, spay=5),
        _button("b2", 130, style=1, borderc=0, borderw=1))),
    # What lies behind it: pictures, at a sta of 2, and crops of them, at a
    # sta of 0, released and pressed, whose style has no entry, so every
    # later entry is one back, each with colours it does not keep; then each
    # with another style, which draws no border there. The first starts
    # pressed.
    _probe("of-pictures-and-crops", with_pictures(
        SCREEN_PICTURES,
        _button("b0", 10, sta=2, pictures={"pic": "bg", "pic2": "bg2"}, val=1, spax=3),
        _button("b1", 70, sta=0, pictures={"picc": "bg2", "picc2": "bg"}, spay=5),
        _button("b2", 130, sta=2, style=2, pictures={"pic": "bg2", "pic2": "bg"}),
        _button("b3", 190, sta=0, style=0, pictures={"picc": "bg", "picc2": "bg2"}, isbr=1),
        _button("b4", 250, sta=2, style=3, pictures={"pic": "bg", "pic2": "bg"})),
        fixtures=True),
    # A style of 1 behind pictures and crops, which draws no border there
    # but gives its borderc's and borderw's entries.
    _probe("of-a-border-behind-pictures-and-crops", with_pictures(
        SCREEN_PICTURES,
        _button("b0", 10, sta=2, style=1, borderc=63488, borderw=3,
                pictures={"pic": "bg", "pic2": "bg2"}),
        _button("b1", 70, sta=0, style=1, borderc=31, borderw=7,
                pictures={"picc": "bg2", "picc2": "bg"}))),
    # Pictures behind it, but none given; and a colour behind it, with
    # pictures and crops given, which it does not keep.
    _probe("of-no-picture-and-of-a-colour-with-pictures", with_pictures(
        SCREEN_PICTURES, _button("b0", 10, sta=2, spax=3),
        _button("b1", 70, pictures={"pic": "bg", "pic2": "bg2", "picc": "bg2", "picc2": "bg"},
                spay=5))),
    # Pictures and crops behind buttons in a project of no pictures, whose
    # entries' highest, the last picture, is -1.
    _probe("of-pictures-in-a-project-of-none", with_components(
        _button("b0", 10, sta=2, spax=3), _button("b1", 70, sta=0, spay=5))),
    # Its border read in code, which cannot set it, and its pictures read and
    # set; then its val and pco2, whose entries are two on at a style of 1
    # and one back behind a picture.
    Probe("button-borders-and-pictures-in-code", "T", with_screen_pictures_and_code(
        ["sys0=b0.borderc", "sys1=b0.borderw", "sys2=b1.pic2", "b1.pic=0", "b1.pic2=1",
         "b0.val=1", "b1.val=0", "sys0=b1.pco2+b0.pco"],
        _button("b0", 10, style=1, borderc=63488, borderw=3, spax=3),
        _button("b1", 70, sta=2, pictures={"pic": "bg2", "pic2": "bg"}, spay=5)),
          ours_in_event, theirs_in_event, "button"),
]
