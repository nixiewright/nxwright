"""The picture cache: screen copies kept between builds, and used only while
everything that made them is unchanged."""
import ast
import contextlib
import importlib.util
import io
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest import mock

import PIL

from nxwright.project import picture_cache
from nxwright.project.device_settings import DeviceSettings
from nxwright.project.dumper import ProjectDumper
from nxwright.project.new_project import write_new_project
from nxwright.project.picture_cache import (ENCODER_MODULES, FILE_NAME, PictureCache,
                                            make_screen_copy, opened_cache)
from nxwright.project.screen_copy import FORMAT_COMPRESSED, FORMAT_RAW
from nxwright.project.screen_models import model_named
from tests.test_project_writer import WriterTestCase, sample_png, write_small_project

PNG = sample_png("compressed/23-alpha-ramp-unique-16x4")
OTHER_PNG = sample_png("compressed/12-dot-top-right-8x8")


class CacheTestCase(unittest.TestCase):
    """A cache folder of its own, named by NXWRIGHT_CACHE."""

    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.addCleanup(self._folder.cleanup)
        self.folder = Path(self._folder.name)
        self.cache_folder = self.folder / "cache"
        patch = mock.patch.dict(os.environ, {"NXWRIGHT_CACHE": str(self.cache_folder)})
        patch.start()
        self.addCleanup(patch.stop)

    def open(self, fingerprint: str = "f") -> PictureCache:
        self.cache_folder.mkdir(exist_ok=True)
        cache = PictureCache(self.cache_folder / FILE_NAME, fingerprint)
        self.addCleanup(cache.close)
        return cache

    def stored(self, png: bytes = PNG, kind: int = FORMAT_COMPRESSED, rotation: int = 0,
               fingerprint: str = "f"):
        """Stores the screen copy of `png` in a fresh connection, and returns it."""
        cache = self.open(fingerprint)
        made = make_screen_copy(png, kind, rotation, cache)
        cache.save()
        return made


class LookupTest(CacheTestCase):

    def test_a_stored_screen_copy_is_found(self):
        made = self.stored()
        found = self.open().get(PNG, FORMAT_COMPRESSED, 0)
        self.assertEqual((found.width, found.height, found.block, found.pixels),
                         (made.width, made.height, made.block, None))

    def test_any_change_misses(self):
        self.stored()
        cache = self.open()
        self.assertIsNone(cache.get(OTHER_PNG, FORMAT_COMPRESSED, 0))
        self.assertIsNone(cache.get(PNG, FORMAT_RAW, 0))
        self.assertIsNone(cache.get(PNG, FORMAT_COMPRESSED, 180))
        self.assertIsNone(self.open("another encoder").get(PNG, FORMAT_COMPRESSED, 0))

    def test_a_damaged_entry_is_not_used(self):
        self.stored()
        with sqlite3.connect(self.cache_folder / FILE_NAME) as connection:
            connection.execute("UPDATE screen_copies SET block = x'00'")
        connection.close()
        self.assertIsNone(self.open().get(PNG, FORMAT_COMPRESSED, 0))

    def test_the_fingerprint_is_the_running_codes(self):
        # A source file changed while the process runs does not describe its code.
        with mock.patch.object(picture_cache, "encoder_fingerprint",
                               return_value="changed on disk"), opened_cache() as cache:
            self.assertEqual(cache.fingerprint, picture_cache._FINGERPRINT)

    def test_a_failed_read_warns_once_and_misses(self):
        self.stored()
        cache = self.open()
        cache._connection.close()
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors):
            self.assertIsNone(cache.get(PNG, FORMAT_COMPRESSED, 0))
            self.assertIsNone(cache.get(PNG, FORMAT_COMPRESSED, 0))
        self.assertEqual(errors.getvalue().count("cannot be read"), 1)

    def test_the_cache_keeps_under_its_size(self):
        self.stored(PNG)
        self.stored(OTHER_PNG)
        cache = self.open()
        newest = cache.get(OTHER_PNG, FORMAT_COMPRESSED, 0).block
        cache._keep_under(cache.size() - 1, len(newest) + 1)
        self.assertEqual(cache.size(), len(newest))
        self.assertIsNone(cache.get(PNG, FORMAT_COMPRESSED, 0))


class BuildTest(CacheTestCase):
    """Writing a project anew, through the cache."""

    def setUp(self):
        super().setUp()
        self.dump = self.folder / "dump"
        ProjectDumper(write_small_project(self.folder), self.dump).dump()
        self.settings = DeviceSettings(model_named("NX8048P050"), 90, "utf-8")

    def build(self, name: str) -> tuple:
        """Builds the dump, and returns the project's bytes and what was warned."""
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors):
            write_new_project(self.dump, self.settings, self.folder / name)
        return (self.folder / name).read_bytes(), errors.getvalue()

    def test_empty_and_full_caches_build_the_same(self):
        empty, _ = self.build("empty.HMI")
        with mock.patch("nxwright.project.picture_cache.read_picture",
                        side_effect=AssertionError("encoded again")):
            full, _ = self.build("full.HMI")
        self.assertEqual(full, empty)
        with mock.patch.dict(os.environ, {"NXWRIGHT_CACHE": "off"}):
            self.assertEqual(self.build("none.HMI")[0], empty)

    def test_off_keeps_no_file(self):
        with mock.patch.dict(os.environ, {"NXWRIGHT_CACHE": "Off"}):
            self.build("none.HMI")
        self.assertFalse(self.cache_folder.exists())

    def test_an_unreadable_cache_warns_and_builds(self):
        self.cache_folder.mkdir()
        (self.cache_folder / FILE_NAME).write_bytes(b"not a database, but long enough" * 10)
        data, warned = self.build("warned.HMI")
        self.assertIn("the picture cache cannot be opened", warned)
        with mock.patch.dict(os.environ, {"NXWRIGHT_CACHE": "off"}):
            self.assertEqual(self.build("none.HMI")[0], data)

    def test_a_failed_save_warns_and_builds(self):
        with mock.patch.object(PictureCache, "save", side_effect=sqlite3.OperationalError("full")):
            data, warned = self.build("unsaved.HMI")
        self.assertIn("cannot be written (full)", warned)
        self.assertTrue(data)

    def test_a_failed_build_still_raises(self):
        with mock.patch("nxwright.project.new_project.copied_contents",
                        side_effect=OSError("disk gone")), self.assertRaises(OSError):
            self.build("failed.HMI")

    def test_no_source_turns_the_cache_off(self):
        with mock.patch.object(picture_cache, "_FINGERPRINT", None):
            self.build("none.HMI")
        self.assertFalse(self.cache_folder.exists())


class WriterTest(CacheTestCase, WriterTestCase):
    """Adding a picture to an existing project, through the cache."""

    def setUp(self):
        CacheTestCase.setUp(self)
        WriterTestCase.setUp(self)
        self.addCleanup(WriterTestCase.tearDown, self)

    def tearDown(self):
        pass

    def test_a_cached_screen_copy_is_written_and_checked(self):
        (self.dump / "images" / "0002.png").write_bytes(PNG)
        self.write()
        made_now = self.output.read_bytes()
        self.output.unlink()
        with mock.patch("nxwright.project.picture_cache.read_picture",
                        side_effect=AssertionError("encoded again")):
            self.write()
        self.assertEqual(self.output.read_bytes(), made_now)


class FingerprintTest(unittest.TestCase):

    def test_it_covers_every_nxwright_module_the_encoder_imports(self):
        listed = {module.__name__ for module in ENCODER_MODULES}
        for module in ENCODER_MODULES:
            tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
            for imported in _nxwright_imports(tree):
                self.assertIn(imported, listed, "%s imports %s" % (module.__name__, imported))

    def test_a_change_to_the_encoder_changes_it(self):
        before = picture_cache.encoder_fingerprint()
        with mock.patch.object(Path, "read_bytes", return_value=b"changed"):
            self.assertNotEqual(picture_cache.encoder_fingerprint(), before)

    def test_another_pillow_changes_it(self):
        before = picture_cache.encoder_fingerprint()
        with mock.patch.object(PIL, "__version__", "0.0.0"):
            self.assertNotEqual(picture_cache.encoder_fingerprint(), before)


def _nxwright_imports(tree: ast.AST) -> set:
    """Returns the nxwright modules a module's code imports. `from p import m`
    imports the module p.m when there is one, and p otherwise."""
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                name = "%s.%s" % (node.module, alias.name)
                found.add(name if importlib.util.find_spec(node.module) and _is_module(name)
                          else node.module)
    return {name for name in found if name == "nxwright" or name.startswith("nxwright.")}


def _is_module(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except ModuleNotFoundError:
        return False


if __name__ == "__main__":
    unittest.main()
