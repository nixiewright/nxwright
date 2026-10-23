"""The language server's requests that start a source folder from VS Code:
nxwright/newFolderChoices, the choices `nxwright new` asks for, and
nxwright/newSourceFolder, which writes the folder."""
from pathlib import Path
import tempfile
import tomllib
import unittest

from nxwright.language_server.server import _OWN
from nxwright.project.device_settings import DEFAULT_ENCODING, ENCODINGS
from nxwright.project.screen_copy import ROTATIONS
from nxwright.project.screen_models import MODELS
from nxwright.source.source_folder import LANGUAGES, NXLANG
from tests.language_server_connection import initialized


def request(method: str, **params) -> dict:
    connection = initialized()
    connection.handle({"jsonrpc": "2.0", "id": 2, "method": _OWN + method, "params": params})
    return connection.sent[-1]


class NewFolderChoicesTest(unittest.TestCase):

    def test_the_choices_and_defaults_of_nxwright_new(self):
        choices = request("newFolderChoices")["result"]
        self.assertEqual([model["name"] for model in choices["models"]],
                         [model.name for model in MODELS])
        self.assertEqual(choices["models"][0]["size"],
                         "%d x %d" % (MODELS[0].width, MODELS[0].height))
        self.assertEqual(choices["rotations"], list(ROTATIONS))
        self.assertEqual(choices["encodings"], list(ENCODINGS.values()))
        self.assertEqual(choices["languages"], list(LANGUAGES))
        self.assertEqual(choices["defaults"], {"rotation": 0, "encoding": DEFAULT_ENCODING,
                                               "language": NXLANG})


class NewSourceFolderTest(unittest.TestCase):

    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.root = Path(self._folder.name) / "app"

    def tearDown(self):
        self._folder.cleanup()

    def test_it_writes_the_folder_and_names_its_first_page(self):
        written = request("newSourceFolder", folder=str(self.root), screen="NX4832F035",
                          rotation=90, encoding="iso-8859-1", language="nextion")["result"]
        self.assertEqual(written, {"file": str(self.root / "pages" / "page0.page.toml"),
                                   "warning": None})
        app = tomllib.loads((self.root / "app.toml").read_text(encoding="utf-8"))
        self.assertEqual((app["screen"], app["rotation"], app["language"]),
                         ("NX4832F035", 90, "nextion"))

    def test_the_apps_name(self):
        request("newSourceFolder", folder=str(self.root), screen="NX4832F035", rotation=0,
                encoding="iso-8859-1", language="nextion", name="Thermostat: v2")
        app = tomllib.loads((self.root / "app.toml").read_text(encoding="utf-8"))
        self.assertEqual(app["name"], "Thermostat: v2")

    def test_a_folder_not_empty_is_refused(self):
        self.root.mkdir()
        (self.root / "notes.txt").write_text("kept", encoding="utf-8")
        reply = request("newSourceFolder", folder=str(self.root), screen="NX4832F035",
                        rotation=0, encoding="iso-8859-1", language="nxlang")
        self.assertIn("is not empty", reply["error"]["message"])
        self.assertEqual(sorted(path.name for path in self.root.iterdir()), ["notes.txt"])

    def test_an_unknown_screen_model_is_refused(self):
        reply = request("newSourceFolder", folder=str(self.root), screen="NX0000X000",
                        rotation=0, encoding="iso-8859-1", language="nxlang")
        self.assertIn("NX0000X000", reply["error"]["message"])
        self.assertFalse(self.root.exists())


if __name__ == "__main__":
    unittest.main()
