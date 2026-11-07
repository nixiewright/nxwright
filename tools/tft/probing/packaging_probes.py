"""The probes of packaging (packaging.py), on the T base folder: blank, with
a picture, with two pictures and two fonts, and with a line of event code.
Run them with `tools.tft.probe run packaging_probes`.

nxwright does not write the user code yet, so each probe borrows the Nextion
Editor's own from its file, packages it with the firmware of the Nextion
Editor the probes drive (probe_firmware), and compares the whole file with
the Nextion Editor's, part by part.

The probe with two pictures and two fonts keeps packaging's fixtures: the
headers, the section's table, and the file's checksum. They are made on
zeros for the firmware, around a user code of nxwright's own
(stand_in_user_code), so that no fixture holds anything the Nextion Editor
wrote.
"""
import os
from pathlib import Path

from PIL import Image

from nxwright import NxwrightError

from nxwright.tft.firmware import firmware_of_editor_program, installed_firmware, zero_firmware
from nxwright.tft.packaging import Firmware, package
from tools.tft.probing.probe_runner import CouldNotRun, Probe, ProbeError, ProbeMismatch
from nxwright.tft.project import Project
from nxwright.tft.tft_file import (HEADER_1_SIZE, HEADER_2_END, TABLE_SIZE, TftFileError, UserCode,
                            VARIABLE_SIZE, PAGE_INDEX_ENTRY_SIZE, read_tft)

FIXTURES = "packaging"


def stand_in_user_code(project: Project) -> UserCode:
    """Returns a user code of nxwright's own for `project`, which packaging's
    fixtures are made around: an empty first block and a 0 word, three int
    variables of zeros, and a page index entry of zeros for each page. Its
    bytes mean nothing: packaging reads only its places and sizes, and
    checksums it."""
    return UserCode([b"", b""], b"", bytes(3 * VARIABLE_SIZE), b"",
                    bytes(PAGE_INDEX_ENTRY_SIZE * len(project.pages)), b"")


def fixture_pieces(project: Project, firmware: Firmware) -> dict:
    """Returns the pieces packaging's fixtures keep, from packaging `project`
    around stand_in_user_code with `firmware`, zeros in tests: the two
    headers, the section's table, and the file's checksum."""
    data = package(project, stand_in_user_code(project), firmware)
    section = read_tft(data, "nxwright's packaging", check=False).section_place
    return {"header-1": data[:HEADER_1_SIZE], "header-2": data[HEADER_1_SIZE:HEADER_2_END],
            "table": data[section:section + TABLE_SIZE], "checksum": data[-4:]}


def file_parts(data: bytes, where: str) -> dict:
    """Returns the file's parts, as the probes compare them."""
    tft = read_tft(data, where, check=False)
    section, user = tft.section_place, tft.user_code_place
    return {"header-1": data[:HEADER_1_SIZE], "header-2": data[HEADER_1_SIZE:HEADER_2_END],
            "filler": data[HEADER_2_END:section], "section": data[section:user],
            "user-code": data[user:-4], "checksum": data[-4:]}


def probe_firmware(series: str = "T") -> Firmware:
    """Returns the firmware of `series` that the probes package with: that of
    the Nextion Editor they drive, so that nxwright's file and the Editor's
    differ only where nxwright writes otherwise. That Editor is the one
    NXWRIGHT_EDITOR names, of whatever release, or else the installed one.
    Raises ProbeError where there is none, and CouldNotRun when a firmware
    file cannot be read, as when a release lacks one of the series' files."""
    program = os.environ.get("NXWRIGHT_EDITOR")
    try:
        if program:
            return firmware_of_editor_program(Path(program), series,
                                              "the Nextion Editor that NXWRIGHT_EDITOR names")
        firmware = installed_firmware(series)
    except NxwrightError as error:
        raise CouldNotRun(str(error)) from None
    if firmware is None:
        raise ProbeError("the probes need the installed Nextion Editor's firmware")
    return firmware


def _user_code(data: bytes) -> UserCode:
    """Returns the Nextion Editor's user code, which the probes borrow."""
    try:
        return read_tft(data, "the Nextion Editor's file").user_code
    except TftFileError as error:
        raise ProbeMismatch(str(error)) from None


def _ours(project: Path, user_code: UserCode) -> dict:
    loaded = Project.from_file(project)
    data = package(loaded, user_code, probe_firmware(loaded.settings.model.series))
    return file_parts(data, "nxwright's file")


def _theirs(data: bytes) -> dict:
    return file_parts(data, "the Nextion Editor's file")


def _kept(project: Path) -> dict:
    loaded = Project.from_file(project)
    return fixture_pieces(loaded, zero_firmware(probe_firmware(loaded.settings.model.series)))


def _add_picture(folder: Path):
    from nxwright.source.resource_adding import add_pictures
    # Drawn beside the folder, which add_pictures copies it into.
    picture = folder.parent / "red.png"
    Image.new("RGB", (8, 4), (255, 0, 0)).save(picture)
    add_pictures(folder, [picture])


def _add_two_of_each(folder: Path):
    """Two pictures of different sizes, and a second font, so that the
    pictures and the fonts each lie back to back in the section."""
    from nxwright.project.truetype import NOTO_SANS
    from nxwright.source.resource_adding import add_font, add_pictures
    pictures = [folder.parent / "red.png", folder.parent / "blue.png"]
    Image.new("RGB", (8, 4), (255, 0, 0)).save(pictures[0])
    Image.new("RGB", (4, 8), (0, 0, 255)).save(pictures[1])
    add_pictures(folder, pictures)
    add_font(folder, NOTO_SANS, 16)


def _add_code(folder: Path):
    # The base folders are in nxlang.
    (folder / "pages" / "page0.nx").write_text("on page0.down:\n  dim = 50\n", encoding="utf-8")


PROBES = [
    Probe("packaging-T-blank", "T", None, _ours, _theirs, borrows=_user_code),
    Probe("packaging-T-picture", "T", _add_picture, _ours, _theirs, borrows=_user_code),
    Probe("packaging-T-two-each", "T", _add_two_of_each, _ours, _theirs, FIXTURES, _kept,
          borrows=_user_code),
    Probe("packaging-T-code", "T", _add_code, _ours, _theirs, borrows=_user_code),
]
