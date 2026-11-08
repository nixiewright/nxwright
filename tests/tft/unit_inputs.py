"""The inputs the unit tests give nxwright's functions, made in memory, and the
expected bytes they compare with, read from the fixtures.

A unit test calls one function of nxwright on that function's own input, and
compares what it returns with a part of a probe's fixture. These helpers
make that input, and read that part:

- page() makes a page, a PageBlock, as nxwright's build gives it: from a page
  file's components and its event code, on the base folder of a probe's
  series (probes/). nxwright's page reader makes it, with the base folder's
  component defaults, so that a page of a probe's components is that
  probe's page. page_of() makes it from what a probe's change adds, which
  probe_change() gives.
- project_of() makes a Project of only the facts a function reads, such as
  the series, a page's components, or the number of pictures. Many of
  nxwright's functions take a Project only to read those. It is never a whole
  project: it has no block of the project file but its macros', as
  nxwright builds them, when it has macros. probe_project() makes one
  of a probe's pages, as the match check reads it, and probe_facts() as a
  type's own functions read it. probe_objects() gives the components of a
  type on such a Project's pages, with their places.
  with_font_blocks() gives such a Project its base folder's font blocks,
  for a function that reads them, as packaging does. font_in_other_bytes()
  makes a font in two codings of the same characters.
- laid_out_pieces() gives the pieces of the user code the frame writes for
  such a Project, by their names.
- piece() reads one piece of a probe's fixtures, by its name, and
  piece_names() lists their names. place() reads where a component of the
  probe lies, its ObjectPlace, which a test gives its type's functions, and
  probe_objects() gives each component of a type in a probe, with its place.
  record_places() reads the places a component's record gives, from where
  the probe's table puts its pieces among the user code's blocks
  (blocks_place). user_code_place() reads where a piece starts in the
  user code, whatever its part.
- user_code_of() joins a probe's parts into its whole user code, as a
  decoder of the decompiler reads it, and whole_file_of() makes a whole TFT
  file of a compile's probe from its headers, table, and user code, with
  zeros for the rest of its section.
- decoded_file_of() makes, from such a Project, the decoded file that a
  decoder of code reads (tft/decompiling/), as small as that decoder
  needs, and the function that names its entries' attributes.
  rebuilt_user_code() compiles such a Project again with its components
  rebuilt from what a decoder reads back of them, so that a test sees
  whether the decoder keeps everything the file keeps.

No helper builds a project, or reads a project file.
"""
from dataclasses import replace
from functools import lru_cache
import json
import struct
from typing import Optional

from nxwright.language.resource_names import ResourceNames
from nxwright.project.editor_limits import check_component_places
from nxwright.source.series_components import check_series_components
from nxwright.source.device_keys import settings_from_keys
from nxwright.source.keyboards import KEYBOARD_PAGES, keyboard as made_keyboard
from nxwright.project.page_block import Attribute, Event
from nxwright.project.zi_font import Glyph, encode_font
from nxwright.source.macros_source import MACROS_PATH
from nxwright.source.page_source import PageSource, page_from_source, page_toml_path
from nxwright.source.source_folder import (_NEW_PAGE, absent_attributes_in_page_data, app_text,
                                           folder_reader, parse_app, parsed_page_toml,
                                           read_folder_source, types_in_page_data)
from nxwright.tft import component_types, frame, label_numbers
from nxwright.tft.component_types import ObjectPlace
from nxwright.tft.decompiling import page_files
from nxwright.tft.decompiling.decoded_file import (CodeRun, DecodedFile, DecodedObject, DecodedPage,
                                            IntVariable, Name, decoded_user_code)
from tools.tft.probing.encoding_probes import EncodingChange
from tools.tft.probing.key_probes import KeyboardChange
from tools.tft.probing.model_probes import ScreenChange
from tools.tft.probing.page_place_probes import placed_page_text
from tools.tft.probing.frame_probes import _KEPT_BLOCK_PARTS, stand_in_code
from tools.tft.probing.probe_runner import BASES, FIXTURES
from tools.tft.probing.statement_probes import program_text, strict_app
from nxwright.tft.statements import page_code_entry
from nxwright.tft.project import Project, program_variables
from nxwright.tft.tft_file import (PAGE_INDEX_ENTRY_SIZE, UserCode, encode_blocks, layout_of,
                            split_blocks)

# The base folders' one page, which the probes put their components on.
_PAGE = "page0"


@lru_cache(maxsize=None)
def _base(series: str, strict: bool, program: tuple = (), declarations: tuple = (),
          macros: str = None, ints: tuple = (), encoding: str = None, screen: str = None,
          rotation: int = None, page_values: tuple = (), keyboard: str = None):
    """Returns the base folder of `series` as nxwright reads it (a
    FolderSource), read once: its settings, component defaults, and
    program.nx. With `strict`, its code is strict Nextion syntax, as a
    probe of code makes it (statement_probes.program_lines). program.nx
    holds the lines `program` and `declarations`, as program_lines adds
    them, and the int variables `ints` (statement_probes.program_text).
    `macros` is the text of the folder's macros.nx, as
    macro_probes.MacrosChange writes it; the base folders have none.
    `encoding`, when given, is its encoding, as nxwright's device command
    writes it in app.toml (encoding_probes.EncodingChange). `screen` and
    `rotation`, each when given, are its screen model's name and its
    rotation, as that command writes them, which also gives each page the
    new screen's size (model_probes.ScreenChange). The command also converts
    the fonts, which these facts only count. `page_values` gives page0's
    own attributes of its place and size (page_place_probes.PlacedChange).
    `keyboard`, when given, is the kind of nxwright's keyboard page the
    folder has (key_probes.KeyboardChange), whose font app.toml lists, as
    nxwright's keyboard command lists it; the probe's pages give the page
    itself (_probe_pages)."""
    read = folder_reader(BASES / series)
    if not (strict or program or declarations or macros is not None or ints or encoding
            or screen or rotation is not None or page_values or keyboard):
        return read_folder_source(read)
    moved = {key: value for key, value in (("screen", screen), ("rotation", rotation))
             if value is not None}

    def read_changed(path: str) -> str:
        if path == MACROS_PATH and macros is not None:
            return macros
        text = read(path)
        if path == "app.toml":
            if strict:
                text = strict_app(text)
            if encoding:
                text = app_text(dict(parse_app(text), encoding=encoding), written=None)
            if moved:
                text = app_text(dict(parse_app(text), **moved), written=None)
            if keyboard:
                app = parse_app(text)
                font = _keyboard(app, keyboard).font_name
                if font not in app["fonts"]:
                    text = app_text(dict(app, fonts=app["fonts"] + [font]), written=None)
            return text
        if path == "program.nx":
            return program_text(text, program, declarations, ints)
        if path == page_toml_path(_PAGE):
            values = tuple(page_values)
            if moved:
                width, height = settings_from_keys(parse_app(read_changed("app.toml"))).page_size
                values = (("w", width), ("h", height)) + values
            return placed_page_text(text, values)
        return text
    return read_folder_source(read_changed)


@lru_cache(maxsize=None)
def _program(series: str, strict: bool, program: tuple = (), declarations: tuple = (),
             macros: str = None, ints: tuple = (), encoding: str = None, screen: str = None,
             rotation: int = None, page_values: tuple = (), keyboard: str = None) -> bytes:
    """Returns program.s, as nxwright builds it from the base folder's
    program.nx, as _base reads it. A call in it must name one of the
    macros."""
    return _base(series, strict, program, declarations, macros, ints, encoding, screen,
                 rotation, page_values, keyboard).build_program()


def page(*components: str, series: str = "T", code: str = "", strict: bool = False,
         pictures: tuple = (), name: str = _PAGE, attributes: str = "",
         program: tuple = (), declarations: tuple = (), macros: str = None,
         ints: tuple = (), encoding: str = None, screen: str = None, rotation: int = None,
         page_values: tuple = (), keyboard: str = None, after: int = 0,
         others: dict = None, text: str = None):
    """Returns the page `name` of the base folder of `series`, with
    `components` added, each in a page file's form (as
    progress_bar_probes.progress_bar_component gives it), and the event code
    `code`, as nxwright's build gives it: a PageBlock. A page other than
    page0 is a new page, listed after the base folder's and the `after`
    pages added before it, as component_probes.with_components adds it.
    `attributes` are lines of the page's own table, such as "sta = 1\\n", as
    component_probes.page_attribute_lines gives them. With `strict`, the
    code is strict Nextion syntax. `pictures` gives the names of the
    project's pictures, in ID order, by which a component may give its
    pictures. `program`, `declarations`, and `ints` are program.nx's lines
    and int variables (_base), whose variables the page's code may use,
    and `macros` the text of macros.nx, whose macros its code may call.
    `encoding`, when given, is the project's encoding, in which the page
    reads its texts, and `screen`, `rotation`, and `page_values` the device
    settings and page0's place and size, and `keyboard` the kind of
    nxwright's keyboard page among the pages (_base). `text`, when given, is
    the page's whole file, as a keyboard page's, in place of the base
    folder's or a new page's. `others` gives the project's other pages, by
    name, each as (its components, its attributes, the pages added before
    it, its whole file or None), so that the page's code may name their
    components.
    Raises NxwrightError when nxwright's build would refuse the page."""
    base = _base_of(series, strict=strict, program=program, declarations=declarations,
                    macros=macros, ints=ints, encoding=encoding, screen=screen,
                    rotation=rotation, page_values=page_values, keyboard=keyboard)
    toml, page_id = _page_file(base, name, components, attributes, after, text)
    data = parsed_page_toml(toml, name, None)
    files = {name: data}
    for other, made_from in (others or {}).items():
        files[other] = parsed_page_toml(_page_file(base, other, *made_from)[0], other, None)
    names = ResourceNames.of_app({**base.app, "pictures": list(pictures)})
    made = page_from_source(
        PageSource(toml, code), name, names, base.defaults, base.declared, page_id, [],
        base.read, {each: types_in_page_data(read) for each, read in files.items()},
        base.encoding, None, base.program_variables, base.macros,
        {each: absent_attributes_in_page_data(read, base.defaults, base.screen)
         for each, read in files.items()}, base.screen)
    # What nxwright's build checks after reading a page (FolderSource.build_page):
    # its components' places, and what the screen's series refuses.
    where = "%s.page.toml" % name
    check_component_places(made, base.screen, settings_from_keys(base.app).page_size, where)
    check_series_components(made, base.screen, where)
    return made


def _base_of(series: str, strict: bool = False, program: tuple = (), declarations: tuple = (),
             macros: str = None, ints: tuple = (), encoding: str = None, screen: str = None,
             rotation: int = None, page_values: tuple = (), keyboard: str = None, **_):
    """Returns the base folder of `series`, as _base reads it, for the
    options of the base folder among page()'s `options`; page()'s others are
    let through."""
    return _base(series, strict, tuple(program), tuple(declarations), macros, tuple(ints),
                 encoding, screen, rotation, tuple(page_values), keyboard)


def _page_file(base, name: str, components, attributes: str, after: int,
               text: str = None) -> tuple:
    """Returns (the text of the page file of the page `name` of `base`, a
    base folder as _base reads it, with `components` and `attributes`
    added, its ID): page0's own file, or, for another, `text` when given or
    else a new page's, after the base folder's and the `after` pages added
    before it."""
    if text is not None:
        toml, page_id = text, len(base.app["pages"]) + after
    elif name == _PAGE:
        toml, page_id = base.read(page_toml_path(_PAGE)), 0
    else:
        # The page file nxwright's add_page writes. add_page gives it only
        # written into a folder, so the helper takes its template.
        width, height = settings_from_keys(base.app).page_size
        toml, page_id = _NEW_PAGE % (name, width, height), len(base.app["pages"]) + after
    # A page file of the base folder holds the page's own table alone, so
    # its attributes follow it, before the components.
    return toml + attributes + "".join(components), page_id


def page_of(probe, **options):
    """Returns the page `probe` adds its components to, as page() makes it.
    The probe's change must keep the components, the page, the code, and
    the page's own attributes it adds, as component_probes.ComponentsChange
    does; with the pictures it adds, as picture_probes.PicturesChange does,
    the page takes their names; with the lines of program.nx it adds, as
    statement_probes.ProgramChange does, their variables; and with the
    macros it adds, as macro_probes.MacrosChange does, their names. A change
    in another encoding (encoding_probes.EncodingChange) gives its
    encoding. `options` are page()'s others, such as `pictures`; the series
    is the probe's, and the code strict for a change that makes it so (its
    `strict`), unless given."""
    change = probe_change(probe)
    options.setdefault("series", probe.base)
    options.setdefault("strict", getattr(change, "strict", False))
    options.setdefault("pictures", getattr(change, "picture_names", ()))
    for name, value in _folder_options(probe).items():
        options.setdefault(name, value)
    return page(*change.components, code=change.code, name=change.page,
                attributes=getattr(change, "attributes", ""), **options)


# The changes of a probe that make another change, then change the device's
# settings or add nxwright's keyboard page, which a unit test gives the base
# folder (_base).
_WRAPPING_CHANGES = (EncodingChange, ScreenChange, KeyboardChange)


def probe_change(probe):
    """Returns the change that adds `probe`'s pages: the probe's change, or,
    for a change that wraps another (_WRAPPING_CHANGES), the change it makes
    first."""
    change = probe.change
    while isinstance(change, _WRAPPING_CHANGES):
        change = change.change
    return change


def _wrapping_changes(probe) -> list:
    """Returns the changes that wrap another of `probe`'s change, outermost
    first (_WRAPPING_CHANGES)."""
    found, change = [], probe.change
    while isinstance(change, _WRAPPING_CHANGES):
        found.append(change)
        change = change.change
    return found


def _keyboard(app: dict, kind: str):
    """Returns nxwright's keyboard page of `kind` for the screen app.toml's
    `app` gives (nxwright.source.keyboards.keyboard): its page file, its
    code, and its font's name, as nxwright's keyboard command makes it."""
    return made_keyboard(kind, *settings_from_keys(app).page_size)


def probe_project(probe, strict: Optional[bool] = None, series: str = None) -> Project:
    """Returns a Project of facts of `probe`'s pages, as the match check
    reads it (matching.project_needs): page0, then each other page the
    probe adds (_probe_pages), and the lines of program.nx and the macros it
    adds. It holds no resource, as the check reads each resource's block,
    which such a Project has not. With `strict`, the code is strict Nextion
    syntax, as a probe of code makes it; unless given, as the probe's change
    makes it.
    Its pages are on `series`, unless given the probe's own, so that a
    probe's change is laid on another series."""
    if strict is None:
        strict = getattr(probe_change(probe), "strict", False)
    series = series or probe.base
    return project_of(*_probe_pages(probe, series, strict=strict), series=series,
                      strict=strict, fonts=0, **_folder_options(probe))


def _folder_options(probe) -> dict:
    """Returns what `probe`'s change gives the base folder, as page()'s and
    project_of()'s options: the lines and the int variables of program.nx
    it adds, none but for a statement_probes.ProgramChange or a
    shared_attribute_probes.IntsChange; the text of the macros.nx it
    writes, none but for a macro_probes.MacrosChange; its encoding, none
    but for an encoding_probes.EncodingChange; its screen model and
    rotation, none but for a model_probes.ScreenChange; page0's place and
    size, none but for a page_place_probes.PlacedChange; and the kind of
    nxwright's keyboard page it adds, none but for a
    key_probes.KeyboardChange."""
    change = probe_change(probe)
    return {"program": getattr(change, "program", ()),
            "declarations": getattr(change, "declarations", ()),
            "macros": getattr(change, "macros_text", None),
            "ints": getattr(change, "ints", ()),
            "encoding": next((each.encoding for each in _wrapping_changes(probe)
                              if isinstance(each, EncodingChange)), None),
            "screen": next((each.screen for each in _wrapping_changes(probe)
                            if isinstance(each, ScreenChange)), None),
            "rotation": next((each.rotation for each in _wrapping_changes(probe)
                              if isinstance(each, ScreenChange)), None),
            "page_values": getattr(change, "page_values", ()),
            "keyboard": next((each.keyboard for each in _wrapping_changes(probe)
                              if isinstance(each, KeyboardChange)), None)}


def probe_facts(probe, series: str = None) -> Project:
    """Returns a Project of facts of `probe`'s pages, as a type's own
    functions read it, such as its memory, its entries, or its drawing:
    page0, then each other page the probe adds (_probe_pages); the pictures
    the probe adds, the lines of program.nx and the macros it adds, its
    encoding, and the base folder's fonts. A change of strict Nextion
    syntax, as a probe of code makes, gives its pages and program.s in it.
    Its pages are on `series`, unless given the probe's own, so that a
    probe's change is laid on another series."""
    change = probe_change(probe)
    pictures = getattr(change, "picture_names", ())
    strict = getattr(change, "strict", False)
    series = series or probe.base
    return project_of(*_probe_pages(probe, series, strict=strict), series=series,
                      strict=strict, pictures=len(pictures), **_folder_options(probe))


def _probe_pages(probe, series: str, **options) -> list:
    """Returns the pages of `probe`, as page() makes them on the base folder
    of `series`: page0, as the probe changes it or as that folder holds it,
    then each other page the probe adds, in order. The probe's change is a
    ComponentsChange, or a PagesChange of several (component_probes.py); its
    pictures' names, its lines of program.nx, and its encoding are given to
    each page. `options` are page()'s others, such as `strict`."""
    adds = probe_change(probe)
    pictures = getattr(adds, "picture_names", ())
    options = {**_folder_options(probe), **options}
    # Each page's components, attributes, the pages added before it, and its
    # whole file, if given; and its code. Each page other than page0 follows
    # those added before it, and a keyboard page those the probe adds.
    files, codes, added = {}, {}, 0
    # A probe without a change, as a blank project's, adds no page.
    for change in () if adds is None else getattr(adds, "changes", (adds,)):
        files[change.page] = (tuple(change.components), getattr(change, "attributes", ""),
                              0 if change.page == _PAGE else added, None)
        codes[change.page] = change.code
        added += change.page != _PAGE
    if options.get("keyboard"):
        keyboard = _keyboard(_base_of(series, **options).app, options["keyboard"])
        files[KEYBOARD_PAGES[options["keyboard"]]] = ((), "", added, keyboard.page_toml)
        codes[KEYBOARD_PAGES[options["keyboard"]]] = keyboard.code
    made = {}
    for name, (components, attributes, after, text) in files.items():
        made[name] = page(*components, series=series, code=codes[name], name=name,
                          pictures=pictures, attributes=attributes, after=after, text=text,
                          others={other: made_from for other, made_from in files.items()
                                  if other != name}, **options)
    first = made.pop(_PAGE, None) or page(series=series, pictures=pictures, **options)
    return [first] + list(made.values())


def probe_objects(probe, type_name: Optional[str], project: Project) -> list:
    """Returns (the page object, its place) of each component of the type
    `type_name`, such as "slider", or of every type for None, on the pages
    of `project`, a Project of facts of `probe`'s pages (probe_facts), its
    place read from the probe's table (place)."""
    return [(page_object, place(probe, "page%d-%d" % (number, object_id)))
            for number, made in enumerate(project.pages)
            for object_id, page_object in enumerate(made.objects)
            if object_id and type_name in (None, component_types.type_name(page_object))]


def project_of(*pages, series: str = "T", strict: bool = False, pictures: int = 0,
               fonts: int = None, program: tuple = (), declarations: tuple = (),
               macros: str = None, ints: tuple = (), encoding: str = None,
               screen: str = None, rotation: int = None, page_values: tuple = (),
               keyboard: str = None) -> Project:
    """Returns a Project of the facts given, never a whole project: the
    device settings and program.s of the base folder of `series`, program.s
    as nxwright builds it, in strict Nextion syntax with `strict`, with the
    lines `program` and `declarations` and the int variables `ints`, in the
    encoding `encoding`, on the screen `screen` at `rotation`, and with
    page0's `page_values`, and with the font of the keyboard page
    `keyboard`, each when given (_base); `pages`, PageBlocks as
    page() gives them, with the same program.nx; the macros of `macros`, the
    text of macros.nx, as nxwright builds them; and as its resources,
    `pictures` pictures and `fonts` fonts, the base folder's unless given.
    It has no block but the macros', so a function that reads a resource's,
    as packaging does, or the match check's reading of a project into needs
    (matching.project_needs), takes it only without resources: no
    pictures, and `fonts` 0. Or, with the base folder's fonts, once
    with_font_blocks has given it their blocks."""
    folder = (tuple(program), tuple(declarations), macros, tuple(ints), encoding, screen,
              rotation, tuple(page_values), keyboard)
    base = _base(series, strict, *folder)
    if fonts is None:
        fonts = len(base.app["fonts"])
    resources = ([("picture", "%d.i" % number) for number in range(pictures)]
                 + [("font", "%d.zi" % number) for number in range(fonts)])
    blocks = {} if macros is None else {"comcode.sn": base.build_macros()}
    return Project("the facts of a unit test", settings_from_keys(base.app), list(pages),
                   _program(series, strict, *folder), resources, blocks)


def with_font_blocks(project: Project, series: str) -> Project:
    """Returns `project`, a Project of facts of the base folder of `series`
    (project_of), with the blocks of its fonts: each the base folder's font
    file, byte for byte, as a whole build holds it. A function that reads a
    font's block, as packaging does, takes such a Project. Raises ValueError
    for a Project of other fonts than the base folder's."""
    fonts = [name for kind, name in project.resources if kind == "font"]
    files = _base(series, False).app["fonts"]
    if len(fonts) != len(files):
        raise ValueError("the Project holds %d fonts, and the base folder of %s %d"
                         % (len(fonts), series, len(files)))
    return replace(project, blocks={**project.blocks, **{
        font: (BASES / series / "fonts" / (file + ".zi")).read_bytes()
        for font, file in zip(fonts, files)}})


def font_in_other_bytes(encoding: str) -> tuple:
    """Returns two blocks of one font at 0 degrees in `encoding`, a one-byte
    encoding, of the same characters: nxwright's, and one whose glyph is
    coded in other bytes, as another generator may code it. The glyph, of
    "!", is a column of full pixels. nxwright marks a glyph without partial
    pixels as of two shades, by a first byte of 1. Marked as of eight, by a
    3, its run of full pixels reads the same."""
    height = 8
    block = encode_font("other bytes", encoding, height, 0, [
        Glyph(ord("!"), 1, 0, 0, (7,) * height)])
    ours = bytes([1, 0x20 | height])
    if block.count(ours) != 1:
        raise ValueError("the font's glyph is not coded as one run of full pixels")
    return block, block.replace(ours, bytes([3, 0x20 | height]))


def laid_out_pieces(project: Project, encode_code=stand_in_code) -> dict:
    """Returns {a piece's name: its bytes} of the user code frame.laid_out
    writes for `project`, a Project of facts (project_of), so that a test
    compares one piece without cutting it from a part itself. `encode_code`
    is the frame's encoder of code: the stand-in, with which the probes
    that keep their whole user code kept it (component_probes.user_code_kept),
    or the statement encoder, for a probe that kept the real one's blocks."""
    code, pieces, _ = frame.laid_out(project, encode_code)
    data, places = code.to_bytes(), code.places()
    return {each.name: data[places[each.part][0] + each.start:places[each.part][0] + each.end]
            for each in pieces}


def piece(probe, name: str) -> bytes:
    """Returns the piece `name` of `probe`'s fixtures, such as
    "page0-1-memory" for page 0's object 1's memory: the bytes of its part
    that the probe's pieces.json gives (probe_runner.Parts). Raises KeyError
    for a piece it does not give."""
    folder = FIXTURES / probe.fixtures / probe.name
    part, start, end = _table(folder)["pieces"][name]
    with open(folder / (part + ".bin"), "rb") as kept:
        kept.seek(start)
        return kept.read(end - start)


def user_code_of(probe, version: tuple = None) -> UserCode:
    """Returns the whole user code of `probe`, joined from the parts its
    fixtures keep, as the frame's probes cut them (frame_probes.pieces): the
    first block's, program.s's, the macros', and the pages' blocks, then the
    parts after them. Its page index's entries are of the size of the
    layout of the Nextion Editor `version` (tft_file.Layout), when given,
    as a probe of an older Nextion Editor keeps that Editor's. Raises
    KeyError for a probe that keeps no such parts."""
    folder = FIXTURES / probe.fixtures / probe.name

    def part(name: str, optional: bool = False) -> bytes:
        path = folder / (name + ".bin")
        if optional and not path.exists():
            return b""
        if not path.exists():
            raise KeyError("%s keeps no %s part" % (probe.name, name))
        return path.read_bytes()
    blocks = split_blocks(part("first-block") + part("program-s") + part("macros", True)
                          + part("pages"))
    entry = PAGE_INDEX_ENTRY_SIZE if version is None else layout_of(version).page_index_entry
    return UserCode(blocks, part("after-blocks"), part("variables"), part("data"),
                    part("page-index"), part("records"), part("macros-table", True), entry)


def whole_file_of(probe) -> bytes:
    """Returns a whole TFT file of `probe`, from the parts its fixtures keep
    as a compile's probes cut them: its headers, its section's table, and
    its user code. The rest of the section, the firmware and the resources,
    is zeros, so the file's checksums do not hold."""
    folder = FIXTURES / probe.fixtures / probe.name
    header_1, header_2, table, code, checksum = (
        (folder / (name + ".bin")).read_bytes()
        for name in ("header-1", "header-2", "table", "user-code", "checksum"))
    # Header 1 gives where the section starts, at its 0x34, and its size, at
    # its 0x40 (tft_file.read_tft).
    section_place, section_size = (struct.unpack_from("<I", header_1, place)[0]
                                   for place in (0x34, 0x40))
    before = header_1 + header_2
    return (before + bytes(section_place - len(before)) + table
            + bytes(section_size - len(table)) + code + checksum)


def piece_names(probe) -> list:
    """Returns the names of the pieces of `probe`'s fixtures, sorted."""
    return sorted(_table(FIXTURES / probe.fixtures / probe.name)["pieces"])


def place(probe, name: str) -> ObjectPlace:
    """Returns where the component `name`, such as "page0-1" for page 0's
    object 1, lies in `probe`'s user code, as the probe's pieces.json gives
    it (probe_runner.Parts): the place to give its type's functions. A
    timer's or a scrolling text's numbers of the counter, which the file
    leaves out, are the frame's for the probe's pages. Raises KeyError for
    a component it does not give."""
    found = ObjectPlace(**_table(FIXTURES / probe.fixtures / probe.name)["places"][name])
    return replace(found, timer_numbers=_timer_numbers(probe).get((found.page, found.object_id)))


@lru_cache(maxsize=None)
def _timer_numbers(probe) -> dict:
    """Returns each timer's and scrolling text's two numbers of the counter
    in `probe`'s pages, by (page ID, object ID) (label_numbers.numbers)."""
    return label_numbers.numbers(probe_facts(probe)).timers


def piece_start(probe, name: str) -> int:
    """Returns where the piece `name` of `probe`'s fixtures starts in its part,
    such as an object's entries' in the data, which gives its first entry's
    number, 24 bytes an entry."""
    return _table(FIXTURES / probe.fixtures / probe.name)["pieces"][name][1]


# The parts of the user code's blocks, in the order the user code holds them:
# those frame_probes.parts_and_pieces names, then the pages'. A project
# without macros has no macros part.
_BLOCK_PARTS = tuple(_KEPT_BLOCK_PARTS.values()) + ("pages",)
# The parts of the user code, in the order it holds them: its blocks', then
# the parts after them, as frame_probes.pieces names them
# (tft_file.UserCode.to_bytes). A project without macros has neither macros
# part.
_PARTS = _BLOCK_PARTS + ("after-blocks", "variables", "data", "macros-table", "page-index",
                         "records")


def blocks_place(probe, name: str) -> int:
    """Returns where the piece `name` of `probe`'s fixtures starts among the
    user code's blocks: the place a goto's operand counts from
    (label_numbers.resolved). The blocks come first in the user code, so
    that is its place in the user code (user_code_place)."""
    return user_code_place(probe, name)


def user_code_place(probe, name: str) -> int:
    """Returns where the piece `name` of `probe`'s fixtures starts in the
    user code, such as the place of a page's entries that the page index
    gives: its start in its part, after the parts before that part, each the
    size its fixture gives."""
    folder = FIXTURES / probe.fixtures / probe.name
    part, start, _ = _table(folder)["pieces"][name]
    before = [folder / (each + ".bin") for each in _PARTS[:_PARTS.index(part)]
              if each not in ("macros", "macros-table") or (folder / (each + ".bin")).exists()]
    return start + sum(path.stat().st_size for path in before)


def record_places(probe, name: str, page_object) -> dict:
    """Returns the places the record of the component `name`, such as
    "page0-1", gives (frame._component_record), as the frame notes them
    while it lays out the component's blocks and events: where its drawing
    starts among the user code's blocks; its first block's place, when its
    drawing has blocks; its background fill's, when its run has blocks; and
    each event's code's, after the event's name, when the event has blocks.
    Each is read from where `probe`'s table puts the component's pieces
    (blocks_place), so nothing is laid out. `page_object` is the component,
    whose type gives its events."""
    end = encode_blocks([b""])
    names = piece_names(probe)
    places = {"drawing": blocks_place(probe, name + "-drawing")}
    if piece(probe, name + "-drawing") != end:
        places[frame._FIRST_BLOCK] = places["drawing"]
    fill = name + "-background-fill"
    if fill in names and piece(probe, fill) != end:
        places[frame._BACKGROUND_FILL] = blocks_place(probe, fill)
    for event in component_types.object_module(page_object).EVENTS:
        event_name = encode_blocks([event.encode("ascii")])
        each = "%s-event-%s" % (name, event)
        if each in names and piece(probe, each) != event_name + end:
            places[event] = blocks_place(probe, each) + len(event_name)
    return places


@lru_cache(maxsize=None)
def _table(folder) -> dict:
    """Returns the pieces.json of the probe whose fixtures are in `folder`,
    read once: its "pieces" and its "places"."""
    return json.loads((folder / "pieces.json").read_text(encoding="utf-8"))


# The names a page's own attributes go by in code (statements.page_code_entry).
_PAGE_CODE_ATTRIBUTES = ("type", "id", "vscope", "x", "y", "w", "h", "endx", "endy", "sta", "bco",
                         "pic", "effect", "first", "time", "up", "down", "left", "right")


def decoded_object_named(name: str, object_id: int = 0) -> DecodedObject:
    """Returns a DecodedObject of the name `name` and the ID `object_id`,
    its other fields empty, for a decoder that reads only names."""
    return DecodedObject(object_id, 0, "", Name(name, 0, True), False, 0, [], b"", 0, [], [], {})


def decoded_file_of(project: Project) -> tuple:
    """Returns (the DecodedFile of `project`'s facts that a decoder of code
    reads, a function attribute_of_entry(decoded_file, number) that names
    its entries' attributes, as decompiling.objects.attribute_of_entry
    does). The file holds the series, the encoding, the int variables in
    the order declared, and each page's objects by name, the rest empty.
    Each entry an attribute of an object has is numbered by the compile's
    own tables (component_types.first_entries and code_entry, and
    statements.page_code_entry)."""
    series = project.settings.model.series
    first = component_types.first_entries(project)
    pages, named = [], {}
    for page_id, page in enumerate(project.pages):
        objects = [decoded_object_named(component_types.object_name(page_object), number)
                   for number, page_object in enumerate(page.objects)]
        pages.append(DecodedPage(page_id, objects, 0, b"", CodeRun(0, [])))
        for object_id, page_object in enumerate(page.objects):
            if object_id == 0:
                attributes = _PAGE_CODE_ATTRIBUTES
                entry = lambda attribute, page_object=page_object: page_code_entry(
                    page_object, attribute, series)
            else:
                module = component_types.object_module(page_object)
                attributes = [item.name for item in page_object.items
                              if isinstance(item, Attribute)]
                entry = (lambda attribute, module=module, page_object=page_object:
                         component_types.code_entry(module, page_object, attribute, series))
            name = objects[object_id].name.text
            for attribute in attributes:
                try:
                    number = first[(page_id, name)] + entry(attribute)
                except KeyError:
                    continue
                named.setdefault(number, (page_id, object_id, attribute))
    ints = [IntVariable(Name(name, 0, True), 0) for name in program_variables(project)]
    decoded = DecodedFile(series, "", 0, project.settings.encoding, ints, b"", CodeRun(0, []),
                          [], pages)

    def attribute_of_entry(decoded_file: DecodedFile, number: int) -> tuple:
        page_id, object_id, attribute = named[number]
        page = decoded_file.pages[page_id]
        return page, page.objects[object_id], attribute

    return decoded, attribute_of_entry


def rebuilt_user_code(project: Project, values_of) -> tuple:
    """Returns (the user code the compile writes for `project`, the user
    code of `project` with objects rebuilt, and how many were rebuilt).
    `values_of(decoded_object, decoded_page, decoded_file)` reads each
    object back from the first user code, decoded: each page, then its
    components. It returns {attribute's name: value}, as ObjectValues'
    attributes, or None to keep the object as it is. An object is rebuilt
    as the source folder's page file builds it (page_files.page_block_object):
    at its type's defaults but those values, with its own events' lines and
    its own name. The name is kept because a name no guess matches gets a
    readable name with another checksum, which the decoded file's tests
    test. So the two user codes are the same when the values keep
    everything the file keeps of each object rebuilt."""
    code = frame.user_code(project)
    decoded = decoded_user_code(code, project.settings.model.series,
                                project.settings.model.name, project.settings.rotation,
                                project.settings.encoding)
    pages, rebuilt = [], 0
    for decoded_page, made in zip(decoded.pages, project.pages):
        objects = []
        for decoded_object, own in zip(decoded_page.objects, made.objects):
            values = values_of(decoded_object, decoded_page, decoded)
            if values is None:
                objects.append(own)
                continue
            lines = {item.name: item.lines for item in own.items if isinstance(item, Event)}
            rebuilt_object = page_files.page_block_object(
                decoded_object, values, lines,
                page_files.component_defaults()[decoded_object.type_number])
            objects.append(replace(rebuilt_object, items=[
                replace(item, value=own.attribute("objname"))
                if isinstance(item, Attribute) and item.name == "objname" else item
                for item in rebuilt_object.items]))
            rebuilt += 1
        pages.append(replace(made, objects=objects))
    return code, frame.user_code(replace(project, pages=pages)), rebuilt
