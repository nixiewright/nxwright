"""Limits of the Nextion Editor that a page or a project can break. The
build checks them before it writes the page, because the Nextion Editor
reports them only when it opens or compiles the project, far from the page
file at fault. They are:

- the names and texts of a page and its components;
- how many components a page has in all (MOST_COMPONENTS), and how many of
  some kinds (PAGE_CAPS);
- a component reaching past the screen, on a series that refuses it
  (check_component_places);
- how many pages a project has (MOST_PAGES).

The module also says which attributes a component has under its choices
and its series (lacked_attributes, screen_holds).

The types and choices a series refuses are checked in
source/series_components.py, as that check reads the attributes'
descriptions. The Editor's language is editor_language.py's, and the
screen's arithmetic screen_arithmetic.py's."""
from dataclasses import dataclass

from nxwright import NxwrightError, after_start
from nxwright.project.editor_language import NAMES_THE_EDITOR_REFUSES
from nxwright.project.object_types import TYPE_NAMES, TYPES_BY_NAME
from nxwright.project.page_block import Attribute, PageBlock
from nxwright.project.screen_models import ScreenModel

# The Editor keeps this many bytes of a page's or component's name, and cuts
# the rest when it opens the project; code naming the full name then fails.
NAME_LIMIT = 14
# The most bytes the Editor takes in a line of code, by series, in the
# project's encoding, counted without the spaces its compile drops
# (code_lines.compact). A longer line it refuses as it compiles: "The
# instructions are too long". An `int` declaration has no limit, and
# neither does the head of an `if` or a `while` as a whole. But each
# comparison in a condition has one, because the Editor compiles it into a
# line of its own. A `for`'s start and step are limited like lines too.
LONGEST_LINES = {"T": 767, "K": 767, "F": 767, "P": 4095, "E": 4095}
# The least width and height the Editor takes for a component: narrower or
# lower, it says "Width can not be less than 2" as it opens the project, and
# sets the side back to its type's default. It did so for every type with a
# place, on an Intelligent screen.
LEAST_SIDE = 2
# The values the Editor gives a component it adds on a screen of each
# series, by the series' letter, where they differ from nxwright's component
# defaults, which came from an Intelligent screen: {series: {type:
# {attribute: value}}}. On the basic, Enhanced, and Discovery series, its
# Toolbox added a gauge with `sta` 1, a colour, where their compile refuses
# the Intelligent's 3. Only the gauge was added: it is the one type whose
# default the memory table shows these series refusing. (Worked out from
# the Editor 1.68.2.)
SERIES_NEW_COMPONENT_VALUES = {series: {"gauge": {"sta": 1}} for series in ("T", "K", "F")}


# The most components the Nextion Editor's compile takes on a page, the page
# itself not counted. It refused a page of 251 on every series
# ("Error:Page:page0 Too many components."), hotspots or variables, of local
# or global scope alike. (Worked out from the Nextion Editor 1.68.2.)
MOST_COMPONENTS = 250
# The most pages the Nextion Editor's compile takes in a project. It refused
# a project of 252 on every series ("Error:Too many pages."). Its compile
# adds no keyboard page of its own, so it counts the pages app.toml lists.
# (Worked out from the Nextion Editor 1.68.2.)
MOST_PAGES = 251


@dataclass(frozen=True)
class PageCap:
    """A cap of the Editor's compile on one page's components: at most
    `most` of the types `types` together, which the build's messages call
    `words`."""
    types: frozenset           # type numbers
    most: int
    words: str


# The Editor's caps on a page's components. Past one, its compile fails,
# saying "Waveform components exceed maximum in page:5", for one. Worked out
# from the Editor 1.68.2: the caps were the same on every series that takes
# their kinds, and only the P and E series take animations and videos.
# Videos, sounds, animations, and file browsers are not counted among the
# timer events: 11 timers beside 2 of each compiled. Every other kind
# compiled 20 to a page, where memory allowed.
PAGE_CAPS = (
    PageCap(frozenset({TYPES_BY_NAME["waveform"]}), 5, "waveforms"),
    PageCap(frozenset({TYPES_BY_NAME["gmov"], TYPES_BY_NAME["video"]}), 16,
            "animations and videos"),
    PageCap(frozenset({TYPES_BY_NAME["timer"], TYPES_BY_NAME["scrolling-text"]}), 12,
            "timers and scrolling texts"),
)
# The attributes named `X_m` that bound no `X`'s length (bounded_attributes),
# by (type number, name).
_NOT_BOUNDS = {(TYPES_BY_NAME["sliding-text"], "path_m")}
# The attributes a component has only under some values of one of its
# choices, as its page file gives them: {type: {attribute: (the choice, the
# values under which the attribute exists)}}. Under any other value the
# component lacks it: the Editor's compile refused code naming it, assigned
# or read ("Invalid Variables"), and its simulator answered 0x1A to a typed
# line naming one, as to a name the page lacks. Each value of each choice
# of every type was compiled apart, the others at their defaults, on every
# series; the rules were the same on all. (Worked out from the Editor 1.68.2.)
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
# When a component lacks an attribute, in words, where a choice's value
# says more than "while `{name}.sta` is 1": {(type, choice, value): words}.
# `{name}` stands for the component's name (lacked_attributes).
_LACKED_WORDS = {
    ("variable", "sta", 0): "while `{name}` contains a number",
    ("variable", "sta", 1): "while `{name}` contains text",
    **{(kind, "from", 0): "while `{name}` plays an internal file (its `from` is 0)"
       for kind in ("video", "audio")},
    **{(kind, "from", 1): "while `{name}` plays a file of an SD card (its `from` is 1)"
       for kind in ("video", "audio")},
}
# Where a type is EVERY_TYPE, the attributes of every type that has them.
EVERY_TYPE = None
# The attributes a component lacks on a screen of each series, by the
# series' letter, whatever its choices: {series: {type: attributes}}. The
# Editor's compile refused code naming them, even read ("Invalid
# Variables"), on the Basic, Enhanced, and Discovery series, and took it on
# the Edge and Intelligent; `objname` on every object, the page too, which
# no page file holds. (Worked out from the Editor 1.68.2.)
SERIES_LACKED_ATTRIBUTES = {
    **{series: {EVERY_TYPE: frozenset(["movex", "movey", "lockobj", "groupid0", "groupid1",
                                       "sendkey", "objname"]),
                "waveform": frozenset(["objWid", "objHig", "inittrue", "molloc", "molloc_s"])}
       for series in ("T", "K", "F")},
    "E": {},
    "P": {},
}


def lacked_attributes(type_name: str, value_of, screen: ScreenModel = None) -> dict:
    """Returns {attribute: when, in words} of the attributes a component of
    the type `type_name`, as page files name types ("video"), lacks. The
    words end the sentence "t0.pic cannot be used", such as "while
    `{name}.sta` is 1" or "on the NX4832T035", with `{name}` where the
    component's name goes. A component lacks an attribute under
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
                                                  "while `{name}.%s` is %d" % (choice, value))
    if screen is not None:
        by_type = SERIES_LACKED_ATTRIBUTES[screen.series]
        for attribute in by_type.get(EVERY_TYPE, frozenset()) | by_type.get(type_name,
                                                                             frozenset()):
            lacked[attribute] = "on the %s" % screen.name
    return lacked


def object_lacked_attributes(page_object, type_name: str) -> dict:
    """Returns lacked_attributes for `page_object` of the type `type_name`,
    reading its choices from its stored attributes."""
    def value_of(name: str):
        stored = page_object.attribute(name)
        return None if stored is None else int.from_bytes(stored, "little")
    return lacked_attributes(type_name, value_of)


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
# (Worked out from the Editor 1.68.2.)
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


def check_page_limits(page: PageBlock, where: str):
    """Raises NxwrightError when:
      - the name of the page or of one of its components is longer than
        NAME_LIMIT, in stored bytes, starts with a digit, or is a name that
        the Nextion Editor rejects (NAMES_THE_EDITOR_REFUSES);
      - a text is longer than its bound, in stored bytes (bounded_attributes);
      - the page has more components than MOST_COMPONENTS
        (check_component_count);
      - the page has more components of one kind than the Nextion Editor's
        compile accepts (PAGE_CAPS).
    The message starts with `where`, the file at fault, unless `where` is
    empty (after_start). The error's `table` is the number of the object at
    fault, counted from 0 for the page. When a kind has too many components,
    the object at fault is the first component past the cap."""
    check_component_count([(page_object.attribute("objname") or b"").decode("latin-1")
                           for page_object in page.objects], 0, where)
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
# Editor 1.68.2, on texts, hotspots, and scrolling texts. In a later probe,
# every type with a place that each series takes was refused past the right
# edge, and a text one pixel past the right or the bottom edge, where one
# ending at both edges compiled.) A negative x or y, and a side under 2, the
# build refuses before this: their bytes hold no negative value, and
# LEAST_SIDE is the least side.
SERIES_REFUSING_PLACES_PAST_THE_SCREEN = frozenset({"T", "K", "F"})


def check_component_places(page: PageBlock, screen: ScreenModel, page_size: tuple, where: str):
    """Raises NxwrightError for the first component of the page that reaches
    past the screen, if the series of `screen`, the folder's screen model,
    does not allow it (SERIES_REFUSING_PLACES_PAST_THE_SCREEN). `page_size`
    is the screen's (width, height) at its rotation. A component without a
    place is not checked. The message starts with `where`, the file at
    fault, unless `where` is empty (after_start), and the error's `table` is
    the component's number in the page."""
    if screen.series not in SERIES_REFUSING_PLACES_PAST_THE_SCREEN:
        return
    width, height = page_size
    for index, page_object in enumerate(page.objects[1:], start=1):
        place = [page_object.attribute(key) for key in ("x", "y", "w", "h")]
        if None in place:
            continue
        x, y, w, h = (int.from_bytes(value, "little") for value in place)
        if x + w > width or y + h > height:
            error = NxwrightError(after_start(
                where, "%s reaches past the screen, which is %d by %d at this rotation"
                % (object_label(page_object, index), width, height)))
            error.table = index
            raise error


# Attributes code can change on the other series that the Editor's compile
# refused code to assign to on a series ("Assignment operation failed"), by
# the series' letter: {series: {type: attributes}}, EVERY_TYPE's those of
# every type that has them. It took code reading them.
#
# The Basic, Enhanced, and Discovery series refused aph, drag, and effect,
# on each of their types that has them, the page among them (worked out
# from the Editor 1.68.2). They refused x and y on each of the 15 types
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


def check_component_count(names: list, generated: int, where: str):
    """Raises NxwrightError when a page has more components than the Nextion
    Editor's compile accepts (MOST_COMPONENTS). The message starts with
    `where`, the file at fault, unless `where` is empty (after_start).
    `names` are the names of the page's objects, the page first, and the
    last `generated` of them are the components nxlang adds to run the
    page's code.

    When the page file's own components are too many, the error's `table` is
    the number of the first component past the limit, counted from 0 for the
    page. When only the components that nxlang adds take the page past the
    limit, the message gives how many nxlang adds, and the error's `table`
    is 0, the page's own table."""
    components = len(names) - 1
    own = components - generated
    if own > MOST_COMPONENTS:
        error = NxwrightError(after_start(
            where, "the page has %d components, and the limit is %d. %s"
            % (own, MOST_COMPONENTS, _components_to_remove(own))))
        error.table = MOST_COMPONENTS + 1
        raise error
    if components > MOST_COMPONENTS:
        error = NxwrightError(after_start(
            where, "the page has %d components, and the limit is %d. nxlang adds %d of them "
            "to run the page's code. %s"
            % (components, MOST_COMPONENTS, generated, _components_to_remove(components))))
        error.table = 0
        raise error


def _components_to_remove(components: int) -> str:
    """Returns the end of the refusal of a page of `components` components:
    how many components to remove."""
    past = components - MOST_COMPONENTS
    return ("Remove %d %s, or move %s to another page."
            % (past, "component" if past == 1 else "components", "it" if past == 1 else "them"))


def page_count_refusal(pages: int, whose: str):
    """Returns the refusal of a project of `pages` pages, when it has more
    than MOST_PAGES, starting with `whose`, such as "the project". Returns
    None when the Nextion Editor's compile takes that many."""
    if pages <= MOST_PAGES:
        return None
    past = pages - MOST_PAGES
    return ("%s has %d pages, and the limit is %d. Remove %d %s."
            % (whose, pages, MOST_PAGES, past, "page" if past == 1 else "pages"))


def check_room_for_a_page(pages: int):
    """Raises NxwrightError when a folder of `pages` pages has no room for
    another one, as the Nextion Editor's compile takes at most MOST_PAGES."""
    if pages >= MOST_PAGES:
        raise NxwrightError("the project already has %d pages, which is the limit. Remove a page "
                            "first." % pages)


def object_label(page_object, index: int) -> str:
    """How a refusal names an object of a page: "page `home`", or "component `t0`"."""
    name = (page_object.attribute("objname") or b"").decode("latin-1")
    return "%s `%s`" % ("page" if index == 0 else "component", name)


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
            error = NxwrightError(after_start(
                where, "the page has %d %s, and the limit is %d"
                % (len(held), cap.words, cap.most)))
            error.table = held[cap.most]
            raise error


def _check_object_limits(page_object, index: int, where: str):
    name = page_object.attribute("objname") or b""
    label = object_label(page_object, index)
    if len(name) > NAME_LIMIT:
        raise NxwrightError(after_start(
            where, "the name of %s has %d bytes, and the limit is %d"
            % (label, len(name), NAME_LIMIT)))
    # The Nextion Editor says "Illegal name" for such a name.
    if name.decode("latin-1") in NAMES_THE_EDITOR_REFUSES:
        raise NxwrightError(after_start(where, "%s has a reserved name" % label))
    # The Nextion Editor refuses such a page or component as it opens the
    # project ("First character of a Name can not be number").
    if name[:1].isdigit():
        raise NxwrightError(after_start(
            where, "the name of %s cannot start with a digit" % label))
    kind = page_object.attribute("type")
    object_type = kind[0] if kind else None
    # An attribute the component lacks is not checked (lacked_attributes).
    # The Editor's compile does not check it either: it compiled a video's or
    # a sound's `path` longer than its `path_m` while their `from` was 0, and
    # a variable's `txt` longer than its `txt_maxl` while it contained a
    # number (Editor 1.68.2). It is taken to do the same for an animation's
    # or a video's `vid`, which has no bound.
    lacked = object_lacked_attributes(page_object, TYPE_NAMES.get(object_type))
    # Every other text longer than its bound is refused. That includes a data
    # record's `format` and `dir`, which the Editor's compile took up to 3
    # bytes longer than their bound (Editor 1.68.2). The screen has that much
    # spare room for them, but the room is not documented, so it may differ
    # between screens or change.
    for attribute, length, bound, limit in _values_past_bounds(page_object):
        if attribute not in lacked:
            raise NxwrightError(after_start(
                where, "attribute `%s` of %s has %d bytes, and its limit, `%s`, is %d"
                % (attribute, label, length, bound, limit)))


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


def bounded_attributes(object_type, names) -> list:
    """Returns (attribute, the attribute holding the most bytes it takes) of
    an object of type number `object_type`, among its attributes' `names`:
    a `txt` and its `txt_maxl`, and each `X_m` with its `X`, such as a
    `path_m` with its `path`. The screen keeps no more of a value code
    stores (the test machine's "text limits"). The Editor refuses to compile
    a longer one ("The length exceeds the maximum value"), with the
    exceptions _check_object_limits gives. Seen for every `X_m` of every
    type (Editor 1.68.2). A sliding text's `path_m` is none: its hint says it
    sets aside room for the text's lines."""
    return [("txt", "txt_maxl")] + [
        (name[:-2], name) for name in names
        if name.endswith("_m") and (object_type, name) not in _NOT_BOUNDS]
