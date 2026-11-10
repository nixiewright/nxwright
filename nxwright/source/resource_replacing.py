"""Replacing a resource of a source folder (`nxwright replace`): a new file
written into its place, by the function that adds its kind
(resource_adding.py, with a Slot), so that it keeps its ID, and its name
unless it is given another.

Each setting that is not given is read from the current resource's files. A
font drawn from a typeface takes the current font's height and smoothing, and
in utf-8 its characters. An animation takes its frames' duration, and a video
its rate, and its size when it is cut from a video file. A placeholder
(resource_adding.add_placeholder) gives no defaults, because its own settings
would make poor ones. A sound takes no settings from the sound it replaces.
"""
from pathlib import Path
import re

from nxwright import NxwrightError
from nxwright.language.resource_names import LISTS
from nxwright.project.font_drawing import code_point_ranges
from nxwright.project.media_files import animation_frames, video_frames
from nxwright.project.pictures import still_picture_size
from nxwright.project.zi_font import UTF8, decode_font, font_facts
from nxwright.source.resource_adding import (PLACEHOLDER_NAME, VIDEO_RATE, Slot, add_animation,
                                             add_font, add_font_file, add_pictures, add_sound,
                                             add_video)
from nxwright.source.resource_removal import KINDS, resource_uses
from nxwright.source.source_folder import read_app, read_bytes

# The options each kind takes, as replace_resource takes them: those of the
# function adding the kind, beside its files and name.
OPTIONS = {"picture": (), "font": ("height", "smoothed", "characters", "full_table"),
           "animation": ("duration",), "video": ("rate", "size", "start", "length", "ffmpeg"),
           "sound": ("rate", "mono", "ffmpeg")}
_PLACEHOLDER = re.compile(PLACEHOLDER_NAME.replace("%d", r"[1-9][0-9]*"))


def is_placeholder(name: str) -> bool:
    """Whether `name` is one a placeholder takes (PLACEHOLDER_NAME)."""
    return bool(_PLACEHOLDER.fullmatch(name))


def current_settings(source_folder: Path, kind: str, name: str) -> dict:
    """Returns the settings of the resource `name` of `kind`, a word of KINDS,
    that replacing it takes as defaults, read from its files: a font's
    {"height", "smoothed"}, and in utf-8 also "characters", its table's code
    points as code_points_of reads them, or None in a full table, and
    "fullTable"; an animation's {"duration"} of its first frame, in ms; a
    video's {"rate", "size": [width, height]}; {} for a picture, a sound, and
    a placeholder. Raises NxwrightError for a kind or a name the folder
    does not have, and a file that cannot be read."""
    source_folder = Path(source_folder)
    listed = _listed(source_folder, kind, name)
    if is_placeholder(name):
        return {}
    if kind == "font":
        block = read_bytes(source_folder / listed / (name + ".zi"))
        facts = font_facts(block)
        settings = {"height": facts.height, "smoothed": facts.smoothed}
        if facts.encoding == UTF8:
            font = decode_font(block)
            full = font.advances is not None
            settings.update(characters=None if full else code_point_ranges(sorted(font.characters)),
                            fullTable=full)
        return settings
    if kind == "animation":
        frames = animation_frames(read_bytes(source_folder / listed / (name + ".screen.gmov")))
        duration = frames.starts[1] - frames.starts[0] if len(frames.starts) > 1 else frames.length
        return {"duration": duration}
    if kind == "video":
        frames = video_frames(read_bytes(source_folder / listed / (name + ".video")))
        return {"rate": frames.rate, "size": [frames.width, frames.height]}
    return {}


def replace_resource(source_folder: Path, kind: str, name: str, files: list,
                     new_name: str = None, checked: bool = False, **options) -> tuple:
    """Writes a new resource of `kind` into the place of the resource `name`.
    The new resource is made from `files` with `options` (OPTIONS), and is
    named `new_name`, or else `name`. A setting not given defaults to the
    current one, as the module's docstring says. Returns (its name, a warning
    or None, the old files deleted, a sentence for each that could not be).

    Raises NxwrightError, writing nothing, for a kind or a name the folder
    does not have, an option its kind does not take, no file, a font's
    height that neither is given nor can be read, and whatever the function
    adding the kind refuses. With `checked` and a `new_name`, also raises it
    if the folder uses the resource by name. Without `checked`, the folder
    is not searched, so a page file or code that still uses the old name no
    longer builds."""
    source_folder = Path(source_folder)
    _listed(source_folder, kind, name)
    wrong = sorted(set(options) - set(OPTIONS[kind]))
    if wrong:
        raise NxwrightError("a %s takes no %s" % (kind, wrong[0].replace("_", " ")))
    if not files:
        raise NxwrightError("replacing a %s needs a file" % kind)
    if checked and new_name is not None and new_name != name:
        _check_unused_by_name(source_folder, kind, name)
    options = _with_defaults(source_folder, kind, name, files, options)
    slot, warning = Slot(name), None
    files = [Path(file) for file in files]
    if kind == "picture":
        new_name = add_pictures(source_folder, files, slot, new_name)[0]
    elif kind == "font" and files[0].suffix.lower() == ".zi":
        if len(files) > 1 or options:
            raise NxwrightError("a font file (.zi) is taken alone, as it is: give no other file "
                                "and no setting")
        new_name, warning = add_font_file(source_folder, files[0], new_name, slot)
    elif kind == "font":
        if len(files) > 1:
            raise NxwrightError("a font is drawn from one typeface file")
        if options.get("height") is None:
            raise NxwrightError("give the font's height: the font it replaces gives none to keep")
        new_name, warning = add_font(source_folder, files[0], options["height"], new_name,
                                     options.get("smoothed", True), options.get("characters"),
                                     options.get("full_table", False), replacing=slot)
    elif kind == "animation":
        new_name = add_animation(source_folder, files, options.get("duration"), new_name, slot)
    elif kind == "video":
        new_name = add_video(source_folder, files, options.get("rate", VIDEO_RATE),
                             options.get("size"), options.get("start"), options.get("length"),
                             new_name, options.get("ffmpeg"), slot)
    else:
        if len(files) > 1:
            raise NxwrightError("a sound is made of one file")
        new_name = add_sound(source_folder, files[0], new_name, options.get("rate"),
                             options.get("mono", False), options.get("ffmpeg"), slot)
    return new_name, warning, slot.deleted, slot.left


def _listed(source_folder: Path, kind: str, name: str) -> str:
    """Returns app.toml's list of `kind`, a word of KINDS. Raises
    NxwrightError for a kind it is not, or a name the list lacks."""
    if kind not in KINDS:
        raise NxwrightError("%s is not a kind of resource: %s" % (kind, ", ".join(KINDS)))
    listed = LISTS[KINDS[kind]]
    if name not in read_app(source_folder)[listed]:
        raise NxwrightError("the folder has no %s named %s" % (kind, name))
    return listed


def _check_unused_by_name(source_folder: Path, kind: str, name: str):
    """Raises NxwrightError while the folder uses the resource by name, as
    those uses would name nothing once it takes another name."""
    _, _, uses = resource_uses(source_folder, kind, name)
    by_name = [use for use in uses if use.by == "name"]
    if by_name:
        raise NxwrightError("cannot give the %s %s another name while the folder uses it by "
                            "name. Rename it with nxwright rename first, then replace it. "
                            "Its uses:\n%s"
                            % (kind, name, "\n".join("  %s" % use for use in by_name)))


def _with_defaults(source_folder: Path, kind: str, name: str, files: list,
                   options: dict) -> dict:
    """Returns `options` with each setting not given taken from the current
    resource (current_settings), where it applies to `files`."""
    current = current_settings(source_folder, kind, name)
    given = {key: value for key, value in options.items() if value is not None}
    if kind == "font" and Path(files[0]).suffix.lower() != ".zi":
        for key in ("height", "smoothed"):
            if key in current:
                given.setdefault(key, current[key])
        # In utf-8, the characters follow the current font's unless either
        # is given.
        if "characters" not in given and "full_table" not in given and "fullTable" in current:
            if current["fullTable"]:
                given["full_table"] = True
            else:
                given["characters"] = current["characters"]
    elif kind == "animation" and Path(files[0]).suffix.lower() != ".gmov":
        if "duration" in current:
            given.setdefault("duration", current["duration"])
    elif kind == "video":
        if "rate" in current:
            given.setdefault("rate", current["rate"])
        # A size is for a video file to cut; still pictures are taken as they are.
        stills = all(still_picture_size(Path(file)) is not None for file in files)
        if "size" in current and not stills:
            given.setdefault("size", tuple(current["size"]))
    return given
