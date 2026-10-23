"""The language server's nxwright/project request: what the side bar's
sections show of a source folder."""
import unittest
from unittest import mock

from nxwright.language_server import server
from nxwright.language_server.server import _OWN
from nxwright.source.source_folder import SOURCE_FORMAT
from tests.language_server_connection import initialized
from tests.test_folder_check import FolderTestCase, edited_app


class ProjectRequestTest(FolderTestCase):
    """The folder of FolderTestCase: pages page0 and second, on an
    NX8048P050 at 0 degrees, in iso-8859-1 and nxlang."""

    def project(self):
        connection = initialized()
        connection.handle({"jsonrpc": "2.0", "id": 2, "method": _OWN + "project",
                           "params": {"folder": str(self.root)}})
        return connection.sent[-1]["result"]

    def test_a_folder_in_the_current_format(self):
        found = self.project()
        self.assertEqual({key: found[key] for key in ("format", "currentFormat", "language",
                                                      "screen", "size", "rotation", "encoding",
                                                      "pages")},
                         {"format": SOURCE_FORMAT, "currentFormat": SOURCE_FORMAT,
                          "language": "nxlang", "screen": "NX8048P050", "size": "800 x 480",
                          "rotation": 0, "encoding": "iso-8859-1",
                          "pages": ["page0", "second"]})
        self.assertEqual(found["resources"], {"fonts": ["NotoSans24"], "pictures": [],
                                              "animations": [], "videos": [], "sounds": []})

    def test_the_apps_name(self):
        # The folder's name without one in app.toml, else its own.
        self.assertEqual(self.project()["name"], self.root.name)
        self.write("app.toml", edited_app(self.text("app.toml"),
                                          lambda app: app.update(name="Clock")))
        self.assertEqual(self.project()["name"], "Clock")

    def test_a_folder_in_an_older_format_has_its_formats_alone(self):
        # nxwright has no older format yet: format 2 stands in for the
        # current one, and the folder's 1 for an older one.
        with mock.patch.object(server, "SOURCE_FORMAT", 2):
            self.assertEqual(self.project(), {"format": 1, "currentFormat": 2})

    def test_a_folder_whose_format_cannot_be_read_has_nothing(self):
        self.write("app.toml", "format = [")
        self.assertIsNone(self.project())


if __name__ == "__main__":
    unittest.main()
