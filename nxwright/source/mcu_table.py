"""The [mcu] table of a source folder's app.toml.

On real hardware, a microcontroller (the MCU) sits at the other end of the
screen's serial line. A project can have an MCU emulator, a Python program
that takes the microcontroller's place while the app runs in the simulator.
The [mcu] table gives that program's path:

    [mcu]
    emulator = "../mcu/main.py"
    wait = 10

`emulator` is the program's file, as a path from the source folder, with
forward slashes. `wait`, which is optional, is how many seconds a simulation
waits for the emulator to connect before the app starts. Without `wait`, the
simulation waits DEFAULT_WAIT seconds. The build does not read the table.
"""
import math
from pathlib import Path

from nxwright import NxwrightError

# The table's keys.
EMULATOR = "emulator"
WAIT = "wait"
# How long a simulation waits for the emulator when `wait` is not given, in
# seconds.
DEFAULT_WAIT = 10


def checked_mcu(table) -> dict:
    """Returns app.toml's [mcu] table `table` once checked, or an empty dict
    when `table` is None because app.toml has no such table. Raises
    NxwrightError if `table` is not a table, if it has a key other than
    `emulator` and `wait`, if `emulator` is missing or is not a path written
    with forward slashes, or if `wait` is not a number of seconds."""
    if table is None:
        return {}
    if not isinstance(table, dict):
        raise NxwrightError("app.toml: mcu must be a table, as in [mcu]")
    extra = set(table) - {EMULATOR, WAIT}
    if extra:
        raise NxwrightError("app.toml: unknown key %s in [mcu]" % sorted(extra)[0])
    emulator = table.get(EMULATOR)
    if not isinstance(emulator, str) or not emulator or "\\" in emulator:
        raise NxwrightError("app.toml: emulator in [mcu] must be the path of the emulator's "
                            "Python file from the source folder, with forward slashes, such "
                            "as \"../mcu/main.py\"")
    if WAIT in table and not is_wait(table[WAIT]):
        raise NxwrightError("app.toml: wait in [mcu] must be a number of seconds, 0 or more, "
                            "such as 10")
    return dict(table)


def is_wait(value) -> bool:
    """Returns whether `value` can be a wait for the emulator: a number of
    seconds, 0 or more."""
    # TOML's and JSON's true becomes Python's True, which is an int, so a
    # bool is ruled out separately.
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and value >= 0)


def emulator_wait(mcu: dict) -> float:
    """Returns how many seconds a simulation waits for the emulator to
    connect before the app starts. `mcu` is a checked [mcu] table, or an
    empty dict for a project without one."""
    return mcu.get(WAIT, DEFAULT_WAIT)


def emulator_file(source_folder: Path, mcu: dict) -> Path:
    """Returns the full path of the emulator's file. `mcu`, a checked [mcu]
    table, gives the file's path from the source folder `source_folder`."""
    return (Path(source_folder) / mcu[EMULATOR]).resolve()
