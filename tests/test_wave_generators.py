"""The waveform generator (testing/wave_generators.py): its shapes, its
settings and their file, and its points in a simulation
(testing/simulation.py)."""
from fractions import Fraction
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from nxwright import NxwrightError
from nxwright.testing.simulation import Simulation
from nxwright.testing.wave_generators import (GeneratorRun, generator_from_json,
                                              generator_settings, generator_to_json,
                                              read_generator_file, wave_value)
from tests.test_simulation import SimulationTestCase, placed, table


def settings(**given):
    """The GeneratorSettings of a generator feeding channel 0 of page0's
    chart, with the generator's own settings `given`; `channels`, when
    given, replaces the channel list."""
    channels = given.pop("channels", [{"channel": 0}])
    return generator_settings(dict({"waveforms": [{"page": "page0", "waveform": "chart"}],
                                    "channels": channels}, **given), "test")


def points(generator: GeneratorRun, count: int) -> list:
    """The next `count` ticks' values of the generator's first channel."""
    return [generator.tick()[0][1] for _ in range(count)]


class ShapeTest(unittest.TestCase):

    def wave(self, **given):
        generator = settings(minimum=0, maximum=100, **given)
        return generator.wave(generator.channels[0])

    def test_each_shape_through_its_cycle(self):
        positions = [Fraction(step, 8) for step in range(8)]
        for shape, expected in (("sine", [0, 15, 50, 85, 100, 85, 50, 15]),
                                ("square", [100, 100, 100, 100, 0, 0, 0, 0]),
                                ("triangle", [0, 25, 50, 75, 100, 75, 50, 25]),
                                ("sawtooth", [0, 13, 25, 38, 50, 63, 75, 88]),
                                ("inverted-sawtooth", [100, 88, 75, 63, 50, 38, 25, 13])):
            with self.subTest(shape=shape):
                self.assertEqual([wave_value(self.wave(shape=shape), at) for at in positions],
                                 expected)

    def test_a_pulse_is_high_for_its_duty(self):
        wave = self.wave(shape="pulse", duty=25)
        self.assertEqual([wave_value(wave, Fraction(step, 8)) for step in range(8)],
                         [100, 100, 0, 0, 0, 0, 0, 0])

    def test_the_sine_starts_at_the_minimum_and_rises(self):
        # As the Nextion Editor's generator draws it.
        run = GeneratorRun(settings(shape="sine", minimum=10, maximum=50, period=4), 0)
        self.assertEqual(points(run, 5), [10, 30, 50, 30, 10])

    def test_a_custom_wave_plays_its_values_in_a_loop(self):
        run = GeneratorRun(settings(shape="custom", values=[5, 9, 200]), 0)
        self.assertEqual(points(run, 5), [5, 9, 200, 5, 9])

    def test_random_values_and_noise_are_the_same_each_time_a_generator_starts(self):
        for given in ({"shape": "random", "minimum": 20, "maximum": 30},
                      {"shape": "sine", "noise": 10}):
            with self.subTest(given=given):
                first = points(GeneratorRun(settings(**given), 0), 50)
                self.assertEqual(points(GeneratorRun(settings(**given), 0), 50), first)
                self.assertGreater(len(set(first)), 5)
        values = points(GeneratorRun(settings(shape="random", minimum=20, maximum=30), 0), 200)
        self.assertEqual((min(values), max(values)), (20, 30))

    def test_noise_keeps_points_from_0_to_255(self):
        for shape, value, extreme in (("custom", 250, 255), ("custom", 3, 0)):
            run = GeneratorRun(settings(shape=shape, values=[value], noise=40), 0)
            self.assertIn(extreme, points(run, 100))
            self.assertTrue(all(0 <= point <= 255 for point in points(run, 100)))

    def test_a_channel_overrides_the_generators_settings(self):
        run = GeneratorRun(settings(shape="square", maximum=80, period=2, interval=10,
                                    channels=[{"channel": 0},
                                              {"channel": 1, "shape": "sawtooth",
                                               "interval": 20}]), 0)
        # Channel 1 starts a quarter into its cycle: a fifth of the way up.
        self.assertEqual([run.tick() for _ in range(3)],
                         [[(0, 80)], [(0, 0), (1, 20)], [(0, 80)]])

    def test_each_channel_starts_a_quarter_cycle_after_the_one_before(self):
        # So that channels with the same wave do not draw over each other.
        run = GeneratorRun(settings(shape="sine", maximum=100, period=4, interval=10,
                                    channels=[{"channel": number} for number in range(4)]), 0)
        self.assertEqual(run.tick(), [(0, 0), (1, 50), (2, 100), (3, 50)])
        self.assertEqual(run.tick(), [(0, 50), (1, 100), (2, 50), (3, 0)])
        # A custom wave starts a quarter of its list further on.
        run = GeneratorRun(settings(shape="custom", values=list(range(8)),
                                    channels=[{"channel": number} for number in range(4)]), 0)
        self.assertEqual(run.tick(), [(0, 0), (1, 2), (2, 4), (3, 6)])

    def test_a_change_keeps_the_waves_place(self):
        run = GeneratorRun(settings(shape="sawtooth", maximum=100, period=4), 0)
        self.assertEqual(points(run, 2), [0, 25])
        # A new period moves on from the place reached, half the cycle.
        run.change(settings(shape="sawtooth", maximum=100, period=8), 20)
        self.assertEqual(points(run, 2), [50, 63])
        # A new shape goes on from the same place, three quarters of it.
        run.change(settings(shape="inverted-sawtooth", maximum=100, period=8), 40)
        self.assertEqual(points(run, 1), [25])


class SettingsFileTest(unittest.TestCase):

    def test_a_file_reads_back_what_was_written(self):
        given = settings(shape="custom", values=[1, 2], interval=5,
                         channels=[{"channel": 0}, {"channel": 2, "noise": 4}])
        text = generator_to_json(given)
        self.assertEqual(generator_from_json(text, "test"), given)
        self.assertEqual(json.loads(text)["nxwrightWaves"], 1)

    def test_a_file_on_disk(self):
        folder = self.enterContext(tempfile.TemporaryDirectory())
        path = Path(folder) / "waves.json"
        path.write_text(generator_to_json(settings()), encoding="utf-8")
        self.assertEqual(read_generator_file(path), settings())
        with self.assertRaisesRegex(NxwrightError, "cannot be read"):
            read_generator_file(path.with_name("missing.json"))

    def test_settings_are_refused_with_their_place(self):
        generator = {"waveforms": [{"page": "page0", "waveform": "chart"}],
                     "channels": [{"channel": 0}]}
        for change, refusal in (
                ({"channels": [{"channel": 0}, {"channel": 1, "shape": "saw"}]},
                 r"generator\.channels\[1\]: shape 'saw' is not a shape"),
                ({"minimum": 90, "maximum": 10},
                 r"generator\.channels\[0\]: minimum 90 is above maximum 10"),
                ({"shape": "custom"},
                 r"generator\.channels\[0\]: a custom wave needs values"),
                ({"interval": 0}, r"generator: interval must be a whole number of 1"),
                ({"maximum": 256},
                 r"generator: maximum must be a whole number from 0 to 255"),
                ({"channels": [{"channel": 4}]},
                 r"generator\.channels\[0\]: channel must be from 0 to 3"),
                ({"channels": [{"channel": 1}, {"channel": 1}]},
                 r"generator: channels lists a channel twice"),
                ({"waveforms": []}, r"generator: waveforms must list one waveform or more"),
                # Settings the generator once had are settings no more.
                ({"phase": 25}, r"generator: phase is not a setting"),
                ({"seed": 3}, r"generator: seed is not a setting"),
                ({"speed": 2}, r"generator: speed is not a setting")):
            with self.subTest(change=change):
                text = json.dumps({"nxwrightWaves": 1, "generator": dict(generator, **change)})
                with self.assertRaisesRegex(NxwrightError, "^waves.json: " + refusal):
                    generator_from_json(text, "waves.json")

    def test_a_custom_wave_ignores_the_minimum_and_the_maximum(self):
        # Its values are played as given, so a minimum above the maximum,
        # here the default of 100, refuses nothing.
        run = GeneratorRun(settings(shape="custom", minimum=150, values=[7, 8]), 0)
        self.assertEqual(points(run, 2), [7, 8])

    def test_other_files_are_refused(self):
        for text, refusal in (("{", "not JSON"), ("{}", "not a waveform generator's file"),
                              ('{"nxwrightWaves": 2, "generator": {}}',
                               "nxwrightWaves 2 is not a version nxwright reads"),
                              ('{"nxwrightWaves": 1}', "a generator must be a JSON object")):
            with self.subTest(text=text):
                with self.assertRaisesRegex(NxwrightError, refusal):
                    generator_from_json(text, "waves.json")


class GeneratorInSimulationTest(SimulationTestCase):
    """A chart of two channels, 10 points wide, on page0; another on second."""

    def setUp(self):
        super().setUp()
        self.program("page page0\n")
        self.page("page0", [table("chart", "waveform", x=0, y=0, w=10, h=50, ch=2),
                            placed("go", "button", 300, 0)], """\
on go.down:
  page second
""")
        self.page("second", [table("other", "waveform", x=0, y=0, w=10, h=50, ch=1)])

    def sine(self, **given):
        return settings(**dict({"shape": "sine", "minimum": 0, "maximum": 100, "period": 4,
                                "interval": 20}, **given))

    def test_points_arrive_on_time_through_add(self):
        simulation = Simulation(self.root)
        simulation.start_generator(self.sine())
        simulation.advance(19)
        self.assertEqual(simulation.waves(), {})
        simulation.advance(61)
        self.assertEqual(simulation.waves(), {"chart": {0: [0, 50, 100, 50]}})

    def test_points_count_apart_from_the_pages_other_changes(self):
        # So that the generator's points bring no drawing of the whole page.
        simulation = Simulation(self.root)
        simulation.start_generator(self.sine(channels=[{"channel": 0}, {"channel": 1}]))
        changes, points = simulation.changes, simulation.wave_changes
        simulation.advance(100)
        self.assertEqual((simulation.changes, simulation.wave_changes), (changes, points + 10))
        # A typed add is an instruction like any other: the page is drawn.
        simulation.serial_input("add 1,0,5")
        self.assertEqual((simulation.changes, simulation.wave_changes),
                         (changes + 1, points + 11))
        simulation.serial_input("cle 1,255")
        self.assertEqual(simulation.wave_changes, points + 12)
        # A point the screen refuses counts as a change of the page, because
        # nothing tells that its instruction changed nothing. The generator
        # never sends such a point, since it skips a channel that a waveform
        # lacks, so this test runs one directly.
        changes = simulation.changes
        simulation._run_points(["add 1,0,5", "add 1,3,5"])
        self.assertEqual(simulation.changes, changes + 1)

    def test_a_tick_runs_its_points_on_one_view(self):
        simulation = Simulation(self.root)
        simulation.start_generator(self.sine(channels=[{"channel": 0}, {"channel": 1}]))
        with mock.patch.object(Simulation, "_view", autospec=True,
                               side_effect=Simulation._view) as view:
            simulation.advance(20)
        self.assertEqual(view.call_count, 1)
        self.assertEqual(simulation.waves(), {"chart": {0: [0], 1: [50]}})

    def test_the_log_tells_the_start_and_the_stop_not_each_point(self):
        simulation = Simulation(self.root)
        feeding = self.sine(channels=[{"channel": 0}, {"channel": 1}])
        simulation.start_generator(feeding)
        simulation.advance(100)
        self.assertEqual(simulation.generator(), feeding)
        simulation.stop_generator()
        simulation.advance(100)
        self.assertEqual([line for _, line in simulation.log],
                         ["the waveform generator starts, sending to channels 0, 1 of "
                          "page0.chart", "the waveform generator stops"])
        self.assertEqual(len(simulation.waves()["chart"][0]), 5)
        self.assertIsNone(simulation.generator())

    def test_a_start_replaces_the_generator_running(self):
        simulation = Simulation(self.root)
        simulation.start_generator(self.sine(shape="sawtooth"))
        simulation.advance(40)
        # Its waves start again, and the one before sends no more.
        simulation.start_generator(self.sine(shape="square", channels=[{"channel": 1}]))
        simulation.advance(40)
        self.assertEqual(simulation.waves(), {"chart": {0: [0, 25], 1: [100, 0]}})

    def test_each_point_is_answered_as_bkcmd_asks(self):
        simulation = Simulation(self.root)
        simulation.serial_input("bkcmd=3")
        simulation.start_generator(self.sine(channels=[{"channel": 0}, {"channel": 1}]))
        before = len(simulation.log)
        simulation.advance(20)
        self.assertEqual([line for _, line in simulation.log[before:]],
                         ["SIM SEND: 01 ff ff ff", "SIM SEND: 01 ff ff ff"])

    def test_com_stop_holds_the_points(self):
        simulation = Simulation(self.root)
        simulation.start_generator(self.sine())
        simulation.serial_input("com_stop")
        simulation.advance(60)
        self.assertEqual(simulation.waves(), {})
        simulation.serial_input("com_star")
        self.assertEqual(simulation.waves(), {"chart": {0: [0, 50, 100]}})
        self.assertEqual([line for _, line in simulation.log if "held" in line],
                         ["the waveform generator's points are held: the serial line is "
                          "stopped", "the waveform generator's held points run"])

    def test_each_hold_is_told_in_the_log(self):
        simulation = Simulation(self.root)
        simulation.start_generator(self.sine())
        simulation.serial_input("com_stop")
        simulation.advance(40)
        # A start again ends the hold, and drops the points it held.
        simulation.start_again()
        simulation.serial_input("com_stop")
        simulation.advance(40)
        self.assertEqual(len([line for _, line in simulation.log
                              if "points are held" in line]), 2)

    def test_during_a_transfer_the_points_arrive_as_bytes(self):
        simulation = Simulation(self.root)
        simulation.start_generator(self.sine())
        # The chart's ID is 1: the transfer takes the next 4 bytes as points.
        simulation.serial_input("addt 1,1,4")
        before = len(simulation.log)
        simulation.advance(20)
        self.assertEqual(simulation.waves(), {"chart": {1: list(b"add ")}})
        # The rest of the point arrives as an instruction the screen refuses,
        # which the log shows as it shows any.
        self.assertEqual([line for _, line in simulation.log[before:]],
                         ["SIM SEND: fd ff ff ff", "SIM RECV: 1,0,0", "SIM SEND: 00 ff ff ff"])

    def test_a_page_not_shown_gets_nothing_and_its_wave_goes_on(self):
        simulation = Simulation(self.root)
        simulation.start_generator(settings(
            waveforms=[{"page": "second", "waveform": "other"}], shape="sawtooth",
            maximum=100, period=4, interval=20))
        simulation.advance(40)
        self.assertEqual(simulation.waves(), {})
        simulation.press("go", 300, 0)
        simulation.release()
        simulation.advance(40)
        # Two points went by unsent, at 20 and 40.
        self.assertEqual(simulation.waves(), {"other": {0: [50, 75]}})

    def test_a_timer_of_the_same_moment_runs_first(self):
        self.page("page0", [table("chart", "waveform", x=0, y=0, w=10, h=50, ch=2),
                            table("tick", "timer", tim=60, en=1)], """\
on tick.timer:
  cle chart.id,0
""")
        simulation = Simulation(self.root)
        simulation.start_generator(self.sine(interval=60))
        simulation.advance(60)
        # The timer cleared the channel, then the generator's point came.
        self.assertEqual(simulation.waves(), {"chart": {0: [0]}})

    def test_points_keep_the_screen_awake_and_wake_it(self):
        simulation = Simulation(self.root)
        simulation.serial_input("ussp=1")
        simulation.start_generator(self.sine())
        simulation.advance(3000)
        self.assertFalse(simulation.asleep)
        simulation.serial_input("sleep=1")
        simulation.advance(40)
        self.assertTrue(simulation.asleep)       # usup is 0: the points run asleep
        self.assertEqual(len(simulation.waves()["chart"][0]), 10)
        simulation.serial_input("usup=1")
        simulation.advance(20)
        self.assertFalse(simulation.asleep)

    def test_a_start_again_keeps_the_generators_pace(self):
        simulation = Simulation(self.root)
        simulation.start_generator(self.sine())
        simulation.advance(30)
        simulation.start_again()
        # Its next point was due at 40, 10 after the start again.
        self.assertEqual(simulation.next_due(), 10)
        simulation.advance(10)
        self.assertEqual(simulation.waves(), {"chart": {0: [50]}})

    def test_a_generator_is_refused_for_a_waveform_or_channel_the_app_lacks(self):
        simulation = Simulation(self.root)
        for given, refusal in (
                ({"waveforms": [{"page": "third", "waveform": "chart"}]}, "has no page third"),
                ({"waveforms": [{"page": "page0", "waveform": "go"}]}, "has no waveform go"),
                ({"channels": [{"channel": 2}]},
                 "none of its waveforms has a channel 2. The most channels any of them has "
                 "is 2")):
            with self.subTest(given=given):
                with self.assertRaisesRegex(NxwrightError, refusal):
                    simulation.start_generator(settings(**given))
        self.assertIsNone(simulation.generator())
        for act in (simulation.stop_generator, lambda: simulation.change_generator(self.sine())):
            with self.assertRaisesRegex(NxwrightError, "no waveform generator is running"):
                act()

    def test_a_channel_goes_only_to_the_waveforms_that_have_it(self):
        self.page("page0", [table("chart", "waveform", x=0, y=0, w=10, h=50, ch=2),
                            table("strip", "waveform", x=0, y=100, w=10, h=50, ch=1)])
        simulation = Simulation(self.root)
        simulation.serial_input("bkcmd=3")
        simulation.start_generator(settings(
            waveforms=[{"page": "page0", "waveform": "chart"},
                       {"page": "page0", "waveform": "strip"}],
            shape="square", period=4, interval=20, channels=[{"channel": 0}, {"channel": 1}]))
        before = len(simulation.log)
        simulation.advance(40)
        # Channel 1 is a quarter cycle ahead of channel 0.
        self.assertEqual(simulation.waves(), {"chart": {0: [100, 100], 1: [100, 0]},
                                              "strip": {0: [100, 100]}})
        # Nothing went to the channel the strip lacks: three points a tick,
        # each answered as bkcmd asks, and no refusal.
        self.assertEqual([line for _, line in simulation.log[before:]],
                         ["SIM SEND: 01 ff ff ff"] * 6)
        # Its `ch` is looked at as the points go: a channel the chart's code
        # takes away gets no more points.
        simulation.fields["page0"]["chart.ch"] = 1
        simulation.advance(20)
        self.assertEqual(simulation.waves()["chart"][1], [100, 0])

    def test_a_change_takes_effect_at_the_next_point(self):
        simulation = Simulation(self.root)
        simulation.start_generator(self.sine())
        simulation.advance(40)
        simulation.change_generator(self.sine(maximum=50))
        simulation.advance(40)
        # Half way through its cycle, with a lower maximum.
        self.assertEqual(simulation.waves(), {"chart": {0: [0, 50, 50, 25]}})


if __name__ == "__main__":
    unittest.main()
