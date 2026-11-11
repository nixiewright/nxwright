"""The files a screen keeps in its memory, whose paths start with `ram/`.

A project sets space aside for these files with the device setting
"Memory file storage size", which is `memory_file_storage_size` in
app.toml, and is 0 by default. The files share that space. If no space
is set aside, the screen does not create any `ram/` file.

The test machine keeps `ram/` files with its other files, in the dict
"file contents" (editor_machine.py). The functions here apply newfile,
twfile, and refile to a `ram/` path in that dict, and check whether a data
record can create its data file in `ram/`. Each returns None if the screen
accepts the command or can create the file, and the reason otherwise,
worded for the simulator's log. When the screen ignores a
command, it answers 0x06, an invalid file operation, and the dict stays
as it was unless the function's docstring describes a change.

Every rule here follows what the Nextion Editor's simulator did for a
screen of the Intelligent series. No real screen has been checked yet.
The probe in tools/screen/, in nxwright's repository, runs the checks on
one.
"""

# How the path of a file in the screen's memory starts. The Nextion
# Editor's simulator rejected `RAM/`.
RAM = "ram/"

# Each file uses FILE_COST bytes of the space set aside, on top of its own
# bytes, and UNUSABLE_SPACE bytes of that space are never available. Both
# numbers were worked out from the largest files the Nextion Editor's
# simulator created: one file alone, then several, with 4096 and with 8192
# bytes set aside.
FILE_COST = 268
UNUSABLE_SPACE = 16

# Reasons the screen ignores a command, worded for the simulator's log.
NO_SPACE = ("the project does not set space aside for ram/ files. Set "
            "memory_file_storage_size in app.toml")
NO_FOLDERS = "ram/ has no folders"


def is_ram_path(path) -> bool:
    """Whether `path`, the path a file command was given, is in the
    screen's memory."""
    return isinstance(path, str) and path.startswith(RAM)


def _names_a_file(path) -> bool:
    """Whether `path` is a `ram/` path with no folder in it. `ram/` has no
    folders, so the screen cannot create a file at a path such as
    `ram/logs/a.bin`."""
    return is_ram_path(path) and "/" not in path[len(RAM):]


def room(files: dict, space: int) -> int:
    """Returns the most bytes a new file can have in `space`, the number
    of bytes the project sets aside. The `ram/` files already in `files`,
    {path: bytes}, use part of that space. The result is below 0 if not
    even an empty file fits."""
    taken = sum(FILE_COST + len(data) for path, data in files.items() if is_ram_path(path))
    return space - UNUSABLE_SPACE - taken - FILE_COST


def fits(size: int, files: dict, space: int) -> bool:
    """Whether a new file of `size` bytes fits in `space` beside the
    `ram/` files already in `files` (room)."""
    return size <= room(files, space)


def _why_no_room(size: int, files: dict, space: int) -> str | None:
    """Returns why a new file of `size` bytes does not fit in `space`
    beside the `ram/` files in `files`, or None if it fits."""
    if space <= 0:
        return NO_SPACE
    most = room(files, space)
    if size <= most:
        return None
    if most < 0:
        return "no new file fits in the %d bytes set aside for ram/ files" % space
    return ("the file does not fit. A new file can have at most %d of the %d bytes set aside "
            "for ram/ files" % (most, space))


def why_no_new_file(files: dict, path: str, size: int, space: int) -> str | None:
    """Returns why the screen cannot create a new file of `size` bytes at
    the `ram/` path `path`, or None if it can. The new file must fit
    beside every file already in `ram/`. The machine calls this before a
    data record creates its data file, and for a `twfile` before its
    transfer starts. The file that the `twfile` will replace still exists
    then, so the new file must fit beside it."""
    if not _names_a_file(path):
        return NO_FOLDERS
    return _why_no_room(size, files, space)


def new_file(files: dict, path: str, size: int, space: int) -> str | None:
    """Runs `newfile` for a file of `size` bytes at the `ram/` path `path`.
    If the file exists with that size, it keeps its bytes. If it exists
    with another size, it is removed first, so the new file needs no room
    beside it. The new file, all zero bytes, is then created if it fits.
    If it does not fit, the old file stays removed. Returns None, or why
    the screen ignores the command."""
    if not _names_a_file(path):
        return NO_FOLDERS
    old = files.get(path)
    if old is not None and len(old) == size:
        return None
    files.pop(path, None)
    reason = _why_no_room(size, files, space)
    if reason is None:
        files[path] = bytes(size)
    return reason


def rename_file(files: dict, path: str, new_path: str) -> str | None:
    """Runs `refile` on the `ram/` path `path`. The file is renamed to
    `new_path`, which must be in `ram/` too, and must not exist yet.
    Returns None, or why the screen ignores the command."""
    if path not in files:
        return "%s does not exist" % path
    if not is_ram_path(new_path):
        return "%s is not in ram/" % new_path
    if not _names_a_file(new_path):
        return "%s is in a folder, and %s" % (new_path, NO_FOLDERS)
    if new_path in files:
        return "%s exists already" % new_path
    files[new_path] = files.pop(path)
    return None
