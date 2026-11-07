"""compile a source folder or a project file into a TFT file

  nxwright compile <source-folder or project.HMI> <output.tft>
                        [--firmware <file.tft> | --editor <folder>] [--download]
                        [--ffmpeg <program>] [--project-file <project.HMI>]
                        [--overwrite] [--json]

Builds a source folder with nxwright, whose build decides what a project
may hold, or reads a project file as it is. With --project-file, the
project file built from a source folder is written there too. Then it
checks everything in the project, and the firmware's version
(tft/matching.py). It refuses what nxwright cannot compile, such as a value
outside the range that can be encoded. Each is listed with its reason
(tft/reasons.py), and no file is written.

The firmware comes from the first of these that has it (tft/firmware.py):
  - the TFT file --firmware names, which must be of the same series, or the
    Nextion Editor folder --editor names;
  - the cache of firmware that an earlier compile found;
  - the installed Nextion Editor;
  - a download from Nextion's site, of about 50 MB. At a terminal, the
    compile asks first. Before it asks, it makes one small request to
    Nextion's site to find the download's size, so that the question can
    show it. Elsewhere, it downloads only with --download, and without
    --download it makes no request at all. The download needs curl, which
    comes with Windows 10 version 1803 and later, macOS, and most Linux
    systems.
The compile prints which one it took. It takes only the firmware of the
Nextion Editor 1.68.2, the version nxwright was tested with. Firmware of
another version may run the compiled code differently, or use other
numbers for its commands.

A sound of another form than 22050 samples a second of 16 bits each is
resampled with ffmpeg, as the Nextion Editor does: the ffmpeg the PATH
finds, or the one --ffmpeg names. Without one, such a project is refused.
An output file that exists already is refused, unless --overwrite is
given. Even then, only a TFT file, or a project file for --project-file, is
replaced, as nxwright build replaces only a project file. Nothing is
written unless the compile succeeds.

--json is for programs, such as nxwright's VS Code extension. The command
then prints one JSON object per line, and its words for people go to
standard error. It never prompts: a download needs --download. The
objects are:
  - {"event": "download", "done": bytes, "size": bytes}, as a download
    goes on;
  - {"event": "firmware-missing", "version": "1.68.2"}, when nothing on the
    computer has the firmware, and --download was not given;
  - {"event": "compiled", "tft": path, "project_file": path or null,
    "firmware_source": words, "warnings": [words]}, once written.

A project decompiled from a file made by an older Nextion Editor may give
an object a disup, an attribute of the Nextion Editors 1.60.1 and 1.63.3
meant to disable its release event after a drag. The Nextion Editor
1.68.2 has no disup, and nor does the file nxwright writes. So for a disup
that is not 0, the compile warns, naming the object, that its release
event may run after a drag.
"""
import argparse
from contextlib import ExitStack
import json
from pathlib import Path
import sys
import tempfile
from typing import NamedTuple
import webbrowser

from nxwright import NxwrightError
from nxwright.project.ffmpeg import find_ffmpeg
from nxwright.project.replacing import held_by_the_nextion_editor, is_project_file, written_beside
from nxwright.project.screen_models import model_with_id
from nxwright.source.project_files import build

from nxwright.tft import firmware_versions, frame
from nxwright.tft.firmware import find_firmware
from nxwright.tft.firmware_download import DownloadAsker, offer_of
from nxwright.tft.firmware_versions import version_text
from nxwright.tft.matching import firmware_needs, project_needs, refuse_unmatched
from nxwright.tft.packaging import Firmware, package
from nxwright.tft.project import Project
from nxwright.tft.tft_file import device_id_of


class Compiled(NamedTuple):
    """A compile's result: the TFT file's bytes, `data`, where its firmware
    came from, `firmware_source`, what the user should know of the project,
    `warnings` (compile_warnings), and the bytes of the project file built
    on the way, `project_file`, when it was asked for."""
    data: bytes
    firmware_source: str
    warnings: tuple = ()
    project_file: bytes = None


# The warning of an object with a disup that is not 0, given where it is,
# such as page0.t0, and its disup (frame.DISUP).
DISUP_WARNING = ("%(where)s has a disup of %(disup)d. Older Nextion Editors, such as 1.63.3, "
                 "have this attribute, meant to disable the release event after a drag. nxwright "
                 "compiles with the firmware of the Nextion Editor 1.68.2, which has no disup, "
                 "so the release event of %(where)s may run after a drag")


def main(arguments: list) -> int:
    parser = argparse.ArgumentParser(prog="nxwright compile",
                                     description="Compiles a source folder or a project file "
                                     "into a TFT file, refusing what nxwright cannot compile.")
    parser.add_argument("source", type=Path, help="a source folder, or a project file (.HMI)")
    parser.add_argument("output", type=Path)
    sources = parser.add_mutually_exclusive_group()
    sources.add_argument("--firmware", type=Path, metavar="FILE.tft",
                         help="a TFT file to take the firmware from")
    sources.add_argument("--editor", type=Path, metavar="FOLDER",
                         help="a Nextion Editor folder to take the firmware from")
    parser.add_argument("--download", action="store_true",
                        help="allow downloading the firmware from Nextion's site without "
                        "asking, when nothing on this computer has it")
    parser.add_argument("--ffmpeg", type=Path, metavar="PROGRAM",
                        help="the ffmpeg program, for a sound the Nextion Editor resamples, "
                        "rather than the one the PATH finds")
    parser.add_argument("--project-file", type=Path, metavar="PROJECT.HMI",
                        help="from a source folder, also write the project file it builds")
    parser.add_argument("--overwrite", action="store_true",
                        help="replace an existing TFT file, and an existing project file given "
                        "with --project-file")
    parser.add_argument("--json", action="store_true",
                        help="print JSON objects, one a line, for programs; never prompt")
    options = parser.parse_args(arguments)
    # With --json, the words for people go to standard error, so that what
    # is printed is JSON alone.
    said = sys.stderr if options.json else sys.stdout
    try:
        compiled = compile_folder(options.source, options.output, options.firmware,
                                  options.ffmpeg, options.editor,
                                  TerminalAsker(options.download, as_json=options.json),
                                  options.project_file, options.overwrite)
        write_outputs(options.output, compiled.data, options.project_file,
                      compiled.project_file, options.overwrite)
    except FirmwareMissing as error:
        if options.json:
            _print_json({"event": "firmware-missing", "version": error.version})
        print("nxwright compile: %s" % error, file=sys.stderr)
        return 1
    except (NxwrightError, OSError) as error:
        print("nxwright compile: %s" % error, file=sys.stderr)
        return 1
    for warning in compiled.warnings:
        print("nxwright compile: warning: %s" % warning, file=sys.stderr)
    print("Took the firmware from %s" % compiled.firmware_source, file=said)
    print("Wrote %s" % options.output, file=said)
    if compiled.project_file is not None:
        print("Wrote %s" % options.project_file, file=said)
    if options.json:
        _print_json({"event": "compiled", "tft": str(options.output),
                     "project_file": None if compiled.project_file is None
                     else str(options.project_file),
                     "firmware_source": compiled.firmware_source,
                     "warnings": list(compiled.warnings)})
    return 0


class FirmwareMissing(NxwrightError):
    """No source on the computer had the firmware of `version`, as "1.68.2",
    and no download was allowed: a caller may offer one."""

    def __init__(self, message: str, version: str):
        super().__init__(message)
        self.version = version


def compile_folder(source: Path, output: Path, firmware_file: Path = None,
                   ffmpeg_file: Path = None, editor_folder: Path = None,
                   asker: DownloadAsker = None, project_file: Path = None,
                   overwrite: bool = False) -> Compiled:
    """Returns the compile of `source`, a source folder or a project file,
    to be written as `output`. With `project_file`, which needs a source
    folder, the result also has the project file built on the way, to be
    written there. The firmware comes from the TFT file `firmware_file` or
    the Nextion Editor folder `editor_folder`, when one is given, or else
    from the cache, the installed Nextion Editor, or a download that `asker`
    lets the user allow (firmware.find_firmware). Without `asker`, nothing is
    downloaded. The ffmpeg is `ffmpeg_file`, or else the PATH's, for a
    sound to resample. Raises NxwrightError when an output exists and
    `overwrite` is not given, or is not of its kind; when `source` is
    neither a folder nor a project file; when a sound needs ffmpeg and there
    is none; or when the project or the firmware holds anything the check
    refuses (matching.py). Raises FirmwareMissing when no firmware is found
    and `asker` could not offer a download, and NxwrightError when a
    download is declined or fails."""
    _refuse_unless_replacing(output, overwrite, _is_tft_file, "TFT file")
    if project_file is not None:
        _refuse_unless_replacing(project_file, overwrite, is_project_file, "project file")
    if not source.exists():
        raise NxwrightError("%s does not exist" % source)
    if source.is_dir():
        project, built = project_and_file_of_folder(source)
    elif is_project_file(source):
        if project_file is not None:
            raise NxwrightError("--project-file writes the project file built from a source "
                                "folder, and %s is a project file already" % source)
        project, built = Project.from_file(source), None
    else:
        raise NxwrightError("%s is neither a source folder nor a project file" % source)
    found = find_firmware(project.settings.model.series, firmware_file, editor_folder, asker)
    if found.firmware is None:
        message = _no_firmware_message(found.skipped)
        # A download that was allowed and failed is not offered again.
        if asker is not None and asker.can_ask():
            raise NxwrightError(message)
        raise FirmwareMissing(message, version_text(max(firmware_versions.MATCHED_VERSIONS)))
    return Compiled(compile_project(project, found.firmware, find_ffmpeg(ffmpeg_file)),
                    found.source, tuple(compile_warnings(project)),
                    built if project_file is not None else None)


def _is_tft_file(path: Path) -> bool:
    """Whether `path` is a file whose header gives a screen model nxwright
    knows, as a TFT file's does: the only kind of file the compile
    replaces."""
    if not path.is_file():
        return False
    device_id = device_id_of(path.read_bytes())
    return device_id is not None and model_with_id(device_id) is not None


def _refuse_unless_replacing(output: Path, overwrite: bool, is_of_its_kind, kind: str):
    """Raises NxwrightError when `output` exists, unless `overwrite` allows
    replacing it and `is_of_its_kind(output)` tells that it is a `kind`, as
    "TFT file"."""
    if not output.exists():
        return
    if not overwrite:
        raise NxwrightError("%s exists; pass --overwrite to replace it" % output)
    if not is_of_its_kind(output):
        raise NxwrightError("%s exists and is not a %s; the compile replaces only a %s"
                            % (output, kind, kind))


def write_outputs(tft: Path, data: bytes, project_file: Path = None, project_data: bytes = None,
                  overwrite: bool = False):
    """Writes `data` as the TFT file `tft`, and `project_data`, when given,
    as `project_file`. Each is written beside its output first. The project
    file then replaces its output first, as the Nextion Editor may keep it
    from being replaced, and the TFT file last. So a project file that
    cannot be replaced leaves both outputs as they were. Only a TFT file
    that cannot be replaced, once the project file was, as a read-only one,
    leaves them apart. Without `overwrite`, an output
    that appeared since compile_folder checked it, as during a download, is
    refused."""
    if not overwrite:
        for output in (tft, project_file if project_data is not None else None):
            if output is not None and output.exists():
                raise NxwrightError("%s exists; pass --overwrite to replace it" % output)
    with ExitStack() as stack:
        # Left in reverse order: the last entered is replaced first.
        written_tft = stack.enter_context(written_beside(tft))
        written_tft.write_bytes(data)
        if project_data is not None:
            stack.enter_context(held_by_the_nextion_editor(project_file))
            written_project = stack.enter_context(written_beside(project_file))
            written_project.write_bytes(project_data)


def _print_json(event: dict):
    print(json.dumps(event), flush=True)


def compile_warnings(project: Project) -> list:
    """Returns what the user should know of `project` that the compile
    does not refuse: each object with a disup that is not 0, in page order
    (DISUP_WARNING)."""
    warnings = []
    for page in project.pages:
        for number, page_object in enumerate(page.objects):
            disup = int.from_bytes(page_object.attribute(frame.DISUP) or b"", "little")
            if disup:
                # Object 0 is the page itself.
                where = page.name if number == 0 else "%s.%s" % (
                    page.name, page_object.attribute("objname").decode("latin-1"))
                warnings.append(DISUP_WARNING % {"where": where, "disup": disup})
    return warnings


def at_terminal() -> bool:
    """Whether a command can ask the user: its input and output are both a
    terminal. input writes its question to the output, so with the output
    sent to a file, the question would not be seen."""
    return sys.stdin.isatty() and sys.stdout.isatty()


class TerminalAsker(DownloadAsker):
    """The command line's asker (firmware_download.DownloadAsker). It asks at
    the terminal, when the command's input and output are both one. Without
    a terminal, it allows a download only when --download allowed it ahead
    of time, and otherwise answers no. `as_json` is --json: it never asks,
    as if there were no terminal, and reports progress as JSON objects."""

    def __init__(self, download_allowed: bool, as_json: bool = False):
        self.download_allowed = download_allowed
        self.as_json = as_json
        self.at_terminal = at_terminal() and not as_json

    def can_ask(self) -> bool:
        return self.at_terminal or self.download_allowed

    def can_ask_to_run(self) -> bool:
        return self.at_terminal

    def allows_download(self, what: str, size: int, address: str, runs: bool = False) -> bool:
        # --download allows a download ahead of time, but not a program
        # that will then run, which always needs the question.
        if self.download_allowed and not runs:
            return True
        if not self.at_terminal:
            return False
        return self._yes("Download %s%s, %.1f MB, from %s?"
                         % ("and run " if runs else "", what, size / 1_000_000, address))

    def offer_page(self, address: str):
        if self.at_terminal and self._yes("Open Nextion's download page, %s?" % address):
            webbrowser.open(address)

    @staticmethod
    def _yes(question: str) -> bool:
        """Whether the user answers yes to `question` at the terminal. The
        end of the input, as Ctrl-D gives it, answers no."""
        try:
            return input(question + " [y/N] ").strip().lower() in ("y", "yes")
        except EOFError:
            return False

    def report_progress(self, done: int, size: int):
        if self.as_json:
            _print_json({"event": "download", "done": done, "size": size})
        elif self.at_terminal:
            # One line, written over as the download goes on.
            print("\rDownloaded %.1f of %.1f MB" % (done / 1_000_000, size / 1_000_000),
                  end="\n" if done >= size else "", flush=True)


def _no_firmware_message(skipped: tuple) -> str:
    """Returns the refusal of a compile that found no firmware, listing why
    each source tried did not serve, and what the user can do."""
    newest = max(firmware_versions.MATCHED_VERSIONS)
    return ("no firmware was found:\n%s\nInstall the Nextion Editor %s from %s, or give a TFT "
            "file it wrote with --firmware."
            % ("\n".join("- %s" % reason for reason in skipped), version_text(newest),
               offer_of(newest).installer_address))


def project_of_folder(source_folder: Path) -> Project:
    """Returns the project nxwright builds from `source_folder`. Raises
    NxwrightError when its build refuses the folder."""
    return project_and_file_of_folder(source_folder)[0]


def project_and_file_of_folder(source_folder: Path) -> tuple:
    """Returns the project nxwright builds from `source_folder`, and the
    bytes of its project file. Raises NxwrightError when its build refuses
    the folder."""
    # A folder of Python's own, which it deletes after.
    with tempfile.TemporaryDirectory(prefix="nxwright-compile-") as folder:
        project_file = Path(folder) / "project.HMI"
        build(source_folder, project_file)
        return Project.from_file(project_file), project_file.read_bytes()


def compile_project(project: Project, firmware: Firmware, ffmpeg: str = None, *,
                    any_release: bool = False) -> bytes:
    """Returns the TFT file of `project` around `firmware`, resampling its
    sounds with the program `ffmpeg` where the Nextion Editor does
    (packaging.py). Raises NxwrightError when the project or the firmware
    holds anything the check refuses (matching.py), the frame refuses
    the project, or a sound needs ffmpeg and `ffmpeg` is None.

    With `any_release`, the firmware may come from a release of the Nextion
    Editor that nxwright has not matched. Only the probes take it, to compare
    nxwright's file with that release's own (probing/packaging_probes.py,
    probe_firmware). Such a file is written as for the matched release."""
    needs = project_needs(project)
    if not any_release:
        needs = firmware_needs(firmware.version) + needs
    refuse_unmatched(needs)
    return package(project, frame.user_code(project), firmware, ffmpeg)
