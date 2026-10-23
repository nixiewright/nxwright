"""Drawing a checkbox: a box of `bco`, with the edges its `style` gives,
as a text's: 0 none, 1 a border `borderw` pixels wide in `borderc`, 2 sunk
(the default), and 3 raised. When `val` is 1, the tick is a square of
`pco`, the box less a quarter of its width on each side, the quarter cut
toward zero: a quarter in from its left and from its top. It is drawn
before the edges: a box wider than high draws it past its bottom, its
bottom edge across it, as the Editor's simulator drew it.

All of this matched the Editor's simulator pixel for pixel
(tests/fixtures/value-widgets/), at widths 4 divides and at widths of 21
to 33, which it does not (tests/fixtures/drawing-assumptions/, page7).
"""
from nxwright.project.screen_colours import rgb565_to_hex

# The styles that draw an edge; 0 draws none.
_BORDER, _SUNK, _RAISED = 1, 2, 3


def paint_checkbox(painter):
    """Paints a checkbox: its box, its edges, and its tick when `val` is 1."""
    values, box = painter.values, painter.box
    painter.add("colour", colour=rgb565_to_hex(values.get("bco", 0)))
    if values.get("val", 0):
        inset = box["w"] // 4
        side = box["w"] - 2 * inset
        painter.add("colour", {"x": box["x"] + inset, "y": box["y"] + inset, "w": side, "h": side},
                    colour=rgb565_to_hex(values.get("pco", 0)))
    # The edges come after the tick: the Editor drew a box's bottom edge
    # across a tick that reached past it.
    style = values.get("style", _SUNK)
    if style in (_SUNK, _RAISED):
        painter.edges(sunk=style == _SUNK)
    elif style == _BORDER:
        painter.border()
