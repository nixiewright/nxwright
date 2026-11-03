"""The Editor's list of screen models (tools/editor/model_list.py): a model
read from the text of its tile in the device settings."""
import unittest

from tools.editor.model_list import listed_model, models_of


class ListedModelTest(unittest.TestCase):

    def test_a_tile_s_text_gives_the_model(self):
        # As UI Automation gives the tile of the Nextion Editor 1.68.2's
        # NX3224T024, whose name it does not give.
        text = ('<font size="9"><br/><br/>inch:2.4(240X320) Flash:4M RAM:3584B '
                'Frequency:48M</font>')
        self.assertEqual(listed_model("T", text),
                         {"series": "T", "inch": 2.4, "width": 240, "height": 320,
                          "flash": "4M", "ram": "3584B", "frequency": "48M"})

    def test_a_text_of_another_form_is_refused(self):
        with self.assertRaisesRegex(ValueError, "Frequency 48M"):
            listed_model("T", "inch:2.4 Frequency 48M")


T_TILE = "inch:2.4(240X320) Flash:4M RAM:3584B Frequency:48M"
F_TILE = "inch:2.4(240X320) Flash:4M RAM:3584B Frequency:64M"


class ModelsOfTest(unittest.TestCase):

    def test_each_series_gives_its_tiles_models(self):
        self.assertEqual([(model["series"], model["frequency"])
                          for model in models_of([("T", [T_TILE]), ("F", [F_TILE])])],
                         [("T", "48M"), ("F", "64M")])

    def test_a_series_showing_the_tiles_of_the_one_before_is_refused(self):
        # As when its button's press did not take: the series before would
        # be counted twice, under two letters.
        with self.assertRaisesRegex(ValueError, "the button of the F series, the tiles of the "
                                                "T series still showed"):
            models_of([("T", [T_TILE]), ("F", [T_TILE])])


if __name__ == "__main__":
    unittest.main()
