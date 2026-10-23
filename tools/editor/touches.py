"""Touches on the Editor's simulator's screen, as `simulate --touch` takes them
(README.md): a list of steps separated by semicolons, such as
"press 200,150; release; wait 500; picture tapped.png".

  press X,Y      presses the screen at its pixel (X, Y)
  release        releases the press, where it was made
  wait MS        waits MS milliseconds
  picture FILE   saves a picture of the simulator's window as FILE

A point is in the screen's own pixels, as a page file gives a component's
`x` and `y`. There is no step that moves a held press: the Editor's simulator
takes no drag from window messages. Mouse moves posted after a press, in one
jump or in steps, left a slider where the press put it, so a drag in the
simulator is done by hand.

The steps are parsed and checked here, before the simulator starts, with
nothing of Windows' or the Editor's, so that the tests need neither.
"""
from dataclasses import dataclass
from pathlib import Path
import re


class StepError(Exception):
    """A list of steps that is refused, saying which step and why."""


@dataclass(frozen=True)
class Press:
    x: int
    y: int


@dataclass(frozen=True)
class Release:
    """A release, at the point of the press it ends."""
    x: int
    y: int


@dataclass(frozen=True)
class Wait:
    milliseconds: int


@dataclass(frozen=True)
class Picture:
    file: Path


_POINT = re.compile(r"(\d+)\s*,\s*(\d+)")


def parse_steps(text: str, screen_size: tuple) -> list:
    """Returns the steps `text` lists, as Press, Release, Wait, and Picture.
    `screen_size` is the screen's (width, height) at the project's rotation.
    Blank steps, as after a last semicolon, are left out.

    Raises StepError, naming the first step refused, for a list with no step,
    a step of none of the forms above, a point outside the screen, a press
    while another is held, or a release while none is."""
    steps = []
    held = None         # the point of the press held, if any
    for number, written in enumerate(text.split(";"), 1):
        word, _, rest = written.strip().partition(" ")
        rest = rest.strip()
        if not word:
            continue
        where = "step %d, %r" % (number, written.strip())
        if word == "press":
            if held is not None:
                raise StepError("%s: a press is held already; release it first" % where)
            held = _point(rest, screen_size, where)
            steps.append(Press(*held))
        elif word == "release" and not rest:
            if held is None:
                raise StepError("%s: no press is held" % where)
            steps.append(Release(*held))
            held = None
        elif word == "wait" and rest.isdecimal():
            steps.append(Wait(int(rest)))
        elif word == "picture" and rest:
            steps.append(Picture(Path(rest)))
        else:
            raise StepError("%s: not a step; the steps are press X,Y, release, wait MS, "
                            "and picture FILE" % where)
    if not steps:
        raise StepError("no steps are given")
    return steps


def _point(text: str, screen_size: tuple, where: str) -> tuple:
    """The (x, y) that `text` writes as "X,Y", within a screen of
    `screen_size`. Raises StepError for any other text, or a point outside."""
    found = _POINT.fullmatch(text)
    if not found:
        raise StepError("%s: a point is written X,Y, such as 200,150" % where)
    x, y = int(found[1]), int(found[2])
    width, height = screen_size
    if x >= width or y >= height:
        raise StepError("%s: the point is outside the screen, %d by %d pixels"
                        % (where, width, height))
    return x, y
