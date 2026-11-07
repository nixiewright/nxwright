"""The number component's probes of its border and of what lies behind it
(component_types/number.py): numbers of each style, of borders at the ends
of their colour and width, with a picture or a crop of one behind them, a
picture not given and pictures given that a number does not show, a
picture behind numbers in a project of none, and their borders and
pictures in code. Run them with
`tools.tft.probe run number_border_and_picture_probes`.

They are apart from number_probes.py, as they take pictures and code from
modules that import number_probes.py. Each probe of numbers compares the
whole file, part by part, and keeps the user code alone as its fixtures
(component_probes.py gives both). The probe of code compares the blocks of
page 0's Touch Release event.
"""
from functools import partial

from tools.tft.probing.component_probes import type_probe, with_components
from tools.tft.probing.number_probes import number_component
from tools.tft.probing.picture_probes import (SCREEN_PICTURES, with_pictures,
                                          with_screen_pictures_and_code)
from tools.tft.probing.probe_runner import Probe
from tools.tft.probing.statement_probes import ours_in_event, theirs_in_event

_probe = partial(type_probe, "number")

# Each number's spax and spay are apart, and its val is not 0, so that an
# entry moved onto another would not match.
PROBES = [
    # Each style: a border of its borderc and borderw, whose entries move
    # every later entry two on; sunken; raised; and none; the last three each
    # with a borderc and a borderw it does not keep.
    _probe("of-each-style", with_components(
        number_component(val=12, style=1, borderc=63488, borderw=3, spax=3, spay=5),
        number_component("n1", y=60, val=34, style=2, borderc=63488, borderw=3, spax=5),
        number_component("n2", y=110, val=56, style=3, borderc=63488, borderw=3, spay=7),
        number_component("n3", y=160, val=78, borderc=63488, borderw=3, isbr=1)),
        fixtures=True),
    # A border at the ends of its colour and of its width, which ends its
    # setbrush.
    _probe("of-borders", with_components(
        number_component(val=1, style=1, borderc=0, borderw=0, spax=3),
        number_component("n1", y=60, val=2, style=1, borderc=65535, borderw=255, spay=5))),
    # What lies behind it: a picture, at a sta of 2, and a crop of one, at a
    # sta of 0, whose style has no entry, so every later entry is one back,
    # each with a bco it does not keep; then each with a 3D style, which
    # draws no border there and is written as a style of 0.
    _probe("of-a-picture-and-a-crop", with_pictures(
        SCREEN_PICTURES, number_component(val=12, sta=2, pictures={"pic": "bg2"}, bco=31, spax=3),
        number_component("n1", y=60, val=34, sta=0, pictures={"picc": "bg"}, bco=31, spay=5),
        number_component("n2", y=110, val=56, sta=2, style=3, pictures={"pic": "bg"}),
        number_component("n3", y=160, val=78, sta=0, style=2, pictures={"picc": "bg2"},
                         isbr=1)), fixtures=True),
    # A style of 1 behind a picture and a crop, which draws no border there
    # but gives its borderc's and borderw's entries, and their values in
    # memory.
    _probe("of-a-border-behind-a-picture-and-a-crop", with_pictures(
        SCREEN_PICTURES,
        number_component(val=12, sta=2, style=1, borderc=63488, borderw=3,
                         pictures={"pic": "bg2"}, spax=3),
        number_component("n1", y=60, val=34, sta=0, style=1, borderc=31, borderw=7,
                         pictures={"picc": "bg"}, spay=5))),
    # A picture behind it, but none given; and a colour behind it, with a
    # picture and a crop given, which it does not keep.
    _probe("of-no-picture-and-of-a-colour-with-pictures", with_pictures(
        SCREEN_PICTURES, number_component(val=12, sta=2, spax=3),
        number_component("n1", y=60, val=34, pictures={"pic": "bg", "picc": "bg2"}, spay=5))),
    # A picture and a crop behind numbers in a project of no pictures, whose
    # entry's highest, the last picture, is -1.
    _probe("of-a-picture-in-a-project-of-none", with_components(
        number_component(val=12, sta=2, spax=3),
        number_component("n1", y=60, val=34, sta=0, spay=5))),
    # Its border and its picture read and set in code; then its val and
    # pco, whose entries are two on at a style of 1 and one back behind a
    # picture.
    Probe("number-borders-and-pictures-in-code", "T", with_screen_pictures_and_code(
        ["sys0=n0.borderc", "n0.borderc=31", "n0.borderw=5", "sys1=n1.pic", "n1.pic=0",
         "n0.val=7", "n1.val=8", "sys2=n1.pco+n0.spax"],
        number_component(val=12, style=1, borderc=63488, borderw=3, spax=3),
        number_component("n1", y=60, val=34, sta=2, pictures={"pic": "bg2"}, spay=5)),
          ours_in_event, theirs_in_event, "number"),
]
