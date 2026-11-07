"""What the component types' probes share: changes that put components on a
page, and the probe's three ways of reading a project or a file.

A type's probes compare the whole file, part by part, compiled as the
compile command compiles it (packaging_probes.file_parts). Their fixtures are
the user code alone, part by part (frame_probes.pieces), made through
frame_probes.stand_in_code, so that a type's tests need neither the
statement encoder nor anything the Nextion Editor wrote.
"""
from dataclasses import dataclass
from pathlib import Path

from nxwright.tft import frame
from nxwright.tft.commands.compile import compile_project
from tools.tft.probing.frame_probes import parts_and_pieces, stand_in_code
from tools.tft.probing.packaging_probes import file_parts, probe_firmware
from tools.tft.probing.probe_runner import Parts, Probe, ProbeMismatch
from nxwright.tft.project import Project
from nxwright.tft.tft_file import TftFileError, read_tft


@dataclass(frozen=True, eq=False)
class ComponentsChange:
    """A probe's change that adds `components`, each in a page file's form, to
    `page`, a new page unless it is page0, and gives that page the event code
    `code`. `attributes` are lines of the page's own table, as
    page_attribute_lines gives them, which come before its components. A
    unit test reads what it adds, to make the same page in memory
    (tests/tft/unit_inputs.py). Two changes are equal only if they are the same
    one, as two functions are."""
    components: tuple
    page: str
    code: str
    attributes: str = ""

    def __call__(self, folder: Path):
        if self.page != "page0":
            from nxwright.source.source_folder import add_page
            add_page(folder, self.page)
        page_file = folder / "pages" / (self.page + ".page.toml")
        page_file.write_text(page_file.read_text(encoding="utf-8") + "".join(self.components),
                             encoding="utf-8")
        if self.code:
            (folder / "pages" / (self.page + ".nx")).write_text(self.code, encoding="utf-8")
        if self.attributes:
            with_page_attribute_lines(folder, self.page, self.attributes)


def page_attribute_lines(**attributes) -> str:
    """Returns the lines of a page file's table of the page that give it
    `attributes`: a number as it is, and a text, such as a picture's name,
    between double quotes."""
    return "".join(("%s = \"%s\"\n" if isinstance(value, str) else "%s = %d\n")
                   % (name, value) for name, value in attributes.items())


def with_page_attribute_lines(folder: Path, page: str, lines: str):
    """Writes `lines`, as page_attribute_lines gives them, into the page file
    of `page` in the source folder `folder`: at the end of its table of the
    page, before its components."""
    path = folder / "pages" / (page + ".page.toml")
    text = path.read_text(encoding="utf-8")
    at = text.index("\n[[component]]") + 1 if "\n[[component]]" in text else len(text)
    path.write_text(text[:at] + lines + text[at:], encoding="utf-8")


@dataclass(frozen=True, eq=False)
class PagesChange:
    """A probe's change of several changes, each to a page of its own, made
    in order, so that a unit test reads each page's components
    (tests/tft/unit_inputs.py). Each is a ComponentsChange, or a change like it,
    such as statement_probes.ProgramChange. A unit test reads the lines of
    program.nx they add, the pictures they add, and whether they make the
    code strict Nextion syntax, from this change, as it reads them from one
    of them alone. Two changes are equal only if they are the same one, as
    two functions are."""
    changes: tuple

    def __call__(self, folder: Path):
        for change in self.changes:
            change(folder)

    @property
    def program(self) -> tuple:
        return sum((tuple(getattr(change, "program", ())) for change in self.changes), ())

    @property
    def declarations(self) -> tuple:
        return sum((tuple(getattr(change, "declarations", ())) for change in self.changes), ())

    @property
    def strict(self) -> bool:
        return any(getattr(change, "strict", False) for change in self.changes)

    @property
    def picture_names(self) -> tuple:
        """The names of the pictures its changes add, in the order of their
        IDs, as they add them in turn (picture_probes.PicturesChange)."""
        return sum((tuple(getattr(change, "picture_names", ())) for change in self.changes), ())


def on_pages(*changes) -> PagesChange:
    """Returns a change that makes each of `changes`, each a ComponentsChange
    or a change like it, in order (PagesChange)."""
    return PagesChange(changes)


def with_components(*components: str, page: str = "page0", code: str = "",
                    attributes: str = "") -> ComponentsChange:
    """Returns a change that adds `components`, each in a page file's form, to
    `page`, a new page unless it is page0, and gives that page the event code
    `code` and the lines of its own table `attributes` (ComponentsChange)."""
    return ComponentsChange(components, page, code, attributes)


def add_second_font(folder: Path) -> str:
    """Adds a second font, Noto Sans at 16 pixels, to the source folder
    `folder`, and returns its name."""
    from nxwright.project.truetype import NOTO_SANS
    from nxwright.source.resource_adding import add_font
    name, _ = add_font(folder, NOTO_SANS, 16)
    return name


def with_second_font(*components: str):
    """Returns a change that adds `components` to page0, then a second font
    (add_second_font)."""
    def change(folder: Path):
        with_components(*components)(folder)
        add_second_font(folder)
    return change


def with_the_first_in_a_second_font(*components: str):
    """Returns a change that adds `components` to page0, each in the base
    folder's font, then a second font (add_second_font), which the first of
    them takes."""
    def change(folder: Path):
        with_components(*components)(folder)
        name = add_second_font(folder)
        page = folder / "pages" / "page0.page.toml"
        page.write_text(page.read_text(encoding="utf-8").replace(
            'font = "NotoSans24"', 'font = "%s"' % name, 1), encoding="utf-8")
    return change


def whole_file(project: Path) -> dict:
    """Returns nxwright's file of `project`, part by part: a probe's ours."""
    loaded = Project.from_file(project)
    return file_parts(compile_project(loaded, probe_firmware(loaded.settings.model.series),
                                      any_release=True), "nxwright's file")


def editor_file(data: bytes) -> dict:
    """Returns the Nextion Editor's file `data`, part by part: a probe's
    theirs. Raises ProbeMismatch for a file whose checks do not hold."""
    try:
        read_tft(data, "the Nextion Editor's file")
    except TftFileError as error:
        raise ProbeMismatch(str(error)) from None
    return file_parts(data, "the Nextion Editor's file")


def user_code_kept(project: Path) -> Parts:
    """Returns the user code of `project`, part by part, through the stand-in
    encoder, with where each of its pieces lies: a probe's kept."""
    return parts_and_pieces(*frame.laid_out(Project.from_file(project), stand_in_code))


def type_probe(type_name: str, name: str, change, fixtures: bool = False) -> Probe:
    """Returns the probe of the component type `type_name` on T, named after
    the type and `name`, such as text-two, which makes `change` to the base
    folder. It compares whole files and, when `fixtures`, keeps the user
    code in the fixture folder named after the type."""
    return Probe(type_name + "-" + name, "T", change, whole_file, editor_file,
                 type_name if fixtures else None, user_code_kept)
