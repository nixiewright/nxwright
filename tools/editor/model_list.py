"""The Editor's list of screen models, as `editor.py models` reads it from
the device settings (README.md). The device settings show a tile for each
model of a series. This module does not drive an Editor or import pywinauto,
so that its tests run with nxwright's own Python.

UI Automation gives the text of each tile, with the model's size and memory,
but not the model's name, which the Editor draws separately. So the list
gives each model by its series and the text of its tile. `editor.py models` writes the list as JSON:

    {"editor_version": "1.68.2.3035",
     "models": [{"series": "T", "inch": 2.4, "width": 240, "height": 320,
                 "flash": "4M", "ram": "3584B", "frequency": "48M"}]}
"""
import re

# The series of the buttons in the device settings, from left to right:
# Basic (T), Discovery (F), Enhanced (K), Intelligent (P), and Edge (E). The
# buttons show only pictures, so UI Automation gives them no text.
SERIES_BUTTONS = ("T", "F", "K", "P", "E")
# The text of a tile without its markup, such as
# "inch:2.4(240X320) Flash:4M RAM:3584B Frequency:48M".
_TILE = re.compile(r"inch:(\d+(?:\.\d+)?)\((\d+)X(\d+)\) Flash:(\S+) RAM:(\S+) Frequency:(\S+)")


def listed_model(series: str, text: str) -> dict:
    """Returns the model of `series` whose tile shows `text`. Raises
    ValueError when the text is not in the form the tool expects."""
    plain = re.sub(r"<[^>]*>", "", text).strip()
    found = _TILE.fullmatch(plain)
    if found is None:
        raise ValueError("a model's tile shows %r, which is not in the form the tool expects"
                         % plain)
    inch, width, height, flash, ram, frequency = found.groups()
    return {"series": series, "inch": float(inch), "width": int(width), "height": int(height),
            "flash": flash, "ram": ram, "frequency": frequency}


def models_of(shown: list) -> list:
    """Returns the models of `shown`, [(series, the texts of its tiles)], in
    the order the series were shown (listed_model).

    Raises ValueError when a series shows the same tiles as the series
    before it. That happens when pressing the series' button did not
    register, and the models of the previous series would then be listed
    twice. In the Nextion Editor 1.68.2, no two neighbouring series have the
    same tiles. Also raises ValueError for a tile whose text is not in the
    form the tool expects."""
    found = []
    for number, (series, texts) in enumerate(shown):
        if number > 0 and texts == shown[number - 1][1]:
            raise ValueError("after pressing the button of the %s series, the tiles of the %s "
                             "series still showed" % (series, shown[number - 1][0]))
        found += [listed_model(series, text) for text in texts]
    return found
