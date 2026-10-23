"""Smoothed shapes for a slider's round knob, a radio, a switch, a gauge's
needle and centre, a combo box's arrow, and a rounded progress bar:
ellipses, polygons, and rectangles with rounded corners.

Pillow draws the shapes SCALE times larger, with hard edges, each over the
ones before: a pixel of the larger picture is a sub-pixel, and each pixel
holds SCALE by SCALE of them. The picture is then shrunk by averaging each
pixel's sub-pixels. So each pixel takes the share of it each shape covers,
and the drawing blends by that share.

The Editor draws an ellipse meant to fill a box of `width` by `height`
inside it by half a pixel on the left and at the top, one and a half on the
right, and two and a half at the bottom (editor_ellipse): this fitted its
radios, their ring and their dot alike. A slider's round knob has a fit of
its own (slider_drawing.py, _round_knob). At SCALE times the size, these
offsets fall on whole sub-pixels.
"""
import functools
import math

from PIL import Image, ImageDraw

from nxwright.project.pictures import write_png

# How many sub-pixels across and down each pixel a shape is drawn at.
SCALE = 16
# The part of a picture its shapes reach is drawn SCALE times larger a band
# of rows at a time. Each band holds at most this many sub-pixels, 4 MB, or
# one row of pixels where a row holds more. Most shapes fit in one band.
_MOST_BAND_SUB_PIXELS = 1 << 20


def editor_ellipse(x: float, y: float, width: float, height: float) -> tuple:
    """Returns the box (left, top, right, bottom) of the ellipse the Editor
    draws for one meant to fill the box at (x, y), `width` by `height`."""
    return x + 0.5, y + 0.5, x + width - 1.5, y + height - 2.5


def grown(box: tuple, by: float) -> tuple:
    """Returns `box` grown by `by` on each side, or shrunk when it is negative:
    the outer and the inner edge of a pen 2 * `by` wide drawn along it."""
    left, top, right, bottom = box
    return left - by, top - by, right + by, bottom + by


class SmoothedPicture:
    """A clear picture `width` by `height`, on which shapes are drawn in turn,
    each over the ones before, their edges smoothed. Places are in pixels,
    from the picture's top-left corner, and colours are RGB."""

    def __init__(self, width: int, height: int):
        self.width, self.height = width, height
        # Each shape as the function that draws it, its place in sub-pixels,
        # the box in sub-pixels it stays within, and its colour.
        self._shapes = []

    def ellipse(self, box: tuple, colour: tuple):
        """Draws the ellipse fitting `box`, (left, top, right, bottom). An
        empty box draws nothing."""
        box = _in_sub_pixels(box)
        self._shapes.append((_draw_ellipse, box, box, colour))

    def polygon(self, points: list, colour: tuple):
        """Draws the polygon through `points`, (x, y) in turn."""
        # Pillow drops a point's fraction of a sub-pixel toward zero. In a
        # band below the point, where the point is negative, that rounds it
        # up, and in its own band down. So each point is moved to its whole
        # sub-pixel here, toward the top-left, alike in every band.
        points = [(math.floor(x * SCALE), math.floor(y * SCALE)) for x, y in points]
        xs, ys = [x for x, _ in points], [y for _, y in points]
        # Pillow takes the sub-pixels on the polygon's edges, its last ones
        # among them.
        within = (min(xs), min(ys), max(xs) + 1, max(ys) + 1)
        self._shapes.append((_draw_polygon, points, within, colour))

    def rounded_rectangle(self, box: tuple, radius: float, colour: tuple):
        """Draws the rectangle `box`, (left, top, right, bottom), its corners
        rounded by `radius`: the points of the box within `radius` of the
        box shrunk by `radius` on each side. A box narrower or lower than
        two roundings shrinks to the line `radius` in from its right or
        bottom edge, so it draws that end's rounding, cut by the box."""
        box = _in_sub_pixels(box)
        self._shapes.append((_draw_rounded_rectangle, (box, round(radius * SCALE)), box,
                             colour))

    def png(self, transpose: Image.Transpose = None) -> bytes:
        """Returns the PNG of the picture, turned or flipped by `transpose`,
        a PIL.Image.Transpose, when one is given."""
        picture = Image.new("RGBA", (self.width, self.height))
        reached = self._reached()
        if reached is not None:
            left, top, right, bottom = reached
            rows = max(1, _MOST_BAND_SUB_PIXELS // ((right - left) * SCALE * SCALE))
            for row in range(top, bottom, rows):
                band = Image.new("RGBA", ((right - left) * SCALE,
                                          (min(row + rows, bottom) - row) * SCALE))
                origin = (left * SCALE, row * SCALE)
                for draw_shape, place, _, colour in self._shapes:
                    draw_shape(band, origin, place, colour + (255,))
                picture.paste(band.reduce(SCALE), (left, row))
        if transpose is not None:
            picture = picture.transpose(transpose)
        return write_png(picture.width, picture.height, picture.tobytes())

    def _reached(self):
        """Returns the box of whole pixels, (left, top, right, bottom), within
        the picture, that the shapes stay within, or None when they reach
        none of its pixels."""
        if not self._shapes:
            return None
        lefts, tops, rights, bottoms = zip(*(within for _, _, within, _ in self._shapes))
        left, top = max(min(lefts) // SCALE, 0), max(min(tops) // SCALE, 0)
        right = min(-(-max(rights) // SCALE), self.width)
        bottom = min(-(-max(bottoms) // SCALE), self.height)
        return (left, top, right, bottom) if right > left and bottom > top else None


def _in_sub_pixels(box: tuple) -> tuple:
    """`box`, in pixels, in whole sub-pixels."""
    return tuple(round(edge * SCALE) for edge in box)


# Each function below draws a shape on `band`, a part of a picture SCALE
# times larger whose top-left sub-pixel is `origin` in the whole, in `ink`.
# Pillow draws a sub-pixel when its middle is about inside the shape: its
# rule differs from that along an edge by up to a sub-pixel. Its shapes take
# both their first and their last sub-pixel, so a box's right and bottom
# edges are given to it one sub-pixel in.

def _draw_ellipse(band: Image.Image, origin: tuple, box: tuple, ink):
    left, top, right, bottom = _moved(box, origin)
    if right > left and bottom > top:
        ImageDraw.Draw(band).ellipse((left, top, right - 1, bottom - 1), fill=ink)


def _draw_rectangle(band: Image.Image, origin: tuple, box: tuple, ink):
    left, top, right, bottom = _moved(box, origin)
    if right > left and bottom > top:
        ImageDraw.Draw(band).rectangle((left, top, right - 1, bottom - 1), fill=ink)


def _draw_polygon(band: Image.Image, origin: tuple, points: list, ink):
    ImageDraw.Draw(band).polygon([(x - origin[0], y - origin[1]) for x, y in points], fill=ink)


def _draw_rounded_rectangle(band: Image.Image, origin: tuple, place: tuple, ink):
    box, reach = place
    left, top, right, bottom = box
    # The box shrunk by the rounding, its left and top no further than its
    # right and bottom.
    inner_left, inner_top = min(left + reach, right - reach), min(top + reach, bottom - reach)
    inner_right, inner_bottom = right - reach, bottom - reach
    # The points within `reach` of it: itself grown across, and grown down,
    # and a disc around each of its corners.
    shape = Image.new("L", band.size)
    _draw_rectangle(shape, origin, (inner_left - reach, inner_top, inner_right + reach,
                                    inner_bottom), 255)
    _draw_rectangle(shape, origin, (inner_left, inner_top - reach, inner_right,
                                    inner_bottom + reach), 255)
    for x in (inner_left, inner_right):
        for y in (inner_top, inner_bottom):
            _draw_ellipse(shape, origin, grown((x, y, x, y), reach), 255)
    # Cut by the box, which a short box's rounding reaches past.
    cut = _moved(box, origin)
    band.paste(ink, cut, shape.crop(cut))


def _moved(box: tuple, origin: tuple) -> tuple:
    """`box` in a band whose top-left sub-pixel is `origin`."""
    left, top, right, bottom = box
    return left - origin[0], top - origin[1], right - origin[0], bottom - origin[1]


def polygon_picture(width: int, height: int, points: list, colour: tuple) -> bytes:
    """Returns the PNG of the polygon through `points` in `colour`, as RGB,
    on a clear picture `width` by `height`, its edge smoothed."""
    picture = SmoothedPicture(width, height)
    picture.polygon(points, colour)
    return picture.png()


def ellipse_picture(width: int, height: int, box: tuple, colour: tuple) -> bytes:
    """Returns the PNG of the ellipse fitting `box` in `colour`, as RGB, on a
    clear picture `width` by `height`, its edge smoothed."""
    picture = SmoothedPicture(width, height)
    picture.ellipse(box, colour)
    return picture.png()


# A rounding below this many pixels is drawn square, a progress bar's and a
# switch's alike, as the Editor drew `dis` 10 on a bar 30 high (1.45
# pixels); 3.6 was rounded.
LEAST_ROUNDING = 2


@functools.lru_cache(maxsize=256)
def rounded_bar(w: int, h: int, radius: float, filled: int, down: bool, back: tuple,
                fill: tuple) -> bytes:
    """Returns the PNG of a rounded progress bar, `w` by `h`, `filled` long
    from its start, clear around it: the back from a cap's width before the
    fill's end to the bar's other end, then the fill over it, each a
    rectangle half a pixel inside the bar's, its corners rounded by
    `radius`, its edges smoothed by the share of the pixel it covers."""
    length, breadth = (h, w) if down else (w, h)
    # Drawn along its length from where it fills, then turned when it runs up.
    picture = SmoothedPicture(length, breadth)
    start = max(filled - 2 * radius, 0) + 0.5 if filled else 0.5
    picture.rounded_rectangle((start, 0.5, length - 0.5, breadth - 0.5), radius, back)
    if filled:
        picture.rounded_rectangle((0.5, 0.5, filled - 0.5, breadth - 0.5), radius, fill)
    return picture.png(Image.Transpose.ROTATE_90 if down else None)
