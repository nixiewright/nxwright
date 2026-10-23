"""Drawing a slider: its track, the part of it filled, and its knob, as
page_drawing.py's opening comment says.
"""
import functools

from nxwright.drawing.drawing_shared import NO_RESOURCE, box_of
from nxwright.drawing.smoothed_shapes import LEAST_ROUNDING, ellipse_picture, rounded_bar
from nxwright.project.pictures import data_url
from nxwright.project.screen_colours import rgb565_to_hex, rgb565_to_rgb


@functools.lru_cache(maxsize=64)
def _round_knob(w: int, h: int, colour: tuple) -> bytes:
    """Returns the PNG of a slider's round knob, `w` by `h`, clear around it,
    its edge smoothed by the share of each pixel it covers. The ellipse is
    inside its box by 13/16 of a pixel on the left, 7/8 at the top, 11/16 on
    the right, and 1 5/8 at the bottom. This fitted the Editor's knobs of 11
    to 81 pixels best, their edges within the smoothing."""
    return ellipse_picture(w, h, (0.8125, 0.875, w - 0.6875, h - 1.625), colour)


def drawn_knob_size(size: int, psta: int) -> int:
    """Returns the size, along a slider's track or across it, at which the
    Editor draws and places a knob of `size`, whose look is `psta`. A round
    knob's even size counts one less, given or chosen by the Editor, so
    that a knob 40 high is drawn 39 high. A picture's (`psta` 1) or a
    square's (2) counts whole."""
    if psta in (1, 2) or size % 2:
        return size
    return max(size - 1, 0)


def paint_slider(painter):
    """Paints a slider: its track, the filled part, and the knob."""
    values, box = painter.values, painter.box
    vertical = values.get("mode") == 1
    length, breadth = (box["h"], box["w"]) if vertical else (box["w"], box["h"])
    knob_along, knob_across = _knob_size(painter, breadth, vertical)
    span = values.get("maxval", 100) - values.get("minval", 0)
    share = (values.get("val", 0) - values.get("minval", 0)) / span if span else 0
    # Cut toward zero: the Editor drew a knob half way along a span of
    # 215 pixels from 107.
    start = int(min(max(share, 0), 1) * max(length - knob_along, 0))
    if painter.scrolled is not None:
        # Where a touch put the knob, which `scrolled` carries for a slider
        # (Simulation._slide), kept on the track though code shrank it.
        start = min(max(painter.scrolled, 0), max(length - knob_along, 0))
    middle = start + knob_along // 2
    side = (breadth - knob_across) // 2
    if vertical:
        # Filled from the bottom: the knob's start counts up from there.
        filled = dict(box, y=box["y"] + length - middle, h=middle)
        knob = {"x": box["x"] + side, "y": box["y"] + length - start - knob_along,
                "w": knob_across, "h": knob_along}
    else:
        filled = dict(box, w=middle)
        knob = {"x": box["x"] + start, "y": box["y"] + side,
                "w": knob_along, "h": knob_across}
    if values.get("sta") == 1:
        _colour_track(painter, length, breadth, middle, vertical)
    else:
        painter.background({0: "picc", 2: "pic"})
        painter.background({0: "picc1", 2: "pic1"}, filled)
    if knob["w"] <= 0 or knob["h"] <= 0:
        return          # `wid` or `hig` 0: no knob
    if values.get("psta") == 1:
        painter.picture("pic2", (0, 0), knob)
    elif values.get("psta") == 2:
        painter.add("colour", knob, colour=rgb565_to_hex(values.get("pco", 0)))
    else:
        colour = rgb565_to_rgb(values.get("pco", 0))
        painter.add("text", knob, image=data_url(_round_knob(knob["w"], knob["h"], colour)))


def _colour_track(painter, length: int, breadth: int, middle: int, vertical: bool):
    """Paints a slider's colour track, as page_drawing.py's opening comment
    says: a progress bar one pixel inside the slider, filled to the knob's
    middle."""
    values, box = painter.values, painter.box
    across = breadth * min(max(values.get("ch", 25), 0), 100) // 100
    # One pixel inside the slider at its start, and at its end across, or
    # two at its bottom down, as the Editor drew them; filled to the
    # knob's middle.
    along = length - (3 if vertical else 2)
    if across <= 0 or along <= 0:
        return          # `ch` 0, or a slider too short: no track
    filled = min(max(middle - (2 if vertical else 1), 0), along)
    offset = (breadth - across) // 2
    if vertical:
        track = box_of(box["x"] + offset, box["y"] + 1, across, along)
        fill_box = box_of(track["x"], track["y"] + along - filled, across, filled)
        rest_box = box_of(track["x"], track["y"], across, along - filled)
    else:
        track = box_of(box["x"] + 1, box["y"] + offset, along, across)
        fill_box = box_of(track["x"], track["y"], filled, across)
        rest_box = box_of(track["x"] + filled, track["y"], along - filled, across)
    radius = min(min(max(values.get("dis", 100), 0), 100) / 100 * (across - 1),
                 (across - 1) / 2)
    back, fill = (rgb565_to_rgb(values.get(colour, 0)) for colour in ("bco", "bco1"))
    if radius < LEAST_ROUNDING:
        for part, colour in ((rest_box, back), (fill_box, fill)):
            if part["w"] > 0 and part["h"] > 0:
                painter.add("colour", part, colour="#%02x%02x%02x" % colour)
        return
    painter.add("text", track, image=data_url(rounded_bar(
        track["w"], track["h"], radius, filled, vertical, back, fill)))


def _knob_size(painter, breadth: int, vertical: bool) -> tuple:
    """Returns a slider knob's size along the track and across it, as it is
    drawn (drawn_knob_size): `wid` and `hig`, where 255 stands for the knob
    picture's size, or the slider's breadth for a coloured knob."""
    psta, size = painter.values.get("psta"), None
    if psta == 1:
        size = painter.resources.picture_size(painter.values.get("pic2", NO_RESOURCE))
    size = size or (breadth, breadth)
    width = size[0] if painter.values.get("wid", 255) == 255 else painter.values["wid"]
    height = size[1] if painter.values.get("hig", 255) == 255 else painter.values["hig"]
    width, height = drawn_knob_size(width, psta), drawn_knob_size(height, psta)
    return (height, width) if vertical else (width, height)
