"""upload a TFT file to a screen over its serial port

  nxwright upload <file.tft> --port PORT [--baud RATE]
      [--upload-baud RATE] [--yes] [--full] [--find] [--json]

Sends the TFT file to the screen on PORT, such as COM5 or /dev/ttyUSB0,
with Nextion's upload protocol, so that the screen runs it from then on.
The file may be nxwright's or the Nextion Editor's.

First the command reads the file and checks its checksums and sizes. If
it cannot read the file, such as one made by a Nextion Editor older than
1.60.1, or if a check fails, it cancels the upload before opening the port.

Then the command finds the screen. --baud gives the rate the screen is
at now. Without it, the command tries each rate the screen takes, 9600
and 115200 first, which takes a few seconds. To find it, the command
sends only `connect`, and the bytes that end a reparse mode, a mode in
which a project hands what the screen receives to its own code. An app
that set one takes instructions again until it restarts.

Once the screen is found, the command cancels the upload if the file is
for another model than the screen's, or if nxwright cannot tell the model
of the file or of the screen. No option makes the command send such a
file, and it exits with 1.

Then it prints the file, its size, its model, the screen's model, the
port, and the upload rate, and prompts "Upload? [y/N]":

  - y uploads the file, and prints its progress;
  - n, or an empty answer, does not send the file, and exits with 1;
  - with no terminal to prompt at, as in a script, or when the input
    ends at the prompt, it does not send the file, and exits with 3.

--yes uploads without prompting.

--upload-baud gives the rate of the upload, 115200 by default, which
sends a megabyte in a little over a minute and a half. Any rate the
screen takes may be given, up to 921600, but some adapters lose bytes at
the highest rates. Above 115200, the command warns that the screen may
not take the rate, unless the screen's answer marks it as taking every
rate. The warning does not stop the upload.

The command lets the screen skip what it has already, such as the
firmware when only the project changed, with Nextion's fast upload,
`whmi-wris`: the screen may answer the first packet with where in the
file to go on from. The command prints how much the screen skipped.
--full sends the whole file, with `whmi-wri`.

--find stops once the screen is found and the file is checked against it,
without prompting or sending the file.

--json is for programs, such as nxwright's VS Code extension. The command
then prints one JSON object per line, and its words for people go to
standard error. It never prompts, so an upload needs --yes. The objects
are:
  - {"event": "found", "file": path, "size": bytes, "file_model": name or
    null, "port": name, "screen": its model as it answers, "screen_rate":
    bauds, "takes_every_rate": bool, "upload_rate": bauds, "warnings":
    [words]}, once the screen is found;
  - {"event": "cancelled", "reason": words}, when the command cancels the
    upload. If the file fails its checks, this is the only object, because
    the port is never opened. Otherwise it follows the found event;
  - {"event": "skipped", "bytes": count}, when the screen skips what it has;
  - {"event": "progress", "sent": place in the file, "size": bytes}, after
    each packet;
  - {"event": "uploaded"}, once the whole file is sent.

Once the screen has taken the upload command, it waits for the whole
file. If it stops answering, the command prints how far it got, and exits
with 1: the screen then needs to be powered off and on, and the file
uploaded again. When the whole file is sent, the screen restarts with it.
"""
import argparse
import json
from pathlib import Path
import sys

from nxwright import NxwrightError
from nxwright.project.screen_models import model_with_id

from nxwright.tft import upload
from nxwright.tft.commands.compile import at_terminal
from nxwright.tft.tft_file import device_id_of, read_tft

# The exit codes: a file or a port that cannot be used, a screen that does
# not answer, or an upload the user chose not to make; and an upload not
# made as there was nobody to prompt, which a script can tell apart, as
# decompile's code 3.
_FAILED, _NOBODY_TO_PROMPT = 1, 3
# The upload rate without --upload-baud.
_DEFAULT_UPLOAD_RATE = 115200


def main(arguments: list, open_port=None, pause_of=upload.pause, settle: float = None,
         answer_wait: float = None) -> int:
    """Runs the command. `open_port(name)` opens the port called `name`, and
    is pyserial's by default. The tests pass one that gives a stand-in
    screen. `pause_of`, `settle`, and `answer_wait` set how long the upload
    waits (see upload.upload), and the tests pass shorter waits."""
    parser = argparse.ArgumentParser(prog="nxwright upload",
                                     description="Uploads a TFT file to a screen over its "
                                     "serial port.")
    parser.add_argument("file", type=Path)
    parser.add_argument("--port", required=True, help="the screen's port, such as COM5")
    parser.add_argument("--baud", type=int, choices=upload.RATES, metavar="RATE",
                        help="the screen's rate now; without it, each rate is tried")
    parser.add_argument("--upload-baud", type=int, choices=upload.RATES, metavar="RATE",
                        default=_DEFAULT_UPLOAD_RATE,
                        help="the rate of the upload, %d by default" % _DEFAULT_UPLOAD_RATE)
    parser.add_argument("--yes", action="store_true", help="upload without prompting")
    parser.add_argument("--full", action="store_true",
                        help="send the whole file, without letting the screen skip what it has")
    parser.add_argument("--find", action="store_true",
                        help="find the screen, print what the upload would be, and send nothing")
    parser.add_argument("--json", action="store_true",
                        help="print JSON objects, one a line, for programs; never prompt")
    options = parser.parse_args(arguments)
    # With --json, the words for people go to standard error, so that what
    # is printed is JSON alone.
    said = sys.stderr if options.json else sys.stdout
    try:
        data = options.file.read_bytes()
    except OSError as error:
        return _failed(error)
    device_id = device_id_of(data)
    if device_id is None:
        return _cancel_upload("%s is too short to be a TFT file." % options.file,
                              options.json)
    file_model = model_with_id(device_id)
    # The file is checked before the port is opened, so that a file that
    # cannot be used does not disturb the screen.
    problem = _why_file_cannot_be_uploaded(data, options.file)
    if problem:
        return _cancel_upload(problem, options.json)
    try:
        port = (open_port or _serial_port)(options.port)
    except (OSError, NxwrightError) as error:
        return _failed(error)
    try:
        screen = upload.find_screen(port, [options.baud] if options.baud else upload.RATES_TRIED,
                                    pause_of)
        if screen is None:
            return _failed("no screen answered on %s at %s" % (
                options.port, options.baud or "any rate it takes"))
        rate_warning = _rate_warning(screen, options.upload_baud)
        warnings = [rate_warning] if rate_warning else []
        if options.json:
            _print_json({"event": "found", "file": str(options.file), "size": len(data),
                         "file_model": file_model.name if file_model else None,
                         "port": options.port, "screen": screen.model,
                         "screen_rate": screen.rate, "takes_every_rate": screen.takes_every_rate,
                         "upload_rate": options.upload_baud, "warnings": warnings})
        problem = _why_file_is_not_for_screen(options.file, file_model, screen, options.port)
        if problem:
            return _cancel_upload(problem, options.json)
        print("Upload %s, %d bytes, made for %s, to the screen %s on %s, at %d baud."
              % (options.file, len(data), file_model.name, screen.model, options.port,
                 options.upload_baud), file=said)
        for warning in warnings:
            print("nxwright upload: warning: %s." % warning, file=sys.stderr)
        if options.find:
            return 0
        stopped = _stop_unless_user_goes_on(options)
        if stopped is not None:
            return stopped
        stopped_by_user = False
        try:
            upload.upload(port, screen, data, options.upload_baud,
                          _json_progress if options.json else _print_progress,
                          fast=not options.full,
                          on_skip=_json_skipped if options.json else _print_skipped,
                          answer_wait=answer_wait, pause_of=pause_of, settle=settle)
        except KeyboardInterrupt:
            stopped_by_user = True
        finally:
            # Ends the progress line, so that what follows starts a line.
            if not options.json:
                print()
        if stopped_by_user:
            # The screen waits for the rest of the file, as when it stops
            # answering.
            return _failed("stopped during the upload; the screen now needs to be powered off "
                           "and on, and the file uploaded again")
        print("nxwright upload: uploaded %s to %s on %s; the screen restarts with it"
              % (options.file, screen.model, options.port), file=said)
        if options.json:
            _print_json({"event": "uploaded"})
        return 0
    except (OSError, NxwrightError) as error:
        return _failed(error)
    finally:
        port.close()


def _serial_port(name: str):
    """Opens the serial port called `name` with pyserial, as the screen's
    line always is: 8 data bits, no parity, 1 stop bit, no flow control."""
    import serial
    try:
        return serial.Serial(name, baudrate=9600, timeout=0)
    except serial.SerialException as error:
        raise NxwrightError("cannot open %s: %s" % (name, error)) from None


def _why_file_cannot_be_uploaded(data: bytes, file: Path):
    """Reads the file `data`, and returns why it cannot be uploaded, or None
    if nxwright reads it without an error."""
    try:
        read_tft(data, str(file))
    except NxwrightError as error:
        return "%s. Compile the project again with nxwright, or with the Nextion Editor." % error
    return None


def _why_file_is_not_for_screen(file: Path, file_model, screen: upload.Screen, port: str):
    """Returns why `file`, made for `file_model`, cannot be uploaded to
    `screen` on `port`, or None. The screen answers with its model and a
    suffix, such as NX4832T035_011R. Only the part before the underscore is
    compared, ignoring case."""
    screens = screen.model.partition("_")[0]
    if not screens:
        return ("nxwright cannot tell whether %s is for the screen on %s, as the screen did not "
                "answer with its model." % (file.name, port))
    if file_model is None:
        return ("nxwright does not know which model %s is for. The screen on %s is the %s, so "
                "compile the project for that model." % (file.name, port, screens))
    if screens.upper() != file_model.name.upper():
        return ("%s is for the %s, but the screen on %s is the %s. Compile the project for the "
                "%s, or connect the screen the file is for."
                % (file.name, file_model.name, port, screens, screens))
    return None


def _rate_warning(screen: upload.Screen, rate: int):
    """Returns why the screen may not take an upload at `rate`, or None.
    Screens whose answer marks them as taking every rate accept uploads up
    to 921600 baud. Others may accept only 115200 or less."""
    if rate > upload.HIGHEST_RATE_ON_OLDER_SCREENS and not screen.takes_every_rate:
        return ("this screen may not take uploads faster than %d baud. If the upload fails, "
                "upload the file again at %d baud"
                % (upload.HIGHEST_RATE_ON_OLDER_SCREENS, upload.HIGHEST_RATE_ON_OLDER_SCREENS))
    return None


def _cancel_upload(reason: str, json_output: bool) -> int:
    """Prints why the upload is cancelled, `reason`, as an error, and also as
    a cancelled event if `json_output` is true. Returns the exit code."""
    if json_output:
        _print_json({"event": "cancelled", "reason": reason})
    return _failed(reason)


def _stop_unless_user_goes_on(options):
    """Prompts the user whether to upload, unless --yes answered ahead of
    time. Returns None to go on, or else the exit code, having printed why
    nothing more was sent. With --json, it never prompts, as with no
    terminal."""
    terminal = at_terminal() and not options.json
    if options.yes:
        return None
    why = "there was no terminal to prompt at"
    while terminal:
        try:
            answer = input("Upload? [y/N]: ").strip().lower()
        except EOFError:
            why = "the input ended at the prompt"
            break
        if answer in ("y", "yes"):
            return None
        if answer in ("", "n", "no"):
            print("nxwright upload: stopped; the file was not sent", file=sys.stderr)
            return _FAILED
        print("Not one of the choices: y, n")
    print("nxwright upload: %s, so the file was not sent. Pass --yes to upload it." % why,
          file=sys.stderr)
    return _NOBODY_TO_PROMPT


def _print_progress(place: int, size: int):
    print("\r%d%%" % (100 * place // size), end="", flush=True)


def _print_skipped(skipped: int):
    print("\rThe screen already had %d bytes of the file, which were not sent." % skipped)


def _json_progress(place: int, size: int):
    _print_json({"event": "progress", "sent": place, "size": size})


def _json_skipped(skipped: int):
    _print_json({"event": "skipped", "bytes": skipped})


def _print_json(event: dict):
    print(json.dumps(event), flush=True)


def _failed(error) -> int:
    print("nxwright upload: %s" % error, file=sys.stderr)
    return _FAILED
