"""The round trip of a release pass: how a new Nextion Editor treats the
projects nxwright builds, beside how the old one, the Editor nxwright is
tested with, treats them.

    python tools/editor/release_pass.py round-trip --old <program> --new <program> <output>

Run it with nxwright's own Python, from nxwright's folder. Each program is a
Nextion Editor's, such as NextionEditor.exe in the folder of its release's
unpacked zip. The script drives each Editor through the Editor tool, run
with the tool's Python, under an Editor name of its own (EDITOR_NAMES). It
writes everything into <output>, a folder it creates, and the findings in
<output>/report.md.

For each project (round_trip_projects), with each Editor in turn, it builds
the project with nxwright, has the Editor open it, compile it in its
simulator, and save it, then writes `nxwright report` of the saved file,
extracts the saved file into a copy of the project's source folder, and
compares the copy with the built file extracted alike, and the built file
with the saved file.

A difference is a file of a folder, or a live block of a project file, that
one side has and the other lacks, or that both have with other bytes. A
changed one comes with its runs: each stretch of bytes that differs, from
where it starts, with the bytes on each side. The directory of a project
file is left aside, as each save adds to it. The differences the old Editor
makes are what any save changes; those the new Editor alone makes are the
findings (new_editor_only).
"""
import argparse
from dataclasses import dataclass, field
import os
from pathlib import Path
import shutil
import subprocess
import sys

# Run as a script, so the folder above tools/ is put first on the import path.
NXWRIGHT_FOLDER = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(NXWRIGHT_FOLDER))

from nxwright import NxwrightError  # noqa: E402
from nxwright.project.container import HmiContainer  # noqa: E402
from nxwright.project.device_settings import DeviceSettings  # noqa: E402
from nxwright.project.new_project import write_new_project  # noqa: E402
from nxwright.project.screen_models import model_named  # noqa: E402
from nxwright.project.truetype import NOTO_SANS  # noqa: E402
from nxwright.source.project_files import build, extract  # noqa: E402
from nxwright.source.report import write_report  # noqa: E402
from nxwright.source.resource_adding import (add_animation, add_font, add_pictures,  # noqa: E402
                                             add_sound, add_video)
from nxwright.source.source_folder import new_source_folder  # noqa: E402
from tools.editor.catalog import with_values  # noqa: E402

# The round trip's own pictures and sound, which no other part of nxwright
# uses, so that the demo and the tests' fixtures stay free to change.
RESOURCES = Path(__file__).resolve().with_name("round_trip")
# The Editor tool, and the Python it runs with (README.md, Setting it up).
EDITOR_SCRIPT = Path(__file__).resolve().with_name("editor.py")
TOOL_PYTHON = Path(__file__).resolve().parent / "build" / "venv" / "Scripts" / "python.exe"
# The Editor name each side runs under, so that the two never share a
# dedicated Editor, even when both are the same program.
EDITOR_NAMES = {"old": "release-old", "new": "release-new"}
# The one small project of each series, of a model of it. Each series stores
# pictures in a form of its own.
SERIES_MODELS = {"T": "NX4832T035", "K": "NX4832K035", "P": "NX8048P050", "E": "NX4880E043",
                 "F": "NX4832F035"}
# The fixture of the tests of file browsers, and the font it names.
FILES_FIXTURE = NXWRIGHT_FOLDER / "tests" / "fixtures" / "files" / "app"
FILES_FIXTURE_FONT = NXWRIGHT_FOLDER / "tests" / "fixtures" / "fonts" / "Sans16.zi"
# The every-component project: the dump of one newly added component of
# each type, and the settings catalog_variants.py builds it with.
EVERY_COMPONENT = NXWRIGHT_FOLDER / "tests" / "fixtures" / "every-component"
EVERY_COMPONENT_SETTINGS = DeviceSettings(model_named("NX8048P070"), 180, "iso-8859-1")
_EVERY_COMPONENT_PAGE = Path("pages") / "00-page0.txt"
# The attributes that name a picture, an animation, a video, or a sound.
# The every-component project's new components name none (65535), which
# the Editor's compile refuses, so each is set to the first of its kind.
_RESOURCE_ATTRIBUTES = ("pic", "pic1", "pic2", "picc", "picc1", "picc2", "bpic", "ppic", "vid")
# The height of the font the every-component project is given, in pixels.
_FONT_HEIGHT = 16

# The kinds of difference: on the second side only, on the first side
# only, and on both, with other bytes.
ADDED, REMOVED, CHANGED = "added", "removed", "changed"


@dataclass(frozen=True)
class Difference:
    """A file or block, `where`, that differs (ADDED, REMOVED, or CHANGED),
    and for a changed one, its runs: (where the run starts, the first
    side's bytes, the second side's bytes)."""
    where: str
    kind: str
    runs: tuple = ()


def differing_runs(first: bytes, second: bytes) -> tuple:
    """Returns the runs where `first` and `second` differ: each stretch of
    neighbouring bytes that differ, as (where it starts, the first side's
    bytes, the second side's). Past the shorter side, the longer side's
    bytes make a run of their own."""
    runs = []
    start = None
    shorter = min(len(first), len(second))
    for place in range(shorter + 1):
        differs = place < shorter and first[place] != second[place]
        if differs and start is None:
            start = place
        elif not differs and start is not None:
            runs.append((start, first[start:place], second[start:place]))
            start = None
    if len(first) != len(second):
        runs.append((shorter, first[shorter:], second[shorter:]))
    return tuple(runs)


def compare_folders(first: Path, second: Path) -> list:
    """Returns the Differences of the folder `second` from the folder
    `first`, file by file, by each file's path from its folder, written
    with /."""
    files = [{path.relative_to(folder).as_posix(): path for path in folder.rglob("*")
              if path.is_file()} for folder in (first, second)]
    return _compared({name: path.read_bytes() for name, path in files[0].items()},
                     {name: path.read_bytes() for name, path in files[1].items()})


def compare_blocks(built: dict, saved: dict) -> list:
    """Returns the Differences of the live blocks `saved` from the live
    blocks `built`, each {name: bytes}, as HmiContainer gives them."""
    return _compared(built, saved)


def _compared(first: dict, second: dict) -> list:
    """Returns the Differences of `second` from `first`, each {name: bytes},
    by name."""
    found = []
    for name in sorted(set(first) | set(second)):
        if name not in first:
            found.append(Difference(name, ADDED))
        elif name not in second:
            found.append(Difference(name, REMOVED))
        elif first[name] != second[name]:
            found.append(Difference(name, CHANGED, differing_runs(first[name], second[name])))
    return found


def new_editor_only(old: list, new: list) -> list:
    """Returns the Differences of `new`, the new Editor's, that the old
    Editor's, `old`, lack: a file or block the old Editor did not add or
    remove alike, and of a changed one, the runs the old Editor's lacks,
    with the same place and the same bytes. So a block both Editors change,
    but differently, is kept."""
    seen = {(each.where, each.kind): each for each in old}
    kept = []
    for each in new:
        before = seen.get((each.where, each.kind))
        if before is None:
            kept.append(each)
        elif each.kind == CHANGED:
            runs = tuple(run for run in each.runs if run not in before.runs)
            if runs:
                kept.append(Difference(each.where, CHANGED, runs))
    return kept


# What changes from one save to the next, whatever the project: the places
# the comparison passes over, as (a block's or file's name, where a run
# starts), each with a comment saying what it is. A run of the Nextion
# Editor 1.68.2 against itself found none: its Save As of a project it
# opened wrote every live block as nxwright built it.
SAVE_TO_SAVE = {}


@dataclass
class Side:
    """What one Editor made of one project: the differences of the extracted
    copy from the source folder (`folder`), and of the saved file from the
    built one (`blocks`), and what else it found (`findings`): the extract's
    warnings and refusals, and a step that failed. `finished` is whether
    the run got as far as both comparisons."""
    folder: list = field(default_factory=list)
    blocks: list = field(default_factory=list)
    findings: list = field(default_factory=list)
    finished: bool = False


def round_trip_projects(work: Path) -> dict:
    """Writes the round trip's projects' source folders in `work`, and
    returns {name: source folder}: the demo, the fixture of the tests of
    files, the every-component project, and one small project of each
    series, with one picture."""
    projects = {}
    for name, source in (("demo", NXWRIGHT_FOLDER / "examples" / "thermostat" / "app"),
                         ("files", FILES_FIXTURE)):
        projects[name] = work / name
        shutil.copytree(source, projects[name])
    # The fixture names a font it does not keep, which its own tests copy in
    # (tests/test_file_browsers.py).
    (projects["files"] / "fonts").mkdir()
    shutil.copyfile(FILES_FIXTURE_FONT, projects["files"] / "fonts" / FILES_FIXTURE_FONT.name)
    projects["every-component"] = _every_component(work)
    for series, model in SERIES_MODELS.items():
        folder = work / ("series-" + series)
        new_source_folder(folder, DeviceSettings(model_named(model), 0, "iso-8859-1"), "nxlang")
        add_pictures(folder, [RESOURCES / "red.png"])
        projects[folder.name] = folder
    return projects


def _every_component(work: Path) -> Path:
    """Writes the every-component project's source folder in `work`, and
    returns it. The project is built from its dump, as catalog_variants.py
    builds it, and extracted into a folder. Each picture and media resource
    its components name is the first of its kind. The folder is given the
    animation, the video, and the sound from RESOURCES, and a font drawn
    from nxwright's own Noto Sans, so that the Editor's compile takes it."""
    dump = work / "every-component-dump"
    shutil.copytree(EVERY_COMPONENT, dump)
    page = dump / _EVERY_COMPONENT_PAGE
    text = page.read_text(encoding="utf-8")
    page.write_text(with_values(text, _resource_settings(text)), encoding="utf-8")
    project = work / "every-component-dump.HMI"
    write_new_project(dump, EVERY_COMPONENT_SETTINGS, project)
    folder = work / "every-component"
    extract(project, folder)
    frames = [RESOURCES / "red.png", RESOURCES / "blue.png"]
    add_font(folder, NOTO_SANS, _FONT_HEIGHT)
    add_animation(folder, frames, name="frames")
    add_video(folder, frames, name="clip")
    add_sound(folder, RESOURCES / "beep.wav", name="beep")
    return folder


def _resource_settings(dump_page: str) -> dict:
    """Returns {component: {attribute: 0}} of the dump's page `dump_page`,
    for each of its objects' attributes that names a picture or a media
    resource (_RESOURCE_ATTRIBUTES)."""
    settings, component = {}, None
    for line in dump_page.split("\n"):
        if line.startswith("object "):
            component = line.split()[2]
        elif component is not None and line.startswith("  ") and line.strip():
            name = line.split()[0].split(":")[0]
            if name in _RESOURCE_ATTRIBUTES:
                settings.setdefault(component, {})[name] = 0
    return settings


def run_side(name: str, source: Path, built: Path, baseline: Path, side: str, program: Path,
             output: Path) -> Side:
    """Has the Editor `program`, the `side` one ("old" or "new"), open the
    built project `built` of the source folder `source`, compile it in its
    simulator, and save it, in `output`. Then writes the saved file's
    report, extracts it into a copy of `source`, and compares the copy with
    `baseline`, the built file extracted alike, so that what extract itself
    writes otherwise than `source`, such as its layout of lists, is left
    out. Returns the Side.

    A step of the Editor that fails is tried again once, from `open`, in a
    fresh Editor. A busy Editor can fail a step once, and take it the next
    time. A step that fails twice is a finding, and ends the side there."""
    result = Side()
    output.mkdir(parents=True)
    saved = output / (name + ".HMI")
    environment = dict(os.environ, NXWRIGHT_EDITOR=str(program),
                       NXWRIGHT_EDITOR_NAME=EDITOR_NAMES[side])
    stopped = _saved_by_the_editor(built, saved, output, environment)
    if stopped is not None:
        # A file the first try saved before a later step stopped would make
        # `save` refuse it the second time.
        saved.unlink(missing_ok=True)
        stopped_again = _saved_by_the_editor(built, saved, output, environment)
        if stopped_again is not None:
            result.findings += [stopped, "tried again: " + stopped_again]
            return result
        # Kept, so that an Editor that fails often shows over several passes.
        result.findings.append("the first try stopped, and the second went through: "
                               + stopped)
    try:
        write_report(saved, output / (name + ".report.md"))
    except NxwrightError as error:
        result.findings.append("`nxwright report` refused the saved file: %s" % error)
    copy = output / "folder"
    shutil.copytree(source, copy)
    try:
        result.findings += ["extract: %s" % warning
                            for warning in extract(saved, copy, continue_with_unknown=True)]
        result.folder = compare_folders(baseline, copy)
        result.blocks = _without_save_to_save(compare_blocks(
            HmiContainer.from_file(built).blocks, HmiContainer.from_file(saved).blocks))
    except NxwrightError as error:
        result.findings.append("nxwright could not read the saved file: %s" % error)
        return result
    result.finished = True
    return result


def _saved_by_the_editor(built: Path, saved: Path, output: Path, environment: dict):
    """Has the Editor that `environment` names open `built`, compile it in
    its simulator, and save it as `saved`, while this script holds that
    Editor (editor.py hold).
    Returns None, or what stopped a step, once the Editor is closed, so
    that a try again starts afresh."""
    holder = "release-pass-%d" % os.getpid()
    steps = [("hold", holder), ("open", str(built), "--as", holder),
             ("simulate", str(output / "simulator.png"), "--as", holder),
             ("save", str(saved), "--as", holder)]
    try:
        for step in steps:
            done = _editor(environment, *step)
            if done.returncode != 0:
                # A dialog or message the step left up would stop `quit`.
                for closing in ("close-simulator", "close-file-dialog", "close-message", "quit"):
                    _editor(environment, closing, "--as", holder)
                return "`editor.py %s` stopped: %s" % (step[0],
                                                       (done.stderr or done.stdout).strip())
        return None
    finally:
        _editor(environment, "release", holder)


def _editor(environment: dict, *command: str) -> subprocess.CompletedProcess:
    """Runs the Editor tool's `command` with the tool's Python, for the
    Editor that `environment` names."""
    return subprocess.run([str(TOOL_PYTHON), str(EDITOR_SCRIPT), *command], cwd=NXWRIGHT_FOLDER,
                          env=environment, capture_output=True, text=True, encoding="utf-8",
                          errors="replace")


def _without_save_to_save(found: list) -> list:
    """Returns the Differences `found`, without the runs SAVE_TO_SAVE passes
    over, and without a changed block that has no run left."""
    kept = []
    for each in found:
        runs = tuple(run for run in each.runs if (each.where, run[0]) not in SAVE_TO_SAVE)
        if each.kind != CHANGED or runs:
            kept.append(Difference(each.where, each.kind, runs))
    return kept


def round_trip(old: Path, new: Path, output: Path) -> str:
    """Runs the round trip of each project with the Editors `old` and `new`,
    writes everything in `output`, a folder it creates, and returns the
    report's text, which it also writes to `output`/report.md."""
    output.mkdir(parents=True)
    work = output / "projects"
    work.mkdir()
    sections = []
    for name, source in round_trip_projects(work).items():
        built = output / name / (name + ".HMI")
        built.parent.mkdir(parents=True)
        try:
            build(source, built)
            # The built file extracted, which each side's saved file is
            # compared with, so that only the Editor's changes show.
            baseline = output / name / "built-folder"
            shutil.copytree(source, baseline)
            extract(built, baseline, continue_with_unknown=True)
        except NxwrightError as error:
            sections.append("## %s\n\nnxwright could not build or extract it: %s\n"
                            % (name, error))
        else:
            sides = {side: run_side(name, source, built, baseline, side, program,
                                    output / name / side)
                     for side, program in (("old", old), ("new", new))}
            sections.append(_section(name, sides["old"], sides["new"]))
        # Written after each project, so that a run stopped later keeps them.
        text = ("# The round trip\n\nThe old Editor: %s\n\nThe new Editor: %s\n\n%s"
                % (old, new, "\n".join(sections)))
        (output / "report.md").write_text(text, encoding="utf-8", newline="\n")
    return text


def _section(name: str, old: Side, new: Side) -> str:
    """Returns the report's section of the project `name`: what the old
    Editor's save changes, then the findings: what the new Editor alone
    changes, and what else each side found. When the old Editor's run did
    not finish, nothing tells the new Editor's changes from what any save
    changes, so they are listed as they are, and said to be so."""
    lines = ["## %s" % name, ""]
    if old.finished:
        lines += ["### What the old Editor changes", ""]
        lines += _listed(old.folder, "source folder") + _listed(old.blocks, "project file")
        lines += ["", "### What the new Editor alone changes", ""]
        if new.finished:
            lines += _listed(new_editor_only(old.folder, new.folder), "source folder")
            lines += _listed(new_editor_only(old.blocks, new.blocks), "project file")
        else:
            lines.append("The new Editor's run did not finish (below).")
    else:
        lines += ["### What the new Editor changes", "",
                  "The old Editor's run did not finish (below), so these are not told apart "
                  "from what any save changes.", ""]
        if new.finished:
            lines += _listed(new.folder, "source folder") + _listed(new.blocks, "project file")
        else:
            lines.append("The new Editor's run did not finish either.")
    for side, found in (("old", old.findings), ("new", new.findings)):
        if found:
            lines += ["", "### What else the %s Editor's run found" % side, ""]
            lines += ["- %s" % each for each in found]
    return "\n".join(lines) + "\n"


def _listed(found: list, what: str) -> list:
    """Returns a line for each Difference of `found`, in the `what`, with
    its runs, or one line when there is none."""
    if not found:
        return ["- In the %s: nothing." % what]
    lines = []
    for each in found:
        lines.append("- In the %s, `%s`: %s" % (what, each.where, each.kind))
        lines += ["  - at %d: %s, then %s" % (start, first.hex(" ") or "nothing",
                                              second.hex(" ") or "nothing")
                  for start, first, second in each.runs]
    return lines


def main(arguments: list = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    trip = commands.add_parser("round-trip", help="how a new Nextion Editor treats nxwright's "
                               "projects, beside the old one")
    trip.add_argument("--old", type=Path, required=True, help="the old Editor's program")
    trip.add_argument("--new", type=Path, required=True, help="the new Editor's program")
    trip.add_argument("output", type=Path, help="the folder to write, which must not exist")
    options = parser.parse_args(arguments)
    if options.output.exists():
        print("%s exists already; nothing was written" % options.output, file=sys.stderr)
        return 1
    if not TOOL_PYTHON.is_file():
        print("the Editor tool's Python is missing, at %s; make it with tools/editor/bootstrap.py "
              "(README.md)" % TOOL_PYTHON, file=sys.stderr)
        return 1
    round_trip(options.old, options.new, options.output)
    print("Wrote %s" % (options.output / "report.md"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
