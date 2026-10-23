"""Drawing a progress bar, of pictures or of colours, square or rounded, as
page_drawing.py's opening comment says.
"""
from nxwright.drawing.drawing_shared import PLACE, box_of
from nxwright.drawing.smoothed_shapes import LEAST_ROUNDING, rounded_bar
from nxwright.project.pictures import data_url
from nxwright.project.screen_colours import rgb565_to_hex, rgb565_to_rgb


def paint_progress_bar(painter):
    """Paints a progress bar: the part `val` of 100 filled, from the left,
    or from the bottom when `dez` is 1, as page_drawing.py's opening
    comment says."""
    values = painter.values
    x, y, w, h = (painter.box[key] for key in PLACE)
    down = values.get("dez") == 1
    filled = (h if down else w) * min(max(values.get("val", 0), 0), 100) // 100
    if down:
        fill_box, rest_box = box_of(x, y + h - filled, w, filled), box_of(x, y, w, h - filled)
    else:
        fill_box, rest_box = box_of(x, y, filled, h), box_of(x + filled, y, w - filled, h)
    parts = [(rest_box, "bpic", "bco"), (fill_box, "ppic", "pco")]
    if values.get("sta") == 1:
        # Each picture at the bar's corner, cut to its part.
        for box, picture, _ in parts:
            if box["w"] > 0 and box["h"] > 0:
                painter.picture(picture, (box["x"] - x, box["y"] - y), box)
        return
    radius = min(max(values.get("dis", 0), 0), 100) / 100 * (min(w, h) - 1) / 2
    if radius < LEAST_ROUNDING:
        for box, _, colour in parts:
            if box["w"] > 0 and box["h"] > 0:
                painter.add("colour", box, colour=rgb565_to_hex(values.get(colour, 0)))
        return
    back, fill = (rgb565_to_rgb(values.get(colour, 0)) for colour in ("bco", "pco"))
    painter.add("text", image=data_url(rounded_bar(w, h, radius, filled, down, back, fill)))
