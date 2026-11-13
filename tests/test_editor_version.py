"""The Nextion Editor's version, as a project file records it
(project/editor_version.py)."""
import unittest

from nxwright.project.device_settings import DeviceSettings, manifest_header
from nxwright.project.editor_version import (CURRENT_VERSION, OLDEST_VERSION,
                                             is_checked_version, version_text)
from nxwright.project.page_header import header_40
from nxwright.project.screen_models import model_named


class EditorVersionTest(unittest.TestCase):

    def test_the_versions_from_the_oldest_to_the_current_are_checked(self):
        for second, third in (OLDEST_VERSION, (61, 2), (62, 9), (68, 1), CURRENT_VERSION):
            with self.subTest(version=version_text(second, third)):
                self.assertTrue(is_checked_version(second, third))

    def test_a_version_before_the_oldest_or_after_the_current_is_not_checked(self):
        for second, third in ((60, 0), (59, 9), (68, 3), (69, 0)):
            with self.subTest(version=version_text(second, third)):
                self.assertFalse(is_checked_version(second, third))

    def test_the_version_is_given_as_text(self):
        self.assertEqual(version_text(0x3d, 2), "1.61.2")

    def test_the_build_writes_the_current_version(self):
        header = manifest_header(DeviceSettings(model_named("NX4832T035"), 0, "iso-8859-1"))
        self.assertEqual((header[9], header[36]), CURRENT_VERSION)
        self.assertEqual(tuple(header_40(3)[1:3]), CURRENT_VERSION)


if __name__ == "__main__":
    unittest.main()
