"""The commands on TFT files (tft/commands/): how nxwright's command
line lists them and hands them their arguments, and tft-read and tft-compare
on files the tests make."""
from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

from nxwright.tft import matching, packaging
from tools.tft.probing import probe_runner
from nxwright.cli import main
from tests.tft.made_tft import made_tft
from tests.tft.stand_in_firmware import stand_in_firmware


def run(arguments: list) -> tuple:
    """Runs nxwright's command line on `arguments`; returns its exit code, and
    what it printed and wrote as errors."""
    printed, errors = io.StringIO(), io.StringIO()
    with redirect_stdout(printed), redirect_stderr(errors):
        code = main(arguments)
    return code, printed.getvalue(), errors.getvalue()


class CommandsTest(unittest.TestCase):

    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.folder = Path(self._folder.name)

    def tearDown(self):
        self._folder.cleanup()

    def write(self, name: str, data: bytes) -> str:
        (self.folder / name).write_bytes(data)
        return str(self.folder / name)

    def test_the_help_lists_them_with_their_summaries(self):
        printed = io.StringIO()
        with redirect_stdout(printed), self.assertRaises(SystemExit):
            main(["--help"])
        for name in ("compile", "decompile", "upload", "rescue", "tft-read", "tft-listing",
                     "tft-compare"):
            self.assertIn(name, printed.getvalue())
        self.assertIn("split a TFT file", printed.getvalue())

    def test_each_parses_its_own_arguments(self):
        # The command's own parser prints its help, under nxwright's name.
        printed = io.StringIO()
        with redirect_stdout(printed), self.assertRaises(SystemExit) as stopped:
            main(["tft-read", "--help"])
        self.assertEqual(stopped.exception.code, 0)
        self.assertIn("usage: nxwright tft-read [-h] file", printed.getvalue())

    def test_read(self):
        good = self.write("good.tft", made_tft("T"))
        code, printed, _ = run(["tft-read", good])
        self.assertEqual(code, 0)
        self.assertIn("series T, written by the Nextion Editor 1.68.2", printed)
        self.assertIn("page 0: 13 blocks", printed)
        self.assertIn("every checksum, size, and place holds", printed)
        data = made_tft("T")
        broken = self.write("broken.tft", data[:-1] + b"\x00")
        code, printed, _ = run(["tft-read", broken])
        self.assertEqual(code, 1)
        self.assertIn("problem: the file's checksum", printed)

    def test_compile_refuses_what_it_cannot_write(self):
        source = self.folder / "app"
        shutil.copytree(probe_runner.BASES / "T", source)
        output = self.folder / "app.tft"
        firmware = self.write("firmware.tft", made_tft("T"))
        # Packaging's rules alone, so that what the other pieces match does
        # not change what this test lists.
        with mock.patch.object(matching, "matched_rules", lambda: list(packaging.MATCHED)), \
                stand_in_firmware(self.folder / "cache"):
            code, _, errors = run(["compile", str(source), str(output), "--firmware", firmware])
            self.assertEqual(code, 1)
            self.assertIn("nxwright does not compile these:\n", errors)
            # The page's type, which packaging does not cover.
            self.assertIn("- type page", errors)
            self.assertNotIn("- firmware", errors)
            self.assertFalse(output.exists())
            other = self.write("other.tft", made_tft("T", version=(1, 67, 0)))
            _, _, errors = run(["compile", str(source), str(output), "--firmware", other])
            self.assertIn("was made by the Nextion Editor 1.67.0, but nxwright takes only the "
                          "firmware of the Nextion Editor 1.68.2", errors)

    def test_compile_refuses_an_existing_output(self):
        output = self.write("app.tft", b"keep")
        code, _, errors = run(["compile", str(probe_runner.BASES / "T"), output])
        self.assertEqual((code, Path(output).read_bytes()), (1, b"keep"))
        self.assertIn("exists; pass --overwrite to replace it", errors)

    def test_compare(self):
        a, b = self.write("a.tft", made_tft("T")), self.write("b.tft", made_tft("T"))
        self.assertEqual(run(["tft-compare", a, b])[:2], (0, "%s and %s are the same, byte for "
                                                         "byte\n" % (a, b)))
        other = self.write("other.tft", made_tft("T", fonts=b"other"))
        code, printed, _ = run(["tft-compare", a, other])
        self.assertEqual(code, 1)
        self.assertIn("- the section:", printed)


if __name__ == "__main__":
    unittest.main()
