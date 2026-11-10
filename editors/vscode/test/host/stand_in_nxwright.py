"""Stands in for nxwright in the tests inside VS Code of the commands on TFT
files (tft.host.cjs) and of Delete (media.host.cjs). A real compile needs
the vendor's firmware, a real upload a screen, and a real decompile a TFT
file of the vendor's, none of which the tests have. A real remove would
delete from the source folder the tests share.

These subcommands are answered here, as the real ones answer with --json:
  - compile: without --firmware, --editor, or --download, no firmware is
    found: it prints {"event": "firmware-missing", ...}, and exits with 1.
    Otherwise it writes stand-in bytes as the TFT file, and as the project
    file --project-file gives, prints {"event": "compiled", ...}, and exits
    with 0.
  - upload: finds a screen at 115200 bauds, whose model is the file's, and
    with --find stops there; with --yes, it gives the progress of a file of
    8192 bytes, and the end. It cancels the upload of a file called
    cancelled-at-find.tft as soon as it finds the screen, and of one called
    cancelled-at-upload.tft only when --find is not given, and then exits
    with 1.
  - decompile: prints, on its output, the list of names that matched no
    guess, and always warns that the folder compiles into a file that
    differs from the TFT file. With --continue-unconfirmed, it then writes
    app.toml in the folder, and exits with 0. Without that option, it
    writes nothing, and exits with 3.
  - remove: it deletes nothing, says what the real one would have removed,
    and exits with 0.
Every other subcommand, such as the language server's, runs the real
nxwright of this checkout, so that the rest of the extension goes on
working.

Each run adds its subcommand and arguments to a log file, as one JSON list
per line, so that a test can check what the extension ran. If the
environment variable NXWRIGHT_STAND_IN_LOG is set, its value is the log's
path. Otherwise the log is stand_in_nxwright.log in this checkout's
.vscode-test folder, where the tests' VS Code keeps its files. The tests
also know that the language server started through the stand-in once the
log contains a run of `lsp`.
"""
import json
import os
from pathlib import Path
import runpy
import sys

NXWRIGHT = Path(__file__).resolve().parents[4]
LOG = Path(os.environ.get("NXWRIGHT_STAND_IN_LOG")
           or Path(__file__).resolve().parents[2] / ".vscode-test" / "stand_in_nxwright.log")


def emit(event: dict):
    print(json.dumps(event), flush=True)


def compile_(arguments: list) -> int:
    source, output = arguments[0], arguments[1]
    if not {"--firmware", "--editor", "--download"} & set(arguments):
        emit({"event": "firmware-missing", "version": "1.68.2"})
        print("nxwright compile: no firmware was found", file=sys.stderr)
        return 1
    Path(output).write_bytes(b"stand-in TFT file of " + source.encode("utf-8"))
    project_file = None
    if "--project-file" in arguments:
        project_file = arguments[arguments.index("--project-file") + 1]
        Path(project_file).write_bytes(b"stand-in project file")
    print("Wrote %s" % output, file=sys.stderr)
    emit({"event": "compiled", "tft": output, "project_file": project_file,
          "firmware_source": "the stand-in", "warnings": []})
    return 0


def upload(arguments: list) -> int:
    port = arguments[arguments.index("--port") + 1]
    emit({"event": "found", "file": arguments[0], "size": 8192, "file_model": "NX4832T035",
          "port": port, "screen": "NX4832T035_011R", "screen_rate": 115200,
          "takes_every_rate": True, "upload_rate": 115200, "warnings": []})
    finding = "--find" in arguments
    if Path(arguments[0]).stem == ("cancelled-at-find" if finding else "cancelled-at-upload"):
        emit({"event": "cancelled", "reason": "%s is for the NX8048P050, but the screen on %s is "
              "the NX4832T035." % (Path(arguments[0]).name, port)})
        return 1
    if finding:
        return 0
    if "--yes" not in arguments:
        return 3
    for sent in (4096, 8192):
        emit({"event": "progress", "sent": sent, "size": 8192})
    emit({"event": "uploaded"})
    return 0


def decompile(arguments: list) -> int:
    print("1 name matched no guess, so the folder gives it a readable one:")
    print("  text3: the text of ID 3, on page0")
    print("nxwright decompile: warning: the folder compiles into a file that differs from "
          "%s:\n  page0: 1 in the file, 2 compiled again" % arguments[0], file=sys.stderr)
    if "--continue-unconfirmed" not in arguments:
        print("nxwright decompile: there was no terminal to prompt at, so nothing was written. "
              "Pass --continue-unconfirmed to write this folder.", file=sys.stderr)
        return 3
    folder = Path(arguments[1])
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "app.toml").write_text("# stand-in\n", encoding="utf-8")
    print("nxwright decompile: wrote %s" % folder)
    return 0


def remove(arguments: list) -> int:
    print("Removed the %s %s from %s: nothing, as this is the stand-in"
          % (arguments[1], arguments[2], arguments[0]))
    return 0


ANSWERED = {"compile": compile_, "upload": upload, "decompile": decompile, "remove": remove}

if __name__ == "__main__":
    name = sys.argv[1] if len(sys.argv) > 1 else ""
    with open(LOG, "a", encoding="utf-8") as log:
        log.write(json.dumps(sys.argv[1:]) + "\n")
    if name in ANSWERED:
        sys.exit(ANSWERED[name](sys.argv[2:]))
    sys.argv = [str(NXWRIGHT / "run.py")] + sys.argv[1:]
    sys.path.insert(0, str(NXWRIGHT))
    runpy.run_path(str(NXWRIGHT / "run.py"), run_name="__main__")
