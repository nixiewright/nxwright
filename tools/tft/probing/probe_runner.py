"""The probe runner: it checks nxwright's output against the TFT files the
Nextion Editor writes for small projects, and keeps the checked output as
the tests' fixtures. A compile is right only when its file is byte for byte
the Nextion Editor's, so the Editor's file is the one measure, and nxwright's
checked output is what the tests then keep.

A probe (Probe) is a project that nxwright builds from a base folder, with
one change. The base folders are in probes/, one blank project per series,
made by `nxwright new` (make_base_folders). For each probe, the runner
(run_probes):

1. builds the probe's project, in a folder of its own that is deleted after;
2. has the agent's own Nextion Editor write the project's TFT file, under
   build/tft/, through nxwright's Editor tool (EditorTool);
3. compares each piece of nxwright's output that the probe names with the same
   piece cut from the Nextion Editor's file;
4. if every piece matches, writes nxwright's pieces as the probe's fixtures, if
   the probe keeps any, records the probe as matched, and deletes the TFT
   file. If a piece differs, it says where, and keeps the TFT file as
   build/kept/<probe>.tft until the probe matches or the agent drops it.

The pieces a probe compares and keeps, one file each, are its parts, such
as all its pages' blocks. Beside them, pieces.json gives where each smaller
piece lies among the parts, such as one object's memory, so that a unit test
reads exactly the bytes it compares, and where each component lies, its
first entry, its base, and where its texts and buffer lie, so that the test
gives the component's type the same place (Parts). cut_probes writes it again for
probes kept before, as when a kind of piece is added.

The record lists each probe matched by the SHA-256 of the project it built,
as nxwright builds the same bytes from the same folder. A later run skips a
probe the record lists, unless nxwright's output for it is no longer its
fixtures', or the run is told to check it again. The record serves
to resume a run: the tests, not the record, show that nxwright's output still
matches. Nothing the Nextion Editor writes is hashed, or kept past its check.

Under build/, the runner deletes only files it wrote, one at a time, each
by its full path (delete_built_file). Each probe's project is built in a
temporary folder of its own, which Python's tempfile deletes after.

Every probe's project is built under one name, probe.HMI. The Editor tool
keeps a copy of each project it opens, by the project's name, so one name
keeps it to two copies, probe.HMI and probe (2).HMI, whatever the number of
probes.
"""
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass, field
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
from typing import Callable, Optional

from nxwright import NxwrightError

from nxwright.tft.firmware_versions import version_text
from nxwright.tft.tft_file import TftFileError, read_tft

# The runner's folders, found from this module's place, never from the
# working folder or an argument. build/ and probes/ are in the tool's own
# folder, tools/tft/, and the fixtures are in nxwright's tests. build/
# contains what the runner writes and deletes, and git ignores it.
_TOOL = Path(__file__).resolve().parents[1]
BUILD = _TOOL / "build"
FIXTURES = _TOOL.parents[1] / "tests" / "tft" / "fixtures"
BASES = _TOOL / "probes"
# Each series' base folder, by its letter: the screen model `nxwright new`
# makes it for, as the research note's blank probes were.
BASE_MODELS = {"T": "NX4832T035", "K": "NX4832K035", "P": "NX8048P050", "E": "NX4848E040",
               "F": "NX4832F035"}
# The name every probe's project is built under (the module's docstring).
_PROJECT = "probe.HMI"
# Under BUILD: the record, the folder the Nextion Editor writes its TFT files
# in, and the folder that keeps those of probes that do not match yet.
_RECORD = "matched.json"
# The table of where each piece lies, beside a probe's fixtures (Parts).
_PIECES = "pieces.json"
_TFT = "tft"
_KEPT = "kept"
# A probe's or a piece's name names files, so it is kept to these characters.
_NAME = re.compile(r"[A-Za-z0-9_-]+")
# The Editor tool's own Python, which has the packages it needs, from nxwright's
# folder.
_TOOL_PYTHON = Path("tools", "editor", "build", "venv", "Scripts", "python.exe")
# How many bytes of each side a difference shows, before and after it.
_AROUND = 8


class ProbeError(Exception):
    """A run that cannot go on, such as the Editor tool failing to open a
    probe's project. Its message says why."""


class CouldNotRun(ProbeError):
    """A probe that could not run, as when the Nextion Editor refused its
    project, or a firmware file could not be read. A run lists it apart,
    with why, and goes on (run_probes)."""


class ProbeMismatch(Exception):
    """A Nextion Editor's file that a probe cannot cut its pieces from, as
    when a checksum it states does not hold. Its message says what."""


@dataclass(frozen=True)
class Probe:
    """One probe: what every phase gives the runner to check a piece of
    nxwright's output.

    - name: names the probe's files, so it is made of letters, digits, `_`,
      and `-`, and unique among the probes of a run.
    - base: the series whose base folder it starts from, such as "T".
    - change: changes a copy of that folder, given the copy's path. None for
      the base folder as it is.
    - ours: nxwright's output for the built project, given the project's path,
      as {piece's name: its bytes}. Piece names follow the probe's rule. When
      `borrows` is set, it is called as ours(project, borrowed) instead. None
      for a probe of an older Nextion Editor, whose files nxwright does not
      write: its file is kept, not compared (kept_from_the_editor).
    - theirs: the same pieces, cut from the Nextion Editor's TFT file, given
      its bytes. It raises ProbeMismatch for a file it cannot cut them from.
    - fixtures: the folder under tests/fixtures/ that keeps its fixtures, or
      None when it keeps none. Only the fewest probes that show a piece keep
      fixtures; the others are checked once, and those few guard what they
      showed.
    - kept: the pieces kept as fixtures when they are not those compared,
      as packaging's, which are made on zeros for the firmware; None to keep
      those of `ours`. It never borrows: it is recomputed once the Nextion
      Editor's file is gone.
    - borrows: what nxwright's output borrows from the Nextion Editor's file
      while nxwright cannot write it yet, such as the user code that packaging
      packages, given the file's bytes; None when it borrows nothing. It
      raises ProbeMismatch for a file it cannot cut that from. A probe that
      borrows, and keeps fixtures, must give `kept`.
    - built_change: changes the project file nxwright built, given its path,
      before the Nextion Editor opens it, as an older Editor may need
      something nxwright does not write; None for no change.
    """
    name: str
    base: str
    change: Optional[Callable[[Path], None]]
    ours: Callable
    theirs: Callable[[bytes], dict]
    fixtures: Optional[str] = None
    kept: Optional[Callable[[Path], dict]] = None
    borrows: Optional[Callable[[bytes], object]] = None
    built_change: Optional[Callable[[Path], None]] = None


@dataclass
class RunResult:
    """What a run did: the names of the probes it checked and found to
    match, those it skipped as recorded, and those that did not match. And
    {name: why} of the probes it could not run, as when the Nextion Editor
    refused a probe's project, or a firmware file is missing."""
    matched: list
    skipped: list
    failed: list
    could_not_run: dict = field(default_factory=dict)


class Parts(dict):
    """A probe's parts, {part's name: its bytes}, as its `ours` or `kept`
    gives them, with `pieces`, where each of its pieces lies among them,
    {piece's name: (part's name, start, end)}, and `places`, where each of
    its components lies, {"page0-1": the fields of its
    component_types.ObjectPlace}. A plain dict of parts, or `pieces` None,
    keeps each part as one piece of the same name, and no places."""

    def __init__(self, parts: dict, pieces: dict = None, places: dict = None):
        super().__init__(parts)
        self.pieces = pieces
        self.places = places


def piece_table(probe: Probe, parts: dict) -> dict:
    """Returns where each piece of the probe's `parts` lies, {piece's name:
    [part's name, start, end]} (Parts). Raises ProbeError, naming the probe,
    when the pieces of a part, put back together, do not give it: when one
    lies outside it or is empty, two overlap, or a byte lies in none."""
    pieces = getattr(parts, "pieces", None)
    if pieces is None:
        pieces = {name: (name, 0, len(data)) for name, data in parts.items() if data}
    by_part = {}
    for name, (part, start, end) in pieces.items():
        if part not in parts:
            raise ProbeError("%s: the piece %s lies in %s, which is not one of its parts"
                             % (probe.name, name, part))
        by_part.setdefault(part, []).append((start, end, name))
    for part, data in parts.items():
        at = 0
        for start, end, name in sorted(by_part.get(part, [])):
            if start != at or not start < end <= len(data):
                raise ProbeError("%s: the piece %s, from %d to %d of %s, does not follow the "
                                 "pieces before it, which end at %d, within its %d bytes"
                                 % (probe.name, name, start, end, part, at, len(data)))
            at = end
        if at != len(data):
            raise ProbeError("%s: the pieces of %s end at %d of its %d bytes"
                             % (probe.name, part, at, len(data)))
    return {name: list(place) for name, place in pieces.items()}


@dataclass
class CutResult:
    """What a cut did: the names of the probes it wrote pieces.json for, and
    for each of those whose checks failed, why."""
    cut: list
    failed: dict


def cut_probes(probes: list, say=print) -> CutResult:
    """Writes pieces.json for each probe of `probes` that keeps fixtures,
    without the Nextion Editor: it builds the probe's project, checks that
    nxwright's parts are still the probe's fixtures, byte for byte, as the
    Nextion Editor confirmed them, then that the pieces put back together
    give each part (piece_table). It writes nothing for a probe whose checks
    fail. `say` is given a line for each probe. Raises ProbeError for
    probes whose names clash or break the rule, and for a probe with
    nothing of nxwright's to compare (_refuse_uncompared)."""
    _refuse_bad_probes(probes)
    _refuse_uncompared(probes)
    result = CutResult([], {})
    for probe in probes:
        if probe.fixtures is None:
            continue
        folder = FIXTURES / probe.fixtures / probe.name
        with tempfile.TemporaryDirectory(prefix="nxwright-cut-") as work:
            project = _built(probe, Path(work))
            parts = (probe.kept or probe.ours)(project)
        fixtures = {file.stem: file.read_bytes() for file in folder.glob("*.bin")}
        why = _first_difference(parts, fixtures)
        if why is None:
            try:
                _write_piece_table(probe, piece_table(probe, parts),
                                   getattr(parts, "places", None))
            except ProbeError as error:
                why = str(error)
        else:
            why = "nxwright's parts are not its fixtures: " + why
        if why is None:
            result.cut.append(probe.name)
            say("%s: cut" % probe.name)
        else:
            result.failed[probe.name] = why
            say("%s: not cut, %s" % (probe.name, why))
    return result


def run_probes(probes: list, tool, again: set = frozenset(), say=print) -> RunResult:
    """Checks each probe of `probes`, in order, with `tool`, which writes a
    project's TFT file (EditorTool), and returns what it did. The probes
    named in `again` are checked whatever the record lists. `say` is given a
    line for each probe checked. Raises ProbeError for names that clash or
    break the rule, and for a probe that borrows and keeps fixtures without
    `kept`.

    A probe that cannot run is listed apart, with why, and the run goes on:
    one whose project nxwright's build refuses, or its compile refuses, one whose firmware file cannot be read, and one the tool stops
    on, as when the Nextion Editor refuses its project."""
    _refuse_bad_probes(probes)
    _refuse_uncompared(probes)
    unknown = sorted(set(again) - {probe.name for probe in probes})
    if unknown:
        raise ProbeError("no probe is named %s" % ", ".join(unknown))
    record = _read_record()
    result = RunResult([], [], [])
    for probe in probes:
        try:
            difference = _difference(probe, tool, record, probe.name in again)
        except (CouldNotRun, NxwrightError) as error:
            result.could_not_run[probe.name] = str(error)
            say("%s: could not run: %s" % (probe.name, error))
            continue
        if difference is _SKIPPED:
            result.skipped.append(probe.name)
        elif difference is None:
            result.matched.append(probe.name)
            say("%s: matches" % probe.name)
        else:
            result.failed.append(probe.name)
            say("%s: %s; the Nextion Editor's file is kept as %s"
                % (probe.name, difference, BUILD / _KEPT / (probe.name + ".tft")))
    return result


# What _difference returns for a probe skipped as recorded.
_SKIPPED = object()


def _difference(probe: Probe, tool, record: dict, again: bool):
    """Checks `probe` with `tool` (_checked), unless `record` lists it as
    matched by the same project, its fixtures still hold, and it is not
    checked `again`. Returns _SKIPPED for a probe skipped, None for one that
    matches, which the record then lists, or else where it differs."""
    # A folder of its own for each probe, deleted after: a project is about
    # 7 MB, and a run may build thousands.
    with tempfile.TemporaryDirectory(prefix="nxwright-probe-") as work:
        project = _built(probe, Path(work))
        digest = sha256(project.read_bytes()).hexdigest()
        if not again and record.get(probe.name) == digest and _fixtures_hold(probe, project):
            return _SKIPPED
        # Out of the record until it matches again, so that a run that stops
        # here checks it again.
        if record.pop(probe.name, None) is not None:
            _write_record(record)
        difference = _checked(probe, project, tool)
    if difference is None:
        record[probe.name] = digest
        _write_record(record)
    return difference


def drop(name: str) -> bool:
    """Deletes the Nextion Editor's file kept for the probe `name`, which did
    not match, as when the agent drops the probe. Returns whether there was
    one."""
    kept = BUILD / _KEPT / (name + ".tft")
    if not _NAME.fullmatch(name) or not kept.exists():
        return False
    delete_built_file(kept)
    return True


def kept_from_the_editor(probes: list, tool, version: tuple, say=print):
    """Has `tool`'s Nextion Editor write each probe of `probes`' TFT file,
    and keeps the pieces the probe's `theirs` cuts from it as the probe's
    fixtures, comparing them with nothing: the probes are of an older
    Nextion Editor, of `version`, such as (1, 63, 3), whose files nxwright does
    not write. `say` is given a line for each probe kept. Raises ProbeError,
    keeping no fixtures of the probe, for a probe that keeps none, and for a
    file of another version, as when NXWRIGHT_EDITOR names another Nextion
    Editor than the probes are of. Every file is checked before any probe's
    fixtures are written, so that a refused run keeps none."""
    _refuse_bad_probes(probes)
    without = [probe.name for probe in probes if probe.fixtures is None]
    if without:
        raise ProbeError("probes of an older Nextion Editor are kept as fixtures, which these "
                         "keep none of: %s" % ", ".join(without))
    pieces = []
    for probe in probes:
        data = editor_tft(probe, tool)
        try:
            written = read_tft(data, "the Nextion Editor's file", check=False).version
        except TftFileError as error:
            raise ProbeError("%s: the Nextion Editor's file could not be read: %s"
                             % (probe.name, error)) from None
        if written != tuple(version):
            raise ProbeError("%s: the Nextion Editor's file is of %s, not %s: NXWRIGHT_EDITOR "
                             "names another Nextion Editor" % (probe.name, version_text(written),
                                                              version_text(version)))
        pieces.append(probe.theirs(data))
    for probe, kept in zip(probes, pieces):
        _write_fixtures(probe, kept)
        say("%s: kept, as the Nextion Editor %s writes it" % (probe.name, version_text(version)))


def editor_tft(probe: Probe, tool) -> bytes:
    """Returns the bytes of the Nextion Editor's TFT file of `probe`'s
    project, which `tool` writes (EditorTool), and deletes the file. It
    compares nothing and records nothing, so that research can read a file
    that no probe checks yet."""
    with tempfile.TemporaryDirectory(prefix="nxwright-probe-") as work:
        tft = tool.write_tft(_built(probe, Path(work)), BUILD / _TFT)
    try:
        return tft.read_bytes()
    finally:
        delete_built_file(tft)


def delete_built_file(path: Path):
    """Deletes the file `path`, which the runner wrote under build/, and that
    file alone. Raises ValueError, deleting nothing, when the file is not one
    it may delete (refuse_unless_deletable)."""
    refuse_unless_deletable(path)
    path.unlink()


def refuse_unless_deletable(path: Path):
    """Raises ValueError unless `path` is a regular file strictly below
    build/, once both are resolved, links and `..` followed. A link, even to
    a file below build/, a folder, and any file when build/ is itself a link
    are refused. It reads the paths, and deletes nothing."""
    if path.is_symlink():
        raise ValueError("%s is a link, which the probe runner never deletes" % path)
    build = BUILD.resolve()
    # A build/ that is itself a link, or a junction, would put "below it"
    # wherever it points.
    if build != BUILD.absolute():
        raise ValueError("%s leads to %s, so the probe runner deletes nothing there"
                         % (BUILD, build))
    resolved = Path(path).resolve()
    if build not in resolved.parents:
        raise ValueError("%s is not below %s, where the probe runner may delete" % (path, build))
    if not resolved.is_file():
        raise ValueError("%s is not a file, so the probe runner does not delete it" % path)


def make_base_folders(series: list = None) -> list:
    """Writes the base folder of each of `series`, all of BASE_MODELS' by
    default, in probes/, as `nxwright new` does: one blank page, and Noto
    Sans at 24 pixels, for BASE_MODELS' screen model at 0 degrees, in
    iso-8859-1 and nxlang. Returns the warnings nxwright gives, such as of
    characters the font leaves out. Raises ProbeError, writing nothing, when
    one of the folders is already there. The probes' projects, and so their
    fixtures, come from these folders, so they are made again only on
    purpose, when nxwright changes what `nxwright new` writes."""
    # nxwright's library, not its command line, which loads every package
    # nxwright uses, some of which the Editor tool's Python lacks.
    from nxwright.project.device_settings import DeviceSettings
    from nxwright.project.screen_models import model_named
    from nxwright.source.source_folder import NXLANG, new_source_folder
    series = list(BASE_MODELS) if series is None else series
    there = [letter for letter in series if (BASES / letter).exists()]
    if there:
        raise ProbeError("the base folders of %s are already in %s"
                         % (", ".join(there), BASES))
    warnings = []
    for letter in series:
        settings = DeviceSettings(model_named(BASE_MODELS[letter]), 0, "iso-8859-1")
        warning = new_source_folder(BASES / letter, settings, NXLANG, letter)
        if warning:
            warnings.append("%s: %s" % (letter, warning))
    return warnings


class EditorTool:
    """nxwright's Editor tool, driving the agent's own dedicated Nextion
    Editor. Its commands run in this process, through the tool's main, which
    saves starting Python, and loading the tool's packages, for each one.
    Used in a `with` block, it holds the Editor for the run, so that no one
    else's command comes between a probe's open and its TFT file.

    It needs NXWRIGHT_EDITOR_NAME, as each agent probes with its own Nextion
    Editor, and the tool's own Python, which has the packages the tool
    needs. A command that stops the tool raises ProbeError. One that never
    returns ends this process, through the tool's watchdog, and a run
    started again goes on where it was."""

    def __init__(self):
        if not os.environ.get("NXWRIGHT_EDITOR_NAME"):
            raise ProbeError("NXWRIGHT_EDITOR_NAME is not set: each agent probes with its own "
                             "Nextion Editor")
        try:
            from tools.editor import editor
        except ImportError as error:
            raise ProbeError("nxwright's Editor tool could not be loaded (%s): run with its "
                             "Python, %s" % (error, _TOOL_PYTHON)) from None
        self._editor = editor
        self._holder = "nxwright-probe-%d" % os.getpid()

    def __enter__(self):
        self._command("hold", self._holder)
        return self

    def __exit__(self, *_):
        # A release that fails warns, so that the error that stopped the
        # run, if any, is the one raised.
        try:
            self._command("release", self._holder)
        except ProbeError as error:
            print("probe: the hold %s on the Editor was not released, and lasts until its "
                  "time ends: %s" % (self._holder, error), file=sys.stderr)

    def write_tft(self, project: Path, folder: Path) -> Path:
        """Opens `project` in the Editor, has it write the project's TFT file
        in `folder`, and returns the file's path."""
        self._command("open", "--as", self._holder, str(project))
        output = self._command("tft", "--as", self._holder, str(folder))
        first = output.splitlines()[0] if output else ""
        if not first.startswith("Wrote "):
            raise ProbeError("the Editor tool's tft command printed %r, not the file it wrote"
                             % first)
        return Path(first[len("Wrote "):])

    def close_messages(self) -> str:
        """Closes the messages the Editor shows, as one that a command stopped
        on, and returns what each said, as the tool's close-message prints
        it."""
        return "\n".join(self._command("close-message", "--as", self._holder).splitlines())

    def _command(self, *arguments: str) -> str:
        # The tool sets its standard output to UTF-8, which a text wrapper
        # over bytes allows and a StringIO does not.
        output = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
        errors = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
        with redirect_stdout(output), redirect_stderr(errors):
            code = self._editor.main(list(arguments))
        if code != 0:
            raise ProbeError("the Editor tool's %s command: %s"
                             % (arguments[0], _text(errors).strip()))
        return _text(output)


def _text(wrapper) -> str:
    wrapper.flush()
    return wrapper.buffer.getvalue().decode("utf-8")


def _refuse_uncompared(probes: list):
    """Raises ProbeError for the probes of `probes` with nothing of nxwright's to
    compare, those of an older Nextion Editor, whose `ours` is None."""
    uncompared = [probe.name for probe in probes if probe.ours is None]
    if uncompared:
        raise ProbeError("these probes have nothing of nxwright's to compare, and are kept from "
                         "the Nextion Editor instead (probe keep): %s" % ", ".join(uncompared))


def _refuse_bad_probes(probes: list):
    names = [probe.name for probe in probes]
    bad = [name for name in names + [probe.fixtures for probe in probes
                                     if probe.fixtures is not None]
           if not _NAME.fullmatch(name)]
    if bad:
        raise ProbeError("probe and fixture folder names may hold only letters, digits, _ "
                         "and -: %s" % ", ".join(bad))
    twice = sorted({name for name in names if names.count(name) > 1})
    if twice:
        raise ProbeError("two probes share the name %s" % ", ".join(twice))
    # Fixtures are checked again once the Nextion Editor's file is gone, so a
    # probe that borrows from it makes them with `kept`, which does not.
    borrowing = [probe.name for probe in probes
                 if probe.borrows is not None and probe.fixtures is not None
                 and probe.kept is None]
    if borrowing:
        raise ProbeError("probes that borrow from the Nextion Editor's file and keep fixtures "
                         "must make them with kept: %s" % ", ".join(borrowing))


def _built(probe: Probe, work: Path) -> Path:
    """Copies the probe's base folder into `work`, applies its change, builds
    the project there, applies its built_change, and returns its path."""
    from nxwright.source.project_files import build
    source = work / "source"
    shutil.copytree(BASES / probe.base, source)
    if probe.change is not None:
        probe.change(source)
    project = work / _PROJECT
    build(source, project)
    if probe.built_change is not None:
        probe.built_change(project)
    return project


def _fixtures_hold(probe: Probe, project: Path) -> bool:
    """Whether nxwright's output for the built `project` is still the probe's
    fixtures. A probe that keeps none has nothing to compare with: the
    probes that keep fixtures guard what it showed."""
    if probe.fixtures is None:
        return True
    folder = FIXTURES / probe.fixtures / probe.name
    kept = {file.stem: file.read_bytes() for file in folder.glob("*.bin")}
    return kept == (probe.kept or probe.ours)(project)


def _checked(probe: Probe, project: Path, tool) -> Optional[str]:
    """Has `tool` write the TFT file of the probe's built `project`, and
    compares the probe's pieces. Returns None when they match, having
    written the probe's fixtures and deleted the TFT file, or else says
    where they differ, having kept the file. Raises CouldNotRun when the
    tool stops, as when the Nextion Editor refuses the project, having
    closed the messages the Editor shows: one left open would stop the
    next probe's commands too."""
    try:
        tft = tool.write_tft(project, BUILD / _TFT)
    except ProbeError as error:
        raise CouldNotRun("%s\n%s" % (error, tool.close_messages())) from None
    kept = BUILD / _KEPT / (probe.name + ".tft")
    try:
        data = tft.read_bytes()
        # Only what is cut from the Nextion Editor's file may fail as the
        # file's fault; nxwright's own output failing is raised below.
        try:
            borrowed = None if probe.borrows is None else probe.borrows(data)
            theirs = probe.theirs(data)
        except ProbeMismatch as error:
            difference = "the Nextion Editor's file could not be read: %s" % error
        else:
            ours = probe.ours(project) if probe.borrows is None else probe.ours(project, borrowed)
            difference = _first_difference(ours, theirs)
    except Exception:
        # nxwright failing on a probe is the agent's to look into, with the
        # Nextion Editor's file at hand.
        _keep(tft, kept)
        raise
    if difference is not None:
        _keep(tft, kept)
        return difference
    if probe.fixtures is not None:
        try:
            _write_fixtures(probe, ours if probe.kept is None else probe.kept(project))
        except Exception:
            _keep(tft, kept)
            raise
    delete_built_file(tft)
    if kept.exists():
        delete_built_file(kept)
    return None


def _keep(tft: Path, kept: Path):
    """Keeps the Nextion Editor's file `tft` as `kept`, over the one an
    earlier run kept for the same probe."""
    refuse_unless_deletable(tft)
    kept.parent.mkdir(parents=True, exist_ok=True)
    if kept.exists():
        delete_built_file(kept)
    tft.rename(kept)


def _first_difference(ours: dict, theirs: dict) -> Optional[str]:
    """Says where nxwright's pieces `ours` first differ from the Nextion
    Editor's `theirs`, or returns None when they are the same. The pieces
    are compared in the order of `ours`, which for a whole file is the
    file's: its checksum, last, differs whenever another piece does."""
    if set(ours) != set(theirs):
        return "nxwright gives the pieces %s, and the Nextion Editor's file %s" % (
            ", ".join(sorted(ours)) or "none", ", ".join(sorted(theirs)) or "none")
    for piece in ours:
        mine, editor = ours[piece], theirs[piece]
        if mine == editor:
            continue
        at = next((index for index, (a, b) in enumerate(zip(mine, editor)) if a != b),
                  min(len(mine), len(editor)))
        start = max(0, at - _AROUND)
        return ("%s first differs at byte %d of %d (the Nextion Editor's: %d): nxwright %s, "
                "the Nextion Editor %s" % (piece, at, len(mine), len(editor),
                                           mine[start:at + _AROUND].hex(" "),
                                           editor[start:at + _AROUND].hex(" ")))
    return None


def _write_fixtures(probe: Probe, pieces: dict):
    """Writes `pieces` as the probe's fixtures, one file a piece, and where
    the smaller pieces lie among them, its pieces.json (Parts). Raises
    ProbeError, before writing anything, when its folder has a fixture of a
    piece it no longer gives, which the agent removes from the repository,
    or when the smaller pieces do not put each back together
    (piece_table)."""
    bad = [piece for piece in pieces if not _NAME.fullmatch(piece)]
    if bad:
        raise ProbeError("%s: piece names may hold only letters, digits, _ and -: %s"
                         % (probe.name, ", ".join(bad)))
    folder = FIXTURES / probe.fixtures / probe.name
    stale = sorted(file.name for file in folder.glob("*.bin") if file.stem not in pieces)
    if stale:
        raise ProbeError("%s: %s keeps fixtures of pieces the probe no longer gives: %s"
                         % (probe.name, folder, ", ".join(stale)))
    table = piece_table(probe, pieces)
    folder.mkdir(parents=True, exist_ok=True)
    for piece, data in pieces.items():
        (folder / (piece + ".bin")).write_bytes(data)
    _write_piece_table(probe, table, getattr(pieces, "places", None))


def _write_piece_table(probe: Probe, table: dict, places: dict = None):
    """Writes the probe's pieces.json, beside its parts: "pieces", `table`,
    where each piece lies (piece_table), and "places", `places`, where each
    of its components lies (Parts)."""
    folder = FIXTURES / probe.fixtures / probe.name
    # With LF line ends on every system, as the repository keeps them.
    content = {"pieces": table, "places": places or {}}
    (folder / _PIECES).write_text(json.dumps(content, indent=1, sort_keys=True) + "\n",
                                  encoding="utf-8", newline="\n")


def _read_record() -> dict:
    try:
        return json.loads((BUILD / _RECORD).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}


def _write_record(record: dict):
    """Writes the record whole, then puts it in place, so that a run stopped
    as it writes leaves the earlier record, not half of one."""
    BUILD.mkdir(parents=True, exist_ok=True)
    written = BUILD / (_RECORD + ".new")
    written.write_text(json.dumps(record, indent=1, sort_keys=True), encoding="utf-8")
    os.replace(written, BUILD / _RECORD)
