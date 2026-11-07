"""The whole compile (tft/commands/compile.py): its fixtures, kept by the
probes of compile_probes.py once they matched the Nextion Editor's files,
and the compile command writing a whole file, with firmware of the tests'
own."""
from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

from nxwright import NxwrightError

from nxwright.tft import frame
from nxwright.tft.commands import compile as compile_command
from nxwright.tft.packaging import Firmware
from tools.tft.probing import compile_probes, probe_runner
from tools.tft.probing.component_probes import with_components
from tools.tft.probing.text_probes import text_component
from nxwright.cli import main
from nxwright.tft.tft_file import firmware_names, read_tft
from tests.tft.made_tft import made_tft, zeros_of_the_table
from tests.tft.stand_in_firmware import stand_in_firmware, write_editor_folder
from tests.tft.whole_builds import built_project

FIXTURES = Path(__file__).resolve().parent / "fixtures" / compile_probes.FIXTURES
# Where Nextion offers the installer of the Nextion Editor 1.68.2.
INSTALLER = "https://nextion.tech/download/nextion-setup-v1-68-2.exe"


class FixtureTest(unittest.TestCase):
    """The whole compile still writes what the probes checked."""

    def test_each_probe_s_fixtures(self):
        probes = [probe for probe in compile_probes.PROBES if probe.fixtures]
        self.assertTrue(probes)
        for probe in probes:
            with self.subTest(probe.name):
                folder = FIXTURES / probe.name
                kept = {file.stem: file.read_bytes() for file in folder.glob("*.bin")}
                project = built_project(probe.base, probe.change)
                firmware = zeros_of_the_table(kept["table"], probe.base)
                self.assertEqual(compile_probes.fixture_pieces(project, firmware), kept)


class CommandTest(unittest.TestCase):

    def test_a_blank_project_is_written_whole(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            source = folder / "app"
            shutil.copytree(probe_runner.BASES / "T", source)
            firmware = folder / "firmware.tft"
            firmware.write_bytes(made_tft("T"))
            output = folder / "app.tft"
            printed = io.StringIO()
            with stand_in_firmware(folder / "cache"), redirect_stdout(printed), \
                    redirect_stderr(io.StringIO()):
                code = main(["compile", str(source), str(output), "--firmware", str(firmware)])
            self.assertEqual((code, printed.getvalue()),
                             (0, "Took the firmware from the TFT file %s\nWrote %s\n"
                              % (firmware, output)))
            tft = read_tft(output.read_bytes(), "app.tft")
            project = built_project("T")
            self.assertEqual(tft.user_code, frame.user_code(project))
            # The firmware is the one --firmware named.
            self.assertEqual(tft.table_part(tft.table[0]), b"input" * 3)

    def compile(self, folder: Path, *options: str) -> tuple:
        """Compiles the T base folder in `folder` with `options`, with the
        stand-in firmware and a cache in `folder`. Returns the exit code, and
        what the compile printed and wrote as errors."""
        source = folder / "app"
        shutil.copytree(probe_runner.BASES / "T", source)
        printed, said = io.StringIO(), io.StringIO()
        with stand_in_firmware(folder / "cache"), redirect_stdout(printed), \
                redirect_stderr(said):
            code = main(["compile", str(source), str(folder / "app.tft")] + list(options))
        return code, printed.getvalue(), said.getvalue()

    def test_a_later_version_is_refused(self):
        # A later version's firmware may number its commands differently.
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            firmware = folder / "firmware.tft"
            firmware.write_bytes(made_tft("T", version=(1, 69, 0)))
            code, _, said = self.compile(folder, "--firmware", str(firmware))
            self.assertEqual(code, 1)
            self.assertEqual(said, "nxwright compile: %s was made by the Nextion Editor 1.69.0, "
                                   "but nxwright takes only the firmware of the Nextion Editor "
                                   "1.68.2. You can install the Nextion Editor 1.68.2 from %s\n"
                                   % (firmware, INSTALLER))
            self.assertFalse((folder / "app.tft").exists())

    def test_a_named_editor_folder(self):
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            editor = write_editor_folder(folder / "editor")
            code, printed, _ = self.compile(folder, "--editor", str(editor))
            self.assertEqual(code, 0)
            self.assertTrue(printed.startswith("Took the firmware from the Nextion Editor folder "
                                               "%s\n" % editor))

    def test_no_firmware_lists_each_source_tried(self):
        with tempfile.TemporaryDirectory() as folder:
            code, _, said = self.compile(Path(folder))
            self.assertEqual(code, 1)
            self.assertEqual(said, "nxwright compile: no firmware was found:\n"
                                   "- the cache has no firmware of the Nextion Editor 1.68.2 for "
                                   "this series\n"
                                   "- no Nextion Editor is installed\n"
                                   "- a download from Nextion needs your consent: run the "
                                   "compile at a terminal, or give --download\n"
                                   "Install the Nextion Editor 1.68.2 from %s, or give a TFT "
                                   "file it wrote with --firmware.\n" % INSTALLER)

    def test_a_tft_file_and_a_folder_together_are_refused(self):
        # argparse refuses them, and exits as it does for any wrong option.
        said = io.StringIO()
        with redirect_stderr(said), self.assertRaises(SystemExit) as exited:
            main(["compile", "app", "app.tft", "--firmware", "a.tft", "--editor", "editor"])
        self.assertEqual(exited.exception.code, 2)
        self.assertIn("argument --editor: not allowed with argument --firmware", said.getvalue())

    def test_the_terminal_asker_without_a_terminal(self):
        # It allows a download only when --download allowed it, never a
        # program's that would then run, and offers no page.
        with mock.patch.object(compile_command.sys.stdin, "isatty", lambda: False), \
                mock.patch("builtins.input") as typed, \
                mock.patch.object(compile_command.webbrowser, "open") as opened:
            for allowed in (False, True):
                asker = compile_command.TerminalAsker(allowed)
                self.assertEqual(asker.can_ask(), allowed)
                self.assertFalse(asker.can_ask_to_run())
                self.assertEqual(asker.allows_download("a zip", 10, "https://nextion.tech/a"),
                                 allowed)
                self.assertFalse(asker.allows_download("an installer", 10,
                                                       "https://nextion.tech/b", runs=True))
                asker.offer_page("https://nextion.tech/")
        typed.assert_not_called()
        opened.assert_not_called()

    def test_the_terminal_asker_at_a_terminal(self):
        with mock.patch.object(compile_command.sys.stdin, "isatty", lambda: True), \
                mock.patch.object(compile_command.sys.stdout, "isatty", lambda: True), \
                mock.patch("builtins.input", side_effect=["y", "", "yes", "y"]) as typed, \
                mock.patch.object(compile_command.webbrowser, "open") as opened:
            asker = compile_command.TerminalAsker(False)
            self.assertTrue(asker.allows_download("a zip", 50_000_000, "https://nextion.tech/a"))
            self.assertFalse(asker.allows_download("an installer", 1, "https://nextion.tech/b",
                                                   runs=True))
            # --download allows a zip without asking, but a program that
            # will then run still needs the prompt.
            allowed = compile_command.TerminalAsker(True)
            self.assertTrue(allowed.allows_download("a zip", 1, "https://nextion.tech/a"))
            self.assertTrue(allowed.allows_download("an installer", 1, "https://nextion.tech/b",
                                                    runs=True))
            asker.offer_page("https://nextion.tech/")
        self.assertEqual([call.args[0] for call in typed.call_args_list[:3]], [
            "Download a zip, 50.0 MB, from https://nextion.tech/a? [y/N] ",
            "Download and run an installer, 0.0 MB, from https://nextion.tech/b? [y/N] ",
            "Download and run an installer, 0.0 MB, from https://nextion.tech/b? [y/N] "])
        self.assertEqual(typed.call_count, 4)
        opened.assert_called_once_with("https://nextion.tech/")

    def test_the_end_of_the_terminal_s_input_answers_no(self):
        # As when the user presses Ctrl-D, or Ctrl-Z then Enter on Windows,
        # at the question.
        with mock.patch.object(compile_command.sys.stdin, "isatty", lambda: True), \
                mock.patch.object(compile_command.sys.stdout, "isatty", lambda: True), \
                mock.patch("builtins.input", side_effect=EOFError):
            asker = compile_command.TerminalAsker(False)
            self.assertFalse(asker.allows_download("a zip", 1, "https://nextion.tech/a"))

    def test_an_ffmpeg_that_is_no_program_is_refused(self):
        # As nxwright's commands refuse one (ffmpeg.find_ffmpeg).
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            source = folder / "app"
            shutil.copytree(probe_runner.BASES / "T", source)
            firmware = folder / "firmware.tft"
            firmware.write_bytes(made_tft("T"))
            output = folder / "app.tft"
            said = io.StringIO()
            with stand_in_firmware(folder / "cache"), redirect_stdout(io.StringIO()), \
                    redirect_stderr(said):
                code = main(["compile", str(source), str(output), "--firmware", str(firmware),
                             "--ffmpeg", str(folder / "none.exe")])
            self.assertEqual(code, 1)
            self.assertIn("none.exe is not a program", said.getvalue())
            self.assertFalse(output.exists())


class AnyReleaseTest(unittest.TestCase):
    """compile_project refuses firmware of a release nxwright has not matched.
    The probes, which compare nxwright's file with the file of that release's
    Nextion Editor, take it with any_release."""

    def test_firmware_of_a_release_not_matched(self):
        project = built_project("T")
        later = Firmware((1, 69, 1), {name: bytes(16) for name in firmware_names("T")})
        with self.assertRaisesRegex(NxwrightError, r"firmware 1\.69\.1"):
            compile_command.compile_project(project, later)
        data = compile_command.compile_project(project, later, any_release=True)
        self.assertEqual(read_tft(data, "nxwright's file", check=False).version, (1, 69, 1))


class DisupTest(unittest.TestCase):
    """disup, an attribute of the Nextion Editors 1.60.1 and 1.63.3, which
    1.68.2 does not have: it writes the same file with or without one."""

    def test_the_compile_leaves_disup_out(self):
        for series in ("T", "P"):
            with self.subTest(series):
                with_disup = built_project(series, with_components(text_component(drag=1,
                                                                                  disup=1)))
                without = built_project(series, with_components(text_component(drag=1)))
                self.assertEqual(frame.user_code(with_disup), frame.user_code(without))

    def compile_text(self, disup: int) -> tuple:
        """Compiles the T base folder with a dragged text of `disup`, and
        returns the exit code and what the compile wrote as errors."""
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            source = folder / "app"
            shutil.copytree(probe_runner.BASES / "T", source)
            with_components(text_component(drag=1, disup=disup))(source)
            firmware = folder / "firmware.tft"
            firmware.write_bytes(made_tft("T"))
            said = io.StringIO()
            with stand_in_firmware(folder / "cache"), redirect_stdout(io.StringIO()), \
                    redirect_stderr(said):
                code = main(["compile", str(source), str(folder / "app.tft"), "--firmware",
                             str(firmware)])
            return code, said.getvalue()

    def test_a_disup_of_1_is_warned_of(self):
        self.assertEqual(self.compile_text(1),
                         (0, "nxwright compile: warning: %s\n"
                          % (compile_command.DISUP_WARNING % {"where": "page0.t0", "disup": 1})))

    def test_a_disup_of_0_is_not(self):
        self.assertEqual(self.compile_text(0), (0, ""))


if __name__ == "__main__":
    unittest.main()
