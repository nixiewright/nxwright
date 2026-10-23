"""Warnings about a source folder's code and files that the build accepts,
but that are likely mistakes. Each has a rule's name:
  - left-to-right, in a folder in the Editor's own language: a line the
    Editor computes otherwise than the usual order of operations, as
    `sys0=a+b*c`, which the Editor computes as `(a+b)*c`. The warning shows
    the Editor's meaning with parentheses, as `nxwright language` would
    write the line.
  - unused-constant, in nxlang: a constant of a page's own .nx file, or of
    program.nx, that no code of the folder uses. Constants of other included
    files are left alone, since a library serves many pages.
  - unused-function, in nxlang: a function of a page's own .nx file that the
    page's code never calls. The build checks such a function, then leaves it
    out of the project.
  - number-past-32-bits, in nxlang: a hex number too large for 32 bits,
    such as 0x0100000005. The build keeps its low 32 bits, 0x00000005, as
    C does, and as a C compiler, warns.
  - sound-file-form: a sound's file without the `hmic` chunk the Editor's
    Audio panel writes, or whose check value there does not match its
    samples (media_files.sound_file_problem), on app.toml's line naming
    the sound. The Editor itself takes such a file, but the screen's chip
    may check the value, which no screen has been seen to do yet.
    `nxwright sound` writes the chunk and its check value.
  - event-never-runs, in either language: an event of a page's .nx files
    that its component's type does not have, such as a page's `postinit`,
    on its heading line, in nxlang in an included file too. The Editor
    keeps its code, but the screen never runs it: the Editor's simulator
    never ran a page's `postinit`. A type's events are those of nxwright's
    own component defaults, not the folder's copy, which can be edited.
A file the build would refuse gets no warnings: its errors come first.

Two rules find an error the build refuses too, which the checks show
without building, each on app.toml's line naming the file's resource:
video-rotation, a video made for another rotation than the folder's
screen, which the Editor refuses to compile
(source_folder.video_rotation_problem); and picture-unreadable, a picture
nxwright cannot read, found by opening its file without decoding its pixels
(pictures.picture_problem).
"""
from dataclasses import dataclass, field
import tomllib

from nxwright import NxwrightError, listed_in_words
from nxwright.language.code_lines import split_line
from nxwright.language.editor_code import hex_written_0x, keep_editor_meaning
from nxwright.language.nxlang import editor_number, is_constant_line, token_spans
from nxwright.project.component_defaults import nxwright_defaults
from nxwright.project.media_files import VIDEO_HEAD_SIZE, sound_file_problem
from nxwright.project.object_types import TYPE_NAMES, TYPES_BY_NAME
from nxwright.project.pictures import picture_problem
from nxwright.source.nx_files import (EVENT_HEADING, FUNCTION_HEADING, event_blocks, read_nx_file,
                                      read_page_files)
from nxwright.source.page_source import page_nx_path, page_toml_path
from nxwright.source.source_folder import (check_picture_file, code_files, picture_file,
                                           types_in_page_data, video_rotation_problem)

ERROR, WARNING = "error", "warning"

# The Editor's event pane names a page's load and loadend so; their own
# names are easy to take for the events' names.
_EVENT_PANE_NAMES = {"preinit": ("Preinitialize Event", "load"),
                     "postinit": ("Postinitialize Event", "loadend")}


@dataclass(frozen=True)
class Finding:
    """A problem found in a source folder: an error the build refuses, or a
    warning. `line` counts from 1, and is 0 when the problem has no line."""
    file: str           # the file's path within the folder
    line: int
    severity: str       # ERROR or WARNING
    message: str
    rule: str = ""      # a warning's rule, such as "unused-constant"
    # An error's one sure fix, as its NxwrightError gives it, which a code
    # editor offers; not part of what the finding is.
    fix: dict = field(default=None, compare=False)

    @property
    def place(self) -> str:
        """Where it is, as messages name it: "pages/home.nx line 3", or the
        file alone when the problem has no line."""
        return "%s line %d" % (self.file, self.line) if self.line else self.file


def warnings(app: dict, read) -> list:
    """Returns the warning Findings of the folder whose settings are `app`
    and whose files `read(path)` returns."""
    if app["language"] == "nxlang":
        return (_unused_constants(app, read) + _unused_functions(app, read)
                + _numbers_past_32_bits(app, read) + _events_never_run(app, read))
    return _left_to_right(app, read) + _events_never_run(app, read)


def sound_warnings(app: dict, read, read_bytes) -> list:
    """Returns the sound-file-form warning Findings of the folder whose
    settings are `app`, whose files' text `read(path)` returns, and their
    bytes `read_bytes(path)`."""
    found = []
    for name in app["sounds"]:
        path = "sounds/%s.wav" % name
        try:
            problem = sound_file_problem(read_bytes(path))
        except (OSError, NxwrightError):
            continue    # the check reports a missing file
        if problem:
            found.append(Finding("app.toml", line_naming(read("app.toml"), name), WARNING,
                                 "%s: %s; the Nextion Editor's Audio panel writes the chunk with "
                                 "the samples' check value, and `nxwright sound` makes the file "
                                 "as it does" % (path, problem), "sound-file-form"))
    return found


def video_rotation_errors(app: dict, read, read_bytes) -> list:
    """Returns the video-rotation error Findings of the folder whose
    settings are `app`, whose files' text `read(path)` returns, and their
    first bytes `read_bytes(path, size)`: a video made for another rotation
    than the folder's screen (source_folder.video_rotation_problem). Only a
    video's first bytes are read, as videos can be large."""
    found = []
    for name in app["videos"]:
        path = "videos/%s.video" % name
        try:
            problem = video_rotation_problem(app, read_bytes(path, VIDEO_HEAD_SIZE))
        except OSError:
            continue    # the check reports a missing file
        if problem:
            found.append(Finding("app.toml", line_naming(read("app.toml"), name), ERROR,
                                 "%s %s" % (path, problem), "video-rotation"))
    return found


def picture_errors(app: dict, read, read_bytes, exists) -> list:
    """Returns the error Findings of the pictures nxwright cannot read, of
    the folder whose settings are `app`, whose files' text `read(path)`
    returns, and their bytes `read_bytes(path)`: each opened without its
    pixels decoded, as the build would refuse it (pictures.picture_problem).
    A picture with no file, or more than one, which the checks report
    already (source_folder.check_picture_file), is not read."""
    found = []
    for name in app["pictures"]:
        try:
            check_picture_file(name, exists)
            path = picture_file(name, exists)
            problem = picture_problem(read_bytes(path))
        except (OSError, NxwrightError):
            continue    # the check reports a missing file
        if problem:
            found.append(Finding("app.toml", line_naming(read("app.toml"), name), ERROR,
                                 "%s: %s" % (path, problem), "picture-unreadable"))
    return found


def line_naming(text: str, name: str) -> int:
    """Returns the line, from 1, of app.toml naming `name` in quotation marks, or 0."""
    for number, line in enumerate(text.split("\n"), start=1):
        if '"%s"' % name in line:
            return number
    return 0


def _left_to_right(app: dict, read) -> list:
    found = []
    files = [page_nx_path(page) for page in app["pages"]]
    for path in files + ["program.nx"]:
        try:
            text = read(path)
            if path == "program.nx":
                groups = [list(enumerate(text.split("\n"), start=1))]
            else:
                groups = [block.code_lines() for block in event_blocks(text, path).values()]
            for lines in groups:
                # A hex number written 0X computes the same once written 0x.
                lines = hex_written_0x(lines)
                for (number, written), (_, rewritten) in zip(lines, keep_editor_meaning(lines)):
                    if rewritten != written:
                        # The code alone, without the line's comment.
                        code = split_line(rewritten, number)[1]
                        found.append(Finding(path, number, WARNING,
                                             "the Nextion Editor computes this from left to "
                                             "right, as %s" % code, "left-to-right"))
        except NxwrightError:
            continue    # the build reports what it cannot read
    return found


def _events_never_run(app: dict, read) -> list:
    """Returns the event-never-runs warning Findings: each event of a page's
    .nx files that its component's type does not have. In nxlang, they are
    the page's own file and those it includes; an event in a file two pages
    include is warned of once."""
    found = []
    defaults = nxwright_defaults()
    for page in app["pages"]:
        path = page_nx_path(page)
        try:
            types = types_in_page_data(tomllib.loads(read(page_toml_path(page))))
            if app["language"] == "nxlang":
                homes = read_page_files(path, read(path), read).homes
                blocks = [(key, home.path, home.blocks[key]) for key, home in homes.items()]
            else:
                blocks = [(key, path, block)
                          for key, block in event_blocks(read(path), path).items()]
        except (NxwrightError, tomllib.TOMLDecodeError):
            continue    # the build reports what it cannot read
        for (name, event), file, block in blocks:
            if name is None:
                continue    # an nxlang function, not an event
            object_type = types.get(name)
            if isinstance(object_type, str):
                object_type = TYPES_BY_NAME.get(object_type)
            # A type that is not a plain number or name is the build's to report.
            if not isinstance(object_type, int) or object_type not in defaults or \
                    event in defaults[object_type].events:
                continue
            events = defaults[object_type].events
            message = "%s, of type %s, has no %s event, so the screen never runs this code; %s" % (
                name, TYPE_NAMES[object_type], event,
                "its events are %s" % listed_in_words(events) if events else "it has no events")
            pane_name, meant = _EVENT_PANE_NAMES.get(event, (None, None))
            if meant in events:
                message += ". The Nextion Editor's %s is %s" % (pane_name, meant)
            finding = Finding(file, block.number, WARNING, message, "event-never-runs")
            if finding not in found:
                found.append(finding)
    return found


def _names_used(path: str, text: str) -> list:
    """Returns (line, name, followed by "(") for each name the code of a .nx
    file uses, leaving out the names a heading or a `const` line defines."""
    used = []
    for number, line in enumerate(text.split("\n"), start=1):
        if EVENT_HEADING.fullmatch(line) or FUNCTION_HEADING.fullmatch(line):
            continue
        try:
            code = split_line(line, number)[1]
        except NxwrightError:
            continue
        tokens = token_spans(code)
        start = 2 if is_constant_line(code) else 0     # `const NAME` defines NAME
        for position in range(start, len(tokens)):
            kind, name = tokens[position][:2]
            after_dot = position > 0 and tokens[position - 1][1] == "."
            if kind == "name" and not after_dot:
                calls = position + 1 < len(tokens) and tokens[position + 1][1] == "("
                used.append((number, name, calls))
    return used


def _own_definitions(path: str, text: str, constants: bool) -> list:
    """Returns (line, name) of each constant, or each function, that the .nx
    file `path` defines."""
    if constants and path == "program.nx":
        lines = list(enumerate(text.split("\n"), start=1))     # constants go anywhere there
    else:
        nx_file = read_nx_file(path, text)
        if not constants:
            return [(block.number, key[1]) for key, block in nx_file.blocks.items()
                    if key[0] is None]
        lines = nx_file.preamble
    found = []
    for number, line in lines:
        code = split_line(line, number)[1]
        tokens = token_spans(code)
        if is_constant_line(code) and len(tokens) > 1:
            found.append((number, tokens[1][1]))
    return found


def _unused_constants(app: dict, read) -> list:
    files = code_files(app, read)
    every_file = list(dict.fromkeys(path for paths in files.values() for path in paths))
    used = set()
    for path in every_file:
        used.update(name for _, name, _ in _names_used(path, read(path)))
    found = []
    for path in [page_nx_path(page) for page in files if page] + ["program.nx"]:
        try:
            defined = _own_definitions(path, read(path), constants=True)
        except NxwrightError:
            continue
        found += [Finding(path, number, WARNING, "constant %s is not used" % name,
                          "unused-constant")
                  for number, name in defined if name not in used]
    return found


def _numbers_past_32_bits(app: dict, read) -> list:
    files = code_files(app, read)
    found = []
    for path in dict.fromkeys(path for paths in files.values() for path in paths):
        try:
            lines = read(path).split("\n")
        except NxwrightError:
            continue
        for number, line in enumerate(lines, start=1):
            try:
                code = split_line(line, number)[1]
            except NxwrightError:
                continue    # the build reports a line it cannot read
            found += [Finding(path, number, WARNING,
                              "%s does not fit in 32 bits: its low 32 bits are kept, %s"
                              % (written, editor_number(written)), "number-past-32-bits")
                      for kind, written, _, _ in token_spans(code)
                      if kind == "number" and written.startswith("0x")
                      and int(written, 16) > 0xFFFFFFFF]
    return found


def _unused_functions(app: dict, read) -> list:
    files = code_files(app, read)
    found = []
    for page, paths in files.items():
        if page is None:
            continue
        called = {name for path in paths for _, name, calls in _names_used(path, read(path))
                  if calls}
        path = page_nx_path(page)
        try:
            defined = _own_definitions(path, read(path), constants=False)
        except NxwrightError:
            continue
        found += [Finding(path, number, WARNING,
                          "function %s is never called on page %s" % (name, page),
                          "unused-function")
                  for number, name in defined if name not in called]
    return found
