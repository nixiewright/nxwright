"""The firmware a TFT file holds, read at run time. The firmware is the
vendor's, so nxwright never keeps it in the repository.

A compile finds the firmware with find_firmware, which tries these sources
in turn:
  1. a TFT file or a Nextion Editor folder the user names. Nothing else is
     tried, and a named source that cannot be read stops the compile;
  2. the cache: firmware an earlier compile found, kept in the user's cache
     folder (nxwright's picture_cache.cache_folder), one folder for each
     version, such as .../nxwright/firmware/1.68.2/asp0.dll;
  3. the installed Nextion Editor;
  4. a download from Nextion's site, with the user's consent
     (firmware_download.py): its zip, whose every series' files are cached,
     or else, on Windows with no Nextion Editor installed, its installer.
     When neither serves, Nextion's download page is offered.
Steps 2 to 4 skip a source that cannot serve, and keep the reason. A
download that the user declines, that breaks off, or whose zip is refused
stops the compile.

A matched version is one that nxwright's probes were matched with
(firmware_versions.py). Firmware of a matched version is checked file by
file against its hashes, and written to the cache once found. Firmware of
any other version, older or later, is skipped in steps 2 and 3, and refused
when it is named.

The installed Nextion Editor is found through the registry, as nxwright's
pinyin table finds it (testing/pinyin_table.py), taking the
first install listed. Its version is its program's, "Nextion Editor.exe",
whose first three numbers a TFT file's header 1 records: 1.68.2 for the
Nextion Editor 1.68.2. Off Windows, where Windows' own functions are not
there, pefile reads that version from the program.
"""
import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import hashlib
from pathlib import Path
import sys
from typing import Optional

from nxwright import NxwrightError
from nxwright.project.picture_cache import cache_folder

from nxwright.tft import firmware_versions
from nxwright.tft.firmware_download import DownloadAsker, download_zip, install_editor, offer_of
from nxwright.tft.firmware_versions import matched_versions_text, version_text
from nxwright.tft.packaging import Firmware
from nxwright.tft.tft_file import SERIES, firmware_names, read_tft

_PROGRAM = "Nextion Editor.exe"
# The uninstall entries of the registry, where the installer records its folder.
_UNINSTALL_KEYS = (r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
                   r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall")


def installed_firmware(series: str):
    """Returns the firmware of `series` from the installed Nextion Editor, or
    None where there is none, as on another system than Windows. Raises
    NxwrightError when a firmware file is missing from its folder. Neither
    the version nor the hashes are checked."""
    folder = installed_editor_folder()
    if folder is None:
        return None
    return firmware_from_editor_folder(folder, series, "the installed Nextion Editor")


def firmware_from_editor_folder(folder: Path, series: str, where: str) -> Firmware:
    """Returns the firmware of `series` from the Nextion Editor folder
    `folder`, which `where` names in messages. The version is that of the
    folder's program, "Nextion Editor.exe" (program_version). Raises
    NxwrightError when a firmware file cannot be read, or the program's
    version cannot. The hashes are not checked."""
    return firmware_of_editor_program(folder / _PROGRAM, series, where)


def firmware_of_editor_program(program: Path, series: str, where: str) -> Firmware:
    """Returns the firmware of `series` from the folder of the Nextion
    Editor's program `program`, at the version of that program. The zips of
    releases before 1.68 name the program NextionEditor.exe, without the
    space the installed one has. `where` names the Editor in messages.
    Raises NxwrightError as firmware_from_editor_folder does."""
    files = {}
    for name in firmware_names(series):
        try:
            files[name] = (program.parent / name).read_bytes()
        except OSError as error:
            raise NxwrightError("%s's %s could not be read: %s"
                                % (where, name, error.strerror or error)) from None
    return Firmware(program_version(program)[:3], files)


def firmware_from_tft(data: bytes, where: str, series: str) -> Firmware:
    """Returns the firmware a TFT file of `series` holds, given its bytes.
    `where` names it in messages. Raises NxwrightError when it is of another
    series, and TftFileError when it cannot be read."""
    tft = read_tft(data, where)
    if tft.series != series:
        raise NxwrightError("%s is a TFT file of the %s series, whose firmware is not the %s "
                            "series'" % (where, tft.series, series))
    rows = {row.name: row for row in tft.table}
    return Firmware(tft.version, {name: tft.table_part(rows[name])
                                  for name in firmware_names(series)})


@dataclass(frozen=True)
class FoundFirmware:
    """What find_firmware found. `firmware` is the firmware, or None when no
    source served. `source` says where it came from, such as "the cache,
    C:\\...", or is "" when none served. `skipped` lists why each source tried
    did not serve."""
    firmware: Optional[Firmware]
    source: str
    skipped: tuple


def find_firmware(series: str, named_tft: Path = None, named_folder: Path = None,
                  asker: DownloadAsker = None) -> FoundFirmware:
    """Returns the firmware of `series` from the first source that serves,
    in the order this module's docstring gives: `named_tft`, a TFT file, or
    `named_folder`, a Nextion Editor folder; else the cache, then the
    installed Nextion Editor, then a download that `asker` lets the user
    allow. Without `asker`, nothing is downloaded.

    Raises NxwrightError when both `named_tft` and `named_folder` are given,
    when a named source cannot be read or comes from a version that is not
    matched, when a file of a matched version fails its hash, and when a
    download is declined, breaks off, or is refused
    (firmware_download.download_zip, install_editor). Raises OSError when
    `named_tft` cannot be read."""
    if named_tft is not None and named_folder is not None:
        raise NxwrightError("give a TFT file with --firmware or a Nextion Editor folder with "
                            "--editor, not both")
    if named_tft is not None:
        firmware = firmware_from_tft(named_tft.read_bytes(), str(named_tft), series)
        _refuse_another_version(firmware, "%s was made by the Nextion Editor" % named_tft)
        _refuse_a_failed_hash(firmware, str(named_tft))
        _write_cache(firmware.version, firmware.files)
        return FoundFirmware(firmware, "the TFT file %s" % named_tft, ())
    if named_folder is not None:
        firmware = firmware_from_editor_folder(named_folder, series, str(named_folder))
        _refuse_another_version(firmware, "the Nextion Editor in %s is" % named_folder)
        _refuse_a_failed_hash(firmware, str(named_folder))
        _cache_editor_folder(named_folder, firmware.version)
        return FoundFirmware(firmware, "the Nextion Editor folder %s" % named_folder, ())
    skipped = []
    found = _cached_firmware(series, skipped) or _usable_installed_firmware(series, skipped)
    if found is None and asker is not None:
        found = _downloaded_firmware(series, asker, skipped)
    if found is None:
        return FoundFirmware(None, "", tuple(skipped))
    return FoundFirmware(found[0], found[1], tuple(skipped))


def _downloaded_firmware(series: str, asker: DownloadAsker, skipped: list):
    """Returns the firmware of `series` from Nextion's site, and its source,
    or None, adding to `skipped` why. It tries, in turn:
      - the zip. Every series' files are written to the cache, so the next
        compile on another series needs no download;
      - when the zip does not answer, on Windows with no Nextion Editor
        installed, the installer. Once it has run, the installed Nextion
        Editor is tried again. The installer is never offered beside an
        installed Nextion Editor, which it could replace;
      - when neither serves, Nextion's download page, offered to open.
    Raises NxwrightError when a download is declined, breaks off, or is
    refused (firmware_download), and when the installer ran but no usable
    Nextion Editor is installed afterwards."""
    if not asker.can_ask():
        skipped.append("a download from Nextion needs your consent: run the compile at a "
                       "terminal, or give --download")
        return None
    offer = offer_of(max(firmware_versions.MATCHED_VERSIONS))
    files = download_zip(offer, asker, skipped)
    if files is not None:
        _write_cache(offer.version, files)
        return (Firmware(offer.version, {name: files[name] for name in firmware_names(series)}),
                "Nextion's site, %s" % offer.zip_address)
    if installed_editor_folder() is not None:
        skipped.append("the installer is not offered, as it could replace the installed Nextion "
                       "Editor")
    elif sys.platform == "win32" and install_editor(offer, asker, skipped):
        found = _usable_installed_firmware(series, skipped)
        if found is None:
            raise NxwrightError("the install of the Nextion Editor %s did not complete. Run the "
                                "compile again once it has." % version_text(offer.version))
        return found
    asker.offer_page(offer.page_address)
    return None


def hash_problem(files: dict, version: tuple):
    """Returns why `files`, firmware files by name, are not those of the
    matched `version`. Returns None when each file has its hash, and when
    `version` is not a matched one, as nxwright knows no hashes for it."""
    hashes = firmware_versions.MATCHED_VERSIONS.get(version)
    if hashes is None:
        return None
    for name, data in files.items():
        if hashlib.sha256(data).hexdigest() != hashes.get(name):
            return "its %s is not the Nextion Editor %s's" % (name, version_text(version))
    return None


def _matched_firmware_only() -> str:
    """Returns the end of each message that refuses or skips firmware of a
    version that is not matched. The text lists the versions nxwright takes,
    and the address of the newest one's installer. Nextion's download page
    links only to Nextion's newest Nextion Editor, which may not be one that
    nxwright takes, so the text includes the address."""
    newest = max(firmware_versions.MATCHED_VERSIONS)
    return ("nxwright takes only the firmware of the Nextion Editor %s. You can install the "
            "Nextion Editor %s from %s" % (matched_versions_text(), version_text(newest),
                                           offer_of(newest).installer_address))


def _refuse_another_version(firmware: Firmware, lead: str):
    """Raises NxwrightError when `firmware`, from a named source, comes from
    a version that is not matched. The message is `lead`, then the version,
    then the versions nxwright takes. `lead` identifies the source, such as
    "app.tft was made by the Nextion Editor"."""
    if firmware.version not in firmware_versions.MATCHED_VERSIONS:
        raise NxwrightError("%s %s, but %s"
                            % (lead, version_text(firmware.version), _matched_firmware_only()))


def _refuse_a_failed_hash(firmware: Firmware, where: str):
    """Raises NxwrightError when `firmware`, from the named source `where`,
    is of a matched version and a file fails its hash."""
    problem = hash_problem(firmware.files, firmware.version)
    if problem is not None:
        raise NxwrightError("%s: %s" % (where, problem))


def _usable_installed_firmware(series: str, skipped: list):
    """Returns the installed Nextion Editor's firmware of `series` and its
    source, or None. When it returns None, it adds to `skipped` why: no
    Nextion Editor is installed, a file cannot be read, the version is not
    a matched one, or a file fails its hash. Firmware it returns is written
    to the cache, with every other series' files."""
    folder = installed_editor_folder()
    if folder is None:
        skipped.append("no Nextion Editor is installed")
        return None
    try:
        firmware = firmware_from_editor_folder(folder, series, "the installed Nextion Editor")
    except NxwrightError as error:
        skipped.append(str(error))
        return None
    if firmware.version not in firmware_versions.MATCHED_VERSIONS:
        skipped.append("the installed Nextion Editor is %s, but %s"
                       % (version_text(firmware.version), _matched_firmware_only()))
        return None
    problem = hash_problem(firmware.files, firmware.version)
    if problem is not None:
        skipped.append("the installed Nextion Editor: %s" % problem)
        return None
    _cache_editor_folder(folder, firmware.version)
    return firmware, "the installed Nextion Editor, %s" % folder


def _cached_firmware(series: str, skipped: list):
    """Returns the cache's firmware of `series` and its source, newest
    matched version first, or None. When it returns None, it adds to
    `skipped` why. A version serves when all the series' files are there
    and each passes its hash."""
    for version in sorted(firmware_versions.MATCHED_VERSIONS, reverse=True):
        folder = _cache_folder_of(version)
        if folder is None:
            skipped.append("the cache is turned off (NXWRIGHT_CACHE)")
            return None
        try:
            files = {name: (folder / name).read_bytes() for name in firmware_names(series)}
        except OSError:
            skipped.append("the cache has no firmware of the Nextion Editor %s for this series"
                           % version_text(version))
            continue
        problem = hash_problem(files, version)
        if problem is not None:
            skipped.append("the cache's firmware of the Nextion Editor %s: %s"
                           % (version_text(version), problem))
            continue
        return Firmware(version, files), "the cache, %s" % folder
    return None


def _cache_editor_folder(folder: Path, version: tuple):
    """Writes to the cache each firmware file, of every series, that the
    Nextion Editor folder `folder` has and that passes its hash for
    `version`. A Nextion Editor folder has every series' files, so the next
    compile on another series finds them too."""
    files = {}
    for name in sorted({name for series in SERIES.values() for name in firmware_names(series)}):
        try:
            files[name] = (folder / name).read_bytes()
        except OSError:
            continue
    _write_cache(version, {name: data for name, data in files.items()
                           if hash_problem({name: data}, version) is None})


def _write_cache(version: tuple, files: dict):
    """Writes `files`, firmware files by name, to the cache's folder of
    `version`. Writes nothing when the cache is off, when `version` is not a
    matched one, or when a file fails its hash."""
    folder = _cache_folder_of(version)
    if (folder is None or version not in firmware_versions.MATCHED_VERSIONS
            or hash_problem(files, version) is not None):
        return
    # The cache only spares a later compile the search. If it cannot be
    # written, this compile goes on without it. A file left half written
    # fails its hash when it is read, so it is skipped then.
    try:
        folder.mkdir(parents=True, exist_ok=True)
        for name, data in files.items():
            (folder / name).write_bytes(data)
    except OSError:
        pass


def _cache_folder_of(version: tuple):
    """Returns the cache's folder of the firmware of `version`, or None when
    NXWRIGHT_CACHE turns the cache off."""
    base = cache_folder()
    return None if base is None else base / "firmware" / version_text(version)


def zero_firmware(firmware: Firmware) -> Firmware:
    """Returns firmware of the same version and sizes as `firmware`, all
    zeros, as tests package with in place of the vendor's."""
    return Firmware(firmware.version, {name: bytes(len(data))
                                       for name, data in firmware.files.items()})


def installed_editor_folder():
    """Returns the folder the Nextion Editor's installer recorded in the
    registry, the first one listed, or None, as on another system than
    Windows."""
    if sys.platform != "win32":
        return None
    import winreg
    for key_path in _UNINSTALL_KEYS:
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
                for index in range(winreg.QueryInfoKey(key)[0]):
                    # An entry that cannot be read is another program's.
                    try:
                        with winreg.OpenKey(key, winreg.EnumKey(key, index)) as entry:
                            if winreg.QueryValueEx(entry, "DisplayName")[0] != "Nextion Editor":
                                continue
                            folder = winreg.QueryValueEx(entry, "InstallLocation")[0]
                    except OSError:
                        continue
                    # An empty folder would be the current one.
                    if folder:
                        return Path(folder)
        except OSError:
            continue
    return None


class _FixedFileInfo(ctypes.Structure):
    """Windows' VS_FIXEDFILEINFO: a program's version, as numbers."""
    _fields_ = [(name, wintypes.DWORD) for name in (
        "dwSignature", "dwStrucVersion", "dwFileVersionMS", "dwFileVersionLS",
        "dwProductVersionMS", "dwProductVersionLS", "dwFileFlagsMask", "dwFileFlags",
        "dwFileOS", "dwFileType", "dwFileSubtype", "dwFileDateMS", "dwFileDateLS")]


def program_version(program: Path) -> tuple:
    """Returns the four numbers of `program`'s file version, from the
    program's version resource: as Windows reads it, on Windows, and with
    pefile elsewhere (_version_from_resource). Raises NxwrightError when it
    has none, or cannot be read."""
    if sys.platform != "win32":
        return _version_from_resource(program)
    version = ctypes.WinDLL("version", use_last_error=True)
    version.GetFileVersionInfoSizeW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
    version.GetFileVersionInfoW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                            ctypes.c_void_p]
    version.VerQueryValueW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR,
                                       ctypes.POINTER(ctypes.c_void_p),
                                       ctypes.POINTER(wintypes.UINT)]
    size = version.GetFileVersionInfoSizeW(str(program), None)
    buffer = ctypes.create_string_buffer(size)
    if not size or not version.GetFileVersionInfoW(str(program), 0, size, buffer):
        raise NxwrightError("%s has no version that could be read" % program)
    info, length = ctypes.c_void_p(), wintypes.UINT()
    if not version.VerQueryValueW(buffer, "\\", ctypes.byref(info), ctypes.byref(length)):
        raise NxwrightError("%s has no version that could be read" % program)
    fixed = ctypes.cast(info, ctypes.POINTER(_FixedFileInfo)).contents
    return (fixed.dwFileVersionMS >> 16, fixed.dwFileVersionMS & 0xFFFF,
            fixed.dwFileVersionLS >> 16, fixed.dwFileVersionLS & 0xFFFF)


def _version_from_resource(program: Path) -> tuple:
    """Returns the four numbers of `program`'s file version, read from its
    version resource with pefile, which works on any system. Raises
    NxwrightError when it has none, or cannot be read."""
    # Imported only here: the Editor tool's environment, which runs nxwright's
    # probes on Windows, reads versions through Windows and lacks pefile.
    try:
        import pefile
    except ImportError:
        raise NxwrightError("reading a Nextion Editor's version off Windows needs pefile, "
                            "which installing nxwright installs: python -m pip install "
                            "pefile") from None
    try:
        image = pefile.PE(str(program), fast_load=True)
    except (OSError, pefile.PEFormatError):
        raise NxwrightError("%s has no version that could be read" % program) from None
    try:
        image.parse_data_directories(
            directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_RESOURCE"]])
        fixed = image.VS_FIXEDFILEINFO[0]
    except (AttributeError, IndexError, pefile.PEFormatError):
        raise NxwrightError("%s has no version that could be read" % program) from None
    finally:
        image.close()
    return (fixed.FileVersionMS >> 16, fixed.FileVersionMS & 0xFFFF,
            fixed.FileVersionLS >> 16, fixed.FileVersionLS & 0xFFFF)
