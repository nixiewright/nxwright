"""Checking a source folder as the build does, writing nothing: for
`nxwright check`, and for code editors, which check unsaved text.

The check runs every check the build makes while it reads the source folder:
its settings, each page and its code, program.nx, and that each file of a
picture, font, animation, video, or sound exists. Where the build stops at
the folder's first error, the check reports the first error of each page. An error in app.toml,
defaults.toml, or program.nx's declarations is reported alone, since every
page depends on them. The warnings of lint.py come with the errors; those
about the sounds' files, only when the check is given their bytes. The
text-cut warnings from compiling a page's nxlang come with them too
(nxlang.compile_page).

Each finding names its file and, when known, its line. An error in a table
of a page's .page.toml file gets the line of the table's header.

The check also measures each page against the limits the build enforces:
its objects, generated variables included, its longest chain of calls and
clicks, the program.s globals it needs, and its memory, as the Editor's
compile counts it (page_memory.py).

A code editor may check only the pages a change can affect. A check of
only some pages still finds the folder's own findings, which are those that
do not come from building one page. It leaves out the two that need every
page: the limit on the program.s globals of all pages, and the pages'
memory. The code editor keeps each page's measures, and works out the
findings about the pages' memory from them (memory_findings).

A code editor also runs the check one step at a time (FolderCheckSteps), so
that it can show each page's findings before the next page is checked.
check_folder runs the same steps one after another, and finds every lint
warning in a single step. A code editor instead finds each page's lint
warnings when it checks that page (lint.page_warnings), so that they show
with the page's errors. The warnings that need several pages come
afterwards, in a step of their own (lint.shared_warnings).
"""
from dataclasses import dataclass, field
import re

from nxwright import NxwrightError
from nxwright.project.page_memory import measure_page, project_memory
from nxwright.project.screen_models import ScreenModel
from nxwright.source.lint import (ERROR, WARNING, Finding, page_warnings, picture_errors,
                                 shared_warnings, sound_errors, sound_warnings,
                                 svg_picture_warnings, video_rotation_errors, warnings)
from nxwright.source.page_source import page_toml_path
from nxwright.source.source_folder import (RESOURCE_FILES, check_globals_count,
                                           check_page_count, line_naming, memory_refusal,
                                           program_ints, read_folder_source, resource_problems)

_TABLE_HEADER = re.compile(r"\s*\[")


@dataclass
class PageMeasures:
    """A page against the build's limits: its objects, its longest chain of
    calls and clicks, as "home.load", "showClock", ..., the program.s
    globals it needs, and its memory, what page_memory.measure_page found,
    or None without screen settings."""
    objects: int
    chain: list
    globals_used: int
    memory: object = None


@dataclass
class FolderCheck:
    """The result of checking a source folder, or some of its pages."""
    folder_findings: list = field(default_factory=list)  # [Finding] not of one page
    page_findings: dict = field(default_factory=dict)    # {page: [Finding]}, of each page checked
    measures: dict = field(default_factory=dict)         # {page: PageMeasures}, of those that built
    # The memory's findings of every page, as memory_findings finds them;
    # none when only some pages were checked.
    memory_findings: list = field(default_factory=list)
    # True when an error every page depends on stopped the check before any page.
    read_failed: bool = False
    # What the memory's findings need beyond the pages' measures: the
    # folder's pages, in order; the screen model app.toml names; and how
    # many ints program.s declares, the generated globals left out. None
    # where not known.
    pages: list = None
    screen: ScreenModel = None
    program_ints: int = None

    def findings(self) -> list:
        """Returns every Finding, the errors first."""
        every = self.folder_findings + self.memory_findings + [
            finding for found in self.page_findings.values() for finding in found]
        return sorted(every, key=lambda finding: finding.severity != ERROR)

    def errors(self) -> list:
        """Returns the Findings the build would stop at, leaving out the warnings."""
        return [finding for finding in self.findings() if finding.severity == ERROR]


def check_folder(read, exists, pages: list = None, read_bytes=None,
                 listed=None) -> FolderCheck:
    """Returns the FolderCheck of the source folder whose files `read(path)`
    returns, and `exists(path)` tells apart from missing ones, by their paths
    within the folder. With `pages`, only those pages are built. With
    `read_bytes(path, size=None)`, which returns a file's bytes, or its
    first `size` (source_folder.folder_byte_reader), the pictures' and the
    media's files are read too: the pictures', each opened without its pixels
    decoded, to find one nxwright cannot read (lint.picture_errors); the
    sounds', to warn of one not in the Editor's form (lint.sound_warnings),
    and to find one a screen does not play (lint.sound_errors); and
    the start of the videos', to find one made for another rotation
    (lint.video_rotation_errors). `listed(folder)` returns the names of the
    files in a folder within the source folder (source_folder.folder_lister).
    If `listed` is given, the checks also find a picture whose file is of a
    type nxwright does not decode (source_folder.kept_picture_paths)."""
    check = FolderCheckSteps(read, exists, read_bytes, listed)
    if check.read_folder():
        for page in check.result.pages:
            if pages is None or page in pages:
                check.check_page(page)
        for step in check.folder_steps(every_page=pages is None):
            step()
    return check.result


class FolderCheckSteps:
    """A check of a source folder that runs one step at a time, for a caller
    that does something between the steps, such as sending a code editor
    what each step found. check_folder runs all the steps at once.

    The caller calls read_folder once, then check_page for each page to
    check, then each function that folder_steps returns. `result` is the
    FolderCheck of the steps run so far.

    To get each page's lint warnings together with that page, a caller calls
    page_warnings for each page and shared_warnings once. Both return the
    warnings without adding them to `result`. The caller then passes
    `with_warnings=False` to folder_steps, which leaves out the step that
    finds the lint warnings of the whole folder."""

    def __init__(self, read, exists, read_bytes=None, listed=None):
        """`read`, `exists`, `read_bytes`, and `listed` read the folder, and
        are the same as check_folder's arguments of those names."""
        self.result = FolderCheck()
        self._read, self._exists = read, exists
        self._read_bytes, self._listed = read_bytes, listed
        self._folder = None         # the FolderSource, once read_folder has read it
        self._globals_used = []     # the program.s globals of the pages checked

    def read_folder(self) -> bool:
        """Reads what every page depends on: the folder's settings, its
        component defaults, what program.nx declares, and the names of every
        page's objects. Returns False when an error in any of them stops the
        check. The error is then the result's only finding, and no other
        step can be run."""
        try:
            self._folder = read_folder_source(self._read, skip_broken_pages=True)
        except NxwrightError as error:
            self.result.folder_findings.append(_finding(error, self._read))
            self.result.read_failed = True
            return False
        try:
            check_page_count(self._folder.app, self._read("app.toml"))
        except NxwrightError as error:
            self.result.folder_findings.append(_finding(error, self._read))
        self.result.pages, self.result.screen = list(self._folder.app["pages"]), self._folder.screen
        return True

    def check_page(self, page: str):
        """Builds the page `page`, one of the result's `pages`, and adds its
        findings to the result. If the page builds, its measures are added
        too."""
        chain, page_globals, cut_texts = [], [], []
        try:
            block = self._folder.build_page(self.result.pages.index(page), page_globals, chain,
                                            cut_texts)
        except NxwrightError as error:
            self.result.page_findings[page] = [_finding(error, self._read)]
            return
        self.result.page_findings[page] = [Finding(file, line, WARNING, message, "text-cut")
                                           for file, line, message in cut_texts]
        screen = self._folder.screen
        memory = measure_page(screen, block) if screen is not None else None
        self.result.measures[page] = PageMeasures(len(block.objects), chain, len(page_globals),
                                                  memory)
        self._globals_used += page_globals

    def page_warnings(self, page: str) -> list:
        """Returns the lint warnings that can be found by reading the page
        `page` alone (lint.page_warnings), whether or not the page builds."""
        return page_warnings(self._folder.app, self._read, page)

    def shared_warnings(self) -> list:
        """Returns the lint warnings that cannot be found by reading one
        page alone, such as a constant that no page uses
        (lint.shared_warnings)."""
        return shared_warnings(self._folder.app, self._read)

    def folder_steps(self, every_page: bool, with_warnings: bool = True) -> list:
        """Returns the steps that add the folder's own findings to the
        result: functions without arguments, to call in order once the pages
        are checked. `every_page` is True if check_page checked every page.
        The limit on the pages' program.s globals and the pages' memory are
        checked only in that case, because both need every page. If
        `with_warnings` is False, no step finds the lint warnings. A caller
        passes False when it finds them itself with page_warnings and
        shared_warnings."""
        steps = [self._check_resource_files, lambda: self._check_program(every_page),
                 self._check_macros]
        if with_warnings:
            steps.append(self._find_warnings)
        if self._read_bytes is not None:
            steps += [self._check_pictures, self._check_media]
        return steps

    def _check_resource_files(self):
        for kind in RESOURCE_FILES:
            for name in self._folder.app[kind]:
                for problem in resource_problems(kind, name, self._exists, self._listed):
                    line = line_naming(self._read("app.toml"), name)
                    self.result.folder_findings.append(Finding("app.toml", line, ERROR, problem))

    def _check_program(self, every_page: bool):
        try:
            if every_page:
                check_globals_count(self._globals_used)
            self.result.program_ints = program_ints(self._folder.build_program(),
                                                    self._folder.encoding)
        except NxwrightError as error:
            self.result.folder_findings.append(_finding(error, self._read))
        if every_page:
            self.result.memory_findings = memory_findings(self.result, self.result.measures)

    def _check_macros(self):
        try:
            self._folder.build_macros()
        except NxwrightError as error:
            self.result.folder_findings.append(_finding(error, self._read))

    def _find_warnings(self):
        self.result.folder_findings += warnings(self._folder.app, self._read)

    def _check_pictures(self):
        self.result.folder_findings += picture_errors(self._folder.app, self._read,
                                                      self._read_bytes, self._exists, self._listed)

    def _check_media(self):
        app, read, read_bytes = self._folder.app, self._read, self._read_bytes
        self.result.folder_findings += (
            svg_picture_warnings(app, read, read_bytes, self._exists, self._listed)
            + video_rotation_errors(app, read, read_bytes)
            + sound_errors(app, read, read_bytes)
            + sound_warnings(app, read, read_bytes))


def memory_findings(check: FolderCheck, measures: dict) -> list:
    """Returns the Findings of the folder's memory, as the Editor's compile
    counts it over every page, from what `check` found and each page's
    measures, {page: PageMeasures}: where the table did not measure all, one
    warning saying what; and an error at the file of each page the compile
    refuses (source_folder.memory_refusal), counted without what the table
    did not measure. Nothing when a page or program.s did not build, or
    without screen settings, as the memory is then unknown."""
    if check.screen is None or check.program_ints is None or \
            any(page not in measures for page in check.pages):
        return []
    memory = project_memory(check.screen, {page: measures[page].memory for page in check.pages},
                            check.program_ints + sum(measures[page].globals_used
                                                     for page in check.pages))
    findings = []
    if memory.unmeasured is not None:
        page = memory.unmeasured[0]
        findings.append(Finding(page_toml_path(page) if page else "app.toml", 0, WARNING,
                                memory.warning, "memory-not-checked"))
    errors = [memory_refusal(page, why) for page, why in memory.refusals]
    return findings + [Finding(error.file, 0, ERROR, str(error)) for error in errors]


def _finding(error: NxwrightError, read) -> Finding:
    """Returns the Finding of an error the build raised."""
    file = error.file or ""
    line = error.line or 0
    if error.table is not None:
        try:
            line = _table_line(read(file), error.table)
        except NxwrightError:
            pass    # the file cannot be read: the error stands without a line
    # The place is part of the finding, so the message leaves it out when the
    # error gave it apart.
    message = error.reason if error.line is not None else str(error)
    return Finding(file, line, ERROR, message, fix=error.fix)


def _table_line(text: str, table: int) -> int:
    """Returns the line, from 1, of the header of table `table` of a page's
    .page.toml file, from 0 for [page]; 0 when there are fewer tables."""
    headers = [number for number, line in enumerate(text.split("\n"), start=1)
               if _TABLE_HEADER.match(line)]
    return headers[table] if table < len(headers) else 0


