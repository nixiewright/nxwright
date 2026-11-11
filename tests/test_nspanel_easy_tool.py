"""How tools/nspanel_easy.py puts back the fonts that an NSPanel-Easy source
folder lists in its fonts.sha256 file."""
import tempfile
import unittest
from pathlib import Path

from tools.nspanel_easy import restore_fonts

FONT = b"a font's bytes"
FONT_SHA256 = "62942d35702e5af800b2efdf24485b8124e8f68d26572be96b73f6e7a33a208e"


class RestoreFontsTest(unittest.TestCase):

    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        stored = self.root / "stored.zi"
        stored.write_bytes(FONT)
        self.fonts = {FONT_SHA256: stored}
        # The source folder sits two folders down, so that a path which
        # leads out of it still lands inside the temporary folder.
        self.folder = self.root / "work" / "nspanel_blank"
        self.folder.mkdir(parents=True)

    def write_list(self, text):
        (self.folder / "fonts.sha256").write_text(text, encoding="utf-8")

    def test_each_listed_font_is_copied_to_its_place_and_the_list_removed(self):
        self.write_list("%s  fonts/CourierNew16.zi\n\n" % FONT_SHA256)
        restore_fonts(self.folder, self.fonts)
        self.assertEqual((self.folder / "fonts" / "CourierNew16.zi").read_bytes(), FONT)
        self.assertFalse((self.folder / "fonts.sha256").exists())

    def test_a_font_with_no_match_is_refused(self):
        self.write_list("%s  fonts/CourierNew16.zi\n" % ("0" * 64))
        with self.assertRaisesRegex(SystemExit, "no font in hmi/dev/fonts"):
            restore_fonts(self.folder, self.fonts)

    def test_a_path_that_leads_out_of_the_folder_is_refused(self):
        for path in ("../escaped.zi", "fonts/../../escaped.zi", str(self.root / "escaped.zi")):
            with self.subTest(path=path):
                self.write_list("%s  %s\n" % (FONT_SHA256, path))
                with self.assertRaisesRegex(SystemExit, "outside the folder"):
                    restore_fonts(self.folder, self.fonts)
                self.assertEqual(list(self.root.rglob("escaped.zi")), [])
