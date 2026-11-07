"""The decompile command (tft/commands/decompile.py): what it writes, what
it refuses, and what it prints, around the round trip
(tft/decompiling/round_trip.py), which a stand-in gives here so that the
command's own choices are tested alone. The round trip itself, on whole
files, has its own tests.
"""
from contextlib import redirect_stderr, redirect_stdout
import io
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

from nxwright.cli import main
from nxwright.tft.decompiling import DecodeError
from nxwright.tft.decompiling.compared import Mismatch
from nxwright.tft.decompiling.decoded_file import Name

# A name no guess matched, of object 3 of page 1, and of page 2.
_NAMES = [(("object", 1, 3), Name("text3", 0x1234, False)),
          (("page", 2), Name("page2", 0x5678, False))]


def _written_round_trip(mismatches: list = (), names: list = (), warning: str = None,
                        compiled_again: bool = True, unchecked_reason: str = None):
    """Returns a stand-in of round_trip, which writes a folder of one file,
    app.toml, and gives a RoundTrip's `mismatches`, `names`, `warning`, and
    `unchecked_reason`, and as its file compiled again a stand-in, or None,
    as for an older file or a folder not compiled again, unless
    `compiled_again`. It imports no round trip, which the unit-test guard
    counts as a build."""
    def round_trip(tft_bytes: bytes, where: str, folder: Path):
        folder.mkdir(parents=True)
        (folder / "app.toml").write_text("format = 1\n", encoding="utf-8")
        return SimpleNamespace(original=None, again=object() if compiled_again else None,
                               mismatches=list(mismatches), names=list(names), warning=warning,
                               unchecked_reason=unchecked_reason)
    return round_trip


# A round trip whose folder the compile refuses, as for a line the compile has
# no rule for.
_NOT_COMPILED = _written_round_trip(
    compiled_again=False,
    unchecked_reason="nxwright does not compile these:\n- code event = 'sys0=x' (page0, line 1)")
# A difference between the file given and the one compiled again.
_MISMATCH = Mismatch("pages[0].objects[1].entries[9]", b"\x01" * 100, b"\x02")


class CommandTest(unittest.TestCase):

    def run_command(self, file: Path, folder: Path, round_trip, *options: str,
                    at_terminal: bool = False, answers: list = ()) -> tuple:
        """Returns (the exit code, what was printed, what was printed as
        errors) of `nxwright decompile file folder options`, with `round_trip`,
        a stand-in. When `at_terminal`, the command's input and output are a
        terminal, where the user gives `answers` one at a time, and then the
        input ends."""
        printed, errors = io.StringIO(), io.StringIO()
        given = iter(answers)

        def answer(question: str) -> str:
            printed.write(question)
            try:
                return next(given)
            except StopIteration:
                raise EOFError from None
        with mock.patch("nxwright.tft.commands.decompile.round_trip", round_trip), \
                mock.patch("nxwright.tft.commands.decompile.at_terminal", lambda: at_terminal), \
                mock.patch("builtins.input", answer), \
                redirect_stdout(printed), redirect_stderr(errors):
            code = main(["decompile", str(file), str(folder), *options])
        return code, printed.getvalue(), errors.getvalue()

    def decompile(self, round_trip, *options: str, at_terminal: bool = False,
                  answers: list = ()) -> tuple:
        """Returns (the exit code, what was printed, what was printed as
        errors, the files written to the folder given) of a decompile of a
        stand-in file into a new folder, as run_command does."""
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)
            (work / "app.tft").write_bytes(b"a TFT file")
            code, printed, errors = self.run_command(work / "app.tft", work / "app", round_trip,
                                                     *options, at_terminal=at_terminal,
                                                     answers=answers)
            written = (sorted(path.name for path in (work / "app").iterdir())
                       if (work / "app").exists() else [])
            printed = printed.replace(str(work), "<work>")
        return code, printed, errors, written

    def test_a_folder_written(self):
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)
            (work / "app.tft").write_bytes(b"a TFT file")
            code, printed, _ = self.run_command(work / "app.tft", work / "app",
                                                _written_round_trip())
            self.assertEqual(code, 0)
            self.assertEqual(sorted(path.name for path in (work / "app").iterdir()),
                             ["app.toml"])
            self.assertIn("wrote %s" % (work / "app"), printed)

    def test_an_empty_folder_written(self):
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)
            (work / "app.tft").write_bytes(b"a TFT file")
            (work / "app").mkdir()
            code, _, _ = self.run_command(work / "app.tft", work / "app", _written_round_trip())
            self.assertEqual(code, 0)
            self.assertTrue((work / "app" / "app.toml").is_file())

    def test_the_names_no_guess_matched(self):
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)
            (work / "app.tft").write_bytes(b"a TFT file")
            _, printed, _ = self.run_command(work / "app.tft", work / "app",
                                             _written_round_trip(names=_NAMES))
            self.assertIn("2 names matched no guess", printed)
            self.assertIn("  text3: object 3 of page 1\n", printed)
            self.assertIn("  page2: page 2\n", printed)

    def test_a_folder_not_empty(self):
        # Nothing is decompiled, and the folder's file stays as it was.
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)
            (work / "app.tft").write_bytes(b"a TFT file")
            (work / "app").mkdir()
            (work / "app" / "notes.txt").write_text("mine", encoding="utf-8")
            never = mock.Mock(side_effect=AssertionError("round_trip was called"))
            code, _, errors = self.run_command(work / "app.tft", work / "app", never)
            self.assertEqual(code, 2)
            self.assertIn("is not an empty folder", errors)
            self.assertEqual([path.name for path in (work / "app").iterdir()], ["notes.txt"])

    def test_a_warning(self):
        # A file of a firmware older than those tested is written all the
        # same, after the warning.
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)
            (work / "app.tft").write_bytes(b"a TFT file")
            code, _, errors = self.run_command(
                work / "app.tft", work / "app", _written_round_trip(warning="an older one"))
            self.assertEqual(code, 0)
            self.assertTrue((work / "app" / "app.toml").is_file())
            self.assertIn("nxwright decompile: warning: an older one", errors)

    def test_an_older_file_without_a_round_trip(self):
        # Its folder is written, and the command claims no check that never ran.
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)
            (work / "app.tft").write_bytes(b"a TFT file")
            code, printed, _ = self.run_command(
                work / "app.tft", work / "app",
                _written_round_trip(warning="an older one", compiled_again=False))
            self.assertEqual(code, 0)
            self.assertTrue((work / "app" / "app.toml").is_file())
            self.assertIn("nxwright decompile: wrote %s\n" % (work / "app"), printed)
            self.assertNotIn("same content", printed)

    def test_a_round_trip_that_differs(self):
        # Each mismatch is printed. With nobody to ask, nothing is written,
        # and the exit code tells this stop from a refusal.
        code, _, errors, written = self.decompile(_written_round_trip([_MISMATCH]))
        self.assertEqual(code, 3)
        self.assertEqual(written, [])
        self.assertIn("compiles into a file that differs", errors)
        self.assertIn("pages[0].objects[1].entries[9]", errors)
        self.assertIn("...", errors)
        self.assertIn("there was no terminal to prompt at, so nothing was written. Pass "
                      "--continue-unconfirmed to write this folder.", errors)

    def test_a_folder_not_compiled_again(self):
        # The refusal is printed whole. With nobody to ask, nothing is
        # written.
        code, _, errors, written = self.decompile(_NOT_COMPILED)
        self.assertEqual(code, 3)
        self.assertEqual(written, [])
        self.assertIn("nxwright decompile: warning: the round trip could not check the folder: "
                      "nxwright does not compile these:\n- code event = 'sys0=x' (page0, line 1)",
                      errors)

    def test_an_unconfirmed_folder_with_the_option(self):
        # Written without a question, after the warning, and the last line
        # claims no check that did not hold.
        for round_trip in (_NOT_COMPILED, _written_round_trip([_MISMATCH])):
            with self.subTest(round_trip=round_trip):
                code, printed, errors, written = self.decompile(
                    round_trip, "--continue-unconfirmed")
                self.assertEqual(code, 0)
                self.assertEqual(written, ["app.toml"])
                self.assertIn("nxwright decompile: warning:", errors)
                self.assertTrue(printed.endswith("nxwright decompile: wrote <work>%sapp\n"
                                                 % os.sep), printed)
                self.assertNotIn("Go on anyway?", printed)

    def test_an_unconfirmed_folder_at_a_terminal(self):
        # "y" writes, "n" or an empty answer stops, another answer asks
        # again, and the end of the input is as nobody to ask.
        cases = ((["y"], 0, ["app.toml"]), (["n"], 1, []), ([""], 1, []),
                 (["maybe", "yes"], 0, ["app.toml"]), ([], 3, []))
        for round_trip in (_NOT_COMPILED, _written_round_trip([_MISMATCH])):
            for answers, code, written in cases:
                with self.subTest(round_trip=round_trip, answers=answers):
                    got, printed, errors, files = self.decompile(round_trip, at_terminal=True,
                                                                 answers=answers)
                    self.assertEqual((got, files), (code, written))
                    self.assertIn("Go on anyway? [y/N]: ", printed)
                    if code == 1:
                        self.assertIn("nxwright decompile: stopped; nothing was written", errors)
                    if code == 3:
                        self.assertIn("the input ended at the prompt, so nothing was written",
                                      errors)
        _, printed, _, _ = self.decompile(_NOT_COMPILED, at_terminal=True,
                                          answers=["maybe", "y"])
        self.assertIn("Not one of the choices: y, n", printed)

    def test_a_confirmed_folder_asks_nothing(self):
        code, printed, _, written = self.decompile(_written_round_trip(), at_terminal=True)
        self.assertEqual((code, written), (0, ["app.toml"]))
        self.assertNotIn("Go on anyway?", printed)
        self.assertIn("which compiles into a file of the same content", printed)

    def test_a_file_the_decompiler_refuses(self):
        # A decoder's refusal is printed, the command exits with 1, and
        # nothing is written to the folder, even with the option.
        def refusing(tft_bytes: bytes, where: str, folder: Path):
            raise DecodeError("an unknown command", 0x40, b"\x09\x99")
        for options in ((), ("--continue-unconfirmed",)):
            with self.subTest(options=options):
                code, _, errors, written = self.decompile(refusing, *options)
                self.assertEqual(code, 1)
                self.assertEqual(written, [])
                self.assertIn("an unknown command, at 0x40", errors)

    def test_a_folder_that_cannot_be_written(self):
        # The copy into the folder fails, as on a full disk.
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)
            (work / "app.tft").write_bytes(b"a TFT file")
            with mock.patch("nxwright.tft.commands.decompile.shutil.copytree",
                            side_effect=OSError("the disk is full")):
                code, _, errors = self.run_command(work / "app.tft", work / "app",
                                                   _written_round_trip())
            self.assertEqual(code, 1)
            self.assertIn("nxwright decompile: the disk is full", errors)

    def test_a_file_that_cannot_be_read(self):
        with tempfile.TemporaryDirectory() as work:
            work = Path(work)
            code, _, errors = self.run_command(work / "missing.tft", work / "app",
                                               _written_round_trip())
            self.assertEqual(code, 1)
            self.assertFalse((work / "app").exists())
            self.assertIn("nxwright decompile:", errors)


if __name__ == "__main__":
    unittest.main()
