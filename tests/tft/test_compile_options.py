"""The compile command's options for a caller such as the VS Code extension
(tft/commands/compile.py): compiling a project file, writing the project
file it builds on the way, replacing existing outputs, and its output for
programs, with firmware of the tests' own."""
from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

from nxwright.cli import main
from nxwright.project.replacing import is_project_file
from nxwright.source.project_files import build

from nxwright.tft.commands import compile as compile_command
from tests.tft.made_tft import made_tft
from tests.tft.stand_in_firmware import stand_in_firmware
from tools.tft.probing import probe_runner


class CompileOptionsTest(unittest.TestCase):

    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.folder = Path(self._folder.name)
        self.source = self.folder / "app"
        shutil.copytree(probe_runner.BASES / "T", self.source)
        self.firmware = self.folder / "firmware.tft"
        self.firmware.write_bytes(made_tft("T"))
        self.tft = self.folder / "app.tft"
        self.project_file = self.folder / "app.HMI"

    def tearDown(self):
        self._folder.cleanup()

    def compile(self, source: Path, *options: str, firmware: bool = True) -> tuple:
        """Compiles `source` into self.tft with `options`, and with the
        stand-in firmware file unless not `firmware`. Returns the exit code,
        and what the compile printed and wrote as errors."""
        printed, said = io.StringIO(), io.StringIO()
        given = ["--firmware", str(self.firmware)] if firmware else []
        with stand_in_firmware(self.folder / "cache"), redirect_stdout(printed), \
                redirect_stderr(said):
            code = main(["compile", str(source), str(self.tft), *given, *options])
        return code, printed.getvalue(), said.getvalue()

    def compiled_from_the_folder(self) -> bytes:
        """Returns the TFT file the folder compiles into, written apart."""
        code, _, said = self.compile(self.source)
        self.assertEqual(code, 0, said)
        data = self.tft.read_bytes()
        self.tft.unlink()
        return data

    def test_a_project_file_compiles_as_its_folder_does(self):
        expected = self.compiled_from_the_folder()
        build(self.source, self.project_file)
        code, _, said = self.compile(self.project_file)
        self.assertEqual(code, 0, said)
        self.assertEqual(self.tft.read_bytes(), expected)

    def test_the_project_file_built_on_the_way(self):
        code, printed, said = self.compile(self.source, "--project-file", str(self.project_file))
        self.assertEqual(code, 0, said)
        self.assertTrue(is_project_file(self.project_file))
        self.assertIn("Wrote %s" % self.project_file, printed)
        # It is the project the TFT file was compiled from.
        compiled = self.tft.read_bytes()
        self.tft.unlink()
        code, _, said = self.compile(self.project_file)
        self.assertEqual((code, self.tft.read_bytes()), (0, compiled), said)

    def test_the_project_file_option_needs_a_source_folder(self):
        build(self.source, self.project_file)
        other = self.folder / "other.HMI"
        code, _, said = self.compile(self.project_file, "--project-file", str(other))
        self.assertEqual(code, 1)
        self.assertIn("--project-file", said)
        self.assertFalse(other.exists())
        self.assertFalse(self.tft.exists())

    def test_a_source_that_is_neither_is_refused(self):
        stray = self.folder / "notes.txt"
        stray.write_text("notes", encoding="utf-8")
        code, _, said = self.compile(stray)
        self.assertEqual(code, 1)
        self.assertIn("is neither a source folder nor a project file", said)
        code, _, said = self.compile(self.folder / "missing")
        self.assertEqual(code, 1)
        self.assertIn("%s does not exist" % (self.folder / "missing"), said)

    def test_existing_outputs_are_kept_without_overwrite(self):
        self.tft.write_bytes(made_tft("T"))
        code, _, said = self.compile(self.source)
        self.assertEqual(code, 1)
        self.assertIn("%s exists; pass --overwrite to replace it" % self.tft, said)
        self.assertEqual(self.tft.read_bytes(), made_tft("T"))
        self.tft.unlink()
        build(self.source, self.project_file)
        kept = self.project_file.read_bytes()
        code, _, said = self.compile(self.source, "--project-file", str(self.project_file))
        self.assertEqual(code, 1)
        self.assertIn("%s exists; pass --overwrite to replace it" % self.project_file, said)
        self.assertEqual(self.project_file.read_bytes(), kept)
        self.assertFalse(self.tft.exists())

    def test_overwrite_replaces_both(self):
        expected = self.compiled_from_the_folder()
        self.tft.write_bytes(made_tft("T"))
        build(self.source, self.project_file)
        code, _, said = self.compile(self.source, "--project-file", str(self.project_file),
                                     "--overwrite")
        self.assertEqual(code, 0, said)
        self.assertEqual(self.tft.read_bytes(), expected)
        self.assertTrue(is_project_file(self.project_file))

    def test_overwrite_replaces_only_files_of_their_kind(self):
        # As build's: a mistyped output, such as a file of the source folder,
        # is refused.
        self.tft.write_text("not a TFT file", encoding="utf-8")
        code, _, said = self.compile(self.source, "--overwrite")
        self.assertEqual(code, 1)
        self.assertIn("%s exists and is not a TFT file" % self.tft, said)
        self.assertEqual(self.tft.read_text(encoding="utf-8"), "not a TFT file")
        self.tft.unlink()
        self.project_file.write_text("not a project", encoding="utf-8")
        code, _, said = self.compile(self.source, "--project-file", str(self.project_file),
                                     "--overwrite")
        self.assertEqual(code, 1)
        self.assertIn("is not a project file", said)
        self.assertEqual(self.project_file.read_text(encoding="utf-8"), "not a project")
        self.assertFalse(self.tft.exists())

    def test_a_refused_compile_writes_neither(self):
        later = self.folder / "later.tft"
        later.write_bytes(made_tft("T", version=(1, 69, 0)))
        self.firmware = later
        code, _, _ = self.compile(self.source, "--project-file", str(self.project_file))
        self.assertEqual(code, 1)
        self.assertFalse(self.tft.exists())
        self.assertFalse(self.project_file.exists())

    def test_a_project_file_that_cannot_be_replaced_leaves_the_tft_file(self):
        # As when the Nextion Editor has the project open: the project file
        # is replaced first, so that the TFT file is kept as it was.
        self.tft.write_bytes(made_tft("T"))
        build(self.source, self.project_file)
        kept = self.project_file.read_bytes()
        replace = os.replace

        def refused(written, output):
            if Path(output) == self.project_file:
                raise PermissionError(13, "Permission denied", str(output))
            return replace(written, output)
        with mock.patch.object(os, "replace", refused):
            code, _, said = self.compile(self.source, "--project-file", str(self.project_file),
                                         "--overwrite")
        self.assertEqual(code, 1)
        self.assertIn("Permission denied", said)
        self.assertEqual(self.tft.read_bytes(), made_tft("T"))
        self.assertEqual(self.project_file.read_bytes(), kept)
        self.assertEqual(sorted(path.name for path in self.folder.glob("*.partial")), [])

    def test_a_file_that_appears_during_the_compile_is_kept(self):
        # Without --overwrite, a file written at the output while the
        # compile ran, as during a download, is not replaced.
        compile_project = compile_command.compile_project

        def compiled(*arguments, **options):
            self.tft.write_bytes(b"written meanwhile")
            return compile_project(*arguments, **options)
        with mock.patch.object(compile_command, "compile_project", compiled):
            code, _, said = self.compile(self.source)
        self.assertEqual(code, 1)
        self.assertIn("%s exists; pass --overwrite to replace it" % self.tft, said)
        self.assertEqual(self.tft.read_bytes(), b"written meanwhile")

    def test_firmware_missing_only_when_no_download_was_allowed(self):
        # A download allowed, which then failed, is not offered again.
        no_firmware = mock.Mock(firmware=None, skipped=("the download failed",))
        with mock.patch.object(compile_command, "find_firmware", lambda *arguments: no_firmware):
            with self.assertRaises(compile_command.FirmwareMissing):
                compile_command.compile_folder(self.source, self.tft,
                                               asker=compile_command.TerminalAsker(False,
                                                                                   as_json=True))
            with self.assertRaises(compile_command.NxwrightError) as refused:
                compile_command.compile_folder(self.source, self.tft,
                                               asker=compile_command.TerminalAsker(True,
                                                                                   as_json=True))
        self.assertNotIsInstance(refused.exception, compile_command.FirmwareMissing)

    def test_json_gives_what_was_written(self):
        code, printed, said = self.compile(self.source, "--project-file", str(self.project_file),
                                           "--json")
        self.assertEqual(code, 0, said)
        self.assertEqual([json.loads(line) for line in printed.splitlines()], [{
            "event": "compiled", "tft": str(self.tft), "project_file": str(self.project_file),
            "firmware_source": "the TFT file %s" % self.firmware, "warnings": []}])
        # The words for people go to standard error.
        self.assertIn("Wrote %s" % self.tft, said)

    def test_json_gives_firmware_it_may_download(self):
        code, printed, said = self.compile(self.source, "--json", firmware=False)
        self.assertEqual(code, 1)
        self.assertEqual([json.loads(line) for line in printed.splitlines()],
                         [{"event": "firmware-missing", "version": "1.68.2"}])
        self.assertIn("no firmware was found", said)

    def test_json_never_prompts(self):
        with mock.patch.object(compile_command.sys.stdin, "isatty", lambda: True), \
                mock.patch.object(compile_command.sys.stdout, "isatty", lambda: True), \
                mock.patch("builtins.input") as typed:
            asker = compile_command.TerminalAsker(False, as_json=True)
            self.assertFalse(asker.can_ask())
            self.assertFalse(asker.allows_download("a zip", 10, "https://nextion.tech/a"))
        typed.assert_not_called()

    def test_json_gives_the_download_s_progress(self):
        printed = io.StringIO()
        with redirect_stdout(printed):
            compile_command.TerminalAsker(True, as_json=True).report_progress(10, 40)
        self.assertEqual(json.loads(printed.getvalue()),
                         {"event": "download", "done": 10, "size": 40})


if __name__ == "__main__":
    unittest.main()
