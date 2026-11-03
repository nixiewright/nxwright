"""The orientation of the fonts nxwright makes (DeviceSettings.font_rotation):
the one a compiled file keeps fonts in, 0 degrees on the F series and the
folder's rotation on the others, so that no compile needs to turn them. The
Nextion Editor 1.68.2 saves a font so as it turns a project, and takes a
font in any orientation (ResearchNotes/format.md, Fonts).
"""
from pathlib import Path
import tempfile
import unittest

from nxwright.project.device_settings import DeviceSettings
from nxwright.project.screen_models import model_named
from nxwright.project.truetype import NOTO_SANS
from nxwright.project.zi_font import font_facts, turned_font
from nxwright.source.keyboard_adding import add_keyboard
from nxwright.source.keyboards import CHINESE_INPUT
from nxwright.source.resource_adding import add_font, add_font_file
from nxwright.source.source_folder import new_source_folder
from tests.test_chinese_keyboard import MEI, characters, chinese_typeface

# A font the generator drew, upright.
GENERATORS = Path(__file__).parent / "fixtures" / "fonts" / "NotoSans20.zi"
# Each screen probed, and the orientation a compiled file keeps fonts in at
# 270 degrees.
SCREENS = (("NX4832F035", 0), ("NX4832T035", 270))


class FontOrientationTest(unittest.TestCase):

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.temp = Path(temporary.name)

    def folder(self, model: str, encoding: str = "iso-8859-1") -> Path:
        """A new source folder of `model` at 270 degrees, of a name of its own."""
        folder = self.temp / ("%s-%s-%d" % (model, encoding, len(list(self.temp.iterdir()))))
        new_source_folder(folder, DeviceSettings(model_named(model), 270, encoding), "nextion")
        return folder

    def rotation(self, folder: Path, name: str) -> int:
        return font_facts((folder / "fonts" / (name + ".zi")).read_bytes()).rotation

    def test_the_orientation_of_each_series(self):
        for model, series in (("NX4832T035", "T"), ("NX4832K035", "K"), ("NX4832F035", "F"),
                              ("NX8048P050", "P"), ("NX4848E040", "E")):
            for rotation in (0, 90, 180, 270):
                with self.subTest(series=series, rotation=rotation):
                    settings = DeviceSettings(model_named(model), rotation, "iso-8859-1")
                    self.assertEqual(settings.font_rotation, 0 if series == "F" else rotation)

    def test_a_new_folder_s_font(self):
        for model, kept in SCREENS:
            with self.subTest(model=model):
                self.assertEqual(self.rotation(self.folder(model), "NotoSans24"), kept)

    def test_a_drawn_font(self):
        for model, kept in SCREENS:
            with self.subTest(model=model):
                folder = self.folder(model)
                add_font(folder, NOTO_SANS, 16)
                self.assertEqual(self.rotation(folder, "NotoSans16"), kept)

    def test_a_ready_made_font(self):
        # Copied as it is in that orientation, else turned to it.
        upright = GENERATORS.read_bytes()
        for model, kept in SCREENS:
            for given in (0, 270):
                with self.subTest(model=model, given=given):
                    folder = self.folder(model)
                    font = self.temp / ("given-%d.zi" % given)
                    font.write_bytes(turned_font(upright, given) if given else upright)
                    name, _ = add_font_file(folder, font, "Given")
                    block = (folder / "fonts" / "Given.zi").read_bytes()
                    if given == kept:
                        self.assertEqual(block, font.read_bytes())
                    else:
                        self.assertEqual(block, turned_font(font.read_bytes(), kept))

    def test_a_keyboard_s_font(self):
        for model, kept in SCREENS:
            with self.subTest(model=model):
                folder = self.folder(model)
                _, font, _ = add_keyboard(folder, "keyboard")
                self.assertEqual(self.rotation(folder, font), kept)

    def test_a_chinese_keyboard_s_font(self):
        typeface = self.temp / "hanzi.ttf"
        typeface.write_bytes(chinese_typeface("".join(characters(MEI))))
        for model, kept in SCREENS:
            with self.subTest(model=model):
                folder = self.folder(model, "gb2312")
                _, font, _ = add_keyboard(folder, CHINESE_INPUT, typeface=typeface)
                self.assertEqual(self.rotation(folder, font), kept)


if __name__ == "__main__":
    unittest.main()
