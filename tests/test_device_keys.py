"""The device settings in a source folder's app.toml."""
import contextlib
import io
import unittest

from nxwright import NxwrightError
from nxwright.cli import main
from nxwright.project.device_settings import (DeviceSettings, password_hash,
                                              read_device_settings)
from nxwright.project.screen_models import model_named
from nxwright.source.device_keys import device_keys, settings_from_keys
from nxwright.source.project_files import build
from nxwright.source.source_folder import folder_device_settings, import_dump
from tests.test_project_writer import edit_text
from tests.test_screen_models import manifest_of
from tests.test_source_folder import SourceFolderTestCase

DEFAULTS = DeviceSettings(model_named("NX8048P050"), 180, "iso-8859-1")
EVERYTHING = DeviceSettings(model_named("NX8048P070"), 90, "utf-8", one_time_update=True,
                            memory_file_storage_size=123456, ignore_library_resources=True,
                            ignore_image_resources=True, password_hash=bytes.fromhex("2c8b519c"))


class DeviceKeysTest(unittest.TestCase):

    def test_round_trip(self):
        for settings in (DEFAULTS, EVERYTHING):
            with self.subTest(settings=settings):
                self.assertEqual(settings_from_keys(device_keys(settings)), settings)

    def test_only_settings_away_from_the_default_are_written(self):
        self.assertEqual(device_keys(DEFAULTS),
                         {"screen": "NX8048P050", "rotation": 180, "encoding": "iso-8859-1"})
        self.assertEqual(list(device_keys(EVERYTHING)),
                         ["screen", "rotation", "encoding", "one_time_update",
                          "memory_file_storage_size", "ignore_library_resources",
                          "ignore_image_resources", "password_hash"])

    def test_no_keys_no_settings(self):
        self.assertIsNone(settings_from_keys({"format": 1}))

    def test_wrong_values_are_refused(self):
        good = device_keys(DEFAULTS)
        for change, message in (({"screen": None}, "needs screen"),
                                ({"screen": "NX0000X000"}, "unknown screen model"),
                                ({"rotation": 45}, "rotation must be"),
                                ({"rotation": True}, "rotation must be"),
                                ({"encoding": "latin-9"}, "unknown character encoding"),
                                ({"one_time_update": 1}, "one_time_update must be true or false"),
                                ({"memory_file_storage_size": -1}, "must be a number of bytes"),
                                ({"password_hash": "2C8B519C"}, "password_hash must be")):
            keys = dict(good, **change)
            keys = {key: value for key, value in keys.items() if value is not None}
            with self.subTest(change=change):
                with self.assertRaisesRegex(NxwrightError, message):
                    settings_from_keys(keys)


class SourceFolderDeviceTest(SourceFolderTestCase):
    """The small test project, an NX1060P101 one."""

    def give_the_dump_header(self, header: bytes):
        """Puts the manifest header `header` in the dump, as project.txt shows it."""
        summary = self.dump / "project.txt"
        lines = [line if not line.split()[:1] == ["unknown_header"]
                 else "  unknown_header   %s" % (header[8:24] + header[32:96]).hex()
                 for line in summary.read_text(encoding="utf-8").split("\n")]
        summary.write_text("\n".join(lines), encoding="utf-8", newline="\n")

    def test_import_writes_the_projects_settings(self):
        self.assertEqual(folder_device_settings(self.source),
                         read_device_settings(manifest_of("NX1060P101")))

    def test_a_project_of_an_unknown_model_has_none(self):
        self.give_the_dump_header(bytes(96))
        source = self.folder / "unknown-model"
        import_dump(self.dump, source)
        self.assertIsNone(folder_device_settings(source))

    def test_import_writes_the_dumps_settings(self):
        header = manifest_of("NX8048P050")[:96]
        self.give_the_dump_header(header)
        source = self.folder / "with-settings"
        import_dump(self.dump, source)
        text = (source / "app.toml").read_text(encoding="utf-8")
        self.assertIn('language = "nextion"\nscreen = "NX8048P050"\n', text)
        self.assertEqual(folder_device_settings(source), read_device_settings(header))

    def test_build_refuses_a_folder_without_settings(self):
        edit_text(self.source / "app.toml",
                  'screen = "NX1060P101"\nrotation = 0\nencoding = "iso-8859-1"\n', "")
        output = self.folder / "built.HMI"
        with self.assertRaisesRegex(NxwrightError, "has no device settings"):
            build(self.source, output)
        self.assertFalse(output.exists())


class PasswordHashTest(unittest.TestCase):

    def test_the_hash_is_the_editors(self):
        # The Editor saved this project with the password "abc", and one with
        # "Password1", which it stored as 44 97 67 f9.
        self.assertEqual(password_hash("Password1"), bytes.fromhex("449767f9"))
        stored = manifest_of("settings-password-abc")[20:24]
        self.assertEqual(password_hash("abc"), stored)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["password-hash", "abc"]), 0)
        self.assertEqual(output.getvalue(), stored.hex() + "\n")

    def test_refusals(self):
        for password, message in (("", "an empty password"), ("é", "outside ASCII")):
            with self.subTest(password=password):
                with self.assertRaisesRegex(NxwrightError, message):
                    password_hash(password)


if __name__ == "__main__":
    unittest.main()
