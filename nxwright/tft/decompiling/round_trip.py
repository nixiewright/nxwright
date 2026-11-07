"""The round trip of a TFT file: the source folder the decompiler writes for
it, built and compiled again around the file's own firmware, then compared with the file by what the two hold (compared.py).

The decompile command makes it into a folder of its own. It writes the
folder it was given at once when the two files give the same, and asks
first otherwise.

A failure to read the file given is refused, even where the round trip
reads the file again after writing its folder, as it cuts the file's
pictures and fonts apart to compare them. Any other failure only means
that the folder could not be checked: nxwright's build refusing the
folder, the compile refusing its project, or the decompiler failing to read
the file it compiled again. The round trip then gives the refusal as its
unchecked_reason, and the folder stays written. As the same errors can
come from either file, the round trip reads the file given before it
compiles the folder again, and tells the two apart by that step.

A file of a Nextion Editor older than every version nxwright was tested with,
such as 1.63.3, has no round trip: its folder is written but not compiled
again, as nxwright compiles only for 1.68.2's layout, whose user code is laid
out otherwise. A warning says so. For a file of a tested version, the
round trip leaves out the compile's check of the firmware's version, as
the file already holds its firmware.

A picture is taken as the same when its pixels are. nxwright compresses a
picture into other colour blocks than the Nextion Editor may, of the same
pixels, and a picture of another size moves every place, size, and
checksum after it. So before the folder's project is packaged again, each
of its pictures whose pixels are the file's takes the file's own screen
copy in its place, and the two files then agree there byte for byte. A
picture of other pixels, or one that cannot be decoded, keeps the
project's screen copy, and the comparison finds it.

A font is taken as the same when its characters are, for the same reason:
a font's glyphs can be coded in other bytes of the same pixels, and
nxwright codes them its own way when it turns a font. Two fonts are the
same when nxwright writes them alike at 0 degrees (zi_font.turned_font),
which keeps the header but for the orientation and the table's layout,
the font's description, and each character's advance, overhangs, and
coverages. Such a font of the folder's project takes the file's own block
in its place. On F, that block is at 0 degrees, and the compile writes a
font already at 0 degrees as it is (packaging._fonts).

The round trip takes what it can from the decompile, rather than making it
again: it compares the file given as the decompile decoded it. The
decompile writes each font into the folder as the file keeps it, so the
folder's project has the file's own fonts, and none is turned to compare
them.
"""
from dataclasses import replace
from pathlib import Path
from typing import NamedTuple, Optional

from nxwright import NxwrightError
from nxwright.project.screen_copy import decode_screen_copy
from nxwright.project.zi_font import turned_font

from nxwright.tft import frame
from nxwright.tft.commands.compile import project_of_folder
from nxwright.tft.decompiling.compared import compared_mismatches, read_for_comparison
from nxwright.tft.decompiling.decoded_file import FONT_ROW, PICTURE_ROW, resource_count
from nxwright.tft.decompiling.folder import written_folder
from nxwright.tft.decompiling.resources import picture_blocks, stored_font_blocks
from nxwright.tft.firmware import firmware_from_tft
from nxwright.tft.firmware_versions import MATCHED_VERSIONS, matched_versions_text, version_text
from nxwright.tft.matching import project_needs, refuse_unmatched
from nxwright.tft.packaging import Firmware, package
from nxwright.tft.project import Project
from nxwright.tft.tft_file import TftFile, read_tft


class RoundTrip(NamedTuple):
    """A round trip's result: `original`, the TFT file given; `again`, the
    file compiled again from the folder the decompiler wrote, or None for a
    file of an older Nextion Editor, which is not compiled again, or for a
    folder that could not be compiled again; `mismatches`, each
    compared.Mismatch between what the two contain, none when the decompiler
    read the file whole, or when nothing was compiled again; `names`, each
    name no guess matched, as (what it names, its decoded_file.Name), as
    folder.unmatched_names gives them; `warning`, which says that the file
    was made by a Nextion Editor older than any nxwright was tested with, or
    None; and `unchecked_reason`, the refusal that kept the folder from
    being compiled again and read (the module's docstring), or None."""
    original: TftFile
    again: Optional[TftFile]
    mismatches: list
    names: list
    warning: Optional[str] = None
    unchecked_reason: Optional[str] = None


class FilesResources(NamedTuple):
    """The pictures' and the fonts' blocks of a TFT file, in ID order, which
    the folder's project takes in place of its own where they show the same
    (the module's docstring)."""
    pictures: list
    fonts: list


def round_trip(tft_bytes: bytes, where: str, folder: Path) -> RoundTrip:
    """Writes the source folder of the TFT file `tft_bytes`, which messages
    call `where`, into `folder`, which must not exist or be empty. Then, but
    for a file of an older Nextion Editor, compiles that folder again around
    the file's own firmware. Returns the RoundTrip, whose unchecked_reason
    gives the refusal when nxwright's build or the compile refuses the
    folder, or the file compiled again cannot be read. Raises TftFileError
    for a file the compile's reader cannot read, DecodeError for what the
    decoders cannot read back of it, and NxwrightError for a folder that
    cannot be written."""
    original = read_tft(tft_bytes, where)
    written = written_folder(original, folder)
    names = written.names
    warning = _older_editor_warning(original.version)
    if warning is not None:
        return RoundTrip(original, None, [], names, warning)
    firmware = firmware_from_tft(tft_bytes, where, original.series)
    # Every read of the file given comes first, so that a failure there is
    # still refused, and not taken for the folder's. The file given is
    # compared as the decompile decoded it.
    given = read_for_comparison(original, written.decoded)
    resources = files_resources(original)
    try:
        again = _compiled(folder, firmware, resources)
        read_again = read_for_comparison(again)
    except NxwrightError as error:
        return RoundTrip(original, None, [], names, unchecked_reason=str(error))
    return RoundTrip(original, again, compared_mismatches(given, read_again), names)


def compiled_again(folder: Path, firmware: Firmware,
                   original: Optional[TftFile] = None) -> TftFile:
    """Returns the TFT file that nxwright compiles from the source folder
    `folder` around `firmware`, of whatever version. When `original` is
    given, each of the project's pictures whose pixels are those of
    `original`'s picture of the same ID is compiled from `original`'s
    screen copy, and each font of the same characters from `original`'s
    font (the module's docstring). Raises DecodeError when `original`'s
    pictures or fonts cannot be cut apart, and NxwrightError when
    nxwright's build or the compile refuses the folder's project."""
    return _compiled(folder, firmware, None if original is None else files_resources(original))


def files_resources(original: TftFile) -> FilesResources:
    """Returns the pictures' and the fonts' blocks of `original`. Raises
    DecodeError when its part of pictures or of fonts cannot be cut
    apart."""
    return FilesResources(
        picture_blocks(original.table_part(original.table[PICTURE_ROW]),
                       resource_count(original, "picture")),
        stored_font_blocks(original.table_part(original.table[FONT_ROW]),
                           resource_count(original, "font")))


def _compiled(folder: Path, firmware: Firmware, resources: Optional[FilesResources]) -> TftFile:
    """Returns the TFT file compiled from `folder` around `firmware`, with
    the file's `resources` where they show the same, as compiled_again
    does. Raises NxwrightError when nxwright's build or the compile refuses
    the folder's project, and TftFileError when the file compiled again
    cannot be read."""
    project = project_of_folder(folder)
    if resources is not None:
        project = _with_the_files_fonts(_with_the_files_pictures(project, resources.pictures),
                                        resources.fonts)
    refuse_unmatched(project_needs(project))
    return read_tft(package(project, frame.user_code(project), firmware),
                    "the TFT file compiled again")


def _with_the_files_pictures(project: Project, files: list) -> Project:
    """Returns `project` with each picture whose pixels are those of the
    file's picture of the same ID, of the blocks `files`, in the file's
    screen copy."""
    names = [name for kind, name in project.resources if kind == "picture"]
    rotation = project.settings.rotation
    kept = {}
    for name, block in zip(names, files):
        try:
            same = (decode_screen_copy(project.blocks[name], rotation)
                    == decode_screen_copy(block, rotation))
        except NxwrightError:
            # The comparison finds a picture that does not decode.
            same = False
        if same:
            kept[name] = block
    return replace(project, blocks={**project.blocks, **kept})


def _with_the_files_fonts(project: Project, files: list) -> Project:
    """Returns `project` with each font of the same characters as the
    file's font of the same ID, of the blocks `files`, in the file's block
    (the module's docstring)."""
    names = [name for kind, name in project.resources if kind == "font"]
    kept = {}
    for name, block in zip(names, files):
        own = project.blocks[name]
        if own == block:
            continue
        try:
            same = turned_font(own, 0) == turned_font(block, 0)
        except NxwrightError:
            # The comparison finds a font that nxwright cannot write again.
            same = False
        if same:
            kept[name] = block
    return replace(project, blocks={**project.blocks, **kept})


def _older_editor_warning(version: tuple) -> Optional[str]:
    """Returns the warning for a file of the Nextion Editor's `version` when
    it is older than every version nxwright was tested with, or None."""
    oldest = min(MATCHED_VERSIONS)
    if version >= oldest:
        return None
    return ("this file was made by the Nextion Editor %s. nxwright compiles only with the firmware "
            "of the Nextion Editor %s, so the round trip check is disabled."
            % (version_text(version), matched_versions_text()))
