"""Adding pictures to a source folder: add_pictures and `nxwright picture`."""
import contextlib
import io
import tomllib
import unittest

from PIL import Image

from nxwright import NxwrightError
from nxwright.cli import main
from nxwright.source.project_files import build
from nxwright.source.resource_adding import add_pictures
from tests.test_folder_check import FolderTestCase


class AddPicturesTest(FolderTestCase):
    """The folder of FolderTestCase, with pictures to add beside it."""

    def setUp(self):
        super().setUp()
        self.files = self.root.parent / "to add"
        self.files.mkdir()

    def picture(self, name: str, kind: str = "PNG"):
        path = self.files / name
        Image.new("RGB", (8, 4), (200, 30, 30)).save(path, kind)
        return path

    def pictures(self) -> list:
        return tomllib.loads(self.text("app.toml"))["pictures"]

    def test_pictures_are_listed_last_named_after_their_files(self):
        self.assertEqual(add_pictures(self.root, [self.picture("logo.png")]), ["logo"])
        added = add_pictures(self.root, [self.picture("My Icon.jpg", "JPEG"),
                                         self.picture("arrow.PNG")])
        self.assertEqual(added, ["MyIcon", "arrow"])
        self.assertEqual(self.pictures(), ["logo", "MyIcon", "arrow"])
        self.assertEqual((self.root / "pictures/MyIcon.jpg").read_bytes(),
                         (self.files / "My Icon.jpg").read_bytes())
        self.assertTrue((self.root / "pictures/arrow.png").is_file())

    def test_the_folder_still_builds(self):
        add_pictures(self.root, [self.picture("logo.png")])
        build(self.root, self.root.parent / "app.HMI")
        self.assertTrue((self.root.parent / "app.HMI").is_file())

    def assertRefused(self, message: str, files: list):
        before = {path: path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        with self.assertRaises(NxwrightError) as raised:
            add_pictures(self.root, files)
        self.assertIn(message, str(raised.exception))
        after = {path: path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        self.assertEqual(after, before)

    def test_a_file_nxwright_cannot_use_is_refused(self):
        damaged = self.files / "damaged.png"
        damaged.write_bytes(b"not a picture")
        self.assertRefused("damaged.png", [self.picture("good.png"), damaged])
        text = self.files / "notes.txt"
        text.write_text("hello", encoding="utf-8")
        self.assertRefused("notes.txt: a picture is a .png, .jpg, .jpeg, .bmp, or .gif file",
                           [text])

    def test_a_name_the_folder_has_in_another_case_is_refused(self):
        add_pictures(self.root, [self.picture("logo.png")])
        self.assertRefused("the folder has a picture named logo already",
                           [self.picture("Logo.gif", "GIF")])

    def test_two_files_giving_one_name_are_refused(self):
        self.assertRefused("logo.png and logo.bmp would both be named logo",
                           [self.picture("logo.png"), self.picture("logo.bmp", "BMP")])

    def test_a_file_of_the_name_already_there_under_another_suffix_is_refused(self):
        (self.root / "pictures").mkdir(exist_ok=True)
        Image.new("RGB", (8, 4)).save(self.root / "pictures/logo.jpg", "JPEG")
        self.assertRefused("logo.jpg is already there, though app.toml does not list it",
                           [self.picture("logo.png")])

    def test_a_name_with_no_character_a_name_may_have_is_refused(self):
        self.assertRefused("gives no name", [self.picture("###.png")])


class PictureCommandTest(FolderTestCase):

    def test_the_subcommand(self):
        picture = self.root.parent / "logo.png"
        Image.new("RGB", (8, 4)).save(picture, "PNG")
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            self.assertEqual(main(["picture", str(self.root), str(picture)]), 0)
        self.assertIn("Added the picture logo", output.getvalue())
        self.assertTrue((self.root / "pictures/logo.png").is_file())


if __name__ == "__main__":
    unittest.main()
