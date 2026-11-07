"""The text component's probes of its border and of what lies behind it
(component_types/text.py): texts of each style, of borders at the ends of
their colour and width, with a picture or a crop of one behind them, a
picture not given and pictures given that a text does not show, a picture
behind texts in a project of none, and their borders and pictures in code. Run them with
`tools.tft.probe run text_border_and_picture_probes`.

They are apart from text_probes.py, as they take pictures and code from
modules that import text_probes.py. Each probe of texts compares the whole
file, part by part, and keeps the user code alone as its fixtures
(component_probes.py gives both). The probe of code compares the blocks of
page 0's Touch Release event.
"""
from functools import partial

from tools.tft.probing.component_probes import type_probe, with_components
from tools.tft.probing.picture_probes import (SCREEN_PICTURES, with_pictures,
                                          with_screen_pictures_and_code)
from tools.tft.probing.probe_runner import Probe
from tools.tft.probing.statement_probes import ours_in_event, theirs_in_event
from tools.tft.probing.text_probes import text_component

_probe = partial(type_probe, "text")

# Each text's pw and isbr are apart, so that an entry moved onto the other
# would not match.
PROBES = [
    # Each style: a border of its borderc and borderw, whose entries move
    # every later entry two on; sunken; raised; and none; the last three each
    # with a borderc and a borderw it does not keep.
    _probe("of-each-style", with_components(
        text_component(style=1, borderc=63488, borderw=3, pw=1),
        text_component("t1", y=60, style=2, borderc=63488, borderw=3, isbr=1),
        text_component("t2", y=110, style=3, borderc=63488, borderw=3, pw=1),
        text_component("t3", y=160, borderc=63488, borderw=3, isbr=1)), fixtures=True),
    # Borders whose borderc is written as digits, 999 and 0, or as a long
    # number, 1000, and whose borderw, which ends its setbrush, is at each
    # end.
    _probe("of-borders", with_components(
        text_component(style=1, borderc=999, borderw=0, pw=1),
        text_component("t1", y=60, style=1, borderc=1000, borderw=255, isbr=1),
        text_component("t2", y=110, style=1, borderc=0, borderw=1, pw=1))),
    # What lies behind it: a picture, at a sta of 2, and a crop of one, at a
    # sta of 0, whose style has no entry, so every later entry is one back,
    # each with a bco it does not keep; then each with a 3D style, which
    # draws no border there.
    _probe("of-a-picture-and-a-crop", with_pictures(
        SCREEN_PICTURES, text_component(sta=2, pictures={"pic": "bg2"}, bco=31, pw=1),
        text_component("t1", y=60, sta=0, pictures={"picc": "bg"}, bco=31, isbr=1),
        text_component("t2", y=110, sta=2, style=3, pictures={"pic": "bg"}, pw=1),
        text_component("t3", y=160, sta=0, style=2, pictures={"picc": "bg2"}, isbr=1)),
        fixtures=True),
    # A style of 1 behind a picture and a crop, which draws no border there
    # but gives its borderc's and borderw's entries.
    _probe("of-a-border-behind-a-picture-and-a-crop", with_pictures(
        SCREEN_PICTURES,
        text_component(sta=2, style=1, borderc=63488, borderw=3, pictures={"pic": "bg2"},
                       pw=1),
        text_component("t1", y=60, sta=0, style=1, borderc=31, borderw=7,
                       pictures={"picc": "bg"}, isbr=1))),
    # A picture behind it, but none given; and a colour behind it, with a
    # picture and a crop given, which it does not keep.
    _probe("of-no-picture-and-of-a-colour-with-pictures", with_pictures(
        SCREEN_PICTURES, text_component(sta=2, pw=1),
        text_component("t1", y=60, pictures={"pic": "bg", "picc": "bg2"}, isbr=1))),
    # A picture and a crop behind texts in a project of no pictures, whose
    # entry's highest, the last picture, is -1.
    _probe("of-a-picture-in-a-project-of-none", with_components(
        text_component(sta=2, pw=1), text_component("t1", y=60, sta=0, isbr=1))),
    # Its border read in code, which cannot set it, and its picture read and
    # set; then its txt and pco, whose entries are two on at a style of 1
    # and one back behind a picture.
    Probe("text-borders-and-pictures-in-code", "T", with_screen_pictures_and_code(
        ["sys0=t0.borderc", "sys1=t0.borderw", 't0.txt="Yo"', "sys2=t1.pic", "t1.pic=0",
         't1.txt="Yo"', "sys0=t1.pco+t0.pw"],
        text_component(style=1, borderc=63488, borderw=3, pw=1),
        text_component("t1", y=60, sta=2, pictures={"pic": "bg2"}, isbr=1)),
          ours_in_event, theirs_in_event, "text"),
]
