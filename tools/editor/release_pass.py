"""Compares a new release of the Nextion Editor with the old release that
nxwright is tested with.

    python tools/editor/release_pass.py round-trip --old <program> --new <program> <output>
    python tools/editor/release_pass.py catalog --old <program> --new <program> <output>
    python tools/editor/release_pass.py models --old <program> --new <program> <output>
    python tools/editor/release_pass.py files --old <folder> --new <folder> <report.md>

Below, "the old Editor" and "the new Editor" are these two releases. The
script makes four comparisons:

- The round trip shows how the new Editor treats the projects that nxwright
  builds, beside how the old Editor treats them.
- The catalog comparison shows how the Attribute panel of the new Editor
  differs from the Attribute panel of the old Editor.
- The model comparison shows how each Editor's list of screen models
  differs from nxwright's table of screen models.
- The file comparison shows which files changed between the two releases.
  It compares the two folders that the releases' zips were unpacked into.

Run the script with nxwright's own Python, from nxwright's folder. Each
<program> is the program file of a Nextion Editor, such as "Nextion
Editor.exe" in the folder of its unpacked release zip. In the zips of 1.68.1
and 1.68.2, the program is "Nextion Editor.exe". In older zips, it is
NextionEditor.exe. The script drives each Editor through the Editor tool
(editor.py), which it runs with the tool's own Python. Each side runs under
its own Editor name (EDITOR_NAMES). The round trip and the catalog and model
comparisons create the folder <output>, write everything into it, and write
the findings to <output>/report.md. The file comparison writes only its
report.

For each project (round_trip_projects), the round trip first builds the
project with nxwright. It extracts the built file into a new folder, called
the baseline below. Then, with each Editor in turn, the round trip:

- has the Editor open the built file, compile it in its simulator, and save
  it;
- writes the `nxwright report` of the saved file;
- extracts the saved file into another new folder, and compares that folder
  with the baseline;
- compares the live blocks of the saved file with those of the built file.

A difference is a file in a folder, or a live block in a project file, that
only one side has, or that both sides have with different bytes. A changed
file or block comes with its runs. A run is a stretch of neighbouring bytes
that differ, given with where it starts and with its bytes on each side
(nxwright/project/byte_differences.py). The comparison leaves out the
directory of a project file, because each save adds to it. The differences
that the old Editor makes are taken as what any save changes. The findings
are the differences that only the new Editor makes (new_editor_only).

The catalog comparison runs catalog_variants.py under each Editor in turn,
and compares the two merged catalogs (compare_catalogs). Each run takes about
two hours. The model comparison has each Editor list its screen models with
`editor.py models`. It compares each list with nxwright's table
(compare_models). The file comparison compares the two folders by the
SHA-256 of each file (compare_files).
"""
import argparse
from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

# This file runs as a script, so it puts the folder above tools/ first on the import path.
NXWRIGHT_FOLDER = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(NXWRIGHT_FOLDER))

from nxwright import NxwrightError  # noqa: E402
from nxwright.project.byte_differences import CHANGED, Difference, compare_by_name  # noqa: E402
from nxwright.project.container import HmiContainer  # noqa: E402
from nxwright.project.device_settings import DeviceSettings  # noqa: E402
from nxwright.project.new_project import write_new_project  # noqa: E402
from nxwright.project.screen_models import MODELS, model_named  # noqa: E402
from nxwright.project.truetype import NOTO_SANS  # noqa: E402
from nxwright.source.project_files import build, extract  # noqa: E402
from nxwright.source.report import write_report  # noqa: E402
from nxwright.source.resource_adding import (add_animation, add_font, add_pictures,  # noqa: E402
                                             add_sound, add_video)
from nxwright.source.source_folder import new_source_folder  # noqa: E402
from tools.editor.catalog import choices_of, with_values  # noqa: E402

# The pictures and the sound that only the round trip uses. They are kept
# apart, so that the demo and the test fixtures stay free to change.
RESOURCES = Path(__file__).resolve().with_name("round_trip")
# The Editor tool, and the Python that runs it. README.md explains how to
# make that Python, under "Setting up the tool".
EDITOR_SCRIPT = Path(__file__).resolve().with_name("editor.py")
TOOL_PYTHON = Path(__file__).resolve().parent / "build" / "venv" / "Scripts" / "python.exe"
# The script that catalogs every attribute the Editor shows. It runs with
# the tool's Python too.
CATALOG_SCRIPT = Path(__file__).resolve().with_name("catalog_variants.py")
# Each side runs under its own Editor name, so that the two sides never share
# a dedicated Editor, even when both run the same program.
EDITOR_NAMES = {"old": "release-old", "new": "release-new"}
# For each series, the screen model of the small project made for that
# series. Each series stores pictures in its own form.
SERIES_MODELS = {"T": "NX4832T035", "K": "NX4832K035", "P": "NX8048P050", "E": "NX4880E043",
                 "F": "NX4832F035"}
# The fixture of the file browser tests, and the font that the fixture uses.
FILES_FIXTURE = NXWRIGHT_FOLDER / "tests" / "fixtures" / "files" / "app"
FILES_FIXTURE_FONT = NXWRIGHT_FOLDER / "tests" / "fixtures" / "fonts" / "Sans16.zi"
# The dump of the every-component project, which has one newly added
# component of each type. catalog_variants.py builds it with the device settings
# EVERY_COMPONENT_SETTINGS.
EVERY_COMPONENT = NXWRIGHT_FOLDER / "tests" / "fixtures" / "every-component"
EVERY_COMPONENT_SETTINGS = DeviceSettings(model_named("NX8048P070"), 180, "iso-8859-1")
_EVERY_COMPONENT_PAGE = Path("pages") / "00-page0.txt"
# The attributes that refer to a picture, an animation, a video, or a sound.
# In the every-component project, the new components refer to none (65535).
# The Editor's compile refuses that value, so the round trip sets each of
# these attributes to the first resource of its kind.
_RESOURCE_ATTRIBUTES = ("pic", "pic1", "pic2", "picc", "picc1", "picc2", "bpic", "ppic", "vid")
# The height in pixels of the font that the every-component project is given.
_FONT_HEIGHT = 16


def compare_folders(first: Path, second: Path) -> list:
    """Returns the Differences of the folder `second` from the folder
    `first`. Files are matched by their path inside their folder, written
    with /."""
    files = [{path.relative_to(folder).as_posix(): path for path in folder.rglob("*")
              if path.is_file()} for folder in (first, second)]
    return compare_by_name({name: path.read_bytes() for name, path in files[0].items()},
                           {name: path.read_bytes() for name, path in files[1].items()})


def new_editor_only(old: list, new: list) -> list:
    """Returns the Differences in `new`, the new Editor's, that are not in
    `old`, the old Editor's. A file or block that the new Editor adds or
    removes is kept, unless the old Editor added or removed it too. For a
    changed file or block, the result keeps each run that the old Editor did
    not make at the same place with the same bytes. A block that both
    Editors change, but in different ways, is kept."""
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


# The places that change from one save to the next, whatever the project.
# The comparison skips them. Each entry is (the name of a block or file,
# where a run starts), with a comment that explains what the place is. When
# the Nextion Editor 1.68.2 was compared with itself, it showed no such
# place. Its Save As of a project it had opened wrote every live block as
# nxwright built it.
SAVE_TO_SAVE = {}


@dataclass
class Side:
    """What one Editor made of one project. `folder` lists the differences
    of the extracted copy from the baseline, the built file extracted the
    same way. `blocks` lists the differences of the saved file from the
    built file. `findings` lists what else the run found: the warnings of
    extract, and each step that failed. `finished` is whether the run got as
    far as both comparisons."""
    folder: list = field(default_factory=list)
    blocks: list = field(default_factory=list)
    findings: list = field(default_factory=list)
    finished: bool = False


def round_trip_projects(work: Path) -> dict:
    """Writes the source folders of the round trip's projects in `work`, and
    returns {name: source folder}. The projects are the demo, the fixture
    of the file browser tests, the every-component project, and one small
    project of each series, with one picture."""
    projects = {}
    for name, source in (("demo", NXWRIGHT_FOLDER / "examples" / "thermostat" / "app"),
                         ("files", FILES_FIXTURE)):
        projects[name] = work / name
        shutil.copytree(source, projects[name])
    # The fixture uses a font that its folder does not contain. The
    # fixture's own tests copy the font in (tests/test_file_browsers.py).
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
    """Writes the source folder of the every-component project in `work`,
    and returns the folder. The project is built from its dump, the way
    catalog_variants.py builds it, then extracted into the folder. Each
    picture or media attribute of its components refers to the first
    resource of its kind. The function adds to the folder a font drawn from
    nxwright's own Noto Sans, and an animation, a video, and a sound made
    from RESOURCES, so that the Editor's compile accepts the project."""
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
    """Returns {component: {attribute: 0}} for the dump's page file
    `dump_page`. The result has each attribute of the page's objects that
    refers to a picture or a media resource (_RESOURCE_ATTRIBUTES)."""
    settings, component = {}, None
    for line in dump_page.split("\n"):
        if line.startswith("object "):
            component = line.split()[2]
        elif component is not None and line.startswith("  ") and line.strip():
            name = line.split()[0].split(":")[0]
            if name in _RESOURCE_ATTRIBUTES:
                settings.setdefault(component, {})[name] = 0
    return settings


def run_side(name: str, built: Path, baseline: Path, side: str, program: Path,
             output: Path) -> Side:
    """Runs one side of the round trip for the project `name`, in `output`,
    and returns the Side. `side` is "old" or "new", and `program` is the
    Editor of that side.

    The Editor opens `built`, the file built from the source folder,
    compiles it in its simulator, and saves it. Then this function
    writes the report of the saved file, and extracts the saved file into a
    new folder. It compares that folder with `baseline`, the built file
    extracted the same way, so that only the Editor's changes show. The
    function also compares the live blocks of the saved file with those of
    `built`.

    If a step of the Editor fails, the side tries again once, from `open`,
    in a fresh Editor. A busy Editor can fail a step once and pass it the
    next time. A step that fails twice is a finding, and the side stops
    there."""
    result = Side()
    output.mkdir(parents=True)
    saved = output / (name + ".HMI")
    environment = _environment(side, program)
    stopped = _saved_by_the_editor(built, saved, output, environment)
    if stopped is not None:
        # The first try may have saved the file before a later step stopped.
        # `save` would then refuse to write over that file on the second try.
        saved.unlink(missing_ok=True)
        stopped_again = _saved_by_the_editor(built, saved, output, environment)
        if stopped_again is not None:
            result.findings += [stopped, "on the second try: " + stopped_again]
            return result
        # The first failure is kept, so that an Editor that often fails shows
        # up over several passes.
        result.findings.append("the first try stopped, but the second try succeeded: "
                               + stopped)
    try:
        write_report(saved, output / (name + ".report.md"))
    except NxwrightError as error:
        result.findings.append("`nxwright report` refused the saved file: %s" % error)
    extracted = output / "folder"
    try:
        result.findings += ["extract: %s" % warning
                            for warning in extract(saved, extracted, continue_with_unknown=True,
                                                    keep_locks_without_password=True)]
        result.folder = compare_folders(baseline, extracted)
        result.blocks = _without_save_to_save(compare_by_name(
            HmiContainer.from_file(built).blocks, HmiContainer.from_file(saved).blocks))
    except NxwrightError as error:
        result.findings.append("nxwright could not read the saved file: %s" % error)
        return result
    result.finished = True
    return result


def _saved_by_the_editor(built: Path, saved: Path, output: Path, environment: dict):
    """Has the Editor that `environment` selects open `built`, compile it in
    its simulator, and save it as `saved`. The script holds that Editor for
    all of these steps (editor.py hold). Returns None when every step
    succeeds. When a step fails, the function closes the Editor, so that a
    second try starts afresh, and returns what stopped the step."""
    holder = "release-pass-%d" % os.getpid()
    steps = [("hold", holder), ("open", str(built), "--as", holder),
             ("simulate", str(output / "simulator.png"), "--as", holder),
             ("save", str(saved), "--as", holder)]
    try:
        for step in steps:
            done = editor_tool(environment, *step)
            if done.returncode != 0:
                # A dialog or a message that the step left open would stop
                # `quit`, so the commands before `quit` close them first.
                for closing in ("close-simulator", "close-file-dialog", "close-message", "quit"):
                    editor_tool(environment, closing, "--as", holder)
                return "`editor.py %s` stopped: %s" % (step[0],
                                                       (done.stderr or done.stdout).strip())
        return None
    finally:
        editor_tool(environment, "release", holder)


def _environment(side: str, program: Path) -> dict:
    """Returns the environment in which the Editor tool drives the Editor
    `program`, under the Editor name of `side`."""
    return dict(os.environ, NXWRIGHT_EDITOR=str(program), NXWRIGHT_EDITOR_NAME=EDITOR_NAMES[side])


def editor_tool(environment: dict, *command: str) -> subprocess.CompletedProcess:
    """Runs the Editor tool's `command` with the tool's Python, for the
    Editor that `environment` selects."""
    return subprocess.run([str(TOOL_PYTHON), str(EDITOR_SCRIPT), *command], cwd=NXWRIGHT_FOLDER,
                          env=environment, capture_output=True, text=True, encoding="utf-8",
                          errors="replace")


def _without_save_to_save(found: list) -> list:
    """Returns the Differences `found` without the runs that SAVE_TO_SAVE
    skips. A changed block that has no run left is dropped."""
    kept = []
    for each in found:
        runs = tuple(run for run in each.runs if (each.where, run[0]) not in SAVE_TO_SAVE)
        if each.kind != CHANGED or runs:
            kept.append(Difference(each.where, each.kind, runs))
    return kept


def round_trip(old: Path, new: Path, output: Path) -> str:
    """Runs the round trip of each project with the Editors `old` and `new`.
    Creates the folder `output` and writes everything in it. Returns the
    text of the report, and also writes the text to `output`/report.md."""
    output.mkdir(parents=True)
    work = output / "projects"
    work.mkdir()
    sections = []
    for name, source in round_trip_projects(work).items():
        built = output / name / (name + ".HMI")
        built.parent.mkdir(parents=True)
        try:
            build(source, built)
            # The extract of each side's saved file is compared with this
            # extract of the built file, so that only the Nextion Editor's
            # changes show. Both keep the pages' locks, so that a lock the
            # Nextion Editor adds shows too.
            baseline = output / name / "built-folder"
            extract(built, baseline, continue_with_unknown=True,
                    keep_locks_without_password=True)
        except NxwrightError as error:
            sections.append("## %s\n\nnxwright could not build or extract the project: %s\n"
                            % (name, error))
        else:
            sides = {side: run_side(name, built, baseline, side, program,
                                    output / name / side)
                     for side, program in (("old", old), ("new", new))}
            sections.append(_section(name, sides["old"], sides["new"]))
        # The report is written after each project, so that a run that stops
        # later keeps the sections written so far.
        text = ("# The round trip\n\nThe old Editor: %s\n\nThe new Editor: %s\n\n%s"
                % (old, new, "\n".join(sections)))
        (output / "report.md").write_text(text, encoding="utf-8", newline="\n")
    return text


def _section(name: str, old: Side, new: Side) -> str:
    """Returns the section of the report for the project `name`. The section
    lists what the old Editor's save changes, then the findings: what only
    the new Editor changes, and what else each side found. When the old
    Editor's run did not finish, the new Editor's changes cannot be told
    apart from what any save changes. The section then lists all of the new
    Editor's changes, under a note that explains why."""
    lines = ["## %s" % name, ""]
    if old.finished:
        lines += ["### What the old Editor changes", ""]
        lines += _listed(old.folder, "source folder") + _listed(old.blocks, "project file")
        lines += ["", "### What the new Editor alone changes", ""]
        if new.finished:
            lines += _listed(new_editor_only(old.folder, new.folder), "source folder")
            lines += _listed(new_editor_only(old.blocks, new.blocks), "project file")
        else:
            lines.append("The new Editor's run did not finish. The section below shows where "
                         "it stopped.")
    else:
        lines += ["### What the new Editor changes", "",
                  "The old Editor's run did not finish, as the section below shows. These "
                  "changes may therefore include what any save changes.", ""]
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
    """Returns a line for each Difference in `found`, with a line under it
    for each of its runs. `what` is where the differences are, "source
    folder" or "project file". Returns a single line when `found` is
    empty."""
    if not found:
        return ["- In the %s: no differences." % what]
    lines = []
    for each in found:
        lines.append("- In the %s, `%s`: %s" % (what, each.where, each.kind))
        lines += ["  - at offset %d: %s became %s" % (start, first.hex(" ") or "nothing",
                                                       second.hex(" ") or "nothing")
                  for start, first, second in each.runs]
    return lines


# The kinds of difference between two catalogs. A hint's list of choices
# changes with the hint, but is reported on its own, because the choices
# decide the values that a page file may set. COLOUR_CHANGED is about the
# colour of an attribute's name. A name shows green when code may change
# the attribute, and black when code may not.
TYPE_ADDED, TYPE_REMOVED = "type added", "type removed"
ATTRIBUTE_ADDED, ATTRIBUTE_REMOVED = "attribute added", "attribute removed"
HINT_CHANGED, CHOICES_CHANGED, COLOUR_CHANGED = "hint changed", "choices changed", "colour changed"


@dataclass(frozen=True)
class ListedDifference:
    """An item that an Editor lists, `where`, that differs by `kind` between
    two lists. The lists are two Editors' catalogs, or an Editor's screen
    models and nxwright's table of screen models. For a change, `old` is the
    value in the first list, and `new` is the value in the second."""
    where: str
    kind: str
    old: str = None
    new: str = None


def compare_catalogs(old: dict, new: dict) -> list:
    """Returns the ListedDifferences of the merged catalog `new` from the
    merged catalog `old`. Each catalog is in the form that
    catalog_variants.py writes to merged.json: {type name: {attribute:
    {"hint", "green", "black", "values"}}}. The comparison counts the colours
    that an attribute's name showed in, but not the variants it showed them
    under."""
    found = []
    for name in sorted(set(old) | set(new)):
        if name not in old:
            found.append(ListedDifference(name, TYPE_ADDED))
        elif name not in new:
            found.append(ListedDifference(name, TYPE_REMOVED))
        else:
            found += _attribute_differences(name, old[name], new[name])
    return found


def _attribute_differences(type_name: str, old: dict, new: dict) -> list:
    """Returns the ListedDifferences of the attributes `new` from the
    attributes `old`, both of the type `type_name`."""
    found = []
    for attribute in sorted(set(old) | set(new)):
        where = "%s, %s" % (type_name, attribute)
        if attribute not in old:
            found.append(ListedDifference(where, ATTRIBUTE_ADDED))
            continue
        if attribute not in new:
            found.append(ListedDifference(where, ATTRIBUTE_REMOVED))
            continue
        before, after = old[attribute], new[attribute]
        if before["hint"] != after["hint"]:
            found.append(ListedDifference(where, HINT_CHANGED, before["hint"], after["hint"]))
        choices = [_choices_text(choices_of(each["hint"])) for each in (before, after)]
        if choices[0] != choices[1]:
            found.append(ListedDifference(where, CHOICES_CHANGED, *choices))
        colours = [_colours(each) for each in (before, after)]
        if colours[0] != colours[1]:
            found.append(ListedDifference(where, COLOUR_CHANGED, *colours))
    return found


def _choices_text(choices: dict) -> str:
    """Returns the choices {number: label} in the form a hint lists them,
    such as "0-crop image;1-solid color"."""
    return ";".join("%d-%s" % (number, label) for number, label in sorted(choices.items()))


def _colours(seen: dict) -> str:
    """Returns the colours that the name of the attribute `seen` showed in:
    "green", "black", or "green and black"."""
    return " and ".join(colour for colour in ("green", "black") if seen[colour])


def catalog(old: Path, new: Path, output: Path) -> str:
    """Runs catalog_variants.py under the Editors `old` and `new` in turn.
    Creates the folder `output`, and gives each run its own folder in it.
    The output of each run goes to catalog_variants.log in its folder.
    Returns the text of the report, and also writes the text to
    `output`/report.md. If the old Editor's catalog is not written, the new
    Editor does not run, because its catalog would have nothing to be
    compared with."""
    output.mkdir(parents=True)
    merged, stopped = {}, []
    for side, program in (("old", old), ("new", new)):
        folder = output / side
        folder.mkdir()
        environment = _environment(side, program)
        with open(folder / "catalog_variants.log", "w", encoding="utf-8") as log:
            done = subprocess.run([str(TOOL_PYTHON), str(CATALOG_SCRIPT), str(folder)],
                                  cwd=NXWRIGHT_FOLDER, env=environment,
                                  stdout=log, stderr=subprocess.STDOUT)
        # The Editor is closed, so that it does not keep running beside the
        # next Editor for hours.
        editor_tool(environment, "quit")
        # catalog_variants.py also exits with 1 after writing its catalog,
        # when one of nxwright's descriptions equals an Editor's hint. The
        # run therefore counts as finished when merged.json exists, whatever
        # the exit code.
        if (folder / "merged.json").is_file():
            merged[side] = json.loads((folder / "merged.json").read_text(encoding="utf-8"))
        else:
            stopped.append("The %s Editor's catalog was not written. catalog_variants.py exited "
                           "with %d, and its output is in %s/catalog_variants.log."
                           % (side, done.returncode, side))
            break
    found = compare_catalogs(merged["old"], merged["new"]) if not stopped else None
    text = catalog_report(old, new, found, stopped)
    (output / "report.md").write_text(text, encoding="utf-8", newline="\n")
    return text


def catalog_report(old: Path, new: Path, found: list, stopped: list) -> str:
    """Returns the report of the catalog comparison of the Editors `old` and
    `new`. The report lists the ListedDifferences `found`. If a catalog was
    not written, the report has the lines of `stopped` instead."""
    lines = ["# The catalogs of two Nextion Editors", "", "The old Editor: %s" % old, "",
             "The new Editor: %s" % new, ""]
    return "\n".join(lines + (stopped or _difference_lines(found))) + "\n"


def _difference_lines(found: list) -> list:
    """Returns the lines of a report for the ListedDifferences `found`. When
    `found` is empty, returns the single line "Nothing differs."."""
    lines = []
    for each in found:
        line = "- `%s`: %s" % (each.where, each.kind)
        if each.old is not None or each.new is not None:
            line += ", from \"%s\" to \"%s\"" % (each.old, each.new)
        lines.append(line)
    return lines or ["Nothing differs."]


# The kinds of difference between an Editor's list of screen models and
# nxwright's table of them.
MODEL_ADDED, MODEL_REMOVED, MODEL_RESIZED = "model added", "model removed", "model resized"


def compare_models(listed: list, table=MODELS) -> list:
    """Returns the ListedDifferences of the screen models `listed` from
    nxwright's table of screen models, `table`. `listed` is in the form that
    `editor.py models` writes (model_list.py). The list does not give the
    names of its models, so each model is matched by its series, inches,
    width, and height. A model of the table may be missing from the list
    while the list has exactly one unmatched model of the same series and
    inches. That unmatched model is then taken to be the table's model,
    resized."""
    unmatched = list(listed)
    missing = []
    for model in table:
        same = next((each for each in unmatched
                     if _told_by(each) == (model.series, model.inches, model.width,
                                           model.height)), None)
        if same is None:
            missing.append(model)
        else:
            unmatched.remove(same)
    found = []
    for model in missing:
        others = [each for each in unmatched
                  if _told_by(each)[:2] == (model.series, model.inches)]
        if len(others) == 1:
            unmatched.remove(others[0])
            found.append(ListedDifference(model.name, MODEL_RESIZED,
                                          "%dx%d" % (model.width, model.height),
                                          "%dx%d" % (others[0]["width"], others[0]["height"])))
        else:
            found.append(ListedDifference(model.name, MODEL_REMOVED))
    found += [ListedDifference("%s, %.1f inches, %dx%d" % _told_by(each), MODEL_ADDED)
              for each in unmatched]
    return found


def _told_by(listed: dict) -> tuple:
    """Returns what tells the model `listed` apart from the others: its
    series, its inches rounded to one decimal, its width, and its height."""
    return listed["series"], round(listed["inch"], 1), listed["width"], listed["height"]


def models(old: Path, new: Path, output: Path) -> str:
    """Has the Editors `old` and `new` in turn list the screen models of
    their device settings (`editor.py models`), and compares each list with
    nxwright's table of screen models. Creates the folder `output`. Returns
    the text of the report, and also writes the text to `output`/report.md.
    Each list is compared with the table, not with the other list, so the
    new Editor runs even when the old Editor's run stops."""
    output.mkdir(parents=True)
    # The Editor shows its device settings only while a project is open.
    source = output / "project"
    new_source_folder(source, DeviceSettings(model_named(SERIES_MODELS["T"]), 0, "iso-8859-1"),
                      "nxlang")
    project = output / "project.HMI"
    build(source, project)
    sections = []
    for side, program in (("old", old), ("new", new)):
        listed = output / (side + ".json")
        stopped = _listed_by_the_editor(project, listed, _environment(side, program))
        lines = ([stopped] if stopped is not None else _difference_lines(
            compare_models(json.loads(listed.read_text(encoding="utf-8"))["models"])))
        sections.append("## The %s Editor: %s\n\n%s\n" % (side, program, "\n".join(lines)))
    text = ("# The screen models of two Nextion Editors\n\nEach Editor's list of screen "
            "models, compared with nxwright's table of screen models.\n\n"
            + "\n".join(sections))
    (output / "report.md").write_text(text, encoding="utf-8", newline="\n")
    return text


def _listed_by_the_editor(project: Path, listed: Path, environment: dict):
    """Has the Editor that `environment` selects open `project` and write
    its list of screen models to `listed`. Closes the Editor, then returns
    None when every step succeeds, or else what stopped the step."""
    try:
        for step in (("open", str(project)), ("models", str(listed))):
            done = editor_tool(environment, *step)
            if done.returncode != 0:
                # A message that the step left open would stop `quit`.
                editor_tool(environment, "close-message")
                return "`editor.py %s` stopped: %s" % (step[0],
                                                       (done.stderr or done.stdout).strip())
        return None
    finally:
        editor_tool(environment, "quit")


def compare_files(old: Path, new: Path) -> list:
    """Returns the Differences of the folder `new` from the folder `old`.
    Files are matched by their path inside their folder, written with /.
    Two files differ when their SHA-256 digests differ. A changed file comes
    without runs."""
    digests = [{path.relative_to(folder).as_posix(): _sha256(path) for path in folder.rglob("*")
                if path.is_file()} for folder in (old, new)]
    return [Difference(each.where, each.kind) for each in compare_by_name(*digests)]


def _sha256(path: Path) -> bytes:
    """Returns the SHA-256 digest of the file `path`. The file is read a
    megabyte at a time."""
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(1 << 20), b""):
            digest.update(chunk)
    return digest.digest()


def files_report(old: Path, new: Path, found: list) -> str:
    """Returns the report of the file comparison of the release folders
    `old` and `new`. The report lists each Difference in `found`."""
    lines = ["# The files of two Nextion Editor releases", "", "The old release: %s" % old, "",
             "The new release: %s" % new, ""]
    lines += ["- `%s`: %s" % (each.where, each.kind) for each in found] or ["Nothing differs."]
    return "\n".join(lines) + "\n"


def _with_editors(command, help_text: str):
    """Adds the options of a comparison that drives the old and the new
    Editor to the subcommand parser `command`. `help_text` is the help of
    the output argument."""
    command.add_argument("--old", type=Path, required=True,
                         help="the program file of the old Nextion Editor")
    command.add_argument("--new", type=Path, required=True,
                         help="the program file of the new Nextion Editor")
    command.add_argument("output", type=Path, help=help_text)


def main(arguments: list = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    _with_editors(commands.add_parser("round-trip", help="show how a new Nextion Editor treats "
                                      "nxwright's projects, compared with the old one"),
                  "the folder to create for the results; it must not exist yet")
    _with_editors(commands.add_parser("catalog", help="show how the Attribute panel of a new "
                                      "Nextion Editor differs from the old one"),
                  "the folder to create for the results; it must not exist yet")
    _with_editors(commands.add_parser("models", help="compare each Nextion Editor's list of "
                                      "screen models with nxwright's table of screen models"),
                  "the folder to create for the results; it must not exist yet")
    files = commands.add_parser("files", help="list the files that differ between two releases, "
                                "given the folders that their zips were unpacked into")
    files.add_argument("--old", type=Path, required=True,
                       help="the folder of the old release")
    files.add_argument("--new", type=Path, required=True,
                       help="the folder of the new release")
    files.add_argument("output", type=Path,
                       help="the report file to create; it must not exist yet")
    options = parser.parse_args(arguments)
    if options.output.exists():
        print("%s already exists. Nothing was written." % options.output, file=sys.stderr)
        return 1
    if options.command == "files":
        for folder in (options.old, options.new):
            if not folder.is_dir():
                print("%s is not a folder. Nothing was written." % folder, file=sys.stderr)
                return 1
        found = compare_files(options.old, options.new)
        options.output.parent.mkdir(parents=True, exist_ok=True)
        with open(options.output, "x", encoding="utf-8", newline="\n") as report:
            report.write(files_report(options.old, options.new, found))
        print("Wrote %s" % options.output)
        return 0
    if not TOOL_PYTHON.is_file():
        print("The Editor tool's Python is missing: %s does not exist. Make it with "
              "tools/editor/bootstrap.py. tools/editor/README.md gives the steps."
              % TOOL_PYTHON, file=sys.stderr)
        return 1
    if options.command == "catalog":
        catalog(options.old, options.new, options.output)
    elif options.command == "models":
        models(options.old, options.new, options.output)
    else:
        round_trip(options.old, options.new, options.output)
    print("Wrote %s" % (options.output / "report.md"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
