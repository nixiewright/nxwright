"""The shared functions of pages/lib/, each run on its own."""
import unittest

from screen import SCREEN

# The constants of pages/lib/constants.nx the tests name.
MODE_OFF, MODE_HEAT, MODE_COOL = 0, 1, 2
RUN_IDLE, RUN_HEATING, RUN_COOLING = 0, 1, 2


def text_of(code: str, include: str, values: dict = None) -> str:
    """Runs `code`, which sets r.txt, and returns r.txt."""
    return SCREEN.run_code(code, dict({"r.txt": ""}, **(values or {})), include)["r.txt"]


def number_of(code: str, include: str, values: dict = None) -> int:
    """Runs `code`, which sets r.val, and returns r.val."""
    return SCREEN.run_code(code, dict({"r.val": 0}, **(values or {})), include)["r.val"]


class TemperatureTextTest(unittest.TestCase):

    def test_celsius_to_the_nearest_tenth(self):
        for hundredths, shown in ((2150, "21.5°"), (2104, "21.0°"), (2105, "21.1°"),
                                  (0, "0.0°"), (-4, "0.0°"), (-5, "-0.1°"), (-150, "-1.5°")):
            with self.subTest(hundredths=hundredths):
                self.assertEqual(text_of("r.txt = temperatureText(%d)" % hundredths, "lib/text.nx"),
                                 shown)

    def test_fahrenheit(self):
        for hundredths, shown in ((2150, "70.7°"), (0, "32.0°"), (1000, "50.0°"), (-2000, "-4.0°")):
            with self.subTest(hundredths=hundredths):
                self.assertEqual(text_of("r.txt = temperatureText(%d)" % hundredths, "lib/text.nx",
                                         {"unit": 1}), shown)


class WholeDegreesTextTest(unittest.TestCase):

    def test_rounded_in_the_chosen_unit(self):
        for hundredths, unit, shown in ((2000, 0, "20°"), (2049, 0, "20°"), (2050, 0, "21°"),
                                        (2000, 1, "68°"), (1500, 1, "59°"), (3000, 1, "86°")):
            with self.subTest(hundredths=hundredths, unit=unit):
                self.assertEqual(text_of("r.txt = wholeDegreesText(%d)" % hundredths, "lib/text.nx",
                                         {"unit": unit}), shown)


class TimeTextTest(unittest.TestCase):

    def test_hours_and_minutes_with_two_digits(self):
        for minutes, shown in ((0, "00:00"), (390, "06:30"), (605, "10:05"), (1439, "23:59")):
            with self.subTest(minutes=minutes):
                self.assertEqual(text_of("r.txt = timeText(%d)" % minutes, "lib/text.nx"), shown)


class ClampTest(unittest.TestCase):

    def test_keeps_a_value_within_limits(self):
        for value, kept in ((5, 10), (10, 10), (15, 15), (20, 20), (25, 20)):
            with self.subTest(value=value):
                self.assertEqual(number_of("r.val = clamp(%d, 10, 20)" % value, "lib/numbers.nx"),
                                 kept)


class ScheduleTest(unittest.TestCase):

    def test_each_period_runs_from_its_start(self):
        # The default schedule: Wake 06:30, Away 08:30, Home 17:30, Sleep 22:30.
        for minute, target in ((0, 1800), (389, 1800), (390, 2100), (509, 2100), (510, 1700),
                               (1049, 1700), (1050, 2150), (1349, 2150), (1350, 1800),
                               (1439, 1800)):
            with self.subTest(minute=minute):
                self.assertEqual(number_of("r.val = scheduledTarget(%d)" % minute,
                                           "lib/schedule.nx"), target)


class SchedulePeriodTest(unittest.TestCase):

    def test_each_period_by_its_number(self):
        for period, start, target in ((0, 390, 2100), (1, 510, 1700), (2, 1050, 2150), (3, 1350, 1800)):
            with self.subTest(period=period):
                self.assertEqual(number_of("r.val = periodStart(%d)" % period, "lib/schedule.nx"), start)
                self.assertEqual(number_of("r.val = periodTarget(%d)" % period, "lib/schedule.nx"),
                                 target)

    def test_a_start_moves_by_the_change(self):
        values = SCREEN.run_code("changeStart(1, -15)", None, "lib/schedule.nx")
        self.assertEqual(values["awayStart"], 495)

    def test_a_start_stays_between_its_neighbours_and_within_the_day(self):
        # Wake 06:30, Away 08:30, Home 17:30, Sleep 22:30; a quarter hour apart at least.
        for period, change, name, start in ((1, -600, "awayStart", 405), (2, 600, "homeStart", 1335),
                                            (0, -600, "wakeStart", 0), (3, 600, "sleepStart", 1425)):
            with self.subTest(period=period, change=change):
                values = SCREEN.run_code("changeStart(%d, %d)" % (period, change), None,
                                         "lib/schedule.nx")
                self.assertEqual(values[name], start)

    def test_a_target_stays_within_its_limits(self):
        values = SCREEN.run_code("changeTarget(0, 50)", None, "lib/schedule.nx")
        self.assertEqual(values["wakeTarget"], 2150)
        values = SCREEN.run_code("changeTarget(3, 5000)", None, "lib/schedule.nx")
        self.assertEqual(values["sleepTarget"], 3000)


class RoomTest(unittest.TestCase):

    def next_running(self, room: int, mode: int, previous: int) -> int:
        return number_of("r.val = nextRunning(%d, 2100, %d, %d)" % (room, mode, previous),
                         "lib/room.nx")

    def test_heating_starts_below_the_gap_and_runs_to_the_target(self):
        for room, previous, running in ((2069, RUN_IDLE, RUN_HEATING),
                                        (2070, RUN_IDLE, RUN_HEATING),
                                        (2071, RUN_IDLE, RUN_IDLE),
                                        (2099, RUN_HEATING, RUN_HEATING),
                                        (2100, RUN_HEATING, RUN_IDLE)):
            with self.subTest(room=room, previous=previous):
                self.assertEqual(self.next_running(room, MODE_HEAT, previous), running)

    def test_cooling_is_the_mirror_image(self):
        for room, previous, running in ((2130, RUN_IDLE, RUN_COOLING),
                                        (2129, RUN_IDLE, RUN_IDLE),
                                        (2101, RUN_COOLING, RUN_COOLING),
                                        (2100, RUN_COOLING, RUN_IDLE)):
            with self.subTest(room=room, previous=previous):
                self.assertEqual(self.next_running(room, MODE_COOL, previous), running)

    def test_nothing_runs_while_off(self):
        self.assertEqual(self.next_running(1000, MODE_OFF, RUN_HEATING), RUN_IDLE)

    def room_after(self, mode: int, state: int) -> int:
        """The room after 12 minutes, from 21.0 degrees."""
        return number_of("r.val = roomAfter(2100, %d, %d, 12)" % (mode, state), "lib/room.nx")

    def test_heat_leaks_out_and_the_system_adds_or_removes_its_share(self):
        # Heating and off: a cold day, 8 degrees outdoors. A twentieth of the
        # 13 degrees to it leaks out in 12 minutes.
        for mode, state, after in ((MODE_OFF, RUN_IDLE, 2100 - 65),
                                   (MODE_HEAT, RUN_IDLE, 2100 - 65),
                                   (MODE_HEAT, RUN_HEATING, 2100 - 65 + 180)):
            with self.subTest(mode=mode, state=state):
                self.assertEqual(self.room_after(mode, state), after)

    def test_cooling_days_are_hot(self):
        # 30 degrees outdoors: a twentieth of the 9 degrees leaks in.
        for state, after in ((RUN_IDLE, 2100 + 45), (RUN_COOLING, 2100 + 45 - 180)):
            with self.subTest(state=state):
                self.assertEqual(self.room_after(MODE_COOL, state), after)


if __name__ == "__main__":
    unittest.main()
