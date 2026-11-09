"""The About page, opened from the settings page: its background is an SVG
picture, and its logo a PNG picture."""
import tomllib
import unittest

from screen import APP, SCREEN


class AboutTest(unittest.TestCase):

    def test_the_about_card_opens_the_page_and_back_returns(self):
        values = SCREEN.run("settings", [("aboutCard", "up")], {"rtc3": 7, "rtc4": 0, "dim": 80})
        self.assertEqual(values["page opened"], "about")
        self.assertEqual(SCREEN.run("about", [("back", "up")])["page opened"], "settings")

    def test_the_page_shows_an_svg_picture_and_a_png_picture(self):
        with open(APP / "pages" / "about.page.toml", "rb") as file:
            tables = tomllib.load(file)
        logo = next(table for table in tables["component"] if table["name"] == "logo")
        self.assertEqual((tables["page"]["pic"], logo["pic"]), ("about/normal", "nxwright"))
        self.assertTrue((APP / "pictures" / "about" / "normal.svg").is_file())
        self.assertTrue((APP / "pictures" / "nxwright.png").is_file())
