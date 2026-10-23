"""The memory probe's projects (memory_probe.py): what each page holds, and
the source folder nxwright builds each from. They need nxwright, but not the
Editor.

A case is one page of a probe project, after page0, which stays empty. Its
components are given by their type and the values they take away from the
series' base: their defaults, with `vscope` 0 for local scope, and in place
of a default the series refuses, the value measured instead, global scope
for a type the series takes of global scope alone (memory_probe.py)."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import tomllib
import wave

import tomli_w

from nxwright.project.device_settings import DeviceSettings
from nxwright.project.editor_language import EDITOR_PROGRAM_DECLARATION
from nxwright.project.editor_limits import bounded_attributes
from nxwright.project.object_types import TYPES_BY_NAME
from nxwright.project.pictures import write_png
from nxwright.project.screen_models import model_named
from nxwright.project.font_drawing import draw_font_block
from nxwright.project.truetype import NOTO_SANS, noto_sans
from nxwright.project.attribute_descriptions import describe
from nxwright.project.component_defaults import nxwright_defaults
from nxwright.project.page_text import is_string_attribute
from nxwright.source.page_source import (attribute_range, page_file_text, page_toml_path,
                                         reference_kind)
from nxwright.source.project_files import build
from nxwright.language.resource_names import ANIMATION, FONT, PICTURE, SOUND, VIDEO
from nxwright.source.source_folder import new_source_folder
from nxwright.source.resource_adding import add_animation, add_font, add_sound, add_video
from nxwright.source.keyboard_adding import add_keyboard

# The types a page may hold, by the names component_defaults gives them.
TYPES = tuple(sorted(name for name in TYPES_BY_NAME if name != "page"))
# The types with no place on the page: their components have no x, y, w, or h.
UNPLACED = frozenset(name for name in TYPES
                     if "x" not in dict(nxwright_defaults()[TYPES_BY_NAME[name]].attributes))
# The types that play what a project holds, and the kind each plays.
PLAYED = {"gmov": ANIMATION, "video": VIDEO, "audio": SOUND}
# The scope attribute: 1 for global scope, 0 for local.
SCOPE = "vscope"
# Attributes the rounds that vary each attribute leave as they are: the
# scope, which global cases set, and the keyboard a component is bound to,
# which binds only one of global scope, beside a keyboard page, and which
# the probe's round of keyboards sets (memory_probe.py).
KEPT = frozenset({SCOPE, "key"})
# The picture and font names every probe folder holds, and the extra font a
# varied case takes in place of the first.
PICTURES = ("picture0", "picture1")
FONTS = ("NotoSans24", "NotoSans16")
SECOND_FONT_HEIGHT = 16
# The pictures' size, also the frames' of the animation and the video: a
# project of two pictures the screen's size took over a minute to open, and
# the size changes no memory.
PICTURE_SIDE = 32
# Changed whenever the way a probe folder is made changes, so that a project
# made the old way, kept in the probe's folder, is not taken for a new one.
MAKING = 2
# The attributes that read another while their own value is 0, {(type,
# attribute): the other}. A sliding text's `path_m`, the room for its lines,
# takes its `txt_maxl` at 0, as its description says, and as the compile
# counted it on the Intelligent and Edge series.
FALLBACKS = {("sliding-text", "path_m"): "txt_maxl"}


def is_buffer(attribute: str) -> bool:
    """Whether an attribute sets how many bytes a component keeps for
    something: `txt_maxl`, an `_m` attribute, `molloc`, or `molloc_s`."""
    return attribute == "txt_maxl" or attribute.endswith("_m") or attribute.startswith("molloc")


def bounded_text(kind: str, buffer: str):
    """The text attribute of `kind` whose most bytes `buffer` sets, as the
    build pairs them (editor_limits.bounded_attributes): `txt` for
    `txt_maxl`, `path` for `path_m`. None for a buffer that bounds no text
    of the type, as `molloc`, or a sliding text's `path_m`."""
    own = defaults(kind)
    text = next((attribute for attribute, bound in bounded_attributes(TYPES_BY_NAME[kind], own)
                 if bound == buffer), None)
    return text if isinstance(own.get(text), str) else None


def defaults(kind: str) -> dict:
    """A type's attributes and their defaults, as values: numbers, or texts
    for its string attributes, from nxwright's component defaults."""
    number = TYPES_BY_NAME[kind]
    return {attribute: (value.decode("latin-1") if is_string_attribute(number, attribute)
                        else int.from_bytes(value, "little"))
            for attribute, value in nxwright_defaults()[number].attributes}


def most_value(kind: str, attribute: str) -> int:
    """The largest number an attribute of `kind` holds, by the bytes its
    default is stored in: 65535 for a colour's two."""
    stored = dict(nxwright_defaults()[TYPES_BY_NAME[kind]].attributes)[attribute]
    return 2 ** (8 * len(stored)) - 1


@dataclass(frozen=True)
class Component:
    """A component of a case: its type, and its values away from the base,
    as ((attribute, value), ...)."""
    kind: str
    values: tuple = ()


@dataclass(frozen=True)
class Case:
    """A page of a probe project: what it measures, as a key such as
    "type text" or "value text txt_maxl 20"; its components; its own
    attributes away from their defaults; and its event code, in which
    `<page>` stands for its page's name, which the project gives it."""
    key: str
    components: tuple = ()
    page_values: tuple = ()
    code: str = ""


@dataclass(frozen=True)
class Project:
    """A probe project: its screen model, its cases, a page each after
    page0, how many `int`s program.nx declares beyond sys0 to sys2, its
    encoding and rotation, each type's base values, as {type: ((attribute,
    value), ...)}, and the kinds of nxwright's keyboard pages it holds
    after its cases' (keyboard_adding.add_keyboard), as "keypad"."""
    model: str
    cases: tuple
    base: tuple = ()
    ints: int = 0
    encoding: str = "iso-8859-1"
    rotation: int = 0
    keyboards: tuple = ()

    def name(self) -> str:
        """A name for its folder, from what it holds, so that a project made
        again is found again."""
        made = [MAKING, self.model, [vars(case) for case in self.cases], self.base, self.ints,
                self.encoding, self.rotation]
        # A project without keyboards is made as before they could be held,
        # so it keeps its name.
        if self.keyboards:
            made.append(list(self.keyboards))
        text = json.dumps(made, default=vars)
        return "%s-%s" % (self.model, hashlib.sha256(text.encode("utf-8")).hexdigest()[:16])

    def page_names(self) -> list:
        return ["page0"] + ["p%03d" % number for number in range(1, len(self.cases) + 1)]

    def values_of(self, case_component: Component) -> dict:
        """A component's values as built: its type's base, then its own."""
        values = dict(dict(self.base).get(case_component.kind, ()))
        values.update(case_component.values)
        return values


def build_project(project: Project, folder: Path) -> Path:
    """Writes the source folder of `project` in `folder`/app, unless an
    earlier run did, and builds it to `folder`/p.HMI. Returns the project
    file. Raises NxwrightError when nxwright refuses to build it."""
    app, built = folder / "app", folder / "p.HMI"
    if built.exists():
        return built
    if not app.exists():
        _write_folder(project, app)
    # The cases hold what the Editor's compile refuses on purpose, to see it
    # refuse them: what a series refuses, and pages past the screen's
    # memory. The build's checks against the table the probe measures are
    # left out.
    build(app, built, refuse_by_table=False)
    return built


def _write_folder(project: Project, app: Path):
    model = model_named(project.model)
    settings = DeviceSettings(model, project.rotation, project.encoding)
    new_source_folder(app, settings, "nextion")
    if project.encoding == "utf-8":
        # A utf-8 case's first font holds U+0020 to U+007E alone, as the
        # cases were measured with; a new utf-8 folder's font of that name
        # holds U+0000 to U+00FF.
        listed = tomllib.loads((app / "app.toml").read_text(encoding="utf-8"))["fonts"]
        if listed != [FONTS[0]]:
            raise RuntimeError("a new utf-8 folder's fonts are %s, where the cases take %s"
                               % (listed, [FONTS[0]]))
        (app / "fonts" / (FONTS[0] + ".zi")).write_bytes(draw_font_block(
            FONTS[0], noto_sans(), 24, "utf-8", project.rotation, characters=range(0x20, 0x7f)))
    add_font(app, NOTO_SANS, SECOND_FONT_HEIGHT, FONTS[1],
             characters="20-7e" if project.encoding == "utf-8" else None)
    width, height = settings.page_size
    pictures = app / "pictures"
    pictures.mkdir()
    for number, name in enumerate(PICTURES):
        colour = bytes([200 * number, 100, 50, 255])
        (pictures / ("%s.png" % name)).write_bytes(
            write_png(PICTURE_SIDE, PICTURE_SIDE, colour * PICTURE_SIDE ** 2))
    kinds = {component.kind for case in project.cases for component in case.components}
    if kinds & set(PLAYED):
        _add_media(app, pictures, kinds)
    data = tomllib.loads((app / "app.toml").read_text(encoding="utf-8"))
    data["pages"] = project.page_names()
    data["pictures"] = list(PICTURES)
    (app / "app.toml").write_text(tomli_w.dumps(data), encoding="utf-8", newline="\n")
    ints = "".join(",probe%d=0" % number for number in range(project.ints))
    program = (app / "program.nx").read_text(encoding="utf-8")
    program = program.replace(EDITOR_PROGRAM_DECLARATION, EDITOR_PROGRAM_DECLARATION + ints, 1)
    (app / "program.nx").write_text(program, encoding="utf-8", newline="\n")
    for page_name, case in zip(project.page_names(), (Case("empty"),) + project.cases):
        (app / page_toml_path(page_name)).write_text(
            _page_text(project, page_name, case, width, height), encoding="utf-8", newline="\n")
        code = case.code.replace("<page>", page_name)
        (app / "pages" / ("%s.nx" % page_name)).write_text(code, encoding="utf-8", newline="\n")
    for kind in project.keyboards:
        add_keyboard(app, kind)


def _add_media(app: Path, pictures: Path, kinds: set):
    """Adds an animation, a video, and a sound, the first of each kind,
    for the played types the cases hold."""
    frames = [pictures / ("%s.png" % name) for name in PICTURES]
    if "gmov" in kinds:
        add_animation(app, frames, 50, "animation0")
    if "video" in kinds:
        add_video(app, frames, name="video0")
    if "audio" in kinds:
        sound = app / "sound0-source.wav"
        with wave.open(str(sound), "wb") as written:
            written.setnchannels(1)
            written.setsampwidth(1)
            written.setframerate(8000)
            written.writeframes(bytes([128]) * 800)
        add_sound(app, sound, "sound0")
        sound.unlink()


def _page_text(project: Project, page_name: str, case: Case, width: int, height: int) -> str:
    page = {"name": page_name, "type": "page", "x": 0, "y": 0, "w": width, "h": height}
    page.update(case.page_values)
    tables = [page]
    for index, case_component in enumerate(case.components):
        table = {"name": "c%d" % index, "type": case_component.kind}
        table.update(project.values_of(case_component))
        tables.append(table)
    return page_file_text(tables)


def varied_values(kind: str, attribute: str, base: dict) -> list:
    """The values to try in place of an attribute's base value, so as to see
    whether its value changes the type's cost, best first; [] for one no case
    changes. A choice: the other choices. A picture, a font, or what a
    component plays: another the probe folder holds. A number: one more,
    then one less, as its bytes hold them; where the build knows the
    Editor's range (page_source.attribute_range), within that range. A
    text: as long, of other characters; an empty one, "x", where its buffer
    holds one; and a value of a byte or two kept as text, its other choices,
    or its last byte changed by one."""
    if attribute in KEPT or is_buffer(attribute):
        return []
    value = base[attribute]
    number = TYPES_BY_NAME[kind]
    kind_of_resource = reference_kind(number, attribute)
    if kind_of_resource == PICTURE:
        return [PICTURES[1]]
    if kind_of_resource == FONT:
        return [FONTS[1]]
    if kind_of_resource in (ANIMATION, VIDEO, SOUND):
        return [{ANIMATION: "animation0", VIDEO: "video0", SOUND: "sound0"}[kind_of_resource]]
    description = describe(kind, attribute)
    if isinstance(value, str):
        if value and not value.isprintable():
            # A value of a byte or two kept as text, as a waveform's `dir`.
            if description is not None and description.choices and len(value) == 1:
                return [chr(choice) for choice in sorted(description.choices)
                        if chr(choice) != value]
            last = ord(value[-1])
            return [value[:-1] + chr(last + 1 if last < 255 else last - 1)]
        if not value:
            buffer = "txt_maxl" if attribute == "txt" else attribute + "_m"
            return ["x"] if base.get(buffer, 1) >= 1 else []
        return ["".join("x" if char != "x" else "y" for char in value)]
    if description is not None and description.choices:
        return [choice for choice in sorted(description.choices) if choice != value]
    allowed = attribute_range(number, attribute) or range(0, most_value(kind, attribute) + 1)
    return [other for other in (value + 1, value - 1) if other in allowed]


def placement(kind: str, width: int, height: int) -> dict:
    """A placed type's x, y, w, and h: its defaults, within a screen
    `width` by `height`."""
    if kind in UNPLACED:
        return {}
    own = defaults(kind)
    return {"x": 0, "y": 0, "w": min(own["w"], width), "h": min(own["h"], height)}
