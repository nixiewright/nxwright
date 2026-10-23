"""Drawing a waveform: its background, its grid, and its channels' points,
as page_drawing.py's opening comment says.
"""
from nxwright.drawing.drawing_shared import PLACE
from nxwright.project.screen_arithmetic import divide_toward_zero
from nxwright.project.screen_colours import rgb565_to_hex


def paint_waveform(painter):
    """Paints a waveform's background and grid."""
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
    percentage = painter.values.get("dis", 100)
    direction = painter.values.get("dir", 0)
    # Points `add` gave a channel past `ch` are kept, but not drawn.
    channels = painter.values.get("ch", 1)
    for channel, values in sorted(painter.waves.items()):
        if channel >= channels:
            continue
        shown = values[-w:] if direction in (1, 2) else values[-w:][::-1]
        # With `dir` 2, the points end at the right edge.
        first = w - len(shown) if direction == 2 else 0
        heights = [y + h - 1 - min(max(divide_toward_zero(value * percentage, 100), 0), h - 1)
                   for value in shown]
        # Each column holds its point, joined by a line up or down to
        # the height of the point before.
        points = []
        for column, height in enumerate(heights):
            previous = heights[column - 1] if column else height
            points += [(x + first + column, row)
                       for row in range(min(previous, height), max(previous, height) + 1)]
        painter.pixels(points, painter.values.get("pco%d" % channel, 0xffff))
