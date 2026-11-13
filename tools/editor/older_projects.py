"""Shows what an older release of the Nextion Editor does with the projects
that nxwright builds:

    python tools/editor/older_projects.py <the release's program> <output folder>

Run it with nxwright's own Python, from nxwright's folder. The release runs
from the folder that its zip was unpacked into, as a dedicated Editor of its
own (README.md).

For each of the release pass's projects (release_pass.round_trip_projects),
the script:

1. builds the project with nxwright;
2. has the release open and compile it;
3. has the release add a page and save the project. The Nextion Editor
   writes a page only when the page changes, so the added page is the one
   page that shows the page header this release writes;
4. reads the saved project's manifest header and page headers;
5. extracts the saved project, builds the folder again, and lists the blocks
   that differ between the saved project and this rebuild;
6. has the release compile the saved project and the rebuild, and compares
   the two TFT files. When they differ, the release compiles the saved
   project once more, to show whether it gives the same file twice.

For the small project of series T, the script also finds which constant bytes
of the manifest header the release writes itself. A release keeps a byte that
it does not write. If the release's own value for a byte is the same as the
current one, saving a project in the current form cannot show whether the
release wrote the byte or kept it. The script therefore changes those bytes
in the built project to the values of the Nextion Editor 1.67.1
(_FORM_OF_1_67_1), has the release save that copy, and lists which of them
the release wrote over.

When a step of the release stops, the script records what stopped it, closes
the Nextion Editor's messages and the Nextion Editor, and goes on with the
next project. The projects of series F and E run last, because an older
release may not offer those series, and the message it then shows can come
back after it is closed.

Everything is written to the output folder, with the findings in report.md.
Every project file is named probe.HMI, so that the Nextion Editor's work
folder keeps one copy (tools/tft/AGENTS.md).
"""
from dataclasses import dataclass, field
import os
from pathlib import Path
import re
import sys

# This file runs as a script, so it puts the folder above tools/ first on the import path.
NXWRIGHT_FOLDER = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(NXWRIGHT_FOLDER))

from nxwright import NxwrightError  # noqa: E402
from nxwright.project.byte_differences import (CHANGED, compare_by_name,  # noqa: E402
                                               differing_ranges, ranges_text)
from nxwright.project.container import HmiContainer  # noqa: E402
from nxwright.project.page_block import parse_page  # noqa: E402
from nxwright.project.resources import parse_manifest  # noqa: E402
from nxwright.project.stamp import with_manifest_stamp  # noqa: E402
from nxwright.source.project_files import build, extract  # noqa: E402
from nxwright.source.unknown_content import CURRENT_FORM  # noqa: E402
from tools.editor.release_pass import editor_tool, round_trip_projects  # noqa: E402

# The name of the dedicated Editor that runs the release.
EDITOR_NAME = "older-release"
# The projects that run last, in this order.
_LAST = ("series-F", "series-E")
# The project that also gets a copy in the manifest header form of 1.67.1.
_OTHER_FORM_PROJECT = "series-T"
# The constant bytes of the manifest header, by place, as the Nextion Editor
# 1.67.1 writes them. Three of them differ from the current form.
_FORM_OF_1_67_1 = {**CURRENT_FORM, 9: 0x43, 36: 1, 65: 2}
# How many times the script tries to close the Nextion Editor after a step stopped.
_CLOSING_TRIES = 3
# The first line of the tft command's output, which gives the file it wrote.
_WROTE = re.compile(r"^Wrote (.+)$", re.MULTILINE)
# The Nextion Editor's version in the status command's output.
_VERSION = re.compile(r"the Nextion Editor [\d.]+")


class Stopped(Exception):
    """Raised when a command of the Editor tool stops. Its text is the
    command and what the tool printed."""


@dataclass
class ProjectResult:
    """What one project showed. A field keeps its default when the project
    stopped before the step that sets it.

    - compiled: the Output panel after the release compiled the built
      project.
    - manifest_header: the saved project's manifest header.
    - page_headers: {page block: its header bytes 40 to 55}, in the
      manifest's order. The last one is the page that the release added.
    - notes: the notes that extract returned for the saved project.
    - blocks: the Differences of the rebuild from the saved project
      (byte_differences.compare_by_name).
    - tft_same: whether the saved project and the rebuild compile to the
      same TFT file.
    - repeats: when the two TFT files differ, whether the release compiles
      the saved project to the same file twice.
    - written_over: for the project in the form of 1.67.1, {place: (the
      byte given, the byte saved)} for each constant byte the release
      changed.
    - stopped: what stopped the project, one text for each stop."""
    name: str
    compiled: str = None
    manifest_header: bytes = None
    page_headers: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)
    blocks: list = None
    tft_same: bool = None
    repeats: bool = None
    written_over: dict = None
    stopped: list = field(default_factory=list)


def in_run_order(names: list) -> list:
    """Returns the projects' `names` in the order they run: as given, with
    those of _LAST moved to the end."""
    return ([name for name in names if name not in _LAST]
            + [name for name in _LAST if name in names])


def manifest_header_of(project: bytes) -> bytes:
    """Returns the manifest header of the project file `project`."""
    manifest = HmiContainer(project).blocks["main.HMI"]
    return manifest[:parse_manifest(manifest).header_size]


def page_headers_of(project: bytes) -> dict:
    """Returns {page block: its header bytes 40 to 55} for the pages of the
    project file `project`, in the manifest's order."""
    blocks = HmiContainer(project).blocks
    return {name: bytes(parse_page(blocks[name]).unknown_40)
            for name in parse_manifest(blocks["main.HMI"]).block_names("pa")}


def with_form_of_1_67_1(project: bytes) -> bytes:
    """Returns the project file `project` with the constant bytes of its
    manifest header as the Nextion Editor 1.67.1 writes them, and the
    manifest's stamp written again. The manifest keeps its size and its
    place in the file, so the file's directory stays as it is."""
    container = HmiContainer(project)
    entry = next(entry for entry in container.entries
                 if not entry.stale and entry.name == "main.HMI")
    manifest = container.blocks["main.HMI"]
    changed = bytearray(manifest)
    for place, value in _FORM_OF_1_67_1.items():
        changed[place] = value
    stamped = with_manifest_stamp(bytes(changed), manifest)
    return project[:entry.offset] + stamped + project[entry.offset + entry.size:]


def written_over(given: bytes, saved: bytes) -> dict:
    """Returns {place: (the byte given, the byte saved)} for each constant
    byte of the manifest header that differs between `given`, the header a
    release opened, and `saved`, the header it saved."""
    return {place: (given[place], saved[place]) for place in sorted(CURRENT_FORM)
            if given[place] != saved[place]}


def block_lines(found: list) -> list:
    """Returns one line for each Difference of `found`: the block, and for
    a changed block, how many bytes differ and where."""
    lines = []
    for each in found:
        if each.kind != CHANGED:
            lines.append("%s: %s" % (each.where, each.kind))
            continue
        ranges = differing_ranges(each.runs)
        lines.append("%s: %d bytes differ, at %s"
                     % (each.where, sum(last - first + 1 for first, last in ranges),
                        ranges_text(ranges)))
    return lines


def section(result: ProjectResult) -> str:
    """Returns the report's section on one project, in Markdown."""
    lines = ["## %s" % result.name, ""]
    if result.compiled is not None:
        lines += ["The release opened the project that nxwright built. The compile's output:",
                  "",
                  "```", result.compiled.strip(), "```", ""]
    if result.manifest_header is not None:
        header = result.manifest_header
        lines += ["The manifest header after the release's save:", "", "```"]
        lines += [header[start:start + 16].hex(" ") for start in range(0, len(header), 16)]
        lines += ["```", "", "Page header bytes 40 to 55, the added page last:", ""]
        lines += ["- %s: `%s`" % (name, data.hex(" "))
                  for name, data in result.page_headers.items()]
        lines.append("")
    if result.notes:
        lines += ["Extract's notes on the saved project:", ""]
        lines += ["- %s" % note for note in result.notes]
        lines.append("")
    if result.blocks is not None:
        lines += ["The blocks of the rebuild that differ from the saved project:", ""]
        lines += ["- %s" % line for line in block_lines(result.blocks)] or ["- none"]
        lines.append("")
    if result.tft_same is not None:
        lines.append("The saved project and the rebuild compile to %s." %
                     ("the same TFT file" if result.tft_same else "different TFT files"))
        if result.repeats is not None:
            lines.append("The release compiled the saved project twice, and got %s." %
                         ("the same file both times" if result.repeats else "different files"))
        lines.append("")
    if result.written_over is not None:
        lines += ["Given the manifest header in the form of 1.67.1, the release wrote over:", ""]
        lines += ["- byte %d: 0x%02x became 0x%02x" % (place, given, saved)
                  for place, (given, saved) in result.written_over.items()] or ["- no byte"]
        lines.append("")
    if result.stopped:
        lines += ["Stopped:", ""]
        lines += ["- %s" % stop for stop in result.stopped]
        lines.append("")
    return "\n".join(lines)


class Release:
    """One release of the Nextion Editor, driven through the Editor tool as
    the dedicated Editor EDITOR_NAME, under a hold of this script's."""

    def __init__(self, program: Path):
        self.environment = dict(os.environ, NXWRIGHT_EDITOR=str(program),
                                NXWRIGHT_EDITOR_NAME=EDITOR_NAME)
        self.holder = "older-projects-%d" % os.getpid()
        # The Nextion Editor's version, as the tool's status gives it, once it
        # has run.
        self.version = "not started"

    def step(self, *command) -> str:
        """Runs the tool's `command` as the holder, and returns what it
        printed. Raises Stopped when the command fails. After the first
        `open`, it also records the release's version, which the tool's
        status gives."""
        done = editor_tool(self.environment, *[str(part) for part in command], "--as",
                           self.holder)
        if done.returncode != 0:
            raise Stopped("`editor.py %s` stopped: %s"
                          % (command[0], (done.stderr or done.stdout).strip()))
        if command[0] == "open" and self.version == "not started":
            status = editor_tool(self.environment, "status").stdout
            found = _VERSION.search(status)
            self.version = found.group(0) if found else status.strip()
        return done.stdout

    def tft(self, project: Path, folder: Path) -> bytes:
        """Has the release open `project` and write its TFT file in the new
        folder `folder`, and returns the file's bytes. A busy Nextion Editor
        can fail a step once and pass it the next time, so a step that stops
        is tried once more, in a fresh Nextion Editor. Raises Stopped with
        both stops when the second try stops too."""
        folder.mkdir(parents=True)
        try:
            return self._written_tft(project, folder)
        except Stopped as first:
            self.close()
            try:
                return self._written_tft(project, folder)
            except Stopped as second:
                raise Stopped("%s; on the second try: %s" % (first, second)) from None

    def _written_tft(self, project: Path, folder: Path) -> bytes:
        """Has the release open `project` and write its TFT file in `folder`,
        and returns the file's bytes."""
        self.step("open", project)
        written = _WROTE.search(self.step("tft", folder))
        if written is None:
            raise Stopped("`editor.py tft` did not say which file it wrote")
        return Path(written.group(1).strip()).read_bytes()

    def hold(self):
        """Takes the hold. Raises Stopped when someone else has it."""
        done = editor_tool(self.environment, "hold", self.holder)
        if done.returncode != 0:
            raise Stopped((done.stderr or done.stdout).strip())

    def release(self):
        """Ends the hold."""
        editor_tool(self.environment, "release", self.holder)

    def close(self):
        """Closes whatever a stopped step left open, then the Nextion
        Editor. A message can come back after it was closed, so the closing
        commands run up to _CLOSING_TRIES times. Raises Stopped when the
        Nextion Editor is still open after that."""
        for _ in range(_CLOSING_TRIES):
            for closing in ("close-simulator", "close-file-dialog", "close-message"):
                editor_tool(self.environment, closing, "--as", self.holder)
            done = editor_tool(self.environment, "quit", "--as", self.holder)
            if done.returncode == 0:
                return
        raise Stopped("the Nextion Editor did not close: %s"
                      % (done.stderr or done.stdout).strip())


def run_project(name: str, source: Path, release: Release, output: Path) -> ProjectResult:
    """Runs the steps of the module's docstring for the project `name`,
    whose source folder is `source`, in the new folder `output`. A step of
    the release that stops ends the project, and is recorded in the
    result. Raises Stopped only when the Nextion Editor cannot be closed
    after."""
    result = ProjectResult(name)
    output.mkdir(parents=True)
    built = output / "built" / "probe.HMI"
    built.parent.mkdir()
    try:
        build(source, built)
        _saved_and_rebuilt(built, release, output, result)
    except (Stopped, NxwrightError) as error:
        result.stopped.append(str(error))
        release.close()
    if name == _OTHER_FORM_PROJECT and built.is_file():
        try:
            result.written_over = _written_over_by(release, built, output)
        except (Stopped, NxwrightError) as error:
            result.stopped.append("with the form of 1.67.1: %s" % error)
            release.close()
    return result


def _saved_and_rebuilt(built: Path, release: Release, output: Path, result: ProjectResult):
    """Runs steps 2 to 6 of the module's docstring on the project file
    `built`, in the folder `output`, and sets what each step shows in
    `result`. Raises Stopped when a step of the release stops, and
    NxwrightError when nxwright cannot read or build the saved project. The
    steps before that one stay recorded in `result`."""
    release.step("open", built)
    result.compiled = release.step("compile")
    release.step("add-page")
    saved = output / "saved" / "probe.HMI"
    saved.parent.mkdir()
    release.step("save", saved)
    result.manifest_header = manifest_header_of(saved.read_bytes())
    result.page_headers = page_headers_of(saved.read_bytes())
    result.notes = extract(saved, output / "folder", continue_with_unknown=True,
                           keep_locks_without_password=True)
    rebuilt = output / "rebuilt" / "probe.HMI"
    rebuilt.parent.mkdir()
    build(output / "folder", rebuilt)
    result.blocks = compare_by_name(HmiContainer.from_file(saved).blocks,
                                    HmiContainer.from_file(rebuilt).blocks)
    of_saved = release.tft(saved, output / "tft-saved")
    result.tft_same = of_saved == release.tft(rebuilt, output / "tft-rebuilt")
    if not result.tft_same:
        result.repeats = of_saved == release.tft(saved, output / "tft-saved-again")


def _written_over_by(release: Release, built: Path, output: Path) -> dict:
    """Has the release save a copy of the project file `built` whose manifest
    header is in the form of 1.67.1, in the folder `output`, and returns the
    constant bytes that the release wrote over (written_over)."""
    given = output / "other-form" / "probe.HMI"
    given.parent.mkdir()
    given.write_bytes(with_form_of_1_67_1(built.read_bytes()))
    release.step("open", given)
    saved = output / "other-form-saved" / "probe.HMI"
    saved.parent.mkdir()
    release.step("save", saved)
    return written_over(manifest_header_of(given.read_bytes()),
                        manifest_header_of(saved.read_bytes()))


def run(program: Path, output: Path) -> str:
    """Runs every project with the release `program`. Creates the folder
    `output` and writes everything in it. Returns the report's text, which
    is also written to `output`/report.md after each project, so that a run
    that stops later keeps the sections written so far."""
    output.mkdir(parents=True)
    work = output / "projects"
    work.mkdir()
    sources = round_trip_projects(work)
    release = Release(program)
    release.hold()
    sections, text = [], ""
    try:
        # A Nextion Editor left open by an earlier run may be another release.
        release.close()
        for name in in_run_order(list(sources)):
            sections.append(section(run_project(name, sources[name], release, output / name)))
            text = ("# An older release, with the projects nxwright builds\n\n"
                    "The release: %s, at %s\n\n%s" % (release.version, program,
                                                      "\n".join(sections)))
            (output / "report.md").write_text(text, encoding="utf-8", newline="\n")
        release.close()
    finally:
        release.release()
    return text


def main(arguments: list = None) -> int:
    arguments = sys.argv[1:] if arguments is None else arguments
    if len(arguments) != 2:
        print("usage: python tools/editor/older_projects.py <the release's program> "
              "<output folder>", file=sys.stderr)
        return 2
    program, output = Path(arguments[0]), Path(arguments[1])
    if not program.is_file():
        print("older_projects: %s is not a file" % program, file=sys.stderr)
        return 2
    if output.exists():
        print("older_projects: %s already exists; nothing was written" % output, file=sys.stderr)
        return 2
    try:
        run(program, output)
    except Stopped as error:
        print("older_projects: stopped: %s" % error, file=sys.stderr)
        return 1
    print("Wrote %s" % (output / "report.md"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
