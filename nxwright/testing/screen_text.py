"""What a simulation's screen shows, in words: its text layout, for an agent
driving the simulator, which often reads a description more readily than a
picture (drawing/screen_pictures.py paints the picture). For example:

    page main (800 x 480), background picture 3 "home"
    t0  text     20,10    200x40  "Temperature"
    n0  number   240,10   120x40  "21"
    b0  button   20,400   120x60  "Set"  pressed
    p0  picture  600,20   64x64   picture 5 "heating"
    painted: xstr "Hello" at 10,300 200x40 #ffffff
    hidden: b3, t7

The first line gives the page, its size, and its background. Then comes a
line for each component that shows, in ID order, which is the order they
are drawn in, so that a later line lies on top: its name, its type, its box
in the page's pixels, and what it shows. Then what drawing commands painted
over the page, in order, and the components that do not show. A picture is
given by its ID, which code uses, and by its name in app.toml, which page
files use.

It is written from the DrawingInputs that the drawing is made from
(Simulation.drawing_inputs), so that the words and the picture always
describe the same screen: after a page change while `ref_stop` holds, the
page before, until `ref_star`.
"""
from nxwright.drawing.drawing_shared import NO_RESOURCE
from nxwright.drawing.number_drawing import number_text, xfloat_text
from nxwright.drawing.text_pictures import shown_text
from nxwright.project.screen_colours import rgb565_to_hex

_PLACE = ("x", "y", "w", "h")
# The types whose `val` the text gives, as "on" or "off", or as a number.
_ON_OR_OFF = ("checkbox", "radio", "switch", "dual-state-button")
_AMOUNTS = ("slider", "progress-bar", "gauge")


def screen_text(inputs, picture_names: list) -> str:
    """Returns the text layout of the screen `inputs` describe, the
    DrawingInputs that Simulation.drawing_inputs() gives. `picture_names`
    are the app's pictures, in ID order, as app.toml lists them."""
    page, *components = inputs.components
    placed = [component for component in components
              if all(key in component.values for key in _PLACE)]
    lines = [_page_line(page, picture_names)]
    lines += _aligned([_component_row(component, inputs.pressed, picture_names)
                       for component in placed if component.name not in inputs.hidden])
    painted = [said for said in (_painted_words(entry, picture_names)
                                 for entry in inputs.painted) if said]
    if painted:
        lines.append("painted: " + "; ".join(painted))
    hidden = [component.name for component in placed if component.name in inputs.hidden]
    if hidden:
        lines.append("hidden: " + ", ".join(hidden))
    return "\n".join(lines)


def _page_line(page, picture_names: list) -> str:
    """The page's line: its name, its size, and what fills its background,
    by its `sta`."""
    values = page.values
    size = " (%d x %d)" % (values["w"], values["h"]) if "w" in values and "h" in values else ""
    sta = values.get("sta", 1)
    if sta == 0:
        background = "no background"
    elif sta == 2:
        background = "background " + _picture_words(values.get("pic", NO_RESOURCE),
                                                    picture_names)
    else:
        background = "background colour %s" % rgb565_to_hex(values.get("bco", 0))
    return "page %s%s, %s" % (page.name, size, background)


def _component_row(component, pressed: str, picture_names: list) -> list:
    """The columns of a component's line: name, type, place, size, and what
    it shows: its text as the drawing writes it, a password as stars; its
    picture; its state; and whether it is held down."""
    values, kind = component.values, component.type
    shows = []
    if kind == "number":
        shows.append('"%s"' % number_text(values))
    elif kind == "xfloat":
        shows.append('"%s"' % xfloat_text(values))
    elif isinstance(values.get("txt"), str):
        shows.append('"%s"' % shown_text(values["txt"], values))
    if kind == "picture":
        shows.append(_picture_words(values.get("pic", NO_RESOURCE), picture_names))
    elif kind == "crop":
        shows.append("crop of " + _picture_words(values.get("picc", NO_RESOURCE),
                                                  picture_names))
    if kind in _ON_OR_OFF:
        shows.append("on" if values.get("val") else "off")
    elif kind in _AMOUNTS:
        shows.append("value %s" % values.get("val", 0))
    if component.name == pressed:
        shows.append("pressed")
    return [component.name, kind, "%d,%d" % (values["x"], values["y"]),
            "%dx%d" % (values["w"], values["h"]), "  ".join(shows)]


def _picture_words(picture_id: int, picture_names: list) -> str:
    """A picture as the text gives it, such as `picture 5 "heating"`."""
    if picture_id == NO_RESOURCE:
        return "no picture"
    return "picture " + _id_and_name(picture_id, picture_names)


def _id_and_name(picture_id: int, picture_names: list) -> str:
    """A picture's ID and name, such as `5 "heating"`; its ID alone when the
    app lists no picture of that ID."""
    if 0 <= picture_id < len(picture_names):
        return '%d "%s"' % (picture_id, picture_names[picture_id])
    return "%d" % picture_id


def _aligned(rows: list) -> list:
    """The rows as lines, each column but the last padded to the widest of
    its column, the columns two spaces apart."""
    if not rows:
        return []
    widths = [max(len(row[column]) for row in rows) for column in range(len(rows[0]) - 1)]
    return ["  ".join([cell.ljust(width) for cell, width in zip(row, widths)] + [row[-1]])
            .rstrip() for row in rows]


def _painted_words(entry: tuple, picture_names: list):
    """What one drawing command painted, as the test machine records it (its
    command, then its arguments, computed), in words; None for an entry
    that paints nothing itself, as `ref_stop`, or a component drawn again."""
    command, arguments = entry[0], entry[1:]
    if command == "cls":
        return "cls %s" % rgb565_to_hex(arguments[0])
    if command == "fill":
        x, y, w, h, colour = arguments
        return "fill %d,%d %dx%d %s" % (x, y, w, h, rgb565_to_hex(colour))
    if command in ("draw", "line"):
        x1, y1, x2, y2, colour = arguments
        return "%s %d,%d to %d,%d %s" % (command, x1, y1, x2, y2, rgb565_to_hex(colour))
    if command in ("cir", "cirs"):
        x, y, radius, colour = arguments
        return "%s %d,%d radius %d %s" % (command, x, y, radius, rgb565_to_hex(colour))
    if command == "pic":
        x, y, picture_id = arguments
        return "pic %s at %d,%d" % (_id_and_name(picture_id, picture_names), x, y)
    if command == "picq":
        x, y, w, h, picture_id = arguments
        return "picq %s at %d,%d %dx%d" % (_id_and_name(picture_id, picture_names), x, y, w, h)
    if command == "xpic":
        x, y, w, h, source_x, source_y, picture_id = arguments
        return "xpic %s from %d,%d at %d,%d %dx%d" % (_id_and_name(picture_id, picture_names),
                                                      source_x, source_y, x, y, w, h)
    if command == "xstr":
        x, y, w, h, _font, pco, _bco, _xcen, _ycen, _sta, text = arguments
        return 'xstr "%s" at %d,%d %dx%d %s' % (text, x, y, w, h, rgb565_to_hex(pco))
    return None
