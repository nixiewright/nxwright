"""The typefaces installed on the computer that nxwright can draw a font from
(font_drawing.py): the typeface files in the folders where Windows, macOS,
and other systems keep their fonts, that truetype.py reads and that have
every letter of an encoding. Of a collection, the first typeface alone is
listed, as truetype.py reads it alone."""
from dataclasses import dataclass
import os
from pathlib import Path
import sys

from nxwright import NxwrightError
from nxwright.project.font_drawing import lacks_a_letter
from nxwright.project.truetype import NOTO_SANS, TYPEFACE_SUFFIXES, TrueTypeFont
from nxwright.project.zi_font import FONT_ENCODINGS, UTF8


@dataclass(frozen=True)
class Typeface:
    """A typeface nxwright can draw a font from: its name, as
    TrueTypeFont.typeface_name gives it, and its typeface file."""
    name: str
    path: Path


def font_folders() -> list:
    """Returns the folders where this computer's system keeps installed fonts,
    whether they exist or not."""
    home = Path.home()
    if sys.platform == "win32":
        folders = [Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"]
        if os.environ.get("LOCALAPPDATA"):
            folders.append(Path(os.environ["LOCALAPPDATA"]) / "Microsoft" / "Windows" / "Fonts")
        return folders
    if sys.platform == "darwin":
        return [Path("/System/Library/Fonts"), Path("/Library/Fonts"),
                home / "Library" / "Fonts"]
    return [Path("/usr/share/fonts"), Path("/usr/local/share/fonts"),
            home / ".local" / "share" / "fonts", home / ".fonts"]


def installed_typefaces(encoding: str, folders: list = None) -> list:
    """Returns the Typefaces nxwright can draw a font of `encoding` from.
    Noto Sans, the file nxwright ships, comes first, in every encoding, as
    keyboards and new folders draw from it, though it lacks some encodings'
    letters. Then come the typeface files of `folders`, by default
    font_folders(), and of their subfolders, in order of name. A file
    truetype.py does not read, or that lacks a letter of a one-byte or
    two-byte encoding, is left out, and so is a typeface whose name is
    listed already. A typeface that lacks only other characters, such as
    koi8-r's box-drawing symbols, is listed: a font drawn from it leaves
    them out, or in a two-byte encoding empty (font_drawing.drawn_codes). In
    utf-8, the characters are chosen as the font is drawn, which leaves out
    any the typeface lacks. Raises NxwrightError for an encoding no project
    can have."""
    if encoding not in FONT_ENCODINGS:
        raise NxwrightError("a font in %s cannot be drawn: it is no encoding a project can have"
                            % encoding)
    shipped = _typeface(NOTO_SANS, UTF8)
    found = {shipped.name: shipped} if shipped else {}
    for folder in font_folders() if folders is None else folders:
        for path in _typeface_files(Path(folder)):
            typeface = _typeface(path, encoding)
            if typeface and typeface.name not in found:
                found[typeface.name] = typeface
    others = sorted((typeface for typeface in found.values() if typeface is not shipped),
                    key=lambda typeface: typeface.name.casefold())
    return ([shipped] if shipped else []) + others


def _typeface_files(folder: Path):
    """Yields the typeface files of a folder and its subfolders, by their
    suffixes, in a fixed order. A folder that cannot be read is passed over,
    as os.walk does."""
    for root, folders, names in os.walk(folder):
        folders.sort()
        for name in sorted(names):
            if name.lower().endswith(TYPEFACE_SUFFIXES):
                yield Path(root) / name


def _typeface(path: Path, encoding: str):
    """Returns the Typeface of a typeface file that has every letter of
    `encoding`, by Unicode's categories, or any in utf-8, or None. A file
    without a name is named after the file."""
    try:
        font = TrueTypeFont(path.read_bytes())
        if encoding != UTF8 and lacks_a_letter(font, encoding):
            return None
        return Typeface(font.typeface_name() or path.stem, path)
    except (OSError, NxwrightError):
        return None
