"""The Editor's list of screen models (tools/editor/model_list.py): a model
read from the text of its tile in the device settings."""
import unittest

from tools.editor.model_list import listed_model


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


if __name__ == "__main__":
    unittest.main()
