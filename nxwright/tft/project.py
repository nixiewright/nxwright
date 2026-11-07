"""A project file, as the compile reads it through nxwright's project
modules: its device settings, its pages, its program.s, and its resources.

A compile builds a source folder into a project file, then reads it here.
Every piece of the compile takes a project in this form.

Each object of a project's pages is a Component: its records as stored,
which code may still read as nxwright's PageObject, with its attributes
found by name, and what describes it worked out the first time it is
needed (component_types.object_module). A project and its components are never
changed once made: code that needs another makes it with
dataclasses.replace, and the new one finds its own attributes. A project
made from another keeps its components, so they are not described again.
A component's events are clean (below), so code that makes a component
with other events gives them clean.

A Project keeps its code clean: program.s, each event's code, and each
macro's lines, as plain_lines gives them. The Nextion Editor stores code
as it was typed, with comments after code. Each reader would otherwise
have to remove them itself, and one that forgot would read a comment as
code.
"""
from dataclasses import dataclass, field, replace
from functools import lru_cache
from pathlib import Path

from nxwright import NxwrightError
from nxwright.language.code_lines import declared_int_names, split_line
from nxwright.project.container import HmiContainer
from nxwright.project.device_settings import DeviceSettings, TextCodec, read_device_settings
from nxwright.project.page_block import Attribute, Event, PageObject, parse_page
from nxwright.project.resources import parse_manifest
from nxwright.source.macros_source import macros_from_block

_MANIFEST_BLOCK = "main.HMI"
_PROGRAM_BLOCK = "Program.s"
_MACROS_BLOCK = "comcode.sn"
_PAGE_KIND = "pa"
# The project's kinds of resources, by their blocks' extension, as the
# manifest lists them (project/resources.py).
RESOURCE_KINDS = {"i": "picture", "zi": "font", "gmov": "animation", "v": "video",
                  "wav": "sound"}


# What a component's description is before it is worked out, as None is
# the description of a component whose type has no module.
NOT_DESCRIBED = object()


@dataclass(eq=False)
class Component(PageObject):
    """An object of a project's page: its records as stored (PageObject's
    `items`), each attribute found by its name, and what describes it,
    once component_types.object_module has worked it out. As PageObject's,
    `attribute` gives the value of the first record of a name. Two
    components of the same records are equal, as PageObject's equality
    goes, but a component never equals a plain PageObject."""
    # Not given when a component is made, so that one made from another
    # with replace is described again.
    description: object = field(default=NOT_DESCRIBED, init=False, repr=False, compare=False)

    def __post_init__(self):
        attributes = {}
        for item in self.items:
            if isinstance(item, Attribute):
                attributes.setdefault(item.name, item.value)
        self._attributes = attributes

    def attribute(self, name: str):
        """Returns the value bytes of the first attribute called `name`, or
        None."""
        return self._attributes.get(name)


def plain_lines(lines: list) -> list:
    """Returns the lines of code `lines`, each without its indentation and
    without a comment after its code, as the Nextion Editor writes it, but
    those holding nothing, or spaces and tabs alone. A comment alone stays a
    line, which gives no block."""
    kept = []
    for number, line in enumerate(lines, 1):
        _, code_part, comment = split_line(line, number)
        plain = code_part or comment.strip(" \t")
        if plain:
            kept.append(plain)
    return kept


def program_variables(project: "Project") -> list:
    """Returns the names of program.s's int variables, in the order declared:
    sys0, sys1, and sys2 first, in a new project. The check and the
    statement encoder both read them here."""
    return list(_declared(project.program, project.settings.encoding))


@lru_cache(maxsize=64)
def _declared(program: bytes, encoding: str) -> tuple:
    """Returns the names program.s `program` declares as int variables, in
    order. Kept, as a compile asks for them once a line. It takes the
    project's program and encoding, not the project, so as to be kept. Each
    line is read without a comment after its code (plain_lines), which a
    Project's program.s is kept without, and its names as nxwright's build
    reads them (code_lines.declared_int_names)."""
    names = []
    text = TextCodec(encoding).decode_keeping_bytes(program).replace("\r\n", "\n")
    for line in plain_lines(text.split("\n")):
        names.extend(declared_int_names(line))
    return tuple(names)


@dataclass
class Project:
    """A project file. `pages` are its pages (nxwright's PageBlock), in page
    ID order; `program` is its program.s; `resources` lists its resources
    as (kind, block name), in the manifest's order, kind being one of
    RESOURCE_KINDS' values; `blocks` holds every block, by name, as stored.
    The code of `program` and of the pages' events is kept clean (the
    module's docstring): `program`'s lines joined by "\\n", and each event's
    a list of lines, empty for an event of blank lines alone."""
    where: str
    settings: DeviceSettings
    pages: list
    program: bytes
    resources: list
    blocks: dict

    def __post_init__(self):
        # New pages, not the ones given, which a caller may still read. An
        # object that is a Component already, as one of a project made from
        # another with replace, keeps its clean events and its description.
        self.program = self._clean_code(self.program)
        self.pages = [replace(page, objects=[
            page_object if isinstance(page_object, Component) else
            Component([replace(item, lines=self._clean_event(item.lines))
                       if isinstance(item, Event) else item
                       for item in page_object.items])
            for page_object in page.objects]) for page in self.pages]

    def _clean_event(self, lines: list) -> list:
        """Returns the lines of an event's code `lines`, clean (_clean_code),
        or none for code of no line but blank ones."""
        code = self._clean_code(b"\n".join(lines))
        return code.split(b"\n") if code else []

    def _clean_code(self, code: bytes) -> bytes:
        """Returns the code `code`, in the project's encoding, with its lines
        as plain_lines gives them, joined by "\\n". A byte the encoding has
        no character for stays as it is."""
        # Lines end with "\r\n" or "\n" alone, as matching.code_lines splits
        # them: str.splitlines would also split at characters a text may hold.
        text = self.codec.decode_keeping_bytes(code).replace("\r\n", "\n")
        return self.codec.encode_keeping_bytes("\n".join(plain_lines(text.split("\n"))),
                                               self.where)

    @classmethod
    def from_bytes(cls, data: bytes, where: str) -> "Project":
        """Returns the project file `data` holds. `where` names it in messages.
        Raises NxwrightError when it is no project file nxwright reads, or
        its screen model is not one nxwright knows."""
        container = HmiContainer(data)
        manifest_block = container.blocks.get(_MANIFEST_BLOCK)
        if manifest_block is None:
            raise NxwrightError("%s: no %s block, so no project file" % (where, _MANIFEST_BLOCK))
        settings = read_device_settings(manifest_block)
        if settings is None:
            raise NxwrightError("%s: its screen model is not one nxwright knows" % where)
        manifest = parse_manifest(manifest_block)
        pages = [parse_page(container.blocks[name]) for name in manifest.block_names(_PAGE_KIND)]
        resources = [(RESOURCE_KINDS.get(kind, "kind %s" % kind), name)
                     for kind, name in manifest.resources if kind != _PAGE_KIND]
        return cls(where, settings, pages, container.blocks.get(_PROGRAM_BLOCK, b""), resources,
                   dict(container.blocks))

    @classmethod
    def from_file(cls, path: Path) -> "Project":
        return cls.from_bytes(Path(path).read_bytes(), str(path))

    def resource_count(self, kind: str) -> int:
        """Returns how many resources of `kind`, one of RESOURCE_KINDS'
        values, such as "picture" or "font", the project has."""
        return sum(1 for resource_kind, _ in self.resources if resource_kind == kind)

    @property
    def codec(self) -> TextCodec:
        """The codec of the project's texts and code."""
        return TextCodec(self.settings.encoding)

    @property
    def macros(self) -> list:
        """The project's macros, [(name, [line])], in the order of its macro
        tab, from its comcode.sn block, which keeps their lines in UTF-8, or
        [] without one. Their lines are clean, as plain_lines gives them.
        Raises NxwrightError for a block nxwright does not read."""
        block = self.blocks.get(_MACROS_BLOCK)
        return [] if block is None else [(name, plain_lines(lines))
                                         for name, lines in macros_from_block(block)[0]]
