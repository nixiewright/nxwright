"""Drawing a scrolling text: a text component's background, text, and
border, its text moving by itself (nxwright/testing/scrolling_texts.py).

`dir` is the way it moves: 0 left to right, 1 right to left, 2 top to
bottom, and 3 bottom to top. A simulation gives where its text has moved:
its left, moving across, or its top, moving up or down, in page pixels, as
the screen keeps it in `vvs0` or `vvs1`. Across its way of moving, the text
sits as a text component's does (`xcen`, `ycen`), and what falls outside
the component is cut. The Editor's simulator drew it so (tests/fixtures/
scrolling-text/), on texts without a border. With one, the text is cut to
the inside of the border, as a text's is, where it moves unchanged, as
the Editor's simulator drew a text placed across the border's left and
right (tests/fixtures/drawing-assumptions/, page10).

Across its way, the text is placed by the size the screen keeps in `vvs2`
and `vvs3`, which its steps measure, not by the text it now shows. A new
font or text shows at once, placed as the old one was until the next step,
as the Editor's simulator drew a stopped one.

The page preview, which runs nothing, draws the text at rest, where a text
component would show it, so that its text, font, and colour can be seen as
the page is designed. The screen never shows it there: it starts outside
the component, and comes in at its first step.
"""
from nxwright.drawing.text_pictures import aligned_start

LEFT_TO_RIGHT, RIGHT_TO_LEFT, TOP_TO_BOTTOM, BOTTOM_TO_TOP = 0, 1, 2, 3


def direction(values: dict) -> int:
    """Returns a scrolling text's `dir`, 0 to 3; right to left, the type's
    default, when `values` lack it."""
    return values.get("dir", RIGHT_TO_LEFT)


def moves_across(values: dict) -> bool:
    """Whether a scrolling text moves across, left or right, rather than up
    or down."""
    return direction(values) in (LEFT_TO_RIGHT, RIGHT_TO_LEFT)


def paint_scrolling_text(painter):
    """Paints a scrolling text: at rest in the preview, else where the
    simulation has moved it (painter.scrolled), placed across its way by
    its kept size."""
    at = (None, None)
    if painter.scrolled is not None:
        # The text is placed from the corner inside the border.
        values, inside = painter.values, painter.inside()
        if moves_across(values):
            at = (painter.scrolled - inside["x"],
                  aligned_start(values.get("ycen", 1), inside["h"], values["vvs3"]))
        else:
            at = (aligned_start(values.get("xcen", 1), inside["w"], values["vvs2"]),
                  painter.scrolled - inside["y"])
    painter.text_component(at=at)
