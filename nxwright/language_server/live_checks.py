"""The build's checks, run as the code editor's files change.

A change marks its file. When typing pauses, each source folder with marked
files is checked again (folder_check.py), with the text of its open files as
the editor has them:
  - the first time, or after a change to app.toml, defaults.toml, or the
    files of program.nx, every page;
  - after a change to a page's .page.toml file, that page;
  - after a change to a .nx file, each page whose code includes it, or is it;
  - after any other change, such as a picture, no page: the folder's own
    findings are found again all the same.
The findings of the pages not checked again stay as they were. The pages'
memory needs every page, so its findings are found again each time, from
each page's last measures (folder_check.memory_findings). Each file's
findings are then sent to the editor, which shows them in its Problems
panel, and a file that no longer has any gets an empty list. When an error
every page depends on stops the check, the pages' findings go with it. Last
comes the notification nxwright/checked, for the editor to show the new
measures.

The last measures of each page are kept for the editor to show: its objects,
its longest chain of calls and clicks, and the program.s globals.
"""
from dataclasses import dataclass, field
from pathlib import Path
import sys
import traceback

from lsprotocol import types

from nxwright.language.nxlang import MOST_CALL_DEPTH, MOST_GLOBALS
from nxwright.language_server.file_texts import uri_of
from nxwright.source.folder_index import APP_FILE, FolderIndex, page_of
from nxwright.source.folder_check import check_folder, memory_findings
from nxwright.source.lint import ERROR
from nxwright.source.page_source import MOST_OBJECTS
from nxwright.source.source_folder import folder_byte_reader

_EVERY_PAGE_FILES = {APP_FILE, "defaults.toml"}


@dataclass
class _FolderState:
    """The last findings and measures of one source folder."""
    checked: bool = False
    folder_findings: list = field(default_factory=list)
    page_findings: dict = field(default_factory=dict)
    measures: dict = field(default_factory=dict)
    memory_findings: list = field(default_factory=list)
    published: set = field(default_factory=set)     # files sent findings last time


class LiveChecks:
    """The checks of the source folders whose files change, read through
    `texts` (file_texts.FileTexts), sent through `server`, a pygls
    LanguageServer: its findings, and the notification nxwright/checked.
    `units(text)` counts the editor's units of a line's text, in which a
    column is given."""

    def __init__(self, texts, server, units):
        self._texts, self._server, self._units = texts, server, units
        self._read = texts.read
        self._folders = {}      # {root: _FolderState}
        self._marked = {}       # {root: {changed paths within the folder}}

    def mark(self, root: Path, path: str):
        """Notes that the folder's file `path` changed."""
        self._marked.setdefault(root, set()).add(path)

    def waiting(self) -> bool:
        """True when a change waits to be checked."""
        return bool(self._marked)

    def run(self):
        """Checks the folders with changes, and sends their findings. A
        mistake in checking one folder must not end the server, nor stop the
        others: its trace goes to standard error, which editors show in their
        log."""
        marked, self._marked = self._marked, {}
        for root, paths in marked.items():
            try:
                self._check(root, paths)
            except Exception:
                traceback.print_exc(file=sys.stderr)

    def limits(self, root: Path, path: str):
        """Returns the protocol's form of the measures of the page of the
        folder's file `path`, or None when it has none yet."""
        state = self._folders.get(root)
        if state is None:
            return None
        index = FolderIndex(root, self._read)
        pages = [page_of(path)] if page_of(path) else index.pages_using(path)
        page = next((page for page in pages if page in state.measures), None)
        if page is None:
            return None
        measures = state.measures[page]
        return {"page": page, "objects": measures.objects, "mostObjects": MOST_OBJECTS,
                "chain": measures.chain, "mostChain": MOST_CALL_DEPTH,
                "globals": sum(found.globals_used for found in state.measures.values()),
                "mostGlobals": MOST_GLOBALS}

    def _check(self, root: Path, paths: set):
        state = self._folders.setdefault(root, _FolderState())
        index = FolderIndex(root, self._read)
        pages = self._pages_to_check(state, index, paths)

        result = check_folder(self._texts.folder_reader(root),
                              lambda path: (root / path).is_file(), pages,
                              folder_byte_reader(root))
        if pages is None or result.read_failed:
            state.page_findings, state.measures = {}, {}
        for page in result.page_findings:
            state.page_findings[page] = result.page_findings[page]
            state.measures.pop(page, None)
        state.measures.update(result.measures)
        state.folder_findings, state.checked = result.folder_findings, True
        state.memory_findings = memory_findings(result, state.measures)
        self._publish(root, index, state)
        self._server.protocol.notify("nxwright/checked", {"uri": uri_of(root)})

    def _pages_to_check(self, state: _FolderState, index: FolderIndex, paths: set):
        """Returns the pages a change of `paths` may affect, or None for all."""
        if not state.checked or paths & (_EVERY_PAGE_FILES | set(index.program_files)):
            return None
        pages = set()
        for path in paths:
            if page_of(path):
                pages.add(page_of(path))
            elif path.endswith(".nx"):
                pages.update(index.pages_using(path))
        return sorted(pages)

    def _publish(self, root: Path, index: FolderIndex, state: _FolderState):
        """Sends each file's findings, and an empty list to each file that no
        longer has any."""
        every = state.folder_findings + state.memory_findings + [
            finding for found in state.page_findings.values() for finding in found]
        by_file = {}
        for finding in dict.fromkeys(every):    # a library's error comes from each page using it
            by_file.setdefault(finding.file or APP_FILE, []).append(finding)
        for file in sorted(set(by_file) | state.published):
            lines = index.lines(file) or []
            diagnostics = [_diagnostic(finding, lines, self._units)
                           for finding in by_file.get(file, [])]
            self._server.text_document_publish_diagnostics(types.PublishDiagnosticsParams(
                uri=uri_of(root / file), diagnostics=diagnostics))
        state.published = set(by_file)


def _diagnostic(finding, lines: list, units) -> types.Diagnostic:
    """Returns the protocol's Diagnostic of a Finding, spanning its line, or
    the file's first line when it has none, its end counted in the editor's
    units, `units(text)`."""
    line = max(finding.line - 1, 0)
    text = lines[line] if line < len(lines) else ""
    return types.Diagnostic(
        range=types.Range(start=types.Position(line=line, character=0),
                          end=types.Position(line=line, character=units(text))),
        severity=(types.DiagnosticSeverity.Error if finding.severity == ERROR
                  else types.DiagnosticSeverity.Warning),
        source="nxwright", message=finding.message, code=finding.rule or None,
        # A quick fix's description, handed back with a code action request.
        data=finding.fix)
