"""What an agent reads of a running simulation (simulation.py), the same
whether the simulation runs on its own or in VS Code's debugger: what the
screen shows, the components of the page shown, values, and the log. Each
is shaped from a Simulation, as plain data for an agent's tool to answer
with. Here too is how a value is grouped, which the debugger's views share
(value_group).

These read the simulation as it stands, and change nothing. The caller
reads it from the thread that runs it, or while that thread stands still.
"""
from nxwright import NxwrightError
from nxwright.language.nxlang import GENERATED_ANY
from nxwright.source import source_folder as folders
from nxwright.testing.editor_machine import RECORD_STARTS, RECORDS
from nxwright.testing.screen_text import screen_text
from nxwright.testing.simulation import Simulation

_PLACE = ("x", "y", "w", "h")


def screen(simulation: Simulation, previews, pictures, picture: bool = True) -> dict:
    """Returns what the screen shows, as {text, page, png}: its text layout
    (screen_text.py); the name of the page shown; and, when `picture`, the
    bytes of a PNG picture of it. All three come from one drawing_inputs(),
    so that they describe the same screen. `previews`, a Previews
    (preview.py), makes the drawing, which `pictures`, the simulation's
    ScreenPictures (drawing/screen_pictures.py), is given first, as the
    screen's latest. While no page shows yet, as before program.nx opens
    one, the text says so, the page is None, and there is no picture."""
    if simulation.page is None:
        return {"text": "no page shows yet", "page": None}
    inputs = simulation.drawing_inputs()
    pictures.shown(previews.simulation_drawing(simulation, inputs))
    shown = {"text": screen_text(inputs, simulation.app["pictures"]), "page": inputs.page}
    if picture:
        shown["png"] = pictures.picture()
    return shown


def components(simulation: Simulation) -> list:
    """Returns the components of the page shown, as {name, type, x, y, w, h,
    shown}: the page first, of type "page", then each component in ID
    order, which is the order they are drawn in. A box is where the
    component is drawn, in the page's pixels. A component without a place,
    as a timer, has None for each of its four numbers. `shown` is False for
    one that does not show, hidden by code or waiting to slide in. With no
    page shown, there are none."""
    if simulation.page is None:
        return []
    hidden = simulation.hidden()
    return [dict({"name": component.name, "type": component.type},
                 **{key: component.values.get(key) for key in _PLACE},
                 shown=component.name not in hidden)
            for component in simulation.components()]


def value_group(name: str, nxlang: bool) -> str:
    """Returns which group a value of a run belongs to, as the debugger
    shows them: "Page", a component's attribute; "Program", an `int`
    variable or a system variable; "Outside the page", what the machine
    records there, as what was sent; or "Generated", a variable the nxlang
    compiler adds, in a run of code compiled from nxlang (`nxlang`). The
    Editor's own language generates nothing, so a name shaped as a
    generated one is the project's own there."""
    if name in RECORDS or name.startswith(RECORD_STARTS):
        return "Outside the page"
    if nxlang and GENERATED_ANY.fullmatch(name.split(".", 1)[0]):
        return "Generated"
    return "Page" if "." in name else "Program"


def values(simulation: Simulation, names: list = None) -> dict:
    """Returns {name: value} of the components' attributes, the `int`
    variables, and the system variables, the names as the shown page's code
    writes them, such as "t0.txt" or "sys0": every one, or those of `names`.
    A component's name alone, such as "t0", gives each of its attributes.
    What the simulation records outside the page, as what was sent, and the
    variables the nxlang compiler adds, are no names code gives, and are
    left out. Raises NxwrightError naming each name it does not know."""
    nxlang = simulation.app["language"] == folders.NXLANG
    known = {name: value for name, value in simulation.values().items()
             if value_group(name, nxlang) in ("Page", "Program")}
    if names is None:
        return known
    found, unknown = {}, []
    for name in names:
        attributes = ({name: known[name]} if name in known else
                      {key: value for key, value in known.items()
                       if key.startswith(name + ".")})
        if attributes:
            found.update(attributes)
        else:
            unknown.append(name)
    if unknown:
        raise NxwrightError("the page shown has nothing named %s" % " or ".join(unknown))
    return found


def log(simulation: Simulation, after: int = 0) -> list:
    """Returns the log's lines after the line numbered `after`, as {number,
    time, line}: what reached outside the screen, each line numbered from 1
    since the simulation started, its time the simulation's, in
    milliseconds. The log is never cut, so a number always means the same
    line. An `after` past the last line gives none, as for a caller asking
    for lines not yet logged. Raises NxwrightError for an `after` that is
    not a whole number of 0 or more."""
    if not isinstance(after, int) or isinstance(after, bool) or after < 0:
        raise NxwrightError("the log is read after a line's number, 0 or more")
    return [{"number": number, "time": time, "line": line}
            for number, (time, line) in enumerate(simulation.log[after:], start=after + 1)]


def touch_refusal(simulation: Simulation, action: str, x: int, y: int):
    """Returns why the screen cannot take an agent's touch, or None if it
    can. `action` is "press" or "move", at the page's pixel (x, y). The
    screen takes one touch at a time, on the page. So a press while one is
    held is refused, and a move while none is. A release is never refused:
    one while none is held does nothing, so that a tap whose press ran
    `rest`, which forgets the press, still ends."""
    if action == "press":
        if simulation.touch_held():
            return ("the screen is pressed already, and takes one touch at a time: "
                    "release it first")
        if simulation.page is None:
            return "no page shows yet, so the screen cannot be pressed"
    elif not simulation.touch_held():
        return "the screen is not pressed: press it first"
    width, height = simulation.touch_area()
    if not (0 <= x < width and 0 <= y < height):
        return "%d,%d lies off the page, which is %d x %d" % (x, y, width, height)
    return None
