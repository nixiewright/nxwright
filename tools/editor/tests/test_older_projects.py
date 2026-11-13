"""The parts of the older release script that do not need the Nextion Editor
(tools/editor/older_projects.py): the order of its projects, what it reads
from a project file, the project it writes in the manifest header form of
1.67.1, and its report."""
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from nxwright.project.byte_differences import ADDED, CHANGED, Difference
from nxwright.project.container import HmiContainer
from nxwright.project.device_settings import DeviceSettings
from nxwright.project.screen_models import model_named
from nxwright.project.stamp import with_manifest_stamp
from nxwright.source.project_files import build
from nxwright.source.source_folder import new_source_folder
from nxwright.source.unknown_content import MAY_BE_LOST, unknown_in_manifest_header
from tools.editor import older_projects


class RunOrderTest(unittest.TestCase):

    def test_the_series_an_older_release_may_lack_run_last(self):
        names = ["demo", "series-T", "series-E", "series-F", "series-P"]
        self.assertEqual(older_projects.in_run_order(names),
                         ["demo", "series-T", "series-P", "series-F", "series-E"])

    def test_a_missing_project_is_not_added(self):
        self.assertEqual(older_projects.in_run_order(["demo"]), ["demo"])


class ProjectFileTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.work = tempfile.TemporaryDirectory()
        folder = Path(cls.work.name)
        settings = DeviceSettings(model_named("NX4832T035"), 0, "iso-8859-1")
        new_source_folder(folder / "source", settings, "nextion", "probe")
        build(folder / "source", folder / "probe.HMI")
        cls.project = (folder / "probe.HMI").read_bytes()

    @classmethod
    def tearDownClass(cls):
        cls.work.cleanup()

    def test_the_headers_are_read_from_the_project(self):
        header = older_projects.manifest_header_of(self.project)
        self.assertEqual((len(header), header[9], header[36], header[65]), (96, 0x44, 2, 3))
        # The page header's current form ends with the encoding's number, 3
        # for iso-8859-1, and twelve zeros.
        self.assertEqual(older_projects.page_headers_of(self.project),
                         {"0.pa": bytes.fromhex("01440203") + bytes(12)})

    def test_the_copy_in_the_form_of_1_67_1_has_its_constants_and_a_fresh_stamp(self):
        older = older_projects.with_form_of_1_67_1(self.project)
        header = older_projects.manifest_header_of(older)
        self.assertEqual((header[9], header[36], header[65]), (0x43, 1, 2))
        # nxwright reads nothing in that header as content that may be lost.
        self.assertEqual([each for each in unknown_in_manifest_header(header)
                          if each.sort == MAY_BE_LOST], [])
        manifest = HmiContainer(older).blocks["main.HMI"]
        self.assertEqual(manifest, with_manifest_stamp(manifest, HmiContainer(
            self.project).blocks["main.HMI"]))
        # Every other block, and the file's size, stay as they were.
        before, after = HmiContainer(self.project).blocks, HmiContainer(older).blocks
        self.assertEqual({name: data for name, data in after.items() if name != "main.HMI"},
                         {name: data for name, data in before.items() if name != "main.HMI"})
        self.assertEqual(len(older), len(self.project))

    def test_the_constants_a_release_wrote_over_are_listed_by_place(self):
        given = bytearray(older_projects.manifest_header_of(
            older_projects.with_form_of_1_67_1(self.project)))
        saved = bytearray(given)
        saved[9], saved[65] = 0x3d, 0
        # A byte that is not one of the constants is left out.
        saved[12] = 3
        self.assertEqual(older_projects.written_over(bytes(given), bytes(saved)),
                         {9: (0x43, 0x3d), 65: (2, 0)})


class StandInRelease:
    """A stand-in for a release: its `save` copies the project it last
    opened, as it is, and its TFT file is that project's bytes. `stops`
    names a command that stops. It records its commands in `commands`."""

    def __init__(self, stops: str = None):
        self.stops = stops
        self.commands = []
        self.opened = None

    def step(self, *command) -> str:
        self.commands.append(command[0])
        if command[0] == self.stops:
            raise older_projects.Stopped("`editor.py %s` stopped" % command[0])
        if command[0] == "open":
            self.opened = Path(command[1])
        if command[0] == "save":
            Path(command[1]).write_bytes(self.opened.read_bytes())
        return "Compile Successful!" if command[0] == "compile" else ""

    def tft(self, project: Path, folder: Path) -> bytes:
        self.commands.append("tft")
        if self.stops == "tft":
            raise older_projects.Stopped("`editor.py tft` stopped")
        return HmiContainer.from_file(project).blocks["0.pa"]

    def close(self):
        self.commands.append("close")


class RunProjectTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.work = tempfile.TemporaryDirectory()
        settings = DeviceSettings(model_named("NX4832T035"), 0, "iso-8859-1")
        cls.source = Path(cls.work.name) / "source"
        new_source_folder(cls.source, settings, "nextion", "probe")

    @classmethod
    def tearDownClass(cls):
        cls.work.cleanup()

    def output(self) -> Path:
        return Path(tempfile.mkdtemp(dir=self.work.name)) / "project"

    def test_a_project_goes_through_every_step(self):
        release = StandInRelease()
        result = older_projects.run_project("series-K", self.source, release, self.output())
        self.assertEqual(release.commands,
                         ["open", "compile", "add-page", "save", "tft", "tft"])
        self.assertEqual(result.stopped, [])
        self.assertEqual(result.compiled, "Compile Successful!")
        self.assertEqual(result.manifest_header[9], 0x44)
        self.assertEqual(list(result.page_headers), ["0.pa"])
        # The stand-in saves what nxwright built, so the rebuild is the same.
        self.assertEqual((result.blocks, result.tft_same, result.repeats), ([], True, None))
        self.assertIsNone(result.written_over)

    def test_the_series_t_project_is_also_saved_in_the_form_of_1_67_1(self):
        release = StandInRelease()
        result = older_projects.run_project("series-T", self.source, release, self.output())
        self.assertEqual(release.commands[-2:], ["open", "save"])
        # The stand-in keeps every byte, so it wrote over none.
        self.assertEqual(result.written_over, {})

    def test_a_step_that_stops_is_recorded_and_the_editor_is_closed(self):
        release = StandInRelease(stops="add-page")
        result = older_projects.run_project("series-K", self.source, release, self.output())
        self.assertEqual(release.commands, ["open", "compile", "add-page", "close"])
        self.assertEqual(result.stopped, ["`editor.py add-page` stopped"])
        # What the steps before the stop showed is kept.
        self.assertEqual(result.compiled, "Compile Successful!")
        self.assertIsNone(result.manifest_header)


class EditorTool:
    """A stand-in for the Editor tool (release_pass.editor_tool). It records
    each command's first word in `commands`. `failing` gives, for a command,
    how many of its runs fail before one succeeds. `printed` gives what a
    command that succeeds prints."""

    def __init__(self, failing: dict = None, printed: dict = None):
        self.failing = dict(failing or {})
        self.printed = printed or {}
        self.commands = []

    def __call__(self, environment: dict, *command: str):
        name = command[0]
        self.commands.append(name)
        if self.failing.get(name, 0) > 0:
            self.failing[name] -= 1
            return SimpleNamespace(returncode=1, stdout="", stderr="%s failed" % name)
        return SimpleNamespace(returncode=0, stdout=self.printed.get(name, ""), stderr="")


class ReleaseTest(unittest.TestCase):

    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.written = self.folder / "probe.tft"
        self.written.write_bytes(b"the TFT file")

    def release(self, tool: EditorTool) -> older_projects.Release:
        patched = mock.patch.object(older_projects, "editor_tool", tool)
        patched.start()
        self.addCleanup(patched.stop)
        return older_projects.Release(Path("NextionEditor.exe"))

    def test_the_version_is_read_from_the_status_after_the_first_open(self):
        tool = EditorTool(printed={"status": "Running: older-release's Editor, as process 7, "
                                             "the Nextion Editor 1.61.2.2014 at C:/editor"})
        release = self.release(tool)
        self.assertEqual(release.version, "not started")
        release.step("open", "probe.HMI")
        release.step("open", "probe.HMI")
        self.assertEqual(release.version, "the Nextion Editor 1.61.2.2014")
        self.assertEqual(tool.commands, ["open", "status", "open"])

    def test_a_tft_file_is_read_from_where_the_tool_wrote_it(self):
        tool = EditorTool(printed={"tft": "Wrote %s\nCompile Successful!\n" % self.written})
        self.assertEqual(self.release(tool).tft(Path("probe.HMI"), self.folder / "tft"),
                         b"the TFT file")

    def test_a_stopped_tft_is_tried_once_more_in_a_fresh_editor(self):
        tool = EditorTool(failing={"tft": 1},
                          printed={"tft": "Wrote %s\n" % self.written})
        self.assertEqual(self.release(tool).tft(Path("probe.HMI"), self.folder / "tft"),
                         b"the TFT file")
        self.assertEqual(tool.commands,
                         ["open", "status", "tft", "close-simulator", "close-file-dialog",
                          "close-message", "quit", "open", "tft"])

    def test_a_tft_that_stops_twice_gives_both_stops(self):
        release = self.release(EditorTool(failing={"tft": 2}))
        with self.assertRaisesRegex(older_projects.Stopped,
                                    "tft failed; on the second try: .*tft failed"):
            release.tft(Path("probe.HMI"), self.folder / "tft")

    def test_closing_is_tried_again_until_the_editor_quits(self):
        tool = EditorTool(failing={"quit": 2})
        self.release(tool).close()
        self.assertEqual(tool.commands.count("quit"), 3)
        self.assertEqual(tool.commands.count("close-message"), 3)

    def test_an_editor_that_never_quits_stops_the_script(self):
        tool = EditorTool(failing={"quit": 5})
        with self.assertRaisesRegex(older_projects.Stopped, "did not close: quit failed"):
            self.release(tool).close()
        self.assertEqual(tool.commands.count("quit"), 3)


class ReportTest(unittest.TestCase):

    def test_a_changed_block_gives_its_places_and_another_its_kind(self):
        found = [Difference("0.pa", CHANGED, ((0, b"abcd", b"wxyz"), (41, b"\x3d", b"\x44"))),
                 Difference("2.ib", ADDED)]
        self.assertEqual(older_projects.block_lines(found),
                         ["0.pa: 5 bytes differ, at 0 to 3, 41", "2.ib: added"])

    def test_a_section_says_what_the_project_showed(self):
        result = older_projects.ProjectResult(
            "series-T", compiled="Compile Successful! 0 Errors\n",
            manifest_header=bytes(range(96)),
            page_headers={"0.pa": bytes.fromhex("01440203") + bytes(12),
                          "1.pa": bytes.fromhex("013d0200") + bytes(12)},
            notes=["a page header form nxwright has not seen"], blocks=[], tft_same=False,
            repeats=True, written_over={9: (0x43, 0x3d)})
        text = older_projects.section(result)
        for expected in ("## series-T", "Compile Successful! 0 Errors",
                         "00 01 02 03 04 05 06 07 08 09 0a 0b 0c 0d 0e 0f",
                         "- 1.pa: `01 3d 02 00 00 00 00 00 00 00 00 00 00 00 00 00`",
                         "- a page header form nxwright has not seen",
                         "differ from the saved project:\n\n- none",
                         "compile to different TFT files.",
                         "compiled the saved project twice, and got the same file both times.",
                         "- byte 9: 0x43 became 0x3d"):
            self.assertIn(expected, text)
        self.assertNotIn("Stopped", text)

    def test_a_project_that_stopped_at_once_has_only_its_stop(self):
        result = older_projects.ProjectResult("series-F", stopped=["`editor.py open` stopped"])
        self.assertEqual(older_projects.section(result),
                         "## series-F\n\nStopped:\n\n- `editor.py open` stopped\n")


if __name__ == "__main__":
    unittest.main()
