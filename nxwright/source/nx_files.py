"""A page's .nx files: its own, and in nxlang, the files it includes; and
the folder's macros.nx, read alike (macros_source.py).

A .nx file holds blocks under headings: an event, `on <object>.<event>:`, or
in nxlang a function, `function <name>(...)`; in macros.nx, a macro,
`macro <name>:`. Their code lines are indented
by two spaces. In nxlang, the lines before the first heading are the file's
preamble: `include "<path>"` lines and constants.

Comment lines starting at the start of the line, right above a heading,
are that event's comment. The Editor keeps comments only inside code. So the
build puts them first in the event, each marked with EVENT_COMMENT_MARKER,
and extracting moves them back. A function's comment stays in the source.

A comment that a blank line parts from what follows, where a heading,
another such comment, or the file's end follows, is above no heading: one
sorting a file into sections, say. It has no event to go into, so it stays
in the source. The block after it holds it (EventBlock.detached), and the
file's end what no block follows, so that a file written again from its
blocks keeps it. A comment at the start of a line followed by more of a
block's code is refused: it may have been meant as code.

An include's path is relative to the file holding it, ends in `.nx`, and
stays inside the source folder. A page reads its own file and every file it
includes, directly or not, each once. Every event and function is defined
in exactly one of them.

Code added at the end of a .nx file comes after one blank line
(with_code_added).
"""
from dataclasses import dataclass, field
import posixpath
import re

from nxwright import NxwrightError
from nxwright.language.code_lines import split_line

CODE_INDENT = "  "
# How the build writes an event comment's `//` inside the event, so that
# extracting can tell the comment from the code's own comments.
EVENT_COMMENT_MARKER = "// ###"
# The heading of an event: `on save.up:` gives the object and the event.
EVENT_HEADING = re.compile(r"on ([A-Za-z0-9_]+)\.([a-z]+):")
# The heading of a function in nxlang; nxlang.py reads the rest of the line.
FUNCTION_HEADING = re.compile(r"function\s+([A-Za-z_][A-Za-z0-9_]*)\b.*")
# The heading of a macro, in macros.nx; macros_source.py checks the name.
MACRO_HEADING = re.compile(r"macro (.+):")
# The code of an include line, which gives the path as written.
INCLUDE = re.compile(r'include\s+"([^"]*)"')


@dataclass
class EventBlock:
    """One event's part of a .nx file, or a function's: the lines after its
    heading, up to the next heading, and the comment above it. `detached`
    holds the comment above no heading before that, with the blank lines
    among and after it, as written."""
    lines: list = field(default_factory=list)   # (line number, text), blank lines included
    heading: str = ""
    number: int = 0                             # the heading's line number
    comment: list = field(default_factory=list) # (line number, text) of the comment above it
    detached: list = field(default_factory=list)

    def marked_comment(self) -> list:
        """Returns the comment's lines as the build puts them in the event:
        `// Save` becomes `// ### Save`, without the spaces and tabs ending it,
        as the build drops them from every code line."""
        return [(EVENT_COMMENT_MARKER + text[2:]).rstrip(" \t") for _, text in self.comment]

    def code_lines(self) -> list:
        """Returns (line number, code without the indentation) for each non-blank line."""
        return [(number, text[len(CODE_INDENT):]) for number, text in self.lines if text.strip()]

    def text(self, heading: str = None) -> str:
        """Returns the block as written, under `heading` (else its own),
        without trailing blank lines."""
        lines = [text for _, text in self.lines]
        while lines and not lines[-1].strip():
            lines.pop()
        above = [text for _, text in self.detached + self.comment]
        return "\n".join(above + [heading or self.heading] + lines) + "\n"


def event_blocks(text: str, file_name: str, preamble: list = None, end: list = None) -> dict:
    """Returns {(object name, event): EventBlock} for a .nx file, in file
    order. With a `preamble` list, the file is in nxlang: the lines before the
    first heading are added to the list instead of being refused, and its
    functions are blocks keyed (None, name). The comment at the file's end,
    above no heading, is added to `end`, if given: what writes the file
    again from its blocks needs it."""
    def heading_of(line: str):
        event = EVENT_HEADING.fullmatch(line)
        if event:
            return event.groups(), "%s.%s" % event.groups()
        function = FUNCTION_HEADING.fullmatch(line) if preamble is not None else None
        if function:
            return (None, function[1]), "function " + function[1]
        return None
    return _blocks(text, file_name, heading_of, "an 'on <name>.<event>:' heading", preamble,
                   end)


def macro_blocks(text: str, file_name: str, end: list = None) -> dict:
    """Returns {macro name: EventBlock} for macros.nx, in file order; `end`,
    as event_blocks says."""
    def heading_of(line: str):
        macro = MACRO_HEADING.fullmatch(line)
        return (macro[1], "macro " + macro[1]) if macro else None
    return _blocks(text, file_name, heading_of, "a 'macro <name>:' heading", None, end)


def _blocks(text: str, file_name: str, heading_of, heading: str, preamble: list,
            end: list) -> dict:
    """Returns {key: EventBlock} for a file of blocks under headings, in file
    order. `heading_of(line)` returns (the block's key, its name in errors)
    for a heading line, else None. `heading` names the file's headings, in
    errors. `preamble` and `end`, as event_blocks says."""
    blocks, current, what = {}, None, None
    # The comment lines since the last other line, and before them, the
    # comment above no heading that waits for what follows.
    comment, detached = [], []
    for number, line in enumerate(text.split("\n"), start=1):
        found = heading_of(line)
        if found:
            key, what = found
            if key in blocks:
                raise NxwrightError("%s appears twice" % what, file=file_name, line=number)
            current = blocks[key] = EventBlock(heading=line, number=number, comment=list(comment),
                                               detached=list(detached))
            comment.clear()
            detached.clear()
        elif line.startswith("//"):
            comment.append((number, line))
        elif current is None and preamble is not None:
            # Before the first heading of a file in nxlang, every line is the
            # preamble's, the comments among them.
            preamble.extend(comment + [(number, line)])
            comment.clear()
        elif not line.strip():
            if comment or detached:
                detached.extend(comment + [(number, line)])
                comment.clear()
            elif current is not None:
                current.lines.append((number, line))
        elif current is not None and line.startswith(CODE_INDENT):
            if comment or detached:
                raise NxwrightError("a comment at the start of a line, inside the code of %s: "
                                    "indent it as its code, or move it right above a heading"
                                    % what, file=file_name, line=(detached or comment)[0][0])
            current.lines.append((number, line))
        else:
            raise NxwrightError("expected %s or a code line indented by two spaces" % heading,
                                file=file_name, line=number)
    if preamble is not None and current is None:
        preamble.extend(comment)
    elif end is not None:
        end.extend(detached + comment)
    return blocks


def with_end(blocks_text: str, end: list) -> str:
    """Returns the text of a .nx file's blocks, `blocks_text`, followed by
    the comment at its end (event_blocks), after one blank line."""
    lines = [text for _, text in end]
    while lines and not lines[-1].strip():
        lines.pop()
    if not lines:
        return blocks_text
    return (blocks_text + "\n" if blocks_text else "") + "\n".join(lines) + "\n"


@dataclass
class NxFile:
    """One .nx file in nxlang."""
    path: str           # relative to the source folder, with "/"
    preamble: list      # (line number, text) before the first heading, include lines left out
    blocks: dict        # {key: EventBlock}, in file order
    includes: list      # [(line number, path)] of the files it includes, as source folder paths
    head: list          # (line number, text) before the first heading, include lines kept
    end: list = field(default_factory=list)    # the comment at its end (event_blocks)


@dataclass
class PageFiles:
    """A page's .nx files: its own, and those it includes."""
    files: list         # [NxFile], each file after the files it includes
    homes: dict         # {key: the NxFile defining that event or function}

    def preambles(self) -> list:
        """Returns [(path, preamble)] of each file, in the order of `files`."""
        return [(nx_file.path, nx_file.preamble) for nx_file in self.files]


def included_path(text: str):
    """Returns the path an `include` line names, as written, or None for another line."""
    match = INCLUDE.fullmatch(split_line(text, 0)[1])
    return match[1] if match else None


def read_nx_file(path: str, text: str) -> NxFile:
    """Returns a .nx file in nxlang, read into its blocks, its includes, and
    its preamble without them.

    Raises NxwrightError for a line starting with `include` that is not
    `include "<path>"`, and for what event_blocks and resolve refuse.
    """
    preamble, end = [], []
    blocks = event_blocks(text, path, preamble, end)
    kept, includes = [], []
    for number, line in preamble:
        code = split_line(line, number)[1]
        match = INCLUDE.fullmatch(code)
        if match:
            includes.append((number, resolve(path, match[1], number)))
        elif code.startswith("include"):
            raise NxwrightError('an include is written include "<path>.nx"', file=path, line=number)
        else:
            kept.append((number, line))
    return NxFile(path, kept, blocks, includes, preamble, end)


def resolve(including: str, written: str, number: int) -> str:
    """Returns the source folder path of an include written in file `including`.

    Raises NxwrightError unless it is a relative path with "/", ending in .nx,
    that stays inside the source folder.
    """
    if not written.endswith(".nx"):
        raise NxwrightError("%s does not end in .nx" % written, file=including, line=number)
    if written.startswith("/") or "\\" in written or ":" in written:
        raise NxwrightError("%s must be a relative path with /"
                            % written, file=including, line=number)
    path = posixpath.normpath(posixpath.join(posixpath.dirname(including), written))
    if path == ".." or path.startswith("../"):
        raise NxwrightError("%s leaves the source folder" % written, file=including, line=number)
    return path


def read_page_files(page_path: str, page_text: str, read) -> PageFiles:
    """Reads a page's own .nx file and every file it includes. `read(path)`
    returns a file's text, raising NxwrightError when it is missing.

    Raises NxwrightError when two of the files define one event or function.
    """
    files, homes, seen = [], {}, set()

    def visit(nx_file: NxFile):
        seen.add(nx_file.path)
        for number, path in nx_file.includes:
            if path not in seen:
                try:
                    text = read(path)
                except NxwrightError as error:
                    raise NxwrightError(str(error), file=nx_file.path, line=number) from None
                visit(read_nx_file(path, text))
        files.append(nx_file)
        for key in nx_file.blocks:
            if key in homes:
                what = "function " + key[1] if key[0] is None else "%s.%s" % key
                raise NxwrightError("%s is also defined in %s" % (what, homes[key].path),
                                    file=nx_file.path, line=nx_file.blocks[key].number)
            homes[key] = nx_file
    visit(read_nx_file(page_path, page_text))
    return PageFiles(files, homes)


def render(nx_file: NxFile, blocks: dict) -> str:
    """Returns the text of `nx_file` with `blocks` in place of its own: the
    lines before its first heading as they were, then `blocks` in order,
    then the comment at its end."""
    lines = [text for _, text in nx_file.head]
    while lines and not lines[-1].strip():
        lines.pop()
    body = with_end("\n".join(block.text() for block in blocks.values()), nx_file.end)
    if not lines:
        return body
    return "\n".join(lines) + "\n" + ("\n" + body if body else "")


def blank_lines_dropped(where: str, count: int) -> str:
    """Returns the warning that extracting dropped `count` blank lines, of
    only spaces and tabs or of nothing, from the code that `where` names. The
    Nextion Editor 3.1.73 compiled such lines to nothing."""
    lines, them = ("line", "it") if count == 1 else ("lines", "them")
    return "%s: %d blank %s dropped; the Nextion Editor compiles %s to nothing" % (
        where, count, lines, them)


def with_code_added(text: str, code: str) -> str:
    """Returns the text of a .nx file, `text`, with `code` added at its end,
    after one blank line, whatever blank lines the file ends with. A file
    with no code, empty or of blank lines only, becomes `code` alone."""
    return text.rstrip("\n") + "\n\n" + code if text.strip() else code
