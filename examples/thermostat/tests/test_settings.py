"""The settings page: the unit, the brightness, and setting the clock."""
import unittest

from screen import SCREEN, picture

WHITE, MUTED = 61342, 36020


def run(events: list, values: dict = None) -> dict:
    return SCREEN.run("settings", events, dict({"rtc3": 7, "rtc4": 0, "dim": 80}, **(values or {})))


class LoadTest(unittest.TestCase):

    def test_shows_the_settings(self):
        values = run([("settings", "load")])
        self.assertEqual((values["brightness.val"], values["brightnessText.txt"]), (80, "80%"))
        self.assertEqual(values["setTime.txt"], "07:00")
        self.assertEqual((values["celsius.picc"], values["celsius.pco"]),
                         (picture("settings/pressed"), WHITE))
        self.assertEqual((values["fahrenheit.picc"], values["fahrenheit.pco"]),
                         (picture("settings/normal"), MUTED))


class UnitTest(unittest.TestCase):

    def test_choosing_fahrenheit_then_celsius(self):
        values = run([("fahrenheit", "up")])
        self.assertEqual(values["unit"], 1)
        self.assertEqual(values["fahrenheit.picc"], picture("settings/pressed"))
        self.assertEqual(values["celsius.picc"], picture("settings/normal"))
        self.assertEqual(run([("celsius", "up")], {"unit": 1})["unit"], 0)


class BrightnessTest(unittest.TestCase):

    def test_the_slider_dims_the_screen(self):
        values = run([("brightness", "slide")], {"brightness.val": 40})
        self.assertEqual((values["dim"], values["brightnessText.txt"]), (40, "40%"))

    def test_a_press_on_the_slider_dims_the_screen_at_once(self):
        # A press away from the knob moves it there, then runs the press's event.
        values = run([("brightness", "down")], {"brightness.val": 30})
        self.assertEqual((values["dim"], values["brightnessText.txt"]), (30, "30%"))


class ClockTest(unittest.TestCase):

    def test_hours_and_minutes_wrap_around_midnight(self):
        for button, hour, minute, shown in (("hourUp", 23, 30, "00:30"), ("hourDown", 0, 15, "23:15"),
                                            ("minuteUp", 23, 59, "00:00"), ("minuteDown", 0, 0, "23:59"),
                                            ("minuteUp", 9, 59, "10:00")):
            with self.subTest(button=button, hour=hour, minute=minute):
                values = run([(button, "up")], {"rtc3": hour, "rtc4": minute, "rtc5": 42})
                self.assertEqual((values["setTime.txt"], values["clock.txt"]), (shown, shown))
                self.assertEqual((values["rtc3"], values["rtc4"], values["rtc5"]),
                                 (int(shown[:2]), int(shown[3:]), 0))


if __name__ == "__main__":
    unittest.main()
