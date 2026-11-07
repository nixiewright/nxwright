"""The rescue command (tft/commands/rescue.py): the source folder of the
rescue app, and the TFT file it compiles into, with firmware of the tests'
own."""
from contextlib import redirect_stderr, redirect_stdout
import io
from pathlib import Path
import tempfile
import tomllib
import unittest

from nxwright.cli import main
from nxwright.project.screen_models import model_named
from nxwright.tft.commands import rescue
from nxwright.tft.tft_file import device_id_of
from tests.tft.made_tft import made_tft
from tests.tft.stand_in_firmware import stand_in_firmware


class RescueCommandTest(unittest.TestCase):

    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.folder = Path(self._folder.name)
        self.firmware = self.folder / "firmware.tft"
        self.firmware.write_bytes(made_tft("T"))
        self.tft = self.folder / "rescue.tft"

    def tearDown(self):
        self._folder.cleanup()

    def rescue(self, *options: str) -> tuple:
        """Runs the rescue command into self.tft with `options`, and the
        stand-in firmware file. Returns the exit code, and what the command
        printed and wrote as errors."""
        printed, said = io.StringIO(), io.StringIO()
        with stand_in_firmware(self.folder / "cache"), redirect_stdout(printed), \
                redirect_stderr(said):
            code = main(["rescue", str(self.tft), "--firmware", str(self.firmware), *options])
        return code, printed.getvalue(), said.getvalue()

    def test_the_rescue_folder_resets_the_saved_settings_then_shows_page_0(self):
        source = self.folder / "rescue"
        rescue.write_rescue_folder(source, model_named("NX4832T035"))
        self.assertEqual((source / "program.nx").read_text(encoding="utf-8"),
                         "int sys0=0,sys1=0,sys2=0\n"
                         "dims=100\n"
                         "bauds=9600\n"
                         "recmod=0\n"
                         "addr=0\n"
                         "sleep=0\n"
                         "page 0\n")
        app = tomllib.loads((source / "app.toml").read_text(encoding="utf-8"))
        self.assertEqual((app["screen"], app["rotation"], app["pages"]),
                         ("NX4832T035", 0, ["page0"]))

    def test_the_tft_file_is_for_the_screen_model(self):
        code, printed, said = self.rescue("--screen", "NX4832T035")
        self.assertEqual(code, 0, said)
        self.assertEqual(device_id_of(self.tft.read_bytes()),
                         model_named("NX4832T035").device_id)
        self.assertIn("Wrote %s" % self.tft, printed)

    def test_an_unknown_screen_model_is_refused(self):
        code, _, said = self.rescue("--screen", "NX0000T000")
        self.assertEqual(code, 1)
        self.assertIn("nxwright rescue: unknown screen model 'NX0000T000'", said)
        self.assertFalse(self.tft.exists())

    def test_an_existing_tft_file_is_replaced_only_with_overwrite(self):
        self.tft.write_bytes(made_tft("T"))
        code, _, said = self.rescue("--screen", "NX4832T035")
        self.assertEqual((code, self.tft.read_bytes()), (1, made_tft("T")))
        self.assertIn("exists; pass --overwrite to replace it", said)
        code, _, said = self.rescue("--screen", "NX4832T035", "--overwrite")
        self.assertEqual(code, 0, said)
        self.assertNotEqual(self.tft.read_bytes(), made_tft("T"))


if __name__ == "__main__":
    unittest.main()
