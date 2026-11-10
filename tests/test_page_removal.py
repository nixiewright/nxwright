"""Deleting a page with `nxwright remove <folder> page`, its report, and the
empty slot page that `--keep-ids` leaves (source/page_removal.py). Also
writing a page's number as the page's name (source/resource_numbers.py)."""
import contextlib
import io
import json
import shutil
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest import mock

from nxwright import NxwrightError
from nxwright.cli import main
from nxwright.project.device_settings import DeviceSettings
from nxwright.project.screen_models import model_named
from nxwright.source.folder_check import check_folder
from nxwright.source.folder_index import FolderIndex, text_on_disk
from nxwright.source.page_removal import (page_removal_report, page_uses, remove_page,
                                          remove_page_keeping_ids)
from nxwright.source.resource_numbers import (page_number_as_name, page_numbers,
                                              placed_page_numbers)
from nxwright.source.source_folder import (add_page, folder_reader, new_source_folder,
                                           read_folder_source)


class PageRemovalTest(unittest.TestCase):
    """A folder of three pages, page0, second, and third. A test that needs
    code using the other pages writes it into page0's load event with `code`."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.source = Path(temporary.name) / "app"
        new_source_folder(self.source, DeviceSettings(model_named("NX4832T035"), 0,
                                                      "iso-8859-1"), "nxlang")
        add_page(self.source, "second")
        add_page(self.source, "third")

    def code(self, *lines: str):
        """Writes `lines` as page0's load event."""
        (self.source / "pages/page0.nx").write_text(
            "on page0.load:\n" + "".join("  %s\n" % line for line in lines), encoding="utf-8")

    def files(self, source: Path = None) -> dict:
        source = source or self.source
        return {str(path.relative_to(source)): path.read_bytes()
                for path in source.rglob("*") if path.is_file()}

    def pages(self) -> list:
        return tomllib.loads((self.source / "app.toml").read_text(encoding="utf-8"))["pages"]

    def builds(self) -> bool:
        return not check_folder(folder_reader(self.source),
                                lambda path: (self.source / path).exists()).errors()

    def test_page_numbers_in_a_line(self):
        self.assertEqual(page_numbers("page 2"), [2])
        self.assertEqual(page_numbers("page second"), [])
        self.assertEqual(page_numbers("dp=1"), [1])
        self.assertEqual(page_numbers("if(dp==1&&sys0==0)"), [1])
        self.assertEqual(page_numbers("if(2!=dp)"), [2])
        # Neither a quoted text nor dp read into a variable gives a page.
        self.assertEqual(page_numbers('t0.txt="dp=1"'), [])
        self.assertEqual(page_numbers("sys0=dp"), [])

    def test_a_page_nothing_uses_is_deleted(self):
        written = remove_page(self.source, "second")
        self.assertEqual(written, (["pages/second.page.toml", "pages/second.nx"], []))
        self.assertEqual(self.pages(), ["page0", "third"])
        self.assertFalse((self.source / "pages/second.page.toml").exists())
        self.assertTrue(self.builds())

    def test_uses_by_name_and_by_number(self):
        self.code("page second", "page 2", "dp=1")
        _, uses = page_uses(self.source, "second")
        self.assertEqual([(use.line, use.text, use.by, use.of) for use in uses],
                         [(2, "page second", "name", "itself"),
                          (3, "page 2", "number", "later"),
                          (4, "dp=1", "number", "itself")])
        # page0's ID is before second's, so `page 0` would not be a use.
        self.code("page 0")
        self.assertEqual(page_uses(self.source, "second")[1], [])

    def test_a_page_in_use_is_deleted_without_a_search(self):
        self.code("page second")
        with mock.patch("nxwright.source.page_removal.check_folder",
                        side_effect=AssertionError("the folder was checked")), \
                mock.patch("nxwright.source.page_removal.references",
                           side_effect=AssertionError("the uses were searched")):
            written = remove_page(self.source, "second")
        self.assertEqual(written, (["pages/second.page.toml", "pages/second.nx"], []))
        self.assertEqual(self.pages(), ["page0", "third"])
        # The use is left as it was, so the folder no longer builds.
        self.assertIn("page second", (self.source / "pages/page0.nx").read_text(
            encoding="utf-8"))
        self.assertFalse(self.builds())

    def test_a_checked_deletion_writes_the_same_files(self):
        for remove in (remove_page, remove_page_keeping_ids):
            with self.subTest(remove=remove.__name__):
                checked = self.source.with_name("checked-" + remove.__name__)
                plain = self.source.with_name("plain-" + remove.__name__)
                shutil.copytree(self.source, checked)
                shutil.copytree(self.source, plain)
                self.assertEqual(remove(checked, "second", checked=True),
                                 remove(plain, "second"))
                self.assertEqual(self.files(checked), self.files(plain))

    def test_a_page_in_use_stays_when_checked(self):
        self.code("page second")
        before = self.files()
        with self.assertRaisesRegex(NxwrightError, "the page second is used, so it stays:\n"
                                                   "  pages/page0.nx line 2: page second"):
            remove_page(self.source, "second", checked=True)
        self.assertEqual(self.files(), before)

    def test_a_later_page_used_by_number_needs_keep_ids(self):
        self.code("page 2")
        with self.assertRaisesRegex(NxwrightError, "page 2"):
            remove_page(self.source, "second", checked=True)
        name, deleted, left = remove_page_keeping_ids(self.source, "second", checked=True)
        self.assertEqual((name, deleted, left),
                         ("empty_slot_1", ["pages/second.page.toml", "pages/second.nx"], []))
        self.assertEqual(self.pages(), ["page0", "empty_slot_1", "third"])
        self.assertIn('name = "empty_slot_1"',
                      (self.source / "pages/empty_slot_1.page.toml").read_text(encoding="utf-8"))
        self.assertTrue(self.builds())
        # The next empty slot page takes the next number.
        self.code()
        self.assertEqual(remove_page_keeping_ids(self.source, "third")[0], "empty_slot_2")

    def test_an_empty_slot_page_is_not_replaced_by_another(self):
        remove_page_keeping_ids(self.source, "second")
        before = self.files()
        with self.assertRaisesRegex(NxwrightError, "empty_slot_1 is an empty slot page already"):
            remove_page_keeping_ids(self.source, "empty_slot_1")
        self.assertEqual(self.files(), before)

    def test_a_shared_file_counts_for_the_other_pages_that_include_it(self):
        (self.source / "pages/lib").mkdir()
        (self.source / "pages/lib/shared.nx").write_text("function go():\n  page 2\n",
                                                         encoding="utf-8")
        (self.source / "pages/second.nx").write_text(
            'include "lib/shared.nx"\n\non second.load:\n  go()\n', encoding="utf-8")
        # While only second includes the shared file, its `page 2` is not a use.
        self.assertEqual(page_uses(self.source, "second")[1], [])
        (self.source / "pages/page0.nx").write_text(
            'include "lib/shared.nx"\n\non page0.load:\n  go()\n', encoding="utf-8")
        [use] = page_uses(self.source, "second")[1]
        self.assertEqual((use.path, use.text, use.of), ("pages/lib/shared.nx", "page 2", "later"))
        self.code()
        remove_page(self.source, "second", checked=True)
        self.assertTrue((self.source / "pages/lib/shared.nx").exists())
        self.assertTrue(self.builds())

    def test_an_empty_slot_page_takes_a_name_no_object_has(self):
        third = self.source / "pages/third.page.toml"
        third.write_text(third.read_text(encoding="utf-8")
                         + '\n[[component]]\nname = "empty_slot_1"\ntype = "variable"\n',
                         encoding="utf-8")
        self.assertTrue(self.builds())
        self.assertEqual(remove_page_keeping_ids(self.source, "second")[0], "empty_slot_2")
        self.assertTrue(self.builds())

    def test_keeping_the_ids_still_refuses_a_use_of_the_page_itself_when_checked(self):
        self.code("dp=1")
        with self.assertRaisesRegex(NxwrightError, "dp=1"):
            remove_page_keeping_ids(self.source, "second", checked=True)
        self.assertEqual(remove_page_keeping_ids(self.source, "second")[0], "empty_slot_1")

    def test_the_only_page_stays(self):
        remove_page(self.source, "second")
        remove_page(self.source, "third")
        for remove in (remove_page, remove_page_keeping_ids, page_removal_report):
            with self.assertRaisesRegex(NxwrightError, "the folder's only page"):
                remove(self.source, "page0")
        for remove in (remove_page, remove_page_keeping_ids):
            with self.assertRaisesRegex(NxwrightError, "the folder's only page"):
                remove(self.source, "page0", checked=True)

    def test_a_page_the_folder_lacks(self):
        for checked in (False, True):
            with self.assertRaisesRegex(NxwrightError, "the folder has no page named fourth"):
                remove_page(self.source, "fourth", checked=checked)

    def test_a_checked_deletion_the_checks_reject_afterwards_writes_nothing(self):
        before = self.files()
        error = mock.Mock(place="x", message="y")
        with mock.patch("nxwright.source.page_removal.check_folder",
                        side_effect=[mock.Mock(errors=lambda: []),
                                     mock.Mock(errors=lambda: [error])]):
            with self.assertRaisesRegex(NxwrightError, "would not build after the deletion"):
                remove_page(self.source, "second", checked=True)
        self.assertEqual(self.files(), before)

    def test_the_report(self):
        self.code("page 2")
        report = page_removal_report(self.source, "second")
        self.assertEqual({key: report[key] for key in ("kind", "name", "id", "last", "later")},
                         {"kind": "page", "name": "second", "id": 1, "last": False,
                          "later": ["third"]})
        self.assertEqual([(use["text"], use["by"], use["of"]) for use in report["uses"]],
                         [("page 2", "number", "later")])

    def test_page_numbers_written_as_names(self):
        self.code("page 2", "dp=1", "page 2")
        index = FolderIndex(self.source, text_on_disk)
        folder = read_folder_source(folder_reader(self.source))
        placed = placed_page_numbers(folder, index, "pages/page0.nx")
        # Each `page 2` is placed, on its own line, but the number given to dp is not.
        self.assertEqual([(number.place.line, number.place.start, number.id) for number in placed],
                         [(1, 7, 2), (3, 7, 2)])
        self.assertEqual(page_number_as_name(folder, placed[0]), "third")

    def test_the_command_line(self):
        self.code("page 2")
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            self.assertEqual(main(["remove", str(self.source), "page", "second", "--report"]), 0)
        self.assertEqual(json.loads(printed.getvalue())["later"], ["third"])
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors):
            self.assertEqual(main(["remove", str(self.source), "page", "second", "--checked"]),
                             1)
        self.assertIn("pages/page0.nx line 2: page 2", errors.getvalue())
        printed = io.StringIO()
        with contextlib.redirect_stdout(printed):
            self.assertEqual(main(["remove", str(self.source), "page", "second", "--keep-ids"]),
                             0)
        self.assertIn("with the empty slot page empty_slot_1", printed.getvalue())
        # Without --checked, the page is deleted though page0's code gives its ID as a number.
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["remove", str(self.source), "page", "third"]), 0)
        self.assertEqual(self.pages(), ["page0", "empty_slot_1"])


if __name__ == "__main__":
    unittest.main()
