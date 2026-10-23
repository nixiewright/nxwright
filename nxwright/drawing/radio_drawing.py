"""Drawing a radio: a disc as wide as the radio, at its top left corner,
filled with `bco` and ringed by a pen a pixel wide in the dark colour of a
3D style's edge; when `val` is 1, a dot of `pco` half as wide, at the same
middle. A radio wider than high draws its disc past its bottom. Both are
ellipses as the Editor draws them, inside their boxes by half a pixel on
the left and at the top, one and a half on the right, and two and a half
at the bottom (smoothed_shapes.py), with smoothed edges.

This matched the Editor's simulator (tests/fixtures/value-widgets/) on the
pixels it draws in one colour; its smoothed edges come within the
smoothing, its dot's edges least closely.
"""
import functools

from nxwright.drawing.smoothed_shapes import SmoothedPicture, editor_ellipse, grown
from nxwright.project.pictures import data_url
from nxwright.project.screen_colours import rgb565_to_rgb

# The ring's pen, half a pixel each side of the ellipse.
_HALF_PEN = 0.5


def paint_radio(painter):
    """Paints a radio: its ring, its fill, and its dot when `val` is 1."""
    values, box = painter.values, painter.box
    width = box["w"]
    if width <= 0 or painter.too_large(width, width, "its disc"):
        return
    dark, _ = painter.edge_colours()
    picture = _radio_picture(width, rgb565_to_rgb(values.get("bco", 0)), dark,
                             rgb565_to_rgb(values.get("pco", 0)) if values.get("val", 0) else None)
    painter.add("text", {"x": box["x"], "y": box["y"], "w": width, "h": width},
                image=data_url(picture))


@functools.lru_cache(maxsize=64)
def _radio_picture(width: int, fill: tuple, ring: tuple, dot) -> bytes:
    """Returns the PNG of a radio `width` pixels wide and high, clear around
    its disc: the disc of `fill`, its ring of `ring`, and the dot of `dot`,
    or none when `dot` is None, each colour as RGB."""
    disc = editor_ellipse(0, 0, width, width)
    picture = SmoothedPicture(width, width)
    # The ring is what the fill, drawn over it, leaves of the disc grown by
    # the pen's half.
    picture.ellipse(grown(disc, _HALF_PEN), ring)
    picture.ellipse(grown(disc, -_HALF_PEN), fill)
    if dot:
        picture.ellipse(editor_ellipse(width / 4, width / 4, width / 2, width / 2), dot)
    return picture.png()
