"""The Editor's list of screen models: what `editor.py models` reads of the
device settings, where the Editor shows a tile for each model of a series
(README.md). It drives no Editor and imports no pywinauto, so that its tests
run with nxwright's own Python.

UI Automation gives a tile's text, its size and memory, but not the model's
name, which the Editor draws apart. So a model is given by its series and
its tile's text. `editor.py models` writes the list as JSON:

    {"editor_version": "1.68.2.3035",
     "models": [{"series": "T", "inch": 2.4, "width": 240, "height": 320,
                 "flash": "4M", "ram": "3584B", "frequency": "48M"}]}
"""
import re

# The series of the device settings' buttons, in their order from the left:
# Basic, Discovery, Enhanced, Intelligent, and Edge. UI Automation gives the
# buttons no names, only pictures.
SERIES_BUTTONS = ("T", "F", "K", "P", "E")
# A tile's text, once its markup is left out, such as
# "inch:2.4(240X320) Flash:4M RAM:3584B Frequency:48M".
_TILE = re.compile(r"inch:(\d+(?:\.\d+)?)\((\d+)X(\d+)\) Flash:(\S+) RAM:(\S+) Frequency:(\S+)")


def listed_model(series: str, text: str) -> dict:
    """Returns the model of `series` whose tile shows `text`. Raises
    ValueError for a text of another form."""
    plain = re.sub(r"<[^>]*>", "", text).strip()
    found = _TILE.fullmatch(plain)
    if found is None:
        raise ValueError("a model's tile shows %r, which the tool does not read" % plain)
    inch, width, height, flash, ram, frequency = found.groups()
    return {"series": series, "inch": float(inch), "width": int(width), "height": int(height),
            "flash": flash, "ram": ram, "frequency": frequency}


def models_of(shown: list) -> list:
    """Returns the models of `shown`, [(series, the texts of its tiles)], in
    the order the series were shown (listed_model). Raises ValueError when a
    series shows the tiles of the series shown before it, as when its
    button's press did not take: the tiles of the series before would be
    given under two series. In the Nextion Editor 1.68.2, no series has the
    tiles of the one before it. Raises ValueError too for a tile's text of
    another form."""
    found = []
    for number, (series, texts) in enumerate(shown):
        if number > 0 and texts == shown[number - 1][1]:
            raise ValueError("pressing the %s series' button left the %s series' tiles"
                             % (series, shown[number - 1][0]))
        found += [listed_model(series, text) for text in texts]
    return found
