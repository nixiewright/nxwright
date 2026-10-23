"""A simulation's SD cards as folders of the computer.

The screen has two SD cards, `sd0/` and `sd1/`. The Editor's simulator keeps
each as a folder of its own, `sdcard0` and `sdcard1` in its settings folder,
so that the app's files are real files. A simulation can be given any
folder for each (`FolderCards`). `sd0/presets/a.cfg` is then the file
`presets/a.cfg` in the folder given for `sd0/`. A path on a card given no
folder, a `ram/` file, and a path on no card stay in the test machine's
memory, as without folders (editor_machine.py, "existing" and "file
contents").

The folders are the user's own, so nothing the app does may harm what lies
outside them, or the folders themselves. Each path is checked to lie
inside its card's folder before anything reads, writes, or deletes, and
the helpers that delete or rename refuse what could do harm: a card's own
folder, a folder that is not empty, a name that exists already. A refusal
raises CardRefusal, which the machine records with the file errors.
"""
from pathlib import Path, PureWindowsPath
import re

from nxwright import NxwrightError

# The cards a folder can stand for, as the app's paths start.
CARDS = ("sd0/", "sd1/")


# The return code the screen gives a file command it refuses: an invalid
# file operation, as the Editor's simulator answered.
INVALID_FILE_OPERATION = 0x06


class CardRefusal(Exception):
    """A file command the cards refuse: its reason, and `code`, the return
    code the screen gives it. A refusal the screen would not make, one
    nxwright adds so as to harm nothing, has none: the screen's answer is a
    success."""

    def __init__(self, reason: str, code: int = None):
        super().__init__(reason)
        self.code = code


def card_folder(text: str) -> Path:
    """Returns the folder a launch configuration names for a card, checked:
    an existing folder, by its full path, not a drive's root. Raises
    NxwrightError, saying why, otherwise."""
    if not isinstance(text, str) or not text.strip():
        raise NxwrightError("an SD card's folder is named by its full path")
    path = Path(text)
    if not path.is_absolute():
        raise NxwrightError("an SD card's folder is named by its full path, not %s" % text)
    if not path.is_dir():
        raise NxwrightError("%s is no folder" % text)
    resolved = path.resolve()
    if resolved == Path(resolved.anchor):
        raise NxwrightError("an SD card's folder cannot be a drive's root, as %s is" % text)
    return resolved


def inside(root: Path, relative: str) -> Path:
    """Returns the path within the folder `root` (resolved) of a path on its
    card, `relative` to the card's own folder ("presets/a.cfg"). Raises
    CardRefusal for one that would leave it: by `..`, a drive, a path from
    the root of the disk, or a link leading out."""
    if PureWindowsPath(relative).drive or relative.startswith(("/", "\\")):
        raise CardRefusal("%s leaves the card" % relative)
    parts = [part for part in re.split(r"[/\\]", relative) if part not in ("", ".")]
    if ".." in parts:
        raise CardRefusal("%s leaves the card" % relative)
    path = root.joinpath(*parts).resolve()
    if path != root and not path.is_relative_to(root):
        raise CardRefusal("%s leaves the card" % relative)
    return path


class FolderCards:
    """The cards given folders: {card ("sd0/"), its folder}. `owns(path)`
    says whether a path is on one of them; the other methods act on such a
    path, raising CardRefusal where they would harm."""

    def __init__(self, folders: dict):
        self.folders = {card: card_folder(str(folder)) for card, folder in folders.items()
                        if card in CARDS}

    def owns(self, path: str) -> bool:
        return isinstance(path, str) and self._card_of(path) is not None

    def _card_of(self, path: str):
        lowered = path.lower()
        return next((card for card in self.folders
                     if lowered.startswith(card) or lowered == card[:-1]), None)

    def local(self, path: str) -> Path:
        """Returns where a path on a card lies on the computer."""
        card = self._card_of(path)
        return inside(self.folders[card], path[len(card):])

    def is_root(self, path: str) -> bool:
        card = self._card_of(path)
        return self.local(path) == self.folders[card]

    # What the app's file commands do.

    def find_file(self, path: str) -> bool:
        return self.local(path).is_file()

    def find_folder(self, path: str) -> bool:
        return self.local(path).is_dir()

    def read(self, path: str) -> bytes:
        """The file's bytes, or none for a file that does not exist."""
        local = self.local(path)
        return local.read_bytes() if local.is_file() else b""

    def write(self, path: str, data: bytes):
        """Writes over an existing file: the file stream writes only to one."""
        local = self.local(path)
        if not local.is_file():
            raise CardRefusal("%s is no file" % path)
        local.write_bytes(data)

    def new_file(self, path: str, size: int):
        """Makes a file of `size` zero bytes, in a folder that exists. One
        that exists already is left as it is. The test machine refuses a size
        below 0 before it comes here (editor_machine.py)."""
        local = self.local(path)
        if local.exists():
            return
        if not local.parent.is_dir():
            raise CardRefusal("%s's folder does not exist" % path, INVALID_FILE_OPERATION)
        local.write_bytes(bytes(size))

    def new_folder(self, path: str):
        """Makes a folder, and its missing parents; within the card, as
        every path is."""
        self.local(path).mkdir(parents=True, exist_ok=True)

    def delete_file(self, path: str):
        local = self._deletable(path)
        if not local.is_file():
            raise CardRefusal("%s is no file" % path)
        local.unlink()

    def delete_folder(self, path: str):
        """Deletes an empty folder. The screen deletes a full one too, as the
        Editor's simulator did, but the card's folder is the user's, and a
        mistake would delete their files: a full one is refused, though the
        screen's answer is a success."""
        local = self._deletable(path)
        if not local.is_dir():
            raise CardRefusal("%s is no folder" % path)
        if any(local.iterdir()):
            raise CardRefusal("%s is not empty" % path)
        local.rmdir()

    def rename(self, path: str, new_path: str):
        """Renames a file or a folder on its card, onto a name that does not
        exist, in a folder that does, so that nothing is overwritten."""
        local = self._deletable(path)
        if not local.exists():
            raise CardRefusal("%s does not exist" % path, INVALID_FILE_OPERATION)
        if not self.owns(new_path) or self._card_of(new_path) != self._card_of(path):
            raise CardRefusal("%s is not on %s's card" % (new_path, path))
        target = self._deletable(new_path)
        if target.exists():
            raise CardRefusal("%s exists already" % new_path, INVALID_FILE_OPERATION)
        if not target.parent.is_dir():
            raise CardRefusal("%s's folder does not exist" % new_path, INVALID_FILE_OPERATION)
        local.rename(target)

    def rename_folder(self, path: str, new_path: str):
        """Renames a folder on its card, with what it holds, as `redir`
        does: both paths end with "/", as the Editor's simulator required,
        and the first names a folder. Each refusal answers 06, as the
        Editor's simulator answered every one it was given."""
        try:
            if not (path.endswith("/") and new_path.endswith("/")):
                raise CardRefusal("%s and %s do not both end with /" % (path, new_path))
            if not self.local(path).is_dir():
                raise CardRefusal("%s is no folder" % path)
            self.rename(path, new_path)
        except CardRefusal as refusal:
            raise CardRefusal(str(refusal), INVALID_FILE_OPERATION) from None

    def _deletable(self, path: str) -> Path:
        """Returns where a path lies, refusing a card's own folder: the one
        check every deletion and renaming goes through."""
        if self.is_root(path):
            raise CardRefusal("%s is the card itself" % path)
        return self.local(path)

    def entries(self, folder: str) -> list:
        """The names in a folder of a card, a folder's ending with "/", or
        none for a folder that does not exist."""
        local = self.local(folder)
        if not local.is_dir():
            return []
        return [entry.name + ("/" if entry.is_dir() else "") for entry in local.iterdir()]
