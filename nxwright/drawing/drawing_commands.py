"""Painting what drawing commands painted on a page, such as `fill`, `line`,
or `xstr`, as page_drawing.py's opening comment says (CommandPainter).
page_drawing.py replays them in order, each through the page's painter,
drawing again between them a component that code changed.
"""
from nxwright import NxwrightError
from nxwright.drawing.drawing_shared import MOST_PICTURE_PIXELS, box_of
from nxwright.drawing.text_pictures import lacking_note, text_picture
from nxwright.project.pictures import data_url, write_png
from nxwright.project.screen_colours import rgb565_to_hex, rgb565_to_rgb


class CommandPainter:
    """Paints what drawing commands painted, as shapes of the page's, through
    `painter`, a ComponentPainter around the page, whose shared methods
    every component's drawing uses too."""

    def __init__(self, painter):
        self.painter = painter

    def paint(self, command: str, arguments: list, spacing: tuple):
        """Paints what one drawing command painted, from its arguments as
        the test machine records them."""
        if command == "cls":
            drawing = self.painter.drawing
            self.painter.add("colour", box_of(0, 0, drawing["width"], drawing["height"]),
                             colour=rgb565_to_hex(arguments[0]))
        elif command == "fill":
            x, y, w, h, colour = arguments
            self.painter.add("colour", box_of(x, y, w, h), colour=rgb565_to_hex(colour))
        elif command == "draw":
            x1, y1, x2, y2, colour = arguments
            left, top, right, bottom = min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)
            for side in ((left, top, right - left + 1, 1), (left, bottom, right - left + 1, 1),
                         (left, top, 1, bottom - top + 1), (right, top, 1, bottom - top + 1)):
                self.painter.add("colour", box_of(*side), colour=rgb565_to_hex(colour))
        elif command == "line":
            x1, y1, x2, y2, colour = arguments
            self.painter.pixels(_line_points(x1, y1, x2, y2), colour)
        elif command in ("cir", "cirs"):
            x, y, radius, colour = arguments
            drawing = self.painter.drawing
            self.painter.pixels(_circle_points(x, y, radius, command == "cirs", drawing["width"],
                                               drawing["height"]), colour)
        elif command == "pic":
            x, y, picture_id = arguments
            size = self.painter.resources.picture_size(picture_id) or (0, 0)
            self._picture_of(picture_id, (0, 0), box_of(x, y, *size))
        elif command == "picq":
            x, y, w, h, picture_id = arguments
            self._picture_of(picture_id, (x, y), box_of(x, y, w, h))
        elif command == "xpic":
            x, y, w, h, source_x, source_y, picture_id = arguments
            self._picture_of(picture_id, (source_x, source_y), box_of(x, y, w, h))
        elif command == "xstr":
            self._xstr(*arguments, spacing=spacing)

    def _picture_of(self, picture_id: int, corner: tuple, box: dict):
        """Paints over `box` the picture `picture_id`, its pixel `corner` at
        the box's corner, or notes why it cannot."""
        self.painter.picture_by_id(picture_id, corner, box, "picture")

    def _xstr(self, x, y, w, h, font_id, pco, bco, xcen, ycen, sta, text, spacing):
        box = box_of(x, y, w, h)
        if sta == 0:
            self._picture_of(bco, (x, y), box)
        elif sta == 1:
            self.painter.add("colour", box, colour=rgb565_to_hex(bco))
        elif sta == 2:
            self._picture_of(bco, (0, 0), box)
        if not text or not 0 < w * h <= MOST_PICTURE_PIXELS:
            return
        try:
            font = self.painter.resources.font(font_id)
            pixels = text_picture(text, font, self.painter.resources.encoding,
                                  {"xcen": xcen, "ycen": ycen, "spax": spacing[0],
                                   "spay": spacing[1]}, w, h, rgb565_to_rgb(pco))
            lacking = lacking_note(text, font, self.painter.resources.encoding)
        except NxwrightError as error:
            self.painter.note("xstr %r: %s" % (text, error))
            return
        if lacking:
            self.painter.note("xstr %r: %s" % (text, lacking))
        self.painter.add("text", box, image=data_url(write_png(w, h, pixels)))


# The screen's coordinates are 16-bit: a line's ends, and a circle's radius,
# are held within this, so that a mistaken huge one cannot stall the drawing.
_FARTHEST = 65535


def _line_points(x1: int, y1: int, x2: int, y2: int) -> list:
    """Returns the pixels of a line from end to end, both included: a pixel
    per step along its longer side, from its start, the other coordinate
    moving as _moved says."""
    x1, y1, x2, y2 = (max(-_FARTHEST, min(value, _FARTHEST)) for value in (x1, y1, x2, y2))
    dx, dy = x2 - x1, y2 - y1
    steps = max(abs(dx), abs(dy))
    if steps == 0:
        return [(x1, y1)]
    return [(x1 + _moved(step, dx, steps), y1 + _moved(step, dy, steps))
            for step in range(steps + 1)]


def _moved(step: int, change: int, steps: int) -> int:
    """How far a line's coordinate that changes by `change` over its `steps`
    has moved at `step`, toward the change's sign: the largest whole number
    below the next step's share of the change. Along the longer side, that
    is `step` itself."""
    if change == 0:
        return 0
    return (1 if change > 0 else -1) * (((step + 1) * abs(change) - 1) // steps)


def _circle_points(centre_x: int, centre_y: int, radius: int, filled: bool,
                   width: int = _FARTHEST, height: int = _FARTHEST) -> list:
    """Returns the pixels of a circle of `radius` around its centre, as the
    midpoint method steps, or of the disc it bounds when `filled`. A disc's
    pixels are only those within a `width` by `height` page."""
    if radius < 0:
        return []
    radius = min(radius, _FARTHEST)
    edge, x, y, decision = set(), radius, 0, 1 - radius
    while x >= y:
        for a, b in ((x, y), (y, x), (-y, x), (-x, y), (-x, -y), (-y, -x), (y, -x), (x, -y)):
            edge.add((centre_x + a, centre_y + b))
        y += 1
        if decision < 0:
            decision += 2 * y + 1
        else:
            x -= 1
            decision += 2 * (y - x) + 1
    if not filled:
        return sorted(edge)
    rows = {}
    for x, y in edge:
        if 0 <= y < height:
            low, high = rows.get(y, (x, x))
            rows[y] = (min(low, x), max(high, x))
    return [(x, y) for y, (low, high) in rows.items()
            for x in range(max(low, 0), min(high, width - 1) + 1)]
