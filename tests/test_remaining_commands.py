"""Runs each of the four commands that no other test module runs (defaults,
language, debug-adapter, and lsp) with real arguments, and checks its main
path."""
import contextlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest

from nxwright.cli import main
from nxwright.project.component_defaults import DEFAULTS_FILE
from nxwright.project.device_settings import DeviceSettings
from nxwright.project.new_project import write_new_project
from nxwright.project.screen_models import model_named
from nxwright.source.source_folder import new_source_folder

RUN = Path(__file__).resolve().parent.parent / "run.py"
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def framed(message: dict) -> bytes:
    """Returns `message` framed for the Language Server and Debug Adapter
    Protocols: a Content-Length header, then the JSON."""
    body = json.dumps(message).encode()
    return b"Content-Length: %d\r\n\r\n" % len(body) + body


def first_message(output: bytes) -> dict:
    """Returns the first message of a stream of framed messages."""
    header, rest = output.split(b"\r\n\r\n", 1)
    length = int(next(line for line in header.split(b"\r\n")
                      if line.lower().startswith(b"content-length:")).split(b":")[1])
    return json.loads(rest[:length])


class FolderCommandTest(unittest.TestCase):

    def setUp(self):
        self._work = tempfile.TemporaryDirectory()
        self.work = Path(self._work.name)

    def tearDown(self):
        self._work.cleanup()

    def run_command(self, *arguments) -> str:
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            self.assertEqual(main([str(argument) for argument in arguments]), 0)
        return printed.getvalue()

    def test_defaults_writes_nxwright_s_own_defaults_from_its_sample(self):
        # nxwright's own defaults file was written from objects.HMI, a project
        # with one component of each type, each with the values the Nextion
        # Editor gives a new component. The every-component fixture is that
        # project's dump. A project built from it, and named objects.HMI, must
        # give the same file, down to the header line that names the sample.
        # The build refuses text components without a font, and the dump has
        # none, so the test adds one.
        dump = Path(shutil.copytree(FIXTURES / "every-component", self.work / "dump"))
        (dump / "fonts").mkdir(exist_ok=True)
        shutil.copyfile(FIXTURES / "fonts" / "NotoSans20.zi", dump / "fonts" / "0.zi")
        sample = self.work / "objects.HMI"
        write_new_project(dump, DeviceSettings(model_named("NX8048P070"), 180, "iso-8859-1"),
                          sample)
        output = self.work / "defaults.toml"
        self.assertIn("Wrote", self.run_command("defaults", sample, output))
        self.assertEqual(output.read_text(encoding="utf-8"),
                         DEFAULTS_FILE.read_text(encoding="utf-8"))

    def test_language_switches_a_folder_to_nxlang(self):
        folder = self.work / "app"
        new_source_folder(folder, DeviceSettings(model_named("NX4832T035"), 0, "iso-8859-1"),
                          "nextion")
        self.assertIn("now uses the nxwright language",
                      self.run_command("language", folder, "nxlang"))
        app = tomllib.loads((folder / "app.toml").read_text(encoding="utf-8"))
        self.assertEqual(app["language"], "nxlang_do_not_change_manually")
        # `check` reads the folder the same way the build does, so 0 errors
        # means the switched folder still builds.
        self.assertIn("0 errors", self.run_command("check", folder))


class ServerCommandTest(unittest.TestCase):
    """Starts each server the way an editor does, as its own process that
    reads requests on its standard input and answers on its standard output."""

    def serve(self, command: str, *messages: dict) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(RUN), command],
                              input=b"".join(framed(message) for message in messages),
                              capture_output=True, timeout=60)

    def test_lsp_answers_initialize(self):
        done = self.serve("lsp",
                          {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                           "params": {"processId": None, "rootUri": None, "capabilities": {}}},
                          {"jsonrpc": "2.0", "id": 2, "method": "shutdown"},
                          {"jsonrpc": "2.0", "method": "exit"})
        self.assertEqual(done.returncode, 0, done.stderr.decode())
        answer = first_message(done.stdout)
        self.assertEqual(answer["id"], 1)
        self.assertIn("capabilities", answer["result"])

    def test_debug_adapter_answers_initialize(self):
        done = self.serve("debug-adapter",
                          {"seq": 1, "type": "request", "command": "initialize",
                           "arguments": {"adapterID": "nxwright"}})
        self.assertEqual(done.returncode, 0, done.stderr.decode())
        answer = first_message(done.stdout)
        self.assertEqual((answer["command"], answer["success"]), ("initialize", True))


if __name__ == "__main__":
    unittest.main()
