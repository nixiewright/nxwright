"""Adding an MCU emulator to a source folder: a first Python program that
emulates the MCU (nxwright/mcu.py), and the [mcu] table of app.toml that
gives the program's path (mcu_table.py)."""
from pathlib import Path

from nxwright import NxwrightError
from nxwright.source.mcu_table import EMULATOR, emulator_file
from nxwright.source.source_folder import app_text_in, parse_app, read_text

# Where the emulator's file goes by default, as a path from the source
# folder: in a folder beside it.
DEFAULT_EMULATOR = "../mcu/main.py"

# The program that add_emulator writes.
_FIRST_EMULATOR = '''\
"""This app's MCU emulator. It emulates the microcontroller at the other end
of the screen's serial line while the app runs in nxwright's simulator.

In VS Code, a simulation whose MCU port is Emulator starts this program. To
start it yourself, run it with a port number, as in `python main.py 7000`,
then connect the simulator's MCU port over TCP to 127.0.0.1:7000.
"""
import sys

from nxwright import mcu

# Ends each instruction the screen receives, and each message it sends.
END = b"\\xff\\xff\\xff"
# What the screen sends once the app has started.
READY = b"\\x88" + END


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else None
    if port is not None:
        # Flushed so that the line shows at once. Python would otherwise keep
        # it back when the output goes to another program.
        print("Waiting for the simulator on 127.0.0.1:%d" % port, flush=True)
    with mcu.open(listen=port) as line:
        while True:
            # Waits for the screen's next message. To do something else
            # while waiting, set line.timeout to a number of seconds. The
            # read then returns what has come once that time has passed.
            message = line.read_until(END)
            if message == READY:
                # The app has started. Send the screen what it shows first,
                # such as:
                #     line.write(b't0.txt="Hello"' + END)
                continue
            # Answer the screen's other messages here: what its code sends
            # with prints and printh, a component's touch event, or a reply
            # to an instruction sent with line.write.


if __name__ == "__main__":
    try:
        main()
    except mcu.LineClosed:
        # The simulation ended.
        pass
'''


def add_emulator(source_folder: Path, emulator: str = DEFAULT_EMULATOR) -> Path:
    """Adds an MCU emulator to a source folder: writes a first program to
    `emulator`, a path from the source folder written with forward slashes,
    and records that path in app.toml's [mcu] table. The program opens the
    screen's serial line, and has comments where the user's own code goes.
    Returns the file written.

    Raises NxwrightError, before writing anything, if app.toml already has an
    [mcu] table, if `emulator` is not a path the table can have, or if the
    file already exists."""
    source_folder = Path(source_folder)
    app = parse_app(read_text(source_folder / "app.toml"))
    if app.get("mcu"):
        raise NxwrightError("app.toml already has an [mcu] table, for the emulator %s"
                            % app["mcu"][EMULATOR])
    # Parsing the new app.toml checks `emulator`, before anything is written.
    text = app_text_in(source_folder, dict(app, mcu={EMULATOR: emulator}))
    parse_app(text)
    file = emulator_file(source_folder, {EMULATOR: emulator})
    if file.exists():
        raise NxwrightError("%s is already there" % file)
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(_FIRST_EMULATOR, encoding="utf-8", newline="\n")
    (source_folder / "app.toml").write_text(text, encoding="utf-8", newline="\n")
    return file
