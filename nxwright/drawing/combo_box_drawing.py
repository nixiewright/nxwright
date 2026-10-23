"""Drawing a combo box: a box showing the chosen item's text, `txt`, and,
while its list is open (`down` 1), the list of its items, the lines of
`path`, as the Editor's simulator draws them (tests/fixtures/combo-box/).

The box. With `style` 0 and a colour background (`sta` 1), it is a
rectangle half a pixel inside the component, its corners rounded
(corner_radius) and its edges smoothed; `dis` 0 draws it square, of whole
pixels. A border (`style` 1) or a 3D style draws it square, as a text's;
so does a picture background, as the Editor's simulator drew one rounded
by `dis` 40 (tests/fixtures/drawing-assumptions/, page7). Its text is
placed as a text component's. With `up` 1, an arrow in `pco3` pointing
the way the list opens (`dir`) is drawn over the text: a triangle of a
fixed size near the right edge, or near the left one for a list opening
left (arrow_points).

The list (list_layout) lies `vvs0` from the box, below it, above it, or
beside it, as `dir` says, the first item first whichever way it opens. It
shows `qty` items at most, each `hig` long and `vvs0` apart, rounded by
`dis` as a box without a border is, a box with a border too, in `bco1`
and `pco1`, the chosen one (`val`) in `bco2` and `pco2`, its text placed
by `xcen` and `ycen`. An item the screen's edge cuts is drawn at its full
size, cut by the edge. At the screen's right or bottom edge, its text is
placed in the part the screen shows; at its left or top edge, in the whole
item, so that a text wider than the item starts at the item's left, its
end showing. So the Editor's simulator drew them
(tests/fixtures/drawing-assumptions/, page7, page10, and page22). Its
lists cut at the top showed no text either way; a select cut there
settles the top edge (page_drawing.py). When there are
more items than `qty`, a scroll mark `wid` long, `vvs1` from the items,
shows at each end, by `mode`: 2 a rounded bar of `bco1` with an arrow of
`pco1`, 1 the arrow alone in `bco1`, and 0 nothing, without room kept for
it. It shows the items from `val`, or the last `qty` of them when `val` is
that near the end; a simulation that has scrolled it gives its first item
shown. The list is drawn with its box, in ID order, so that a component
later in the page's order draws over it, as on the screen.
"""
from dataclasses import dataclass
import math

from nxwright.drawing.smoothed_shapes import LEAST_ROUNDING, polygon_picture, rounded_bar
from nxwright.drawing.text_pictures import path_lines
from nxwright.project.pictures import data_url
from nxwright.project.screen_colours import rgb565_to_hex, rgb565_to_rgb

# Which way the list opens, `dir`, and so which way an arrow points.
UP, DOWN, LEFT, RIGHT = 0, 1, 2, 3
# What shows that the list scrolls, `mode`.
NO_MARK, ARROW_MARK, BAR_MARK = 0, 1, 2
# The attributes the list's layout reads, at the type's defaults
# (component_defaults.toml), for a table marked defaults = false.
DEFAULTS = {"qty": 4, "hig": 42, "vvs0": 8, "vvs1": 2, "wid": 12, "mode": BAR_MARK,
            "val": 0, "dis": 25, "up": 1}
# Two places a pixel short of the rest, as the Editor's simulator drew
# them: the list opening right lies a pixel less than `vvs0` from the box,
# and the last scroll mark of a list opening down a pixel nearer its items
# than `vvs1`.
_A_PIXEL_SHORT = 1
# The room an arrow's picture takes around its centre.
_ARROW_REACH = 7


def value(values: dict, attribute: str) -> int:
    """A combo box's `attribute`, its type's default when `values` lack it."""
    return values.get(attribute, DEFAULTS[attribute])


def direction(values: dict) -> int:
    """Which way the list opens: `dir`, UP, DOWN, LEFT, or RIGHT; DOWN, the
    type's default, for any other value."""
    number = values.get("dir", DOWN)
    return number if number in (UP, DOWN, LEFT, RIGHT) else DOWN


def items(values: dict) -> list:
    """The items to choose from: the lines of `path`, none when it is empty."""
    return path_lines(values.get("path", ""))


def corner_radius(width: int, height: int, dis: int) -> int:
    """The radius of the rounded corners of a box `width` by `height`: `dis`
    percent of half its shorter side, rounded up, and at most half that side
    less a pixel. The Editor's simulator drew 28 boxes so, from 24 to 100
    pixels high and `dis` 5 to 100."""
    side = min(width, height)
    return max(min(math.ceil(min(max(dis, 0), 100) * side / 200), (side - 1) // 2), 0)


def arrow_points(pointing: int, x: int, y: int) -> list:
    """The corners of an arrow pointing `pointing` (UP, DOWN, LEFT, RIGHT),
    centred near the pixel (x, y), in a pixel's own coordinates, where
    (x, y) is that pixel's middle. The Editor's simulator drew each the
    same at every size: 12 pixels across and 6 deep."""
    return {DOWN: [(x - 6, y - 3), (x + 6, y - 3), (x, y + 3)],
            UP: [(x - 6, y + 2), (x + 6, y + 2), (x, y - 4)],
            LEFT: [(x + 3, y - 6), (x + 3, y + 6), (x - 3, y)],
            RIGHT: [(x - 3, y - 6), (x - 3, y + 6), (x + 3, y)]}[pointing]


@dataclass(frozen=True)
class ListLayout:
    """Where an open list's parts lie on the page."""
    first: int          # the number of the first item shown
    items: tuple        # ((item number, box), ...) of the items shown, in order
    marks: tuple        # ((box, the way its arrow points), ...): a scroll mark at each end
    area: dict          # the list's whole rectangle, which touches reach the box by


def list_layout(values: dict, count: int, first: int = None) -> ListLayout:
    """Returns where the open list of a combo box with the attributes
    `values` and `count` items lies, showing items from `first`, or as the
    module's docstring says when None; None when it has no items."""
    if count <= 0:
        return None
    pointing = direction(values)
    sideways = pointing in (LEFT, RIGHT)
    shown = min(max(value(values, "qty"), 1), count)
    first = min(max(value(values, "val") if first is None else first, 0), count - shown)
    hig, gap = value(values, "hig"), value(values, "vvs0")
    marked = count > shown and value(values, "mode") != NO_MARK
    wid, mark_gap = (value(values, "wid"), value(values, "vvs1")) if marked else (0, 0)
    length = shown * hig + (shown - 1) * gap + 2 * (wid + mark_gap)
    x, y, w, h = values["x"], values["y"], values["w"], values["h"]
    start = {DOWN: y + h + gap, UP: y - gap - length, RIGHT: x + w + gap - _A_PIXEL_SHORT,
             LEFT: x - gap - length}[pointing]
    if marked and pointing == DOWN:
        length -= _A_PIXEL_SHORT

    def box(along: int, size: int) -> dict:
        return {"x": along, "y": y, "w": size, "h": h} if sideways else \
            {"x": x, "y": along, "w": w, "h": size}
    item_start = start + wid + mark_gap
    item_boxes = tuple((first + index, box(item_start + index * (hig + gap), hig))
                       for index in range(shown))
    marks = ()
    if marked:
        ends = (LEFT, RIGHT) if sideways else (UP, DOWN)
        marks = ((box(start, wid), ends[0]), (box(start + length - wid, wid), ends[1]))
    return ListLayout(first, item_boxes, marks, box(start, length))


def paint_combo_box(painter):
    """Paints a combo box: its box, its text, its arrow, and its list when
    open."""
    values, box = painter.values, painter.box
    if box["w"] <= 0 or box["h"] <= 0:
        return
    if values.get("style", 0) == 0 and values.get("sta", 1) == 1:
        _rounded(painter, box, values.get("bco", 0), value(values, "dis"))
        painter.text()
    else:
        painter.text_component()
    pointing = direction(values)
    if value(values, "up") == 1:
        middle = box["y"] + box["h"] // 2
        across = box["x"] + 10 if pointing == LEFT else box["x"] + box["w"] - 11
        _arrow(painter, pointing, across, middle, values.get("pco3", 0))
    if values.get("down") == 1:
        _paint_list(painter)


def _paint_list(painter):
    """Paints the open list: its items, and its scroll marks by `mode`."""
    values = painter.values
    lines = items(values)
    layout = list_layout(values, len(lines), painter.scrolled)
    if layout is None:
        return
    dis, chosen = value(values, "dis"), value(values, "val")
    for number, box in layout.items:
        back, ink = ("bco2", "pco2") if number == chosen else ("bco1", "pco1")
        _rounded(painter, box, values.get(back, 0), dis)
        # An item the screen's right or bottom edge cuts has its text placed
        # in the part shown.
        shown = painter.before_screen_end(box)
        if shown is not None:
            painter.text(lines[number], shown, dict(values, pco=values.get(ink, 0)))
    mode = value(values, "mode")
    for box, pointing in layout.marks:
        if mode == BAR_MARK:
            _rounded(painter, box, values.get("bco1", 0), dis)
        ink = values.get("pco1" if mode == BAR_MARK else "bco1", 0)
        _arrow(painter, pointing, box["x"] + box["w"] // 2, box["y"] + box["h"] // 2, ink)


def _rounded(painter, box: dict, colour: int, dis: int):
    """Paints `box` in `colour`, a 16-bit colour, rounded by `dis`
    (corner_radius) and smoothed, or square of whole pixels below a radius
    of LEAST_ROUNDING, as a scroll bar 8 high was."""
    if box["w"] <= 0 or box["h"] <= 0 or painter.too_large(box["w"], box["h"], "the combo box"):
        return
    radius = corner_radius(box["w"], box["h"], dis)
    if radius < LEAST_ROUNDING:
        painter.add("colour", box, colour=rgb565_to_hex(colour))
        return
    rgb = rgb565_to_rgb(colour)
    painter.add("text", box, image=data_url(rounded_bar(box["w"], box["h"], radius, 0, False,
                                                        rgb, rgb)))


def _arrow(painter, pointing: int, x: int, y: int, colour: int):
    """Paints an arrow pointing `pointing`, centred near the pixel (x, y),
    in `colour`, a 16-bit colour."""
    reach = _ARROW_REACH
    corner = (x - reach, y - reach)
    # The pixel's middle is half a pixel into it.
    points = [(across - corner[0] + 0.5, down - corner[1] + 0.5)
              for across, down in arrow_points(pointing, x, y)]
    side = 2 * reach + 1
    painter.add("text", {"x": corner[0], "y": corner[1], "w": side, "h": side},
                image=data_url(polygon_picture(side, side, points, rgb565_to_rgb(colour))))
