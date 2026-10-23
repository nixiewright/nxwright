"""The schedule page: the four periods, selecting one, and changing it."""
import unittest

from screen import SCREEN, picture

WHITE, MUTED = 61342, 36020
NAMES = ("wake", "away", "home", "sleep")


def run(events: list, values: dict = None) -> dict:
    return SCREEN.run("schedule", events, dict({"rtc3": 7, "rtc4": 0}, **(values or {})))


class LoadTest(unittest.TestCase):

    def test_shows_each_period(self):
        values = run([("schedule", "load")])
        self.assertEqual([(values[name + "Time.txt"], values[name + "Temp.txt"])
                          for name in NAMES],
                         [("06:30", "21.0°"), ("08:30", "17.0°"), ("17:30", "21.5°"),
                          ("22:30", "18.0°")])

    def test_marks_the_selected_period(self):
        values = run([("schedule", "load")], {"selectedPeriod": 2})
        for i, name in enumerate(NAMES):
            with self.subTest(period=name):
                selected = i == 2
                self.assertEqual(values[name + "Marker.pic"],
                                 picture("marker/on" if selected else "marker/off"))
                self.assertEqual(values[name + "Name.pco"], WHITE if selected else MUTED)
        self.assertEqual((values["selectedName.txt"], values["startText.txt"], values["targetText.txt"]),
                         ("Home", "17:30", "21.5°"))


class EditTest(unittest.TestCase):

    def test_touching_a_period_selects_it(self):
        values = run([("awayRow", "up")])
        self.assertEqual(values["selectedPeriod"], 1)
        self.assertEqual((values["selectedName.txt"], values["startText.txt"]), ("Away", "08:30"))
        self.assertEqual(values["awayMarker.pic"], picture("marker/on"))

    def test_moving_the_selected_start(self):
        values = run([("awayRow", "up"), ("earlier", "up")])
        self.assertEqual(values["awayStart"], 495)
        self.assertEqual((values["awayTime.txt"], values["startText.txt"]), ("08:15", "08:15"))
        values = run([("later", "up")], {"selectedPeriod": 3})
        self.assertEqual(values["sleepTime.txt"], "22:45")

    def test_changing_the_selected_target(self):
        values = run([("warmer", "up")], {"selectedPeriod": 3})
        self.assertEqual(values["sleepTarget"], 1850)
        self.assertEqual((values["sleepTemp.txt"], values["targetText.txt"]), ("18.5°", "18.5°"))
        self.assertEqual(run([("cooler", "up")])["wakeTarget"], 2050)


if __name__ == "__main__":
    unittest.main()
