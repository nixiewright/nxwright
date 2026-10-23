"""Drawing a switch. A switch lies across, or stands up when its `dez` is
1; its breadth is its height across, its width standing up, and its length
the other.

It draws a pill of `bco` while off (`val` 0), of `bco2` while on, with
rounded ends: rounded by `dis` hundredths of half its breadth less a pixel,
half a pixel inside the switch, as a rounded progress bar is, and square
under LEAST_ROUNDING pixels (smoothed_shapes.py). Over it, a knob as wide as
the breadth, of `pco` while off and `pco2` while on, at the start, the left
or the top, while off, and at the end while on, one pixel further along:
each the Editor's ellipse of its square, inside it by half a pixel on the
left and at the top, one and a half on the right, and two and a half at
the bottom. Then its words, `txt` split at its first "/": the first while
off, the second while on, in the font `font` and the colour `pco1`, centred
in the part of the switch the knob leaves free. A `txt` with no "/" was not
seen; it shows whole in either state.

This matched the Editor's simulator (tests/fixtures/value-widgets/) on the
pixels it draws in one colour; its smoothed edges come within the
smoothing.
"""
from nxwright.drawing.smoothed_shapes import (LEAST_ROUNDING, editor_ellipse, ellipse_picture,
                                              rounded_bar)
from nxwright.project.pictures import data_url
from nxwright.project.screen_colours import rgb565_to_hex, rgb565_to_rgb

_UPRIGHT = 1


def paint_switch(painter):
    """Paints a switch: its pill, its knob, and its words."""
    values, box = painter.values, painter.box
    x, y, w, h = box["x"], box["y"], box["w"], box["h"]
    if w <= 0 or h <= 0 or painter.too_large(w, h, "the switch"):
        return
    on = values.get("val", 0) != 0
    upright = values.get("dez", 0) == _UPRIGHT
    breadth, length = (w, h) if upright else (h, w)
    back = values.get("bco2" if on else "bco", 0)
    radius = min(max(values.get("dis", 0), 0), 100) / 100 * (breadth - 1) / 2
    if radius < LEAST_ROUNDING:
        painter.add("colour", colour=rgb565_to_hex(back))
    else:
        colour = rgb565_to_rgb(back)
        painter.add("text", image=data_url(rounded_bar(w, h, radius, 0, upright, colour,
                                                       colour)))
    start = length - breadth + 1 if on else 0
    knob = editor_ellipse(0, start, breadth, breadth) if upright else \
        editor_ellipse(start, 0, breadth, breadth)
    painter.add("text", image=data_url(ellipse_picture(
        w, h, knob, rgb565_to_rgb(values.get("pco2" if on else "pco", 0)))))
    words = str(values.get("txt", "")).split("/", 1)
    word = words[-1] if on else words[0]
    free_start = 0 if on else breadth
    free = {"x": x, "y": y + free_start, "w": w, "h": h - breadth} if upright else \
        {"x": x + free_start, "y": y, "w": w - breadth, "h": h}
    if free["w"] > 0 and free["h"] > 0:
        painter.text(word, free, dict(values, pco=values.get("pco1", 0), xcen=1, ycen=1))
