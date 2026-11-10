"""The nxwright command (cli.py) imports the language server, the debug
adapter, the MCP server, and the test runner only in the subcommands that run
them, so that no other subcommand waits for them."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from nxwright.project.device_settings import DeviceSettings
from nxwright.project.screen_models import model_named
from nxwright.source.source_folder import new_source_folder

# The folder that contains the nxwright package. The tests run each
# subcommand in a new Python process, which starts in this folder so that the
# process can import nxwright.
_PACKAGE_FOLDER = Path(__file__).resolve().parent.parent
# The modules that only the subcommands lsp, debug-adapter, mcp, and test
# use: their own modules, and the two libraries that the language server uses
# for its protocol.
_SUBCOMMAND_ONLY_MODULES = ("lsprotocol", "pygls", "nxwright.language_server.server",
                            "nxwright.debug_adapter.adapter", "nxwright.mcp_server.server",
                            "nxwright.testing.reports")
# Runs the subcommand given in its arguments, then prints the exit code and
# which of _SUBCOMMAND_ONLY_MODULES the process has loaded.
_SCRIPT = """
import contextlib, io, json, sys
from nxwright.cli import main
with contextlib.redirect_stdout(io.StringIO()):
    code = main(sys.argv[1:])
print(json.dumps({"code": code, "loaded": [name for name in %r if name in sys.modules]}))
""" % (_SUBCOMMAND_ONLY_MODULES,)


class CommandStartTest(unittest.TestCase):

    def run_subcommand(self, *arguments: str) -> dict:
        """Runs `nxwright <arguments>` in a new Python process, and returns
        {"code": its exit code, "loaded": the modules of
        _SUBCOMMAND_ONLY_MODULES it loaded}."""
        ran = subprocess.run([sys.executable, "-c", _SCRIPT, *arguments], cwd=_PACKAGE_FOLDER,
                             capture_output=True, text=True)
        self.assertEqual(ran.returncode, 0, ran.stderr)
        return json.loads(ran.stdout.strip().splitlines()[-1])

    def test_a_subcommand_loads_no_module_that_only_another_subcommand_uses(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "app"
            new_source_folder(source, DeviceSettings(model_named("NX4832T035"), 0, "iso-8859-1"),
                              "nxlang")
            self.assertEqual(self.run_subcommand("check", str(source)),
                             {"code": 0, "loaded": []})
            self.assertEqual(self.run_subcommand("new-page", str(source), "second"),
                             {"code": 0, "loaded": []})

    def test_the_test_subcommand_loads_the_test_runner(self):
        with tempfile.TemporaryDirectory() as folder:
            tests = Path(folder) / "tests"
            tests.mkdir()
            (tests / "test_nothing.py").write_text(
                "import unittest\n\n\nclass NothingTest(unittest.TestCase):\n\n"
                "    def test_nothing(self):\n        pass\n", encoding="utf-8")
            self.assertEqual(self.run_subcommand("test", str(tests), "--list"),
                             {"code": 0, "loaded": ["nxwright.testing.reports"]})


if __name__ == "__main__":
    unittest.main()
