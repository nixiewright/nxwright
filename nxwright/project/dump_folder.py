"""Reading the dump folders that `nxwright dump` writes.

The layout is described in docs/dumps.md. Pages, pictures, fonts,
animations, videos, and sounds are numbered by their Editor IDs.
"""
from pathlib import Path
import re

from nxwright import NxwrightError
from nxwright.project.device_settings import HEADER_SIZE, encoding_name, read_device_settings
from nxwright.project.page_text import page_line_name
from nxwright.project.pictures import picture_data_size
from nxwright.project.resources import (PICTURE_SUFFIXES, SOURCE_SUFFIX, CopiedKind, ImageSource,
                                        encode_image_source)
from nxwright.project.screen_copy import decode_screen_copy

# First line of project.txt. It changes whenever the dump's layout does, so that
# a dump written by another version of nxwright is refused rather than misread.
_FORMAT_LINE = "dump format        %d"
# Format 5 adds one form to format 4: the quoted page line of a page name that
# is not printable ASCII, or has a double quote (page_text.page_line_name). A
# dump without such a line stays in format 4, which an older nxwright still
# reads. Both are read.
_FORMATS_READ = (4, 5)
# A project's macros: the block holding them, which a project without
# macros lacks, and the dump's file of its bytes (format.md).
MACROS_BLOCK = "comcode.sn"
MACROS_FILE = "macros.s"


def dump_format_line(page_names: list) -> str:
    """Returns the first line of project.txt for a dump of the pages named
    `page_names`: format 5 when the page line of one of them is quoted, and
    format 4 otherwise."""
    quoted = any(page_line_name(name) != name for name in page_names)
    return _FORMAT_LINE % (5 if quoted else 4)


def check_dump_format(dump_folder: Path):
    """Stops on a folder that is not a dump in the current format.

    Dumps are temporary, so an older one is not converted: dump the project
    again instead.
    """
    summary = dump_folder / "project.txt"
    first_line = summary.read_text(encoding="utf-8").split("\n", 1)[0] if summary.exists() else ""
    if first_line not in [_FORMAT_LINE % found for found in _FORMATS_READ]:
        raise NxwrightError("%s is not a dump in the current format; dump the project "
                            "again with nxwright dump" % dump_folder)


def dump_device_settings(dump_folder: Path):
    """Returns the DeviceSettings of the dump's project, from the manifest
    header bytes its project.txt shows, or None when it shows none or the
    screen model is not one nxwright knows."""
    header = dump_manifest_header(dump_folder)
    return None if header is None else read_device_settings(header)


def dump_encoding(dump_folder: Path):
    """Returns the character encoding of the dump's project, by its
    manifest header's byte 13, which does not depend on the screen model
    (device_settings.encoding_name), or None when the dump shows no header."""
    header = dump_manifest_header(dump_folder)
    return None if header is None else encoding_name(header[13])


def dump_manifest_header(dump_folder: Path):
    """Returns the manifest header of the dump's project, as its project.txt
    shows it, or None when it shows none of HEADER_SIZE bytes. The dump
    shows bytes 8 to 23, then 32 to the end; the others are left 0."""
    shown = dump_header_bytes(dump_folder)
    if shown is None or len(shown) != 16 + HEADER_SIZE - 32:
        return None
    header = bytearray(HEADER_SIZE)
    header[8:24] = shown[:16]
    header[32:HEADER_SIZE] = shown[16:16 + HEADER_SIZE - 32]
    return bytes(header)


def dump_header_bytes(dump_folder: Path):
    """Returns the manifest header's bytes that the dump's project.txt shows,
    bytes 8 to 23, then 32 to the end, or None when it shows none, as in a
    dump written from a source folder."""
    summary = dump_folder / "project.txt"
    for line in summary.read_text(encoding="utf-8").split("\n") if summary.exists() else []:
        words = line.split()
        if len(words) == 2 and words[0] == "unknown_header":
            return bytes.fromhex(words[1])
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


# A picture's file in a dump: its ID, then one suffix, such as 0003.png.
_PICTURE_FILE = re.compile(r"(\d+)(\.[A-Za-z0-9]+)")


def dump_pictures(dump_folder: Path) -> list:
    """Returns the dump's pictures in ID order, each as (its file's path
    within the dump, its bytes, its suffix): images/<ID>.png, .jpg, or any
    other suffix a picture's record gives, as one of a type nxwright does not
    decode (resources.decodes_picture). The screen copies, images/<ID>.i, and
    the sources of resized pictures are not pictures' files.

    Raises NxwrightError when their IDs do not run from 0 without gaps, or
    one has two files."""
    found = {}
    folder = dump_folder / "images"
    # In PICTURE_SUFFIXES' order, then by name, so that a refusal of two
    # files of one picture names them in the same order each time.
    def suffix_order(path: Path) -> tuple:
        suffix = path.suffix.lower()
        return (PICTURE_SUFFIXES.index(suffix) if suffix in PICTURE_SUFFIXES
                else len(PICTURE_SUFFIXES), path.name)
    for path in sorted(folder.iterdir(), key=suffix_order) if folder.is_dir() else []:
        matched = _PICTURE_FILE.fullmatch(path.name)
        if matched is None or matched[2].lower() == ".i" or not path.is_file():
            continue
        picture_id = int(matched[1])
        if picture_id in found:
            raise NxwrightError("images/%s and images/%s are there; a picture has one "
                                "file" % (found[picture_id].name, path.name))
        found[picture_id] = path
    check_ids_without_gaps(found, "picture")
    return [("images/" + found[picture_id].name, found[picture_id].read_bytes(),
             found[picture_id].suffix.lower()) for picture_id in range(len(found))]


def kept_picture_blocks(dump_folder: Path, picture_id: int, file_name: str, data: bytes,
                        suffix: str, rotation: int) -> tuple:
    """Returns (the file's block, ".is", the screen copy, ".i") of the
    picture `picture_id`, in a file of a type nxwright does not decode
    (resources.decodes_picture): its file `data`, of `suffix`, at
    `file_name` within the dump, and the dump's screen copy of it,
    images/<ID>.i, as it is. The file's block gives the screen copy's
    width and height, which are the picture's.

    Raises NxwrightError, naming `file_name`, when the screen copy is
    missing or does not decode at `rotation`. The error carries
    `file_name` as its `file` and the rest as its `reason`, so that a
    build from a source folder can name the folder's file instead."""
    path = dump_folder / "images" / ("%04d.i" % picture_id)
    if not path.is_file():
        reason = ("nxwright does not decode this type of picture, and its screen copy is "
                  "missing; save the picture as a PNG, JPEG, BMP, or GIF file")
    else:
        block = path.read_bytes()
        try:
            pixels = decode_screen_copy(block, rotation)
        except NxwrightError as error:
            reason = "its screen copy: %s" % error
        else:
            return encode_image_source(ImageSource(pixels.width, pixels.height, data,
                                                   suffix)), block
    refusal = NxwrightError("%s: %s" % (file_name, reason))
    refusal.file, refusal.reason = file_name, reason
    raise refusal


def dump_picture_sources(dump_folder: Path, picture_count: int) -> dict:
    """Returns the sources of the dump's resized pictures, {picture ID: (its
    file's path within the dump, its bytes, its suffix)}: the files named
    images/<ID>.source with one of a picture's suffixes, such as
    images/0002.source.png. A picture never resized has none. Raises
    NxwrightError when one picture has two, or one is of a picture ID past
    the dump's `picture_count` pictures."""
    found = {}
    for suffix in PICTURE_SUFFIXES:
        for picture_id, path in numbered_files(dump_folder / "images",
                                               SOURCE_SUFFIX + suffix).items():
            if picture_id in found:
                raise NxwrightError("images/%s and images/%s are there; a picture has one "
                                    "source file" % (found[picture_id].name, path.name))
            if picture_id >= picture_count:
                raise NxwrightError("images/%s is there, but no picture %d; a source file goes "
                                    "with its picture" % (path.name, picture_id))
            found[picture_id] = path
    return {picture_id: ("images/" + path.name, path.read_bytes(),
                         path.suffix.lower()) for picture_id, path in found.items()}


def picture_source_block(path: str, data: bytes, suffix: str) -> bytes:
    """Returns the block of a resized picture's source (".ib") for the
    dump's file `data`, of `suffix`, at `path` within the dump. Its record
    gives the file's own width and height, as the Editor's does. Raises
    NxwrightError, naming `path`, for a file nxwright cannot read."""
    try:
        width, height = picture_data_size(data)
    except NxwrightError as error:
        raise NxwrightError("%s: %s" % (path, error)) from None
    return encode_image_source(ImageSource(width, height, data, suffix))


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
