"""The build's checks, run as the code editor's files change.

A change to a file marks that file. When typing pauses, each source folder
with marked files is checked again (folder_check.py), with the text of its
open files as the editor has them. The pages to check depend on what
changed:
  - the first time, or after a change to app.toml, defaults.toml, or the
    files of program.nx, every page;
  - after a change to a page's .page.toml file, that page, and each page
    whose code refers to it, as `second.t0.txt` refers to `second`
    (FolderIndex.pages_naming);
  - after a change to a .nx file, each page whose code is that file or
    includes it;
  - after any other change, such as a picture, no page.
A page that is not checked again keeps the errors and warnings it had.

The errors and warnings of a check are its findings (lint.Finding). A page's
findings are the error that stops its build or, if the page builds, a
warning for each text that may be cut. They also include the page's own
warnings, which are the lint warnings that can be found by reading that
page alone, such as a function it never calls (lint.page_warnings).

The folder's own findings are all the others, such as a missing file, and
each check finds them again. Among them, the shared warnings are the lint
warnings that need the code of several pages, such as a constant that no
page uses (lint.shared_warnings).

Checking a page also gives its measures, which are its objects, its longest
chain of calls and clicks, and the program.s globals. Each page's last
measures are kept for the editor to show.

A check runs in steps, so that the editor gets a page's findings as soon
as that page is checked. Between two steps, the server may do something
else, such as read a message (LiveChecks.step). A check goes in this order:
  - a step for each page to check. The pages most likely to have the error
    the user just corrected go first: those with a finding in a marked file,
    then the other pages with an error, then the rest. After each page,
    the editor is sent the findings of each file whose findings changed,
    and shows them in its Problems panel.
  - once the pages are checked, the notification nxwright/checked, for the
    editor to show the new measures.
  - a step for the shared warnings, which are sent immediately.
  - several steps for the rest of the folder's own findings. The findings
    about the pages' memory are among them. They depend on every page, and
    a check may cover only some, so each check finds them again from each
    page's last measures (folder_check.memory_findings). After the last of
    these steps, each file's findings are sent, and a file that no longer
    has any gets an empty list.
If an error in a file that every page depends on stops the check, the pages'
findings and the shared warnings are removed, and the error is sent with the
notification nxwright/checked.

While a page waits for its step, its findings in a marked file are left out
of what is sent. They were found in the file's old text, so each one may be
gone, or on another line. For example, if twelve pages include a file with
an error on one of its lines, all twelve report that error. Once the user
corrects the line, the error clears as soon as the first of those pages is
checked, without waiting for the other eleven.

If a file is marked during a check, the check stops before its next step.
The files it was started for are marked again, so the next check covers them
together with the new file.
"""
from dataclasses import dataclass, field
from pathlib import Path
import sys
import traceback

from lsprotocol import types

from nxwright.language.nxlang import MOST_CALL_DEPTH, MOST_GLOBALS
from nxwright.language_server.file_texts import uri_of
from nxwright.project.editor_limits import MOST_COMPONENTS
from nxwright.source.folder_index import APP_FILE, FolderIndex, page_of
from nxwright.source.folder_check import FolderCheckSteps, memory_findings
from nxwright.source.lint import ERROR
from nxwright.source.source_folder import folder_byte_reader, folder_lister

_EVERY_PAGE_FILES = {APP_FILE, "defaults.toml"}


@dataclass
class _FolderState:
    """The last findings and measures of one source folder."""
    checked: bool = False       # whether a check has covered every page
    # The folder's own findings, except the shared warnings, which are found
    # and sent before the others.
    folder_findings: list = field(default_factory=list)
    shared_warnings: list = field(default_factory=list)
    page_findings: dict = field(default_factory=dict)   # {page: [Finding]}, each page's findings
    measures: dict = field(default_factory=dict)
    memory_findings: list = field(default_factory=list)
    sent: dict = field(default_factory=dict)    # {file: [Finding]}, as last sent


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
        self._steps = None      # the steps left of the checks in progress, a generator
        self._checking = None   # (root, paths) of the folder being checked

    def mark(self, root: Path, path: str):
        """Notes that the folder's file `path` changed. A check in progress
        stops before its next step, and the files it was started for are
        marked again, so that the next check covers them together with
        `path`."""
        if self._steps is not None:
            self._steps.close()
            self._steps = None
        if self._checking is not None:
            stopped_root, stopped_paths = self._checking
            self._marked.setdefault(stopped_root, set()).update(stopped_paths)
            self._checking = None
        self._marked.setdefault(root, set()).add(path)

    def waiting(self) -> bool:
        """True when a change waits to be checked, or a check has steps left."""
        return bool(self._marked) or self._steps is not None

    def step(self) -> bool:
        """Runs the next step of checking the folders with changes, and sends
        what that step found. Returns whether more steps wait."""
        if self._steps is None:
            self._steps = self._checks_in_steps()
        try:
            next(self._steps)
        except StopIteration:
            self._steps = None
        return self.waiting()

    def run(self):
        """Checks the folders with changes without stopping between steps,
        and sends their findings."""
        while self.step():
            pass

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
        # The objects are the page's components and the page itself.
        return {"page": page, "objects": measures.objects, "mostObjects": MOST_COMPONENTS + 1,
                "chain": measures.chain, "mostChain": MOST_CALL_DEPTH,
                "globals": sum(found.globals_used for found in state.measures.values()),
                "mostGlobals": MOST_GLOBALS}

    def _checks_in_steps(self):
        """Checks the folders with changes, yielding between steps. An
        unexpected error in checking one folder must not end the server, or
        stop the checks of the other folders. The method catches such an
        error, and prints its trace to standard error, which editors show in
        their log."""
        while self._marked:
            root = next(iter(self._marked))
            self._checking = (root, self._marked.pop(root))
            try:
                yield from self._check(*self._checking)
            except Exception:
                traceback.print_exc(file=sys.stderr)
            self._checking = None

    def _check(self, root: Path, paths: set):
        """Checks the folder `root` after a change of `paths`, yielding
        between steps."""
        state = self._folders.setdefault(root, _FolderState())
        index = FolderIndex(root, self._read)
        check = FolderCheckSteps(self._texts.folder_reader(root),
                                 lambda path: (root / path).is_file(),
                                 folder_byte_reader(root), folder_lister(root))
        if not check.read_folder():
            state.page_findings, state.measures, state.memory_findings = {}, {}, []
            state.folder_findings, state.shared_warnings = check.result.folder_findings, []
            self._send(root, index, state, every_file=True)
            self._server.protocol.notify("nxwright/checked", {"uri": uri_of(root)})
            return
        affected = self._pages_to_check(state, index, paths)
        every_page = affected is None
        if every_page:
            _forget_unlisted_pages(state, check.result.pages)
        waiting = _in_order_of_interest(
            [page for page in check.result.pages if every_page or page in affected],
            state.page_findings, paths)
        while waiting:
            _check_page(check, state, waiting.pop(0))
            self._send(root, index, state, waiting, paths)
            if waiting:
                yield
        state.checked = state.checked or every_page
        self._server.protocol.notify("nxwright/checked", {"uri": uri_of(root)})
        yield
        state.shared_warnings = check.shared_warnings()
        self._send(root, index, state)
        for step in check.folder_steps(every_page, with_warnings=False):
            yield
            step()
        state.folder_findings = check.result.folder_findings
        state.memory_findings = memory_findings(check.result, state.measures)
        self._send(root, index, state, every_file=True)

    def _pages_to_check(self, state: _FolderState, index: FolderIndex, paths: set):
        """Returns the pages a change of `paths` may affect, or None for all."""
        if not state.checked or paths & (_EVERY_PAGE_FILES | set(index.program_files)):
            return None
        pages = set()
        for path in paths:
            if page_of(path):
                # Code that refers to the page depends on the page's file, for
                # example for its components.
                pages.add(page_of(path))
                pages.update(index.pages_naming(page_of(path)))
            elif path.endswith(".nx"):
                pages.update(index.pages_using(path))
        return pages

    def _send(self, root: Path, index: FolderIndex, state: _FolderState, waiting=(),
              changed=frozenset(), every_file: bool = False):
        """Sends the findings of each file whose findings changed since they
        were last sent. If `every_file` is True, sends the findings of every
        file that has findings, or had some when they were last sent. A file
        that no longer has findings gets an empty list. Sending every file
        also brings each finding's place up to date: a finding spans its
        line, whose text may have changed while the finding stayed the same.
        The findings that the pages in `waiting` have in the `changed` files
        are left out, because those pages are not checked yet and the
        findings were found in the files' old text."""
        every = state.folder_findings + state.shared_warnings + state.memory_findings + [
            finding for page, found in state.page_findings.items() for finding in found
            if not (page in waiting and _file_of(finding) in changed)]
        by_file = {}
        for finding in dict.fromkeys(every):    # a library's error comes from each page using it
            by_file.setdefault(_file_of(finding), []).append(finding)
        for file in sorted(set(by_file) | set(state.sent)):
            findings = by_file.get(file, [])
            if not every_file and findings == state.sent.get(file, []):
                continue
            lines = index.lines(file) or []
            diagnostics = [_diagnostic(finding, lines, self._units) for finding in findings]
            self._server.text_document_publish_diagnostics(types.PublishDiagnosticsParams(
                uri=uri_of(root / file), diagnostics=diagnostics))
        state.sent = by_file


def _file_of(finding) -> str:
    """Returns the file a Finding is shown in. A finding without a file of
    its own, such as some errors in the folder's settings, is shown in
    app.toml."""
    return finding.file or APP_FILE


def _forget_unlisted_pages(state: _FolderState, pages: list):
    """Removes from `state` the findings and measures of each page that
    app.toml no longer lists. `pages` is app.toml's list of pages. The pages
    still listed keep their findings and measures until their step."""
    for page in set(state.page_findings) - set(pages):
        del state.page_findings[page]
        state.measures.pop(page, None)


def _check_page(check: FolderCheckSteps, state: _FolderState, page: str):
    """Checks the page `page` with `check`, and keeps in `state` its
    findings, with its own warnings, and its measures when it builds."""
    check.check_page(page)
    state.page_findings[page] = check.result.page_findings[page] + check.page_warnings(page)
    state.measures.pop(page, None)
    if page in check.result.measures:
        state.measures[page] = check.result.measures[page]


def _in_order_of_interest(pages: list, page_findings: dict, changed: set) -> list:
    """Returns `pages` in the order to check them, so that a corrected error
    clears soonest: the pages with a finding in one of the `changed` files,
    then the other pages with an error, then the rest. Within each group
    the pages keep their order. `page_findings` is {page: [Finding]}.

    A warning in a file that did not change does not put its page ahead.
    Such warnings can stay on most pages for a long time, and nearly every
    page would then be in the second group."""
    def group(page: str) -> int:
        found = page_findings.get(page, [])
        if any(_file_of(finding) in changed for finding in found):
            return 0
        return 1 if any(finding.severity == ERROR for finding in found) else 2
    return sorted(pages, key=group)


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
