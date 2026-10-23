"""The screen model table and the device settings, against manifests the
Editor saved: one per model (fixtures/manifests/<model>.main), and one per
device setting changed alone (fixtures/manifests/settings-*.main)."""
from pathlib import Path
import unittest

from nxwright import NxwrightError
from nxwright.project.device_settings import (DeviceSettings, manifest_header,
                                              read_device_settings)
from nxwright.project.resources import encode_manifest, parse_manifest
from nxwright.project.screen_copy import FORMAT_COMPRESSED, FORMAT_RAW, FORMAT_RAW_WITH_HEADER
from nxwright.project.screen_models import MODELS, model_named, model_with_id
from nxwright.project.stamp import stamp_number, with_model_manifest_stamp

MANIFESTS = Path(__file__).resolve().parent / "fixtures" / "manifests"


def manifest_of(name: str) -> bytes:
    return (MANIFESTS / (name + ".main")).read_bytes()


class ScreenModelTest(unittest.TestCase):

    def test_the_table_holds_each_model_once(self):
        self.assertEqual(len(MODELS), 27)
        self.assertEqual(len({model.name for model in MODELS}), 27)
        self.assertEqual(len({model.device_id for model in MODELS}), 27)

    def test_each_models_manifest_names_it_and_gives_its_stamp_number(self):
        for model in MODELS:
            with self.subTest(model=model.name):
                manifest = manifest_of(model.name)
                self.assertEqual(model_with_id(manifest[16:20]), model)
                self.assertEqual(stamp_number(manifest), model.stamp_number)

    def test_the_editors_manifests_are_written_back_byte_for_byte(self):
        # The header from the settings, the Editor's resource list, then the
        # stamp from the table: no reference manifest is needed.
        for model in MODELS:
            with self.subTest(model=model.name):
                manifest = manifest_of(model.name)
                settings = read_device_settings(manifest)
                written = with_model_manifest_stamp(
                    encode_manifest(manifest_header(settings),
                                    parse_manifest(manifest).resources), model.stamp_number)
                self.assertEqual(written, manifest)

    def test_the_picture_format_follows_the_series(self):
        for name, kind in (("NX4832T035", FORMAT_RAW), ("NX8048K050", FORMAT_RAW),
                           ("NX3224F024", FORMAT_RAW_WITH_HEADER), ("NX8048P050", FORMAT_COMPRESSED),
                           ("NX4880E043", FORMAT_COMPRESSED)):
            with self.subTest(model=name):
                self.assertEqual(model_named(name).picture_format, kind)

    def test_an_unknown_model_is_refused_by_name(self):
        with self.assertRaisesRegex(NxwrightError, "unknown screen model 'NX9999X999'"):
            model_named("NX9999X999")


class DeviceSettingsTest(unittest.TestCase):
    """The settings-*.main manifests: an NX3224T024 project with one setting
    changed each, but for the memory size, which needs an Intelligent screen."""

    def settings(self, name: str) -> DeviceSettings:
        return read_device_settings(manifest_of("settings-" + name))

    def test_each_setting(self):
        default = self.settings("default")
        self.assertEqual((default.model.name, default.rotation, default.encoding),
                         ("NX3224T024", 0, "iso-8859-1"))
        self.assertEqual(self.settings("password-abc").password_hash, bytes.fromhex("2c8b519c"))
        memory = self.settings("memory-file-storage-size-123456bytes")
        self.assertEqual((memory.model.name, memory.memory_file_storage_size),
                         ("NX4827P043", 123456))
        self.assertTrue(
            self.settings("ignore-image-resources-at-compile-time").ignore_image_resources)
        self.assertTrue(
            self.settings("ignore-library-resouces-at-compile-time").ignore_library_resources)
        self.assertEqual(self.settings("encoding-utf-8").encoding, "utf-8")

    def test_the_header_is_written_back(self):
        for path in sorted(MANIFESTS.glob("settings-*.main")):
            with self.subTest(manifest=path.stem):
                manifest = path.read_bytes()
                header = bytearray(manifest_header(read_device_settings(manifest)))
                # The stamp and the resource count depend on the whole manifest.
                header[0:4], header[28:32] = manifest[0:4], manifest[28:32]
                self.assertEqual(bytes(header), manifest[:96])

    def test_an_unknown_device_has_no_settings(self):
        self.assertIsNone(read_device_settings(bytes(96)))

    def test_a_page_is_the_screen_turned_as_the_project_is(self):
        model = model_named("NX4832T035")
        for rotation, size in ((0, (320, 480)), (90, (480, 320)), (180, (320, 480)),
                               (270, (480, 320))):
            with self.subTest(rotation=rotation):
                self.assertEqual(DeviceSettings(model, rotation, "iso-8859-1").page_size, size)

    def test_a_series_that_is_not_the_models_is_refused(self):
        header = bytearray(manifest_of("NX8048P050")[:96])
        header[11] = 0
        with self.assertRaisesRegex(NxwrightError, "names NX8048P050 but series 0"):
            read_device_settings(bytes(header))


if __name__ == "__main__":
    unittest.main()
