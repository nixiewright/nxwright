"""Drawing a sliding text: a text of several lines that a touch slides up and
down inside it, drawn as a text component is, its lines from its top.

Its lines are laid out as a text's (text_pictures.py), wrapped at the width
inside its border when `isbr` is 1, and placed across by `xcen`. They start
at the top inside its border, scrolled up by `val_y`, and are cut to the
inside of its border. The farthest they scroll, `maxval_y`, is how much
taller they are than that inside; code may scroll them 32 pixels further,
but not so far that the last line goes above the top (sliding_layout). Its
scroll bar's thumb shows by `left` (ComponentPainter.scroll_thumb). All of
this matched the Editor's simulator (tests/fixtures/sliding-text/), but for
two cases. The Editor drew the thumb one pixel higher at about one `val_y`
in three, for no rule found. And when code scrolled lines that fit past
their end, the Editor wrapped them one character sooner.
"""
from dataclasses import dataclass

from nxwright import NxwrightError
from nxwright.drawing.text_pictures import block_size

# How much further than `maxval_y` code may scroll a sliding text's lines, a
# file browser's entries, or a data record's records (testing/simulation.py).
FURTHER_BY_CODE = 32
# How far above their top code may scroll them, as the Nextion Editor's
# simulator settled each of the three (testing/list_working.py).
ABOVE_BY_CODE = 32


@dataclass(frozen=True)
class SlidingLayout:
    """How far a sliding text's lines scroll."""
    most: int          # `maxval_y`: how far a touch scrolls them
    farthest: int      # how far code may scroll them, setting `val_y`


def sliding_layout(values: dict, font, encoding: str, inside: dict) -> SlidingLayout:
    """Returns how far a sliding text's lines scroll, `values` its attributes,
    `font` its font (zi_font.Font), and `inside` the rectangle inside its
    border. Code may scroll them 32 pixels past `maxval_y`, but leaving the
    last line's height at least (both seen with lines 20 pixels high). Raises
    MissingCharacter for a character `font` or `encoding` lacks."""
    _, height = block_size(values.get("txt", ""), font, encoding, values, inside["w"])
    most = max(height - inside["h"], 0)
    return SlidingLayout(most, max(min(most + FURTHER_BY_CODE, height - font.height), 0))


def paint_sliding_text(painter):
    """Paints a sliding text: its background, its lines scrolled by `val_y`,
    its border, and its scroll bar's thumb. A `val_y` past the farthest code
    may scroll the lines, either way, is drawn at that farthest, as the
    simulator settles it (testing/list_working.py)."""
    values = painter.values
    inside = painter.inside()
    try:
        font = painter.resources.font(values.get("font", 0))
        layout = sliding_layout(values, font, painter.resources.encoding, inside)
    except NxwrightError:
        layout = None       # the text's own drawing notes why
    scrolled = values.get("val_y", 0)
    if layout is not None:
        scrolled = min(max(scrolled, -ABOVE_BY_CODE), layout.farthest)
    painter.background({0: "picc", 1: "bco", 2: "pic"})
    painter.text(box=inside, at=(None, -scrolled))
    painter.border()
    if layout is not None:
        painter.scroll_thumb(scrolled, layout.most)
