"""The home page's events, from the state program.nx starts with: the room at
20.5 degrees, a target of 21.0 that follows the schedule, the heat mode, and
nothing running yet."""
import unittest

from screen import SCREEN, picture

# The colours of pages/lib/constants.nx the tests name.
WHITE, MUTED, HEAT, TEAL, GREY = 61342, 36020, 64584, 16054, 31794
# 07:00 on the screen's clock, during the Wake period (21.0 degrees).
SEVEN = {"rtc3": 7, "rtc4": 0}


def run(events: list, values: dict = None) -> dict:
    return SCREEN.run("home", events, dict(SEVEN, **(values or {})))


class LoadTest(unittest.TestCase):

    def test_shows_the_state(self):
        values = run([("home", "load")])
        self.assertEqual(values["clock.txt"], "07:00")
        self.assertEqual(values["roomText.txt"], "20.5°")
        self.assertEqual(values["targetText.txt"], "21.0°")
        self.assertEqual((values["stateText.txt"], values["stateText.pco"]), ("At target", TEAL))
        self.assertEqual(values["stateIcon.pic"], picture("state/idle"))

    def test_the_selected_mode_and_the_switch_show_their_pressed_look(self):
        values = run([("home", "load")])
        self.assertEqual((values["modeHeat.picc"], values["modeHeat.pco"]),
                         (picture("home/pressed"), WHITE))
        for name in ("modeOff", "modeCool"):
            self.assertEqual((values[name + ".picc"], values[name + ".pco"]),
                             (picture("home/normal"), MUTED))
        self.assertEqual(values["follow.picc"], picture("home/pressed"))


class TargetTest(unittest.TestCase):

    def test_raising_holds_the_target(self):
        values = run([("raise", "up")])
        self.assertEqual((values["target"], values["targetText.txt"]), (2150, "21.5°"))
        self.assertEqual(values["following"], 0)
        self.assertEqual(values["follow.picc"], picture("home/normal"))

    def test_lowering(self):
        self.assertEqual(run([("lower", "up")])["target"], 2050)

    def test_the_target_stays_within_its_limits(self):
        self.assertEqual(run([("raise", "up")], {"target": 3000})["target"], 3000)
        self.assertEqual(run([("lower", "up")], {"target": 1000})["target"], 1000)

    def test_the_switch_holds_then_follows_the_schedule_again(self):
        # At 18:00 the Home period (21.5 degrees) runs.
        values = run([("follow", "up")], {"rtc3": 18, "target": 1900})
        self.assertEqual((values["following"], values["target"]), (0, 1900))
        values = run([("follow", "up"), ("follow", "up")], {"rtc3": 18, "target": 1900})
        self.assertEqual((values["following"], values["target"]), (1, 2150))
        self.assertEqual(values["targetText.txt"], "21.5°")
        self.assertEqual(values["follow.picc"], picture("home/pressed"))


class ModeTest(unittest.TestCase):

    def test_choosing_cool(self):
        values = run([("modeCool", "up")])
        self.assertEqual(values["mode"], 2)
        self.assertEqual((values["modeCool.picc"], values["modeCool.pco"]),
                         (picture("home/pressed"), WHITE))
        self.assertEqual(values["modeHeat.picc"], picture("home/normal"))

    def test_off_stops_the_system(self):
        values = run([("modeOff", "up")], {"running": 1})
        self.assertEqual((values["mode"], values["running"]), (0, 0))
        self.assertEqual((values["stateText.txt"], values["stateText.pco"]), ("Off", GREY))
        self.assertEqual(values["stateIcon.pic"], picture("state/off"))


class TickTest(unittest.TestCase):

    def test_a_minute_of_heating(self):
        # 20.5 is more than the gap below 21.0: heating starts. The room loses
        # (8.0 - 20.5) / 240, 0.05 degrees, and heating adds 0.15.
        values = run([("tick", "timer")])
        self.assertEqual(values["running"], 1)
        self.assertEqual(values["room"], 2050 - 5 + 15)
        self.assertEqual((values["stateText.txt"], values["stateText.pco"]), ("Heating", HEAT))
        self.assertEqual(values["stateIcon.pic"], picture("state/heating"))
        self.assertEqual(values["roomText.txt"], "20.6°")

    def test_the_target_follows_the_schedule(self):
        values = run([("tick", "timer")], {"rtc3": 9})
        self.assertEqual((values["target"], values["targetText.txt"]), (1700, "17.0°"))

    def test_a_held_target_stays(self):
        values = run([("tick", "timer")], {"rtc3": 9, "following": 0})
        self.assertEqual(values["target"], 2100)

    def test_the_room_cools_down_while_off(self):
        values = run([("tick", "timer")], {"mode": 0})
        self.assertEqual((values["running"], values["room"]), (0, 2045))


class NavigationTest(unittest.TestCase):

    def test_each_tab_opens_its_page(self):
        for tab, page in (("navHome", "home"), ("navSchedule", "schedule"), ("navDay", "day"),
                          ("navSettings", "settings")):
            with self.subTest(tab=tab):
                self.assertEqual(run([(tab, "up")])["page opened"], page)


if __name__ == "__main__":
    unittest.main()
