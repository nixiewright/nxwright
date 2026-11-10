"""Drawing a waveform: its background, its grid, and its channels' points,
as page_drawing.py's opening comment says.

A channel is a shape of its own kind, "wave", which gives the channel's
points rather than their pixels. So the simulator's panel can paint new
points without a drawing of the whole page. wave_pixels gives the pixels of
a "wave" shape, for the pictures nxwright paints itself
(screen_pictures.py). The webviews paint the same pixels
(editors/vscode/media/wave-painter.mjs), and both are checked against
tests/fixtures/wave-painter/cases.json.
"""
from nxwright.drawing.drawing_shared import PLACE
from nxwright.project.screen_arithmetic import divide_toward_zero
from nxwright.project.screen_colours import rgb565_to_hex


def paint_waveform(painter):
    """Paints a waveform's background, its grid, and its channels."""
    painter.background({0: "picc", 1: "bco", 2: "pic"})
    x, y, w, h = (painter.box[key] for key in PLACE)
    colour = rgb565_to_hex(painter.values.get("gdc", 0))
    across, down = painter.values.get("gdw", 0), painter.values.get("gdh", 0)
    lines = []
    if across > 0:
        lines += [(x + step, y, 1, h) for step in range(0, w, across)]
    if down > 0:
        lines += [(x, y + step, w, 1) for step in range(h - 1, -1, -down)]
    for line in lines:
        painter.add("colour", dict(zip(PLACE, line)), colour=colour)
    paint_channels(painter)


def paint_channels(painter):
    """Adds a "wave" shape for each of a waveform's channels, over the
    waveform's box: the channel's colour, its latest points, oldest first,
    as many as the waveform is wide at most, and the waveform's `dis` and
    `dir`. A channel without points gets a shape too, which paints nothing.
    That shape keeps the channel's place among the drawing's shapes, for
    points sent on their own later (page_drawing.draw_waves)."""
    width = max(painter.box["w"], 0)
    # Points `add` gave a channel past `ch` are kept, but not drawn.
    for channel in range(painter.values.get("ch", 1)):
        values = painter.waves.get(channel, [])
        painter.add("wave", colour=rgb565_to_hex(painter.values.get("pco%d" % channel, 0xffff)),
                    points=list(values[-width:]) if width else [],
                    dis=painter.values.get("dis", 100), dir=painter.values.get("dir", 0))


def wave_pixels(width: int, height: int, points: list, dis: int, direction: int) -> list:
    """Returns the pixels of a channel of a waveform `width` by `height`,
    as [(column, row)] from the waveform's top left corner, in column
    order. `points` are the channel's values, oldest first; `dis` and
    `direction` are the waveform's `dis` and `dir`.

    A value of v is drawn v * dis / 100 pixels up from the bottom row, cut
    toward zero, and kept within the waveform. With `dir` 0, the latest
    point is in the first column, and the older ones follow to its right.
    With `dir` 1 or 2, the oldest point shown is first; with `dir` 2, the
    points end at the right edge. Each column holds its point, joined by a
    line up or down to the height of the point in the column before."""
    if width <= 0 or height <= 0:
        return []
    shown = points[-width:] if direction in (1, 2) else points[-width:][::-1]
    first = width - len(shown) if direction == 2 else 0
    rows = [height - 1 - min(max(divide_toward_zero(value * dis, 100), 0), height - 1)
            for value in shown]
    pixels = []
    for column, row in enumerate(rows):
        previous = rows[column - 1] if column else row
        pixels += [(first + column, each)
                   for each in range(min(previous, row), max(previous, row) + 1)]
    return pixels
