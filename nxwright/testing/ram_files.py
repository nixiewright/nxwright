"""The files a screen keeps in its memory, whose paths start with `ram/`.

A project sets space aside for these files with the device setting
"Memory file storage size", which is `memory_file_storage_size` in
app.toml, and is 0 by default. The files share that space. If no space
is set aside, the screen does not create any `ram/` file.

The test machine keeps `ram/` files with its other files, in the dict
"file contents" (editor_machine.py). The functions here apply newfile,
twfile, and refile to a `ram/` path in that dict, and each returns
whether the screen accepts the command. If the screen ignores the
command, it answers 0x06, an invalid file operation, and the dict stays
as it was, unless the function's docstring describes a change.

Every rule here follows what the Nextion Editor's simulator did for a
screen of the Intelligent series. No real screen was probed.
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


def is_ram_path(path) -> bool:
    """Whether `path`, the path a file command was given, is in the
    screen's memory."""
    return isinstance(path, str) and path.startswith(RAM)


def _names_a_file(path) -> bool:
    """Whether `path` is a `ram/` path with no folder in it. `ram/` has no
    folders, so the screen cannot create a file at a path such as
    `ram/logs/a.bin`."""
    return is_ram_path(path) and "/" not in path[len(RAM):]


def fits(size: int, files: dict, space: int) -> bool:
    """Whether a new file of `size` bytes fits in `space`, the number of
    bytes the project sets aside. The `ram/` files already in `files`,
    {path: bytes}, use part of that space."""
    taken = sum(FILE_COST + len(data) for path, data in files.items() if is_ram_path(path))
    return UNUSABLE_SPACE + taken + FILE_COST + size <= space


def takes_transfer(files: dict, path: str, size: int, space: int) -> bool:
    """Whether `twfile` starts a transfer of `size` bytes to the `ram/`
    path `path`. The new file must fit beside every file in `ram/`,
    including the one it will replace."""
    return _names_a_file(path) and fits(size, files, space)


def new_file(files: dict, path: str, size: int, space: int) -> bool:
    """Runs `newfile` for a file of `size` bytes at the `ram/` path `path`.
    If the file exists with that size, it keeps its bytes. If it exists
    with another size, it is removed first, so the new file needs no room
    beside it. The new file, all zero bytes, is then created if it fits.
    If it does not fit, the old file stays removed."""
    if not _names_a_file(path):
        return False
    old = files.get(path)
    if old is not None and len(old) == size:
        return True
    files.pop(path, None)
    if not fits(size, files, space):
        return False
    files[path] = bytes(size)
    return True


def rename_file(files: dict, path: str, new_path: str) -> bool:
    """Runs `refile` on the `ram/` path `path`. The file is renamed to
    `new_path`, which must be in `ram/` too, and must not exist yet."""
    if path not in files or new_path in files or not _names_a_file(new_path):
        return False
    files[new_path] = files.pop(path)
    return True
