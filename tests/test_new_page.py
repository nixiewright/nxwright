"""Adding a blank page to a source folder: add_page, `nxwright new-page`, and
the language server's nxwright/addPage."""
import contextlib
import io
from pathlib import Path
import tomllib
import unittest

from nxwright import NxwrightError
from nxwright.cli import main
from nxwright.language_server.file_texts import uri_of
from nxwright.language_server.server import _OWN
from nxwright.project.device_settings import DeviceSettings
from nxwright.project.screen_models import model_named
from nxwright.source.project_files import build
from nxwright.source.source_folder import add_page, new_source_folder
from tests.language_server_connection import initialized
from tests.test_folder_check import FolderTestCase


class AddPageTest(FolderTestCase):
    """The folder of FolderTestCase: pages page0 and second, on an
    NX8048P050 at 0 degrees."""

    def app(self) -> dict:
        return tomllib.loads(self.text("app.toml"))

    def test_a_named_page_is_listed_last_with_its_files(self):
        self.assertEqual(add_page(self.root, "settings"), "settings")
        self.assertEqual(self.app()["pages"], ["page0", "second", "settings"])
        table = tomllib.loads(self.text("pages/settings.page.toml"))["page"]
        self.assertEqual((table["name"], table["w"], table["h"]), ("settings", 800, 480))
        self.assertEqual(self.text("pages/settings.nx"), "")

    def test_without_a_name_it_takes_the_first_free_one(self):
        self.assertEqual(add_page(self.root), "page1")
        self.assertEqual(add_page(self.root), "page2")
        self.assertEqual(self.app()["pages"], ["page0", "second", "page1", "page2"])

    def test_the_page_is_the_size_of_the_screen_at_its_rotation(self):
        turned = self.root.parent / "turned"
        new_source_folder(turned, DeviceSettings(model_named("NX8048P050"), 90, "iso-8859-1"),
                          "nxlang")
        add_page(turned, "side")
        table = tomllib.loads((turned / "pages/side.page.toml").read_text(encoding="utf-8"))
        self.assertEqual((table["page"]["w"], table["page"]["h"]), (480, 800))

    def test_the_folder_still_builds(self):
        add_page(self.root, "settings")
        build(self.root, self.root.parent / "app.HMI")
        self.assertTrue((self.root.parent / "app.HMI").is_file())

    def assertRefused(self, message: str, name):
        before = {path: path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        with self.assertRaises(NxwrightError) as raised:
            add_page(self.root, name)
        self.assertIn(message, str(raised.exception))
        after = {path: path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        self.assertEqual(after, before)

    def test_a_name_the_folder_has_in_any_case_is_refused(self):
        self.assertRefused("the folder has a page named second already", "Second")

    def test_names_the_folder_or_the_editor_refuses_are_refused(self):
        self.assertRefused("is not a valid page name", "sub/page")
        self.assertRefused("is not a valid page name", "two words")
        self.assertRefused("has 15 characters; the Nextion Editor keeps 14", "averylongpage15")
        self.assertRefused("the Nextion Editor refuses this name", "dim")
        # The Nextion Editor refused a project with such a page as it opened it.
        self.assertRefused('the Nextion Editor refuses a name that starts with a digit, saying '
                           '"First character of a Name can not be number": 2page', "2page")

    def test_a_file_already_there_is_refused(self):
        self.write("pages/settings.nx", "")
        self.assertRefused("is already there, though app.toml does not list it", "settings")

    def test_a_folder_without_screen_settings_is_refused(self):
        app = self.text("app.toml")
        self.write("app.toml", "\n".join(line for line in app.split("\n")
                                         if not line.startswith(("screen", "rotation",
                                                                 "encoding"))))
        self.assertRefused("app.toml gives no screen settings", "settings")


class NewPageCommandTest(FolderTestCase):

    def test_the_subcommand(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["new-page", str(self.root), "settings"]), 0)
            self.assertEqual(main(["new-page", str(self.root)]), 0)
        self.assertIn("Added the page settings", output.getvalue())
        self.assertIn("Added the page page1", output.getvalue())
        self.assertTrue((self.root / "pages/page1.page.toml").is_file())


class AddPageRequestTest(FolderTestCase):

    def request(self, **params) -> dict:
        connection = initialized()
        params["textDocument"] = {"uri": uri_of(self.root / "pages/page0.page.toml")}
        connection.handle({"jsonrpc": "2.0", "id": 2, "method": _OWN + "addPage",
                           "params": params})
        return connection.sent[-1]

    def test_it_adds_the_page_and_names_its_file(self):
        added = self.request(name="settings")["result"]
        self.assertEqual(added["page"], "settings")
        # The folder comes from the file's URI, whose drive letter may differ in case.
        self.assertTrue(Path(added["file"]).samefile(self.root / "pages" / "settings.page.toml"))
        self.assertEqual(self.request()["result"]["page"], "page1")

    def test_a_refusal_is_the_requests_error(self):
        self.assertIn("the folder has a page named second already",
                      self.request(name="second")["error"]["message"])


if __name__ == "__main__":
    unittest.main()
