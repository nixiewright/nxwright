"""The day page: the scale's labels, and the chart of a day under the schedule."""
import unittest

from screen import SCREEN

CHART = 21     # any ID: the chart's commands name it


def draw(values: dict = None) -> dict:
    return SCREEN.run("day", [("day", "loadend")], dict({"chart.id": CHART}, **(values or {})))


def channel(values: dict, number: int) -> list:
    """The points added to one channel, a quarter hour every 7 of them."""
    return [command[3] for command in values["waveform"]
            if command[0] == "add" and command[2] == number][::7]


class LabelTest(unittest.TestCase):

    def test_the_scale_in_the_chosen_unit(self):
        for unit, labels in ((0, ["10°", "15°", "20°", "25°", "30°"]),
                             (1, ["50°", "59°", "68°", "77°", "86°"])):
            with self.subTest(unit=unit):
                values = SCREEN.run("day", [("day", "load")], {"unit": unit, "rtc3": 7, "rtc4": 0})
                self.assertEqual([values["label%d.txt" % degrees] for degrees in (10, 15, 20, 25, 30)],
                                 labels)


class ChartTest(unittest.TestCase):

    def test_clears_then_draws_a_day_of_quarter_hours(self):
        commands = draw()["waveform"]
        self.assertEqual(commands[0], ("cle", CHART, 255))
        self.assertEqual(len(commands), 1 + 96 * 7 * 2)
        # Midnight: the Sleep target, 18.0. The room starts there and loses 0.2
        # degrees in each of two 5-minute steps; at 17.6, the gap below the
        # target, heating starts, and the third step ends at 18.15.
        self.assertEqual(commands[1:3], [("add", CHART, 0, 80), ("add", CHART, 1, 81)])

    def test_the_target_follows_the_schedule(self):
        # A pixel per tenth of a degree above 10: 18.0 is 80, 21.0 is 110.
        targets = channel(draw(), 0)
        self.assertEqual([targets[quarter] for quarter in (0, 25, 26, 33, 34, 69, 70, 89, 90)],
                         [80, 80, 110, 110, 70, 70, 115, 115, 80])

    def test_heating_brings_the_room_to_the_evening_target(self):
        rooms = channel(draw(), 1)
        self.assertTrue(all(0 <= room <= 200 for room in rooms))
        # By 20:00 the room is around the Home target, 21.5. It may be up to half
        # a degree over: heating stops only at the end of a 5-minute step.
        self.assertTrue(110 <= rooms[80] <= 120, rooms[80])

    def test_cooling_brings_the_room_to_the_evening_target(self):
        # A hot day warms the room; cooling holds it to the target. By 20:00 it
        # is around the Home target, 21.5. It may be up to half a degree under:
        # cooling stops only at the end of a 5-minute step.
        rooms = channel(draw({"mode": 2}), 1)
        self.assertTrue(110 <= rooms[80] <= 120, rooms[80])
        self.assertTrue(all(65 <= room <= 120 for room in rooms), rooms)

    def test_off_the_room_only_cools(self):
        rooms = channel(draw({"mode": 0}), 1)
        self.assertEqual(rooms, sorted(rooms, reverse=True))
        self.assertLess(rooms[-1], rooms[0])

    def test_the_lowest_and_highest_temperatures(self):
        stats = draw()["stats.txt"]
        self.assertRegex(stats, r"^Low \d+\.\d°    High \d+\.\d°$")


if __name__ == "__main__":
    unittest.main()
