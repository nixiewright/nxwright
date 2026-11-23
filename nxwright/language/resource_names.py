"""Names for a project's pictures, fonts, animations, videos, and sounds in a
source folder.

A source folder refers to a picture, font, animation, video, or sound by
name, such as "mono-dark/toast", where the project stores its ID, a number;
the build turns each name into its ID. A name is made of letters, digits, "-"
and "_", in one or more parts separated by "/". A "/" makes a subfolder: the
picture's file is pictures/mono-dark/toast.png. Names are unique within
their kind even when letter case is ignored, since Windows file names ignore
it; a name cannot also be the folder part of another ("a" beside "a/b"); and
no part may be a name Windows keeps for devices ("con", "nul", ...).
"""
from dataclasses import dataclass, field
import re

from nxwright import NxwrightError
from nxwright.project.zi_font import stored_name

# The kinds of name, spelled as in "@pic(name)", "@font(name)", and so on.
PICTURE, FONT, ANIMATION, VIDEO, SOUND = "pic", "font", "animation", "video", "sound"
# Each kind's list in app.toml, and its folder of files.
LISTS = {PICTURE: "pictures", FONT: "fonts", ANIMATION: "animations", VIDEO: "videos",
         SOUND: "sounds"}
KIND_OF_LIST = {listed: kind for kind, listed in LISTS.items()}
# One of each kind, in messages.
NOUNS = {PICTURE: "picture", FONT: "font", ANIMATION: "animation", VIDEO: "video",
         SOUND: "sound"}
# A resource named in code, "@pic(name)", which the build turns into its ID:
# as text to match within other patterns, and as a pattern whose groups are
# the kind and the name.
REFERENCE_TEXT = r"@(?:%s)\([^()]*\)" % "|".join(LISTS)
REFERENCE = re.compile(r"@(%s)\(([^()]*)\)" % "|".join(LISTS))
_PART = re.compile(r"[A-Za-z0-9_-]+")
_DEVICE_NAMES = frozenset({"con", "prn", "aux", "nul"} | {"com%d" % n for n in range(1, 10)}
                          | {"lpt%d" % n for n in range(1, 10)})


class UnknownNameError(NxwrightError):
    """Raised for a reference to a resource's name that app.toml does not list."""


def is_device_name(name: str) -> bool:
    """True when `name` is a name Windows keeps for devices, such as "con",
    in any letter case. Windows does not let a file have such a name."""
    return name.lower() in _DEVICE_NAMES


def is_valid_name(name: str) -> bool:
    """True when `name` follows the character and device-name rules."""
    parts = name.split("/")
    return all(_PART.fullmatch(part) and not is_device_name(part) for part in parts)


def check_names(names: list, kind: str):
    """Raises NxwrightError unless `names`, the names of one kind in ID order,
    follow every rule in this module's docstring. `kind` is the kind's list
    in app.toml, such as "pictures". The error message says which kind the
    name is of."""
    noun = NOUNS[KIND_OF_LIST[kind]]
    seen = {}
    for name in names:
        # A reserved name is not valid as the file's name, or as the name of
        # one of its folders.
        if isinstance(name, str) and any(is_device_name(part) for part in name.split("/")):
            raise NxwrightError("`%s` is not a valid %s name, because Windows reserves it as a "
                                "file name, and %s are written as files" % (name, noun, kind))
        if not isinstance(name, str) or not is_valid_name(name):
            raise NxwrightError("`%s` is not a valid %s name. Use only letters, digits, `-`, and "
                                "`_`, with `/` for subfolders." % (name, noun))
        if name.lower() in seen:
            existing = seen[name.lower()]
            raise NxwrightError("%s `%s` already exists%s" % (
                noun, existing, "" if existing == name else " (resources are case insensitive)"))
        seen[name.lower()] = name
    folders = {"/".join(name.lower().split("/")[:end]) for name in names
               for end in range(1, name.count("/") + 1)}
    clashes = sorted(name for name in names if name.lower() in folders)
    if clashes:
        raise NxwrightError("`%s` cannot be both %s %s and a folder"
                            % (clashes[0], "an" if noun[0] in "aeiou" else "a", noun))


@dataclass
class ResourceNames:
    """The names of the pictures, fonts, animations, videos, and sounds, each
    in ID order."""
    pictures: list
    fonts: list
    animations: list = field(default_factory=list)
    videos: list = field(default_factory=list)
    sounds: list = field(default_factory=list)
    _ids: dict = field(init=False, repr=False, compare=False)

    def __post_init__(self):
        self._ids = {kind: {name: resource_id for resource_id, name in enumerate(self.names(kind))}
                     for kind in LISTS}

    @classmethod
    def of_app(cls, app: dict):
        """Returns the names a source folder's app.toml lists, as read."""
        return cls(*(app[LISTS[kind]] for kind in LISTS))

    def names(self, kind: str) -> list:
        """Returns the names of `kind`, such as PICTURE, in ID order."""
        return getattr(self, LISTS[kind])

    def name_of(self, kind: str, resource_id: int):
        """Returns the name of `kind`'s `resource_id`, or None if there is none."""
        names = self.names(kind)
        return names[resource_id] if 0 <= resource_id < len(names) else None

    def id_of(self, kind: str, name: str) -> int:
        """Returns the ID of the resource of `kind` called `name`.

        Raises UnknownNameError when there is no such name.
        """
        try:
            return self._ids[kind][name]
        except KeyError:
            raise UnknownNameError("unknown %s `%s`" % (NOUNS[kind], name)) from None


def font_header_name(font: bytes):
    """Returns the name the Editor's font generator stored in a font's header
    (such as "Impact16"), or None when there is none or it is not a valid
    name without "/"."""
    name = stored_name(font)
    if name is None or not name.isascii():
        return None
    text = name.decode("ascii")
    return text if is_valid_name(text) and "/" not in text else None
