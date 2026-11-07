"""write the TFT file of a rescue SD card for a screen model

  nxwright rescue <output.tft> --screen MODEL
                  [--firmware <file.tft> | --editor <folder>] [--download]
                  [--overwrite] [--no-backup]

Writes a TFT file for the screen model MODEL, such as NX4832T035. Its app
sets the screen's settings back to their defaults, then shows one blank
page. Its program sets:
  - dims=100: the screen starts at full brightness again;
  - bauds=9600: the serial line starts at 9600 bauds again;
  - recmod=0: a reparse mode ends, so that the screen takes instructions
    again;
  - addr=0: the screen's address is removed, so that it takes
    instructions without one;
  - sleep=0: the screen wakes.

Use the file for a screen that no longer answers on its serial line
because of one of these settings. Copy it to a microSD card, as the only
TFT file there, and power the screen on with the card in it. The screen
installs the file from the card. Then power the screen off, take the card
out, and upload your own app.

The firmware comes from where nxwright compile takes it, with the same
options: --firmware, --editor, and --download. An output file that exists
already is refused, unless --overwrite is given. Even then, only a TFT
file is replaced. If it changed since nxwright wrote it, it is kept as a
backup beside the new one, unless --no-backup is given.
"""
import argparse
from pathlib import Path
import sys
import tempfile

from nxwright import NxwrightError
from nxwright.project.device_settings import DEFAULT_ENCODING, DeviceSettings
from nxwright.project.editor_language import EDITOR_PROGRAM_DECLARATION
from nxwright.project.screen_models import ScreenModel, model_named
from nxwright.source.source_folder import NEXTION, new_source_folder

from nxwright.tft.commands.compile import Compiled, TerminalAsker, compile_folder, write_outputs
from nxwright.tft.firmware_download import DownloadAsker

# The rescue app's program.nx: the int variables of a new project, the
# settings it sets back, then its one page.
_RESCUE_PROGRAM = """%s
dims=100
bauds=9600
recmod=0
addr=0
sleep=0
page 0
""" % EDITOR_PROGRAM_DECLARATION


def main(arguments: list) -> int:
    parser = argparse.ArgumentParser(prog="nxwright rescue",
                                     description="Writes the TFT file of a rescue SD card for "
                                     "a screen model. Its app sets the screen's settings back "
                                     "to their defaults.")
    parser.add_argument("output", type=Path, help="the TFT file to write")
    parser.add_argument("--screen", required=True, metavar="MODEL",
                        help="the screen model, such as NX4832T035")
    sources = parser.add_mutually_exclusive_group()
    sources.add_argument("--firmware", type=Path, metavar="FILE.tft",
                         help="a TFT file to take the firmware from")
    sources.add_argument("--editor", type=Path, metavar="FOLDER",
                         help="a Nextion Editor folder to take the firmware from")
    parser.add_argument("--download", action="store_true",
                        help="allow downloading the firmware from Nextion's site without "
                        "asking, when nothing on this computer has it")
    parser.add_argument("--overwrite", action="store_true",
                        help="replace an existing TFT file")
    parser.add_argument("--no-backup", action="store_true",
                        help="do not keep a backup of a TFT file that changed since "
                        "nxwright wrote it")
    options = parser.parse_args(arguments)
    try:
        compiled = compile_rescue(model_named(options.screen), options.output, options.firmware,
                                  options.editor, TerminalAsker(options.download),
                                  options.overwrite)
        write_outputs(options.output, compiled.data, overwrite=options.overwrite,
                      keep_backup=not options.no_backup)
    except (NxwrightError, OSError) as error:
        print("nxwright rescue: %s" % error, file=sys.stderr)
        return 1
    print("Took the firmware from %s" % compiled.firmware_source)
    print("Wrote %s" % options.output)
    return 0


def compile_rescue(model: ScreenModel, output: Path, firmware_file: Path = None,
                   editor_folder: Path = None, asker: DownloadAsker = None,
                   overwrite: bool = False) -> Compiled:
    """Returns the compile of the rescue app for `model`, to be written as
    `output`. The firmware comes from where compile_folder takes it. Raises
    NxwrightError as compile_folder does."""
    # A folder of Python's own, which it deletes after.
    with tempfile.TemporaryDirectory(prefix="nxwright-rescue-") as folder:
        source = Path(folder) / "rescue"
        write_rescue_folder(source, model)
        return compile_folder(source, output, firmware_file, editor_folder=editor_folder,
                              asker=asker, overwrite=overwrite)


def write_rescue_folder(folder: Path, model: ScreenModel):
    """Writes the source folder of the rescue app for `model` into `folder`,
    which must not exist or be empty. It starts as nxwright new starts a
    folder, and its program then sets the screen's settings back to their
    defaults."""
    new_source_folder(folder, DeviceSettings(model, 0, DEFAULT_ENCODING), NEXTION, "rescue")
    (folder / "program.nx").write_text(_RESCUE_PROGRAM, encoding="utf-8", newline="\n")
