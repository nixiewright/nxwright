"""The switch to nxlang worked out without writing (nxlang_switch_files), and
the language server's nxwright/nxlangSwitch giving it to the panel that
makes the switch in VS Code."""
import unittest

from nxwright import NxwrightError
from nxwright.source.source_folder import nxlang_switch_files, switch_to_nxlang
from tests.language_server_connection import initialized
from tests.test_nxlang import NxlangFolderTestCase


class NxlangSwitchFilesTest(NxlangFolderTestCase):
    """The folder of NxlangFolderTestCase, whose page first holds
    `x.val=a.val+a.val*2`, which the switch writes `x.val=(a.val+a.val)*2`."""

    def test_the_files_are_those_the_switch_writes(self):
        before = {path: path.read_bytes() for path in self.source.rglob("*") if path.is_file()}
        files = nxlang_switch_files(self.source)
        # Nothing written yet.
        self.assertEqual({path: path.read_bytes() for path in self.source.rglob("*")
                          if path.is_file()}, before)
        self.assertEqual(sorted(files), ["app.toml", "pages/first.nx"])
        switch_to_nxlang(self.source)
        for path, text in files.items():
            self.assertEqual((self.source / path).read_text(encoding="utf-8"), text, path)

    def test_it_refuses_as_the_switch_does(self):
        switch_to_nxlang(self.source)
        with self.assertRaisesRegex(NxwrightError, "already uses nxlang"):
            nxlang_switch_files(self.source)

    def request(self) -> dict:
        connection = initialized()
        connection.handle({"jsonrpc": "2.0", "id": 2, "method": "nxwright/nxlangSwitch",
                           "params": {"folder": str(self.source)}})
        return connection.sent[-1]

    def test_the_request_gives_the_files_and_the_lines_changed(self):
        reply = self.request()["result"]
        self.assertEqual(sorted(entry["path"] for entry in reply["files"]),
                         ["app.toml", "pages/first.nx"])
        self.assertEqual(reply["changes"], [{
            "file": "pages/first.nx", "line": 2,
            "before": "  x.val=a.val+a.val*2", "after": "  x.val=(a.val+a.val)*2"}])

    def test_the_request_refuses_as_the_switch_does(self):
        switch_to_nxlang(self.source)
        self.assertIn("already uses nxlang", self.request()["error"]["message"])


if __name__ == "__main__":
    unittest.main()
