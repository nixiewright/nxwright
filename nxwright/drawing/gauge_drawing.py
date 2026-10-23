"""Drawing a gauge: the background its `sta` chooses, as a text's (3, its
default, none), then its needle, then the disc at its middle.

The needle turns about the gauge's middle, at `val` degrees plus `format`:
0 points left, 90 up, 180 right, 270 down. It is a polygon, its edges
smoothed, through three widths: at its tip, `up` pixels from the middle, at
most half the gauge's height less a pixel (32767, `up`'s default, reaching
that); at its widest point, `left` pixels from the middle toward the tip;
and at its foot, `down` pixels back from the widest point. Its widths there
are `vvs0`, `vvs1`, and `vvs2` pixels each side of a pixel's middle: a
width of 1 draws a line one pixel wide. It is drawn in `pco`. The disc, of
`pco2`, is `hig` pixels across, smoothed, at the needle's middle: the
middle of the gauge's middle pixel. `hig` 0 draws none.

This matched the Editor's simulator (tests/fixtures/value-widgets/) on the
pixels it draws in one colour, and its smoothed edges come within the
smoothing, but for a few pixels at the needle's ends, where the Editor's
polygon differs most: at most one in 200 of a gauge, and most where the
widest point passes the foot (`left` past `down`). The background on each
`sta` matched the Editor's simulator too (tests/fixtures/drawing-assumptions/,
page6).

Not modelled, as no app has a use for them:
  - an `up` or `down` past 32767, which the Editor's panel shows negative,
    and its simulator drew as a short, thin outline of a needle. It is taken
    here as stored, so that such an `up` reaches as far as the tip can;
  - a `left` past the tip, which still drew a needle in the Editor's
    simulator, where none is drawn here. The Nextion Editor refuses a
    `left` past 1024, and so does the build.
"""
import functools
import math

from nxwright.drawing.smoothed_shapes import ellipse_picture, polygon_picture
from nxwright.project.pictures import data_url
from nxwright.project.screen_colours import rgb565_to_rgb

# `up` when the tip reaches as far as it can.
_AUTOMATIC = 32767


def paint_gauge(painter):
    """Paints a gauge: its background, its needle, and its disc."""
    values, box = painter.values, painter.box
    w, h = box["w"], box["h"]
    if w <= 0 or h <= 0 or painter.too_large(w, h, "the gauge"):
        return
    painter.background({0: "picc", 1: "bco", 2: "pic"})
    # The middle of the middle pixel, as the needle one pixel wide showed.
    centre = (w / 2 + 0.5, h / 2 + 0.5)
    longest = h / 2 - 1
    up = values.get("up", _AUTOMATIC)
    tip = longest if up == _AUTOMATIC else min(up, longest)
    widths = (values.get("vvs0", 0), values.get("vvs1", 0), values.get("vvs2", 0))
    needle = _needle_picture(w, h, centre, (values.get("val", 0) + values.get("format", 0)) % 360,
                             tip, values.get("left", 0), values.get("down", 0), widths,
                             rgb565_to_rgb(values.get("pco", 0)))
    painter.add("text", image=data_url(needle))
    across = values.get("hig", 0)
    if across > 0:
        left, top = centre[0] - across / 2, centre[1] - across / 2
        # Inside its square by half a pixel at the top and on the right, and
        # one at the bottom: the box that fitted the Editor's discs best.
        disc = (left, top + 0.5, left + across - 0.5, top + across - 1)
        painter.add("text", image=data_url(ellipse_picture(
            w, h, disc, rgb565_to_rgb(values.get("pco2", 0)))))


@functools.lru_cache(maxsize=64)
def _needle_picture(w: int, h: int, centre: tuple, degrees: int, tip: float, widest: float,
                    foot: float, widths: tuple, colour: tuple) -> bytes:
    """Returns the PNG of a gauge's needle, `w` by `h`, clear around it: the
    polygon from its tip, `tip` pixels from `centre` at `degrees`, through
    its widest point, `widest` pixels from it, to its foot, `foot` pixels
    back from there, `widths` each side at the three."""
    angle = math.radians(degrees)
    along = (-math.cos(angle), -math.sin(angle))
    side = (-along[1], along[0])

    def point(distance: float, offset: float) -> tuple:
        return (centre[0] + along[0] * distance + side[0] * offset,
                centre[1] + along[1] * distance + side[1] * offset)
    stops = ((tip, widths[0]), (widest, widths[1]), (widest - foot, widths[2]))
    # A width of n reaches n - 1 pixels each side of a middle pixel.
    points = [point(distance, width - 0.5) for distance, width in stops] + \
        [point(distance, 0.5 - width) for distance, width in reversed(stops)]
    return polygon_picture(w, h, points, colour)
