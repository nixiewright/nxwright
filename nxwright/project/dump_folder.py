"""Reading the dump folders that `nxwright dump` writes.

The layout is described in docs/dumps.md. Pages, pictures, fonts,
animations, videos, and sounds are numbered by their Editor IDs.
"""
from pathlib import Path

from nxwright import NxwrightError
from nxwright.project.device_settings import HEADER_SIZE, read_device_settings
from nxwright.project.resources import PICTURE_SUFFIXES, CopiedKind

# First line of project.txt. It changes whenever the dump's layout does, so that
# a dump written by another version of nxwright is refused rather than misread.
DUMP_FORMAT_LINE = "dump format        3"
# A project's macros: the block holding them, which a project without
# macros lacks, and the dump's file of its bytes (format.md).
MACROS_BLOCK = "comcode.sn"
MACROS_FILE = "macros.s"


def check_dump_format(dump_folder: Path):
    """Stops on a folder that is not a dump in the current format.

    Dumps are temporary, so an older one is not converted: dump the project
    again instead.
    """
    summary = dump_folder / "project.txt"
    first_line = summary.read_text(encoding="utf-8").split("\n", 1)[0] if summary.exists() else ""
    if first_line != DUMP_FORMAT_LINE:
        raise NxwrightError("%s is not a dump in the current format; dump the project "
                            "again with nxwright dump" % dump_folder)


def dump_device_settings(dump_folder: Path):
    """Returns the DeviceSettings of the dump's project, from the manifest
    header bytes its project.txt shows, or None when it shows none or the
    screen model is not one nxwright knows."""
    summary = dump_folder / "project.txt"
    for line in summary.read_text(encoding="utf-8").split("\n") if summary.exists() else []:
        words = line.split()
        if len(words) == 2 and words[0] == "unknown_header":
            # The dump shows header bytes 8 to 23, then 32 to the end.
            shown = bytes.fromhex(words[1])
            if len(shown) != 16 + HEADER_SIZE - 32:
                return None
            header = bytearray(HEADER_SIZE)
            header[8:24] = shown[:16]
            header[32:HEADER_SIZE] = shown[16:16 + HEADER_SIZE - 32]
            return read_device_settings(bytes(header))
    return None


def page_text_files(dump_folder: Path) -> dict:
    """Returns {page ID: path} for the page files of a dump.

    Raises NxwrightError when a file name does not start with a page ID, or two
    files share an ID.
    """
    pages = {}
    for path in sorted((dump_folder / "pages").glob("*.txt")):
        prefix = path.name.split("-", 1)[0]
        if not (prefix.isascii() and prefix.isdigit()):
            raise NxwrightError("page file %s does not start with a page ID" % path.name)
        if int(prefix) in pages:
            raise NxwrightError("two page files have ID %d" % int(prefix))
        pages[int(prefix)] = path
    return pages


def numbered_files(folder: Path, suffix: str) -> dict:
    """Returns {ID: path} for files named "<ID><suffix>" in `folder`."""
    found = {}
    for path in folder.glob("*" + suffix):
        stem = path.name[:-len(suffix)]
        if stem.isascii() and stem.isdigit():
            found[int(stem)] = path
    return found


def check_ids_without_gaps(ids, noun: str):
    """Raises NxwrightError unless `ids` run from 0 without gaps. They are
    the dump's IDs of one kind of thing, and `noun` is its word, such as "page".
    The error gives the first ID missing."""
    present = set(ids)
    missing = next(number for number in range(len(present) + 1) if number not in present)
    if missing < len(present):
        raise NxwrightError("the dump's %s IDs must run from 0 without gaps: it has no %s %d"
                            % (noun, noun, missing))


def dump_pictures(dump_folder: Path) -> list:
    """Returns the dump's pictures in ID order, each as (its file's path
    within the dump, its bytes, its suffix): images/<ID>.png, .jpg, or one of
    the other suffixes a picture's record may give (resources.PICTURE_SUFFIXES).

    Raises NxwrightError when their IDs do not run from 0 without gaps, or
    one has two files."""
    found = {}
    for suffix in PICTURE_SUFFIXES:
        for picture_id, path in numbered_files(dump_folder / "images", suffix).items():
            if picture_id in found:
                raise NxwrightError("images/%s and images/%s are there; a picture has one "
                                    "file" % (found[picture_id].name, path.name))
            found[picture_id] = path
    check_ids_without_gaps(found, "picture")
    return [("images/" + found[picture_id].name, found[picture_id].read_bytes(),
             found[picture_id].suffix.lower()) for picture_id in range(len(found))]


def copied_file_name(resource_id: int, suffix: str) -> str:
    """Returns the name of a dump's file of one block of a font, animation,
    video, or sound: its ID, then the block's suffix ("03.screen.gmov")."""
    return "%02d%s" % (resource_id, suffix)


def copied_contents(dump_folder: Path, kind: CopiedKind) -> list:
    """Returns the files of a dump's fonts, animations, videos, or sounds
    (`kind`) in ID order, each as a tuple of the bytes of its blocks' files,
    in the order of `kind.blocks`.

    Raises NxwrightError when their IDs do not run from 0 without gaps, or
    one lacks a file."""
    found = [numbered_files(dump_folder / kind.folder, suffix) for suffix in kind.suffixes]
    ids = sorted(set().union(*found))
    check_ids_without_gaps(ids, kind.noun)
    for files, suffix in zip(found, kind.suffixes):
        missing = [resource_id for resource_id in ids if resource_id not in files]
        if missing:
            raise NxwrightError("the dump's %s %d has no %s file" % (kind.noun, missing[0], suffix))
    return [tuple(files[resource_id].read_bytes() for files in found) for resource_id in ids]
