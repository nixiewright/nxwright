"""The probes of the rooms of P's types at the most the Nextion Editor
takes, which no entry gives. A room sets how many bytes a type keeps for
one of its texts, such as a path's path_m. The Nextion Editor takes each
room up to 65534, and refuses 65535 ("Out of range"), but a select's
path_m, which it takes up to 8192.

Each room is probed twice: at its most, its text at its default; and at
1000, past the most the check took before, its text of 1000 letters. A video
and an audio play from a file, as their path_m has a room only then. Each
probe is built on P and on E, one component on page0, and compares the
whole file. Run them with `tools.tft.probe run room_probes`.
"""
from tools.tft.probing.component_probes import editor_file, whole_file, with_components
from tools.tft.probing.probe_runner import Probe

# Each type's name for its component, and its place and size where it has
# them, in a page file's form.
_COMPONENT = {
    "file-browser": ("fbrowser0", "x = 10\ny = 60\nw = 240\nh = 200\n"),
    "select": ("select0", "x = 10\ny = 10\nw = 90\nh = 60\n"),
    "data-record": ("data0", "x = 10\ny = 60\nw = 240\nh = 200\n"),
    "external-picture": ("exp0", "x = 10\ny = 10\nw = 100\nh = 100\n"),
    "video": ("vd0", "x = 10\ny = 10\nw = 128\nh = 128\n"),
    "audio": ("wav0", ""),
    "combo-box": ("cb0", "x = 10\ny = 10\nw = 100\nh = 30\n"),
    "gmov": ("gm0", "x = 10\ny = 10\nw = 128\nh = 128\n"),
    "sliding-text": ("slt0", "x = 10\ny = 10\nw = 120\nh = 120\n"),
}
# The types that play from a file, and the path each plays when the probe
# gives none.
_FROM_A_FILE = {"video": "sd0/a.video", "audio": "sd0/a.wav"}
# Each room, its text, and the most the Nextion Editor takes, by type.
ROOMS = {
    "file-browser": [("dir_m", "dir", 0xFFFE), ("txt_m", "txt", 0xFFFE),
                     ("filter_m", "filter", 0xFFFE), ("vvs2_m", "vvs2", 0xFFFE)],
    "select": [("path_m", "path", 8192), ("txt_maxl", "txt", 0xFFFE)],
    "data-record": [("format_m", "format", 0xFFFE), ("filter_m", "filter", 0xFFFE)],
    "external-picture": [("path_m", "path", 0xFFFE)],
    "video": [("path_m", "path", 0xFFFE)],
    "audio": [("path_m", "path", 0xFFFE)],
    "combo-box": [("path_m", "path", 0xFFFE)],
    "gmov": [("path_m", "path", 0xFFFE)],
    "sliding-text": [("path_m", "path", 0xFFFE)],
}
# A room past the most the check took before, and the length of its text.
_FILLED = 1000


def _component(type_name: str, attributes: dict) -> str:
    """Returns the component of `type_name` in a page file's form, with
    `attributes`, {name: a number or a text}. A video and an audio play from
    a file, their path _FROM_A_FILE's unless `attributes` gives one."""
    name, place = _COMPONENT[type_name]
    if type_name in _FROM_A_FILE:
        attributes = {"from": 1, "path": _FROM_A_FILE[type_name], **attributes}
    lines = "".join('%s = "%s"\n' % item if isinstance(item[1], str) else "%s = %d\n" % item
                    for item in attributes.items())
    return '\n[[component]]\nname = "%s"\ntype = "%s"\n%s%s' % (name, type_name, place, lines)


def _filled(rooms: list) -> dict:
    """Returns the attributes that fill each of `rooms` to _FILLED, its text
    of as many letters."""
    return {name: value for room, text, _ in rooms
            for name, value in ((room, _FILLED), (text, "a" * _FILLED))}


PROBES = [
    Probe("%s-%s-%s-at-its-most" % (series.lower(), type_name, room.replace("_", "-")), series,
          with_components(_component(type_name, {room: most})), whole_file, editor_file)
    for series in ("P", "E") for type_name, rooms in ROOMS.items()
    for room, _, most in rooms
] + [
    Probe("%s-%s-rooms-filled" % (series.lower(), type_name), series,
          with_components(_component(type_name, _filled(rooms))),
          whole_file, editor_file)
    for series in ("P", "E") for type_name, rooms in ROOMS.items()
]
