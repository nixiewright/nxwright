"""Downloading the firmware from Nextion's site (tft/firmware_download.py),
with a stand-in for Nextion's site in place of the network, and zips built
here from the made-up firmware of the stand-in (tests/tft/stand_in_firmware.py)."""
from contextlib import contextmanager
import hashlib
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

from nxwright import NxwrightError

from nxwright.tft import firmware, firmware_download, firmware_versions
from nxwright.tft.firmware import find_firmware
from nxwright.tft.firmware_download import DownloadAsker
from nxwright.tft.tft_file import firmware_names
from tests.tft.stand_in_firmware import made_firmware_files, stand_in_firmware, write_editor_folder

ZIP = "https://nextion.tech/download/nextion-setup-v1-68-2.zip"
# Nextion's update check, which answers with its newest version.
CHECK = "https://nextion.tech/ver/ver.php?state=0&dver=1.68.2"


def made_zip(files: dict = None) -> bytes:
    """Returns a zip of `files`, by name, at its root: by default every
    series' made-up firmware files, beside a program as the real zip has."""
    files = made_firmware_files() if files is None else files
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        archive.writestr("Nextion Editor.exe", b"a program")
        for name, content in files.items():
            archive.writestr(name, content)
    return data.getvalue()


class _Answer(io.BytesIO):
    """A stand-in for an answer of the network: its body and its headers."""

    def __init__(self, body: bytes, headers: dict):
        super().__init__(body)
        self.headers = headers


class StandInNextion:
    """A stand-in for Nextion's site. `pages` gives each address's body, and
    the size its Content-Length states, by default the body's own. Every
    request is recorded in `requests`."""

    def __init__(self, pages: dict):
        self.pages = pages
        self.requests = []

    def open(self, address: str):
        self.requests.append(address)
        if address not in self.pages:
            raise firmware_download._NoAnswer("%s did not answer: Not Found" % address)
        body, stated = self.pages[address]
        headers = {} if stated is None else {"Content-Length": str(stated)}
        return _Answer(body, headers)


class Asker(DownloadAsker):
    """An asker that can ask, and answers `allow` to each question."""

    def __init__(self, allow: bool = True):
        self.allow = allow
        self.questions = []
        self.progress = []

    def can_ask(self) -> bool:
        return True

    def can_ask_to_run(self) -> bool:
        return True

    def allows_download(self, what: str, size: int, address: str, runs: bool = False) -> bool:
        self.questions.append((what, size, address, runs))
        return self.allow

    def report_progress(self, done: int, size: int):
        self.progress.append((done, size))


class DownloadTest(unittest.TestCase):

    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.folder = Path(self._folder.name)
        self.cache = self.folder / "cache"
        self.searches = 0
        self.written = []
        real_mkstemp = tempfile.mkstemp

        def recorded_mkstemp(*arguments, **options):
            handle, path = real_mkstemp(*arguments, **options)
            self.written.append(Path(path))
            return handle, path
        patcher = mock.patch.object(firmware_download.tempfile, "mkstemp", recorded_mkstemp)
        patcher.start()
        self.addCleanup(patcher.stop)

    def tearDown(self):
        self._folder.cleanup()

    def site(self, zip_data: bytes = None, stated: int = None) -> dict:
        """Returns the pages of a site offering `zip_data`, by default the
        made-up firmware's zip, whose Content-Length is `stated`, by default
        its size."""
        zip_data = made_zip() if zip_data is None else zip_data
        return {ZIP: (zip_data, len(zip_data) if stated is None else stated)}

    def search(self, pages: dict, asker: DownloadAsker, series: str = "T"):
        """Runs find_firmware with nothing else serving, against `pages`;
        returns what it found, and the site's stand-in. Each search has a
        new, empty cache, `self.cache`, so that an earlier download does not
        serve it."""
        self.searches += 1
        self.cache = self.folder / ("cache-%d" % self.searches)
        site = StandInNextion(pages)
        with stand_in_firmware(self.cache), mock.patch.object(firmware_download, "_open",
                                                              site.open):
            return find_firmware(series, asker=asker), site

    def assert_no_temporary_left(self):
        self.assertTrue(self.written)
        for path in self.written:
            self.assertFalse(path.exists())

    def test_the_zip_serves_and_every_series_is_cached(self):
        asker = Asker()
        found, site = self.search(self.site(), asker)
        self.assertEqual(found.source, "Nextion's site, %s" % ZIP)
        self.assertEqual(found.firmware.version, (1, 68, 2))
        self.assertEqual(list(found.firmware.files), list(firmware_names("T")))
        self.assertEqual(asker.questions, [("the Nextion Editor 1.68.2, whose firmware the "
                                            "compile needs", len(made_zip()), ZIP, False)])
        self.assertEqual(asker.progress[-1], (len(made_zip()), len(made_zip())))
        for name in made_firmware_files():
            self.assertTrue((self.cache / "firmware" / "1.68.2" / name).is_file(), name)
        self.assertFalse((self.cache / "firmware" / "1.68.2" / "Nextion Editor.exe").exists())
        # The zip's size, from an answer closed after its headers, then the
        # download.
        self.assertEqual(site.requests, [ZIP, ZIP])
        self.assert_no_temporary_left()

    def test_the_matched_version_is_downloaded_whatever_is_newest(self):
        # The update check would answer with a later version, which nxwright
        # does not take, so the download does not use the check.
        pages = self.site()
        pages[CHECK] = (b"&*@ver=1.69.0&*@exeadd=http://nextion.tech/download/"
                        b"nextion-setup-v1-69-0.exe", None)
        found, site = self.search(pages, Asker())
        self.assertEqual(found.source, "Nextion's site, %s" % ZIP)
        self.assertNotIn(CHECK, site.requests)

    def test_nothing_goes_to_the_network_without_a_way_to_consent(self):
        found, site = self.search(self.site(), DownloadAsker())
        self.assertIsNone(found.firmware)
        self.assertEqual(site.requests, [])
        self.assertEqual(found.skipped[-1], "a download from Nextion needs your consent: run "
                                            "the compile at a terminal, or give --download")

    def test_only_another_release_s_firmware_gets_the_offer_of_none(self):
        # As for a user who updated nxwright after it moved to another release:
        # the old release's firmware, cached and installed, is skipped, and
        # the matched release's zip is offered as to a user with none. The
        # old release's cache is left as it is.
        old_cache = write_editor_folder(self.folder / "cache" / "firmware" / "1.67.0")
        editor = write_editor_folder(self.folder / "old")
        asker = Asker()
        site = StandInNextion(self.site())
        with stand_in_firmware(self.folder / "cache", installed=editor,
                               installed_version=(1, 67, 0)), \
                mock.patch.object(firmware_download, "_open", site.open):
            found = find_firmware("T", asker=asker)
        self.assertEqual(found.source, "Nextion's site, %s" % ZIP)
        self.assertEqual(asker.questions, [("the Nextion Editor 1.68.2, whose firmware the "
                                            "compile needs", len(made_zip()), ZIP, False)])
        self.assertIn("the installed Nextion Editor is 1.67.0, but nxwright takes only the firmware "
                      "of the Nextion Editor 1.68.2", " ".join(found.skipped))
        self.assertEqual(sorted(path.name for path in old_cache.iterdir()),
                         sorted(made_firmware_files()))

    def test_a_declined_download_stops_the_search(self):
        with self.assertRaisesRegex(NxwrightError, "the download of the firmware from %s was "
                                                   "declined" % ZIP):
            self.search(self.site(), Asker(allow=False))
        self.assertFalse(self.cache.exists())

    def test_a_zip_that_does_not_answer_is_skipped(self):
        pages = self.site()
        del pages[ZIP]
        found, _ = self.search(pages, Asker())
        self.assertIsNone(found.firmware)
        self.assertIn("Nextion's site did not offer the zip of the Nextion Editor 1.68.2: %s did "
                      "not answer: Not Found" % ZIP, found.skipped)

    def test_a_download_that_breaks_off_stops_the_search(self):
        data = made_zip()
        with self.assertRaisesRegex(NxwrightError, "broke off after %d of %d bytes"
                                                   % (len(data), len(data) + 10)):
            self.search(self.site(stated=len(data) + 10), Asker())
        self.assert_no_temporary_left()
        self.assertFalse(self.cache.exists())

    def test_a_download_that_grows_past_its_size_stops_the_search(self):
        with self.assertRaisesRegex(NxwrightError, "grew past its size of 10 bytes"):
            self.search(self.site(stated=10), Asker())
        self.assert_no_temporary_left()

    def test_a_size_missing_or_too_large_stops_the_search_before_the_download(self):
        # A zip that answers but is refused stops the search, and offers
        # nothing more: no question, and no installer.
        for stated, said in ((None, "does not give its size"),
                             (300 * 1024 * 1024, "more than a firmware download needs")):
            with self.subTest(stated=stated):
                pages = self.site()
                pages[ZIP] = (pages[ZIP][0], stated)
                asker = Asker()
                with self.assertRaisesRegex(NxwrightError, said):
                    self.search(pages, asker)
                self.assertEqual(asker.questions, [])
                self.assertEqual(self.written, [])

    def test_a_zip_missing_a_firmware_file_is_refused_and_not_cached(self):
        files = made_firmware_files()
        del files["cdx.dll"]
        with self.assertRaisesRegex(NxwrightError, "the downloaded zip has no cdx.dll at its "
                                                   "root"):
            self.search(self.site(made_zip(files)), Asker())
        self.assertFalse(self.cache.exists())
        self.assert_no_temporary_left()

    def test_a_zip_whose_file_fails_its_hash_is_refused_and_not_cached(self):
        files = made_firmware_files()
        files["asp0.dll"] = b"another file"
        with self.assertRaisesRegex(NxwrightError, "the downloaded zip's asp0.dll is not the "
                                                   "Nextion Editor 1.68.2's"):
            self.search(self.site(made_zip(files)), Asker())
        self.assertFalse(self.cache.exists())

    def test_a_damaged_zip_is_refused(self):
        # A zip whole in size, but whose member fails its check when read,
        # by its CRC or by its packed data.
        data = bytearray(made_zip())
        member = data.find(b"inputinputinput")
        self.assertGreater(member, 0)
        data[member] ^= 0xFF
        with self.assertRaisesRegex(NxwrightError, "the downloaded zip could not be read"):
            self.search(self.site(bytes(data)), Asker())
        self.assertFalse(self.cache.exists())
        self.assert_no_temporary_left()

    def test_a_file_too_large_in_the_zip_is_refused(self):
        files = made_firmware_files()
        files["3.cc"] = bytes(17 * 1024 * 1024)
        with self.assertRaisesRegex(NxwrightError, "the downloaded zip's 3.cc is %d bytes"
                                                   % (17 * 1024 * 1024)):
            self.search(self.site(made_zip(files)), Asker())


INSTALLER = "https://nextion.tech/download/nextion-setup-v1-68-2.exe"
PAGE = "https://nextion.tech/nextion-editor/#_section1"
INSTALLER_BYTES = b"a stand-in for the installer"


class InstallerAsker(Asker):
    """An asker that also records the pages it is offered."""

    def __init__(self, allow: bool = True):
        super().__init__(allow)
        self.pages = []

    def offer_page(self, address: str):
        self.pages.append(address)


@contextmanager
def stand_in_lock(path: Path):
    """Stands in for the installer's lock against changes, which needs
    Windows: yields the file's bytes, and locks nothing."""
    yield path.read_bytes()


class AheadAsker(InstallerAsker):
    """An asker that allows downloads ahead of time, but cannot ask about
    running a program, as --download without a terminal."""

    def can_ask_to_run(self) -> bool:
        return False


class InstallerTest(unittest.TestCase):
    """When the zip does not answer: the installer on Windows with no Nextion
    Editor installed, then Nextion's download page."""

    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.folder = Path(self._folder.name)
        self.installed = None
        self.ran = []

    def tearDown(self):
        self._folder.cleanup()

    def stand_in_run(self, program: Path):
        """Stands in for running the installer: records it, and installs a
        Nextion Editor of the made-up firmware."""
        self.ran.append(program.read_bytes())
        self.installed = write_editor_folder(self.folder / "editor")

    def search(self, asker: DownloadAsker, hashes: dict = None, platform: str = "win32",
               installer_answers: bool = True, run=None, installed_version: tuple = (1, 68, 2),
               real_lock: bool = False):
        """Runs find_firmware against a site without the zip, whose
        installer answers when `installer_answers`, and a Nextion Editor of
        `installed_version` when one is installed; returns what it found.
        The installer's lock against changes is a stand-in that reads the
        file, so that these tests run on any system, unless `real_lock`."""
        pages = {}
        if installer_answers:
            pages[INSTALLER] = (INSTALLER_BYTES, len(INSTALLER_BYTES))
        if hashes is None:
            hashes = {(1, 68, 2): hashlib.sha256(INSTALLER_BYTES).hexdigest()}
        site = StandInNextion(pages)
        self.requests = site.requests
        lock = firmware_download._locked_against_changes if real_lock else stand_in_lock
        with stand_in_firmware(self.folder / "cache", installed_version=installed_version), \
                mock.patch.object(firmware_download, "_locked_against_changes", lock), \
                mock.patch.object(firmware_download, "_open", site.open), \
                mock.patch.object(firmware_versions, "INSTALLER_HASHES", hashes), \
                mock.patch.object(firmware_download, "run_and_wait", run or self.stand_in_run), \
                mock.patch.object(firmware, "installed_editor_folder", lambda: self.installed), \
                mock.patch.object(sys, "platform", platform):
            return find_firmware("T", asker=asker)

    def test_the_installer_runs_then_the_installed_editor_serves(self):
        asker = InstallerAsker()
        found = self.search(asker)
        self.assertEqual(self.ran, [INSTALLER_BYTES])
        self.assertEqual(found.source, "the installed Nextion Editor, %s" % self.installed)
        self.assertEqual(asker.questions[-1], ("the installer of the Nextion Editor 1.68.2",
                                               len(INSTALLER_BYTES), INSTALLER, True))
        self.assertEqual(asker.pages, [])

    def test_an_installer_that_fails_its_hash_is_not_run(self):
        with self.assertRaisesRegex(NxwrightError, "the downloaded installer of the Nextion "
                                                   "Editor 1.68.2 is not the one nxwright knows"):
            self.search(InstallerAsker(), hashes={(1, 68, 2): "0" * 64})
        self.assertEqual(self.ran, [])

    def test_an_install_that_does_not_complete_stops_the_search(self):
        with self.assertRaisesRegex(NxwrightError, "the install of the Nextion Editor 1.68.2 did "
                                                   "not complete. Run the compile again once it "
                                                   "has."):
            self.search(InstallerAsker(), run=lambda program: None)

    def test_the_page_is_offered_when_the_installer_does_not_serve(self):
        cases = {"declined": dict(asker=InstallerAsker(allow=False)),
                 "no hash known": dict(asker=InstallerAsker(), hashes={}),
                 "not on Windows": dict(asker=InstallerAsker(), platform="linux"),
                 "no installer": dict(asker=InstallerAsker(), installer_answers=False)}
        for name, case in cases.items():
            with self.subTest(name):
                found = self.search(**case)
                self.assertIsNone(found.firmware)
                self.assertEqual(case["asker"].pages, [PAGE])
                self.assertEqual(self.ran, [])

    @unittest.skipIf(sys.platform != "win32", "the installer is locked on Windows alone")
    def test_the_installer_is_run_while_locked(self):
        locked = []

        def stand_in_run(program: Path):
            with self.assertRaises(PermissionError):
                open(program, "r+b").close()
            locked.append(program)
            self.stand_in_run(program)
        found = self.search(InstallerAsker(), run=stand_in_run, real_lock=True)
        self.assertEqual(len(locked), 1)
        self.assertTrue(found.source.startswith("the installed Nextion Editor, "))

    def test_the_installer_is_not_asked_for_when_nobody_can_be_asked(self):
        # As with --download and no terminal: the zip may be downloaded, but
        # running a program needs a question, so the installer is not even
        # requested.
        asker = AheadAsker()
        found = self.search(asker)
        self.assertIsNone(found.firmware)
        self.assertNotIn(INSTALLER, self.requests)
        self.assertIn("running the installer of the Nextion Editor 1.68.2 needs your consent "
                      "at a terminal", found.skipped)

    def test_the_installer_is_not_offered_beside_an_installed_editor(self):
        # An installed Nextion Editor older than nxwright takes, which the
        # installer could replace.
        self.installed = write_editor_folder(self.folder / "old")
        asker = InstallerAsker()
        found = self.search(asker, installed_version=(1, 67, 0))
        self.assertIsNone(found.firmware)
        self.assertIn("the installer is not offered, as it could replace the installed Nextion "
                      "Editor", found.skipped)
        self.assertEqual(asker.pages, [PAGE])
        self.assertNotIn(INSTALLER, [question[2] for question in asker.questions])


@unittest.skipIf(sys.platform != "win32", "the installer is offered on Windows alone")
class LockedInstallerTest(unittest.TestCase):
    """The installer is locked against changes from its hash check to its
    run, so that no other program can replace it in between."""

    def test_a_locked_file_cannot_be_written_or_deleted_but_can_be_read(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "installer.exe"
            path.write_bytes(INSTALLER_BYTES)
            with firmware_download._locked_against_changes(path) as data:
                self.assertEqual(data, INSTALLER_BYTES)
                with self.assertRaises(PermissionError):
                    open(path, "r+b").close()
                with self.assertRaises(PermissionError):
                    path.unlink()
                self.assertEqual(path.read_bytes(), INSTALLER_BYTES)
            path.write_bytes(b"writable again")



def curl_output(status_line: str, headers: dict = None, body: bytes = b"") -> bytes:
    """Returns what curl writes for an answer: its status line, its
    headers, a blank line, then its body."""
    lines = [status_line] + ["%s: %s" % header for header in (headers or {}).items()]
    return ("\r\n".join(lines) + "\r\n\r\n").encode("ascii") + body


class StandInCurl:
    """A stand-in for a running curl, which writes `output`, then exits
    with `code`, having written `error`. It runs until it is waited on, or
    killed."""

    def __init__(self, output: bytes, error: bytes = b"", code: int = 0):
        self.stdout = io.BytesIO(output)
        self.stderr = io.BytesIO(error)
        self.code = code
        self.returncode = None
        self.killed = False

    def poll(self):
        return self.returncode

    def kill(self):
        self.killed = True
        self.returncode = 1

    def wait(self):
        if self.returncode is None:
            self.returncode = self.code
        return self.returncode


class StandInCurlSite:
    """Stands in for starting curl: each command's last argument, its
    address, gives the StandInCurl's arguments in `answers`. Every command,
    and every StandInCurl, is recorded."""

    def __init__(self, answers: dict):
        self.answers = answers
        self.commands = []
        self.started = []

    def start(self, command: list):
        self.commands.append(command)
        process = StandInCurl(*self.answers[command[-1]])
        self.started.append(process)
        return process

    def addresses(self) -> list:
        return [command[-1] for command in self.commands]


@contextmanager
def stand_in_curl(answers: dict):
    """While it lasts, curl is found, and each start of it is a StandInCurl
    given by `answers` (StandInCurlSite). Yields the site."""
    site = StandInCurlSite(answers)
    with mock.patch.object(firmware_download, "_curl", lambda: "curl"), \
            mock.patch.object(firmware_download, "_start_curl", site.start):
        yield site


def redirect(location: str) -> tuple:
    """Returns the arguments of a StandInCurl that answers a redirect to
    `location`."""
    return (curl_output("HTTP/1.1 302 Found", {"Location": location, "Content-Length": "0"}),)


class AddressTest(unittest.TestCase):
    """Every address, redirects included, must be HTTPS on nextion.tech, and
    curl fetches each one."""

    def test_an_address_off_nextion_or_not_https_is_refused_before_curl_starts(self):
        for address in ("http://nextion.tech/download/a.zip", "https://example.com/a.zip",
                        "https://nextion.tech.example.com/a.zip", "ftp://nextion.tech/a.zip"):
            with self.subTest(address=address):
                with stand_in_curl({}) as site:
                    with self.assertRaisesRegex(NxwrightError, "is not HTTPS on nextion.tech"):
                        firmware_download._open(address)
                self.assertEqual(site.commands, [])

    def test_a_redirect_off_nextion_or_off_https_is_refused(self):
        for location in ("http://nextion.tech/a.zip", "https://example.com/a.zip"):
            with self.subTest(location=location):
                with stand_in_curl({ZIP: redirect(location)}) as site:
                    with self.assertRaises(NxwrightError) as raised:
                        firmware_download._open(ZIP)
                self.assertEqual(str(raised.exception), "%s redirected to %s, which is not HTTPS "
                                                        "on nextion.tech" % (ZIP, location))
                # Refused, as against not answering, so the search stops.
                self.assertNotIsInstance(raised.exception, firmware_download._NoAnswer)
                self.assertEqual(site.addresses(), [ZIP])

    def test_a_redirect_on_nextion_is_followed(self):
        second = "https://nextion.tech/download/b.zip"
        third = "https://nextion.tech/download/c.zip"
        answers = {ZIP: redirect("/download/b.zip"), second: redirect(third),
                   third: (curl_output("HTTP/1.1 200 OK", {"Content-Length": "4"}, b"body"),)}
        with stand_in_curl(answers) as site:
            with firmware_download._open(ZIP) as answer:
                self.assertEqual(answer.read(10), b"body")
        self.assertEqual(site.addresses(), [ZIP, second, third])

    def test_more_than_10_redirects_do_not_answer(self):
        second = "https://nextion.tech/download/b.zip"
        with stand_in_curl({ZIP: redirect(second), second: redirect(second)}) as site:
            with self.assertRaisesRegex(firmware_download._NoAnswer,
                                        "^%s redirected more than 10 times" % ZIP):
                firmware_download._open(ZIP)
        self.assertEqual(len(site.commands), 11)

    def test_a_redirect_without_a_location_does_not_answer(self):
        answers = {ZIP: (curl_output("HTTP/1.1 302 Found", {"Content-Length": "0"}),)}
        with stand_in_curl(answers):
            with self.assertRaisesRegex(firmware_download._NoAnswer,
                                        "redirected without an address"):
                firmware_download._open(ZIP)

    def test_curl_s_command(self):
        answers = {ZIP: (curl_output("HTTP/1.1 200 OK", {"Content-Length": "0"}),)}
        with stand_in_curl(answers) as site:
            firmware_download._open(ZIP).close()
        command = site.commands[0]
        self.assertEqual(command[:2], ["curl", "-q"])
        self.assertEqual(command[-1], ZIP)
        self.assertIn("-i", command)
        self.assertEqual(command[command.index("--proto") + 1], "=https")
        self.assertEqual(command[command.index("--output") + 1], "-")
        # curl never follows a redirect itself, and sends its own User-Agent.
        for option in ("-L", "--location", "-A", "--user-agent", "-H", "--header"):
            self.assertNotIn(option, command)


class CurlAnswerTest(unittest.TestCase):
    """curl's output read as an answer: its status line, its headers, and its
    body, and curl's errors."""

    def test_the_headers_and_the_body_are_read_as_curl_writes_them(self):
        for status_line in ("HTTP/1.1 200 OK", "HTTP/2 200"):
            with self.subTest(status_line):
                output = curl_output(status_line, {"content-length": "4"}, b"body")
                with stand_in_curl({ZIP: (output,)}):
                    with firmware_download._open(ZIP) as answer:
                        self.assertEqual(answer.headers.get("Content-Length"), "4")
                        self.assertEqual(answer.read(2), b"bo")
                        self.assertEqual(answer.read(10), b"dy")
                        self.assertEqual(answer.read(10), b"")

    def test_informational_answers_before_the_final_one_are_skipped(self):
        output = (curl_output("HTTP/2 103", {"link": "</a.css>; rel=preload"})
                  + curl_output("HTTP/2 200", {"content-length": "4"}, b"body"))
        with stand_in_curl({ZIP: (output,)}):
            with firmware_download._open(ZIP) as answer:
                self.assertEqual(answer.headers.get("Content-Length"), "4")
                self.assertEqual(answer.read(10), b"body")

    def test_a_status_of_404_does_not_answer(self):
        answers = {ZIP: (curl_output("HTTP/1.1 404 Not Found", {"Content-Length": "0"}),)}
        with stand_in_curl(answers):
            with self.assertRaisesRegex(firmware_download._NoAnswer, "status 404"):
                firmware_download._open(ZIP)

    def test_curl_failing_before_its_headers_does_not_answer(self):
        error = b"curl: (6) Could not resolve host: nextion.tech\n"
        with stand_in_curl({ZIP: (b"", error, 6)}):
            with self.assertRaisesRegex(firmware_download._NoAnswer,
                                        r"curl: \(6\) Could not resolve host: nextion.tech$"):
                firmware_download._open(ZIP)

    def test_curl_failing_in_the_body_breaks_the_download_off(self):
        output = curl_output("HTTP/1.1 200 OK", {"Content-Length": "10"}, b"part")
        error = b"curl: (56) Recv failure: Connection was reset\n"
        with stand_in_curl({ZIP: (output, error, 56)}):
            with self.assertRaises(NxwrightError) as raised:
                with firmware_download._downloaded(ZIP, 10, Asker(), ".zip"):
                    pass
        self.assertEqual(str(raised.exception), "the download from %s broke off: curl: (56) Recv "
                                                "failure: Connection was reset" % ZIP)
        self.assertNotIsInstance(raised.exception, firmware_download._NoAnswer)

    def test_closing_the_answer_before_its_body_ends_stops_curl(self):
        output = curl_output("HTTP/1.1 200 OK", {"Content-Length": "4"}, b"body")
        with stand_in_curl({ZIP: (output,)}) as site:
            with firmware_download._open(ZIP) as answer:
                answer.read(2)
        self.assertTrue(site.started[0].killed)
        # Once the body has ended, curl has exited, and is not stopped.
        with stand_in_curl({ZIP: (output,)}) as site:
            with firmware_download._open(ZIP) as answer:
                answer.read(10)
                answer.read(10)
        self.assertFalse(site.started[0].killed)

    def test_curl_not_found_does_not_answer_and_the_page_is_offered(self):
        with mock.patch.object(firmware_download, "_curl", lambda: None):
            with self.assertRaisesRegex(firmware_download._NoAnswer, "curl was not found"):
                firmware_download._open(ZIP)
        asker = InstallerAsker()
        with tempfile.TemporaryDirectory() as folder, stand_in_firmware(Path(folder)), \
                mock.patch.object(firmware_download, "_curl", lambda: None), \
                mock.patch.object(sys, "platform", "linux"):
            found = find_firmware("T", asker=asker)
        self.assertIsNone(found.firmware)
        self.assertEqual(asker.pages, [PAGE])
        self.assertTrue(any("curl was not found" in reason for reason in found.skipped))

    def test_curl_that_cannot_start_does_not_answer(self):
        def start(command):
            raise PermissionError("Access is denied")
        with mock.patch.object(firmware_download, "_curl", lambda: "curl"), \
                mock.patch.object(firmware_download, "_start_curl", start):
            with self.assertRaisesRegex(firmware_download._NoAnswer,
                                        "curl could not be started: Access is denied"):
                firmware_download._open(ZIP)


class FindCurlTest(unittest.TestCase):
    """Which curl runs: on Windows, Windows' own alone."""

    def test_on_windows_only_windows_own_curl_is_taken(self):
        with tempfile.TemporaryDirectory() as folder:
            system = Path(folder) / "System32"
            with mock.patch.object(sys, "platform", "win32"), \
                    mock.patch.dict(os.environ, {"SystemRoot": folder}), \
                    mock.patch.object(firmware_download.shutil, "which",
                                      lambda name: r"C:\project\curl.exe"):
                self.assertIsNone(firmware_download._curl())
                system.mkdir()
                (system / "curl.exe").write_bytes(b"a stand-in for curl")
                self.assertEqual(firmware_download._curl(), str(system / "curl.exe"))

    def test_elsewhere_the_curl_on_the_path_is_taken(self):
        found = []

        def which(name):
            found.append(name)
            return "/usr/bin/curl"
        with mock.patch.object(sys, "platform", "linux"), \
                mock.patch.object(firmware_download.shutil, "which", which):
            self.assertEqual(firmware_download._curl(), "/usr/bin/curl")
        self.assertEqual(found, ["curl"])


if __name__ == "__main__":
    unittest.main()
