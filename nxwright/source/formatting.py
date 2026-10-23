"""Formatting a source folder's .nx files (formatter.py), checked
so that it never changes what the code does.

A file is formatted only if every page using it, and program.nx when the
file is one of its own, build to the same Editor code after formatting as
before, apart from spaces and tabs at the start and end of lines. The build
copies a line's indentation into the project, so that may change; nothing
else may. Code that does not build is not formatted, since the check cannot
run. A file that neither a page nor program.nx uses builds into no project,
so it is formatted with nothing to check.

macros.nx is Editor code in either language, laid out as such
(formatter.format_macros), and formatted only if each of its macros builds
to the same Editor code as before, alike apart from those spaces.
"""
from nxwright import NxwrightError
from nxwright.project.page_block import Event
from nxwright.source.formatter import format_code, format_macros
from nxwright.source.macros_source import MACROS_PATH
from nxwright.source.source_folder import NXLANG, code_files, read_folder_source


def format_folder(read, only: list = None) -> dict:
    """Returns {path: new text} of the .nx files of a source folder whose
    layout formatting changes, `read(path)` returning its files' text. With
    `only`, only those files are formatted.

    Raises NxwrightError, naming the cause, when the folder does not build,
    or when the formatted files would build to other Editor code."""
    folder = _built(read, "the folder does not build, so formatting cannot be checked")
    files = code_files(folder.app, read)
    program_files = files.pop(None)
    every_file = list(dict.fromkeys(program_files + [path for paths in files.values()
                                                     for path in paths]))
    if folder.macros_text is not None:
        every_file.append(MACROS_PATH)
    changed = {}
    for path in every_file if only is None else only:
        text = read(path)
        try:
            if path == MACROS_PATH:
                formatted = format_macros(text)
            else:
                formatted = format_code(text, folder.app["language"] == NXLANG,
                                        program=path == "program.nx")
        except NxwrightError as error:
            raise NxwrightError("%s cannot be formatted: %s" % (path, error)) from None
        if formatted != text:
            changed[path] = formatted
    if not changed:
        return {}
    every_page = any(path in program_files for path in changed)
    pages = [page for page, paths in files.items()
             if every_page or any(path in changed for path in paths)]

    def read_formatted(path: str) -> str:
        return changed[path] if path in changed else read(path)
    with_macros = MACROS_PATH in changed
    before = _editor_code(folder, pages, every_page, with_macros, "the folder does not build")
    failure = "the formatted files would not build"
    after = _editor_code(_built(read_formatted, failure), pages, every_page, with_macros,
                         failure)
    # A macro is named by the file, so one could be lost or gained.
    for name in list(before) + [name for name in after if name not in before]:
        if before.get(name) != after.get(name):
            old, new = before.get(name, []), after.get(name, [])
            first = next((n for n, (a, b) in enumerate(zip(old, new)) if a != b),
                         min(len(old), len(new)))
            line = old[first] if first < len(old) else new[first]
            raise NxwrightError("formatting would change the code in strict Nextion syntax "
                                "that %s builds to, at %r"
                                % (name, line.decode("latin-1")
                                   if isinstance(line, bytes) else line))
    return changed


def _built(read, failure: str):
    """Returns the FolderSource read through `read`, raising NxwrightError
    that starts with `failure` when it cannot be read."""
    try:
        return read_folder_source(read)
    except NxwrightError as error:
        raise NxwrightError("%s: %s" % (failure, error)) from None


def _editor_code(folder, pages: list, with_program: bool, with_macros: bool,
                 failure: str) -> dict:
    """Returns {page, "program.nx", or "macro <name>": its built code, as
    lines stripped of spaces and tabs at their start and end}. A page's lines
    are its objects' records in order, each event's code after a line naming
    its object and event, so that any other change of the page shows too.
    A macro's are its Editor code, without the lines of macros.nx they come
    from. Raises NxwrightError that starts with `failure` when a page or a
    macro does not build."""
    stripped = {}
    globals_used = []
    try:
        for page_id, page in enumerate(folder.app["pages"]):
            if page in pages:
                block = folder.build_page(page_id, globals_used)
                stripped[page] = [line for index, page_object in enumerate(block.objects)
                                  for line in _object_lines(index, page_object)]
        if with_program:
            stripped["program.nx"] = [line.strip(b" \t")
                                      for line in folder.build_program().split(b"\r\n")]
        if with_macros:
            for name, lines in folder.compiled_macros().items():
                stripped["macro " + name] = [line.strip(" \t") for _, line in lines]
    except NxwrightError as error:
        raise NxwrightError("%s: %s" % (failure, error)) from None
    return stripped


def _object_lines(index: int, page_object) -> list:
    """Returns an object's records as lines of bytes: an event's code lines
    stripped of spaces and tabs at their ends, any other record as it is."""
    lines = []
    for item in page_object.items:
        if isinstance(item, Event):
            lines.append(b"object %d, event %s:" % (index, item.name.encode("latin-1")))
            lines += [line.strip(b" \t") for line in item.lines]
        else:
            lines.append(repr(item).encode("latin-1", "replace"))
    return lines
