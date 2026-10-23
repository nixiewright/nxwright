"""Compiling a source folder's pages and running their events on a PC, for tests.

A test names a page of a source folder and the events to run, such as
[("settings", "load"), ("save", "up")], with the values the code starts from.
The page's code is compiled as the build compiles it, then run in order by an
EditorMachine (editor_machine.py), and the values it leaves are returned for
the test to check.

The machine is also given the page's components' values, as the page file
and its defaults give them, beneath the test's own, and the folder's fonts
and pictures (folder_resources.py). It reads them to know a component's
type and to work its list components as the simulator does
(list_working.py), not for the code: code reading a field the test did not
give still stops the run. Before the events, the page's opening works its
list components, as the simulator's does (EditorMachine.open_page); then
the test's values are written again, as given, so that they win.
"""
from dataclasses import dataclass, field
from pathlib import Path
import re

from nxwright import NxwrightError
from nxwright.language.code_checks import ObjectNames
from nxwright.language.code_lines import program_int_variables, split_line
from nxwright.language.code_preprocessor import (Owner, preprocess, preprocess_with_places,
                                                 with_own_attributes)
from nxwright.language.nxlang import GENERATED_GLOBAL, GENERATED_NAME
from nxwright.language.resource_names import ResourceNames
from nxwright.project.component_defaults import defaults_from_toml
from nxwright.project.device_settings import DEFAULT_ENCODING
from nxwright.project.editor_limits import bounded_attributes, lacked_attributes
from nxwright.project.object_types import TYPES_BY_NAME
from nxwright.source import source_folder as folders
from nxwright.source.device_keys import screen_model
from nxwright.source.macros_source import (MACROS_PATH, callable_macros, compiled_macros,
                                           read_macros_text)
from nxwright.source.nx_files import event_blocks
from nxwright.source.page_source import (compile_nxlang_page, file_at_fault, generated_table,
                                         page_nx_path, page_toml_path, table_types)
from nxwright.testing.editor_machine import EditorMachine
from nxwright.testing.folder_resources import FolderResources
from nxwright.testing.pinyin_table import pinyin_table_of
from nxwright.testing.recording import Place, current_recorder

# run_code compiles its code as the Touch Press event of a page of its own,
# named "p", with no components.
_CODE_PAGE = "p"
_CODE_EVENT = (_CODE_PAGE, "down")

# The result of each compile, kept for the rest of the test run, as
# {key: (the paths of the files it read, their _stamp, the result, what it
# was made from: the folder's FolderPageTables, or None)}.
_COMPILED = {}


@dataclass
class RunnablePage:
    """A compiled page, with what the debugger's recording needs too."""
    code: dict          # {(component, event): its Editor code lines}
    start: dict         # {name: start value}
    places: dict        # {(component, event): a recording Place or None per line}
    local_names: dict   # {owner: {generated variable: nxlang name}}
    # The folder's character encoding, read from app.toml with the rest, so
    # that a run does not read app.toml again.
    encoding: str
    # Whether the code was compiled from nxlang, whose generated variables
    # the debugger groups apart: none is generated in the Editor's own language.
    nxlang: bool
    # The page's Components, from its page file, and their values, beneath
    # the test's (component_start_values); read once, as each compile is.
    components: list = field(default_factory=list)
    page_values: dict = field(default_factory=dict)


@dataclass
class FolderPageTables:
    """What the compile of every page reads of a source folder, each file
    parsed once: app.toml's settings, the component defaults of
    defaults.toml, and what each page's .page.toml file holds. A page's code
    may name another page's components, and set its texts, so each page's
    compile needs every page's file. The runner keeps one per folder until
    one of those files changes. It is shared by every caller: do not change it."""
    app: dict
    defaults: dict          # {type number: TypeDefaults}
    texts: dict             # {page: the text of its .page.toml file}
    names: dict             # {page: the names of the page and its components, in ID order}
    types: dict             # {page: {name: type} of the page and its components}
    globals: dict           # {page: the names of its components of global scope}
    text_limits: dict       # {page: {"name.attribute": the most bytes it keeps}}
    system_pages: dict      # {page: the system page its file says it is, or None}
    absent_attributes: dict  # {page: {name: {attribute: why}} of what its components lack}

    def page_toml(self, page: str) -> folders.PageToml:
        """Returns the PageToml of `page`, as read_page_toml reads it, from
        the files already read."""
        return folders.PageToml(self.app, ResourceNames.of_app(self.app),
                                self.defaults, _encoding(self.app), self.texts[page])


class SourceFolderRunner:
    """Runs the code of one source folder's pages.

    Compiling is the slow part of a test, and many tests run the same page, so
    each page's compiled code is kept for the rest of the run, shared by every
    runner of the same folder. It is compiled again when a file it was
    compiled from has changed since.

    `pinyin_table`, a path or a PinyinTable (pinyin_table.py), is the
    screen's pinyin table, which the code's `pa_q` and `pa_txt` read. A test
    has none unless it gives one, so that its results do not depend on the
    computer. Raises NxwrightError for a path that holds no pinyin table.
    """

    def __init__(self, source_folder: Path, pinyin_table=None):
        self.source_folder = Path(source_folder).resolve()
        self.pinyin_table = pinyin_table_of(pinyin_table)
        # The fonts decoded for the list components' layouts, kept across runs.
        self._decoded_fonts = {}

    def compile(self, page: str, text: str = None, blank_fields: bool = False) -> tuple:
        """Returns ({(component, event): its Editor code lines}, {name: start value})
        for `page`, compiled from its .nx file or from `text` in its place.

        The start values are program.nx's `int` variables, at their declared
        value or 0; the generated variables, at 0 or ""; and `dp`, the current
        page's number. With `blank_fields`, every other `.val` or `.txt`
        attribute the code names starts at 0 or "" too. The result is shared:
        do not change it.

        The page's own code must name only what exists, as the build checks.
        Code given as `text` is not checked: it is run, never built, and may be
        an older version naming components the page no longer has.
        """
        compiled = self.runnable_page(page, text, blank_fields)
        return compiled.code, compiled.start

    def folder_page_tables(self) -> FolderPageTables:
        """Returns the folder's FolderPageTables, read again only once one of
        its files has changed. Raises NxwrightError for one of them that is
        missing or cannot be parsed, as a compile does."""
        return _cached(("tables", self.source_folder), self.source_folder,
                       lambda read: _read_page_tables(self.source_folder, read))

    def macros(self) -> dict:
        """Returns the folder's macros as EditorMachine takes them: {name:
        (its Editor code lines, a Place or None per line)}, none when the
        folder has no macros.nx. They are compiled again only once a file
        they were compiled from has changed. Raises NxwrightError as the
        build does for them."""
        tables = self.folder_page_tables()
        return _cached(("macros", self.source_folder), self.source_folder,
                       lambda read: _compile_macros(tables, read), tables)

    def runnable_page(self, page: str, text: str = None,
                      blank_fields: bool = False) -> RunnablePage:
        """Returns `page` compiled as `compile` compiles it, with what the
        simulator and the debugger's recording need too: a RunnablePage.
        The result is shared: do not change it."""
        tables = self.folder_page_tables()
        return _cached(("page", self.source_folder, page, text, blank_fields), self.source_folder,
                       lambda read: _compile_page(self.source_folder, tables, read, page, text,
                                                  blank_fields), tables)

    def run(self, page: str, events: list, values: dict = None, text: str = None,
            blank_fields: bool = False) -> dict:
        """Runs the `events` of `page`, a list of (component, event), in turn, and
        returns the values they leave. They start from the start values of
        `compile`, updated with `values`. `text` and `blank_fields` are as for
        `compile`. Refuses an event that has no code.

        Texts keep at most their limits, from the page files: a `txt` its
        `txt_maxl` bytes, a `path` its `path_m`, and so on. A "text limits" in
        `values`, {"name.attribute": the most bytes it keeps}, adds to them:
        the sizes of texts the page files no longer hold, which an older
        `text` uses."""
        compiled = self.runnable_page(page, text, blank_fields)
        for key in events:
            if key not in compiled.code:
                raise NxwrightError("page %s has no event %s.%s with code" % (page, *key))
        title = "%s: %s" % (page, ", ".join("%s.%s" % key for key in events))
        return self._run_recorded(compiled, page, events, values, title)

    def _run_recorded(self, compiled: RunnablePage, page: str, events: list, values: dict,
                      title: str) -> dict:
        """Runs `events` of a compiled page, from its start values updated with
        `values`, and returns the values they leave. While recording is on
        (recording.py), the run is recorded under `title`."""
        recorder = current_recorder()
        # The page's objects in ID order, which code may name by their IDs; a
        # page run_code makes up has none but itself.
        tables = self.folder_page_tables()
        components = tables.names.get(page, [page])
        machine = EditorMachine(_with_values(compiled.start, values), compiled.code, page,
                                compiled.encoding, recorder, compiled.places,
                                macros=self.macros(), components=components,
                                resources=ResourceNames.of_app(tables.app),
                                pinyin_table=self.pinyin_table,
                                folder_resources=FolderResources(self.source_folder, tables.app,
                                                                 self._decoded_fonts),
                                page_values=compiled.page_values)
        # The page as it opened, then the values the test gives again, which
        # win, written as they are, not worked again.
        machine.open_page()
        machine.values.update({key: value for key, value in (values or {}).items()
                               if key != "text limits"})
        if recorder is None:
            for key in events:
                machine.run(compiled.code[key], compiled.places[key])
            return machine.values
        recorder.begin(title, str(self.source_folder), machine.values, compiled.local_names,
                       compiled.nxlang)
        try:
            for key in events:
                machine.run(compiled.code[key], compiled.places[key])
        except Exception as error:
            recorder.end(machine.values, "%s: %s" % (type(error).__name__, error))
            raise
        recorder.end(machine.values)
        return machine.values

    def run_code(self, code: str, values: dict = None, include: str = None) -> dict:
        """Runs nxlang `code` as the only event of a page of its own, and returns
        the values it leaves. The page includes the file `include` when given, a
        path relative to the pages folder such as "lib/units.nx". This tests a
        library's functions: `code` calls them, and its values show the results.

        The folder must use nxlang, since the Editor's own language has no
        functions or includes. program.nx's constants and `int` variables apply,
        and its variables start at their declared value or 0.
        """
        lines = [("include %s" % _quoted(include)) if include else "", "",
                 "on %s.%s:" % _CODE_EVENT]
        lines += ["  " + line for line in code.rstrip("\n").split("\n")]
        page_text = "\n".join(lines) + "\n"
        tables = self.folder_page_tables()
        compiled = _cached(("code", self.source_folder, page_text), self.source_folder,
                           lambda read: _compile_code(self.source_folder, tables, read, page_text),
                           tables)
        return self._run_recorded(compiled, _CODE_PAGE, [_CODE_EVENT], values,
                                  "run_code: " + code.strip().split("\n")[0])

    def events_from_text(self, text: str, file_name: str = "page.nx") -> dict:
        """Returns {(component, event): its Editor code lines} for the events
        of a .nx text in the Editor's own language, such as a copy of a page
        kept from before it moved to nxlang. Its `@pic(...)` and `@font(...)`
        become the folder's IDs. `file_name` names the text in errors."""
        app = _app(self.source_folder)
        names = ResourceNames.of_app(app)
        return {key: preprocess(block.code_lines(), names)
                for key, block in event_blocks(text, file_name).items()}


def _cached(key: tuple, source_folder: Path, compile_from, made_from=None):
    """Returns compile_from(read)'s result, reusing the one kept under `key`
    while none of the files it read has changed. `read(path)` returns the text
    of a file of the folder and notes its path.

    `made_from`, when given, is another result of _cached that compile_from
    works from, such as the folder's FolderPageTables. Its files are noted
    under its own key, not read through `read`. So a result kept is reused
    only while `made_from` is the very one it was made from."""
    kept = _COMPILED.get(key)
    if kept is not None and kept[3] is made_from and _stamp(source_folder, kept[0]) == kept[1]:
        return kept[2]
    # app.toml is read directly, not through `read`, so it is noted here: a change
    # to it compiles again too.
    paths = ["app.toml"]
    read_file = folders.folder_reader(source_folder)

    def read(path: str) -> str:
        paths.append(path)
        return read_file(path)

    result = compile_from(read)
    _COMPILED[key] = (tuple(paths), _stamp(source_folder, paths), result, made_from)
    return result


def _stamp(source_folder: Path, paths) -> tuple:
    """Returns (path, modification time, size) for each of `paths`, with None
    for a missing file. It changes whenever one of the files does."""
    stamp = []
    for path in paths:
        try:
            status = (source_folder / path).stat()
        except FileNotFoundError:
            stamp.append((path, None, None))
        else:
            stamp.append((path, status.st_mtime_ns, status.st_size))
    return tuple(stamp)


def _app(source_folder: Path) -> dict:
    """Returns the folder's app.toml, parsed and checked."""
    return folders.parse_app(folders.read_text(source_folder / "app.toml"))


def _encoding(app: dict) -> str:
    """Returns the character encoding of a folder's parsed app.toml, the
    Editor's default when it gives none."""
    return app.get("encoding", DEFAULT_ENCODING)


def _quoted(path: str) -> str:
    """Returns `path` in quotation marks, for an include line."""
    if '"' in path:
        raise NxwrightError("an include path cannot hold a quotation mark: %r" % path)
    return '"%s"' % path


def _read_page_tables(source_folder: Path, read) -> FolderPageTables:
    """Returns the folder's FolderPageTables, reading defaults.toml and the
    page files through `read`. Raises NxwrightError for a file that is
    missing or cannot be parsed."""
    app = _app(source_folder)
    defaults = defaults_from_toml(read("defaults.toml"), "defaults.toml")
    texts, names, types, globals_, text_limits, system_pages = {}, {}, {}, {}, {}, {}
    absent_attributes = {}
    screen = screen_model(app)
    for page in app["pages"]:
        texts[page] = read(page_toml_path(page))
        data = folders.parsed_page_toml(texts[page], page)
        names[page] = folders.names_in_page_data(data)
        page_table = data.get("page", {})
        types[page] = table_types([page_table] + data.get("component", []))
        globals_[page] = folders.global_names_in_page_data(data, defaults)
        absent_attributes[page] = folders.absent_attributes_in_page_data(data, defaults,
                                                                          screen)
        text_limits[page] = table_limits([page_table] + data.get("component", []), defaults)
        system_pages[page] = page_table.get("system_page")
    return FolderPageTables(app, defaults, texts, names, types, globals_, text_limits,
                            system_pages, absent_attributes)


def _compile_page(source_folder: Path, tables: FolderPageTables, read, page: str, text: str,
                  blank_fields: bool) -> RunnablePage:
    """Does the work of SourceFolderRunner.compile, from the folder's
    FolderPageTables and its other files, read through `read`, and returns
    the page, a RunnablePage."""
    app = tables.app
    names = ResourceNames.of_app(app)
    if page not in app["pages"]:
        raise NxwrightError("%s has no page %s" % (source_folder, page))
    events_text = read(page_nx_path(page)) if text is None else text
    # As in the build, the page's own code may name only components that exist,
    # and use nothing its screen's series lacks.
    in_order = tables.names
    page_objects = dict(tables.types)
    checked = text is None
    screen = screen_model(app) if checked else None
    generated = []
    start = _program_start(read)
    if app["language"] == folders.NXLANG:
        program = folders.program_names(read("program.nx"), read)
        compiled = compile_nxlang_page(events_text, page, in_order[page], program, read=read,
                                       object_types=page_objects)
        generated = compiled.generated
        objects = None
        if checked:
            own = frozenset(page_objects[page]) | {variable.name
                                                   for variable in compiled.generated}
            objects = ObjectNames(own, page_objects, page,
                                  absent_attributes=tables.absent_attributes)
        placed = {}
        for key, lines in compiled.events.items():
            try:
                placed[key] = preprocess_with_places(lines, names, objects, screen=screen)
            except NxwrightError as error:
                # Its file named, as the build names it.
                raise error.in_file(file_at_fault(compiled, key, page, names, objects,
                                                  screen)) from None
        places = _nxlang_places(compiled, placed)
        local_names = compiled.local_names
        code = {key: [text for _, text in lines] for key, lines in placed.items()}
    else:
        objects = ObjectNames(frozenset(page_objects[page]), page_objects, page,
                              absent_attributes=tables.absent_attributes) if checked else None
        # As in the build, sys0 to sys2 only as program.nx declares them, and
        # a call only of a macro the folder has.
        variables = program_int_variables(read("program.nx")) if checked else None
        macros = callable_macros(read_macros_text(read)) if checked else None
        path = page_nx_path(page)
        blocks = event_blocks(events_text, path)
        owners = {key: Owner.among(key[0], in_order[page]) for key in blocks}
        placed = {}
        for key, block in blocks.items():
            try:
                placed[key] = preprocess_with_places(block.code_lines(), names, objects,
                                                     variables, macros, screen, owners[key])
            except NxwrightError as error:
                raise error.in_file(path) from None
        places = {key: [Place(path, number, "%s.%s" % key) for number, _ in lines]
                  for key, lines in placed.items()}
        local_names = {}
        # The screen runs an event's code as the Editor read it, its own
        # attributes written '&name&' replaced.
        code = {key: [with_own_attributes(text, owners[key]) if owners[key] else text
                      for _, text in lines]
                for key, lines in placed.items()}
    if app["language"] == folders.NXLANG:
        _add_hidden_variables(start, code.values())
    if blank_fields:
        for lines in code.values():
            for line in lines:
                line = split_line(line, 0)[1]
                for name in re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*"
                                       r"\.(?:val|txt)\b", line):
                    start.setdefault(name, "" if name.endswith(".txt") else 0)
    # dp is the current page's number. On the screen, a page's own .id does not
    # give it, so code must read dp. <page>.id starts at 99 here, a deliberately
    # wrong value.
    start["dp"] = app["pages"].index(page)
    start["%s.id" % page] = 99
    start["text limits"] = _text_limits(tables, page, generated)
    components = folders.page_toml_components(tables.page_toml(page), page)
    return RunnablePage(code, start, places, local_names, _encoding(app),
                        app["language"] == folders.NXLANG, components,
                        component_start_values(components, screen_model(app)))


def _compile_macros(tables: FolderPageTables, read) -> dict:
    """Does the work of SourceFolderRunner.macros, from the folder's
    FolderPageTables and its other files, read through `read`. They are
    checked as the build checks them."""
    text = read_macros_text(read)
    if text is None:
        return {}
    compiled = compiled_macros(text, ResourceNames.of_app(tables.app), tables.types,
                               tables.globals, program_int_variables(read("program.nx")),
                               tables.absent_attributes, screen_model(tables.app))
    return {name: ([line for _, line in lines],
                   [Place(MACROS_PATH, number, "macro " + name) if number else None
                    for number, _ in lines])
            for name, lines in compiled.items()}


def _nxlang_places(compiled, placed: dict) -> dict:
    """Returns {key: a Place or None per line} of a compiled page's events in
    nxlang, `placed` giving each Editor line's source line. An event's lines
    come from the file defining it. A function hotspot's event holds the
    bodies of its functions, each after a comment line naming the function,
    which tells whose body a line belongs to; the dispatching around each
    body has the function's heading line, and no place."""
    places = {}
    for key, lines in placed.items():
        if key in compiled.sources:
            places[key] = [Place(compiled.sources[key], number, "%s.%s" % key) if number else None
                           for number, _ in lines]
            continue
        headings = {"// " + function.signature: function for function in compiled.functions.values()
                    if function.hotspot == key[0]}
        function, places[key] = None, []
        for number, text in lines:
            function = headings.get(text.strip(), function)
            inside = function is not None and number and number != function.number
            places[key].append(Place(function.file, number, function.name) if inside else None)
    return places


def _compile_code(source_folder: Path, tables: FolderPageTables, read,
                  page_text: str) -> RunnablePage:
    """Returns the RunnablePage of the code for SourceFolderRunner.run_code, from the
    folder's FolderPageTables and its other files, read through `read`.
    Refuses a folder that does not use nxlang."""
    app = tables.app
    if app["language"] != folders.NXLANG:
        raise NxwrightError("%s does not use nxlang, so it has no functions to run"
                            % source_folder)
    program = folders.program_names(read("program.nx"), read)
    # Its code runs in no object's event, so the form '&name&' stays refused.
    compiled = compile_nxlang_page(page_text, _CODE_PAGE, [_CODE_PAGE], program, read=read,
                                   own_attributes=False)
    names = ResourceNames.of_app(app)
    placed = {key: preprocess_with_places(lines, names) for key, lines in compiled.events.items()}
    places = _nxlang_places(compiled, placed)
    # The code's own lines are of a page made up for it, with no file.
    places[_CODE_EVENT] = [None] * len(placed[_CODE_EVENT])
    code = {key: [text for _, text in lines] for key, lines in placed.items()}
    start = _program_start(read)
    _add_hidden_variables(start, code.values())
    start["text limits"] = _text_limits(tables, _CODE_PAGE, compiled.generated)
    return RunnablePage(code, start, places, compiled.local_names, _encoding(app), True)


def _with_values(start: dict, values: dict) -> dict:
    """Returns `start` updated with `values`, whose "text limits" adds to the
    start's rather than replacing them."""
    given = dict(values or {})
    limits = dict(start["text limits"], **given.pop("text limits", {}))
    return dict(start, **given, **{"text limits": limits})


def _text_limits(tables: FolderPageTables, page: str, generated: list) -> dict:
    """Returns {"name.attribute": the most bytes it keeps} of every bounded
    text of the app (table_limits), named as the code of `page` names it:
    the page's own alone, another page's after that page's name. `generated`
    holds the page's generated variables, which the build adds to it."""
    limits = {}
    for page_name in tables.app["pages"]:
        own = tables.text_limits[page_name]
        if page_name == page:
            own = {**own, **table_limits([generated_table(variable) for variable in generated],
                                          tables.defaults)}
        prefix = "" if page_name == page else page_name + "."
        limits.update((prefix + name, limit) for name, limit in own.items())
    return limits


def component_start_values(components: list, screen) -> dict:
    """Returns the values of a page's Components, as its page file and their
    defaults give them, named as code names them ("t0.txt"), `type` as the
    type's number, which code reads. An attribute a component lacks, as a
    variable holding a number its `txt`, or `movex` on a Basic screen, is
    none of its values: the screen `screen` has no such name."""
    start = {}
    for component in components:
        lacked = lacked_attributes(component.type, component.values.get, screen)
        start.update({"%s.%s" % (component.name, attribute): value
                      for attribute, value in component.values.items()
                      if attribute not in lacked})
        start["%s.type" % component.name] = TYPES_BY_NAME.get(
            component.type, int(component.type) if component.type.isdigit() else 0)
    return start


def table_limits(toml_tables: list, defaults: dict) -> dict:
    """Returns {"name.attribute": the most bytes it keeps} of a page file's
    `toml_tables` that have a name: a `txt`'s `txt_maxl`, and each `X`'s
    `X_m`, as a `path`'s `path_m` (editor_limits.bounded_attributes). Each
    limit is the table's own, or else its type's, from `defaults`."""
    limits = {}
    for table in toml_tables:
        if "name" not in table:
            continue
        object_type = TYPES_BY_NAME.get(table.get("type"))
        type_defaults = defaults.get(object_type)
        stored = dict(type_defaults.attributes) if type_defaults is not None else {}
        for attribute, bound in bounded_attributes(object_type, {*table, *stored}):
            limit = table.get(bound)
            if limit is None and bound in stored:
                limit = int.from_bytes(stored[bound], "little")
            if isinstance(limit, int):
                limits["%s.%s" % (table["name"], attribute)] = limit
    return limits


def _program_start(read) -> dict:
    """Returns program.nx's `int` variables, at the value each declares, or 0. Only
    program.nx itself declares them: the files it includes hold constants."""
    start = {}
    # A tab after `int` declares in nxlang, which writes it as a space.
    for declaration in re.findall(r"^int[ \t]+(.*)$", read("program.nx"), re.M):
        for name, value in re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\s*(?:=\s*(-?[0-9]+))?",
                                      split_line(declaration, 0)[1]):
            start[name] = int(value) if value else 0
    return start


# A generated variable that compiled code names: a global, or a generated
# component's `val` or `txt`.
_HIDDEN_VARIABLE = re.compile(r"(?<![\w.])(?:%s|(?:%s)\.(?:val|txt))\b"
                              % (GENERATED_GLOBAL.pattern, GENERATED_NAME.pattern))


def _add_hidden_variables(start: dict, events):
    """Sets each generated variable that `events`, compiled from nxlang, name
    to 0 or "" in `start`, as the Editor creates them."""
    for lines in events:
        for line in lines:
            for found in _HIDDEN_VARIABLE.finditer(line):
                start[found[0]] = "" if found[0].endswith(".txt") else 0
