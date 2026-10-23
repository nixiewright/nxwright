"""Drawing a select: its lines repeating round from the one `val` picks, in
its middle, as page_drawing.py's opening comment says. The simulation reads
its defaults too (SELECT_DEFAULTS).
"""
from nxwright import NxwrightError
from nxwright.drawing.drawing_shared import PLACE, border_width, box_of
from nxwright.drawing.text_pictures import path_lines
from nxwright.project.screen_colours import rgb565_to_hex


# The attributes of a select that its drawing and the simulation read, at the
# type's defaults (component_defaults.toml), for a table marked
# defaults = false.
SELECT_DEFAULTS = {"w": 90, "h": 200, "sta": 1, "style": 0, "borderw": 2, "font": 0,
                   "bco": 0xFFFF, "pco": 0, "pco1": 31, "pco2": 31, "spax": 0, "hig": 42,
                   "dis": 1, "val": 0,
                   "path": "\r\n".join("%02d" % number for number in range(1, 13))}


def paint_select(painter):
    """Paints a select: its background and border, its lines repeating
    round from the one `val` picks in its middle, faded toward its top
    and bottom on a colour, and the middle's rules, as
    page_drawing.py's opening comment says."""
    painter.values = dict(SELECT_DEFAULTS, **painter.values)
    values = painter.values
    painter.background({0: "picc", 1: "bco", 2: "pic"})
    x, y, w, h = (painter.box[key] for key in PLACE)
    border = border_width(values)
    inside = box_of(x + border, y + border, w - 2 * border, h - 2 * border)
    lines = path_lines(values["path"])
    height = max(values["hig"], 1)
    middle = (h - height) // 2
    val = values["val"] if isinstance(values["val"], int) else 0
    try:
        font = painter.resources.font(values["font"]) if lines and w > 0 and h > 0 else None
    except NxwrightError as error:
        painter.note("its lines are not drawn: font %s: %s" % (values["font"], error))
        font = None
    if font is not None:
        # On a colour alone, the lines fade toward the top and bottom.
        fading = (lambda row: min(min(row - y, y + h - 1 - row) / height, 1)) \
            if values["sta"] == 1 else None
        reach = h // height + 2
        for step in range(-reach, reach + 1):
            top = middle + painter.moved + step * height
            if top + height <= 0 or top >= h:
                continue
            # A band the screen's right or bottom edge cuts has its line
            # placed in the part the screen shows.
            band = painter.before_screen_end(box_of(x, y + top, w, height))
            if band is None:
                continue
            # The line `val` picks is in `pco2` wherever it repeats.
            index = (val + step) % len(lines)
            chosen = index == val
            painter.text_within(lines[index], font,
                                {"xcen": 1, "ycen": 1, "spax": values["spax"]}, band,
                                values["pco2" if chosen else "pco"], inside, fading)
    if values["dis"] == 1:
        for row in (middle, middle + height - 1):
            if 0 <= row < h:
                painter.add("colour", box_of(x, y + row, w, 1),
                            colour=rgb565_to_hex(values["pco1"]))
    painter.border()
