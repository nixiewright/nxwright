"""The source folder: the screen project laid out for editing, and its
conversion to and from a dump folder.

Layout:
  app.toml                 format, the app's name, the language ("nextion"
                           or "nxlang"), then pages, pictures, fonts,
                           animations, videos, and sounds in ID order; a
                           folder without animations, videos, or sounds may
                           leave their lists out
  defaults.toml            what a newly added component of each type has; page
                           files leave out what equals it (component_defaults.py)
  program.nx               the global program code
  pages/<page>.page.toml   the page and its components (see page_source.py)
  pages/<page>.nx          their event code
  pictures/<name>.png      or .jpg, the picture's file as the project keeps it;
                           a "/" in a name makes a subfolder (resource_names.py)
  fonts/<name>.zi
  animations/<name>.gmov          GmovMaker's file
  animations/<name>.screen.gmov   the form the Editor made of it, which the
                                  screen shows
  videos/<name>.video      VideoBox's file
  sounds/<name>.wav        the WAV file as the Editor converted it
Fonts, animations, videos, and sounds are their blocks of the project file,
byte for byte (resources.py, CopiedKind).

program.nx is program.s with LF line endings, read in the project's
character encoding (app.toml's encoding); the dump stores it with CRLF line
endings. The build turns the code of program.nx and of every page's .nx file
into Editor syntax with code_preprocessor.py, after compiling it with nxlang.py
when the folder uses nxlang.

Adding one of nxwright's keyboard pages to a folder is keyboard_adding.py's.
Adding pictures, fonts, animations, videos, and sounds is
resource_adding.py's, and removing one is resource_removal.py's.
"""
from dataclasses import dataclass
from functools import cache, partial
from itertools import count
from pathlib import Path
import re
import tomllib

import tomli_w

from nxwright import MissingFileError, NxwrightError
from nxwright.language.code_lines import program_int_variables
from nxwright.language.code_preprocessor import preprocess
from nxwright.project.editor_language import EDITOR_PROGRAM_DECLARATION, NAMES_THE_EDITOR_REFUSES
from nxwright.project.editor_limits import NAME_LIMIT, check_component_places, lacked_attributes
from nxwright.project.object_types import TYPES_BY_NAME
from nxwright.project.page_memory import measure_page, project_memory
from nxwright.project.font_drawing import draw_font_block, drawn_codes, lacking_words
from nxwright.project.media_files import video_rotation
from nxwright.project.pictures import picture_problem
from nxwright.project.truetype import NOTO_SANS, noto_sans
from nxwright.project.zi_font import UTF8
from nxwright.source.keyboards import UTF8_CHARACTERS
from nxwright.project.attribute_values import number_from_bytes
from nxwright.project.component_defaults import DEFAULTS_FILE, defaults_from_toml
from nxwright.project.dump_folder import (DUMP_FORMAT_LINE, MACROS_FILE, check_dump_format,
                                          check_ids_without_gaps, copied_contents,
                                          copied_file_name, dump_device_settings, dump_pictures,
                                          page_text_files)
from nxwright.project.resources import COPIED_KINDS, FONTS, MEDIA, PICTURE_SUFFIXES
from nxwright.project.device_settings import DEFAULT_ENCODING, ENCODINGS, DeviceSettings, TextCodec
from nxwright.source.device_keys import DEVICE_KEYS, device_keys, screen_model, settings_from_keys
from nxwright.source.nx_files import (blank_lines_dropped, included_path, read_nx_file,
                                      read_page_files, resolve)
from nxwright.source.macros_source import (MACROS_PATH, block_of_compiled, callable_macros,
                                           compiled_macros, followed_macros,
                                           keep_comfortable_macros,
                                           macros_from_block, macros_to_source,
                                           read_macros_text)
from nxwright.source.page_source import (PAGE_FILE_SUFFIX, PageSource, editor_code_of_file,
                                         page_components, page_from_source, page_nx_path,
                                         page_to_source, page_toml_path, strip_generated,
                                         table_types)
from nxwright.source.editor_code_merge import (check_nxlang_imports, keep_comfortable_events,
                                               merge_nxlang_imports, nxlang_import_changes,
                                               switch_events_to_nxlang)
from nxwright.project.page_text import page_from_text, page_to_text
from nxwright.language.resource_names import (ANIMATION, LISTS, SOUND, VIDEO, ResourceNames,
                                              UnknownNameError, check_names, font_header_name,
                                              is_valid_name)
from nxwright.language.editor_code import (editor_equivalent, global_declarations,
                                           keep_editor_meaning, without_global_declarations)
from nxwright.language.nxlang import (MOST_GLOBALS, ProgramNames, compile_program,
                                      is_constant_line, read_program_names)
from nxwright.project.page_block import Event, PageBlock
from nxwright.project.screen_models import ScreenModel
from nxwright.source.series_components import check_series_components

SOURCE_FORMAT = 1
# The kinds of resource a source folder holds, by their list in app.toml,
# which is also their folder: the suffixes of each one's files. A picture has
# one file, of any of its suffixes (picture_file); the others, a file of each.
RESOURCE_FILES = {"pictures": PICTURE_SUFFIXES,
                  **{kind.folder: kind.suffixes for kind in COPIED_KINDS}}
# The suffix of a font's file in a source folder.
FONT_SUFFIX = FONTS.suffixes[0]
# The name extract gives a new resource of each kind, from its ID, when its
# files hold none.
_PLACEHOLDERS = {"pictures": "picture-%04d", "fonts": "font-%02d",
                 "animations": "animation-%02d", "videos": "video-%02d", "sounds": "sound-%02d"}
# The lists app.toml may leave out, meaning none: a folder written before
# nxwright knew animations, videos, and sounds has none of them.
_OPTIONAL_LISTS = tuple(kind.folder for kind in MEDIA)
# The suffix of the file of an animation, a video, or a sound that the
# screen plays, by its kind (resource_names.py): an animation's screen form.
_PLAYED_SUFFIXES = {ANIMATION: ".screen.gmov", VIDEO: ".video", SOUND: ".wav"}
# The languages app.toml names: the Editor's own, written comfortably, or nxlang.
NEXTION = "nextion"
NXLANG = "nxlang"
LANGUAGES = (NEXTION, NXLANG)


def import_dump(dump_folder: Path, source_folder: Path, name: str = None) -> list:
    """Imports the dump's project into `source_folder`, and returns the
    warnings of what the source files leave out: blank lines of the code,
    which the build would drop.

    A new or empty folder gets a fresh import, in the Editor's own language
    ("nextion"), its app named `name` where that is a name an app may have
    (_is_app_name). A folder holding app.toml is updated and keeps its
    name, or its lack of one, and its language:
      - pictures and fonts keep their names when their bytes match;
      - every event, and program.nx, keeps its existing text when that turns
        into the dump's Editor code;
      - in a folder using nxlang, an event the Editor changed is written into
        whichever .nx file holds it (see nxlang_import_changes);
      - everything else is rewritten;
      - files the old app.toml lists that the project no longer has are
        deleted, one by one.
    Folders are never deleted, and files the old app.toml does not list are
    never touched.

    Raises NxwrightError, before writing or deleting anything, when the dump
    holds something the source folder cannot represent, the folder's own code
    cannot be turned into Editor code, or `source_folder` is neither empty nor
    a source folder.
    """
    dump_folder, source_folder = Path(dump_folder), Path(source_folder)
    updating = (source_folder / "app.toml").is_file()
    if not updating and source_folder.exists() and any(source_folder.iterdir()):
        raise NxwrightError("%s is neither empty nor a source folder (it has no app.toml)"
                            % source_folder)
    check_dump_format(dump_folder)
    old_app = parse_app(read_text(source_folder / "app.toml")) if updating else None
    if updating:
        name = old_app.get("name")
    elif name is not None and not _is_app_name(name):
        name = None
    files, names, generated, warnings = _source_files_from_dump(dump_folder, source_folder,
                                                                old_app, name)
    stale = _keep_existing_code(source_folder, files, names, old_app, generated) if updating else []
    for relative, content in files.items():
        path = source_folder / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    # Windows file names ignore case: a stale path that differs from a new one
    # only in case is the new file, and must stay.
    written = {relative.lower() for relative in files}
    for relative in stale:
        if relative.lower() not in written:
            (source_folder / relative).unlink(missing_ok=True)
    return warnings


def _keep_existing_code(source_folder: Path, files: dict, names: ResourceNames,
                        old_app: dict, generated: dict) -> list:
    """Puts the existing folder's code into `files` wherever it preprocesses to
    the same Editor code, and returns the files the old app.toml lists that
    `files` no longer has. `generated` is {page name: the events of its
    generated components}, for a folder using nxlang."""
    uses_nxlang = old_app["language"] == NXLANG
    read = folder_reader(source_folder)
    old_program = source_folder / "program.nx"
    old_text = read_text(old_program) if old_program.is_file() else None
    program = (program_names(old_text, read) if uses_nxlang and old_text is not None
               else ProgramNames())
    pages = []
    new_pages = parse_app(files["app.toml"].decode("utf-8"))["pages"]
    components = {page_name: _page_components(files[page_toml_path(page_name)].decode("utf-8"),
                                               page_name) for page_name in new_pages}
    # nxlang compiles each page with every page's object types, as the build does.
    object_types = {page_name: types for page_name, (_, types) in components.items()}
    for new_id, page_name in enumerate(new_pages):
        relative = page_nx_path(page_name)
        old = source_folder / relative
        if not old.is_file():
            continue
        fresh = files[relative].decode("utf-8")
        object_names = components[page_name][0]
        if uses_nxlang:
            # The generated globals are named after the page's ID at the last
            # build: its place in the old app.toml.
            built_id = old_app["pages"].index(page_name) if page_name in old_app["pages"] else new_id
            page_files = read_page_files(relative, read_text(old), read)
            pages.append(nxlang_import_changes(fresh, page_name, page_files, names, object_names,
                                               program, generated.get(page_name, {}), built_id,
                                               object_types))
        else:
            kept = keep_comfortable_events(fresh, read_text(old), page_name, names, object_names)
            files[relative] = kept.encode("utf-8")
    if pages:
        # Every page's changes are gathered first. A file that several pages
        # include changes only where they agree, and nothing is written until
        # every page is checked.
        texts = merge_nxlang_imports(pages)
        check_nxlang_imports(pages, texts, read, names)
        for page in pages:
            relative = page_nx_path(page.page_name)
            files[relative] = texts.pop(relative, read_text(source_folder / relative)).encode("utf-8")
        for relative, text in texts.items():
            files[relative] = text.encode("utf-8")
    if old_text is not None:
        fresh = files["program.nx"].decode("utf-8")
        encoding = parse_app(files["app.toml"].decode("utf-8")).get("encoding", DEFAULT_ENCODING)
        new_program = _program_from_source(fresh, names, encoding=encoding)
        try:
            old_code = _program_from_source(old_text, names, program if uses_nxlang else None,
                                            encoding)
            unchanged = old_code == new_program
        except UnknownNameError:
            unchanged = False   # it names a picture or font the app no longer lists
        if unchanged:
            files["program.nx"] = old_text.encode("utf-8")
        elif uses_nxlang:
            files["program.nx"] = _nxlang_program(fresh, old_text, new_program, names, read,
                                                  encoding)
    old_macros = source_folder / MACROS_PATH
    if MACROS_PATH in files and old_macros.is_file():
        files[MACROS_PATH] = keep_comfortable_macros(files[MACROS_PATH].decode("utf-8"),
                                                     read_text(old_macros), names).encode("utf-8")
    return [relative for relative in _layout_files(old_app) if relative not in files]


def program_names(program_text: str, read) -> ProgramNames:
    """Returns the constants and int variables program.nx declares, with the
    constants of the files it includes, and the folder's macros, which
    nxlang follows where its code calls one (macros_source.followed_macros)."""
    lines = numbered_lines(program_text)
    included, seen = [], set()

    def visit(path: str, number: int, including: str):
        if path in seen:
            return
        seen.add(path)
        try:
            text = read(path)
        except NxwrightError as error:
            raise NxwrightError(str(error), file=including, line=number) from None
        nx_file = read_nx_file(path, text)
        if nx_file.blocks:
            raise NxwrightError("program.nx can include constants only, and %s "
                                "holds events or functions" % path, file=including, line=number)
        for inner_number, inner in nx_file.includes:
            visit(inner, inner_number, path)
        included.append((path, nx_file.preamble))
    for number, text in lines:
        written = included_path(text)
        if written is not None:
            visit(resolve("program.nx", written, number), number, "program.nx")
    names = read_program_names(lines, included)
    names.macros = followed_macros(read)
    return names


def folder_reader(source_folder: Path):
    """Returns read(path): the text of a file of the source folder, by its relative path."""
    def read(path: str) -> str:
        if not (source_folder / path).is_file():
            raise MissingFileError("%s is missing" % path)
        return read_text(source_folder / path)
    return read


def folder_byte_reader(source_folder: Path):
    """Returns read_bytes(path, size=None): the bytes of a file of the
    source folder, by its relative path, or its first `size` bytes. It
    raises OSError for a file it cannot read."""
    def read_bytes(path: str, size: int = None) -> bytes:
        with open(Path(source_folder) / path, "rb") as file:
            return file.read(-1 if size is None else size)
    return read_bytes


def video_rotation_problem(app: dict, head: bytes):
    """Returns what keeps a video whose file starts with `head`
    (media_files.VIDEO_HEAD_SIZE bytes or more) from a folder whose settings
    are `app`, or None: it was made for another rotation than the folder's
    screen, which the Editor refuses to compile, saying "The direction of
    the file is inconsistent with the current engineering display
    direction". A folder without screen settings, whose rotation is not
    known, and a file that is not a video file, are left to other checks."""
    settings = settings_from_keys(app)
    try:
        made_for = video_rotation(head)
    except NxwrightError:
        return None
    if settings is None or made_for == settings.rotation:
        return None
    return ("was made for a screen turned %d degrees, where the folder's is turned %d; the "
            "Nextion Editor refuses to compile it: make it again for the folder's rotation, with "
            "`nxwright video` or VideoBox's display direction" % (made_for, settings.rotation))


def _nxlang_program(fresh: str, old_text: str, new_program: bytes, names: ResourceNames,
                    read, encoding: str) -> bytes:
    """Returns program.nx for Editor code the Editor changed, in a folder using
    nxlang: the old file's includes and constants, then the Editor's code with
    keep_editor_meaning's parentheses.

    Raises NxwrightError when that would not build to the Editor's code.
    """
    lines = keep_editor_meaning(numbered_lines(fresh))
    const_lines = [text for _, text in numbered_lines(old_text)
                   if is_constant_line(text) or included_path(text) is not None]
    text = "\n".join(const_lines + [line for _, line in lines])
    text += "\n" if fresh.endswith("\n") else ""
    codec = TextCodec(encoding)
    expected = "\r\n".join(editor_equivalent(codec.decode(new_program, "program.s").split("\r\n")))
    if (_program_from_source(text, names, program_names(text, read), encoding)
            != codec.encode(expected, "program.s")):
        raise NxwrightError("program.nx: its code in strict Nextion syntax would not build to "
                            "the same code in nxlang")
    return text.encode("utf-8")


def _page_components(page_toml: str, page_name: str) -> tuple:
    """Returns (the names in a page's .page.toml file, the page's then its
    components', in ID order; the types of its objects, {name: type}), as
    nxlang's compiler takes them."""
    data = parsed_page_toml(page_toml, page_name)
    return names_in_page_data(data), types_in_page_data(data)


def parsed_page_toml(page_toml: str, page_name: str) -> dict:
    """Returns a page's .page.toml file parsed. Raises NxwrightError naming
    the file when it is not TOML."""
    try:
        return tomllib.loads(page_toml)
    except tomllib.TOMLDecodeError as error:
        raise NxwrightError("%s%s: %s" % (page_name, PAGE_FILE_SUFFIX, error)) from None


def _page_data_tables(data: dict) -> list:
    """Returns the tables of a parsed .page.toml file: the page's, then its
    components', in ID order. A table of the wrong shape, or whose name is
    not text, as one being typed may hold, is skipped here, as no name can
    key it: building the page reports it."""
    components = data.get("component", [])
    return [table for table in
            [data.get("page")] + (components if isinstance(components, list) else [])
            if isinstance(table, dict) and isinstance(table.get("name"), (str, type(None)))]


def names_in_page_data(data: dict) -> list:
    """Returns the names in a parsed .page.toml file: the page's, then its
    components', in ID order (_page_data_tables)."""
    return [table.get("name") for table in _page_data_tables(data)]


def global_names_in_page_data(data: dict, defaults: dict) -> frozenset:
    """Returns the names of the components of global scope (`vscope` 1) of a
    parsed .page.toml file. `defaults`, the folder's {type number:
    TypeDefaults}, gives the scope of a component whose table leaves it out."""
    return frozenset(table.get("name") for table in _page_data_tables(data)
                     if table is not data.get("page")
                     and number_in_table(table, defaults, "vscope") == 1)


def absent_attributes_in_page_data(data: dict, defaults: dict, screen=None) -> dict:
    """Returns {name: {attribute: why}} of the page and the components of a
    parsed .page.toml file that lack attributes by their values, as the file
    gives them or their type's defaults do, or on the series of `screen`, the
    folder's screen model, when given (editor_limits.lacked_attributes).
    `defaults`, the folder's {type number: TypeDefaults}, gives a value a
    table leaves out."""
    found = {}
    for table in _page_data_tables(data):
        lacked = lacked_attributes(table.get("type"), partial(number_in_table, table, defaults),
                                   screen)
        if lacked:
            found[table.get("name")] = lacked
    return found


def number_in_table(table: dict, defaults: dict, attribute: str):
    """Returns a component's number `attribute`, such as `vscope`, as its
    page file's `table` gives it. A page file leaves out an attribute equal
    to its type's default, so a table without it has its type's. None when
    neither gives one; the page's build then reports what is wrong."""
    if attribute in table:
        return table[attribute]
    type_value = table.get("type")
    object_type = TYPES_BY_NAME.get(type_value) if isinstance(type_value, str) else type_value
    type_defaults = defaults.get(object_type) if isinstance(object_type, int) else None
    stored = dict(type_defaults.attributes).get(attribute) if type_defaults else None
    return None if stored is None else number_from_bytes(stored)


def types_in_page_data(data: dict) -> dict:
    """Returns {name: type} of the objects of a parsed .page.toml file: the
    page's, then its components', in ID order (_page_data_tables)."""
    return table_types(_page_data_tables(data))


def numbered_lines(text: str) -> list:
    """Returns [(line number, text)] of `text`, from 1, ignoring a final newline."""
    body = text[:-1] if text.endswith("\n") else text
    return list(enumerate(body.split("\n"), start=1))


def played_file(kind: str, name: str) -> str:
    """Returns the path, within a source folder, of the file the screen
    plays for the animation, video, or sound (`kind`) called `name`."""
    return "%s/%s%s" % (LISTS[kind], name, _PLAYED_SUFFIXES[kind])


def picture_file(name: str, exists) -> str:
    """Returns the path, within the folder, of the picture `name`'s file,
    pictures/<name> with one of the suffixes its record may give
    (resources.PICTURE_SUFFIXES), as `exists(path)` finds it: the first in
    their order when several are there, which the build and the checks
    refuse (check_picture_file); or its PNG's path when none is."""
    paths = picture_paths(name)
    return next((path for path in paths if exists(path)), paths[0])


def check_picture_file(name: str, exists):
    """Raises NxwrightError unless the picture `name` has one file, as
    `exists(path)` finds them (picture_file)."""
    paths = picture_paths(name)
    found = [path for path in paths if exists(path)]
    if not found:
        raise NxwrightError("%s, %s, or %s is missing" % (
            paths[0], ", ".join(suffix for suffix in RESOURCE_FILES["pictures"][1:-1]),
            RESOURCE_FILES["pictures"][-1]))
    if len(found) > 1:
        raise NxwrightError("%s are there; a picture has one file" % " and ".join(found))


def picture_paths(name: str) -> list:
    """The paths the picture `name`'s file may have, in PICTURE_SUFFIXES' order."""
    return ["pictures/%s%s" % (name, suffix) for suffix in RESOURCE_FILES["pictures"]]


def resource_paths(kind: str, name: str, exists) -> list:
    """Returns the paths, within the folder, of the files of the resource
    `name` that app.toml lists in `kind`: a picture's one file
    (picture_file), or a file of each of RESOURCE_FILES' suffixes for the
    others. `exists(path)` says whether the folder holds a file."""
    if kind == "pictures":
        return [picture_file(name, exists)]
    return ["%s/%s%s" % (kind, name, suffix) for suffix in RESOURCE_FILES[kind]]


def resource_problems(kind: str, name: str, exists) -> list:
    """Returns what keeps the resource `name`, of app.toml's list `kind`,
    from being built, a sentence each: a picture with no file or more than
    one (check_picture_file), or a missing file of another resource."""
    if kind == "pictures":
        try:
            check_picture_file(name, exists)
        except NxwrightError as error:
            return [str(error)]
        return []
    return ["%s is missing" % path for path in resource_paths(kind, name, exists)
            if not exists(path)]


def _layout_files(app: dict) -> list:
    """Returns the files of a source folder, by relative path, that `app` lists."""
    # macros.nx is the folder's whenever it has macros: an update of a
    # project without them removes it.
    listed = ["app.toml", "defaults.toml", "program.nx", MACROS_PATH]
    for page_name in app["pages"]:
        listed += [page_toml_path(page_name), "pages/%s.nx" % page_name]
    for kind, suffixes in RESOURCE_FILES.items():
        listed += ["%s/%s%s" % (kind, name, suffix) for name in app[kind] for suffix in suffixes]
    return listed


# What nxwright new writes: the Editor's blank project, as extracting it
# gives, but for the comments of its program.
_NEW_PROGRAM = """// Runs once at power-on: the variables every page shares, settings, then
// the first page.
%s
baud=9600
dim=100
recmod=0
printh 00 00 00 ff ff ff 88 ff ff ff
page 0
""" % EDITOR_PROGRAM_DECLARATION
# The height of the font a new folder starts with (_shipped_font), in pixels:
# one a text of the Editor's default height, 30, holds.
NEW_FOLDER_FONT_HEIGHT = 24
_NEW_PAGE = """[page]
name = "%s"
type = "page"
x = 0
y = 0
w = %d
h = %d
"""


def new_source_folder(source_folder: Path, settings: DeviceSettings, language: str,
                      name: str = None):
    """Writes a new source folder holding one blank page the size of the
    screen, and one font, so that a first text builds (_shipped_font). Its
    app.toml names the app `name`, or else after the folder, so that
    renaming the folder keeps the app's name. Returns the font's warning, or
    None. Raises NxwrightError, before
    writing anything, when the folder exists and is not empty, the name is
    none an app may have (_is_app_name), or the language or encoding is not
    one nxwright knows."""
    source_folder = Path(source_folder)
    name = Path(source_folder).resolve().name if name is None else name
    if not _is_app_name(name):
        raise NxwrightError("the app's %s" % _APP_NAME_RULE)
    if source_folder.exists() and any(source_folder.iterdir()):
        raise NxwrightError("%s is not empty" % source_folder)
    if language not in LANGUAGES:
        raise NxwrightError("language must be %r or %r" % LANGUAGES)
    if settings.encoding not in ENCODINGS.values():
        raise NxwrightError("unknown character encoding %r" % settings.encoding)
    width, height = settings.page_size
    font_name, font_block, warning = _shipped_font(settings.encoding, settings.rotation)
    app = dict({"format": SOURCE_FORMAT, "name": name, "language": language},
               **device_keys(settings), pages=["page0"], pictures=[],
               fonts=[font_name])
    files = {"app.toml": app_text(app).encode("utf-8"),
             "defaults.toml": DEFAULTS_FILE.read_bytes(),
             "program.nx": _NEW_PROGRAM.encode("utf-8"),
             page_toml_path("page0"): (_NEW_PAGE % ("page0", width, height)).encode("utf-8"),
             "pages/page0.nx": b"",
             "fonts/%s%s" % (font_name, FONT_SUFFIX): font_block}
    for relative, content in files.items():
        path = source_folder / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    return warning


def add_page(source_folder: Path, name: str = None) -> str:
    """Adds a blank page the size of the screen, at its rotation, to a source
    folder, as new_source_folder writes page0: its page file, and an empty
    code file. The page is listed last in app.toml. Without a name, it takes
    the first of page0, page1, and so on that the folder lacks. Returns the
    page's name.

    Raises NxwrightError, before writing anything, for a folder without
    screen settings; a name app.toml's pages may not hold, or one the build
    refuses for a page (editor_limits.check_page_limits); a name the folder
    has already, in any case; and a file already at the place of one it
    writes."""
    source_folder = Path(source_folder)
    app = parse_app(read_text(source_folder / "app.toml"))
    settings = settings_from_keys(app)
    if settings is None:
        raise NxwrightError("app.toml gives no screen settings, so the page's size is not known")
    taken = {page.lower(): page for page in app["pages"]}
    if name is None:
        name = next("page%d" % number for number in count() if "page%d" % number not in taken)
    elif not is_valid_name(name) or "/" in name:
        raise NxwrightError("%r is not a valid page name" % name)
    elif name.lower() in taken:
        raise NxwrightError("the folder has a page named %s already" % taken[name.lower()])
    if len(name) > NAME_LIMIT:
        raise NxwrightError("the name %s has %d characters; the Nextion Editor keeps %d"
                            % (name, len(name), NAME_LIMIT))
    if name in NAMES_THE_EDITOR_REFUSES:
        raise NxwrightError('the Nextion Editor refuses this name, saying "Illegal name": %s'
                            % name)
    if name[:1].isdigit():
        raise NxwrightError('the Nextion Editor refuses a name that starts with a digit, saying '
                            '"First character of a Name can not be number": %s' % name)
    width, height = settings.page_size
    files = {page_toml_path(name): (_NEW_PAGE % (name, width, height)).encode("utf-8"),
             "pages/%s.nx" % name: b""}
    for relative in files:
        if (source_folder / relative).exists():
            raise NxwrightError("%s is already there, though app.toml does not list it"
                                % (source_folder / relative))
    for relative, content in files.items():
        (source_folder / relative).parent.mkdir(parents=True, exist_ok=True)
        (source_folder / relative).write_bytes(content)
    (source_folder / "app.toml").write_text(app_text(dict(app, pages=app["pages"] + [name])),
                                           encoding="utf-8", newline="\n")
    return name


@cache
def _shipped_font(encoding: str, rotation: int):
    """Returns (name, block, a warning or None) of the font a new folder
    starts with: Noto Sans, which nxwright ships, NEW_FOLDER_FONT_HEIGHT
    pixels tall, in `encoding` and turned to `rotation`, as add_font draws
    it. In utf-8, it holds UTF8_CHARACTERS, as a keyboard's font does. In an
    encoding Noto Sans lacks some characters of, such as koi8-r, it leaves
    them out, or in a two-byte encoding draws them empty, and the warning
    says so. Each is drawn once per process, as many folders may start
    alike."""
    typeface = noto_sans()
    name = drawn_font_name(typeface.typeface_name(), NOTO_SANS, NEW_FOLDER_FONT_HEIGHT)
    characters = UTF8_CHARACTERS if encoding == UTF8 else None
    block = draw_font_block(name, typeface, NEW_FOLDER_FONT_HEIGHT, encoding, rotation,
                            characters=characters)
    warning = None if encoding == UTF8 else noto_sans_lacks("the font %s" % name, encoding,
                                                            "text")
    return name, block, warning


# What a name in app.toml's `name` must be, as a refusal says it.
_APP_NAME_RULE = "name must be a text of one line, not empty, with no spaces at its start or end"


def _is_app_name(name) -> bool:
    """Whether `name` may be an app's name in app.toml: a text of one line,
    not empty, without spaces at its start or end. It is a name to show, so
    it may hold any other character."""
    return (isinstance(name, str) and name != "" and name == name.strip()
            and "\n" not in name and "\r" not in name)


def app_name(app: dict, source_folder: Path) -> str:
    """Returns the app's name, as nxwright shows it: the `name` of `app`,
    app.toml's keys as read_app gives them, or else the source folder's
    name."""
    return app.get("name") or Path(source_folder).resolve().name


def read_app(source_folder: Path) -> dict:
    """Returns the keys of the folder's app.toml, each list of resources and
    the language filled in when app.toml leaves them out. Raises
    NxwrightError when app.toml cannot be read, as for a folder in another
    format than the current one."""
    return parse_app(read_text(Path(source_folder) / "app.toml"))


def switch_to_nxlang(source_folder: Path):
    """Switches a source folder to nxlang: rewrites each line of
    its code that nxlang would read differently (see
    keep_editor_meaning), then sets `language = "nxlang"` in app.toml.

    Raises NxwrightError, before writing anything, when the folder already
    uses it, or its code would not build to the same project.
    """
    source_folder = Path(source_folder)
    for relative, text in nxlang_switch_files(source_folder).items():
        (source_folder / relative).write_text(text, encoding="utf-8", newline="\n")


def nxlang_switch_files(source_folder: Path) -> dict:
    """Returns the files switch_to_nxlang writes, {relative path: new text},
    without writing them: each code file with a line nxlang would read
    differently, and app.toml. Raises NxwrightError as switch_to_nxlang does.
    """
    source_folder = Path(source_folder)
    app = parse_app(read_text(source_folder / "app.toml"))
    if app["language"] == NXLANG:
        raise NxwrightError("%s already uses nxlang" % source_folder)
    names = ResourceNames.of_app(app)
    files = {}
    program = read_text(source_folder / "program.nx")
    declared = program_names(program, folder_reader(source_folder))
    pages = source_folder / "pages"
    components = {page_name: _page_components(read_text(pages / (page_name + PAGE_FILE_SUFFIX)),
                                              page_name)
                  for page_name in app["pages"]}
    # nxlang compiles each page with every page's object types, as the build does.
    object_types = {page_name: types for page_name, (_, types) in components.items()}
    for page_name in app["pages"]:
        events = read_text(pages / (page_name + ".nx"))
        switched = switch_events_to_nxlang(events, page_name, names, components[page_name][0],
                                           declared, object_types)
        if switched != events:
            files["pages/%s.nx" % page_name] = switched
    encoding = app.get("encoding", DEFAULT_ENCODING)
    codec = TextCodec(encoding)
    expected = "\r\n".join(editor_equivalent(codec.decode(
        _program_from_source(program, names, encoding=encoding), "program.s").split("\r\n")))
    lines = keep_editor_meaning(numbered_lines(program))
    switched = "\n".join(text for _, text in lines) + ("\n" if program.endswith("\n") else "")
    if (_program_from_source(switched, names, declared, encoding)
            != codec.encode(expected, "program.s")):
        raise NxwrightError("program.nx would not build to the same code in nxlang")
    if switched != program:
        files["program.nx"] = switched
    files["app.toml"] = app_text(dict(app, language=NXLANG))
    return files


def drawn_font_name(typeface: str, font_file: Path, height: int) -> str:
    """Returns the name add_font gives a font drawn from a typeface file when
    given none: the typeface's name, as TrueTypeFont.typeface_name gives it,
    or the file's when the typeface's has no letter a name may have, then
    the height, as NotoSans20."""
    return "%s%d" % (name_part(typeface) or name_part(Path(font_file).stem) or "font",
                     height)


def noto_sans_lacks(font: str, encoding: str, text: str):
    """Returns what a warning says of a font drawn from Noto Sans in a
    one-byte `encoding`, `font` naming it, when Noto Sans lacks some of the
    encoding's characters, which the font leaves out, and `text` showing
    them: what the screen shows in their place (font_drawing.lacking_words).
    None when it lacks none."""
    words = lacking_words(*drawn_codes(noto_sans(), encoding), encoding)
    if words is None:
        return None
    return "%s is drawn from Noto Sans, which lacks %s: %s in them shows %s" % (font, words[0],
                                                                                text, words[1])


def name_part(text: str) -> str:
    """Returns `text` kept to the characters a name may have: "Noto Sans
    Bold" gives NotoSansBold, the start of a font's name."""
    return re.sub(r"[^A-Za-z0-9_-]", "", text)


def export_dump(source_folder: Path, dump_folder: Path, refuse_by_table: bool = True) -> tuple:
    """Writes the dump files the project writer reads, built from a source
    folder, into the new or empty folder `dump_folder`. Returns (the
    pictures it wrote, {the dump's file, as "images/0000.png": the folder's,
    as "pictures/logo.png"}, so that a refusal of the dump's file can name
    the folder's; the project's memory, as the Editor's compile counts it,
    a page_memory.ProjectMemory, or None without screen settings).

    Raises NxwrightError, before writing anything, naming the source file at
    fault: a picture nxwright cannot read among them (pictures.picture_problem),
    and the first page whose memory the Editor's compile refuses
    (memory_refusal). Without `refuse_by_table`, the pages are not checked
    against the memory table (FolderSource.refuse_by_table).
    """
    source_folder, dump_folder = Path(source_folder), Path(dump_folder)
    if dump_folder.exists() and any(dump_folder.iterdir()):
        raise NxwrightError("%s exists and is not empty" % dump_folder)
    files, pictures, memory = _dump_files_from_source(source_folder, refuse_by_table)
    for relative, content in files.items():
        path = dump_folder / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    return pictures, memory


def _source_files_from_dump(dump_folder: Path, source_folder: Path, old_app,
                            project_name: str = None) -> tuple:
    """Returns the source folder's files for a dump, as a tuple of:
      - {relative path: bytes} of every file;
      - the ResourceNames chosen for the pictures, fonts, and media;
      - {page name: the events of its generated variables}, filled only when
        the folder uses nxlang;
      - the warnings of what the source files leave out, in the order met.
    `old_app` is the app.toml of the folder being updated, or None, and
    `project_name` the app's name its app.toml gives, or None."""
    # A dump missing one of these would import as a project without it.
    for required in ("pages", "images") + tuple(kind.folder for kind in COPIED_KINDS):
        if not (dump_folder / required).is_dir():
            raise NxwrightError("%s has no %s folder" % (dump_folder, required))
    files = {}
    # Each resource as the bytes of its files, in the order of RESOURCE_FILES.
    pictures = dump_pictures(dump_folder)
    resources = {"pictures": [(data,) for _, data, _ in pictures],
                 **{kind.folder: copied_contents(dump_folder, kind) for kind in COPIED_KINDS}}
    chosen = {kind: _choose_names(kind, contents, source_folder, old_app)
              for kind, contents in resources.items()}
    names = ResourceNames.of_app(chosen)
    defaults_text = DEFAULTS_FILE.read_bytes()
    defaults = defaults_from_toml(defaults_text.decode("utf-8"), DEFAULTS_FILE.name)
    files["defaults.toml"] = defaults_text
    for kind, contents in resources.items():
        for number, (name, parts) in enumerate(zip(chosen[kind], contents)):
            # A picture's one file has the suffix its record gives; another
            # resource has a file of each of its suffixes.
            suffixes = [pictures[number][2]] if kind == "pictures" else RESOURCE_FILES[kind]
            for suffix, content in zip(suffixes, parts):
                files["%s/%s%s" % (kind, name, suffix)] = content
    uses_nxlang = old_app is not None and old_app["language"] == NXLANG
    settings = dump_device_settings(dump_folder)
    encoding = settings.encoding if settings is not None else DEFAULT_ENCODING
    pages, generated, warnings = [], {}, []
    page_files = page_text_files(dump_folder)
    check_ids_without_gaps(page_files, "page")
    for page_id in range(len(page_files)):
        page = _without_trailing_spaces(
            page_from_text(page_files[page_id].read_text(encoding="utf-8")))
        if uses_nxlang:
            page, generated[page.name] = strip_generated(page, encoding)
        source = page_to_source(page, names, defaults, encoding)
        warnings += source.warnings
        pages.append(page.name)
        files[page_toml_path(page.name)] = source.toml.encode("utf-8")
        files["pages/%s.nx" % page.name] = source.events.encode("utf-8")
    if len(set(pages)) != len(pages):
        raise NxwrightError("two pages share a name")
    # The spaces and tabs ending a line are dropped first, as for the events.
    program = b"\r\n".join(line.rstrip(b" \t")
                           for line in (dump_folder / "program.s").read_bytes().split(b"\r\n"))
    if uses_nxlang:
        # The build adds the declarations of its globals again.
        codec = TextCodec(encoding)
        lines = codec.decode(program, "program.s").split("\r\n")
        program = codec.encode("\r\n".join(without_global_declarations(lines)), "program.s")
    files["program.nx"], dropped = _program_to_source(program, encoding)
    warnings += dropped
    if (dump_folder / MACROS_FILE).is_file():
        try:
            macros, dropped = macros_from_block((dump_folder / MACROS_FILE).read_bytes())
        except NxwrightError as error:
            raise NxwrightError("%s: %s" % (MACROS_FILE, error)) from None
        warnings += dropped
        files[MACROS_PATH] = macros_to_source(macros).encode("utf-8")
    app = {"format": SOURCE_FORMAT, "name": project_name,
           "language": NXLANG if uses_nxlang else NEXTION, "pages": pages, **chosen}
    if settings is not None:
        app.update(device_keys(settings))
    files["app.toml"] = app_text(app).encode("utf-8")
    return files, names, generated, warnings


def app_text(app: dict) -> str:
    """Returns the text of app.toml, its keys in their usual order, leaving
    out the empty lists it may leave out."""
    order = ("format", "name", "language") + DEVICE_KEYS + ("pages",) + tuple(RESOURCE_FILES)
    shown = {key: app[key] for key in order
             if app.get(key) is not None and not (key in _OPTIONAL_LISTS and not app[key])}
    return tomli_w.dumps(shown)


def _choose_names(kind: str, contents: list, source_folder: Path, old_app) -> list:
    """Returns a name for each resource of `kind`, its list in app.toml, in
    `contents`, in ID order, each one given as the bytes of its files
    (RESOURCE_FILES).

    One whose bytes match one of the folder being updated keeps its name
    (byte-identical ones in ID order). One whose bytes changed keeps the
    name of the old one at the same ID, if that matched nothing: it was
    edited in place. A new font is named after the name in its header.
    Anything else gets a placeholder name; no name repeats one already taken,
    even in different letter case.
    """
    old_list = old_app[kind] if old_app else []
    old_names = {}
    for name in old_list:
        paths = [source_folder / path for path in resource_paths(
            kind, name, lambda path: (source_folder / path).is_file())]
        # A missing file matches nothing; the import writes it again.
        if all(path.is_file() for path in paths):
            old_names.setdefault(tuple(path.read_bytes() for path in paths), []).append(name)
    names = [old_names[content].pop(0) if old_names.get(content) else None
             for content in contents]
    matched = set(names)
    for resource_id in range(min(len(names), len(old_list))):
        if names[resource_id] is None and old_list[resource_id] not in matched:
            names[resource_id] = old_list[resource_id]
    # New names have no "/", so they only clash with a kept name or its folders.
    taken = {name.lower() for name in names if name}
    taken |= {name.lower().split("/")[0] for name in names if name and "/" in name}
    for resource_id, content in enumerate(contents):
        if names[resource_id] is None:
            header_name = font_header_name(content[0]) if kind == "fonts" else None
            name = header_name if header_name and header_name.lower() not in taken \
                else _PLACEHOLDERS[kind] % resource_id
            base, number = name, 2
            while name.lower() in taken:
                name, number = "%s-%d" % (base, number), number + 1
            names[resource_id] = name
            taken.add(name.lower())
    check_names(names, kind)
    return names


def _without_trailing_spaces(page: PageBlock) -> PageBlock:
    """Returns a page read from a dump, the spaces and tabs ending each line
    of its events dropped. The Nextion Editor's compile drops them too. The
    bytes are cut: a space or a tab is never part of a two-byte character."""
    for page_object in page.objects:
        page_object.items = [Event(item.name, [line.rstrip(b" \t") for line in item.lines])
                             if isinstance(item, Event) else item
                             for item in page_object.items]
    return page


def _program_to_source(program: bytes, encoding: str) -> tuple:
    """Returns (program.nx, as UTF-8 with LF line endings, for the bytes of
    program.s, in the project's character encoding `encoding`; the warnings
    of what it dropped). The build drops blank lines, so program.nx could
    not give them back, and they compile to nothing: they are dropped.

    Raises NxwrightError for what program.nx cannot keep: mixed line
    endings, or a control character.
    """
    # An empty program has no line, not one empty line.
    lines = program.split(b"\r\n") if program else []
    if any(b"\r" in line or b"\n" in line for line in lines):
        raise NxwrightError("program.s mixes line endings; only CRLF can be kept")
    # A program ending in a line end ends with an empty last line, which stays.
    body, end = (lines[:-1], lines[-1:]) if program.endswith(b"\r\n") else (lines, [])
    kept = [line for line in body if line.strip()]
    warnings = [blank_lines_dropped("program.s", len(body) - len(kept))] \
        if len(kept) < len(body) else []
    text = TextCodec(encoding).decode(b"\n".join(kept + end), "program.s")
    if any(ord(char) < 0x20 and char not in "\t\n" or ord(char) == 0x7f for char in text):
        raise NxwrightError("program.s holds a control character")
    return text.encode("utf-8"), warnings


@dataclass
class FolderSource:
    """What building any page of a source folder needs, read once: the
    folder's settings and component defaults, what program.nx declares, and
    the names of every page's objects, since code may name another page's.
    Its files are read through `read(path)`, which returns a file's text by
    its path within the folder, and raises NxwrightError for a missing one."""
    read: object
    app: dict
    names: ResourceNames
    defaults: dict
    program: str                # program.nx's text
    declared: ProgramNames      # what program.nx declares; None in the Editor's own language
    page_objects: dict          # {page name: {object name: type}; None if broken}
    broken_pages: dict          # {page name: the NxwrightError reading its names}
    # Each page's components of global scope, which alone a macro reaches.
    page_globals: dict
    macros_text: str            # macros.nx's text; None when the folder has no macros
    macros: frozenset           # the macros' names, which a `call` must name; None if unread
    # program.nx's int variables, in the Editor's own language, which the
    # code's names of sys0 to sys2 are checked against (preprocess); None in
    # nxlang, whose compiler checks every name against `declared`.
    program_variables: frozenset = None
    # The attributes each page's components lack by their page file's
    # values, {page name: {name: {attribute: why}}}
    # (absent_attributes_in_page_data); None for a broken page.
    absent_attributes: dict = None
    # The screen model app.toml names, whose series' lacked commands and
    # system variables the code may not use; None without screen settings.
    screen: ScreenModel = None
    # Whether the pages are checked against the types and choices the
    # screen's series refuses (series_components.check_series_components), most
    # of them from the memory table, which the Editor tool's memory probe
    # measures. The probe builds such pages on purpose, to see the Editor
    # refuse them, and turns it off.
    refuse_by_table: bool = True

    def build_page(self, page_id: int, globals_used: list, chain: list = None) -> PageBlock:
        """Returns the page `page_id`, built from its files as page_from_source
        does, adding the program.s globals it uses to `globals_used`, and its
        longest chain of calls and clicks to `chain` when given. With the
        screen known, a component reaching past it is refused where its
        series refuses it (check_component_places); with `refuse_by_table`
        too, its components are checked against what the screen's series
        refuses (check_series_components).

        Raises NxwrightError naming the file at fault, which is also its `file`."""
        page_name = self.app["pages"][page_id]
        if page_name in self.broken_pages:
            raise self.broken_pages[page_name]
        toml_path, nx_path = page_toml_path(page_name), page_nx_path(page_name)
        source = PageSource(_in_file(toml_path, lambda: self.read(toml_path)),
                            _in_file(nx_path, lambda: self.read(nx_path)))
        page = page_from_source(source, page_name, self.names, self.defaults, self.declared,
                                page_id, globals_used, self.read, self.page_objects,
                                self.encoding, chain, self.program_variables, self.macros,
                                self.absent_attributes, self.screen)
        # Not a refusal by the memory table: the memory probe, which turns
        # those off, places every component inside the screen.
        if self.screen is not None:
            page_size = settings_from_keys(self.app).page_size
            _in_file(toml_path, lambda: check_component_places(page, self.screen, page_size,
                                                               "%s.page.toml" % page_name))
        if self.refuse_by_table and self.screen is not None:
            _in_file(toml_path, lambda: check_series_components(page, self.screen,
                                                                "%s.page.toml" % page_name))
        return page

    def build_program(self) -> bytes:
        """Returns program.s built from program.nx, without the declarations
        of the globals the pages use. Raises NxwrightError naming program.nx."""
        return _program_from_source(self.program, self.names, self.declared, self.encoding,
                                    self.program_variables, self.macros, self.screen,
                                    self.page_objects)

    def build_macros(self):
        """Returns the macros' block built from macros.nx (macros_source.py),
        or None when the folder has no macros. Raises NxwrightError naming
        macros.nx and the line at fault."""
        if self.macros_text is None:
            return None
        return block_of_compiled(self.compiled_macros())

    def compiled_macros(self) -> dict:
        """Returns the macros of macros.nx compiled, as
        macros_source.compiled_macros returns them; none when the folder has
        no macros. Raises NxwrightError as build_macros does."""
        if self.macros_text is None:
            return {}
        # macros.nx is Editor code, its names of sys0 to sys2 checked against
        # program.nx's int variables, in either language.
        return compiled_macros(self.macros_text, self.names, self.page_objects,
                               self.page_globals, program_int_variables(self.program),
                               self.absent_attributes, self.screen)

    @property
    def encoding(self) -> str:
        """The project's character encoding, in which its texts and code are
        stored; the Editor's default for a folder without device settings."""
        return self.app.get("encoding", DEFAULT_ENCODING)

    def editor_code(self, page_name: str, path: str) -> list:
        """Returns the Editor code of the events and functions of the .nx file
        `path`, as page `page_name` compiles them (editor_code_of_file in
        page_source.py). Raises NxwrightError as the build does."""
        component_names, own_types = _page_components(self.read(page_toml_path(page_name)),
                                                      page_name)
        # Every page's types, as the build compiles the page with them.
        return editor_code_of_file(path, page_name, self.read(page_nx_path(page_name)),
                                   self.names, component_names, self.declared,
                                   self.app["pages"].index(page_name), self.read,
                                   {**self.page_objects, page_name: own_types})


def read_folder_source(read, skip_broken_pages: bool = False,
                       refuse_by_table: bool = True) -> FolderSource:
    """Returns the FolderSource of the source folder whose files `read(path)`
    returns. Raises NxwrightError naming the file at fault, which is also its
    `file`: app.toml, defaults.toml, program.nx, or a page's .page.toml file.

    With `skip_broken_pages`, a page whose .toml file cannot be read is kept
    with its names unknown instead, and building it raises its error. So one
    half-typed page file does not stop a check of the others, and their
    references to it are not checked. Without `refuse_by_table`, its pages
    are not checked against the memory table (FolderSource.refuse_by_table)."""
    app = _in_file("app.toml", lambda: parse_app(read("app.toml")))
    defaults = _in_file("defaults.toml",
                        lambda: defaults_from_toml(read("defaults.toml"), "defaults.toml"))
    program = _in_file("program.nx", lambda: read("program.nx"))
    declared = program_variables = None
    if app["language"] == NXLANG:
        declared = _in_file("program.nx", lambda: program_names(program, read))
    else:
        # Read as the Editor reads them, without nxlang's rules for names.
        program_variables = _in_file("program.nx", lambda: program_int_variables(program))
    screen = screen_model(app)
    page_objects, page_globals, broken_pages, absent_attributes = {}, {}, {}, {}
    for page_name in app["pages"]:
        path = page_toml_path(page_name)
        try:
            data = _in_file(path, lambda: parsed_page_toml(read(path), page_name))
            page_objects[page_name] = types_in_page_data(data)
            page_globals[page_name] = global_names_in_page_data(data, defaults)
            absent_attributes[page_name] = absent_attributes_in_page_data(data, defaults, screen)
        except NxwrightError as error:
            if not skip_broken_pages:
                raise
            broken_pages[page_name] = error
            page_objects[page_name] = page_globals[page_name] = absent_attributes[page_name] = None
    macros_text = read_macros_text(read)
    return FolderSource(read, app, ResourceNames.of_app(app), defaults, program,
                        declared, page_objects, broken_pages, page_globals, macros_text,
                        callable_macros(macros_text), program_variables, absent_attributes,
                        screen, refuse_by_table)


@dataclass
class PageToml:
    """A page's .page.toml file, with what reading its tables needs."""
    app: dict                   # app.toml's settings
    names: ResourceNames
    defaults: dict              # the folder's component defaults
    encoding: str
    text: str                   # the page file's text


def read_page_toml(read, page_name: str) -> PageToml:
    """Returns a page's PageToml, read through `read(path)` as
    read_folder_source does, from app.toml, defaults.toml, and the page's
    .page.toml file alone: a page whose code does not build still has its
    components. Raises NxwrightError naming the file at fault."""
    app = _in_file("app.toml", lambda: parse_app(read("app.toml")))
    defaults = _in_file("defaults.toml",
                        lambda: defaults_from_toml(read("defaults.toml"), "defaults.toml"))
    path = page_toml_path(page_name)
    return PageToml(app, ResourceNames.of_app(app), defaults,
                    app.get("encoding", DEFAULT_ENCODING), _in_file(path, lambda: read(path)))


def read_page_components(read, page_name: str) -> tuple:
    """Returns (app.toml's settings, the page's Components), read as
    read_page_toml reads them. Raises NxwrightError naming the file at fault."""
    page_toml = read_page_toml(read, page_name)
    return page_toml.app, page_toml_components(page_toml, page_name)


def page_toml_components(page_toml: PageToml, page_name: str) -> list:
    """Returns the Components of the page `page_name`, from its PageToml.
    Raises NxwrightError naming the page's file at fault."""
    path = page_toml_path(page_name)
    return _in_file(path, lambda: page_components(
        page_toml.text, page_name, page_toml.names, page_toml.defaults, page_toml.encoding))


def _in_file(file: str, work):
    """Returns work(). An NxwrightError it raises that names no file gets
    `file` as its `file`."""
    try:
        return work()
    except NxwrightError as error:
        error.file = error.file or file
        raise


def code_files(app: dict, read) -> dict:
    """Returns {page: [paths of its .nx files]}: its own and those it
    includes, directly or not; and under None, program.nx and the files it
    includes. `app` is the folder's app.toml, and `read(path)` returns a file
    of the folder. Pages whose files cannot be read are left out."""
    files = {}
    for page in app["pages"]:
        try:
            page_files = read_page_files(page_nx_path(page), read(page_nx_path(page)), read)
        except NxwrightError:
            continue
        files[page] = [nx_file.path for nx_file in page_files.files]
    program = ["program.nx"]

    def visit(path: str):
        # Lists the files `path` includes, then those they include in turn,
        # as the build reads them (program_names). A file that cannot be
        # read is listed, but not what it would include.
        try:
            text = read(path)
            if path == "program.nx":
                written = [(number, included_path(line))
                           for number, line in enumerate(text.split("\n"), start=1)]
                includes = [resolve(path, include, number)
                            for number, include in written if include is not None]
            else:
                includes = [include for _, include in read_nx_file(path, text).includes]
        except NxwrightError:
            return
        for include in includes:
            if include not in program:
                program.append(include)
                visit(include)
    visit("program.nx")
    files[None] = program
    return files


def _dump_files_from_source(source_folder: Path, refuse_by_table: bool) -> tuple:
    """Returns ({relative path: bytes} of the dump files the writer reads,
    {the dump's file of each picture: the folder's}, the project's memory),
    checking the pages against the memory table as export_dump says."""
    folder = read_folder_source(folder_reader(source_folder), refuse_by_table=refuse_by_table)
    app = folder.app
    files = {"project.txt": (DUMP_FORMAT_LINE + "\n").encode("utf-8")}
    globals_used = []
    measured = {}       # {page name: what page_memory.measure_page found}
    for page_id, page_name in enumerate(app["pages"]):
        page = folder.build_page(page_id, globals_used)
        files["pages/%02d-%s.txt" % (page_id, page_name)] = page_to_text(page).encode("utf-8")
        if folder.screen is not None:
            measured[page_name] = measure_page(folder.screen, page)
    resources, pictures = _resource_dump_files(app, source_folder)
    files.update(resources)
    check_globals_count(globals_used)
    program_s = folder.build_program()
    memory = _checked_memory(folder, measured, program_s, len(globals_used))
    if globals_used:
        # Declared first, before any code of program.s runs.
        declarations = "\r\n".join(global_declarations(globals_used)) + "\r\n"
        program_s = TextCodec(folder.encoding).encode(declarations, "program.s") + program_s
    files["program.s"] = program_s
    # A folder whose macros.nx holds no macro has none. The Editor removes
    # the block once every macro is deleted.
    macros = folder.build_macros()
    if macros:
        files[MACROS_FILE] = macros
    return files, pictures, memory


def _resource_dump_files(app: dict, source_folder: Path) -> tuple:
    """Returns ({relative path: bytes} of the dump's pictures, animations,
    videos, and sounds, {the dump's file of each picture: the folder's}).
    Raises NxwrightError naming a picture nxwright cannot read, or a video
    made for another rotation."""
    def exists(path: str) -> bool:
        return (source_folder / path).is_file()
    files, pictures = {}, {}
    for picture_id, name in enumerate(app["pictures"]):
        check_picture_file(name, exists)
        path = picture_file(name, exists)
        content = read_bytes(source_folder / path)
        problem = picture_problem(content)
        if problem:
            raise NxwrightError("%s: %s" % (path, problem))
        dump_path = "images/%04d%s" % (picture_id, Path(path).suffix)
        files[dump_path] = content
        pictures[dump_path] = path
    for kind in COPIED_KINDS:
        for resource_id, name in enumerate(app[kind.folder]):
            for suffix in kind.suffixes:
                path = "%s/%s%s" % (kind.folder, name, suffix)
                content = read_bytes(source_folder / path)
                problem = video_rotation_problem(app, content) if kind.folder == LISTS[VIDEO] \
                    else None
                if problem:
                    raise NxwrightError("%s %s" % (path, problem))
                files["%s/%s" % (kind.folder, copied_file_name(resource_id, suffix))] = content
    return files, pictures


def _checked_memory(folder: FolderSource, measured: dict, program_s: bytes, generated: int):
    """Returns the project's ProjectMemory, from each page's, `measured`,
    program.s as built, and the count of `generated` globals; None without
    screen settings. Raises the first page's memory_refusal, unless the
    folder is built without the checks against the memory table
    (FolderSource.refuse_by_table)."""
    if folder.screen is None:
        return None
    # The generated globals are each an int.
    memory = project_memory(folder.screen, measured,
                            program_ints(program_s, folder.encoding) + generated)
    if memory.refusals and folder.refuse_by_table:
        raise memory_refusal(*memory.refusals[0])
    return memory


def program_ints(program_s: bytes, encoding: str) -> int:
    """Returns how many `int`s program.s declares, as `program_s` holds it
    built in `encoding` (FolderSource.build_program), sys0 to sys2 among
    them, and not the generated globals the build declares before it."""
    text = TextCodec(encoding).decode(program_s, "program.s").replace("\r\n", "\n")
    return len(program_int_variables(text))


def memory_refusal(page: str, why: str) -> NxwrightError:
    """Returns the error of a page whose memory the Editor's compile refuses,
    `why` saying how (page_memory.ProjectMemory.refusals), from its page file."""
    error = NxwrightError("%s.page.toml: %s" % (page, why))
    error.file = page_toml_path(page)
    return error


def check_globals_count(globals_used: list):
    """Raises NxwrightError, with program.nx as its `file`, when the pages
    need more program.s globals than were checked to work."""
    if len(globals_used) > MOST_GLOBALS:
        error = NxwrightError("nxlang needs %d program.s globals; at most %d were "
                              "checked to work" % (len(globals_used), MOST_GLOBALS))
        error.file = "program.nx"
        raise error


def folder_device_settings(source_folder: Path):
    """Returns the DeviceSettings in the folder's app.toml, or None when it
    has none. Raises NxwrightError when app.toml is missing or wrong."""
    return settings_from_keys(parse_app(read_text(Path(source_folder) / "app.toml")))


def parse_app(text: str) -> dict:
    """Returns the settings of an app.toml file as a dict, after checking them.

    Raises NxwrightError naming the first problem.
    """
    try:
        app = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise NxwrightError("app.toml: %s" % error) from None
    found = app.get("format")
    # TOML's true is Python's True, which equals 1: only a real number counts.
    is_number = isinstance(found, int) and not isinstance(found, bool)
    if is_number and found > SOURCE_FORMAT:
        raise NxwrightError("app.toml is in source format %d, which needs a newer nxwright; "
                            "this one reads format %d" % (found, SOURCE_FORMAT))
    if is_number and 1 <= found < SOURCE_FORMAT:
        raise NxwrightError("app.toml is in source format %d; nxwright upgrade converts it to "
                            "format %d" % (found, SOURCE_FORMAT))
    if not is_number or found != SOURCE_FORMAT:
        raise NxwrightError("app.toml: format must be %d" % SOURCE_FORMAT)
    pages = app.get("pages")
    if not isinstance(pages, list) or not all(isinstance(name, str) and is_valid_name(name)
                                              and "/" not in name for name in pages):
        raise NxwrightError("app.toml: pages must be a list of plain names")
    if len(set(pages)) != len(pages):
        raise NxwrightError("app.toml: pages lists a name twice")
    for kind in _OPTIONAL_LISTS:
        app.setdefault(kind, [])
    for kind in RESOURCE_FILES:
        if not isinstance(app.get(kind), list):
            raise NxwrightError("app.toml: %s must be a list of names" % kind)
        try:
            check_names(app[kind], kind)
        except NxwrightError as error:
            raise NxwrightError("app.toml: %s" % error) from None
    extra = (set(app) - {"format", "name", "language", "pages"} - set(RESOURCE_FILES)
             - set(DEVICE_KEYS))
    if extra:
        raise NxwrightError("app.toml: unknown key %s" % sorted(extra)[0])
    if "name" in app and not _is_app_name(app["name"]):
        raise NxwrightError("app.toml: %s" % _APP_NAME_RULE)
    if app.get("language") not in LANGUAGES:
        raise NxwrightError("app.toml: language must be %r or %r" % LANGUAGES)
    settings_from_keys(app)
    return app


def read_text(path: Path) -> str:
    """Returns the text of a UTF-8 file, with LF line endings."""
    try:
        return read_bytes(path).decode("utf-8-sig").replace("\r\n", "\n")
    except UnicodeDecodeError:
        raise NxwrightError("%s is not UTF-8 text" % path) from None


def read_bytes(path: Path) -> bytes:
    """Returns the bytes of the file at `path`. Raises NxwrightError when it
    is missing."""
    try:
        return path.read_bytes()
    except FileNotFoundError:
        raise NxwrightError("%s is missing" % path) from None


def _program_from_source(text: str, names: ResourceNames, program: ProgramNames = None,
                         encoding: str = DEFAULT_ENCODING, variables: frozenset = None,
                         macros: frozenset = None, screen: ScreenModel = None,
                         pages: dict = None) -> bytes:
    """Returns program.s for the text of program.nx: Editor syntax, CRLF line
    endings. With `program` (what program.nx declares), the text is in nxlang
    and is compiled first. With `variables`, its int variables, its names of
    sys0 to sys2 are checked, with `macros`, its calls, with `screen`, what
    its series lacks, and with `pages`, each page's objects by page name,
    the commands that name a page or a component (preprocess)."""
    ends_with_newline = text.endswith("\n")
    try:
        lines = numbered_lines(text)
        if program is not None:
            lines = compile_program(lines, program)
        lines = preprocess(lines, names, variables=variables, macros=macros, screen=screen,
                           program_pages=pages)
    except NxwrightError as error:
        if error.file is not None:
            raise   # a refusal at a line of macros.nx, which program.nx calls
        raise error.in_file("program.nx") from None
    return TextCodec(encoding).encode(
        "\r\n".join(lines) + ("\r\n" if ends_with_newline and lines else ""), "program.nx")
