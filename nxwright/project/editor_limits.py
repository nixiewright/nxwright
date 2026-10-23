"""Limits of the Editor that a page can break, checked before the page is
written: its names, its texts, and how many components of some kinds it
holds (PAGE_CAPS); and, given the screen, a component reaching past it on
a series that refuses that (check_component_places). The Editor itself
reports them only when it opens or compiles the project, far from the page
file at fault. Also which attributes a component has under its choices and
its series (lacked_attributes, screen_holds).

The types and choices a series refuses are checked in
source/series_components.py, as that check reads the attributes'
descriptions. The Editor's language is editor_language.py's, and the
screen's arithmetic screen_arithmetic.py's."""
from dataclasses import dataclass

from nxwright import NxwrightError
from nxwright.project.attribute_values import number_from_bytes
from nxwright.project.component_defaults import nxwright_defaults
from nxwright.project.editor_language import NAMES_THE_EDITOR_REFUSES
from nxwright.project.object_types import TYPE_NAMES, TYPES_BY_NAME
from nxwright.project.page_block import Attribute, PageBlock
from nxwright.project.screen_models import ScreenModel

# The Editor keeps this many bytes of a page's or component's name, and cuts
# the rest when it opens the project; code naming the full name then fails.
NAME_LIMIT = 14
# The least width and height the Editor takes for a component: narrower or
# lower, it says "Width can not be less than 2" as it opens the project, and
# sets the side back to its type's default (least_size_words).
LEAST_SIDE = 2
# The values the Editor gives a component it adds on a screen of each
# series, by the series' letter, where they differ from nxwright's component
# defaults, which came from an Intelligent screen: {series: {type:
# {attribute: value}}}. On the basic, Enhanced, and Discovery series, its
# Toolbox added a gauge with `sta` 1, a colour, where their compile refuses
# the Intelligent's 3. Only the gauge was added: it is the one type whose
# default the memory table shows these series refusing. (Worked out from
# the Editor 3.1.73.)
SERIES_NEW_COMPONENT_VALUES = {series: {"gauge": {"sta": 1}} for series in ("T", "K", "F")}


@dataclass(frozen=True)
class PageCap:
    """A cap of the Editor's compile on one page's components: at most
    `most` of the types `types` together, which the build's messages call
    `words`, and the Editor's message past it starts with `editor_words`."""
    types: frozenset           # type numbers
    most: int
    words: str
    editor_words: str


# The Editor's caps on a page's components. Past one, its compile fails,
# saying "Waveform components exceed maximum in page:5", for one. Worked out
# from the Editor 3.1.73: the caps were the same on every series that takes
# their kinds, and only the P and E series take animations and videos.
# Videos, sounds, animations, and file browsers are not counted among the
# timer events: 11 timers beside 2 of each compiled. Every other kind
# compiled 20 to a page, where memory allowed.
PAGE_CAPS = (
    PageCap(frozenset({TYPES_BY_NAME["waveform"]}), 5, "waveforms", "Waveform components"),
    PageCap(frozenset({TYPES_BY_NAME["gmov"], TYPES_BY_NAME["video"]}), 16,
            "animations and videos", "Gmov and video components"),
    PageCap(frozenset({TYPES_BY_NAME["timer"], TYPES_BY_NAME["scrolling-text"]}), 12,
            "timers and scrolling texts", "Timer events"),
)
# The attributes named `X_m` that bound no `X`'s length (bounded_attributes),
# by (type number, name).
_NOT_BOUNDS = {(TYPES_BY_NAME["sliding-text"], "path_m")}
# The bounds the Editor's compile takes a longer value past, up to the room
# the screen sets aside for it, by (type number, name). That room is the
# bound plus 1, rounded up to a multiple of 4, as the memory table counts it.
# The compile took a data record's `format` or `dir` 1 byte shorter than its
# room, and the screen showed all of it. It refused 1 byte more ("The length
# exceeds the maximum value"). Code storing a longer one still keeps only
# its first bytes. (Editor 3.1.73.)
_BOUNDS_COMPILED_TO_THEIR_ROOM = {(TYPES_BY_NAME["data-record"], "format_m"),
                                  (TYPES_BY_NAME["data-record"], "dir_m")}
# The attributes a component has only under some values of one of its
# choices, as its page file gives them: {type: {attribute: (the choice, the
# values under which the attribute exists)}}. Under any other value the
# component lacks it: the Editor's compile refused code naming it, assigned
# or read ("Invalid Variables"), and its simulator answered 0x1A to a typed
# line naming one, as to a name the page lacks. Each value of each choice
# of every type was compiled apart, the others at their defaults, on every
# series; the rules were the same on all. (Worked out from the Editor 3.1.73.)
#
# A component appears as its page opens by its `effect`, after the others
# of a lower `first`, over `time`: every effect but 0, at once, has them.
_OPENING = {"first": ("effect", range(1, 256)), "time": ("effect", range(1, 256))}
# Where its background comes from, its `sta`: a crop of a picture (0), a
# colour (1), or a picture (2); 3 is nothing. A colour has a `style`, whose
# 1, a border, has the border's colour and width.
_BACKGROUND = {"picc": ("sta", {0}), "bco": ("sta", {1}), "pic": ("sta", {2})}
_BORDER = {"borderc": ("style", {1}), "borderw": ("style", {1})}
_STYLED = {**_OPENING, **_BACKGROUND, "style": ("sta", {1}), **_BORDER}
# A button's background while it is pressed follows the same `sta`.
_PRESSED = {"picc2": ("sta", {0}), "bco2": ("sta", {1}), "pic2": ("sta", {2})}
# A player's file: its `path` on an SD card (`from` 1), or its `vid` in the
# project (0).
_PLAYED = {"path": ("from", {1}), "path_m": ("from", {1}), "vid": ("from", {0})}
PRESENT_WHILE = {
    **{kind: _OPENING for kind in ("crop", "external-picture", "hotspot", "picture", "radio",
                                   "switch")},
    **{kind: _STYLED for kind in ("text", "scrolling-text", "number", "xfloat", "combo-box",
                                  "data-record", "sliding-text")},
    "button": {**_STYLED, **_PRESSED},
    "dual-state-button": {**_STYLED, **_PRESSED},
    "select": {**_STYLED, "pco1": ("dis", {1})},
    "file-browser": {**_STYLED, "pic1": ("psta", {1})},
    "checkbox": {**_OPENING, **_BORDER},
    "gauge": {**_OPENING, **_BACKGROUND},
    "page": {**_OPENING, "bco": ("sta", {1}), "pic": ("sta", {2})},
    # Its colour background has the grid's colour and cells. Its channels'
    # colours are those of channels it has, `ch` of them.
    "waveform": {**_OPENING, **_BACKGROUND, "gdc": ("sta", {1}), "gdh": ("sta", {1}),
                 "gdw": ("sta", {1}), "pco1": ("ch", {2, 3, 4}), "pco2": ("ch", {3, 4}),
                 "pco3": ("ch", {4})},
    # Its track by `sta` alike, the part before its knob too; its knob,
    # `psta`, is round (0), a picture (1), or square (2).
    "slider": {**_OPENING, "picc": ("sta", {0}), "picc1": ("sta", {0}), "bco": ("sta", {1}),
               "bco1": ("sta", {1}), "ch": ("sta", {1}), "dis": ("sta", {1}),
               "pic": ("sta", {2}), "pic1": ("sta", {2}), "pic2": ("psta", {1}),
               "pco": ("psta", {0, 2})},
    # Colours (0) or pictures (1).
    "progress-bar": {**_OPENING, "bco": ("sta", {0}), "pco": ("sta", {0}), "dis": ("sta", {0}),
                     "bpic": ("sta", {1}), "ppic": ("sta", {1})},
    # Its logo, `sta` 1.
    "qr-code": {**_OPENING, "pic": ("sta", {1})},
    "video": {**_OPENING, **_PLAYED},
    "audio": _PLAYED,
    # An animation plays from the project, whatever its `from`, and keeps
    # its `path` (project/attribute_descriptions.toml, `gmov.from`).
    "gmov": {**_OPENING, "vid": ("from", {0})},
    # A number in `val` (`sta` 0), or a text in `txt` (1).
    "variable": {"val": ("sta", {0}), "txt": ("sta", {1}), "txt_maxl": ("sta", {1})},
}
# Why a component lacks an attribute, in words, where a choice's value says
# more than "has its sta at 1": {(type, choice, value): words}.
_LACKED_WORDS = {
    ("variable", "sta", 0): "holds a number",
    ("variable", "sta", 1): "holds a text",
    **{(kind, "from", 0): "plays an internal file (its from is 0)" for kind in ("video", "audio")},
    **{(kind, "from", 1): "plays a file of an SD card (its from is 1)"
       for kind in ("video", "audio")},
}
# Where a type is EVERY_TYPE, the attributes of every type that has them.
EVERY_TYPE = None
# The attributes a component lacks on a screen of each series, by the
# series' letter, whatever its choices: {series: {type: attributes}}. The
# Editor's compile refused code naming them, even read ("Invalid
# Variables"), on the Basic, Enhanced, and Discovery series, and took it on
# the Edge and Intelligent; `objname` on every object, the page too, which
# no page file holds. (Worked out from the Editor 3.1.73.)
SERIES_LACKED_ATTRIBUTES = {
    **{series: {EVERY_TYPE: frozenset(["movex", "movey", "lockobj", "groupid0", "groupid1",
                                       "sendkey", "objname"]),
                "waveform": frozenset(["objWid", "objHig", "inittrue", "molloc", "molloc_s"])}
       for series in ("T", "K", "F")},
    "E": {},
    "P": {},
}


def lacked_attributes(type_name: str, value_of, screen: ScreenModel = None) -> dict:
    """Returns {attribute: why, in words} of the attributes a component of
    the type `type_name`, as page files name types ("video"), lacks: under
    its choices (PRESENT_WHILE), `value_of(attribute)` giving the number one
    of its attributes holds, or None; and, given the folder's `screen`, on
    its series (SERIES_LACKED_ATTRIBUTES). The build's code checks, its
    length bounds, and the simulator all read the tables through it. A type
    that is no name, as a malformed page file may give, lacks nothing: the
    page's build refuses it."""
    if not isinstance(type_name, str):
        return {}
    lacked = {}
    for attribute, (choice, values) in PRESENT_WHILE.get(type_name, {}).items():
        value = value_of(choice)
        if value is not None and value not in values:
            lacked[attribute] = _LACKED_WORDS.get((type_name, choice, value),
                                                  "has its %s at %d" % (choice, value))
    if screen is not None:
        by_type = SERIES_LACKED_ATTRIBUTES[screen.series]
        for attribute in by_type.get(EVERY_TYPE, frozenset()) | by_type.get(type_name,
                                                                             frozenset()):
            lacked[attribute] = "is on an %s" % screen.name
    return lacked


# The attributes a screen does not hold, though code may name them, by the
# series' letter: {series: {type: attributes}}, EVERY_TYPE's those of every
# type that has them; and a bound, a name ending `_m`, as the sliding
# text's `path_m` (screen_holds), which only types the Edge and Intelligent
# alone take have. The Editor's simulator answered 0x1A, an invalid variable,
# to a typed line naming one, read or stored; event code read 0, whatever
# the page file stored, and a store answered 0x1C, a failed assignment, and
# changed nothing. A typed get of every attribute the compile took, at
# defaults, found them on every series: the Edge's and the Intelligent's
# the same, and the others' the same. An Intelligent screen does not hold
# an object's `objname` either, which no page file holds, and the Edge is
# taken to match it, as in every other probe. Code reading it into a text
# read 0, which the text refused (0x1C), as a text refuses any number
# (testing/editor_machine.py, _ATTRIBUTE_KINDS). The screen still draws
# with the page file's values.
# (Worked out from the Editor 3.1.73.)
_UNHELD_ON_THE_EDGE_AND_INTELLIGENT = {
    EVERY_TYPE: frozenset(["movex", "movey", "lockobj", "groupid0", "groupid1", "sendkey",
                           "molloc", "molloc_s", "objname"]),
    **{kind: frozenset(["key"]) for kind in ("text", "scrolling-text", "number", "xfloat")},
    "sliding-text": frozenset(["key", "leftshow", "path"]),
    "page": frozenset(["drag", "aph"]),
    "combo-box": frozenset(["drastate"]),
    "data-record": frozenset(["init", "autoleft"]),
    "file-browser": frozenset(["autoleft", "buff", "fwarning"]),
    "gauge": frozenset(["wid"]),
    "select": frozenset(["txt_maxl"]),
    "waveform": frozenset(["objWid", "objHig", "inittrue"]),
}
_UNHELD_ON_THE_OTHERS = {
    # A page or a component has first and time only with an effect. With
    # one, typed on the Basic, they answered 0x1A, read or stored. The
    # Basic's simulator played no opening effect either.
    EVERY_TYPE: frozenset(["aph", "drag", "effect", "first", "time"]),
    **{kind: frozenset(["key"]) for kind in ("text", "scrolling-text", "number", "xfloat")},
    # The pages a swipe opens.
    "page": frozenset(["up", "down", "left", "right"]),
    "gauge": frozenset(["up", "down", "left", "hig", "format", "pco2", "vvs0", "vvs1", "vvs2"]),
    "slider": frozenset(["dis"]),
}
UNHELD_ATTRIBUTES = {
    **{series: _UNHELD_ON_THE_EDGE_AND_INTELLIGENT for series in ("E", "P")},
    **{series: _UNHELD_ON_THE_OTHERS for series in ("T", "K", "F")},
}


def screen_holds(type_name: str, attribute: str, series: str) -> bool:
    """Returns whether a screen of the series `series`, as "P", holds the
    attribute `attribute` of a component of the type `type_name`, as page
    files name types: False for one of UNHELD_ATTRIBUTES, and for a bound,
    a name ending `_m`."""
    by_type = UNHELD_ATTRIBUTES[series]
    return not (attribute.endswith("_m") or attribute in by_type.get(EVERY_TYPE, frozenset())
                or attribute in by_type.get(type_name, frozenset()))


def least_size_words(type_name: str, width: int, height: int) -> str:
    """Says what the Nextion Editor does with a component of the type
    `type_name`, `width` by `height`, a side or both under LEAST_SIDE: as it
    opens the project, it says so of each side, and sets it back to its
    type's default, as it did for every type with a place, on an Intelligent
    screen. The defaults are nxwright's own, which the Editor's matched; on
    the other series, its new components' sizes are taken alike
    (SERIES_NEW_COMPONENT_VALUES). A type nxwright does not know, or one
    without a default size, is told without the number."""
    type_defaults = nxwright_defaults().get(TYPES_BY_NAME.get(type_name))
    defaults = dict(type_defaults.attributes) if type_defaults is not None else {}
    short = [(word, defaults.get(key))
             for word, key, side in (("Width", "w", width), ("Height", "h", height))
             if side < LEAST_SIDE]
    said = " and ".join('"%s can not be less than %d"' % (word, LEAST_SIDE) for word, _ in short)
    if any(default is None for _, default in short):
        back = "%s back to its type's default" % ("each" if len(short) == 2
                                                  else "the " + short[0][0].lower())
    elif len(short) == 2:
        back = "them back to %d by %d, its type's default" % tuple(
            number_from_bytes(value) for _, value in short)
    else:
        back = "the %s back to %d, its type's default" % (short[0][0].lower(),
                                                            number_from_bytes(short[0][1]))
    return ("the Nextion Editor says %s as it opens the project, and sets %s; make it at least "
            "%d by %d" % (said, back, LEAST_SIDE, LEAST_SIDE))


def check_page_limits(page: PageBlock, where: str):
    """Raises NxwrightError, starting with `where` (the file at fault), when a
    name of the page or of one of its components is longer than NAME_LIMIT or
    is one the Editor refuses (NAMES_THE_EDITOR_REFUSES), or a text is longer
    than the Editor's compile takes for the attribute bounding it
    (bounded_attributes, _most_compiled), both counting stored bytes; or
    when the page holds more components of some kinds than the Editor's
    compile takes (PAGE_CAPS). The error's `table` is the place in the page
    of the object at fault, from 0 for the page: past a cap, the first
    component past it."""
    for index, page_object in enumerate(page.objects):
        try:
            _check_object_limits(page_object, index, where)
        except NxwrightError as error:
            error.table = index
            raise
    _check_page_caps(page, where)


# The series whose Editor refuses to compile a component reaching past the
# screen, at its rotation: past its right or bottom edge, or starting past
# it ("Page:page0 Fail:t0 Position Invalid."). One ending at an edge it
# compiled. The Intelligent and Edge series took any. (Worked out from the
# Editor 3.1.73, on texts, hotspots, and scrolling texts. In a later probe,
# every type with a place that each series takes was refused past the right
# edge, and a text one pixel past the right or the bottom edge, where one
# ending at both edges compiled.) A negative x or y, and a side under 2, the
# build refuses before this: their bytes hold no negative value, and
# LEAST_SIDE is the least side.
SERIES_REFUSING_PLACES_PAST_THE_SCREEN = frozenset({"T", "K", "F"})


def check_component_places(page: PageBlock, screen: ScreenModel, page_size: tuple, where: str):
    """Raises NxwrightError, starting with `where` (the file at fault), for
    the first component of the page reaching past the screen, `page_size`
    (width, height) at its rotation, on a series that refuses it
    (SERIES_REFUSING_PLACES_PAST_THE_SCREEN), `screen` being the folder's
    screen model. A component without a place is not checked. The error's
    `table` is the component's place in the page."""
    if screen.series not in SERIES_REFUSING_PLACES_PAST_THE_SCREEN:
        return
    width, height = page_size
    for index, page_object in enumerate(page.objects[1:], start=1):
        place = [page_object.attribute(key) for key in ("x", "y", "w", "h")]
        if None in place:
            continue
        x, y, w, h = (int.from_bytes(value, "little") for value in place)
        if x + w > width or y + h > height:
            error = NxwrightError("%s: %s: it reaches past the screen, %d by %d at its rotation, "
                                  "and the Nextion Editor refuses to compile it on the %s "
                                  "(\"Position Invalid\")"
                                  % (where, object_label(page_object, index), width, height,
                                     screen.name))
            error.table = index
            raise error


# Attributes code can change on the other series that the Editor's compile
# refused code to assign to on a series ("Assignment operation failed"), by
# the series' letter: {series: {type: attributes}}, EVERY_TYPE's those of
# every type that has them. It took code reading them.
#
# The Basic, Enhanced, and Discovery series refused aph, drag, and effect,
# on each of their types that has them, the page among them (worked out
# from the Editor 3.1.73). They refused x and y on each of the 15 types
# each of those series takes, the Basic's simulator answering a typed store
# 0x1C. In a later probe, every attribute code can change on the Intelligent
# was assigned on each type those series take, under each choice that gives
# one. The three refused the same lines, and the Edge and Intelligent took
# them all. A Basic page refused first and time too, its effect 1. The
# Basic's simulator answered 0x1C to a typed store of a text's spax and
# borderc, a button's borderw, and a crop's vvs0.
_CANNOT_CHANGE_ON_THE_OTHERS = {
    EVERY_TYPE: frozenset(["aph", "drag", "effect", "first", "time", "x", "y"]),
    # A number, an xfloat, and a scrolling text took their border and
    # spacing, and a checkbox its border.
    **{kind: frozenset(["borderc", "borderw", "spax", "spay"])
       for kind in ("button", "dual-state-button", "text")},
    "crop": frozenset(["vvs0", "vvs1"]),
}
ATTRIBUTES_CODE_CANNOT_CHANGE_ON_SERIES = {series: _CANNOT_CHANGE_ON_THE_OTHERS
                                           for series in ("T", "K", "F")}


def code_cannot_change_on_series(type_name: str, attribute: str, series: str) -> bool:
    """Returns whether code cannot change the attribute `attribute` of a
    component of the type `type_name`, as page files name types, on a screen
    of the series `series`, as "T", though it can on other series
    (ATTRIBUTES_CODE_CANNOT_CHANGE_ON_SERIES). Whether the type has the
    attribute at all is the caller's to ask."""
    by_type = ATTRIBUTES_CODE_CANNOT_CHANGE_ON_SERIES.get(series, {})
    return (attribute in by_type.get(EVERY_TYPE, frozenset())
            or attribute in by_type.get(type_name, frozenset()))


def object_label(page_object, index: int) -> str:
    """How a refusal names an object of a page: "page home", or "component t0"."""
    name = (page_object.attribute("objname") or b"").decode("latin-1")
    return "%s %s" % ("page" if index == 0 else "component", name)


def _check_page_caps(page: PageBlock, where: str):
    """Raises NxwrightError when the page holds more components of a cap's
    types than PAGE_CAPS takes, saying how many it holds; its `table` is the
    first component past the cap."""
    # Each object's type number, None for one without a type.
    types = [kind[0] if kind else None
             for kind in (page_object.attribute("type") for page_object in page.objects)]
    for cap in PAGE_CAPS:
        held = [index for index, kind in enumerate(types) if kind in cap.types]
        if len(held) > cap.most:
            past = held[cap.most]
            name = (page.objects[past].attribute("objname") or b"").decode("latin-1")
            error = NxwrightError(
                "%s: component %s: the page holds %d %s; the Nextion Editor's compile takes %d "
                'on a page, saying "%s exceed maximum in page:%d"'
                % (where, name, len(held), cap.words, cap.most, cap.editor_words, cap.most))
            error.table = past
            raise error


def _check_object_limits(page_object, index: int, where: str):
    name = page_object.attribute("objname") or b""
    label = object_label(page_object, index)
    if len(name) > NAME_LIMIT:
        raise NxwrightError("%s: %s: its name has %d bytes; the Nextion Editor keeps %d"
                            % (where, label, len(name), NAME_LIMIT))
    if name.decode("latin-1") in NAMES_THE_EDITOR_REFUSES:
        raise NxwrightError('%s: %s: the Nextion Editor refuses this name, saying "Illegal name"'
                            % (where, label))
    # The Nextion Editor refuses such a page or component as it opens the project.
    if name[:1].isdigit():
        raise NxwrightError('%s: %s: the Nextion Editor refuses a name that starts with a digit, '
                            'saying "First character of a Name can not be number"'
                            % (where, label))
    kind = page_object.attribute("type")
    object_type = kind[0] if kind else None
    for attribute, length, bound, limit in _values_past_bounds(page_object):
        most = _most_compiled(page_object, object_type, attribute, bound, limit)
        if most is None or length <= most:
            continue
        if most == limit:
            raise NxwrightError("%s: %s: its %s has %d bytes; its %s is %d"
                                % (where, label, attribute, length, bound, limit))
        raise NxwrightError("%s: %s: its %s has %d bytes; its %s of %d holds %d at most, and the "
                            "Nextion Editor refuses more (\"The length exceeds the maximum value\")"
                            % (where, label, attribute, length, bound, limit, most))


def _values_past_bounds(page_object) -> list:
    """Returns (attribute, its bytes, the attribute bounding it, the most
    bytes it sets) of each value of `page_object` longer than its bound
    (bounded_attributes), whether or not the Editor's compile refuses it."""
    kind = page_object.attribute("type")
    object_type = kind[0] if kind else None
    names = [item.name for item in page_object.items if isinstance(item, Attribute)]
    found = []
    for attribute, bound in bounded_attributes(object_type, names):
        value, limit = page_object.attribute(attribute), page_object.attribute(bound)
        if value is not None and limit is not None and \
                len(value) > int.from_bytes(limit, "little"):
            found.append((attribute, len(value), bound, int.from_bytes(limit, "little")))
    return found


def _most_compiled(page_object, object_type, attribute: str, bound: str, limit: int):
    """The most bytes the Editor's compile takes of `page_object`'s
    `attribute`, of type number `object_type`, whose `bound`
    (bounded_attributes) is `limit`: the limit itself, or for one of
    _BOUNDS_COMPILED_TO_THEIR_ROOM, 1 byte less than its room. None for any
    length. It checks none of an attribute the component lacks
    (lacked_attributes): it compiled a video's or a sound's `path` longer
    than its `path_m` while their `from` was 0, and a variable's `txt`
    longer than its `txt_maxl` while it held a number (Editor 3.1.73). It
    is taken to do alike for an animation's or a video's `vid`, which has
    no bound."""
    def value_of(name: str):
        stored = page_object.attribute(name)
        return None if stored is None else int.from_bytes(stored, "little")
    if attribute in lacked_attributes(TYPE_NAMES.get(object_type), value_of):
        return None
    if (object_type, bound) in _BOUNDS_COMPILED_TO_THEIR_ROOM:
        room = (limit + 1 + 3) // 4 * 4
        return room - 1
    return limit


def bounded_attributes(object_type, names) -> list:
    """Returns (attribute, the attribute holding the most bytes it takes) of
    an object of type number `object_type`, among its attributes' `names`:
    a `txt` and its `txt_maxl`, and each `X_m` with its `X`, such as a
    `path_m` with its `path`. The screen keeps no more of a value code
    stores (the test machine's "text limits"). The Editor refuses to compile
    a longer one ("The length exceeds the maximum value"), but where
    _most_compiled says otherwise. Seen for every `X_m` of every type
    (Editor 3.1.73). A sliding text's `path_m` is none: its hint says it
    sets aside room for the text's lines."""
    return [("txt", "txt_maxl")] + [
        (name[:-2], name) for name in names
        if name.endswith("_m") and (object_type, name) not in _NOT_BOUNDS]
