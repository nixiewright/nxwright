"""What every module of the page drawing shares: a rectangle as the drawing
writes one, {"x", "y", "w", "h"} (box_of, PLACE, part_within); the width of
a component's border (border_width); the ID that stands for no picture or
font (NO_RESOURCE); and the most pixels a picture the drawing makes may hold
(MOST_PICTURE_PIXELS). They live apart from page_drawing.py, which imports
each type's drawing module, so that those modules can use them without
importing it back.
"""


# A picture or font ID meaning "none".
NO_RESOURCE = 65535


# The keys of a rectangle, as the drawing writes one, in their order.
PLACE = ("x", "y", "w", "h")


# The most pixels a picture the drawing makes, of a text or of a QR code,
# may hold: four times the largest screen's.
MOST_PICTURE_PIXELS = 4 * 1280 * 800


def border_width(values: dict) -> int:
    """The width of the border a component's `style` draws inside its
    rectangle, as ComponentPainter.border draws it: `borderw` for a border
    (`style` 1) on a colour, never past the component's middle; a pixel for
    a 3D style's edges on a colour; else 0. A checkbox has no `sta`, its
    background being its colour."""
    style, sta = values.get("style"), values.get("sta")
    if style == 1 and sta in (1, None):
        return max(min(values.get("borderw", 0), values.get("w", 0) // 2,
                       values.get("h", 0) // 2), 0)
    if style in (2, 3, 4) and sta == 1:
        return 1
    return 0


def box_of(x: int, y: int, w: int, h: int) -> dict:
    """Returns the rectangle at (x, y), `w` wide and `h` high, as the drawing
    writes one."""
    return {"x": x, "y": y, "w": w, "h": h}


def part_within(box: dict, inside: dict):
    """The part of the rectangle `box` within the rectangle `inside`, or
    None for none."""
    left, top = max(box["x"], inside["x"]), max(box["y"], inside["y"])
    right = min(box["x"] + box["w"], inside["x"] + inside["w"])
    bottom = min(box["y"] + box["h"], inside["y"] + inside["h"])
    return box_of(left, top, right - left, bottom - top) if right > left and bottom > top else None
