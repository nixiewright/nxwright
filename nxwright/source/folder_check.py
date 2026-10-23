"""Checking a source folder as the build does, writing nothing: for
`nxwright check`, and for code editors, which check unsaved text.

The check runs every check the build makes while it reads the source folder:
its settings, each page and its code, program.nx, and that each file of a
picture, font, animation, video, or sound exists. Where the build stops at
the folder's first error, the check reports the first error of each page. An error in app.toml,
defaults.toml, or program.nx's declarations is reported alone, since every
page depends on them. The warnings of lint.py come with the errors; those
about the sounds' files, only when the check is given their bytes.

Each finding names its file and, when known, its line. An error in a table
of a page's .page.toml file gets the line of the table's header.

The check also measures each page against the limits the build enforces:
its objects, generated variables included, its longest chain of calls and
clicks, the program.s globals it needs, and its memory, as the Editor's
compile counts it (page_memory.py).

A code editor may check only the pages a change can affect. The folder's
own findings are then found again, but not the limit on the program.s
globals of all pages, nor the pages' memory, which need every page: the
editor keeps each page's measures, and finds the memory's findings from
them (memory_findings).
"""
from dataclasses import dataclass, field
import re

from nxwright import NxwrightError
from nxwright.project.page_memory import measure_page, project_memory
from nxwright.project.screen_models import ScreenModel
from nxwright.source.lint import (ERROR, WARNING, Finding, line_naming, picture_errors,
                                 sound_warnings, video_rotation_errors, warnings)
from nxwright.source.page_source import page_toml_path
from nxwright.source.source_folder import (RESOURCE_FILES, check_globals_count, memory_refusal,
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


def check_folder(read, exists, pages: list = None, read_bytes=None) -> FolderCheck:
    """Returns the FolderCheck of the source folder whose files `read(path)`
    returns, and `exists(path)` tells apart from missing ones, by their paths
    within the folder. With `pages`, only those pages are built. With
    `read_bytes(path, size=None)`, which returns a file's bytes, or its
    first `size` (source_folder.folder_byte_reader), the pictures' and the
    media's files are read too: the pictures', each opened without its pixels
    decoded, to find one nxwright cannot read (lint.picture_errors); the
    sounds', to warn of one not in the Editor's form (lint.sound_warnings);
    and the start of the videos', to find one made for another rotation
    (lint.video_rotation_errors)."""
    result = FolderCheck()
    try:
        folder = read_folder_source(read, skip_broken_pages=True)
    except NxwrightError as error:
        result.folder_findings.append(_finding(error, read))
        result.read_failed = True
        return result
    globals_used = []
    for page_id, page in enumerate(folder.app["pages"]):
        if pages is not None and page not in pages:
            continue
        chain, page_globals = [], []
        try:
            block = folder.build_page(page_id, page_globals, chain)
        except NxwrightError as error:
            result.page_findings[page] = [_finding(error, read)]
            continue
        result.page_findings[page] = []
        memory = measure_page(folder.screen, block) if folder.screen is not None else None
        result.measures[page] = PageMeasures(len(block.objects), chain, len(page_globals), memory)
        globals_used += page_globals
    for kind in RESOURCE_FILES:
        for name in folder.app[kind]:
            for problem in resource_problems(kind, name, exists):
                line = line_naming(read("app.toml"), name)
                result.folder_findings.append(Finding("app.toml", line, ERROR, problem))
    result.pages, result.screen = list(folder.app["pages"]), folder.screen
    try:
        if pages is None:
            check_globals_count(globals_used)
        result.program_ints = program_ints(folder.build_program(), folder.encoding)
    except NxwrightError as error:
        result.folder_findings.append(_finding(error, read))
    if pages is None:
        result.memory_findings = memory_findings(result, result.measures)
    try:
        folder.build_macros()
    except NxwrightError as error:
        result.folder_findings.append(_finding(error, read))
    result.folder_findings += warnings(folder.app, read)
    if read_bytes is not None:
        result.folder_findings += (picture_errors(folder.app, read, read_bytes, exists)
                                   + video_rotation_errors(folder.app, read, read_bytes)
                                   + sound_warnings(folder.app, read, read_bytes))
    return result


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


