"""The [mcu] table of a source folder's app.toml.

On real hardware, a microcontroller (the MCU) sits at the other end of the
screen's serial line. A project can have an MCU emulator, a Python program
that takes the microcontroller's place while the app runs in the simulator.
The [mcu] table gives that program's path:

    [mcu]
    emulator = "../mcu/main.py"

`emulator` is the program's file, as a path from the source folder, with
forward slashes. The build does not read the table.
"""
from pathlib import Path

from nxwright import NxwrightError

# The table's key.
EMULATOR = "emulator"


def checked_mcu(table) -> dict:
    """Returns app.toml's [mcu] table `table` once checked, or an empty dict
    when `table` is None because app.toml has no such table. Raises
    NxwrightError if `table` is not a table, if it has a key other than
    `emulator`, or if `emulator` is missing or is not a path written with
    forward slashes."""
    if table is None:
        return {}
    if not isinstance(table, dict):
        raise NxwrightError("app.toml: mcu must be a table, as in [mcu]")
    extra = set(table) - {EMULATOR}
    if extra:
        raise NxwrightError("app.toml: unknown key %s in [mcu]" % sorted(extra)[0])
    emulator = table.get(EMULATOR)
    if not isinstance(emulator, str) or not emulator or "\\" in emulator:
        raise NxwrightError("app.toml: emulator in [mcu] must be the path of the emulator's "
                            "Python file from the source folder, with forward slashes, such "
                            "as \"../mcu/main.py\"")
    return dict(table)


def emulator_file(source_folder: Path, mcu: dict) -> Path:
    """Returns the full path of the emulator's file. `mcu`, a checked [mcu]
    table, gives the file's path from the source folder `source_folder`."""
    return (Path(source_folder) / mcu[EMULATOR]).resolve()
