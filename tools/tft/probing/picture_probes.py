"""The picture component's probes (component_types/picture.py): pictures on
the T base folder's pages, showing one of the project's pictures or none,
two of them, one among a text, a number, a button, a variable, and a timer,
one before a text, one on a second page, ten on a page, one at the screen's
edges, one shown in a larger area than its picture, and code in a picture's
event; then a picture's pic in code. Run them with `tools.tft.probe run
picture_probes`.

Each probe of a picture compares the whole file, part by part, and keeps
the user code alone as its fixtures (component_probes.py gives both). Each
probe of code compares the blocks of page0's Touch Release event alone,
which it keeps as its fixture (statement_probes.py gives both).
"""
from dataclasses import dataclass
from functools import partial
from pathlib import Path

from tools.tft.probing.button_probes import button_component
from tools.tft.probing.component_probes import ComponentsChange, type_probe, with_components
from tools.tft.probing.number_probes import number_component
from tools.tft.probing.probe_runner import Probe
from tools.tft.probing.statement_probes import (ours_in_event, program_lines, theirs_in_event,
                                           touch_release_code)
from tools.tft.probing.text_probes import text_component
from tools.tft.probing.timer_probes import timer_component
from tools.tft.probing.variable_probes import variable_component

# The project's pictures: a name, a size, and a colour each.
_RED = ("red", (8, 4), (255, 0, 0))
_BLUE = ("blue", (4, 8), (0, 0, 255))


def picture_component(name: str = "p0", x: int = 10, y: int = 10, w: int = 8, h: int = 4,
                      pic: str = "red", **attributes: int) -> str:
    """Returns a picture component in a page file's form, showing the
    project's picture `pic`, or none when `pic` is None, its other
    attributes at their defaults unless given."""
    shown = "" if pic is None else 'pic = "%s"\n' % pic
    return ('\n[[component]]\nname = "%s"\ntype = "picture"\nx = %d\ny = %d\nw = %d\nh = %d\n%s'
            % (name, x, y, w, h, shown)
            + "".join("%s = %d\n" % item for item in attributes.items()))


@dataclass(frozen=True, eq=False)
class PicturesChange(ComponentsChange):
    """A probe's change that adds `pictures` to the project, each a name, a
    size, and a colour, drawn in that one colour, then does what a
    ComponentsChange does."""
    pictures: tuple = ()

    @property
    def picture_names(self) -> tuple:
        """The pictures' names, in the order of their IDs."""
        return tuple(name for name, _, _ in self.pictures)

    def __call__(self, folder: Path):
        from PIL import Image
        from nxwright.source.resource_adding import add_pictures
        # Drawn beside the folder, which add_pictures copies them into.
        files = []
        for name, size, colour in self.pictures:
            files.append(folder.parent / (name + ".png"))
            Image.new("RGB", size, colour).save(files[-1])
        add_pictures(folder, files)
        super().__call__(folder)


def with_pictures(pictures: list, *components: str, page: str = "page0",
                  code: str = "", attributes: str = "") -> PicturesChange:
    """Returns a change that adds `pictures` to the project, each drawn in
    one colour, then puts `components` on `page`, with `code` and the lines
    of the page's own table `attributes` (PicturesChange)."""
    return PicturesChange(components, page, code, attributes, tuple(pictures))


# Two pictures as large as the screen, bg and bg2, pictures 0 and 1, to put
# behind components, so that a crop of either fills any of them.
SCREEN_PICTURES = [("bg", (320, 480), (0, 0, 255)), ("bg2", (320, 480), (0, 255, 0))]

# What lies behind a component that has a sta, by the words of a probe's
# name: its sta, and the lines that give its crop or its picture, bg2, the
# second of SCREEN_PICTURES, so that its ID, 1, is no default's.
BACKGROUNDS = {"a-crop": (0, 'picc = "bg2"\n'), "a-picture": (2, 'pic = "bg2"\n'),
               "nothing": (3, "")}


def with_a_background(component_of, background: str, **attributes) -> PicturesChange:
    """Returns a probe's change: the component `component_of(sta=...,
    **attributes)` gives, in a page file's form, with the background
    `background` of BACKGROUNDS behind it, in a project of SCREEN_PICTURES."""
    sta, lines = BACKGROUNDS[background]
    return with_pictures(SCREEN_PICTURES, component_of(sta=sta, **attributes) + lines)


@dataclass(frozen=True, eq=False)
class StrictPicturesChange(PicturesChange):
    """A PicturesChange whose code is strict Nextion syntax, as a probe of
    code makes it (statement_probes.program_lines)."""
    strict: bool = True

    def __call__(self, folder: Path):
        program_lines([])(folder)
        super().__call__(folder)


def with_pictures_and_code(pictures: list, lines: list, *components: str) -> StrictPicturesChange:
    """Returns a change that adds `pictures`, each a name, a size, and a
    colour, puts `components` on page0, and gives page0's Touch Release
    event `lines`, in strict Nextion syntax (StrictPicturesChange)."""
    return StrictPicturesChange(components, "page0", touch_release_code(lines),
                                pictures=tuple(pictures))


def with_screen_pictures_and_code(lines: list, *components: str) -> StrictPicturesChange:
    """Returns a change that adds SCREEN_PICTURES, puts `components` on
    page0, and gives page0's Touch Release event `lines`, in strict Nextion
    syntax (with_pictures_and_code)."""
    return with_pictures_and_code(SCREEN_PICTURES, lines, *components)


_probe = partial(type_probe, "picture")


def _code_probe(name: str, lines: list) -> Probe:
    """Returns a probe of `lines` in page0's Touch Release event, beside p0
    and p1, in a project of two pictures."""
    change = with_pictures_and_code([_RED, _BLUE], lines, picture_component(),
                                    picture_component("p1", y=40, w=4, h=8, pic="blue"))
    return Probe("picture-" + name, "T", change, ours_in_event, theirs_in_event, "picture")


# The probes keeping fixtures are the fewest that show each part: two
# pictures on a page, of two pictures; a picture among a text, a number, a
# button, a variable, and a timer; and a picture on a second page, numbered
# on from the first's.
PROBES = [
    _probe("one", with_pictures([_RED], picture_component())),
    _probe("two", with_pictures([_RED, _BLUE], picture_component(),
                                picture_component("p1", y=40, w=4, h=8, pic="blue")),
           fixtures=True),
    _probe("of-none", with_components(picture_component(w=60, h=60, pic=None))),
    _probe("in-a-larger-area", with_pictures([_RED], picture_component(w=20, h=20))),
    _probe("in-a-smaller-area", with_pictures([_RED], picture_component(w=4, h=2))),
    # A pic given as a number, past the project's two pictures.
    _probe("of-a-number-past-the-last", with_pictures(
        [_RED, _BLUE], picture_component().replace('pic = "red"', "pic = 5"))),
    _probe("among-the-types-matched",
           with_pictures([_RED], text_component(), picture_component(y=60),
                         number_component(y=90), button_component(y=130), variable_component(),
                         timer_component()), fixtures=True),
    _probe("before-a-text", with_pictures([_RED], picture_component(), text_component(y=60))),
    _probe("on-second-page", with_pictures([_RED], picture_component(), page="page1"),
           fixtures=True),
    _probe("ten-on-a-page", with_pictures([_RED], *[picture_component("p%d" % number,
                                                                      y=10 + 20 * number)
                                                    for number in range(10)])),
    _probe("at-the-edges", with_pictures([_RED], picture_component(x=312, y=476))),
    _probe("event-code", with_pictures([_RED], picture_component(),
                                       code="on p0.down:\n  sys0=1\non p0.up:\n  sys1=2\n")),
    _probe("named-with-14", with_pictures([_RED], picture_component("Pict_name_of14"))),
    # A picture's pic set, stepped, read, and compared, and a picture as the
    # component of the screen's commands.
    _code_probe("pic-in-code", [
        "p0.pic=1", "sys0=p1.pic", "p1.pic=p0.pic", "p0.pic++", "if(p0.pic==1)", "{",
        "p1.pic=0", "}", "vis p0,0", "tsw p0,0", "click p1,1", "ref p1"]),
]
