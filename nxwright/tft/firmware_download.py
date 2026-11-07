"""Downloading the firmware from Nextion's site: the last source a compile
tries (firmware.find_firmware), when nothing on the computer serves.

Nextion offers each Nextion Editor version as an installer, and as a zip at
the same address with ".zip" in place of ".exe", such as
https://nextion.tech/download/nextion-setup-v1-68-2.zip. The zip is about
50 MB, and has every series' firmware files at its root
(ResearchNotes/tft/nextion-downloads.md).

The search uses this module in turn:
  1. offer_of returns the addresses of a matched version's zip and
     installer (firmware_versions.py). The search downloads the newest
     matched version, even when Nextion offers a newer one.
  2. download_zip asks for the zip's size, then for the user's consent,
     through the DownloadAsker its caller gives. It downloads the zip to a
     temporary file, takes every series' firmware files from the zip's root,
     and checks their hashes.
  3. When the zip does not answer, install_editor may offer the installer,
     on Windows, when no Nextion Editor is installed. It checks the
     installer against its hash, runs it, and waits until it exits.
Every downloaded file is deleted once its use is over, on every way out.

The rules for the network:
  - Every address, and every address a redirect leads to, must be HTTPS on
    nextion.tech.
  - A download must give its size, at most 200 MB, and stops if it grows
    past it. A firmware file over 16 MB unpacked refuses the zip.
  - curl makes every request, one address at a time, and never follows a
    redirect itself. This module checks each address before curl starts
    for it. curl sends its own User-Agent, such as curl/8.13.0, and nothing
    that identifies the computer or nxwright.tft. Python's own request is not
    used, as Nextion's server refuses its User-Agent.
  - On Windows, the curl that runs is Windows' own, in System32, which
    Windows has shipped since Windows 10 version 1803. Elsewhere, it is
    the curl on the PATH.
  - Nothing goes to the network unless a download could follow: the search
    calls this module only when the user can be asked, or allowed the
    download ahead of time (DownloadAsker.can_ask).
"""
from contextlib import contextmanager
import ctypes
from ctypes import wintypes
import hashlib
import http.client
import io
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import NamedTuple
import urllib.parse
import zipfile
import zlib

from nxwright import NxwrightError

from nxwright.tft import firmware_versions
from nxwright.tft.firmware_versions import version_text
from nxwright.tft.tft_file import SERIES, firmware_names

_HOST = "nextion.tech"
_INSTALLER_ADDRESS = "https://nextion.tech/download/nextion-setup-v%s.exe"
_DOWNLOAD_PAGE = "https://nextion.tech/nextion-editor/#_section1"
# How long a request may wait for Nextion's server, in seconds: to connect,
# and then each time the download stalls.
_TIMEOUT = 60
# As many redirects as Python's own request follows.
_MOST_REDIRECTS = 10
_REDIRECT_STATUSES = (301, 302, 303, 307, 308)
_MOST_DOWNLOAD = 200 * 1024 * 1024
_MOST_FIRMWARE_FILE = 16 * 1024 * 1024
# The size of each read of a download, which progress is reported after.
_CHUNK = 1024 * 1024


class DownloadAsker:
    """What a search for firmware asks its caller, so that it never reads
    the terminal or prints itself. A caller gives its own: the command line
    asks at the terminal (commands/compile.py). This one asks nothing, and
    allows nothing."""

    def can_ask(self) -> bool:
        """Whether the user can be asked, or allowed a download ahead of
        time. When neither, nothing goes to the network."""
        return False

    def can_ask_to_run(self) -> bool:
        """Whether the user can be asked about running a downloaded program,
        which no consent given ahead of time allows."""
        return False

    def allows_download(self, what: str, size: int, address: str, runs: bool = False) -> bool:
        """Whether the user allows the download of `what`, of `size` bytes,
        from `address`. When `runs`, `what` is a program that will run once
        downloaded, which only a question to the user may allow."""
        return False

    def report_progress(self, done: int, size: int):
        """Reports that `done` bytes of a download of `size` have come."""

    def offer_page(self, address: str):
        """Offers the user to open the web page at `address`."""


class Offer(NamedTuple):
    """The Nextion Editor version to download, and its addresses: its zip,
    its installer, and Nextion's download page."""
    version: tuple
    zip_address: str
    installer_address: str
    page_address: str


def offer_of(version: tuple) -> Offer:
    """Returns the addresses of the zip and the installer of the Nextion
    Editor `version`, a matched one, and of Nextion's download page."""
    installer = _INSTALLER_ADDRESS % version_text(version).replace(".", "-")
    return Offer(version, installer[:-len(".exe")] + ".zip", installer, _DOWNLOAD_PAGE)


def download_zip(offer: Offer, asker: DownloadAsker, skipped: list):
    """Returns every series' firmware files from `offer`'s zip, by name, or
    None when the zip does not answer, adding to `skipped` why. The files
    have passed their hashes.

    Raises NxwrightError when the user declines the download, the download
    breaks off, or the zip is refused: it gives no size, or one over 200 MB,
    or a firmware file is missing from its root, is over 16 MB unpacked, or
    fails its hash."""
    try:
        size = _size_of(offer.zip_address)
    except _NoAnswer as error:
        skipped.append("Nextion's site did not offer the zip of the Nextion Editor %s: %s"
                       % (version_text(offer.version), error))
        return None
    what = "the Nextion Editor %s, whose firmware the compile needs" % version_text(offer.version)
    if not asker.allows_download(what, size, offer.zip_address):
        raise NxwrightError("the download of the firmware from %s was declined"
                            % offer.zip_address)
    with _downloaded(offer.zip_address, size, asker, ".zip") as path:
        return _firmware_in_zip(path.read_bytes(), offer.version)


def install_editor(offer: Offer, asker: DownloadAsker, skipped: list) -> bool:
    """Offers to download and run `offer`'s installer, and returns whether it
    ran. The caller offers it only on Windows, when no Nextion Editor is
    installed. Returns False, adding to `skipped` why, when nxwright knows no
    hash for that installer, the user cannot be asked about running it, the
    installer does not answer, or the user declines it.

    Raises NxwrightError when the installer gives no size or one over
    200 MB, the download breaks off, the downloaded file cannot be opened
    and locked, or the installer fails its hash, in which case it is not
    run."""
    expected = firmware_versions.INSTALLER_HASHES.get(offer.version)
    name = "the installer of the Nextion Editor %s" % version_text(offer.version)
    if expected is None:
        skipped.append("nxwright knows no hash for %s, so it does not offer to run it" % name)
        return False
    if not asker.can_ask_to_run():
        skipped.append("running %s needs your consent at a terminal" % name)
        return False
    try:
        size = _size_of(offer.installer_address)
    except _NoAnswer as error:
        skipped.append("Nextion's site did not offer %s: %s" % (name, error))
        return False
    if not asker.allows_download(name, size, offer.installer_address, runs=True):
        skipped.append("you declined %s" % name)
        return False
    # The file is locked against changes from its check to its run, so that
    # no other program can replace it in between.
    with _downloaded(offer.installer_address, size, asker, ".exe") as path, \
            _locked_against_changes(path) as data:
        if hashlib.sha256(data).hexdigest() != expected:
            raise NxwrightError("the downloaded installer of the Nextion Editor %s is not the one "
                                "nxwright knows, so it was not run" % version_text(offer.version))
        # The installer's bytes, some 50 MB, are not needed while it runs.
        del data
        run_and_wait(path)
    return True


def run_and_wait(program: Path):
    """Runs `program` as an ordinary program, with its own windows, and
    waits until it exits. An installer asks for administrator rights, and
    Python's subprocess cannot start such a program (Windows refuses it,
    error 740). So it is started through Windows' ShellExecuteEx, which
    shows that request, and this waits on the process it returns. Raises
    NxwrightError when Windows cannot start it."""
    info = _ShellExecuteInfo()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = _SEE_MASK_NOCLOSEPROCESS
    info.lpVerb = "open"
    info.lpFile = str(program)
    info.nShow = _SW_SHOWNORMAL
    shell = ctypes.WinDLL("shell32", use_last_error=True)
    if not shell.ShellExecuteExW(ctypes.byref(info)):
        raise NxwrightError("%s could not be started: Windows error %d"
                            % (program.name, ctypes.get_last_error()))
    if not info.hProcess:
        return
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    try:
        kernel.WaitForSingleObject(info.hProcess, _INFINITE)
    finally:
        kernel.CloseHandle(info.hProcess)


@contextmanager
def _locked_against_changes(path: Path):
    """Opens `path`, on Windows, and keeps it open until the `with` block
    ends, so that no program can write it, replace it, or delete it until
    then. Yields the file's bytes. Other programs may still read it, as
    Windows does to run it. Raises NxwrightError when it cannot be
    opened."""
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                   ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD,
                                   wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    # Sharing reading alone denies every other program writing and deleting.
    handle = kernel.CreateFileW(str(path), _GENERIC_READ, _FILE_SHARE_READ, None,
                                _OPEN_EXISTING, _FILE_ATTRIBUTE_NORMAL, None)
    if handle in (None, _INVALID_HANDLE_VALUE):
        raise NxwrightError("%s could not be opened: Windows error %d"
                            % (path.name, ctypes.get_last_error()))
    # msvcrt exists on Windows alone, the one system the installer is
    # offered on. The file object owns the handle from here, and closes it.
    import msvcrt
    try:
        locked = os.fdopen(msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY), "rb")
    except OSError:
        kernel.CloseHandle(handle)
        raise
    with locked:
        yield locked.read()


_GENERIC_READ = 0x80000000
_FILE_SHARE_READ = 0x1
_OPEN_EXISTING = 3
_FILE_ATTRIBUTE_NORMAL = 0x80
_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
_SEE_MASK_NOCLOSEPROCESS = 0x40
_SW_SHOWNORMAL = 1
_INFINITE = 0xFFFFFFFF


class _ShellExecuteInfo(ctypes.Structure):
    """Windows' SHELLEXECUTEINFOW: what ShellExecuteEx starts, and how."""
    _fields_ = [("cbSize", wintypes.DWORD), ("fMask", wintypes.ULONG),
                ("hwnd", wintypes.HWND), ("lpVerb", wintypes.LPCWSTR),
                ("lpFile", wintypes.LPCWSTR), ("lpParameters", wintypes.LPCWSTR),
                ("lpDirectory", wintypes.LPCWSTR), ("nShow", ctypes.c_int),
                ("hInstApp", wintypes.HINSTANCE), ("lpIDList", ctypes.c_void_p),
                ("lpClass", wintypes.LPCWSTR), ("hkeyClass", wintypes.HKEY),
                ("dwHotKey", wintypes.DWORD), ("hIconOrMonitor", wintypes.HANDLE),
                ("hProcess", wintypes.HANDLE)]


def _size_of(address: str) -> int:
    """Returns the size of the download at `address`, from the headers of an
    answer that is closed before its body is read, as a server may refuse a
    request for the headers alone. Raises NxwrightError when it does not
    answer, gives no size, or is larger than 200 MB."""
    with _open(address) as response:
        return _stated_size(response, address)


@contextmanager
def _downloaded(address: str, size: int, asker: DownloadAsker, suffix: str):
    """Downloads `address`, of `size` bytes, to a temporary file, reporting
    progress to `asker`, and gives the file's path for the duration of the
    `with` block. The file is deleted afterwards, on every way out. Raises
    NxwrightError when the download breaks off, or grows past its size."""
    handle, temporary = tempfile.mkstemp(prefix="nxwright-firmware-", suffix=suffix)
    path = Path(temporary)
    try:
        try:
            _write_download(handle, address, size, asker)
        except (OSError, http.client.HTTPException) as error:
            raise NxwrightError("the download from %s broke off: %s"
                                % (address, error)) from None
        yield path
    finally:
        _delete_temporary(path)


def _write_download(handle: int, address: str, size: int, asker: DownloadAsker):
    """Writes the download at `address`, of `size` bytes, to the open file
    `handle`, and closes it. Raises NxwrightError when the download breaks
    off, grows past its size, or states another size than before."""
    done = 0
    with os.fdopen(handle, "wb") as written, _open(address) as response:
        if _stated_size(response, address) != size:
            raise NxwrightError("%s changed size during the download" % address)
        while True:
            chunk = response.read(_CHUNK)
            if not chunk:
                break
            done += len(chunk)
            if done > size:
                raise NxwrightError("%s grew past its size of %d bytes" % (address, size))
            written.write(chunk)
            asker.report_progress(done, size)
    if done != size:
        raise NxwrightError("the download from %s broke off after %d of %d bytes"
                            % (address, done, size))


def _firmware_in_zip(data: bytes, version: tuple) -> dict:
    """Returns every series' firmware files from the root of the zip
    `data`, by name. Raises NxwrightError when one is missing, is over
    16 MB unpacked, or fails its hash for `version`. Nothing in the zip is
    run, and no path from it is used to write a file."""
    names = sorted({name for series in SERIES.values() for name in firmware_names(series)})
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as error:
        raise NxwrightError("the downloaded zip could not be read: %s" % error) from None
    files = {}
    with archive:
        for name in names:
            try:
                info = archive.getinfo(name)
            except KeyError:
                raise NxwrightError("the downloaded zip has no %s at its root" % name) from None
            # The size the zip's list gives, before anything is unpacked.
            if info.file_size > _MOST_FIRMWARE_FILE:
                raise NxwrightError("the downloaded zip's %s is %d bytes, more than a firmware "
                                    "file has" % (name, info.file_size))
            # A damaged member fails its CRC, or its packed data, as it is read.
            try:
                files[name] = archive.read(info)
            except (zipfile.BadZipFile, zlib.error) as error:
                raise NxwrightError("the downloaded zip could not be read: %s" % error) from None
    hashes = firmware_versions.MATCHED_VERSIONS[version]
    for name, data in files.items():
        if hashlib.sha256(data).hexdigest() != hashes.get(name):
            raise NxwrightError("the downloaded zip's %s is not the Nextion Editor %s's"
                                % (name, version_text(version)))
    return files


def _delete_temporary(path: Path):
    """Deletes the downloaded file `path`, once it is checked to be a
    regular file in the temporary folder it was written to."""
    if path.parent == Path(tempfile.gettempdir()) and path.is_file() and not path.is_symlink():
        path.unlink()


def _stated_size(response, address: str) -> int:
    """Returns the size `response` gives in its Content-Length. Raises
    NxwrightError when it gives none, or one larger than 200 MB."""
    try:
        size = int(response.headers.get("Content-Length", ""))
    except ValueError:
        raise NxwrightError("%s does not give its size" % address) from None
    if size > _MOST_DOWNLOAD:
        raise NxwrightError("%s is %d bytes, more than a firmware download needs"
                            % (address, size))
    return size


def _is_allowed(address: str) -> bool:
    """Whether `address` is HTTPS on Nextion's host."""
    try:
        parts = urllib.parse.urlsplit(address)
        return parts.scheme == "https" and parts.hostname == _HOST
    except ValueError:
        return False


def _open(address: str):
    """Returns the answer to a GET request for `address`, made by curl, to
    be closed by its caller. A redirect is followed only to HTTPS on
    Nextion's host, up to 10 times. Raises NxwrightError when `address`, or
    an address it redirects to, is not HTTPS on Nextion's host. Raises
    _NoAnswer when curl is not found or cannot start, curl fails before the
    answer's headers, or the answer is neither a success nor a redirect."""
    if not _is_allowed(address):
        raise NxwrightError("%s is not HTTPS on %s" % (address, _HOST))
    curl = _curl()
    if curl is None:
        raise _NoAnswer("curl was not found, so nothing could be downloaded from %s" % address)
    asked = address
    for _ in range(_MOST_REDIRECTS + 1):
        try:
            process = _start_curl(_curl_command(curl, address))
        except OSError as error:
            raise _NoAnswer("curl could not be started: %s" % error) from None
        answer = _CurlAnswer(process, address)
        if answer.status == 200:
            return answer
        answer.close()
        if answer.status not in _REDIRECT_STATUSES:
            raise _NoAnswer("%s answered with the status %d" % (address, answer.status))
        location = answer.headers.get("Location")
        if not location:
            raise _NoAnswer("%s redirected without an address" % address)
        # A Location may be relative to the address that gave it.
        redirected = urllib.parse.urljoin(address, location)
        if not _is_allowed(redirected):
            raise NxwrightError("%s redirected to %s, which is not HTTPS on %s"
                                % (address, redirected, _HOST))
        address = redirected
    raise _NoAnswer("%s redirected more than %d times" % (asked, _MOST_REDIRECTS))


def _curl():
    """Returns the path of the curl to run, or None when there is none. On
    Windows, it is Windows' own alone. Windows' search of the PATH looks in
    the current folder first, so a curl.exe left in a project folder would
    otherwise run."""
    if sys.platform == "win32":
        system = os.environ.get("SystemRoot")
        if not system:
            return None
        path = Path(system) / "System32" / "curl.exe"
        return str(path) if path.is_file() else None
    return shutil.which("curl")


def _curl_command(curl: str, address: str) -> list:
    """Returns the command that has `curl` write the answer to a GET request
    for `address`: its status line and headers, then its body. curl
    follows no redirect, as the command has no -L, and sends its own
    User-Agent, as the command has no -A or -H."""
    return [curl,
            # First, so that curl reads no .curlrc, which could make it
            # follow redirects, or write the download elsewhere.
            "-q",
            "--silent", "--show-error",
            # The short form, which every curl has: newer ones call it
            # --show-headers, older ones --include.
            "-i",
            # A proxy's own answer is not written before the site's.
            "--suppress-connect-headers",
            # A second guard behind _is_allowed.
            "--proto", "=https",
            "--connect-timeout", str(_TIMEOUT),
            "--speed-limit", "1", "--speed-time", str(_TIMEOUT),
            "--output", "-", address]


def _start_curl(command: list):
    """Starts curl with `command`, with its output and its errors piped
    back, and no input. Returns the process."""
    return subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)


class _CurlAnswer:
    """The answer curl writes for `address`, read as it comes: its `status`,
    its `headers`, then its body, by read(size). Closing it before the body
    ends stops curl. Raises _NoAnswer when curl fails before the headers,
    or writes something that is not an answer."""

    def __init__(self, process, address: str):
        self._process = process
        self._address = address
        try:
            self.status, self.headers = self._read_head()
        except BaseException:
            self.close()
            raise

    def _read_head(self) -> tuple:
        while True:
            status_line = self._process.stdout.readline()
            if not status_line:
                raise _NoAnswer("%s did not answer: %s" % (self._address, self._error()))
            # Such as "HTTP/1.1 200 OK", or "HTTP/2 200", which has no reason.
            parts = status_line.split()
            try:
                if not parts[0].startswith(b"HTTP/"):
                    raise ValueError
                status = int(parts[1])
                headers = http.client.parse_headers(self._process.stdout)
            except (IndexError, ValueError, http.client.HTTPException):
                raise _NoAnswer("%s gave an answer that could not be read"
                                % self._address) from None
            # curl also writes the informational answers, of a status from
            # 100 to 199, such as 103 Early Hints, before the final one.
            if not 100 <= status < 200:
                return status, headers

    def _error(self) -> str:
        """Returns what curl wrote of its error, once it has exited."""
        code = self._process.wait()
        error = self._process.stderr.read().decode("utf-8", "replace").strip()
        return error or "curl exited with %d" % code

    def read(self, size: int) -> bytes:
        """Returns up to `size` bytes of the body, or no bytes once it has ended.
        Raises NxwrightError when curl failed before the end."""
        data = self._process.stdout.read(size)
        if not data and self._process.wait() != 0:
            raise NxwrightError("the download from %s broke off: %s"
                                % (self._address, self._error()))
        return data

    def close(self):
        if self._process.poll() is None:
            self._process.kill()
        self._process.wait()
        self._process.stdout.close()
        self._process.stderr.close()

    def __enter__(self):
        return self

    def __exit__(self, *exception):
        self.close()


class _NoAnswer(NxwrightError):
    """An address that did not answer, as against one that answered and was
    refused: only the first lets the search go on to another source."""
