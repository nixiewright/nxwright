"""nxwright's version: installed_version, `nxwright --version`, and what the
two servers report. Each test replaces the package metadata's lookup, so that
none depends on whether the machine running it has nxwright installed."""
from contextlib import redirect_stdout
import importlib.metadata
import io
import tempfile
import unittest
from unittest import mock

from nxwright import installed_version
from nxwright.cli import main
from nxwright.language_server.server import NxwrightServer
from nxwright.mcp_server.server import mcp_server


def installed(version):
    """A stand-in for importlib.metadata.version: nxwright at `version`, or
    not installed when `version` is None."""
    def lookup(name):
        if version is None:
            raise importlib.metadata.PackageNotFoundError(name)
        return version
    return mock.patch("importlib.metadata.version", lookup)


class VersionTest(unittest.TestCase):

    def version_printed(self) -> str:
        printed = io.StringIO()
        with redirect_stdout(printed), self.assertRaises(SystemExit) as stopped:
            main(["--version"])
        self.assertEqual(stopped.exception.code, 0)
        return printed.getvalue()

    def test_installed(self):
        with installed("1.2.3"):
            self.assertEqual(installed_version(), "1.2.3")
            self.assertEqual(self.version_printed(), "nxwright 1.2.3\n")

    def test_a_source_copy_that_is_not_installed(self):
        with installed(None):
            self.assertIsNone(installed_version())
            self.assertEqual(self.version_printed(), "nxwright (from source, not installed)\n")

    def test_the_servers_report_it(self):
        with installed("1.2.3"), tempfile.TemporaryDirectory() as pictures:
            self.assertEqual(NxwrightServer().version, "1.2.3")
            self.assertEqual(mcp_server(pictures).version, "1.2.3")

    def test_the_mcp_server_says_unknown_for_a_source_copy(self):
        # The protocol wants a version, even from a source copy.
        with installed(None), tempfile.TemporaryDirectory() as pictures:
            self.assertEqual(mcp_server(pictures).version, "unknown")
            self.assertIsNone(NxwrightServer().version)


if __name__ == "__main__":
    unittest.main()
